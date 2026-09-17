from django.urls import path

from . import views

app_name = "tutors"

urlpatterns = [
    path("tutors/", views.tutor_list, name="list"),
    path("tutors/<slug:slug>/", views.tutor_detail, name="detail"),
    path("tutor/dashboard/", views.tutor_dashboard, name="dashboard"),
    path("tutor/onboarding/<int:step>/", views.onboarding, name="onboarding"),
    path("tutor/availability/", views.availability_view, name="availability"),
    path("tutor/availability/<int:slot_id>/delete/", views.delete_slot, name="delete_slot"),
    path("tutor/profile/", views.profile_edit, name="profile_edit"),
    path("tutor/profile/extras/", views.profile_edit_extras, name="profile_extras"),
    path("tutor/profile/publish/", views.toggle_publish, name="toggle_publish"),
    path("tutor/students/", views.tutor_students, name="students"),
]
