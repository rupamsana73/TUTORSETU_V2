"""Auth, RBAC, IDOR and account-security tests."""
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from accounts.services import send_verification_email
from accounts.tokens import email_verification_token
from core.models import Board, ClassLevel
from locations.models import Location
from parents.models import ParentProfile, StudentChild
from tutors.models import TeachingMode, TutorProfile

from .models import AccountStatus, User, UserRole


@override_settings(RATELIMIT_ENABLE=False)
class BaseAccountsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.board = Board.objects.create(name="CBSE-test")
        cls.class_level = ClassLevel.objects.create(name="Class 10 test", order=10)
        cls.location = Location.objects.create(city="Howrah", area="Shibpur-test")

    def make_user(self, email, role, password="Passw0rd!23", **kwargs):
        return User.objects.create_user(email=email, password=password, role=role, **kwargs)

    def make_tutor(self, email="tutor@example.com", **kwargs):
        user = self.make_user(email, UserRole.TUTOR, **kwargs)
        profile = TutorProfile.objects.create(
            user=user, teaching_mode=TeachingMode.BOTH, is_published=True,
            city=self.location, hourly_fee=300,
        )
        return user, profile


class RegistrationTests(BaseAccountsTest):
    def test_student_registration_creates_profile(self):
        response = self.client.post(reverse("accounts:register_role", args=["student"]), {
            "full_name": "New Student", "email": "newstudent@example.com",
            "phone": "9000000001", "password1": "Secur3Pass!", "password2": "Secur3Pass!",
            "class_level": self.class_level.pk, "board": self.board.pk,
            "preferred_location": self.location.pk,
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="newstudent@example.com")
        self.assertEqual(user.role, UserRole.STUDENT)
        self.assertTrue(hasattr(user, "student_profile"))
        self.assertFalse(user.email_verified)

    def test_tutor_registration_creates_profile(self):
        response = self.client.post(reverse("accounts:register_role", args=["tutor"]), {
            "full_name": "New Tutor", "email": "newtutor@example.com",
            "phone": "9000000002", "password1": "Secur3Pass!", "password2": "Secur3Pass!",
            "gender": "FEMALE", "city": self.location.pk, "teaching_mode": "BOTH",
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="newtutor@example.com")
        self.assertEqual(user.role, UserRole.TUTOR)
        self.assertTrue(hasattr(user, "tutor_profile"))

    def test_cannot_register_as_admin(self):
        self.client.post(reverse("accounts:register_role", args=["student"]), {
            "full_name": "Sneaky", "email": "sneaky@example.com",
            "password1": "Secur3Pass!", "password2": "Secur3Pass!",
            "class_level": self.class_level.pk, "board": self.board.pk,
            "preferred_location": self.location.pk, "role": "ADMIN",
        })
        user = User.objects.get(email="sneaky@example.com")
        self.assertNotEqual(user.role, UserRole.ADMIN)
        self.assertFalse(user.is_superuser)

    def test_invalid_registration_role_redirects(self):
        response = self.client.get(reverse("accounts:register_role", args=["superadmin"]))
        self.assertEqual(response.status_code, 302)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"],
    RATELIMIT_ENABLE=False,
)
class EmailVerificationFlowTests(BaseAccountsTest):
    def setUp(self):
        mail.outbox.clear()

    def _register_student(self, email):
        response = self.client.post(
            reverse("accounts:register_role", args=["student"]),
            {
                "full_name": "Verified Student",
                "email": email,
                "phone": "9000000009",
                "password1": "Secur3Pass!",
                "password2": "Secur3Pass!",
                "class_level": self.class_level.pk,
                "board": self.board.pk,
                "preferred_location": self.location.pk,
            },
        )
        user = User.objects.get(email=email)
        return response, user

    def test_registration_creates_user_and_sends_verification_email(self):
        email = "verify-me@example.com"
        response, user = self._register_student(email)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(user.email_verified)
        self.assertEqual(len(mail.outbox), 1)

        message = mail.outbox[0]
        self.assertEqual(message.to, [email])
        self.assertEqual(message.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertIn("TutorSetu", message.body)
        self.assertIn("verify your email", message.body.lower())
        self.assertIn("/verify-email/", message.body)
        self.assertIn("3 days", message.body)
        self.assertNotIn("password", message.body.lower())
        self.assertNotIn("admin", [addr.lower() for addr in message.to])

    def test_api_registration_triggers_verification_email(self):
        client = APIClient()
        payload = {
            "role": UserRole.STUDENT,
            "full_name": "API Student",
            "email": "api-verify@example.com",
            "phone": "9000000010",
            "password": "Secur3Pass!",
        }

        response = client.post("/api/auth/register/", payload, format="json")

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="api-verify@example.com")
        self.assertFalse(user.email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["api-verify@example.com"])
        self.assertEqual(mail.outbox[0].from_email, settings.DEFAULT_FROM_EMAIL)

    def test_valid_verification_link_marks_user_verified(self):
        _, user = self._register_student("verified-user@example.com")
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = email_verification_token.make_token(user)

        response = self.client.get(reverse("accounts:verify_email", args=[uid, token]))

        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.email_verified)

    def test_invalid_verification_link_is_rejected(self):
        _, user = self._register_student("invalid-user@example.com")
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        response = self.client.get(reverse("accounts:verify_email", args=[uid, "bad-token"]))

        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertFalse(user.email_verified)

    def test_verification_email_delivery_failure_is_not_silently_hidden(self):
        user = self.make_user("smtp-fail@example.com", UserRole.STUDENT)

        with patch("accounts.services.send_mail", side_effect=Exception("SMTP failure")):
            self.assertFalse(send_verification_email(None, user))


class LoginTests(BaseAccountsTest):
    def test_login_logout_flow(self):
        self.make_user("loginme@example.com", UserRole.STUDENT)
        response = self.client.post(reverse("accounts:login"), {
            "username": "loginme@example.com", "password": "Passw0rd!23",
        })
        self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse("students:dashboard"))
        self.assertEqual(response.status_code, 302)  # redirected to login

    def test_get_logout_not_allowed(self):
        response = self.client.get(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 405)

    def test_failed_login_generic_error(self):
        response = self.client.post(reverse("accounts:login"), {
            "username": "nosuch@example.com", "password": "whatever",
        })
        self.assertContains(response, "Invalid email or password", status_code=200)

    def test_suspended_user_cannot_login(self):
        self.make_user("suspended@example.com", UserRole.STUDENT,
                       status=AccountStatus.SUSPENDED)
        response = self.client.post(reverse("accounts:login"), {
            "username": "suspended@example.com", "password": "Passw0rd!23",
        }, follow=True)
        self.assertFalse(response.context["user"].is_authenticated)


class RBACTests(BaseAccountsTest):
    def test_student_cannot_access_admin_dashboard(self):
        self.make_user("s1@example.com", UserRole.STUDENT)
        self.client.login(username="s1@example.com", password="Passw0rd!23")
        response = self.client.get(reverse("manage:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_student_cannot_access_tutor_dashboard(self):
        self.make_user("s2@example.com", UserRole.STUDENT)
        self.client.login(username="s2@example.com", password="Passw0rd!23")
        response = self.client.get(reverse("tutors:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_tutor_cannot_access_student_dashboard(self):
        user, _ = self.make_tutor("t2@example.com")
        self.client.login(username="t2@example.com", password="Passw0rd!23")
        response = self.client.get(reverse("students:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_manage_dashboard(self):
        self.make_user("admin2@example.com", UserRole.ADMIN,
                       is_staff=True, _allow_admin=True)
        self.client.force_login(User.objects.get(email="admin2@example.com"))
        response = self.client.get(reverse("manage:dashboard"))
        self.assertEqual(response.status_code, 200)


class IDORTests(BaseAccountsTest):
    def test_parent_cannot_edit_other_parents_child(self):
        p1 = self.make_user("p1@example.com", UserRole.PARENT)
        ParentProfile.objects.create(user=p1)
        p2 = self.make_user("p2@example.com", UserRole.PARENT)
        profile2 = ParentProfile.objects.create(user=p2)
        child = StudentChild.objects.create(parent=profile2, name="Other Child")
        self.client.login(username="p1@example.com", password="Passw0rd!23")
        response = self.client.get(reverse("parents:child_edit", args=[child.pk]))
        self.assertEqual(response.status_code, 404)
        response = self.client.post(reverse("parents:child_delete", args=[child.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(StudentChild.objects.filter(pk=child.pk).exists())

    def test_account_status_middleware_blocks_suspended(self):
        user = self.make_user("blocked@example.com", UserRole.STUDENT)
        self.client.force_login(user)
        user.status = AccountStatus.SUSPENDED
        user.save()
        response = self.client.get(reverse("core:home"), follow=True)
        self.assertFalse(response.context["user"].is_authenticated)


@override_settings(RATELIMIT_ENABLE=True)
class RateLimitTests(TestCase):
    """Verify brute-force protection actually triggers (not just configured)."""

    def test_login_rate_limit_blocks_after_threshold(self):
        codes = []
        for i in range(7):
            response = self.client.post(
                reverse("accounts:login"),
                {"username": f"brute{i}@example.com", "password": "wrongpass1"},
                REMOTE_ADDR="10.9.9.9",
            )
            codes.append(response.status_code)
        # Limit: 5 per 15 minutes per IP → later attempts must be denied (403)
        self.assertEqual(codes[:5], [200] * 5)
        self.assertIn(403, codes[5:])

    def test_register_rate_limit_blocks_after_threshold(self):
        from core.models import Board, ClassLevel
        from locations.models import Location

        board = Board.objects.create(name="B-rl")
        cls = ClassLevel.objects.create(name="C-rl")
        loc = Location.objects.create(city="Howrah", area="Shibpur-rl")
        codes = []
        for i in range(7):
            response = self.client.post(
                reverse("accounts:register_role", args=["student"]),
                {
                    "full_name": f"U{i}", "email": f"rl{i}@example.com",
                    "password1": "Secur3Pass!", "password2": "Secur3Pass!",
                    "class_level": cls.pk, "board": board.pk,
                    "preferred_location": loc.pk,
                },
                REMOTE_ADDR="10.9.9.10",
            )
            codes.append(response.status_code)
        self.assertIn(403, codes)  # limit 5/hour/IP must eventually block
