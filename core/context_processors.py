"""Site-wide template context."""
from django.conf import settings


def site_context(request):
    return {
        "SITE_NAME": getattr(settings, "SITE_NAME", "TutorSetu"),
        "SITE_TAGLINE": getattr(settings, "SITE_TAGLINE", ""),
        "CURRENT_YEAR": __import__("datetime").date.today().year,
    }
