from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("tutors", views.TutorViewSet, basename="tutors")
router.register("enquiries", views.EnquiryViewSet, basename="enquiries")
router.register("tutor-requests", views.TutorRequestViewSet, basename="tutor-requests")
router.register("saved-tutors", views.SavedTutorViewSet, basename="saved-tutors")
router.register("conversations", views.ConversationViewSet, basename="conversations")
router.register("notifications", views.NotificationViewSet, basename="notifications")

app_name = "api"

urlpatterns = [
    path("auth/register/", views.RegisterAPIView.as_view(), name="register"),
    path("auth/login/", views.LoginAPIView.as_view(), name="login"),
    path("auth/logout/", views.LogoutAPIView.as_view(), name="logout"),
    path("subjects/", views.SubjectListAPIView.as_view(), name="subjects"),
    path("classes/", views.ClassLevelListAPIView.as_view(), name="classes"),
    path("boards/", views.BoardListAPIView.as_view(), name="boards"),
    path("locations/", views.LocationListAPIView.as_view(), name="locations"),
    path("reviews/", views.ReviewCreateAPIView.as_view(), name="reviews"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="docs"),
    path("", include(router.urls)),
]
