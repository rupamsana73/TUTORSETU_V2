"""Tutor platform views: public discovery (Phase 5) + tutor area (Phase 3)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import tutor_required
from core.models import Board, ClassLevel, Subject
from locations.models import Location
from reviews.models import Review, ReviewStatus

from .forms import (
    AvailabilitySlotForm, Step1BasicForm, Step2EducationForm, Step3TeachingForm,
    Step4LocationForm, Step5FeesForm, TutorExtrasForm, TutorSearchForm,
)
from .models import (
    TeachingMode, TutorAvailability, TutorProfile, VerificationStatus, Weekday,
)
from .services import MatchPreferences, TutorMatchingService

ONBOARDING_STEPS = {
    1: ("Basic Information", Step1BasicForm),
    2: ("Education", Step2EducationForm),
    3: ("Teaching Details", Step3TeachingForm),
    4: ("Location", Step4LocationForm),
    5: ("Fees", Step5FeesForm),
}


# ---------------------------------------------------------------------------
# Public discovery (Phase 5)
# ---------------------------------------------------------------------------
def tutor_list(request):
    form = TutorSearchForm(request.GET or None)
    qs = (
        TutorProfile.objects.filter(is_published=True, is_deleted=False)
        .select_related("user", "city")
        .prefetch_related("subjects", "classes", "boards", "badges")
    )

    prefs_kwargs = {}
    if form.is_valid():
        cd = form.cleaned_data
        if cd.get("q"):
            qs = qs.filter(
                Q(user__full_name__icontains=cd["q"])
                | Q(subjects__name__icontains=cd["q"])
                | Q(tagline__icontains=cd["q"])
            ).distinct()
        if cd.get("subject"):
            qs = qs.filter(subjects__id=cd["subject"])
            prefs_kwargs["subject_id"] = cd["subject"]
        if cd.get("class_level"):
            qs = qs.filter(classes__id=cd["class_level"])
            prefs_kwargs["class_level_id"] = cd["class_level"]
        if cd.get("board"):
            qs = qs.filter(boards__id=cd["board"])
            prefs_kwargs["board_id"] = cd["board"]
        if cd.get("location"):
            qs = qs.filter(Q(city__id=cd["location"]) | Q(teaching_areas__location__id=cd["location"]))
            prefs_kwargs["location_id"] = cd["location"]
        if cd.get("mode"):
            qs = qs.filter(Q(teaching_mode=cd["mode"]) | Q(teaching_mode=TeachingMode.BOTH))
            prefs_kwargs["mode"] = cd["mode"]
        if cd.get("min_experience") is not None:
            qs = qs.filter(experience_years__gte=cd["min_experience"])
            prefs_kwargs["min_experience"] = cd["min_experience"]
        if cd.get("fee_min") is not None:
            qs = qs.filter(Q(hourly_fee__gte=cd["fee_min"]) | Q(monthly_fee__gte=cd["fee_min"]))
        if cd.get("fee_max") is not None:
            qs = qs.filter(Q(hourly_fee__lte=cd["fee_max"]) | Q(monthly_fee__lte=cd["fee_max"]))
        if cd.get("min_rating") is not None:
            qs = qs.filter(average_rating__gte=cd["min_rating"])
            prefs_kwargs["min_rating"] = float(cd["min_rating"])
        if cd.get("verified_only"):
            qs = qs.filter(verification_status=VerificationStatus.VERIFIED)
        if cd.get("weekday") is not None:
            qs = qs.filter(availability__weekday=cd["weekday"])
            prefs_kwargs["weekday"] = cd["weekday"]
        if cd.get("budget") is not None:
            prefs_kwargs["budget"] = float(cd["budget"])

        sort = cd.get("sort") or "relevance"
        if sort == "rating":
            qs = qs.order_by(F("average_rating").desc(nulls_last=True), "-reviews_count")
        elif sort == "experience":
            qs = qs.order_by("-experience_years")
        elif sort == "fee_low":
            qs = qs.order_by(F("hourly_fee").asc(nulls_last=True))
        elif sort == "fee_high":
            qs = qs.order_by(F("hourly_fee").desc(nulls_last=True))
        elif sort == "newest":
            qs = qs.order_by("-created_at")
        else:
            qs = qs.order_by("-verification_status", "-average_rating")

    qs = qs.distinct()

    # Smart matching scores (kept out of the view logic proper)
    matches = {}
    if prefs_kwargs:
        prefs = MatchPreferences(**prefs_kwargs)
        service = TutorMatchingService(prefs)
        scored = service.match(queryset=list(qs)[:60], limit=60)
        matches = {r.tutor.pk: r for r in scored}
        if (form.cleaned_data.get("sort") or "relevance") == "relevance":
            order = [r.tutor.pk for r in scored]
            qs = sorted(qs, key=lambda t: order.index(t.pk) if t.pk in order else len(order))

    paginator = Paginator(qs, 12)
    tutors_page = paginator.get_page(request.GET.get("page"))

    context = {
        "form": form,
        "tutors": tutors_page,
        "matches": matches,
        "weekdays": Weekday.choices,
        "search_meta": _search_meta(request),
        "meta_title": "Find Tutors in Kolkata & Howrah | TutorSetu",
        "meta_description": "Search verified local and online tutors by subject, class, board, budget and location across Kolkata and Howrah.",
    }
    return render(request, "tutors/tutor_list.html", context)


def _search_meta(request):
    return {
        "subjects": Subject.objects.filter(is_active=True, is_deleted=False),
        "classes": ClassLevel.objects.filter(is_active=True, is_deleted=False),
        "boards": Board.objects.filter(is_active=True, is_deleted=False),
        "locations": Location.objects.filter(is_active=True, is_deleted=False),
    }


def tutor_detail(request, slug):
    tutor = get_object_or_404(
        TutorProfile.objects.select_related("user", "city").prefetch_related(
            "subjects", "classes", "boards", "availability", "badges",
            "teaching_areas__location",
        ),
        slug=slug, is_deleted=False,
    )
    public = tutor.is_published
    if not public:
        # Only the owner and admins can view an unpublished profile.
        if not (request.user.is_authenticated and (
            request.user == tutor.user or request.user.is_platform_admin
        )):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("This tutor profile is not available.")
    else:
        TutorProfile.objects.filter(pk=tutor.pk).update(profile_views=F("profile_views") + 1)

    reviews = tutor.reviews.filter(status=ReviewStatus.PUBLISHED).select_related("reviewer")[:20]
    from marketplace.models import SavedTutor

    is_saved = (
        request.user.is_authenticated
        and SavedTutor.objects.filter(user=request.user, tutor=tutor).exists()
    )
    primary_subject = tutor.subjects.first()
    primary = primary_subject.name if primary_subject else "Tutor"
    city = tutor.city.city if tutor.city_id else "Kolkata"
    return render(
        request,
        "tutors/tutor_detail.html",
        {
            "tutor": tutor,
            "reviews": reviews,
            "is_saved": is_saved,
            "weekday_labels": dict(Weekday.choices),
            "meta_title": f"{primary} Tutor in {city} | TutorSetu",
            "meta_description": (tutor.tagline or f"Book {tutor.user.full_name}, a {primary} tutor in {city}, on TutorSetu.")[:155],
        },
    )


# ---------------------------------------------------------------------------
# Tutor area (Phase 3)
# ---------------------------------------------------------------------------
def _get_own_profile(request):
    return get_object_or_404(TutorProfile, user=request.user)


@tutor_required
def tutor_dashboard(request):
    tutor = _get_own_profile(request)
    enquiries = tutor.enquiries.select_related("sender", "subject").order_by("-created_at")[:5]
    from marketplace.models import TutorApplication, TutorRequestStatus

    applications = tutor.applications.select_related("request").order_by("-created_at")[:5]
    from messaging.models import Conversation

    conversations = Conversation.objects.filter(participants=request.user).count()
    pending_enquiries = tutor.enquiries.filter(status="PENDING").count()
    return render(
        request,
        "tutors/dashboard.html",
        {
            "tutor": tutor,
            "enquiries": enquiries,
            "applications": applications,
            "conversations_count": conversations,
            "pending_enquiries": pending_enquiries,
            "completion": _profile_completion(tutor),
        },
    )


def _profile_completion(tutor):
    checks = [
        bool(tutor.user.profile_image),
        bool(tutor.about),
        bool(tutor.highest_qualification),
        tutor.subjects.exists(),
        tutor.classes.exists(),
        bool(tutor.city_id),
        tutor.availability.exists(),
        bool(tutor.hourly_fee or tutor.monthly_fee),
    ]
    done = sum(1 for c in checks if c)
    return int(done / len(checks) * 100)


@tutor_required
def onboarding(request, step):
    step = int(step)
    if step not in ONBOARDING_STEPS:
        return redirect("tutors:onboarding", step=1)
    title, form_class = ONBOARDING_STEPS[step]
    tutor = _get_own_profile(request)
    kwargs = {"instance": tutor}
    if form_class is Step1BasicForm:
        kwargs["user"] = request.user
    if request.method == "POST":
        form = form_class(request.POST, request.FILES, **kwargs)
        if form.is_valid():
            with transaction.atomic():
                form.save()
            if step < max(ONBOARDING_STEPS):
                return redirect("tutors:onboarding", step=step + 1)
            return redirect("tutors:availability")
    else:
        form = form_class(**kwargs)
    return render(
        request,
        "tutors/onboarding.html",
        {"form": form, "step": step, "steps": ONBOARDING_STEPS, "title": title},
    )


@tutor_required
def availability_view(request):
    tutor = _get_own_profile(request)
    if request.method == "POST":
        form = AvailabilitySlotForm(request.POST)
        if form.is_valid():
            slot = form.save(commit=False)
            slot.tutor = tutor
            if slot.end_time <= slot.start_time:
                form.add_error("end_time", "End time must be after start time.")
            else:
                try:
                    slot.save()
                    messages.success(request, "Availability slot added.")
                    return redirect("tutors:availability")
                except Exception:
                    form.add_error(None, "This slot already exists.")
    else:
        form = AvailabilitySlotForm()
    slots = tutor.availability.all()
    return render(
        request,
        "tutors/availability.html",
        {"form": form, "slots": slots, "weekday_labels": dict(Weekday.choices)},
    )


@require_POST
@tutor_required
def delete_slot(request, slot_id):
    tutor = _get_own_profile(request)
    slot = get_object_or_404(TutorAvailability, pk=slot_id, tutor=tutor)  # IDOR-safe
    slot.delete(hard=True)
    messages.info(request, "Slot removed.")
    return redirect("tutors:availability")


@tutor_required
def profile_edit_extras(request):
    tutor = _get_own_profile(request)
    if request.method == "POST":
        form = TutorExtrasForm(request.POST, instance=tutor)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile details updated.")
            return redirect("tutors:profile_edit")
    else:
        form = TutorExtrasForm(instance=tutor)
    return render(request, "tutors/profile_extras.html", {"form": form, "tutor": tutor})


@tutor_required
def profile_edit(request):
    """Hub page for editing all profile sections."""
    tutor = _get_own_profile(request)
    return render(
        request,
        "tutors/profile_edit.html",
        {"tutor": tutor, "completion": _profile_completion(tutor)},
    )


@require_POST
@tutor_required
def toggle_publish(request):
    tutor = _get_own_profile(request)
    if not tutor.is_published:
        if _profile_completion(tutor) < 60:
            messages.error(request, "Complete at least 60% of your profile before publishing.")
            return redirect("tutors:profile_edit")
        tutor.is_published = True
        tutor.save(update_fields=["is_published", "updated_at"])
        messages.success(request, "Your profile is now live.")
    else:
        tutor.is_published = False
        tutor.save(update_fields=["is_published", "updated_at"])
        messages.info(request, "Your profile is now hidden from search.")
    return redirect("tutors:dashboard")


@tutor_required
def tutor_students(request):
    """Students/parents connected via accepted enquiries."""
    tutor = _get_own_profile(request)
    accepted = tutor.enquiries.filter(status="ACCEPTED").select_related(
        "sender", "subject", "class_level", "child"
    )
    return render(request, "tutors/students.html", {"enquiries": accepted})
