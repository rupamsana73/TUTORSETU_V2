"""Review views (Phase 7)."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from accounts.decorators import student_or_parent_required
from core.ratelimits import RATE_LIMITS
from core.utils import audit
from tutors.models import TutorProfile

from .forms import ReviewForm
from .models import Review, ReviewReport
from .services import can_review, create_review


@ratelimit(key="user", rate=RATE_LIMITS["review"], method="POST", block=True)
@student_or_parent_required
def create(request, tutor_slug):
    tutor = get_object_or_404(TutorProfile, slug=tutor_slug, is_published=True)
    allowed, reason = can_review(request.user, tutor)
    if not allowed:
        messages.error(request, reason)
        return redirect("tutors:detail", slug=tutor_slug)
    if request.method == "POST":
        form = ReviewForm(request.POST)
        if form.is_valid():
            try:
                create_review(
                    request.user, tutor,
                    form.cleaned_data["rating"], form.cleaned_data["title"],
                    form.cleaned_data["text"],
                )
                audit(request, "REVIEW_CREATED", target=f"tutor:{tutor.pk}")
                messages.success(request, "Thank you — your review is published.")
                return redirect("tutors:detail", slug=tutor_slug)
            except PermissionError as exc:
                messages.error(request, str(exc))
                return redirect("tutors:detail", slug=tutor_slug)
    else:
        form = ReviewForm()
    return render(request, "reviews/review_form.html", {"form": form, "tutor": tutor})


@ratelimit(key="user", rate=RATE_LIMITS["report"], method="POST", block=True)
@require_POST
@student_or_parent_required
def report_review(request, review_id):
    review = get_object_or_404(Review, pk=review_id)
    reason = (request.POST.get("reason") or "").strip()[:1000]
    if reason:
        _, created = ReviewReport.objects.get_or_create(
            review=review, reporter=request.user, defaults={"reason": reason}
        )
        if created:
            audit(request, "REVIEW_REPORTED", target=f"review:{review.pk}")
            messages.success(request, "The review has been reported to our team.")
        else:
            messages.info(request, "You have already reported this review.")
    return redirect("tutors:detail", slug=review.tutor.slug)
