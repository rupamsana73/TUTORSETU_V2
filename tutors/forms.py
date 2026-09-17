"""Tutor onboarding & profile forms (multi-step, server-validated)."""
from django import forms
from django.core.exceptions import ValidationError

from accounts.models import UserGender
from core.models import Board, ClassLevel, Subject
from core.validators import validate_image
from locations.models import Location

from .models import TeachingMode, TutorAvailability, TutorProfile, Weekday


class BootstrapFormMixin:
    def _bootstrap(self):
        for name, f in self.fields.items():
            css = "form-check-input" if isinstance(f.widget, forms.CheckboxInput) else (
                "form-select" if isinstance(f.widget, (forms.Select, forms.SelectMultiple)) else "form-control"
            )
            f.widget.attrs.setdefault("class", css)


class Step1BasicForm(BootstrapFormMixin, forms.ModelForm):
    full_name = forms.CharField(max_length=150, widget=forms.TextInput())
    email = forms.EmailField(disabled=True, required=False)
    phone = forms.CharField(max_length=20, required=False)
    gender = forms.ChoiceField(
        choices=[("", "Select")] + list(UserGender.choices), required=False
    )
    profile_image = forms.ImageField(required=False, validators=[validate_image])

    class Meta:
        model = TutorProfile
        fields = ("tagline", "about")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["full_name"].initial = self.user.full_name
        self.fields["email"].initial = self.user.email
        self.fields["phone"].initial = self.user.phone
        self.fields["gender"].initial = self.user.gender
        self.fields["profile_image"].initial = self.user.profile_image
        self._bootstrap()

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = self.user
        user.full_name = self.cleaned_data["full_name"]
        user.phone = self.cleaned_data.get("phone", "")
        user.gender = self.cleaned_data.get("gender", "")
        if self.cleaned_data.get("profile_image"):
            user.profile_image = self.cleaned_data["profile_image"]
        if commit:
            user.save()
            profile.save()
        return profile


class Step2EducationForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = TutorProfile
        fields = ("highest_qualification", "degree", "institution", "university", "passing_year")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrap()


class Step3TeachingForm(BootstrapFormMixin, forms.ModelForm):
    subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.filter(is_active=True, is_deleted=False),
        widget=forms.CheckboxSelectMultiple, required=True,
    )
    classes = forms.ModelMultipleChoiceField(
        queryset=ClassLevel.objects.filter(is_active=True, is_deleted=False),
        widget=forms.CheckboxSelectMultiple, required=True,
    )
    boards = forms.ModelMultipleChoiceField(
        queryset=Board.objects.filter(is_active=True, is_deleted=False),
        widget=forms.CheckboxSelectMultiple, required=False,
    )

    class Meta:
        model = TutorProfile
        fields = ("experience_years", "teaching_mode", "subjects", "classes", "boards")

    def save(self, commit=True):
        profile = super().save(commit=False)
        if commit:
            profile.save()
            profile.subjects.set(self.cleaned_data["subjects"])
            profile.classes.set(self.cleaned_data["classes"])
            profile.boards.set(self.cleaned_data["boards"])
        return profile


class Step4LocationForm(BootstrapFormMixin, forms.ModelForm):
    teaching_areas = forms.ModelMultipleChoiceField(
        queryset=Location.objects.filter(is_active=True, is_deleted=False),
        widget=forms.CheckboxSelectMultiple, required=False,
        label="Areas you cover for home tuition",
    )

    class Meta:
        model = TutorProfile
        fields = ("city", "pincode", "teaching_radius_km")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["teaching_areas"].initial = self.instance.teaching_areas.values_list(
                "location_id", flat=True
            )
        self._bootstrap()

    def clean_pincode(self):
        pin = (self.cleaned_data.get("pincode") or "").strip()
        if pin and not (pin.isdigit() and len(pin) == 6):
            raise ValidationError("Enter a valid 6-digit pincode.")
        return pin

    def save(self, commit=True):
        profile = super().save(commit=False)
        if commit:
            profile.save()
            from locations.models import TutorTeachingArea

            wanted = set(self.cleaned_data["teaching_areas"].values_list("id", flat=True))
            existing = set(profile.teaching_areas.values_list("location_id", flat=True))
            for loc_id in wanted - existing:
                TutorTeachingArea.objects.get_or_create(tutor=profile, location_id=loc_id)
            profile.teaching_areas.filter(location_id__in=existing - wanted).delete()
        return profile


class Step5FeesForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = TutorProfile
        fields = ("hourly_fee", "monthly_fee", "fee_negotiable")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrap()

    def clean(self):
        data = super().clean()
        if not data.get("hourly_fee") and not data.get("monthly_fee"):
            raise ValidationError("Set at least an hourly or a monthly fee.")
        return data


class AvailabilitySlotForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = TutorAvailability
        fields = ("weekday", "start_time", "end_time")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["start_time"].widget = forms.TimeInput(attrs={"type": "time", "class": "form-control"})
        self.fields["end_time"].widget = forms.TimeInput(attrs={"type": "time", "class": "form-control"})
        self.fields["weekday"].widget = forms.Select(
            choices=Weekday.choices, attrs={"class": "form-select"}
        )


class TutorExtrasForm(BootstrapFormMixin, forms.ModelForm):
    """Methodology, languages, achievements, certifications."""

    class Meta:
        model = TutorProfile
        fields = ("teaching_methodology", "languages", "achievements", "certifications")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrap()


class TutorSearchForm(forms.Form):
    """Public tutor search form (GET)."""

    q = forms.CharField(required=False, label="Tutor name or keyword")
    subject = forms.IntegerField(required=False)
    class_level = forms.IntegerField(required=False)
    board = forms.IntegerField(required=False)
    location = forms.IntegerField(required=False)
    mode = forms.ChoiceField(required=False, choices=[("", "Any mode")] + list(TeachingMode.choices))
    min_experience = forms.IntegerField(required=False, min_value=0)
    fee_min = forms.IntegerField(required=False, min_value=0)
    fee_max = forms.IntegerField(required=False, min_value=0)
    min_rating = forms.DecimalField(required=False, min_value=0, max_value=5)
    verified_only = forms.BooleanField(required=False)
    weekday = forms.TypedChoiceField(
        required=False, coerce=int, empty_value=None,
        choices=[("", "Any day")] + list(Weekday.choices),
    )
    sort = forms.ChoiceField(
        required=False,
        choices=[
            ("relevance", "Relevance"),
            ("rating", "Rating"),
            ("experience", "Experience"),
            ("fee_low", "Fee: low to high"),
            ("fee_high", "Fee: high to low"),
            ("newest", "Newest"),
        ],
    )
    budget = forms.IntegerField(required=False, min_value=0)
