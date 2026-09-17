from django import forms

from .models import Review


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ("rating", "title", "text")
        widgets = {
            "rating": forms.Select(choices=[(i, "★" * i) for i in range(1, 6)], attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "text": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }
