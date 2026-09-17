"""Review models (Phase 7)."""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import TimeStampedModel
from tutors.models import TutorProfile


class ReviewStatus(models.TextChoices):
    PUBLISHED = "PUBLISHED", "Published"
    HIDDEN = "HIDDEN", "Hidden"
    REMOVED = "REMOVED", "Removed"


class Review(TimeStampedModel):
    """A review of a tutor. Eligibility enforced in services (accepted enquiry)."""

    tutor = models.ForeignKey(TutorProfile, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_written"
    )
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=120)
    text = models.TextField(max_length=2000)
    status = models.CharField(
        max_length=10, choices=ReviewStatus.choices,
        default=ReviewStatus.PUBLISHED, db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["tutor", "reviewer"], name="unique_tutor_review")
        ]
        indexes = [models.Index(fields=["tutor", "status"])]

    def __str__(self):
        return f"{self.rating}* by {self.reviewer} for {self.tutor}"


class ReviewReport(TimeStampedModel):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="review_reports"
    )
    reason = models.TextField(max_length=1000)
    is_resolved = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["review", "reporter"], name="unique_review_report")
        ]

    def __str__(self):
        return f"Report on review #{self.review_id}"
