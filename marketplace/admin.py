from django.contrib import admin

from .models import Enquiry, SavedTutor, TutorApplication, TutorRequest


@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ("sender", "tutor", "subject", "status", "created_at")
    list_filter = ("status",)


@admin.register(TutorRequest)
class TutorRequestAdmin(admin.ModelAdmin):
    list_display = ("title", "poster", "subject", "status", "created_at")
    list_filter = ("status",)


@admin.register(TutorApplication)
class TutorApplicationAdmin(admin.ModelAdmin):
    list_display = ("tutor", "request", "status", "created_at")
    list_filter = ("status",)


@admin.register(SavedTutor)
class SavedTutorAdmin(admin.ModelAdmin):
    list_display = ("user", "tutor", "created_at")
