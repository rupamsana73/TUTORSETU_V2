"""Tutor platform, search and matching tests."""
from datetime import time

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User, UserRole
from core.models import ClassLevel, Subject, SubjectCategory
from locations.models import Location

from .models import TeachingMode, TutorAvailability, TutorProfile, VerificationStatus
from .services import MatchPreferences, TutorMatchingService, haversine_km


@override_settings(RATELIMIT_ENABLE=False)
class TutorBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.location = Location.objects.create(
            city="Howrah", area="Shibpur-test", latitude=22.5675, longitude=88.3117
        )
        cls.category = SubjectCategory.objects.create(name="School-test")
        cls.maths = Subject.objects.create(name="Maths-test", category=cls.category)
        cls.physics = Subject.objects.create(name="Physics-test", category=cls.category)
        cls.cls10 = ClassLevel.objects.create(name="Class 10-test", order=10)
        cls.tutor_user = User.objects.create_user(
            email="matchtutor@example.com", password="Passw0rd!23",
            role=UserRole.TUTOR, full_name="Match Tutor",
        )
        cls.tutor = TutorProfile.objects.create(
            user=cls.tutor_user, teaching_mode=TeachingMode.BOTH, is_published=True,
            city=cls.location, hourly_fee=300, experience_years=6,
            verification_status=VerificationStatus.VERIFIED,
        )
        cls.tutor.subjects.add(cls.maths)
        cls.tutor.classes.add(cls.cls10)
        TutorAvailability.objects.create(
            tutor=cls.tutor, weekday=5, start_time=time(10), end_time=time(12)
        )


class MatchingServiceTests(TutorBase):
    def test_subject_and_class_match_scores_high(self):
        prefs = MatchPreferences(subject_id=self.maths.pk, class_level_id=self.cls10.pk)
        results = TutorMatchingService(prefs).match()
        self.assertTrue(results)
        top = results[0]
        self.assertEqual(top.tutor, self.tutor)
        self.assertGreaterEqual(top.score, 50)
        self.assertTrue(top.reasons)

    def test_wrong_subject_excluded(self):
        prefs = MatchPreferences(subject_id=self.physics.pk)
        results = TutorMatchingService(prefs).match()
        self.assertEqual(results, [])

    def test_haversine_distance(self):
        d = haversine_km(22.5675, 88.3117, 22.5726, 88.3639)
        self.assertIsNotNone(d)
        self.assertGreater(d, 3)
        self.assertLess(d, 8)
        self.assertIsNone(haversine_km(None, 88.3, 22.5, 88.3))


class TutorSearchTests(TutorBase):
    def test_list_page_ok_and_filter(self):
        response = self.client.get(reverse("tutors:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Match Tutor")
        response = self.client.get(reverse("tutors:list"), {"subject": self.physics.pk})
        self.assertNotContains(response, "Match Tutor")

    def test_sort_by_fee(self):
        response = self.client.get(reverse("tutors:list"), {"sort": "fee_low"})
        self.assertEqual(response.status_code, 200)

    def test_tutor_detail_and_view_count(self):
        response = self.client.get(reverse("tutors:detail", args=[self.tutor.slug]))
        self.assertEqual(response.status_code, 200)
        self.tutor.refresh_from_db()
        self.assertEqual(self.tutor.profile_views, 1)

    def test_unpublished_profile_hidden(self):
        user = User.objects.create_user(
            email="hidden@example.com", password="Passw0rd!23", role=UserRole.TUTOR,
        )
        hidden = TutorProfile.objects.create(user=user, is_published=False)
        response = self.client.get(reverse("tutors:detail", args=[hidden.slug]))
        self.assertEqual(response.status_code, 403)


class TutorAreaTests(TutorBase):
    def setUp(self):
        self.client.force_login(self.tutor_user)

    def test_onboarding_step1_saves(self):
        response = self.client.post(reverse("tutors:onboarding", args=[1]), {
            "full_name": "Match Tutor", "phone": "9000000099", "gender": "MALE",
            "tagline": "I teach well", "about": "About me text",
        })
        self.assertEqual(response.status_code, 302)
        self.tutor_user.refresh_from_db()
        self.assertEqual(self.tutor_user.phone, "9000000099")

    def test_add_and_delete_availability_slot(self):
        response = self.client.post(reverse("tutors:availability"), {
            "weekday": 1, "start_time": "14:00", "end_time": "16:00",
        })
        self.assertEqual(response.status_code, 302)
        slot = TutorAvailability.objects.get(tutor=self.tutor, weekday=1)
        response = self.client.post(reverse("tutors:delete_slot", args=[slot.pk]))
        self.assertFalse(TutorAvailability.objects.filter(pk=slot.pk).exists())

    def test_invalid_slot_rejected(self):
        response = self.client.post(reverse("tutors:availability"), {
            "weekday": 2, "start_time": "16:00", "end_time": "14:00",
        })
        self.assertEqual(response.status_code, 200)  # form error shown
        self.assertFalse(TutorAvailability.objects.filter(tutor=self.tutor, weekday=2).exists())

    def test_cannot_delete_other_tutors_slot(self):
        other_user = User.objects.create_user(
            email="other@example.com", password="Passw0rd!23", role=UserRole.TUTOR,
        )
        other = TutorProfile.objects.create(user=other_user, is_published=True)
        slot = TutorAvailability.objects.create(
            tutor=other, weekday=3, start_time=time(9), end_time=time(11)
        )
        response = self.client.post(reverse("tutors:delete_slot", args=[slot.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(TutorAvailability.objects.filter(pk=slot.pk).exists())
