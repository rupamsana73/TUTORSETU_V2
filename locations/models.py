"""Location models: database-driven cities/areas with geo coordinates."""
from django.db import models
from django.utils.text import slugify

from core.models import TimeStampedModel


class Location(TimeStampedModel):
    """A searchable area within a city (e.g. 'Shibpur, Howrah')."""

    city = models.CharField(max_length=100, db_index=True)
    area = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10, blank=True, db_index=True)
    state = models.CharField(max_length=100, default="West Bengal")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["city", "area"]
        constraints = [
            models.UniqueConstraint(
                fields=["city", "area"], name="unique_location_city_area"
            )
        ]
        indexes = [models.Index(fields=["city", "is_active"])]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = f"{self.area} {self.city}"
            slug = slugify(base) or "location"
            candidate, i = slug, 2
            while Location.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{slug}-{i}"
                i += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.area}, {self.city}"


class TutorTeachingArea(TimeStampedModel):
    """Areas a tutor covers for local/home tuition."""

    tutor = models.ForeignKey(
        "tutors.TutorProfile",
        on_delete=models.CASCADE,
        related_name="teaching_areas",
    )
    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="tutors_covering"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tutor", "location"], name="unique_tutor_teaching_area"
            )
        ]

    def __str__(self):
        return f"{self.tutor} -> {self.location}"
