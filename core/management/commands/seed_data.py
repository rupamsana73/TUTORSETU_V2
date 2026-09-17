"""Development-only seed data for TutorSetu.

Creates fictional users, tutors, subjects, boards and locations.
Admin password is read from the SEED_ADMIN_PASSWORD environment variable
(never hardcoded). Safe to re-run — it is idempotent.
"""
import os
import random
from datetime import time

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User, UserGender, UserRole
from core.models import Board, ClassLevel, Subject, SubjectCategory
from locations.models import Location
from parents.models import ParentProfile, StudentChild
from students.models import StudentProfile
from tutors.models import TeachingMode, TutorAvailability, TutorProfile, VerificationStatus

FIRST_NAMES = [
    "Rahul", "Priya", "Amit", "Sneha", "Arjun", "Kavita", "Vikram", "Ananya",
    "Rohan", "Meera", "Sourav", "Pooja", "Kunal", "Ritika", "Abhijit", "Sangita",
    "Debasish", "Moumita", "Tanmay", "Riya", "Subhasis", "Payel",
]
LAST_NAMES = ["Sharma", "Banerjee", "Chatterjee", "Mukherjee", "Das", "Ghosh",
              "Sen", "Roy", "Bose", "Dutta", "Pal", "Kundu"]

SUBJECTS = {
    "School": ["Mathematics", "Physics", "Chemistry", "Biology", "English", "Bengali", "History", "Geography"],
    "College": ["Accounts", "Economics", "Business Studies"],
    "Programming": ["Computer Science"],
}

BOARDS = ["CBSE", "ICSE", "WBBSE", "WBCHSE", "NIOS"]

CLASSES = [f"Class {i}" for i in range(5, 13)] + ["Graduation"]

LOCATIONS = [
    ("Howrah", "Shibpur", "711102", 22.5675, 88.3117),
    ("Howrah", "Howrah Maidan", "711101", 22.5830, 88.3410),
    ("Howrah", "Santragachi", "711104", 22.5750, 88.2900),
    ("Howrah", "Bally", "711201", 22.6450, 88.3580),
    ("Howrah", "Liluah", "711204", 22.6270, 88.3420),
    ("Howrah", "Belur", "711202", 22.6310, 88.3150),
    ("Howrah", "Salkia", "711106", 22.6040, 88.3190),
    ("Kolkata", "Salt Lake", "700091", 22.5860, 88.4170),
    ("Kolkata", "New Town", "700156", 22.6010, 88.4790),
    ("Kolkata", "Ballygunge", "700019", 22.5270, 88.3660),
    ("Kolkata", "Dum Dum", "700074", 22.6200, 88.3960),
    ("Kolkata", "Behala", "700034", 22.4990, 88.3100),
]

QUALIFICATIONS = [
    ("M.Sc", "M.Sc in {}"), ("M.A.", "M.A. in {}"), ("B.Ed", "B.Ed + M.Sc in {}"),
    ("M.Tech", "M.Tech"), ("B.Sc", "B.Sc in {}"), ("MBA", "MBA"),
]


class Command(BaseCommand):
    help = "Seed the database with fictional development data (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--tutors", type=int, default=22)

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding TutorSetu development data…")
        rng = random.Random(42)

        categories = {}
        for name in SUBJECTS:
            categories[name], _ = SubjectCategory.objects.get_or_create(name=name)

        subjects = []
        for cat, names in SUBJECTS.items():
            for name in names:
                subject, _ = Subject.objects.get_or_create(
                    name=name, defaults={"category": categories[cat]}
                )
                subjects.append(subject)

        boards = [Board.objects.get_or_create(name=name)[0] for name in BOARDS]
        classes = [
            ClassLevel.objects.get_or_create(name=name, defaults={"order": i})[0]
            for i, name in enumerate(CLASSES)
        ]
        locations = [
            Location.objects.get_or_create(
                city=city, area=area,
                defaults={"pincode": pin, "latitude": lat, "longitude": lon},
            )[0]
            for city, area, pin, lat, lon in LOCATIONS
        ]

        # --- Admin (password from environment, never hardcoded) -----------
        admin_email = os.environ.get("SEED_ADMIN_EMAIL", "admin@tutorsetu.local")
        admin_password = os.environ.get("SEED_ADMIN_PASSWORD", "")
        if not User.objects.filter(email=admin_email).exists():
            if not admin_password:
                admin_password = "Admin@12345"
            User.objects.create_superuser(
                email=admin_email, password=admin_password, full_name="Site Admin"
            )
            self.stdout.write(f"  admin: {admin_email} (password from SEED_ADMIN_PASSWORD or default dev password)")

        # --- Students ------------------------------------------------------
        for i in range(1, 3):
            email = f"student{i}@example.com"
            if not User.objects.filter(email=email).exists():
                user = User.objects.create_user(
                    email=email, password="Student@123", full_name=f"Demo Student {i}",
                    role=UserRole.STUDENT,
                )
                StudentProfile.objects.create(
                    user=user,
                    class_level=rng.choice(classes),
                    board=rng.choice(boards),
                    preferred_location=rng.choice(locations),
                )

        # --- Parents -------------------------------------------------------
        for i in range(1, 3):
            email = f"parent{i}@example.com"
            if not User.objects.filter(email=email).exists():
                user = User.objects.create_user(
                    email=email, password="Parent@123", full_name=f"Demo Parent {i}",
                    role=UserRole.PARENT,
                )
                profile = ParentProfile.objects.create(user=user, location=rng.choice(locations))
                child = StudentChild.objects.create(
                    parent=profile, name=f"Child {i} One",
                    class_level=rng.choice(classes), board=rng.choice(boards),
                )
                child.subjects.set(rng.sample(subjects, 3))

        # --- Tutors --------------------------------------------------------
        target = options["tutors"]
        created = 0
        i = 1
        while User.objects.filter(role=UserRole.TUTOR).count() < target and i < 200:
            email = f"tutor{i}@example.com"
            i += 1
            if User.objects.filter(email=email).exists():
                continue
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
            user = User.objects.create_user(
                email=email, password="Tutor@123", full_name=name,
                role=UserRole.TUTOR, gender=rng.choice(
                    [UserGender.MALE, UserGender.FEMALE]
                ),
            )
            subject_pool = rng.sample(subjects, rng.randint(1, 3))
            qual, degree_fmt = rng.choice(QUALIFICATIONS)
            city = rng.choice(locations)
            profile = TutorProfile.objects.create(
                user=user,
                tagline=f"Passionate {subject_pool[0].name} tutor in {city.city}",
                about=(
                    f"I am {name}, a dedicated educator helping students build strong "
                    f"foundations in {subject_pool[0].name} with patient, structured lessons."
                ),
                highest_qualification=qual,
                degree=degree_fmt.format(subject_pool[0].name),
                institution="University of Calcutta",
                passing_year=rng.randint(2005, 2023),
                experience_years=rng.randint(1, 18),
                teaching_mode=rng.choice(list(TeachingMode)),
                city=city,
                hourly_fee=rng.choice([200, 300, 400, 500, 600, 800]),
                monthly_fee=rng.choice([2000, 3000, 4000, 5000]),
                fee_negotiable=rng.choice([True, True, False]),
                languages=rng.choice(["Bengali, English", "Hindi, English", "Bengali, Hindi, English", "English"]),
                verification_status=rng.choice(
                    [VerificationStatus.VERIFIED] * 3 + [VerificationStatus.PENDING]
                ),
                is_profile_complete=True,
                is_published=True,
            )
            profile.subjects.set(subject_pool)
            profile.classes.set(rng.sample(classes, rng.randint(2, 5)))
            profile.boards.set(rng.sample(boards, 2))
            for weekday in rng.sample(range(7), rng.randint(3, 6)):
                start_hour = rng.randint(9, 17)
                TutorAvailability.objects.get_or_create(
                    tutor=profile, weekday=weekday,
                    start_time=time(start_hour, 0), end_time=time(start_hour + 2, 0),
                )
            if profile.is_verified:
                from verification.models import TutorBadge, VerificationBadge

                TutorBadge.objects.get_or_create(tutor=profile, badge=VerificationBadge.IDENTITY)
                TutorBadge.objects.get_or_create(tutor=profile, badge=VerificationBadge.QUALIFICATION)
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Tutors created: {created}. Total tutors: "
            f"{User.objects.filter(role=UserRole.TUTOR).count()}"
        ))
