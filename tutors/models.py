"""Tutor marketplace profile models (Phase 3)."""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify

from core.models import Board, ClassLevel, Subject, TimeStampedModel
from core.validators import validate_image


class TeachingMode(models.TextChoices):
    ONLINE = "ONLINE", "Online"
    OFFLINE = "OFFLINE", "Offline (Home/Local)"
    BOTH = "BOTH", "Online & Offline"


class VerificationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    VERIFIED = "VERIFIED", "Verified"
    REJECTED = "REJECTED", "Rejected"
    SUSPENDED = "SUSPENDED", "Suspended"


class Weekday(models.IntegerChoices):
    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


class TutorProfile(TimeStampedModel):
    """Public-facing tutor profile. One per tutor account."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tutor_profile"
    )
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    tagline = models.CharField(max_length=160, blank=True)
    about = models.TextField(blank=True)
    teaching_methodology = models.TextField(blank=True)
    languages = models.CharField(max_length=200, blank=True, help_text="Comma-separated")
    achievements = models.TextField(blank=True)
    certifications = models.TextField(blank=True)

    # Education
    highest_qualification = models.CharField(max_length=120, blank=True)
    degree = models.CharField(max_length=120, blank=True)
    institution = models.CharField(max_length=150, blank=True)
    university = models.CharField(max_length=150, blank=True)
    passing_year = models.PositiveSmallIntegerField(null=True, blank=True)

    # Teaching
    experience_years = models.PositiveSmallIntegerField(default=0)
    teaching_mode = models.CharField(
        max_length=10, choices=TeachingMode.choices, default=TeachingMode.BOTH
    )
    subjects = models.ManyToManyField(Subject, through="TutorSubject", related_name="tutors")
    classes = models.ManyToManyField(ClassLevel, through="TutorClass", related_name="tutors")
    boards = models.ManyToManyField(Board, blank=True, related_name="tutors")

    # Location
    city = models.ForeignKey(
        "locations.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tutors_based",
    )
    pincode = models.CharField(max_length=10, blank=True)
    teaching_radius_km = models.PositiveSmallIntegerField(default=5)

    # Fees
    hourly_fee = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    monthly_fee = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    fee_negotiable = models.BooleanField(default=True)

    # Trust
    verification_status = models.CharField(
        max_length=10,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
        db_index=True,
    )
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    reviews_count = models.PositiveIntegerField(default=0)
    profile_views = models.PositiveIntegerField(default=0)

    # Publishing
    is_profile_complete = models.BooleanField(default=False)
    is_published = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["verification_status", "is_published"]),
            models.Index(fields=["average_rating"]),
            models.Index(fields=["hourly_fee"]),
            models.Index(fields=["experience_years"]),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            city = self.city.city if self.city_id else ""
            self.slug = self._build_slug(city)
        elif self.city_id:
            # Keep slug meaningful when the city changes AND slug was auto-built.
            pass
        super().save(*args, **kwargs)

    def _build_slug(self, city):
        parts = [self.user.full_name]
        primary_subject = self.subjects.first() if self.pk else None
        if primary_subject:
            parts.append(primary_subject.name)
        if city:
            parts.append(city)
        base = slugify(" ".join(parts)) or "tutor"
        candidate, i = base[:200], 2
        while TutorProfile.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
            candidate = f"{base[:195]}-{i}"
            i += 1
        return candidate

    def __str__(self):
        return self.user.full_name

    # --- Display helpers ----------------------------------------------------
    @property
    def is_verified(self):
        return self.verification_status == VerificationStatus.VERIFIED

    @property
    def display_location(self):
        """Approximate public location only — never a full address."""
        if self.city_id:
            return str(self.city)
        return "Kolkata / Howrah"

    @property
    def language_list(self):
        return [lng.strip() for lng in self.languages.split(",") if lng.strip()]

    def fee_display(self):
        if self.hourly_fee:
            return f"₹{self.hourly_fee:,.0f}/hr"
        if self.monthly_fee:
            return f"₹{self.monthly_fee:,.0f}/mo"
        return "Fee on request"


class TutorSubject(TimeStampedModel):
    tutor = models.ForeignKey(TutorProfile, on_delete=models.CASCADE, related_name="tutor_subjects")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="tutor_subjects")
    proficiency = models.CharField(max_length=60, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tutor", "subject"], name="unique_tutor_subject")
        ]

    def __str__(self):
        return f"{self.tutor} - {self.subject}"


class TutorClass(TimeStampedModel):
    tutor = models.ForeignKey(TutorProfile, on_delete=models.CASCADE, related_name="tutor_classes")
    class_level = models.ForeignKey(ClassLevel, on_delete=models.CASCADE, related_name="tutor_classes")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tutor", "class_level"], name="unique_tutor_class")
        ]
        verbose_name_plural = "tutor classes"

    def __str__(self):
        return f"{self.tutor} - {self.class_level}"


class TutorAvailability(TimeStampedModel):
    """One weekly time slot. Tutors may add many per weekday."""

    tutor = models.ForeignKey(TutorProfile, on_delete=models.CASCADE, related_name="availability")
    weekday = models.IntegerField(choices=Weekday.choices, db_index=True)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["weekday", "start_time"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F("start_time")),
                name="availability_end_after_start",
            ),
            models.UniqueConstraint(
                fields=["tutor", "weekday", "start_time", "end_time"],
                name="unique_tutor_slot",
            ),
        ]

    def __str__(self):
        return f"{self.tutor} {self.get_weekday_display()} {self.start_time:%H:%M}-{self.end_time:%H:%M}"


class TutorProfileImage(TimeStampedModel):
    """Reserved for future gallery support."""
    tutor = models.ForeignKey(TutorProfile, on_delete=models.CASCADE, related_name="gallery")
    image = models.ImageField(upload_to="tutors/gallery/%Y/%m/", validators=[validate_image])
