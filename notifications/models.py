"""In-app + email notification records (push-ready architecture)."""
from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class NotificationType(models.TextChoices):
    NEW_ENQUIRY = "NEW_ENQUIRY", "New enquiry"
    ENQUIRY_RESPONSE = "ENQUIRY_RESPONSE", "Enquiry response"
    NEW_MESSAGE = "NEW_MESSAGE", "New message"
    REQUEST_RESPONSE = "REQUEST_RESPONSE", "Tutor request response"
    REVIEW_RECEIVED = "REVIEW_RECEIVED", "Review received"
    VERIFICATION_RESULT = "VERIFICATION_RESULT", "Verification result"
    ACCOUNT_STATUS = "ACCOUNT_STATUS", "Account status"
    DEMO_REQUEST = "DEMO_REQUEST", "Demo request"
    GENERIC = "GENERIC", "Notification"


class Notification(TimeStampedModel):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    notification_type = models.CharField(
        max_length=24, choices=NotificationType.choices, default=NotificationType.GENERIC,
        db_index=True,
    )
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    email_sent = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read"])]

    def __str__(self):
        return f"{self.notification_type} -> {self.recipient}"
