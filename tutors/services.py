"""Search & smart matching services (Phase 5).

The matching engine is deliberately kept separate from views and is
replaceable — a future AI matcher only needs to expose the same interface.
"""
import math
from dataclasses import dataclass, field

from django.db.models import Avg, Count, F, Q

from .models import TeachingMode, TutorProfile, VerificationStatus


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in kilometres."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    radius = 6371.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlmb = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


@dataclass
class MatchPreferences:
    """Student/parent requirements used by the matching engine."""

    subject_id: int | None = None
    class_level_id: int | None = None
    board_id: int | None = None
    location_id: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float | None = None
    mode: str | None = None
    budget: float | None = None          # max acceptable hourly fee
    min_experience: int | None = None
    min_rating: float | None = None
    weekday: int | None = None


@dataclass
class MatchResult:
    tutor: TutorProfile
    score: float
    reasons: list = field(default_factory=list)


# Static weights — easy to tune or replace with a trained model later.
WEIGHTS = {
    "subject": 30,
    "class_level": 20,
    "board": 10,
    "mode": 10,
    "location": 10,
    "distance": 5,
    "budget": 5,
    "experience": 3,
    "rating": 4,
    "verified": 3,
}


class TutorMatchingService:
    """Scores published tutors against a student's preferences."""

    def __init__(self, preferences: MatchPreferences):
        self.prefs = preferences

    def base_queryset(self):
        return (
            TutorProfile.objects.filter(
                is_published=True, is_deleted=False,
                verification_status__in=(VerificationStatus.PENDING, VerificationStatus.VERIFIED),
            )
            .select_related("user", "city")
            .prefetch_related("subjects", "classes", "boards", "availability")
            .distinct()
        )

    def match(self, queryset=None, limit=20):
        qs = queryset if queryset is not None else self.base_queryset()
        results = [self._score(t) for t in qs]
        results = [r for r in results if r.score > 0]
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def _score(self, tutor: TutorProfile) -> MatchResult:
        prefs, score, reasons = self.prefs, 0, []
        subject_ids = {s.id for s in tutor.subjects.all()}
        class_ids = {c.id for c in tutor.classes.all()}
        board_ids = {b.id for b in tutor.boards.all()}

        if prefs.subject_id:
            if prefs.subject_id in subject_ids:
                score += WEIGHTS["subject"]
                reasons.append("Teaches the subject you need")
            else:
                return MatchResult(tutor, 0, [])

        if prefs.class_level_id:
            if prefs.class_level_id in class_ids:
                score += WEIGHTS["class_level"]
                reasons.append("Experienced with your class level")
            elif class_ids:
                return MatchResult(tutor, 0, [])

        if prefs.board_id and prefs.board_id in board_ids:
            score += WEIGHTS["board"]
            reasons.append("Familiar with your board")

        if prefs.mode:
            if tutor.teaching_mode in (prefs.mode, TeachingMode.BOTH):
                score += WEIGHTS["mode"]
                reasons.append(f"Offers {dict(TeachingMode.choices).get(prefs.mode, prefs.mode).lower()} classes")
            else:
                return MatchResult(tutor, 0, [])

        if prefs.location_id and tutor.city_id:
            if tutor.city_id == prefs.location_id:
                score += WEIGHTS["location"]
                reasons.append("Based in your area")

        if prefs.latitude is not None and prefs.longitude is not None and tutor.city_id:
            loc = tutor.city
            dist = haversine_km(prefs.latitude, prefs.longitude, loc.latitude, loc.longitude)
            if dist is not None:
                radius = prefs.radius_km or tutor.teaching_radius_km or 10
                if dist <= radius:
                    score += WEIGHTS["distance"]
                    reasons.append(f"Within ~{dist:.1f} km of you")

        if prefs.budget and tutor.hourly_fee is not None:
            if float(tutor.hourly_fee) <= prefs.budget:
                score += WEIGHTS["budget"]
                reasons.append("Fits your budget")

        if prefs.min_experience and tutor.experience_years >= prefs.min_experience:
            score += WEIGHTS["experience"]
            reasons.append(f"{tutor.experience_years}+ years of experience")
        elif tutor.experience_years >= 5:
            score += WEIGHTS["experience"]
            reasons.append(f"{tutor.experience_years}+ years of experience")

        if tutor.reviews_count and float(tutor.average_rating) >= 4.0:
            score += WEIGHTS["rating"]
            reasons.append(f"Rated {tutor.average_rating}/5 by students")

        if prefs.weekday is not None:
            if any(a.weekday == prefs.weekday for a in tutor.availability.all()):
                reasons.append("Available on your preferred day")

        if tutor.is_verified:
            score += WEIGHTS["verified"]
            reasons.append("Verified by TutorSetu")

        if not reasons and tutor.is_published:
            reasons.append("Available tutor on TutorSetu")

        return MatchResult(tutor, score, reasons)
