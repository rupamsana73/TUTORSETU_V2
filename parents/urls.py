from django.urls import path

from students.views import saved_tutors

from . import views

app_name = "parents"

urlpatterns = [
    path("parent/dashboard/", views.dashboard, name="dashboard"),
    path("parent/children/", views.children, name="children"),
    path("parent/children/add/", views.child_create, name="child_create"),
    path("parent/children/<int:child_id>/edit/", views.child_edit, name="child_edit"),
    path("parent/children/<int:child_id>/delete/", views.child_delete, name="child_delete"),
    path("parent/saved/", saved_tutors, name="saved"),
    path("parent/profile/", views.parent_profile_view, name="profile"),
]
