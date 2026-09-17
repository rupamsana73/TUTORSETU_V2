"""API tests: auth, permissions, throttling config, error envelope."""
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User, UserRole
from core.models import Subject, SubjectCategory
from locations.models import Location
from marketplace.models import Enquiry, EnquiryStatus, SavedTutor
from tutors.models import TutorProfile

FAST_THROTTLES = {  # high limits so ordinary API tests aren't throttled
    "anon": "10000/min", "user": "10000/min", "auth": "3/min",
    "register": "10000/min", "password_reset": "10000/min",
    "messaging": "10000/min", "enquiry": "10000/min",
    "review": "10000/min", "upload": "10000/min",
}


@override_settings(RATELIMIT_ENABLE=False, REST_FRAMEWORK={
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticatedOrReadOnly"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 12,
    "DEFAULT_THROTTLE_RATES": FAST_THROTTLES,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "api.exceptions.api_exception_handler",
})
class APIBase(TestCase):
    def setUp(self):
        self.api = APIClient()

    @classmethod
    def setUpTestData(cls):
        cls.location = Location.objects.create(city="Kolkata", area="API-test")
        cls.category = SubjectCategory.objects.create(name="School-api")
        cls.subject = Subject.objects.create(name="Maths-api", category=cls.category)
        cls.tutor_user = User.objects.create_user(
            email="api-tutor@example.com", password="Passw0rd!23", role=UserRole.TUTOR,
        )
        cls.tutor = TutorProfile.objects.create(
            user=cls.tutor_user, is_published=True, hourly_fee=300,
        )
        cls.tutor.subjects.add(cls.subject)
        cls.student = User.objects.create_user(
            email="api-student@example.com", password="Passw0rd!23", role=UserRole.STUDENT,
        )


class PublicAPITests(APIBase):
    def test_subjects_list(self):
        response = self.api.get("/api/subjects/")
        self.assertEqual(response.status_code, 200)

    def test_tutors_list_and_filter(self):
        response = self.api.get("/api/tutors/")
        self.assertEqual(response.status_code, 200)
        response = self.api.get("/api/tutors/", {"subject": self.subject.pk})
        self.assertEqual(response.status_code, 200)

    def test_location_privacy_filtering(self):
        response = self.api.get("/api/locations/")
        self.assertEqual(response.status_code, 200)
        for item in response.json():
            self.assertNotIn("pincode", item)
            self.assertNotIn("latitude", item)


class AuthAPITests(APIBase):
    def test_register_login_logout(self):
        response = self.api.post("/api/auth/register/", {
            "role": "STUDENT", "full_name": "API User",
            "email": "apiuser@example.com", "password": "Secur3Pass!",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["role"], "STUDENT")

        response = self.api.post("/api/auth/login/", {
            "email": "apiuser@example.com", "password": "Secur3Pass!",
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        response = self.api.post("/api/auth/logout/")
        self.assertTrue(response.json()["success"])

    def test_bad_login_generic_error(self):
        response = self.api.post("/api/auth/login/", {
            "email": "nobody@example.com", "password": "nope1234",
        }, format="json")
        self.assertEqual(response.status_code, 401)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertNotIn("does not exist", str(body).lower())

    def test_register_never_admin(self):
        response = self.api.post("/api/auth/register/", {
            "role": "ADMIN", "full_name": "Hack",
            "email": "hack@example.com", "password": "Secur3Pass!",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="hack@example.com").exists())


class ThrottleTests(APIBase):
    def test_login_throttle_triggers(self):
        # auth scope = 3/min in FAST_THROTTLES
        codes = [
            self.api.post("/api/auth/login/", {
                "email": "x@example.com", "password": "wrongpass",
            }, format="json").status_code
            for _ in range(5)
        ]
        self.assertIn(429, codes)


class ProtectedAPITests(APIBase):
    def test_enquiry_create_requires_student_or_parent(self):
        response = self.api.post("/api/enquiries/", {
            "tutor_slug": self.tutor.slug, "subject": self.subject.pk, "message": "Hi",
        }, format="json")
        self.assertIn(response.status_code, (401, 403))
        # Tutor cannot enquire as a student would
        self.api.force_authenticate(self.tutor_user)
        response = self.api.post("/api/enquiries/", {
            "tutor_slug": self.tutor.slug, "subject": self.subject.pk, "message": "Hi",
        }, format="json")
        self.assertEqual(response.status_code, 403)

    def test_saved_tutor_flow(self):
        self.api.force_authenticate(self.student)
        response = self.api.post("/api/saved-tutors/", {"tutor": self.tutor.pk}, format="json")
        self.assertEqual(response.status_code, 201)
        response = self.api.post("/api/saved-tutors/", {"tutor": self.tutor.pk}, format="json")
        self.assertEqual(response.status_code, 400)  # duplicate
        saved = SavedTutor.objects.get(user=self.student)
        response = self.api.delete(f"/api/saved-tutors/{saved.pk}/")
        self.assertEqual(response.status_code, 204)

    def test_review_api_eligibility(self):
        self.api.force_authenticate(self.student)
        response = self.api.post("/api/reviews/", {
            "tutor_slug": self.tutor.slug, "rating": 5, "title": "T", "text": "Good",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        Enquiry.objects.create(sender=self.student, tutor=self.tutor,
                               message="e", status=EnquiryStatus.ACCEPTED)
        response = self.api.post("/api/reviews/", {
            "tutor_slug": self.tutor.slug, "rating": 5, "title": "T", "text": "Good",
        }, format="json")
        self.assertEqual(response.status_code, 201)

    def test_error_envelope_shape(self):
        self.api.force_authenticate(self.student)
        response = self.api.get("/api/saved-tutors/999999/")
        body = response.json()
        self.assertEqual(response.status_code, 404)
        self.assertIn("success", body)
        self.assertIn("message", body)
        self.assertIn("errors", body)
        self.assertNotIn("traceback", str(body).lower())
