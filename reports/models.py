"""General user reporting system (Phase 7)."""
from django.conf import settings
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from core.models import TimeStampedModel


class ReportCategory(models.TextChoices):
    SPAM = "SPAM", "Spam"
    FRAUD = "FRAUD", "Fraud"
    HARASSMENT = "HARASSMENT", "Harassment"
    FAKE_INFORMATION = "FAKE_INFORMATION", "Fake information"
    INAPPROPRIATE_BEHAVIOUR = "INAPPROPRIATE_BEHAVIOUR", "Inappropriate behaviour"
    OTHER = "OTHER", "Other"


class ReportStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    RESOLVED = "RESOLVED", "Resolved"
    DISMISSED = "DISMISSED", "Dismissed"


class Report(TimeStampedModel):
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports_filed"
    )
    category = models.CharField(max_length=24, choices=ReportCategory.choices)
    description = models.TextField(max_length=2000)
    status = models.CharField(
        max_length=14, choices=ReportStatus.choices,
        default=ReportStatus.OPEN, db_index=True,
    )
    # Generic target: user, tutor profile, review, message, etc.
    target_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    target_object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("target_content_type", "target_object_id")
    resolution_notes = models.TextField(blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="reports_handled",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["reporter", "target_content_type", "target_object_id"],
                name="unique_report_per_target",
            )
        ]

    def __str__(self):
        return f"{self.category} report #{self.pk} by {self.reporter}"
