"""Parent dashboard & children management (Phase 4)."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import parent_required
from marketplace.models import Enquiry, SavedTutor, TutorRequest
from students.views import saved_tutors  # shared view

from .forms import ChildForm
from .models import ParentProfile, StudentChild


@parent_required
def dashboard(request):
    user = request.user
    profile = user.parent_profile
    return render(
        request,
        "parents/dashboard.html",
        {
            "children": profile.children.prefetch_related("subjects"),
            "saved_count": SavedTutor.objects.filter(user=user).count(),
            "active_enquiries": Enquiry.objects.filter(
                sender=user, status__in=["PENDING", "CONTACTED", "ACCEPTED"]
            ).select_related("tutor__user")[:5],
            "requests": TutorRequest.objects.filter(poster=user)[:5],
        },
    )


@parent_required
def children(request):
    profile = request.user.parent_profile
    return render(request, "parents/children.html", {"children": profile.children.all()})


@parent_required
def child_create(request):
    if request.method == "POST":
        form = ChildForm(request.POST)
        if form.is_valid():
            child = form.save(commit=False)
            child.parent = request.user.parent_profile
            child.save()
            form.save_m2m()
            messages.success(request, f"{child.name} added.")
            return redirect("parents:children")
    else:
        form = ChildForm()
    return render(request, "parents/child_form.html", {"form": form, "title": "Add Child"})


@parent_required
def child_edit(request, child_id):
    # IDOR-safe: child must belong to the logged-in parent
    child = get_object_or_404(StudentChild, pk=child_id, parent=request.user.parent_profile)
    if request.method == "POST":
        form = ChildForm(request.POST, instance=child)
        if form.is_valid():
            form.save()
            messages.success(request, "Child details updated.")
            return redirect("parents:children")
    else:
        form = ChildForm(instance=child)
    return render(request, "parents/child_form.html", {"form": form, "title": "Edit Child"})


@require_POST
@parent_required
def child_delete(request, child_id):
    child = get_object_or_404(StudentChild, pk=child_id, parent=request.user.parent_profile)
    child.delete()
    messages.info(request, f"{child.name} removed.")
    return redirect("parents:children")


@parent_required
def parent_profile_view(request):
    return render(request, "parents/profile.html", {"profile": request.user.parent_profile})
