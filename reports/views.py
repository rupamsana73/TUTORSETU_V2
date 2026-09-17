"""User reporting views (Phase 7)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404, redirect, render
from django_ratelimit.decorators import ratelimit

from core.ratelimits import RATE_LIMITS
from core.utils import audit
from tutors.models import TutorProfile

from .forms import ReportForm
from .models import Report

REPORTABLE = {
    "tutor": TutorProfile,
}


@ratelimit(key="user", rate=RATE_LIMITS["report"], method="POST", block=True)
@login_required
def report_target(request, target_type, object_id):
    model = REPORTABLE.get(target_type)
    if model is None:
        messages.error(request, "Unsupported report type.")
        return redirect("core:home")
    target = get_object_or_404(model, pk=object_id)
    if target_type == "tutor" and hasattr(target, "user_id") and target.user_id == request.user.pk:
        messages.error(request, "You cannot report yourself.")
        return redirect("tutors:list")

    if request.method == "POST":
        form = ReportForm(request.POST)
        if form.is_valid():
            report, created = Report.objects.get_or_create(
                reporter=request.user,
                target_content_type=ContentType.objects.get_for_model(model),
                target_object_id=target.pk,
                defaults={
                    "category": form.cleaned_data["category"],
                    "description": form.cleaned_data["description"],
                },
            )
            if created:
                audit(request, "REPORT_FILED", target=f"{target_type}:{target.pk}")
                messages.success(request, "Thank you. Our safety team will review this report.")
            else:
                messages.info(request, "You have already reported this.")
            if target_type == "tutor":
                return redirect("tutors:detail", slug=target.slug)
            return redirect("core:home")
    else:
        form = ReportForm()
    return render(
        request, "reports/report_form.html",
        {"form": form, "target": target, "target_type": target_type},
    )
