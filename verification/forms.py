"""Verification submission forms."""
from django import forms

from core.validators import validate_document, validate_image

from .models import DocumentType


class VerificationUploadForm(forms.Form):
    id_document = forms.FileField(validators=[validate_document], label="ID document")
    qualification_certificate = forms.FileField(
        validators=[validate_document], label="Qualification certificate"
    )
    experience_certificate = forms.FileField(
        validators=[validate_document], required=False, label="Experience certificate (optional)"
    )
    profile_photo = forms.FileField(
        validators=[validate_image], required=False, label="Profile photo (optional)"
    )
