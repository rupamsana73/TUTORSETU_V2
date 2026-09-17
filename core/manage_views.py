"""Platform management dashboard (/admin/dashboard/...) — Phase 8.

All views are admin-only and server-side enforced. Every sensitive action is
audit-logged with actor, target and IP.
"""
import json
import logging
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required
from accounts.models import AccountStatus, UserRole
from core.models import AuditLog, Board, ClassLevel, PlatformSetting, Subject, SubjectCategory
from core.utils import audit
from locations.models import Location
from marketplace.models import Enquiry, TutorApplication, TutorRequest
from messaging.models import Conversation
from notifications.models import Notification, NotificationType
from notifications.services import notify
from reports.models import Report, ReportStatus
from reviews.models import Review, ReviewStatus
from reviews.services import recompute_tutor_rating
from tutors.models import TutorProfile, VerificationStatus
from verification.models import TutorBadge, TutorVerification, VerificationBadge

User = get_user_model()
logger = logging.getLogger("tutorsetu")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@admin_required
def dashboard(request):
    today = timezone.now().date()
    days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    signups = {
        row["d"].strftime("%Y-%m-%d"): row["c"]
        for row in (
            User.objects.filter(date_joined__date__gte=days[0])
            .annotate(d=TruncDate("date_joined"))
            .values("d").annotate(c=Count("pk"))
        )
    }
    enquiry_counts = {
        row["d"].strftime("%Y-%m-%d"): row["c"]
        for row in (
            Enquiry.objects.filter(created_at__date__gte=days[0])
            .annotate(d=TruncDate("created_at"))
            .values("d").annotate(c=Count("pk"))
        )
    }
    stats = {
        "total_users": User.objects.count(),
        "students": User.objects.filter(role=UserRole.STUDENT).count(),
        "parents": User.objects.filter(role=UserRole.PARENT).count(),
        "tutors": User.objects.filter(role=UserRole.TUTOR).count(),
        "verified_tutors": TutorProfile.objects.filter(verification_status=VerificationStatus.VERIFIED).count(),
        "pending_verification": TutorProfile.objects.filter(verification_status=VerificationStatus.PENDING).count(),
        "active_enquiries": Enquiry.objects.filter(status__in=("PENDING", "CONTACTED", "ACCEPTED")).count(),
        "tutor_requests": TutorRequest.objects.count(),
        "reviews": Review.objects.count(),
        "open_reports": Report.objects.filter(status__in=(ReportStatus.OPEN, ReportStatus.UNDER_REVIEW)).count(),
    }
    return render(request, "manage/dashboard.html", {
        "stats": stats,
        "chart_labels": json.dumps([d.strftime("%b %d") for d in days]),
        "chart_users": json.dumps([signups.get(d.strftime("%Y-%m-%d"), 0) for d in days]),
        "chart_enquiries": json.dumps([enquiry_counts.get(d.strftime("%Y-%m-%d"), 0) for d in days]),
        "recent_users": User.objects.order_by("-date_joined")[:8],
        "pending_verifications": TutorVerification.objects.filter(status="PENDING")[:5],
    })


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------
@admin_required
def users_list(request, role=None):
    qs = User.objects.all().order_by("-date_joined")
    if role in (UserRole.STUDENT, UserRole.PARENT, UserRole.TUTOR, UserRole.ADMIN):
        qs = qs.filter(role=role)
    status = request.GET.get("status")
    if status in dict(AccountStatus.choices):
        qs = qs.filter(status=status)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(email__icontains=q))
    paginator = Paginator(qs, 20)
    return render(request, "manage/users.html", {
        "users_page": paginator.get_page(request.GET.get("page")),
        "role": role, "q": q, "status": status,
        "statuses": AccountStatus.choices,
    })


@admin_required
def user_detail(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    return render(request, "manage/user_detail.html", {"target_user": user})


@require_POST
@admin_required
def user_delete(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    if user.is_platform_admin:
        messages.error(request, "Admin accounts cannot be deleted here.")
        return redirect("manage:user_detail", user_id=user.pk)

    deleted_user_id = user.pk
    deleted_role = user.role
    files = []
    if user.profile_image:
        files.append((user.profile_image.storage, user.profile_image.name))

    tutor = getattr(user, "tutor_profile", None)
    if tutor:
        files.extend(
            (image.image.storage, image.image.name)
            for image in tutor.gallery.all()
            if image.image
        )
        files.extend(
            (document.file.storage, document.file.name)
            for verification in tutor.verifications.prefetch_related("documents")
            for document in verification.documents.all()
            if document.file
        )

    with transaction.atomic():
        audit(
            request,
            "ADMIN_USER_DELETED",
            target=deleted_user_id,
            metadata={"deleted_user_id": deleted_user_id, "deleted_role": deleted_role},
        )
        user.delete()

    for storage, name in files:
        try:
            storage.delete(name)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to delete uploaded file after user deletion")

    messages.success(request, "The user account was permanently deleted.")
    return redirect("manage:users")


@require_POST
@admin_required
def user_set_status(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    new_status = request.POST.get("status")
    if new_status not in dict(AccountStatus.choices):
        messages.error(request, "Invalid status.")
        return redirect("manage:user_detail", user_id=user.pk)
    if user.is_platform_admin and new_status in (AccountStatus.SUSPENDED, AccountStatus.BANNED):
        messages.error(request, "Admin accounts cannot be suspended or banned here.")
        return redirect("manage:user_detail", user_id=user.pk)
    old = user.status
    with transaction.atomic():
        user.status = new_status
        user.is_active = new_status != AccountStatus.BANNED
        user.save(update_fields=["status", "is_active"])
    audit(request, f"USER_{new_status}", target=user.email, metadata={"old": old})
    notify(user, NotificationType.ACCOUNT_STATUS,
           f"Your account status changed to {dict(AccountStatus.choices)[new_status]}",
           "If you believe this is a mistake, contact TutorSetu support.",
           send_email=True)
    messages.success(request, f"{user.full_name}'s status is now {new_status}.")
    return redirect("manage:user_detail", user_id=user.pk)


@require_POST
@admin_required
def user_password_reset(request, user_id):
    """Trigger a reset email — admins never see or set plaintext passwords."""
    user = get_object_or_404(User, pk=user_id)
    from django.contrib.auth.forms import PasswordResetForm

    form = PasswordResetForm({"email": user.email})
    if form.is_valid():
        form.save(
            request=request, use_https=request.is_secure(),
            email_template_name="accounts/emails/password_reset_email.html",
            subject_template_name="accounts/emails/password_reset_subject.txt",
        )
        audit(request, "ADMIN_PASSWORD_RESET_SENT", target=user.email)
        messages.success(request, f"Password reset email sent to {user.email}.")
    return redirect("manage:user_detail", user_id=user.pk)


# ---------------------------------------------------------------------------
# Tutor verification (Phase 7/8 queue)
# ---------------------------------------------------------------------------
@admin_required
def verification_queue(request):
    status = request.GET.get("status", "PENDING")
    qs = TutorVerification.objects.select_related("tutor__user", "reviewed_by")
    if status in dict(VerificationStatus.choices):
        qs = qs.filter(status=status)
    paginator = Paginator(qs, 15)
    return render(request, "manage/verifications.html", {
        "verifications": paginator.get_page(request.GET.get("page")),
        "status": status, "statuses": VerificationStatus.choices,
    })


@admin_required
def verification_detail(request, verification_id):
    verification = get_object_or_404(
        TutorVerification.objects.select_related("tutor__user").prefetch_related("documents"),
        pk=verification_id,
    )
    return render(request, "manage/verification_detail.html", {
        "verification": verification, "badges": VerificationBadge.choices,
    })


@require_POST
@admin_required
def verification_decide(request, verification_id):
    verification = get_object_or_404(TutorVerification, pk=verification_id)
    action = request.POST.get("action")
    reason = (request.POST.get("reason") or "").strip()
    tutor = verification.tutor

    if action == "approve":
        with transaction.atomic():
            verification.status = VerificationStatus.VERIFIED
            verification.reviewed_by = request.user
            verification.reviewed_at = timezone.now()
            verification.rejection_reason = ""
            verification.save()
            tutor.verification_status = VerificationStatus.VERIFIED
            tutor.save(update_fields=["verification_status", "updated_at"])
            # Award badges based on the documents actually submitted.
            submitted = set(verification.documents.values_list("document_type", flat=True))
            badge_map = {
                "ID_DOCUMENT": VerificationBadge.IDENTITY,
                "QUALIFICATION": VerificationBadge.QUALIFICATION,
            }
            for doc_type, badge in badge_map.items():
                if doc_type in submitted:
                    TutorBadge.objects.get_or_create(
                        tutor=tutor, badge=badge, defaults={"awarded_by": request.user}
                    )
            TutorBadge.objects.get_or_create(
                tutor=tutor, badge=VerificationBadge.PROFILE, defaults={"awarded_by": request.user}
            )
        audit(request, "TUTOR_APPROVED", target=tutor.user.email,
              metadata={"verification": verification.pk})
        notify(tutor.user, NotificationType.VERIFICATION_RESULT,
               "Your tutor profile has been verified! 🎉",
               "You now have a verified badge on your TutorSetu profile.",
               url="/tutor/verification/", send_email=True)
        messages.success(request, f"{tutor.user.full_name} verified.")
    elif action in ("reject", "changes"):
        if not reason:
            messages.error(request, "A reason is required when rejecting or requesting changes.")
            return redirect("manage:verification_detail", verification_id=verification.pk)
        status = VerificationStatus.REJECTED if action == "reject" else VerificationStatus.PENDING
        with transaction.atomic():
            verification.status = status
            verification.rejection_reason = reason
            verification.reviewed_by = request.user
            verification.reviewed_at = timezone.now()
            verification.save()
            tutor.verification_status = status
            tutor.save(update_fields=["verification_status", "updated_at"])
        audit(request, "TUTOR_REJECTED" if action == "reject" else "TUTOR_CHANGES_REQUESTED",
              target=tutor.user.email, metadata={"reason": reason})
        notify(tutor.user, NotificationType.VERIFICATION_RESULT,
               "Action needed on your verification",
               reason, url="/tutor/verification/", send_email=True)
        messages.info(request, "Verification updated.")
    else:
        messages.error(request, "Invalid action.")
    return redirect("manage:verifications")


@admin_required
def verification_document(request, document_id):
    """Private document download — admin only, never public-media served."""
    from django.http import FileResponse, Http404

    from verification.models import VerificationDocument

    document = get_object_or_404(VerificationDocument, pk=document_id)
    if not document.file:
        raise Http404
    audit(request, "VERIFICATION_DOC_VIEWED", target=f"document:{document_id}")
    return FileResponse(document.file.open("rb"), as_attachment=False)


# ---------------------------------------------------------------------------
# Marketplace management
# ---------------------------------------------------------------------------
@admin_required
def enquiries(request):
    qs = Enquiry.objects.select_related("tutor__user", "sender", "subject")
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    paginator = Paginator(qs, 20)
    return render(request, "manage/enquiries.html", {
        "enquiries": paginator.get_page(request.GET.get("page")), "status": status,
    })


@admin_required
def requests_admin(request):
    qs = TutorRequest.objects.select_related("poster", "subject")
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    paginator = Paginator(qs, 20)
    return render(request, "manage/requests.html", {
        "requests": paginator.get_page(request.GET.get("page")), "status": status,
    })


@admin_required
def applications_admin(request):
    qs = TutorApplication.objects.select_related("tutor__user", "request")
    paginator = Paginator(qs, 20)
    return render(request, "manage/applications.html", {
        "applications": paginator.get_page(request.GET.get("page")),
    })


# ---------------------------------------------------------------------------
# Content management: subjects / classes / boards / locations
# ---------------------------------------------------------------------------
CONTENT_MODELS = {
    "subjects": (Subject, ("name", "category", "is_active")),
    "classes": (ClassLevel, ("name", "order", "is_active")),
    "boards": (Board, ("name", "is_active")),
    "locations": (Location, ("city", "area", "pincode", "latitude", "longitude", "is_active")),
    "categories": (SubjectCategory, ("name",)),
}


@admin_required
def content_list(request, kind):
    model_fields = CONTENT_MODELS.get(kind)
    if not model_fields:
        messages.error(request, "Unknown content type.")
        return redirect("manage:dashboard")
    model, fields = model_fields
    items = model.objects.all()
    paginator = Paginator(items, 25)
    return render(request, "manage/content_list.html", {
        "kind": kind, "items_page": paginator.get_page(request.GET.get("page")),
        "fields": fields,
    })


@admin_required
def content_edit(request, kind, object_id=None):
    from django.forms import modelform_factory

    model_fields = CONTENT_MODELS.get(kind)
    if not model_fields:
        messages.error(request, "Unknown content type.")
        return redirect("manage:dashboard")
    model, fields = model_fields
    instance = get_object_or_404(model, pk=object_id) if object_id else None
    form_class = modelform_factory(model, fields=list(fields))

    if request.method == "POST":
        form = form_class(request.POST, instance=instance)
        if form.is_valid():
            obj = form.save()
            audit(request, f"CONTENT_{'UPDATED' if instance else 'CREATED'}",
                  target=f"{kind}:{obj.pk}")
            messages.success(request, "Saved.")
            return redirect("manage:content_list", kind=kind)
    else:
        form = form_class(instance=instance)
    return render(request, "manage/content_form.html",
                  {"form": form, "kind": kind, "instance": instance})


# ---------------------------------------------------------------------------
# Trust & safety management
# ---------------------------------------------------------------------------
@admin_required
def reviews_admin(request):
    qs = Review.objects.select_related("tutor__user", "reviewer")
    status = request.GET.get("status")
    if status in dict(ReviewStatus.choices):
        qs = qs.filter(status=status)
    paginator = Paginator(qs, 20)
    return render(request, "manage/reviews.html", {
        "reviews": paginator.get_page(request.GET.get("page")),
        "status": status, "statuses": ReviewStatus.choices,
    })


@require_POST
@admin_required
def review_moderate(request, review_id):
    review = get_object_or_404(Review, pk=review_id)
    action = request.POST.get("action")
    mapping = {"hide": ReviewStatus.HIDDEN, "publish": ReviewStatus.PUBLISHED, "remove": ReviewStatus.REMOVED}
    if action in mapping:
        review.status = mapping[action]
        review.save(update_fields=["status", "updated_at"])
        recompute_tutor_rating(review.tutor)
        audit(request, f"REVIEW_{action.upper()}", target=f"review:{review.pk}")
        messages.success(request, "Review updated.")
    return redirect("manage:reviews")


@admin_required
def reports_admin(request):
    qs = Report.objects.select_related("reporter", "target_content_type", "handled_by")
    status = request.GET.get("status")
    if status in dict(ReportStatus.choices):
        qs = qs.filter(status=status)
    paginator = Paginator(qs, 20)
    return render(request, "manage/reports.html", {
        "reports": paginator.get_page(request.GET.get("page")),
        "status": status, "statuses": ReportStatus.choices,
    })


@require_POST
@admin_required
def report_handle(request, report_id):
    report = get_object_or_404(Report, pk=report_id)
    action = request.POST.get("action")
    notes = (request.POST.get("notes") or "").strip()[:2000]
    mapping = {
        "review": ReportStatus.UNDER_REVIEW,
        "resolve": ReportStatus.RESOLVED,
        "dismiss": ReportStatus.DISMISSED,
    }
    if action in mapping:
        report.status = mapping[action]
        report.resolution_notes = notes
        report.handled_by = request.user
        report.save(update_fields=["status", "resolution_notes", "handled_by", "updated_at"])
        audit(request, "REPORT_RESOLVED" if action == "resolve" else f"REPORT_{action.upper()}",
              target=f"report:{report.pk}")
        messages.success(request, "Report updated.")
    return redirect("manage:reports")


# ---------------------------------------------------------------------------
# System: notifications, audit logs, settings
# ---------------------------------------------------------------------------
@admin_required
def notifications_admin(request):
    if request.method == "POST":
        role = request.POST.get("role")
        title = (request.POST.get("title") or "").strip()[:200]
        body = (request.POST.get("body") or "").strip()
        if title:
            qs = User.objects.filter(is_active=True)
            if role in dict(UserRole.choices):
                qs = qs.filter(role=role)
            count = 0
            for user in qs[:500]:
                notify(user, NotificationType.GENERIC, title, body, send_email=False)
                count += 1
            audit(request, "BROADCAST_NOTIFICATION", target=role or "ALL",
                  metadata={"count": count})
            messages.success(request, f"Notification sent to {count} users.")
            return redirect("manage:notifications")
    recent = Notification.objects.select_related("recipient")[:30]
    return render(request, "manage/notifications.html", {
        "recent": recent, "roles": UserRole.choices,
    })


@admin_required
def audit_logs(request):
    qs = AuditLog.objects.select_related("user")
    action = request.GET.get("action", "").strip()
    if action:
        qs = qs.filter(action__icontains=action)
    paginator = Paginator(qs, 30)
    return render(request, "manage/audit_logs.html", {
        "logs": paginator.get_page(request.GET.get("page")), "action": action,
    })


@admin_required
def settings_admin(request):
    if request.method == "POST":
        for key, value in request.POST.items():
            if key.startswith("setting__"):
                setting_key = key[len("setting__"):]
                PlatformSetting.objects.filter(key=setting_key).update(value=value)
        audit(request, "SETTINGS_CHANGED")
        messages.success(request, "Settings saved.")
        return redirect("manage:settings")
    return render(request, "manage/settings.html", {
        "settings_list": PlatformSetting.objects.all().order_by("key"),
    })
