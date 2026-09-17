from django.urls import path

from . import views

app_name = "verification"

urlpatterns = [
    path("tutor/verification/", views.verification_status_view, name="status"),
    path("tutor/verification/submit/", views.submit_verification, name="submit"),
]
