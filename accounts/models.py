"""Custom user model with role-based access control."""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserRole(models.TextChoices):
    STUDENT = "STUDENT", "Student"
    PARENT = "PARENT", "Parent"
    TUTOR = "TUTOR", "Tutor"
    ADMIN = "ADMIN", "Admin"


class AccountStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"
    SUSPENDED = "SUSPENDED", "Suspended"
    BANNED = "BANNED", "Banned"


class UserGender(models.TextChoices):
    MALE = "MALE", "Male"
    FEMALE = "FEMALE", "Female"
    OTHER = "OTHER", "Other"
    PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY", "Prefer not to say"


PUBLIC_REGISTRATION_ROLES = (UserRole.STUDENT, UserRole.PARENT, UserRole.TUTOR)


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, role=UserRole.STUDENT, **extra):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email)
        # Admins can only be created via management commands / superuser paths.
        if role == UserRole.ADMIN and not extra.get("_allow_admin", False):
            role = UserRole.STUDENT
        extra.pop("_allow_admin", None)
        user = self.model(email=email, role=role, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra["role"] = UserRole.ADMIN
        extra["_allow_admin"] = True
        if not extra.get("is_superuser"):
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Email-authenticated user with a platform role and account status."""

    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    gender = models.CharField(
        max_length=20, choices=UserGender.choices, blank=True
    )
    role = models.CharField(
        max_length=10, choices=UserRole.choices, default=UserRole.STUDENT, db_index=True
    )
    status = models.CharField(
        max_length=10,
        choices=AccountStatus.choices,
        default=AccountStatus.ACTIVE,
        db_index=True,
    )
    email_verified = models.BooleanField(default=False)
    profile_image = models.ImageField(
        upload_to="profiles/%Y/%m/", blank=True, null=True
    )
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        indexes = [
            models.Index(fields=["role", "status"]),
        ]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    # --- Role helpers -------------------------------------------------------
    @property
    def is_student(self):
        return self.role == UserRole.STUDENT

    @property
    def is_parent(self):
        return self.role == UserRole.PARENT

    @property
    def is_tutor(self):
        return self.role == UserRole.TUTOR

    @property
    def is_platform_admin(self):
        return self.role == UserRole.ADMIN or self.is_superuser

    @property
    def is_account_blocked(self):
        return self.status != AccountStatus.ACTIVE

    def dashboard_url_name(self):
        """Namespaced URL name of the user's role dashboard."""
        if self.is_platform_admin:
            return "manage:dashboard"
        return {
            UserRole.STUDENT: "students:dashboard",
            UserRole.PARENT: "parents:dashboard",
            UserRole.TUTOR: "tutors:dashboard",
        }.get(self.role, "core:home")
