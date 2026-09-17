"""Student dashboard & saved tutors (Phase 4)."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.decorators import student_or_parent_required, student_required
from marketplace.models import Enquiry, SavedTutor, TutorRequest


@student_required
def dashboard(request):
    user = request.user
    context = {
        "saved_tutors": SavedTutor.objects.filter(user=user).select_related(
            "tutor__user", "tutor__city"
        )[:6],
        "active_enquiries": Enquiry.objects.filter(
            sender=user, status__in=["PENDING", "CONTACTED", "ACCEPTED"]
        ).select_related("tutor__user")[:5],
        "requests": TutorRequest.objects.filter(poster=user)[:5],
        "recommended": _recommended(request),
    }
    return render(request, "students/dashboard.html", context)


def _recommended(request):
    """Smart-matching recommendations for the student dashboard."""
    from tutors.services import MatchPreferences, TutorMatchingService

    profile = getattr(request.user, "student_profile", None)
    if not profile or not profile.class_level_id:
        return []
    prefs = MatchPreferences(
        class_level_id=profile.class_level_id,
        board_id=profile.board_id,
        location_id=profile.preferred_location_id,
    )
    return TutorMatchingService(prefs).match(limit=6)


@student_or_parent_required
def saved_tutors(request):
    saved = SavedTutor.objects.filter(user=request.user).select_related(
        "tutor__user", "tutor__city"
    ).prefetch_related("tutor__subjects")
    return render(request, "marketplace/saved_tutors.html", {"saved": saved})


@student_required
def student_profile_view(request):
    return render(request, "students/profile.html", {"profile": request.user.student_profile})
