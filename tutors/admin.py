from django.contrib import admin

from .models import (
    TutorAvailability, TutorClass, TutorProfile, TutorSubject,
)


@admin.register(TutorProfile)
class TutorProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "verification_status", "is_published", "average_rating", "experience_years", "city")
    list_filter = ("verification_status", "is_published", "teaching_mode")
    search_fields = ("user__full_name", "user__email")


@admin.register(TutorSubject)
class TutorSubjectAdmin(admin.ModelAdmin):
    list_display = ("tutor", "subject")


@admin.register(TutorClass)
class TutorClassAdmin(admin.ModelAdmin):
    list_display = ("tutor", "class_level")


@admin.register(TutorAvailability)
class TutorAvailabilityAdmin(admin.ModelAdmin):
    list_display = ("tutor", "weekday", "start_time", "end_time")
