from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("how-it-works/", views.how_it_works, name="how_it_works"),
    path("become-a-tutor/", views.become_a_tutor, name="become_a_tutor"),
    path("subjects/", views.subjects, name="subjects"),
    path("subjects/<slug:slug>/", views.subject_detail, name="subject_detail"),
    path("locations/", views.locations, name="locations"),
    path("locations/<slug:slug>/", views.location_detail, name="location_detail"),
]
