"""Marketplace forms: enquiries, tutor requests, applications."""
from django import forms

from core.models import Board, ClassLevel, Subject
from locations.models import Location
from tutors.models import TeachingMode, TutorProfile, Weekday

from .models import Enquiry, TutorApplication, TutorRequest


def _bootstrap(form):
    for f in form.fields.values():
        if isinstance(f.widget, forms.CheckboxSelectMultiple):
            continue
        css = "form-select" if isinstance(f.widget, forms.Select) else (
            "form-check-input" if isinstance(f.widget, forms.CheckboxInput) else "form-control"
        )
        f.widget.attrs.setdefault("class", css)


class EnquiryForm(forms.ModelForm):
    preferred_days = forms.MultipleChoiceField(
        choices=Weekday.choices, widget=forms.CheckboxSelectMultiple, required=False
    )

    class Meta:
        model = Enquiry
        fields = (
            "child", "subject", "class_level", "message", "teaching_mode",
            "preferred_days", "preferred_time", "budget", "location",
        )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subject"].queryset = Subject.objects.filter(is_active=True, is_deleted=False)
        self.fields["class_level"].queryset = ClassLevel.objects.filter(is_active=True, is_deleted=False)
        self.fields["location"].queryset = Location.objects.filter(is_active=True, is_deleted=False)
        self.fields["subject"].required = True
        self.fields["message"].required = True
        self.fields["message"].widget.attrs.update({"rows": 4})
        # Parents may pick one of their own children (IDOR-safe queryset)
        if user is not None and getattr(user, "is_parent", False):
            self.fields["child"].queryset = user.parent_profile.children.all()
            self.fields["child"].widget.attrs.pop("class", None)
            self.fields["child"].widget.attrs["class"] = "form-select"
        else:
            self.fields.pop("child", None)
        _bootstrap(self)

    def clean_preferred_days(self):
        return ",".join(self.cleaned_data.get("preferred_days") or [])


class TutorRequestForm(forms.ModelForm):
    class Meta:
        model = TutorRequest
        fields = (
            "title", "description", "child", "subject", "class_level", "board",
            "location", "mode", "budget", "preferred_schedule", "start_date",
        )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        for field, model in (
            ("subject", Subject), ("class_level", ClassLevel),
            ("board", Board), ("location", Location),
        ):
            self.fields[field].queryset = model.objects.filter(is_active=True, is_deleted=False)
        self.fields["start_date"].widget = forms.DateInput(attrs={"type": "date", "class": "form-control"})
        if user is not None and getattr(user, "is_parent", False):
            self.fields["child"].queryset = user.parent_profile.children.all()
        else:
            self.fields.pop("child", None)
        _bootstrap(self)


class TutorApplicationForm(forms.ModelForm):
    class Meta:
        model = TutorApplication
        fields = ("message", "proposed_fee")
        widgets = {"message": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self)
