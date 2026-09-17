from django import forms

from .models import Report, ReportCategory


class ReportForm(forms.Form):
    category = forms.ChoiceField(
        choices=ReportCategory.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    description = forms.CharField(
        max_length=2000,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )
