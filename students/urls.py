from django.urls import path

from . import views

app_name = "students"

urlpatterns = [
    path("student/dashboard/", views.dashboard, name="dashboard"),
    path("student/saved/", views.saved_tutors, name="saved"),
    path("student/profile/", views.student_profile_view, name="profile"),
]
