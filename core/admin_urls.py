"""Custom platform management URLs, mounted under /admin/ BEFORE admin.site.urls
so /admin/dashboard/ etc. resolve to these views while /admin/ retains Django admin."""
from django.urls import path

from . import manage_views

app_name = "manage"

urlpatterns = [
    path("dashboard/", manage_views.dashboard, name="dashboard"),
    path("users/", manage_views.users_list, name="users"),
    path("users/<str:role>/", manage_views.users_list, name="users_by_role"),
    path("users/detail/<int:user_id>/", manage_views.user_detail, name="user_detail"),
    path("users/<int:user_id>/delete/", manage_views.user_delete, name="user_delete"),
    path("users/<int:user_id>/status/", manage_views.user_set_status, name="user_status"),
    path("users/<int:user_id>/password-reset/", manage_views.user_password_reset, name="user_password_reset"),
    path("tutors/", manage_views.users_list, {"role": "TUTOR"}, name="tutors"),
    path("verifications/", manage_views.verification_queue, name="verifications"),
    path("verifications/<int:verification_id>/", manage_views.verification_detail, name="verification_detail"),
    path("verifications/<int:verification_id>/decide/", manage_views.verification_decide, name="verification_decide"),
    path("verifications/documents/<int:document_id>/", manage_views.verification_document, name="verification_document"),
    path("enquiries/", manage_views.enquiries, name="enquiries"),
    path("requests/", manage_views.requests_admin, name="requests"),
    path("applications/", manage_views.applications_admin, name="applications"),
    path("content/<str:kind>/", manage_views.content_list, name="content_list"),
    path("content/<str:kind>/new/", manage_views.content_edit, name="content_new"),
    path("content/<str:kind>/<int:object_id>/edit/", manage_views.content_edit, name="content_edit"),
    path("reviews/", manage_views.reviews_admin, name="reviews"),
    path("reviews/<int:review_id>/moderate/", manage_views.review_moderate, name="review_moderate"),
    path("reports/", manage_views.reports_admin, name="reports"),
    path("reports/<int:report_id>/handle/", manage_views.report_handle, name="report_handle"),
    path("notifications/", manage_views.notifications_admin, name="notifications"),
    path("audit-logs/", manage_views.audit_logs, name="audit_logs"),
    path("settings/", manage_views.settings_admin, name="settings"),
]
