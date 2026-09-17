from django.urls import path

from . import views

app_name = "reviews"

urlpatterns = [
    path("tutors/<slug:tutor_slug>/review/", views.create, name="create"),
    path("reviews/<int:review_id>/report/", views.report_review, name="report"),
]
