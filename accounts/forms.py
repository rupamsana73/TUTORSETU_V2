"""Authentication & registration forms (server-validated)."""
from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, SetPasswordForm
from django.core.exceptions import ValidationError

from core.models import Board, ClassLevel
from locations.models import Location
from tutors.models import TeachingMode
from .models import PUBLIC_REGISTRATION_ROLES, User, UserGender, UserRole


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"class": "form-control", "autofocus": True, "placeholder": "you@example.com"}),
    )
    password = forms.CharField(
        label="Password", strip=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Your password"}),
    )

    error_messages = {
        "invalid_login": "Invalid email or password.",
        "inactive": "This account is inactive.",
    }


class BaseRegistrationForm(forms.ModelForm):
    """Common registration fields. ADMIN can never be self-assigned."""

    password1 = forms.CharField(
        label="Password", strip=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "At least 8 characters"}),
        min_length=8,
    )
    password2 = forms.CharField(
        label="Confirm password", strip=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Repeat password"}),
    )
    role = UserRole.STUDENT  # overridden per form

    class Meta:
        model = User
        fields = ("full_name", "email", "phone")
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        # Generic error only — do not leak whether an account exists.
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("Unable to register with this email address.")
        return email

    def clean(self):
        data = super().clean()
        if data.get("password1") != data.get("password2"):
            self.add_error("password2", "Passwords do not match.")
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = self.role if self.role in PUBLIC_REGISTRATION_ROLES else UserRole.STUDENT
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class StudentRegistrationForm(BaseRegistrationForm):
    role = UserRole.STUDENT

    class_level = forms.ModelChoiceField(
        queryset=ClassLevel.objects.filter(is_active=True, is_deleted=False),
        widget=forms.Select(attrs={"class": "form-select"}), label="Class",
    )
    board = forms.ModelChoiceField(
        queryset=Board.objects.filter(is_active=True, is_deleted=False),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    preferred_location = forms.ModelChoiceField(
        queryset=Location.objects.filter(is_active=True, is_deleted=False),
        widget=forms.Select(attrs={"class": "form-select"}), label="Preferred Location",
    )


class ParentRegistrationForm(BaseRegistrationForm):
    role = UserRole.PARENT

    location = forms.ModelChoiceField(
        queryset=Location.objects.filter(is_active=True, is_deleted=False),
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class TutorRegistrationForm(BaseRegistrationForm):
    role = UserRole.TUTOR

    gender = forms.ChoiceField(
        choices=UserGender.choices, widget=forms.Select(attrs={"class": "form-select"})
    )
    city = forms.ModelChoiceField(
        queryset=Location.objects.filter(is_active=True, is_deleted=False),
        widget=forms.Select(attrs={"class": "form-select"}), label="City",
    )
    teaching_mode = forms.ChoiceField(
        choices=TeachingMode.choices, widget=forms.Select(attrs={"class": "form-select"})
    )


class EmailChangeForm(forms.Form):
    pass  # Reserved for future use.
