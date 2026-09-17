from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("notifications/", views.notification_list, name="list"),
    path("notifications/<int:notification_id>/open/", views.notification_open, name="open"),
    path("notifications/mark-all-read/", views.mark_all_read, name="mark_all_read"),
]
