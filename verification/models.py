"""Tutor verification: submissions, documents, badges (Phase 7)."""
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models

from core.models import TimeStampedModel
from core.validators import validate_document
from tutors.models import TutorProfile, VerificationStatus


class PrivateMediaStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=settings.PRIVATE_MEDIA_ROOT, base_url=None)


private_storage = PrivateMediaStorage()


class DocumentType(models.TextChoices):
    ID_DOCUMENT = "ID_DOCUMENT", "ID document"
    QUALIFICATION = "QUALIFICATION", "Qualification certificate"
    EXPERIENCE = "EXPERIENCE", "Experience certificate"
    PHOTO = "PHOTO", "Profile photo"


class TutorVerification(TimeStampedModel):
    """One verification submission per review cycle."""

    tutor = models.ForeignKey(TutorProfile, on_delete=models.CASCADE, related_name="verifications")
    status = models.CharField(
        max_length=10, choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING, db_index=True,
    )
    rejection_reason = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="verifications_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Verification #{self.pk} for {self.tutor} ({self.status})"


def verification_upload_path(instance, filename):
    """Private path — verification documents are never publicly served."""
    return f"private/verification/tutor_{instance.verification.tutor_id}/{filename}"


class VerificationDocument(TimeStampedModel):
    verification = models.ForeignKey(
        TutorVerification, on_delete=models.CASCADE, related_name="documents"
    )
    document_type = models.CharField(max_length=20, choices=DocumentType.choices)
    file = models.FileField(
        storage=private_storage,
        upload_to=verification_upload_path,
        validators=[validate_document],
    )

    def __str__(self):
        return f"{self.get_document_type_display()} for verification #{self.verification_id}"


class VerificationBadge(models.TextChoices):
    IDENTITY = "IDENTITY", "Identity Verified"
    QUALIFICATION = "QUALIFICATION", "Qualification Verified"
    PROFILE = "PROFILE", "Profile Verified"


class TutorBadge(TimeStampedModel):
    """Badges awarded by admin after verification — never self-assigned."""

    tutor = models.ForeignKey(TutorProfile, on_delete=models.CASCADE, related_name="badges")
    badge = models.CharField(max_length=20, choices=VerificationBadge.choices)
    awarded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tutor", "badge"], name="unique_tutor_badge")
        ]

    def __str__(self):
        return f"{self.get_badge_display()} - {self.tutor}"
