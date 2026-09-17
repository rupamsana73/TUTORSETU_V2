"""Marketplace views: enquiries, tutor requests, applications, saved tutors."""
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from accounts.decorators import student_or_parent_required, tutor_required
from core.ratelimits import RATE_LIMITS
from core.utils import audit
from notifications.models import NotificationType
from notifications.services import notify
from tutors.models import TutorProfile, Weekday

from .forms import EnquiryForm, TutorApplicationForm, TutorRequestForm
from .models import (
    ApplicationStatus, Enquiry, EnquiryStatus, SavedTutor,
    TutorApplication, TutorRequest, TutorRequestStatus,
)


# ---------------------------------------------------------------------------
# Enquiries
# ---------------------------------------------------------------------------
@ratelimit(key="user", rate=RATE_LIMITS["enquiry"], method="POST", block=True)
@student_or_parent_required
def send_enquiry(request, tutor_slug):
    tutor = get_object_or_404(
        TutorProfile.objects.select_related("user"), slug=tutor_slug, is_published=True
    )
    if request.user == tutor.user:
        messages.error(request, "You cannot enquire about yourself.")
        return redirect("tutors:detail", slug=tutor_slug)

    if request.method == "POST":
        form = EnquiryForm(request.POST, user=request.user)
        if form.is_valid():
            open_enquiry_exists = Enquiry.objects.filter(
                tutor=tutor, sender=request.user,
                status__in=(EnquiryStatus.PENDING, EnquiryStatus.CONTACTED),
            ).exists()
            if open_enquiry_exists:
                messages.info(request, "You already have an open enquiry with this tutor.")
                return redirect("marketplace:enquiry_list")
            with transaction.atomic():
                enquiry = form.save(commit=False)
                enquiry.tutor = tutor
                enquiry.sender = request.user
                enquiry.save()
            notify(
                tutor.user, NotificationType.NEW_ENQUIRY,
                f"New enquiry from {request.user.full_name}",
                enquiry.message[:300],
                url="/tutor/enquiries/", send_email=True,
            )
            audit(request, "ENQUIRY_SENT", target=f"enquiry:{enquiry.pk}")
            messages.success(request, "Your enquiry has been sent.")
            return redirect("marketplace:enquiry_list")
    else:
        initial = {"subject": tutor.subjects.first()}
        form = EnquiryForm(user=request.user, initial=initial)
    return render(request, "marketplace/enquiry_form.html", {"form": form, "tutor": tutor})


@student_or_parent_required
def enquiry_list(request):
    enquiries = (
        Enquiry.objects.filter(sender=request.user)
        .select_related("tutor__user", "subject", "class_level")
    )
    return render(request, "marketplace/enquiry_list.html", {"enquiries": enquiries})


@tutor_required
def tutor_enquiry_list(request):
    enquiries = (
        request.user.tutor_profile.enquiries
        .select_related("sender", "subject", "class_level")
    )
    return render(request, "marketplace/tutor_enquiry_list.html", {"enquiries": enquiries})


@require_POST
@tutor_required
def respond_enquiry(request, enquiry_id):
    tutor = request.user.tutor_profile
    enquiry = get_object_or_404(Enquiry, pk=enquiry_id, tutor=tutor)  # IDOR-safe
    action = request.POST.get("action")
    response_text = (request.POST.get("response") or "").strip()

    valid = {"accept": EnquiryStatus.ACCEPTED, "reject": EnquiryStatus.REJECTED, "contact": EnquiryStatus.CONTACTED}
    if action not in valid:
        messages.error(request, "Invalid action.")
        return redirect("marketplace:tutor_enquiries")

    enquiry.status = valid[action]
    enquiry.tutor_response = response_text
    enquiry.responded_at = timezone.now()
    enquiry.save(update_fields=["status", "tutor_response", "responded_at", "updated_at"])

    if action == "accept":
        # Auto-open a conversation between the two parties.
        from messaging.services import get_or_create_conversation

        conversation = get_or_create_conversation(
            [tutor.user, enquiry.sender],
            subject=f"Enquiry #{enquiry.pk}",
            enquiry=enquiry,
        )
        notify(
            enquiry.sender, NotificationType.ENQUIRY_RESPONSE,
            f"{tutor.user.full_name} accepted your enquiry",
            response_text or "Your enquiry was accepted. You can now message the tutor.",
            url=f"/messages/{conversation.pk}/", send_email=True,
        )
    else:
        notify(
            enquiry.sender, NotificationType.ENQUIRY_RESPONSE,
            f"{tutor.user.full_name} responded to your enquiry",
            response_text or f"Status: {enquiry.get_status_display()}",
            url="/student/enquiries/", send_email=True,
        )
    audit(request, "ENQUIRY_RESPONDED", target=f"enquiry:{enquiry.pk}",
          metadata={"status": enquiry.status})
    messages.success(request, "Enquiry updated.")
    return redirect("marketplace:tutor_enquiries")


@require_POST
@student_or_parent_required
def withdraw_enquiry(request, enquiry_id):
    enquiry = get_object_or_404(Enquiry, pk=enquiry_id, sender=request.user)  # IDOR-safe
    if enquiry.can_withdraw():
        enquiry.status = EnquiryStatus.WITHDRAWN
        enquiry.save(update_fields=["status", "updated_at"])
        messages.info(request, "Enquiry withdrawn.")
    else:
        messages.error(request, "This enquiry can no longer be withdrawn.")
    return redirect("marketplace:enquiry_list")


@require_POST
@student_or_parent_required
def close_enquiry(request, enquiry_id):
    enquiry = get_object_or_404(Enquiry, pk=enquiry_id, sender=request.user)
    enquiry.status = EnquiryStatus.CLOSED
    enquiry.save(update_fields=["status", "updated_at"])
    messages.info(request, "Enquiry closed.")
    return redirect("marketplace:enquiry_list")


# ---------------------------------------------------------------------------
# Tutor requests
# ---------------------------------------------------------------------------
def request_browse(request):
    """Public list of open tutor requests (tutors browse these)."""
    requests_qs = (
        TutorRequest.objects.filter(status=TutorRequestStatus.OPEN, is_deleted=False)
        .select_related("poster", "subject", "class_level", "location")
    )
    paginator = Paginator(requests_qs, 15)
    return render(
        request, "marketplace/request_browse.html",
        {"requests": paginator.get_page(request.GET.get("page"))},
    )


def request_detail(request, request_id):
    tutor_request = get_object_or_404(
        TutorRequest.objects.select_related("poster", "subject", "class_level", "location"),
        pk=request_id, is_deleted=False,
    )
    my_application = None
    if request.user.is_authenticated and getattr(request.user, "is_tutor", False):
        my_application = TutorApplication.objects.filter(
            request=tutor_request, tutor=request.user.tutor_profile
        ).first()
    applications = None
    if request.user.is_authenticated and (
        request.user == tutor_request.poster or request.user.is_platform_admin
    ):
        applications = tutor_request.applications.select_related("tutor__user")
    return render(
        request, "marketplace/request_detail.html",
        {"tutor_request": tutor_request, "my_application": my_application,
         "applications": applications},
    )


@ratelimit(key="user", rate=RATE_LIMITS["tutor_request"], method="POST", block=True)
@student_or_parent_required
def request_create(request):
    if request.method == "POST":
        form = TutorRequestForm(request.POST, user=request.user)
        if form.is_valid():
            tutor_request = form.save(commit=False)
            tutor_request.poster = request.user
            tutor_request.save()
            audit(request, "TUTOR_REQUEST_CREATED", target=f"request:{tutor_request.pk}")
            messages.success(request, "Your tutor request is live.")
            return redirect("marketplace:my_requests")
    else:
        form = TutorRequestForm(user=request.user)
    return render(request, "marketplace/request_form.html", {"form": form})


@student_or_parent_required
def my_requests(request):
    requests_qs = TutorRequest.objects.filter(poster=request.user).select_related(
        "subject", "class_level", "location"
    ).annotate()
    return render(request, "marketplace/my_requests.html", {"requests": requests_qs})


@require_POST
@student_or_parent_required
def request_close(request, request_id):
    tutor_request = get_object_or_404(TutorRequest, pk=request_id, poster=request.user)
    tutor_request.status = TutorRequestStatus.CANCELLED
    tutor_request.save(update_fields=["status", "updated_at"])
    messages.info(request, "Request cancelled.")
    return redirect("marketplace:my_requests")


@ratelimit(key="user", rate=RATE_LIMITS["tutor_application"], method="POST", block=True)
@tutor_required
def apply_to_request(request, request_id):
    tutor = request.user.tutor_profile
    tutor_request = get_object_or_404(
        TutorRequest, pk=request_id, status=TutorRequestStatus.OPEN, is_deleted=False
    )
    if tutor_request.poster == request.user:
        messages.error(request, "You cannot apply to your own request.")
        return redirect("marketplace:request_detail", request_id=request_id)
    if request.method == "POST":
        form = TutorApplicationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    application = form.save(commit=False)
                    application.tutor = tutor
                    application.request = tutor_request
                    application.save()
                    if tutor_request.status == TutorRequestStatus.OPEN:
                        tutor_request.status = TutorRequestStatus.RESPONDED
                        tutor_request.save(update_fields=["status", "updated_at"])
                notify(
                    tutor_request.poster, NotificationType.REQUEST_RESPONSE,
                    f"{tutor.user.full_name} responded to your request",
                    application.message[:300],
                    url=f"/requests/{tutor_request.pk}/", send_email=True,
                )
                audit(request, "APPLICATION_SUBMITTED", target=f"application:{application.pk}")
                messages.success(request, "Your response was sent.")
                return redirect("marketplace:request_detail", request_id=request_id)
            except IntegrityError:
                messages.info(request, "You have already responded to this request.")
                return redirect("marketplace:request_detail", request_id=request_id)
    else:
        form = TutorApplicationForm()
    return render(
        request, "marketplace/application_form.html",
        {"form": form, "tutor_request": tutor_request},
    )


@require_POST
@student_or_parent_required
def respond_application(request, application_id):
    """Accept/reject a tutor's application (request owner only)."""
    application = get_object_or_404(
        TutorApplication.objects.select_related("request", "tutor__user"),
        pk=application_id, request__poster=request.user,  # IDOR-safe
    )
    action = request.POST.get("action")
    if action in (ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED, ApplicationStatus.SHORTLISTED):
        application.status = action
        application.save(update_fields=["status", "updated_at"])
        notify(
            application.tutor.user, NotificationType.REQUEST_RESPONSE,
            f"Update on your application to \"{application.request.title}\"",
            f"Status: {application.get_status_display()}",
            url=f"/requests/{application.request_id}/", send_email=True,
        )
        messages.success(request, "Application updated.")
    return redirect("marketplace:request_detail", request_id=application.request_id)


# ---------------------------------------------------------------------------
# Saved tutors
# ---------------------------------------------------------------------------
@ratelimit(key="user", rate=RATE_LIMITS["save_tutor"], method="POST", block=True)
@require_POST
@student_or_parent_required
def toggle_save_tutor(request, tutor_id):
    tutor = get_object_or_404(TutorProfile, pk=tutor_id, is_published=True)
    existing = SavedTutor.objects.filter(user=request.user, tutor=tutor).first()
    if existing:
        existing.delete(hard=True)
        messages.info(request, f"{tutor.user.full_name} removed from your saved list.")
    else:
        try:
            SavedTutor.objects.create(user=request.user, tutor=tutor)
            messages.success(request, f"{tutor.user.full_name} saved to your list.")
        except IntegrityError:
            messages.info(request, "This tutor is already saved.")
    next_url = request.POST.get("next", "")
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect("tutors:detail", slug=tutor.slug)


# ---------------------------------------------------------------------------
# Demo class request (lightweight enquiry variant)
# ---------------------------------------------------------------------------
@ratelimit(key="user", rate=RATE_LIMITS["enquiry"], method="POST", block=True)
@require_POST
@student_or_parent_required
def request_demo(request, tutor_slug):
    tutor = get_object_or_404(TutorProfile.objects.select_related("user"),
                              slug=tutor_slug, is_published=True)
    if request.user == tutor.user:
        messages.error(request, "You cannot request a demo from yourself.")
        return redirect("tutors:detail", slug=tutor_slug)
    with transaction.atomic():
        enquiry = Enquiry.objects.create(
            tutor=tutor,
            sender=request.user,
            message="Demo class request: " + (request.POST.get("message", "")[:500] or "I would like to book a demo class."),
            subject=tutor.subjects.first(),
        )
    notify(
        tutor.user, NotificationType.DEMO_REQUEST,
        f"Demo class requested by {request.user.full_name}",
        enquiry.message[:300], url="/tutor/enquiries/", send_email=True,
    )
    messages.success(request, "Demo class request sent.")
    return redirect("tutors:detail", slug=tutor_slug)
