"""TutorSetu root URL configuration."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponseNotFound
from django.urls import include, path

urlpatterns = [
    # Custom platform management dashboard takes precedence for /admin/dashboard etc.
    path("admin/", include("core.admin_urls")),
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("", include("accounts.urls")),
    path("", include("students.urls")),
    path("", include("parents.urls")),
    path("", include("tutors.urls")),
    path("", include("marketplace.urls")),
    path("", include("messaging.urls")),
    path("", include("reviews.urls")),
    path("", include("verification.urls")),
    path("", include("notifications.urls")),
    path("", include("reports.urls")),
    path("api/", include("api.urls")),
]

handler404 = "core.views.error_404"
handler403 = "core.views.error_403"
handler500 = "core.views.error_500"


def private_media_forbidden(request, path=""):
    return HttpResponseNotFound()


if settings.DEBUG:
    urlpatterns += [
        path("media/private/<path:path>", private_media_forbidden),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
