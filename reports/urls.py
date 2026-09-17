from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("report/<str:target_type>/<int:object_id>/", views.report_target, name="report"),
]
