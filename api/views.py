"""DRF API views with authentication, permissions, throttling, pagination."""
from django.contrib.auth import login, logout
from django.db import IntegrityError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, permissions, status, throttling, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import UserRole
from core.models import Board, ClassLevel, Subject
from core.utils import audit
from locations.models import Location
from marketplace.models import (
    Enquiry, EnquiryStatus, SavedTutor, TutorRequest, TutorRequestStatus,
)
from messaging.models import Conversation, Message
from notifications.models import Notification
from reviews.models import Review, ReviewStatus
from reviews.services import create_review
from tutors.models import TeachingMode, TutorProfile, VerificationStatus

from . import serializers as s
from .filters import TutorProfileFilter


# ---------------------------------------------------------------------------
# Scoped throttle classes (rates configured in settings, not hardcoded)
# ---------------------------------------------------------------------------
class FlexibleRateThrottleMixin:
    """Extends DRF's parser with minute-window rates like '5/15min'."""

    def parse_rate(self, rate):
        if rate and "/" in rate:
            num, _, period = rate.partition("/")
            if period.endswith("min") and period[:-3].isdigit():
                return int(num), int(period[:-3]) * 60
        return super().parse_rate(rate)


class AuthThrottle(FlexibleRateThrottleMixin, throttling.AnonRateThrottle):
    scope = "auth"


class RegisterThrottle(FlexibleRateThrottleMixin, throttling.AnonRateThrottle):
    scope = "register"


class MessagingThrottle(FlexibleRateThrottleMixin, throttling.UserRateThrottle):
    scope = "messaging"


class EnquiryThrottle(FlexibleRateThrottleMixin, throttling.UserRateThrottle):
    scope = "enquiry"


class ReviewThrottle(FlexibleRateThrottleMixin, throttling.UserRateThrottle):
    scope = "review"


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------
class IsStudentOrParent(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in (
            UserRole.STUDENT, UserRole.PARENT
        )


class IsTutor(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == UserRole.TUTOR


class IsEnquiryParticipant(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        user = request.user
        return obj.sender_id == user.pk or obj.tutor.user_id == user.pk


class IsConversationParticipant(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.is_participant(request.user)


def ok(data=None, message="", status_code=status.HTTP_200_OK):
    return Response({"success": True, "message": message, "data": data or {}}, status_code)


def fail(message="Unable to process your request.", errors=None,
         status_code=status.HTTP_400_BAD_REQUEST):
    return Response(
        {"success": False, "message": message, "errors": errors or {}}, status_code
    )


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------
class RegisterAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [RegisterThrottle]
    serializer_class = s.RegisterSerializer

    def post(self, request):
        serializer = s.RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return fail("Registration failed.", serializer.errors)
        user = serializer.save()
        from accounts.services import create_profile_for_user, send_verification_email

        create_profile_for_user(user, {})
        audit(request, "API_REGISTER", target=user.email, user=user)
        if not send_verification_email(request, user):
            return fail(
                "Registration created, but the verification email could not be sent. Please contact support or request a fresh verification email after logging in.",
                errors={"email": ["Verification email delivery failed."]},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return ok({"id": user.pk, "email": user.email, "role": user.role},
                  "Registration successful. Please check your email to verify your account.",
                  status.HTTP_201_CREATED)


class LoginAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthThrottle]
    serializer_class = s.LoginSerializer

    def post(self, request):
        serializer = s.LoginSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return fail("Invalid email or password.", serializer.errors,
                        status.HTTP_401_UNAUTHORIZED)
        user = serializer.validated_data["user"]
        login(request, user)
        audit(request, "API_LOGIN", target=user.email, user=user)
        return ok({"id": user.pk, "full_name": user.full_name, "role": user.role},
                  "Logged in.")


class LogoutAPIView(APIView):
    serializer_class = s.EmptySerializer

    def post(self, request):
        if request.user.is_authenticated:
            audit(request, "API_LOGOUT", target=request.user.email)
        logout(request)
        return ok(message="Logged out.")


# ---------------------------------------------------------------------------
# Lookups (public, read-only)
# ---------------------------------------------------------------------------
class SubjectListAPIView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = s.SubjectSerializer
    queryset = Subject.objects.filter(is_active=True, is_deleted=False).select_related("category")
    search_fields = ("name",)
    pagination_class = None


class ClassLevelListAPIView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = s.ClassLevelSerializer
    queryset = ClassLevel.objects.filter(is_active=True, is_deleted=False)
    pagination_class = None


class BoardListAPIView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = s.BoardSerializer
    queryset = Board.objects.filter(is_active=True, is_deleted=False)
    pagination_class = None


class LocationListAPIView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = s.LocationSerializer
    queryset = Location.objects.filter(is_active=True, is_deleted=False)
    search_fields = ("city", "area")
    pagination_class = None


# ---------------------------------------------------------------------------
# Tutors (public read)
# ---------------------------------------------------------------------------
class TutorViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"
    filterset_class = TutorProfileFilter
    search_fields = ("user__full_name", "subjects__name", "tagline")
    ordering_fields = ("average_rating", "experience_years", "hourly_fee", "created_at")
    ordering = ("-verification_status", "-average_rating")

    def get_queryset(self):
        return (
            TutorProfile.objects.filter(is_published=True, is_deleted=False)
            .select_related("user", "city")
            .prefetch_related("subjects", "classes", "boards", "availability", "badges")
            .distinct()
        )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return s.TutorDetailSerializer
        return s.TutorListSerializer

    @action(detail=True, methods=["get"], permission_classes=[permissions.AllowAny])
    def reviews(self, request, slug=None):
        tutor = self.get_object()
        reviews = tutor.reviews.filter(status=ReviewStatus.PUBLISHED).select_related("reviewer")
        page = self.paginate_queryset(reviews)
        return self.get_paginated_response(
            s.ReviewSerializer(page, many=True).data
        )


# ---------------------------------------------------------------------------
# Enquiries
# ---------------------------------------------------------------------------
class EnquiryViewSet(viewsets.ModelViewSet):
    throttle_classes = [EnquiryThrottle]
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return s.EnquiryCreateSerializer
        return s.EnquirySerializer

    def get_permissions(self):
        if self.action == "create":
            return [IsStudentOrParent()]
        return [permissions.IsAuthenticated(), IsEnquiryParticipant()]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Enquiry.objects.none()
        if user.role == UserRole.TUTOR:
            return Enquiry.objects.filter(tutor__user=user).select_related("sender", "subject")
        return Enquiry.objects.filter(sender=user).select_related("tutor__user", "subject")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return fail("Unable to send enquiry.", serializer.errors)
        data = serializer.validated_data
        try:
            tutor = TutorProfile.objects.get(slug=data["tutor_slug"], is_published=True)
        except TutorProfile.DoesNotExist:
            return fail("Tutor not found.", status_code=status.HTTP_404_NOT_FOUND)
        if tutor.user_id == request.user.pk:
            return fail("You cannot enquire about yourself.")
        if Enquiry.objects.filter(
            tutor=tutor, sender=request.user,
            status__in=(EnquiryStatus.PENDING, EnquiryStatus.CONTACTED),
        ).exists():
            return fail("You already have an open enquiry with this tutor.")
        enquiry = Enquiry.objects.create(
            tutor=tutor, sender=request.user, subject=data["subject"],
            message=data["message"], teaching_mode=data["teaching_mode"],
        )
        from notifications.models import NotificationType
        from notifications.services import notify

        notify(tutor.user, NotificationType.NEW_ENQUIRY,
               f"New enquiry from {request.user.full_name}", enquiry.message[:300],
               url="/tutor/enquiries/", send_email=True)
        return ok(s.EnquirySerializer(enquiry).data, "Enquiry sent.", status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Tutor requests
# ---------------------------------------------------------------------------
class TutorRequestViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        return s.TutorRequestSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        return [IsStudentOrParent()]

    def get_queryset(self):
        return TutorRequest.objects.filter(is_deleted=False).select_related(
            "poster", "subject", "class_level", "location"
        )

    def perform_create(self, serializer):
        serializer.save(poster=self.request.user, status=TutorRequestStatus.OPEN)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return fail("Unable to create request.", serializer.errors)
        self.perform_create(serializer)
        return ok(serializer.data, "Tutor request created.", status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Saved tutors
# ---------------------------------------------------------------------------
class SavedTutorViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStudentOrParent]
    serializer_class = s.SavedTutorSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SavedTutor.objects.none()
        return SavedTutor.objects.filter(user=self.request.user).select_related(
            "tutor__user", "tutor__city"
        ).prefetch_related("tutor__subjects", "tutor__badges")

    def create(self, request, *args, **kwargs):
        tutor_id = request.data.get("tutor")
        try:
            tutor = TutorProfile.objects.get(pk=tutor_id, is_published=True)
        except (TutorProfile.DoesNotExist, ValueError, TypeError):
            return fail("Tutor not found.", status_code=status.HTTP_404_NOT_FOUND)
        if SavedTutor.objects.filter(user=request.user, tutor=tutor).exists():
            return fail("This tutor is already in your saved list.")
        saved = SavedTutor.objects.create(user=request.user, tutor=tutor)
        return ok(self.get_serializer(saved).data, "Tutor saved.", status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------
class ReviewCreateAPIView(APIView):
    permission_classes = [IsStudentOrParent]
    throttle_classes = [ReviewThrottle]
    serializer_class = s.ReviewCreateSerializer

    def post(self, request):
        serializer = s.ReviewCreateSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return fail("Unable to publish review.", serializer.errors)
        data = serializer.validated_data
        try:
            review = create_review(
                request.user, data["tutor"], data["rating"], data["title"], data["text"]
            )
        except (PermissionError, IntegrityError) as exc:
            return fail(str(exc) or "Unable to publish review.")
        return ok(s.ReviewSerializer(review).data, "Review published.", status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------
class ConversationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsConversationParticipant]
    serializer_class = s.ConversationSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Conversation.objects.none()
        return Conversation.objects.filter(participants=self.request.user).prefetch_related(
            "conversation_participants__user", "messages__sender"
        )

    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        conversation = self.get_object()
        messages_qs = conversation.messages.select_related("sender")
        page = self.paginate_queryset(messages_qs)
        return self.get_paginated_response(s.MessageSerializer(page, many=True).data)

    @action(detail=True, methods=["post"], throttle_classes=[MessagingThrottle])
    def send(self, request, pk=None):
        conversation = self.get_object()
        serializer = s.MessageCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return fail("Unable to send message.", serializer.errors)
        message = Message.objects.create(
            conversation=conversation, sender=request.user,
            body=serializer.validated_data["body"],
        )
        conversation.last_message_at = message.created_at
        conversation.save(update_fields=["last_message_at"])
        for recipient in conversation.participants.exclude(pk=request.user.pk):
            from notifications.models import NotificationType
            from notifications.services import notify

            notify(recipient, NotificationType.NEW_MESSAGE,
                   f"New message from {request.user.full_name}",
                   message.body[:200], url=f"/messages/{conversation.pk}/")
        return ok(s.MessageSerializer(message).data, "Message sent.", status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = s.NotificationSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return ok(message="All notifications marked as read.")

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return ok(message="Marked as read.")
