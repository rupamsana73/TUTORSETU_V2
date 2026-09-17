"""Review business rules (eligibility, duplicates, rating recompute)."""
from django.db import transaction
from django.db.models import Avg, Count

from marketplace.models import Enquiry, EnquiryStatus
from notifications.models import NotificationType
from notifications.services import notify

from .models import Review, ReviewStatus


def can_review(user, tutor_profile) -> tuple:
    """A student/parent may review a tutor after an ACCEPTED enquiry,
    never themselves, and only once per tutor (DB-enforced too)."""
    if not user.is_authenticated:
        return False, "Please log in."
    if user.pk == tutor_profile.user_id:
        return False, "Tutors cannot review themselves."
    if user.role not in ("STUDENT", "PARENT"):
        return False, "Only students and parents can leave reviews."
    if Review.objects.filter(tutor=tutor_profile, reviewer=user).exists():
        return False, "You have already reviewed this tutor."
    eligible = Enquiry.objects.filter(
        tutor=tutor_profile, sender=user, status=EnquiryStatus.ACCEPTED
    ).exists()
    if not eligible:
        return False, "You can review a tutor after they accept your enquiry."
    return True, ""


def recompute_tutor_rating(tutor_profile):
    aggregate = Review.objects.filter(
        tutor=tutor_profile, status=ReviewStatus.PUBLISHED
    ).aggregate(avg=Avg("rating"), count=Count("pk"))
    tutor_profile.average_rating = (aggregate["avg"] or 0)
    tutor_profile.reviews_count = aggregate["count"] or 0
    tutor_profile.save(update_fields=["average_rating", "reviews_count", "updated_at"])


@transaction.atomic
def create_review(user, tutor_profile, rating, title, text):
    allowed, reason = can_review(user, tutor_profile)
    if not allowed:
        raise PermissionError(reason)
    review = Review.objects.create(
        tutor=tutor_profile, reviewer=user, rating=rating, title=title, text=text
    )
    recompute_tutor_rating(tutor_profile)
    notify(
        tutor_profile.user, NotificationType.REVIEW_RECEIVED,
        f"New {rating}-star review from {user.full_name}",
        text[:300], url=f"/tutors/{tutor_profile.slug}/", send_email=True,
    )
    return review
