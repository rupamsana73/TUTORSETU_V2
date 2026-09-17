"""Public pages, error handlers, and static content views."""
from django.shortcuts import get_object_or_404, render

from core.models import Subject, SubjectCategory
from locations.models import Location
from tutors.models import TeachingMode, TutorProfile, VerificationStatus


def home(request):
    featured = (
        TutorProfile.objects.filter(is_published=True, is_deleted=False)
        .select_related("user", "city")
        .prefetch_related("subjects")
        .order_by("-verification_status", "-average_rating")[:6]
    )
    context = {
        "featured_tutors": featured,
        "popular_subjects": Subject.objects.filter(is_active=True, is_deleted=False)[:10],
        "popular_locations": Location.objects.filter(is_active=True, is_deleted=False)[:8],
        "subject_categories": SubjectCategory.objects.all()[:8],
        "teaching_modes": TeachingMode.choices,
        "meta_title": "TutorSetu — Find the Right Tutor. Learn the Right Way.",
        "meta_description": "Discover trusted local and online tutors across Kolkata and Howrah. Search by subject, class, board, budget and location.",
    }
    return render(request, "core/home.html", context)


def about(request):
    return render(request, "core/about.html", {
        "meta_title": "About TutorSetu",
        "meta_description": "TutorSetu connects students, parents and trusted tutors across Kolkata, Howrah and West Bengal.",
    })


def how_it_works(request):
    return render(request, "core/how_it_works.html", {
        "meta_title": "How TutorSetu Works",
        "meta_description": "Search tutors, compare profiles, send enquiries and start learning — how TutorSetu works for students, parents and tutors.",
    })


def become_a_tutor(request):
    return render(request, "core/become_a_tutor.html", {
        "meta_title": "Become a Tutor | TutorSetu",
        "meta_description": "Join TutorSetu as a tutor. Create a professional profile, get verified and connect with students in Kolkata and Howrah.",
    })


def subjects(request):
    categories = SubjectCategory.objects.prefetch_related("subjects")
    return render(request, "core/subjects.html", {
        "categories": categories,
        "meta_title": "Subjects | TutorSetu",
        "meta_description": "Browse tutors by subject — Mathematics, Physics, Chemistry, Bengali, Computer Science and more.",
    })


def subject_detail(request, slug):
    subject = get_object_or_404(
        Subject.objects.prefetch_related("tutors__user", "tutors__city"),
        slug=slug, is_active=True, is_deleted=False,
    )
    tutors = subject.tutors.filter(is_published=True, is_deleted=False).distinct()[:24]
    return render(request, "core/subject_detail.html", {
        "subject": subject, "tutors": tutors,
        "meta_title": f"{subject.name} Tutors in Kolkata & Howrah | TutorSetu",
        "meta_description": f"Find verified {subject.name} tutors near you on TutorSetu.",
    })


def locations(request):
    all_locations = Location.objects.filter(is_active=True, is_deleted=False)
    return render(request, "core/locations.html", {
        "locations": all_locations,
        "meta_title": "Tutoring Locations | TutorSetu",
        "meta_description": "Find tutors across Shibpur, Howrah Maidan, Salt Lake, New Town and more.",
    })


def location_detail(request, slug):
    location = get_object_or_404(Location, slug=slug, is_active=True, is_deleted=False)
    tutors = (
        TutorProfile.objects.filter(
            is_published=True, is_deleted=False
        ).filter(city=location) | TutorProfile.objects.filter(
            is_published=True, is_deleted=False, teaching_areas__location=location
        )
    ).distinct().select_related("user", "city")[:24]
    return render(request, "core/location_detail.html", {
        "location": location, "tutors": tutors,
        "meta_title": f"Tutors in {location.area}, {location.city} | TutorSetu",
        "meta_description": f"Find trusted tutors in {location.area}, {location.city} on TutorSetu.",
    })


# ---------------------------------------------------------------------------
# Error handlers — no stack traces, friendly pages
# ---------------------------------------------------------------------------
def error_404(request, exception=None):
    return render(request, "404.html", status=404)


def error_403(request, exception=None):
    return render(request, "403.html", status=403)


def error_500(request):
    return render(request, "500.html", status=500)
