"""Marketplace: enquiries, requests, applications, saved tutors."""
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User, UserRole
from core.models import ClassLevel, Subject, SubjectCategory
from locations.models import Location
from notifications.models import Notification, NotificationType
from tutors.models import TeachingMode, TutorProfile

from .models import (
    ApplicationStatus, Enquiry, EnquiryStatus, SavedTutor, TutorApplication,
    TutorRequest, TutorRequestStatus,
)


@override_settings(RATELIMIT_ENABLE=False)
class MarketplaceBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.location = Location.objects.create(city="Kolkata", area="Salt Lake-test")
        cls.category = SubjectCategory.objects.create(name="School-mkt")
        cls.subject = Subject.objects.create(name="Maths-mkt", category=cls.category)
        cls.class_level = ClassLevel.objects.create(name="Class 10-mkt", order=10)
        cls.tutor_user = User.objects.create_user(
            email="mkt-tutor@example.com", password="Passw0rd!23", role=UserRole.TUTOR,
        )
        cls.tutor = TutorProfile.objects.create(
            user=cls.tutor_user, is_published=True, city=cls.location,
            teaching_mode=TeachingMode.BOTH,
        )
        cls.tutor.subjects.add(cls.subject)
        cls.student = User.objects.create_user(
            email="mkt-student@example.com", password="Passw0rd!23", role=UserRole.STUDENT,
        )


class EnquiryTests(MarketplaceBase):
    def setUp(self):
        self.client.force_login(self.student)

    def test_send_enquiry(self):
        response = self.client.post(
            reverse("marketplace:send_enquiry", args=[self.tutor.slug]),
            {"subject": self.subject.pk, "message": "Need help with algebra",
             "teaching_mode": "BOTH"},
        )
        self.assertEqual(response.status_code, 302)
        enquiry = Enquiry.objects.get(sender=self.student, tutor=self.tutor)
        self.assertEqual(enquiry.status, EnquiryStatus.PENDING)
        self.assertTrue(Notification.objects.filter(
            recipient=self.tutor_user, notification_type=NotificationType.NEW_ENQUIRY
        ).exists())

    def test_duplicate_open_enquiry_blocked(self):
        Enquiry.objects.create(sender=self.student, tutor=self.tutor,
                               subject=self.subject, message="first")
        self.client.post(reverse("marketplace:send_enquiry", args=[self.tutor.slug]),
                         {"subject": self.subject.pk, "message": "second",
                          "teaching_mode": "BOTH"})
        self.assertEqual(Enquiry.objects.filter(
            sender=self.student, tutor=self.tutor,
            status__in=[EnquiryStatus.PENDING, EnquiryStatus.CONTACTED]).count(), 1)

    def test_tutor_accept_creates_conversation_and_notification(self):
        enquiry = Enquiry.objects.create(sender=self.student, tutor=self.tutor,
                                         subject=self.subject, message="Hi")
        self.client.force_login(self.tutor_user)
        response = self.client.post(
            reverse("marketplace:respond_enquiry", args=[enquiry.pk]),
            {"action": "accept", "response": "Happy to help"},
        )
        self.assertEqual(response.status_code, 302)
        enquiry.refresh_from_db()
        self.assertEqual(enquiry.status, EnquiryStatus.ACCEPTED)
        self.assertTrue(enquiry.conversations.exists())
        self.assertTrue(Notification.objects.filter(
            recipient=self.student,
            notification_type=NotificationType.ENQUIRY_RESPONSE).exists())

    def test_tutor_cannot_respond_to_other_tutors_enquiry(self):
        enquiry = Enquiry.objects.create(sender=self.student, tutor=self.tutor,
                                         subject=self.subject, message="Hi")
        intruder = User.objects.create_user(
            email="intruder@example.com", password="Passw0rd!23", role=UserRole.TUTOR,
        )
        TutorProfile.objects.create(user=intruder)
        self.client.force_login(intruder)
        response = self.client.post(
            reverse("marketplace:respond_enquiry", args=[enquiry.pk]),
            {"action": "accept"},
        )
        self.assertEqual(response.status_code, 404)

    def test_withdraw_idor(self):
        enquiry = Enquiry.objects.create(sender=self.student, tutor=self.tutor,
                                         subject=self.subject, message="Hi")
        other_student = User.objects.create_user(
            email="otherstudent@example.com", password="Passw0rd!23", role=UserRole.STUDENT,
        )
        self.client.force_login(other_student)
        response = self.client.post(reverse("marketplace:withdraw_enquiry", args=[enquiry.pk]))
        self.assertEqual(response.status_code, 404)


class TutorRequestTests(MarketplaceBase):
    def test_request_lifecycle(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse("marketplace:request_create"), {
            "title": "Need a Maths tutor for Class 10 in Howrah",
            "description": "Weekend classes preferred.", "subject": self.subject.pk,
            "class_level": self.class_level.pk, "location": self.location.pk,
            "mode": "OFFLINE", "budget": 500,
        })
        self.assertEqual(response.status_code, 302)
        request_obj = TutorRequest.objects.get(poster=self.student)
        self.assertEqual(request_obj.status, TutorRequestStatus.OPEN)

        # Tutor applies
        self.client.force_login(self.tutor_user)
        response = self.client.post(
            reverse("marketplace:apply", args=[request_obj.pk]),
            {"message": "I can help", "proposed_fee": 450},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(TutorApplication.objects.filter(
            tutor=self.tutor, request=request_obj).exists())

        # Duplicate application rejected
        self.client.post(reverse("marketplace:apply", args=[request_obj.pk]),
                         {"message": "Again", "proposed_fee": 400})
        self.assertEqual(TutorApplication.objects.filter(
            tutor=self.tutor, request=request_obj).count(), 1)

        # Student accepts
        application = TutorApplication.objects.get(tutor=self.tutor, request=request_obj)
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("marketplace:respond_application", args=[application.pk]),
            {"action": ApplicationStatus.ACCEPTED},
        )
        self.assertEqual(response.status_code, 302)
        application.refresh_from_db()
        self.assertEqual(application.status, ApplicationStatus.ACCEPTED)

    def test_student_cannot_apply(self):
        request_obj = TutorRequest.objects.create(
            poster=self.student, title="T", description="D", mode="BOTH"
        )
        self.client.force_login(self.student)
        response = self.client.post(reverse("marketplace:apply", args=[request_obj.pk]))
        self.assertEqual(response.status_code, 403)


class SavedTutorTests(MarketplaceBase):
    def test_save_toggle_and_db_unique(self):
        self.client.force_login(self.student)
        url = reverse("marketplace:toggle_save", args=[self.tutor.pk])
        self.client.post(url)
        self.assertTrue(SavedTutor.objects.filter(user=self.student, tutor=self.tutor).exists())
        self.client.post(url)  # toggle off
        self.assertFalse(SavedTutor.objects.filter(user=self.student, tutor=self.tutor).exists())
        SavedTutor.objects.create(user=self.student, tutor=self.tutor)
        with self.assertRaises(IntegrityError):
            SavedTutor.objects.create(user=self.student, tutor=self.tutor)
