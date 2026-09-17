from django.contrib import admin

from .models import AuditLog, Board, ClassLevel, PlatformSetting, Subject, SubjectCategory


@admin.register(SubjectCategory)
class SubjectCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ClassLevel)
class ClassLevelAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "is_active")
    ordering = ("order",)


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "user", "target", "ip_address", "created_at")
    list_filter = ("action",)
    search_fields = ("target", "user__email")
    readonly_fields = ("user", "action", "target", "ip_address", "metadata", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(PlatformSetting)
class PlatformSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "description", "updated_at")
