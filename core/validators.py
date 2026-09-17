"""Upload security validators (used by models and forms)."""
import os
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_DOC_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
ALLOWED_DOC_MIMES = {"application/pdf", "image/jpeg", "image/png"}


def _validate_file(upload, allowed_exts, allowed_mimes, max_mb, kind):
    ext = Path(upload.name or "").suffix.lower()
    if ext not in allowed_exts:
        raise ValidationError(f"Unsupported {kind} file type '{ext}'.")
    content_type = getattr(upload, "content_type", "") or ""
    if content_type and content_type not in allowed_mimes:
        raise ValidationError(f"Unsupported {kind} content type.")
    max_bytes = max_mb * 1024 * 1024
    if upload.size > max_bytes:
        raise ValidationError(f"{kind.capitalize()} file too large (max {max_mb} MB).")
    # Basic path traversal / weird filename guard
    name = os.path.basename(upload.name or "")
    if name != upload.name or ".." in name:
        raise ValidationError("Invalid file name.")


def validate_image(upload):
    max_mb = getattr(settings, "MAX_UPLOAD_IMAGE_MB", 5)
    _validate_file(upload, ALLOWED_IMAGE_EXTENSIONS, ALLOWED_IMAGE_MIMES, max_mb, "image")
    # Verify it is a real image by decoding the header.
    try:
        from PIL import Image

        pos = upload.tell() if hasattr(upload, "tell") else None
        img = Image.open(upload)
        img.verify()
        if pos is not None and hasattr(upload, "seek"):
            upload.seek(pos)
    except Exception as exc:  # noqa: BLE001
        raise ValidationError("Uploaded file is not a valid image.") from exc


def validate_document(upload):
    max_mb = getattr(settings, "MAX_UPLOAD_DOC_MB", 8)
    _validate_file(upload, ALLOWED_DOC_EXTENSIONS, ALLOWED_DOC_MIMES, max_mb, "document")
