"""Review eligibility, duplicates, moderation tests."""
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User, UserRole
from marketplace.models import Enquiry, EnquiryStatus
from tutors.models import TutorProfile

from .models import Review, ReviewStatus
from .services import can_review, create_review


@override_settings(RATELIMIT_ENABLE=False)
class ReviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tutor_user = User.objects.create_user(
            email="rev-tutor@example.com", password="Passw0rd!23", role=UserRole.TUTOR)
        cls.tutor = TutorProfile.objects.create(user=cls.tutor_user, is_published=True)
        cls.student = User.objects.create_user(
            email="rev-student@example.com", password="Passw0rd!23", role=UserRole.STUDENT)

    def test_not_eligible_without_accepted_enquiry(self):
        allowed, reason = can_review(self.student, self.tutor)
        self.assertFalse(allowed)

    def test_eligible_after_accepted_enquiry_and_rating_updates(self):
        Enquiry.objects.create(sender=self.student, tutor=self.tutor,
                               message="Hi", status=EnquiryStatus.ACCEPTED)
        review = create_review(self.student, self.tutor, 5, "Great", "Very patient.")
        self.assertEqual(review.status, ReviewStatus.PUBLISHED)
        self.tutor.refresh_from_db()
        self.assertEqual(float(self.tutor.average_rating), 5.0)
        self.assertEqual(self.tutor.reviews_count, 1)

    def test_duplicate_review_blocked(self):
        Enquiry.objects.create(sender=self.student, tutor=self.tutor,
                               message="Hi", status=EnquiryStatus.ACCEPTED)
        create_review(self.student, self.tutor, 5, "Great", "Nice")
        with self.assertRaises(PermissionError):
            create_review(self.student, self.tutor, 4, "Again", "Dup")

    def test_self_review_blocked(self):
        allowed, _ = can_review(self.tutor_user, self.tutor)
        self.assertFalse(allowed)

    def test_review_view_post_and_redirect(self):
        Enquiry.objects.create(sender=self.student, tutor=self.tutor,
                               message="Hi", status=EnquiryStatus.ACCEPTED)
        self.client.force_login(self.student)
        response = self.client.post(reverse("reviews:create", args=[self.tutor.slug]),
                                    {"rating": 4, "title": "Good", "text": "Helpful tutor."})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Review.objects.filter(reviewer=self.student).exists())
