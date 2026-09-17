"""Parent forms: child management."""
from django import forms

from core.models import Board, ClassLevel, Subject

from .models import StudentChild


class ChildForm(forms.ModelForm):
    subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.filter(is_active=True, is_deleted=False),
        widget=forms.CheckboxSelectMultiple, required=False,
    )

    class Meta:
        model = StudentChild
        fields = ("name", "class_level", "school", "board", "subjects", "learning_requirements")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "class_level": forms.Select(attrs={"class": "form-select"}),
            "school": forms.TextInput(attrs={"class": "form-control"}),
            "board": forms.Select(attrs={"class": "form-select"}),
            "learning_requirements": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }
