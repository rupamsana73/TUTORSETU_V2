"""Core security: headers, error pages, upload validators, audit log."""
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest.mock import patch

from core.models import AuditLog
from core.utils import audit
from core.validators import validate_document, validate_image


class SecurityHeadersTests(TestCase):
    def test_security_headers_present(self):
        response = self.client.get("/")
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertIn("geolocation=()", response.headers.get("Permissions-Policy", ""))

    def test_404_page(self):
        response = self.client.get("/definitely-not-a-page/")
        self.assertEqual(response.status_code, 404)

    def test_xss_escaped_in_profile(self):
        """Stored XSS in tutor about must be HTML-escaped in templates."""
        from accounts.models import User, UserRole
        from tutors.models import TutorProfile

        user = User.objects.create_user(
            email="xss@example.com", password="Passw0rd!23", role=UserRole.TUTOR,
        )
        tutor = TutorProfile.objects.create(
            user=user, is_published=True, about="<script>alert(1)</script>",
        )
        response = self.client.get(f"/tutors/{tutor.slug}/")
        self.assertNotContains(response, "<script>alert(1)</script>")


class UploadValidatorTests(TestCase):
    def fake_image(self, name="pic.png", content_type="image/png"):
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (8, 8), color="red").save(buf, format="PNG")
        buf.seek(0)
        return SimpleUploadedFile(name, buf.read(), content_type=content_type)

    def test_valid_image_accepted(self):
        validate_image(self.fake_image())

    def test_executable_rejected(self):
        bad = SimpleUploadedFile("evil.exe", b"MZ\x90", content_type="application/x-msdownload")
        with self.assertRaises(ValidationError):
            validate_image(bad)

    def test_fake_image_content_rejected(self):
        bad = SimpleUploadedFile("pic.png", b"not an image", content_type="image/png")
        with self.assertRaises(ValidationError):
            validate_image(bad)

    def test_wrong_mime_rejected(self):
        bad = SimpleUploadedFile("pic.png", b"x" * 100, content_type="text/html")
        with self.assertRaises(ValidationError):
            validate_document(bad)

    def test_dangerous_extension_rejected(self):
        # PHP/HTML disguised uploads rejected by extension allowlist
        for name in ("evil.php", "evil.html", "evil.svg"):
            bad = SimpleUploadedFile(name, b"x", content_type="application/octet-stream")
            with self.assertRaises(ValidationError, msg=name):
                validate_document(bad)


class AuditLogTests(TestCase):
    def test_audit_writes_record(self):
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.user = type("Anon", (), {"is_authenticated": False})()
        audit(request, "TEST_ACTION", target="thing", metadata={"k": 1})
        log = AuditLog.objects.get(action="TEST_ACTION")
        self.assertEqual(log.target, "thing")


class AdminUserDeletionTests(TestCase):
    def setUp(self):
        from accounts.models import User, UserRole

        self.admin = User.objects.create_superuser(
            email="delete-admin@example.com",
            password="AdminPass!123",
            full_name="Delete Admin",
        )
        self.client.force_login(self.admin)
        self.target_role = UserRole

    def create_target(self, role, email):
        from accounts.models import User

        return User.objects.create_user(
            email=email, password="UserPass!123", full_name="Delete Target", role=role
        )

    def test_admin_can_delete_student_parent_and_tutor(self):
        from accounts.models import UserRole
        from parents.models import ParentProfile
        from students.models import StudentProfile
        from tutors.models import TutorProfile

        student = self.create_target(UserRole.STUDENT, "delete-student@example.com")
        StudentProfile.objects.create(user=student)
        parent = self.create_target(UserRole.PARENT, "delete-parent@example.com")
        ParentProfile.objects.create(user=parent)
        tutor = self.create_target(UserRole.TUTOR, "delete-tutor@example.com")
        TutorProfile.objects.create(user=tutor)

        for user in (student, parent, tutor):
            response = self.client.post(
                reverse("manage:user_delete", args=[user.pk]),
                follow=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertFalse(type(user).objects.filter(pk=user.pk).exists())

    def test_admin_cannot_delete_another_admin(self):
        from accounts.models import User

        other_admin = User.objects.create_superuser(
            email="delete-other-admin@example.com",
            password="AdminPass!123",
            full_name="Other Admin",
        )
        response = self.client.post(reverse("manage:user_delete", args=[other_admin.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(pk=other_admin.pk).exists())
        self.assertFalse(
            AuditLog.objects.filter(
                action="ADMIN_USER_DELETED", target=str(other_admin.pk)
            ).exists()
        )

    def test_admin_user_detail_exposes_confirmation_only_for_deletable_users(self):
        from accounts.models import User

        target = self.create_target(self.target_role.STUDENT, "delete-ui@example.com")
        response = self.client.get(reverse("manage:user_detail", args=[target.pk]))
        self.assertContains(
            response, "Are you sure you want to permanently delete this user?"
        )

        response = self.client.get(
            reverse("manage:user_detail", args=[self.admin.pk])
        )
        self.assertNotContains(
            response, "Are you sure you want to permanently delete this user?"
        )
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_delete_requires_admin_and_post(self):
        from accounts.models import User, UserRole

        target = self.create_target(UserRole.STUDENT, "delete-protected@example.com")
        response = self.client.get(reverse("manage:user_delete", args=[target.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(User.objects.filter(pk=target.pk).exists())

        self.client.logout()
        response = self.client.post(reverse("manage:user_delete", args=[target.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

        for role in (UserRole.STUDENT, UserRole.PARENT, UserRole.TUTOR):
            actor = self.create_target(role, f"actor-{role.lower()}@example.com")
            self.client.force_login(actor)
            response = self.client.post(reverse("manage:user_delete", args=[target.pk]))
            self.assertEqual(response.status_code, 403)
            self.assertTrue(User.objects.filter(pk=target.pk).exists())

    def test_delete_requires_csrf_token(self):
        from accounts.models import UserRole

        target = self.create_target(UserRole.STUDENT, "delete-csrf@example.com")
        csrf_client = self.client.__class__(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)

        response = csrf_client.post(reverse("manage:user_delete", args=[target.pk]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(type(target).objects.filter(pk=target.pk).exists())

    def test_deletion_cascades_related_records_and_preserves_audit(self):
        from accounts.models import UserRole
        from notifications.models import Notification
        from students.models import StudentProfile

        target = self.create_target(UserRole.STUDENT, "delete-related@example.com")
        StudentProfile.objects.create(user=target)
        Notification.objects.create(
            recipient=target, notification_type="GENERIC", title="Test"
        )

        response = self.client.post(reverse("manage:user_delete", args=[target.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(StudentProfile.objects.filter(user_id=target.pk).exists())
        self.assertFalse(Notification.objects.filter(recipient_id=target.pk).exists())
        log = AuditLog.objects.get(
            action="ADMIN_USER_DELETED", target=str(target.pk)
        )
        self.assertEqual(log.user_id, self.admin.pk)
        self.assertEqual(log.metadata["deleted_user_id"], target.pk)
        self.assertEqual(log.metadata["deleted_role"], UserRole.STUDENT)

    def test_tutor_verification_files_are_removed_after_deletion(self):
        from accounts.models import UserRole
        from tutors.models import TutorProfile
        from verification.models import TutorVerification, VerificationDocument

        target = self.create_target(UserRole.TUTOR, "delete-files@example.com")
        tutor = TutorProfile.objects.create(user=target)
        verification = TutorVerification.objects.create(tutor=tutor)
        document = VerificationDocument.objects.create(
            verification=verification,
            document_type="ID_DOCUMENT",
            file=SimpleUploadedFile("id.txt", b"test", content_type="text/plain"),
        )

        with patch.object(document.file.storage, "delete") as delete_file:
            response = self.client.post(reverse("manage:user_delete", args=[target.pk]))

        self.assertEqual(response.status_code, 302)
        delete_file.assert_called_once_with(document.file.name)
        document.file.storage.delete(document.file.name)
