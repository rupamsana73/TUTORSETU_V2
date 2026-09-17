from django.contrib import admin

from .models import Location, TutorTeachingArea


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("area", "city", "pincode", "state", "is_active")
    list_filter = ("city", "is_active")
    search_fields = ("area", "city", "pincode")


@admin.register(TutorTeachingArea)
class TutorTeachingAreaAdmin(admin.ModelAdmin):
    list_display = ("tutor", "location")
