"""Request-level security regression tests."""
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountStatus, User, UserRole
from core.models import Board, ClassLevel, Subject, SubjectCategory
from locations.models import Location
from marketplace.models import (
    Enquiry, EnquiryStatus, SavedTutor, TutorApplication, TutorRequest,
)
from messaging.models import Message
from messaging.services import get_or_create_conversation
from reports.models import Report
from reviews.models import Review
from tutors.models import TeachingMode, TutorProfile
from verification.models import (
    DocumentType, TutorVerification, VerificationDocument,
)


class SecurityFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.location = Location.objects.create(city="Security City", area="Audit Area")
        cls.category = SubjectCategory.objects.create(name="Security Subject Group")
        cls.subject = Subject.objects.create(name="Security Maths", category=cls.category)
        cls.class_level = ClassLevel.objects.create(name="Security Class", order=1)
        cls.board = Board.objects.create(name="Security Board")

        cls.student = User.objects.create_user(
            email="security-student@example.com",
            password="Passw0rd!23",
            role=UserRole.STUDENT,
        )
        cls.other_student = User.objects.create_user(
            email="security-other@example.com",
            password="Passw0rd!23",
            role=UserRole.STUDENT,
        )
        cls.tutor_user = User.objects.create_user(
            email="security-tutor@example.com",
            password="Passw0rd!23",
            role=UserRole.TUTOR,
        )
        cls.other_tutor_user = User.objects.create_user(
            email="security-other-tutor@example.com",
            password="Passw0rd!23",
            role=UserRole.TUTOR,
        )
        cls.admin = User.objects.create_user(
            email="security-admin@example.com",
            password="Passw0rd!23",
            role=UserRole.ADMIN,
            is_staff=True,
            _allow_admin=True,
        )
        cls.tutor = TutorProfile.objects.create(
            user=cls.tutor_user,
            city=cls.location,
            teaching_mode=TeachingMode.BOTH,
            is_published=True,
        )
        cls.other_tutor = TutorProfile.objects.create(
            user=cls.other_tutor_user,
            city=cls.location,
            teaching_mode=TeachingMode.BOTH,
            is_published=True,
        )
        cls.tutor.subjects.add(cls.subject)

    def login_as(self, user):
        self.client.force_login(user)


@override_settings(RATELIMIT_ENABLE=False)
class IDORAndRoleSecurityTests(SecurityFixtureMixin, TestCase):
    def test_user_cannot_modify_another_users_marketplace_objects(self):
        enquiry = Enquiry.objects.create(
            sender=self.other_student,
            tutor=self.tutor,
            subject=self.subject,
            message="Private enquiry",
        )
        request_obj = TutorRequest.objects.create(
            poster=self.other_student,
            title="Private request",
            description="Private description",
        )
        application = TutorApplication.objects.create(
            request=request_obj,
            tutor=self.tutor,
            message="Private application",
        )
        saved = SavedTutor.objects.create(user=self.other_student, tutor=self.tutor)
        self.login_as(self.student)

        self.assertEqual(
            self.client.post(
                reverse("marketplace:withdraw_enquiry", args=[enquiry.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("marketplace:request_close", args=[request_obj.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("marketplace:respond_application", args=[application.pk]),
                {"action": "ACCEPTED"},
            ).status_code,
            404,
        )
        self.assertFalse(
            self.client.post(
                reverse("marketplace:toggle_save", args=[self.tutor.pk])
            ).status_code == 200
        )
        self.assertTrue(SavedTutor.objects.filter(pk=saved.pk).exists())

    def test_user_cannot_read_or_send_in_another_users_conversation(self):
        conversation = get_or_create_conversation([self.other_student, self.tutor_user])
        self.login_as(self.student)
        self.assertEqual(
            self.client.get(
                reverse("messaging:conversation", args=[conversation.pk])
            ).status_code,
            403,
        )
        before = Message.objects.count()
        self.assertEqual(
            self.client.post(
                reverse("messaging:send", args=[conversation.pk]),
                {"body": "Unauthorized"},
            ).status_code,
            403,
        )
        self.assertEqual(Message.objects.count(), before)

    def test_registration_cannot_escalate_role_or_privileges(self):
        response = self.client.post(
            reverse("accounts:register_role", args=["student"]),
            {
                "full_name": "Role Escalation",
                "email": "role-escalation@example.com",
                "password1": "Secur3Pass!",
                "password2": "Secur3Pass!",
                "class_level": self.class_level.pk,
                "board": self.board.pk,
                "preferred_location": self.location.pk,
                "role": UserRole.ADMIN,
                "is_staff": "true",
                "is_superuser": "true",
            },
        )
        self.assertEqual(response.status_code, 302)
        created = User.objects.get(email="role-escalation@example.com")
        self.assertEqual(created.role, UserRole.STUDENT)
        self.assertFalse(created.is_staff)
        self.assertFalse(created.is_superuser)

    def test_api_read_scopes_saved_tutors_to_current_user(self):
        SavedTutor.objects.create(user=self.other_student, tutor=self.tutor)
        api = APIClient()
        api.force_authenticate(self.student)
        response = api.get("/api/saved-tutors/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)


@override_settings(RATELIMIT_ENABLE=False)
class AccountStateAndCsrfTests(SecurityFixtureMixin, TestCase):
    def test_inactive_suspended_and_banned_accounts_cannot_login(self):
        for status in (
            AccountStatus.INACTIVE,
            AccountStatus.SUSPENDED,
            AccountStatus.BANNED,
        ):
            user = User.objects.create_user(
                email=f"{status.lower()}@example.com",
                password="Passw0rd!23",
                role=UserRole.STUDENT,
                status=status,
                is_active=status != AccountStatus.BANNED,
            )
            response = self.client.post(
                reverse("accounts:login"),
                {"username": user.email, "password": "Passw0rd!23"},
                follow=True,
            )
            self.assertFalse(
                response.context["user"].is_authenticated,
                msg=f"{status} account logged in",
            )

    def test_session_unsafe_request_requires_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.student)
        response = csrf_client.post(
            reverse("messaging:start", args=[self.tutor_user.pk])
        )
        self.assertEqual(response.status_code, 403)


@override_settings(RATELIMIT_ENABLE=True)
class RequestLayerRateLimitTests(SecurityFixtureMixin, TestCase):
    def setUp(self):
        cache.clear()

    def _post_until_blocked(self, url, data, limit, **extra):
        statuses = []
        for _ in range(limit + 1):
            response = self.client.post(url, data, **extra)
            statuses.append(response.status_code)
        self.assertTrue(
            any(code in (403, 429) for code in statuses),
            msg=f"Expected throttling for {url}, got {statuses}",
        )
        return statuses

    def test_login_rate_limit_rejects_excess_requests(self):
        statuses = self._post_until_blocked(
            reverse("accounts:login"),
            {"username": "unknown@example.com", "password": "wrong"},
            5,
            REMOTE_ADDR="10.10.10.10",
        )
        self.assertEqual(statuses[:5], [200] * 5)

    def test_registration_rate_limit_does_not_create_excess_users(self):
        before = User.objects.count()
        statuses = self._post_until_blocked(
            reverse("accounts:register_role", args=["student"]),
            {
                "full_name": "Rate Limited",
                "email": "rate-limited@example.com",
                "password1": "Secur3Pass!",
                "password2": "Secur3Pass!",
                "class_level": self.class_level.pk,
                "board": self.board.pk,
                "preferred_location": self.location.pk,
            },
            5,
            REMOTE_ADDR="10.10.10.11",
        )
        self.assertIn(403, statuses)
        self.assertLessEqual(User.objects.count(), before + 1)

    def test_enquiry_rate_limit_is_request_level(self):
        self.login_as(self.student)
        url = reverse("marketplace:send_enquiry", args=[self.tutor.slug])
        statuses = self._post_until_blocked(
            url,
            {"subject": self.subject.pk, "message": "Please help", "teaching_mode": "BOTH"},
            10,
        )
        self.assertEqual(Enquiry.objects.filter(sender=self.student).count(), 1)
        self.assertIn(403, statuses)

    def test_tutor_request_rate_limit_is_request_level(self):
        self.login_as(self.student)
        statuses = self._post_until_blocked(
            reverse("marketplace:request_create"),
            {"title": "Need tutor", "description": "For testing", "mode": "BOTH"},
            10,
        )
        self.assertLessEqual(
            TutorRequest.objects.filter(poster=self.student).count(), 10
        )
        self.assertIn(403, statuses)

    def test_save_tutor_rate_limit_does_not_bypass_user_scoping(self):
        self.login_as(self.student)
        statuses = self._post_until_blocked(
            reverse("marketplace:toggle_save", args=[self.tutor.pk]),
            {},
            60,
        )
        self.assertLessEqual(
            SavedTutor.objects.filter(user=self.student, tutor=self.tutor).count(), 1
        )
        self.assertIn(403, statuses)

    def test_password_reset_rate_limit_rejects_excess_requests(self):
        statuses = self._post_until_blocked(
            reverse("accounts:password_reset"),
            {"email": "unknown-reset@example.com"},
            5,
            REMOTE_ADDR="10.10.10.12",
        )
        self.assertIn(403, statuses)

    def test_application_rate_limit_rejects_excess_requests(self):
        request_obj = TutorRequest.objects.create(
            poster=self.student,
            title="Application target",
            description="Testing applications",
        )
        self.login_as(self.tutor_user)
        statuses = self._post_until_blocked(
            reverse("marketplace:apply", args=[request_obj.pk]),
            {"message": "I can help", "proposed_fee": 300},
            20,
        )
        self.assertLessEqual(
            TutorApplication.objects.filter(request=request_obj).count(), 1
        )
        self.assertIn(403, statuses)

    def test_message_rate_limit_rejects_excess_requests(self):
        conversation = get_or_create_conversation([self.student, self.tutor_user])
        self.login_as(self.student)
        statuses = self._post_until_blocked(
            reverse("messaging:send", args=[conversation.pk]),
            {"body": "Rate limit message"},
            30,
        )
        self.assertLessEqual(Message.objects.filter(conversation=conversation).count(), 30)
        self.assertIn(403, statuses)

    def test_review_rate_limit_rejects_excess_requests(self):
        Enquiry.objects.create(
            sender=self.student,
            tutor=self.tutor,
            subject=self.subject,
            message="Accepted enquiry",
            status=EnquiryStatus.ACCEPTED,
        )
        self.login_as(self.student)
        statuses = self._post_until_blocked(
            reverse("reviews:create", args=[self.tutor.slug]),
            {"rating": 5, "title": "Good", "text": "Helpful"},
            10,
        )
        self.assertLessEqual(Review.objects.filter(reviewer=self.student).count(), 1)
        self.assertIn(403, statuses)

    def test_report_rate_limit_rejects_excess_requests(self):
        self.login_as(self.student)
        statuses = self._post_until_blocked(
            reverse("reports:report", args=["tutor", self.tutor.pk]),
            {"category": "SPAM", "description": "Repeated test report"},
            10,
        )
        self.assertEqual(Report.objects.filter(reporter=self.student).count(), 1)
        self.assertIn(403, statuses)

    def test_upload_rate_limit_rejects_excess_invalid_requests(self):
        self.login_as(self.tutor_user)
        statuses = []
        for _ in range(21):
            response = self.client.post(
                reverse("verification:submit"),
                {
                    "id_document": SimpleUploadedFile(
                        "bad.exe", b"bad", content_type="application/octet-stream"
                    ),
                    "qualification_certificate": SimpleUploadedFile(
                        "bad.exe", b"bad", content_type="application/octet-stream"
                    ),
                },
            )
            statuses.append(response.status_code)
        self.assertIn(403, statuses)
        self.assertFalse(TutorVerification.objects.filter(tutor=self.tutor).exists())

    def test_search_is_read_only_and_does_not_create_records(self):
        before = TutorRequest.objects.count()
        for query in ("math", "security"):
            response = self.client.get(reverse("tutors:list"), {"q": query})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(TutorRequest.objects.count(), before)


@override_settings(RATELIMIT_ENABLE=False)
class UploadAndPrivateDocumentTests(SecurityFixtureMixin, TestCase):
    def _document(self, name="identity.pdf", content_type="application/pdf"):
        verification = TutorVerification.objects.create(tutor=self.tutor)
        return verification, VerificationDocument.objects.create(
            verification=verification,
            document_type=DocumentType.ID_DOCUMENT,
            file=SimpleUploadedFile(name, b"%PDF-test", content_type=content_type),
        )

    def test_invalid_verification_uploads_are_rejected(self):
        self.login_as(self.tutor_user)
        invalid = SimpleUploadedFile(
            "identity.exe", b"not a document", content_type="application/octet-stream"
        )
        response = self.client.post(
            reverse("verification:submit"),
            {
                "id_document": invalid,
                "qualification_certificate": SimpleUploadedFile(
                    "qualification.pdf", b"%PDF-test", content_type="application/pdf"
                ),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TutorVerification.objects.filter(tutor=self.tutor).exists())

    def test_private_document_requires_admin_and_is_not_public_media(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=Path(temp_dir)):
                _, document = self._document()
                self.assertTrue(document.file.name.startswith("private/verification/"))
                anonymous = Client()
                public_url = f"{settings.MEDIA_URL}{document.file.name}"
                self.assertIn(
                    anonymous.get(public_url).status_code,
                    (403, 404),
                )
                self.login_as(self.other_student)
                self.assertEqual(
                    self.client.get(
                        reverse("manage:verification_document", args=[document.pk])
                    ).status_code,
                    403,
                )
                self.login_as(self.admin)
                response = self.client.get(
                    reverse("manage:verification_document", args=[document.pk])
                )
                self.assertEqual(response.status_code, 200)
                response.close()

    def test_malformed_image_upload_is_rejected(self):
        self.login_as(self.tutor_user)
        response = self.client.post(
            reverse("verification:submit"),
            {
                "id_document": SimpleUploadedFile(
                    "identity.pdf", b"%PDF-test", content_type="application/pdf"
                ),
                "qualification_certificate": SimpleUploadedFile(
                    "qualification.pdf", b"%PDF-test", content_type="application/pdf"
                ),
                "profile_photo": SimpleUploadedFile(
                    "photo.png", b"not an image", content_type="image/png"
                ),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TutorVerification.objects.filter(tutor=self.tutor).exists())
