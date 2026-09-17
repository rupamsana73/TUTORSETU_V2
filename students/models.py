"""Student profile model."""
from django.conf import settings
from django.db import models

from core.models import Board, ClassLevel, TimeStampedModel


class StudentProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_profile"
    )
    class_level = models.ForeignKey(
        ClassLevel, on_delete=models.SET_NULL, null=True, blank=True
    )
    board = models.ForeignKey(Board, on_delete=models.SET_NULL, null=True, blank=True)
    school = models.CharField(max_length=150, blank=True)
    preferred_location = models.ForeignKey(
        "locations.Location", on_delete=models.SET_NULL, null=True, blank=True
    )
    learning_requirements = models.TextField(blank=True)

    def __str__(self):
        return f"Student: {self.user.full_name}"
