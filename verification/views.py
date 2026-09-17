"""Tutor-side verification submission (admin queue lives in core.manage)."""
from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django_ratelimit.decorators import ratelimit

from accounts.decorators import tutor_required
from core.ratelimits import RATE_LIMITS
from core.utils import audit
from tutors.models import VerificationStatus

from .forms import VerificationUploadForm
from .models import DocumentType, TutorVerification, VerificationDocument


@tutor_required
def verification_status_view(request):
    tutor = request.user.tutor_profile
    latest = tutor.verifications.first()
    return render(
        request, "verification/status.html",
        {"tutor": tutor, "latest": latest,
         "documents": latest.documents.all() if latest else []},
    )


@ratelimit(key="user", rate=RATE_LIMITS["upload"], method="POST", block=True)
@tutor_required
def submit_verification(request):
    tutor = request.user.tutor_profile
    if tutor.verification_status == VerificationStatus.VERIFIED:
        messages.info(request, "Your profile is already verified.")
        return redirect("verification:status")
    if request.method == "POST":
        form = VerificationUploadForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                verification = TutorVerification.objects.create(tutor=tutor)
                mapping = (
                    (DocumentType.ID_DOCUMENT, "id_document"),
                    (DocumentType.QUALIFICATION, "qualification_certificate"),
                    (DocumentType.EXPERIENCE, "experience_certificate"),
                    (DocumentType.PHOTO, "profile_photo"),
                )
                for doc_type, field in mapping:
                    upload = form.cleaned_data.get(field)
                    if upload:
                        VerificationDocument.objects.create(
                            verification=verification, document_type=doc_type, file=upload
                        )
                tutor.verification_status = VerificationStatus.PENDING
                tutor.save(update_fields=["verification_status", "updated_at"])
            audit(request, "VERIFICATION_SUBMITTED", target=f"verification:{verification.pk}")
            messages.success(request, "Your documents have been submitted for review.")
            return redirect("verification:status")
    else:
        form = VerificationUploadForm()
    return render(request, "verification/submit.html", {"form": form})
