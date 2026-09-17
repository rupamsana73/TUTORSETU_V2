"""Account services: profile creation, verification emails."""
import logging

from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import UserRole
from .tokens import email_verification_token

logger = logging.getLogger("tutorsetu")


def create_profile_for_user(user, cleaned_data):
    """Create the role-specific profile after registration (transactional)."""
    from django.db import transaction

    with transaction.atomic():
        if user.role == UserRole.STUDENT:
            from students.models import StudentProfile

            StudentProfile.objects.get_or_create(
                user=user,
                defaults={
                    "class_level": cleaned_data.get("class_level"),
                    "board": cleaned_data.get("board"),
                    "preferred_location": cleaned_data.get("preferred_location"),
                },
            )
        elif user.role == UserRole.PARENT:
            from parents.models import ParentProfile

            ParentProfile.objects.get_or_create(
                user=user, defaults={"location": cleaned_data.get("location")}
            )
        elif user.role == UserRole.TUTOR:
            from tutors.models import TutorProfile

            TutorProfile.objects.get_or_create(
                user=user,
                defaults={
                    "city": cleaned_data.get("city"),
                    "teaching_mode": cleaned_data.get("teaching_mode"),
                },
            )


def send_verification_email(request, user):
    """Send the email-verification link for the given user.

    Returns True on success and False on failure so callers can surface the
    problem without silently pretending the verification workflow completed.
    """
    try:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = email_verification_token.make_token(user)
        domain = get_current_site(request).domain if request else "localhost:8000"
        scheme = "https" if request and request.is_secure() else "http"
        url = f"{scheme}://{domain}{reverse('accounts:verify_email', args=[uid, token])}"
        body = render_to_string(
            "accounts/emails/verification_email.txt",
            {"user": user, "verification_url": url},
        )
        sent = send_mail(
            subject="Verify your TutorSetu email",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return sent == 1
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send verification email to user %s", user.pk)
        return False
