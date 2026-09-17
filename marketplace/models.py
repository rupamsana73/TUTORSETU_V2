"""Marketplace models: enquiries, tutor requests, applications, saved tutors."""
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.models import Board, ClassLevel, Subject, TimeStampedModel
from tutors.models import TeachingMode, TutorProfile, Weekday


class EnquiryStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    CONTACTED = "CONTACTED", "Contacted"
    ACCEPTED = "ACCEPTED", "Accepted"
    REJECTED = "REJECTED", "Rejected"
    CLOSED = "CLOSED", "Closed"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"


class Enquiry(TimeStampedModel):
    """A student/parent enquiry sent to a tutor."""

    tutor = models.ForeignKey(TutorProfile, on_delete=models.CASCADE, related_name="enquiries")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_enquiries"
    )
    child = models.ForeignKey(
        "parents.StudentChild", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="enquiries",
        help_text="Set when a parent enquires for a child.",
    )
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True)
    class_level = models.ForeignKey(ClassLevel, on_delete=models.SET_NULL, null=True, blank=True)
    message = models.TextField()
    teaching_mode = models.CharField(
        max_length=10, choices=TeachingMode.choices, default=TeachingMode.BOTH
    )
    preferred_days = models.CharField(max_length=120, blank=True)
    preferred_time = models.CharField(max_length=60, blank=True)
    budget = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    location = models.ForeignKey(
        "locations.Location", on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.CharField(
        max_length=10, choices=EnquiryStatus.choices,
        default=EnquiryStatus.PENDING, db_index=True,
    )
    tutor_response = models.TextField(blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tutor", "status"]),
            models.Index(fields=["sender", "status"]),
        ]

    def __str__(self):
        return f"Enquiry #{self.pk}: {self.sender} -> {self.tutor}"

    # --- transitions ---------------------------------------------------------
    def can_withdraw(self):
        return self.status in (EnquiryStatus.PENDING, EnquiryStatus.CONTACTED)


class TutorRequestStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    MATCHING = "MATCHING", "Matching"
    RESPONDED = "RESPONDED", "Responded"
    CLOSED = "CLOSED", "Closed"
    CANCELLED = "CANCELLED", "Cancelled"


class TutorRequest(TimeStampedModel):
    """A public requirement posted by a student/parent that tutors can apply to."""

    poster = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tutor_requests"
    )
    child = models.ForeignKey(
        "parents.StudentChild", on_delete=models.SET_NULL, null=True, blank=True
    )
    title = models.CharField(max_length=160)
    description = models.TextField()
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True)
    class_level = models.ForeignKey(ClassLevel, on_delete=models.SET_NULL, null=True, blank=True)
    board = models.ForeignKey(Board, on_delete=models.SET_NULL, null=True, blank=True)
    location = models.ForeignKey(
        "locations.Location", on_delete=models.SET_NULL, null=True, blank=True
    )
    mode = models.CharField(max_length=10, choices=TeachingMode.choices, default=TeachingMode.BOTH)
    budget = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    preferred_schedule = models.CharField(max_length=200, blank=True)
    start_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=TutorRequestStatus.choices,
        default=TutorRequestStatus.OPEN, db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "subject"])]

    def __str__(self):
        return self.title


class ApplicationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SHORTLISTED = "SHORTLISTED", "Shortlisted"
    ACCEPTED = "ACCEPTED", "Accepted"
    REJECTED = "REJECTED", "Rejected"


class TutorApplication(TimeStampedModel):
    """A tutor's response/application to a TutorRequest."""

    request = models.ForeignKey(TutorRequest, on_delete=models.CASCADE, related_name="applications")
    tutor = models.ForeignKey(TutorProfile, on_delete=models.CASCADE, related_name="applications")
    message = models.TextField()
    proposed_fee = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    status = models.CharField(
        max_length=12, choices=ApplicationStatus.choices,
        default=ApplicationStatus.PENDING, db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["request", "tutor"], name="unique_request_application"
            )
        ]

    def __str__(self):
        return f"{self.tutor} -> {self.request}"


class SavedTutor(TimeStampedModel):
    """A student's/parent's bookmarked tutor (duplicates blocked at DB level)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_tutors"
    )
    tutor = models.ForeignKey(TutorProfile, on_delete=models.CASCADE, related_name="saved_by")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "tutor"], name="unique_saved_tutor")
        ]

    def __str__(self):
        return f"{self.user} saved {self.tutor}"
