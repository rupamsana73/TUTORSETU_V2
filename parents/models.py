"""Parent profile and children models."""
from django.conf import settings
from django.db import models

from core.models import Board, ClassLevel, Subject, TimeStampedModel


class ParentProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="parent_profile"
    )
    location = models.ForeignKey(
        "locations.Location", on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        return f"Parent: {self.user.full_name}"


class StudentChild(TimeStampedModel):
    """A child managed by a parent."""

    parent = models.ForeignKey(
        ParentProfile, on_delete=models.CASCADE, related_name="children"
    )
    name = models.CharField(max_length=120)
    class_level = models.ForeignKey(
        ClassLevel, on_delete=models.SET_NULL, null=True, blank=True
    )
    school = models.CharField(max_length=150, blank=True)
    board = models.ForeignKey(Board, on_delete=models.SET_NULL, null=True, blank=True)
    subjects = models.ManyToManyField(Subject, blank=True, related_name="children")
    learning_requirements = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} (child of {self.parent.user.full_name})"
