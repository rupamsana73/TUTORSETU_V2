"""Shared helpers."""
from core.models import AuditLog


def get_client_ip(request):
    """Best-effort client IP (respects a single proxy hop)."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def audit(request, action, target="", metadata=None, user=None):
    """Write an AuditLog entry. Never raises."""
    try:
        actor = user if user is not None else (
            request.user if getattr(request, "user", None) and request.user.is_authenticated else None
        )
        AuditLog.objects.create(
            user=actor,
            action=action,
            target=str(target)[:255],
            ip_address=get_client_ip(request) if request else None,
            metadata=metadata or {},
        )
    except Exception:  # noqa: BLE001 - auditing must never break requests
        pass


def star_range(rating):
    """Return (filled, empty) star counts for display."""
    full = int(round(rating or 0))
    full = max(0, min(5, full))
    return range(full), range(5 - full)
