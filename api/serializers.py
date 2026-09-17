"""DRF serializers — only expose fields the requesting user may see."""
from django.contrib.auth import authenticate
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from accounts.models import User, UserRole
from core.models import Board, ClassLevel, Subject, SubjectCategory
from locations.models import Location
from marketplace.models import Enquiry, SavedTutor, TutorApplication, TutorRequest
from messaging.models import Conversation, Message
from notifications.models import Notification
from reviews.models import Review
from reviews.services import can_review
from tutors.models import TutorAvailability, TutorProfile, Weekday


# ---------------------------------------------------------------------------
# Core / lookup
# ---------------------------------------------------------------------------
class SubjectCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubjectCategory
        fields = ("id", "name", "slug")


class SubjectSerializer(serializers.ModelSerializer):
    category = SubjectCategorySerializer(read_only=True)

    class Meta:
        model = Subject
        fields = ("id", "name", "slug", "category")


class ClassLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassLevel
        fields = ("id", "name", "slug", "order")


class BoardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Board
        fields = ("id", "name", "slug")


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ("id", "city", "area", "slug")
        # pincode / coordinates withheld from public API


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class RegisterSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=(UserRole.STUDENT, UserRole.PARENT, UserRole.TUTOR))
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    password = serializers.CharField(min_length=8, write_only=True)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Unable to register with this email address.")
        return value.lower()

    def create(self, validated):
        return User.objects.create_user(**validated)


class EmptySerializer(serializers.Serializer):
    """Used for endpoints with an empty request body (e.g. logout)."""


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        request = self.context.get("request")
        user = authenticate(
            request=request, username=attrs["email"].lower(), password=attrs["password"]
        )
        if user is None:
            # Generic message — never reveal whether the account exists.
            raise serializers.ValidationError("Invalid email or password.")
        if user.is_account_blocked:
            raise serializers.ValidationError("This account is restricted.")
        attrs["user"] = user
        return attrs


class PublicUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "full_name", "role")


# ---------------------------------------------------------------------------
# Tutors
# ---------------------------------------------------------------------------
class TutorAvailabilitySerializer(serializers.ModelSerializer):
    weekday_label = serializers.CharField(source="get_weekday_display", read_only=True)

    class Meta:
        model = TutorAvailability
        fields = ("weekday", "weekday_label", "start_time", "end_time")


class TutorListSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="user.full_name", read_only=True)
    profile_image = serializers.SerializerMethodField()
    subjects = SubjectSerializer(many=True, read_only=True)
    location = serializers.CharField(source="display_location", read_only=True)
    badges = serializers.SerializerMethodField()
    fee = serializers.SerializerMethodField()

    class Meta:
        model = TutorProfile
        fields = (
            "slug", "name", "tagline", "profile_image", "subjects",
            "experience_years", "teaching_mode", "location",
            "average_rating", "reviews_count", "verification_status",
            "badges", "fee",
        )

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_profile_image(self, obj):
        image = obj.user.profile_image
        if image:
            request = self.context.get("request")
            url = image.url
            return request.build_absolute_uri(url) if request else url
        return None

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_badges(self, obj):
        return [b.get_badge_display() for b in obj.badges.all()]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_fee(self, obj):
        return obj.fee_display()


class TutorDetailSerializer(TutorListSerializer):
    classes = ClassLevelSerializer(many=True, read_only=True)
    boards = BoardSerializer(many=True, read_only=True)
    availability = TutorAvailabilitySerializer(many=True, read_only=True)

    class Meta(TutorListSerializer.Meta):
        fields = TutorListSerializer.Meta.fields + (
            "about", "teaching_methodology", "languages",
            "highest_qualification", "degree", "institution", "university",
            "passing_year", "hourly_fee", "monthly_fee", "fee_negotiable",
            "teaching_radius_km", "classes", "boards", "availability",
        )


# ---------------------------------------------------------------------------
# Marketplace
# ---------------------------------------------------------------------------
class EnquirySerializer(serializers.ModelSerializer):
    tutor_slug = serializers.SlugField(source="tutor.slug", read_only=True)
    sender_name = serializers.CharField(source="sender.full_name", read_only=True)

    class Meta:
        model = Enquiry
        fields = (
            "id", "tutor_slug", "sender_name", "subject", "class_level",
            "message", "teaching_mode", "preferred_days", "preferred_time",
            "budget", "status", "created_at",
        )
        read_only_fields = ("status", "created_at")


class EnquiryCreateSerializer(serializers.Serializer):
    tutor_slug = serializers.SlugField()
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all())
    message = serializers.CharField(max_length=2000)
    teaching_mode = serializers.ChoiceField(choices=("ONLINE", "OFFLINE", "BOTH"), default="BOTH")


class TutorRequestSerializer(serializers.ModelSerializer):
    poster_name = serializers.CharField(source="poster.full_name", read_only=True)
    applications_count = serializers.IntegerField(source="applications.count", read_only=True)

    class Meta:
        model = TutorRequest
        fields = (
            "id", "title", "description", "subject", "class_level", "board",
            "location", "mode", "budget", "preferred_schedule", "start_date",
            "status", "poster_name", "applications_count", "created_at",
        )
        read_only_fields = ("status", "created_at")


class TutorApplicationSerializer(serializers.ModelSerializer):
    tutor_name = serializers.CharField(source="tutor.user.full_name", read_only=True)

    class Meta:
        model = TutorApplication
        fields = ("id", "request", "tutor_name", "message", "proposed_fee", "status", "created_at")
        read_only_fields = ("status", "created_at")


class SavedTutorSerializer(serializers.ModelSerializer):
    tutor = TutorListSerializer(read_only=True)

    class Meta:
        model = SavedTutor
        fields = ("id", "tutor", "created_at")


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------
class ReviewSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.CharField(source="reviewer.full_name", read_only=True)

    class Meta:
        model = Review
        fields = ("id", "rating", "title", "text", "reviewer_name", "created_at")
        read_only_fields = ("created_at",)


class ReviewCreateSerializer(serializers.Serializer):
    tutor_slug = serializers.SlugField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    title = serializers.CharField(max_length=120)
    text = serializers.CharField(max_length=2000)

    def validate(self, attrs):
        request = self.context["request"]
        try:
            tutor = TutorProfile.objects.get(slug=attrs["tutor_slug"], is_published=True)
        except TutorProfile.DoesNotExist:
            raise serializers.ValidationError({"tutor_slug": "Tutor not found."})
        allowed, reason = can_review(request.user, tutor)
        if not allowed:
            raise serializers.ValidationError({"non_field_errors": [reason]})
        attrs["tutor"] = tutor
        return attrs


# ---------------------------------------------------------------------------
# Messaging & notifications
# ---------------------------------------------------------------------------
class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source="sender.full_name", read_only=True)

    class Meta:
        model = Message
        fields = ("id", "sender_name", "body", "created_at")
        read_only_fields = ("created_at",)


class MessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=4000)


class ConversationSerializer(serializers.ModelSerializer):
    participants = PublicUserSerializer(many=True, read_only=True)
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ("id", "subject", "participants", "last_message", "last_message_at")

    @extend_schema_field(MessageSerializer(allow_null=True))
    def get_last_message(self, obj):
        last = obj.messages.last()
        return MessageSerializer(last).data if last else None


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "notification_type", "title", "body", "url", "is_read", "created_at")
        read_only_fields = fields
