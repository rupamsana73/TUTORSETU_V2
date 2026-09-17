"""Central, configurable rate limits (no hardcoded limits scattered in views).

Override any value via environment variables, e.g. RATE_LIMIT_LOGIN=8/15m.
Django-ratelimit rate format: "5/m", "5/15m", "5/h".
"""
import os

RATE_LIMITS = {
    "login": os.environ.get("RATE_LIMIT_LOGIN", "5/15m"),
    "register": os.environ.get("RATE_LIMIT_REGISTER", "5/h"),
    "password_reset": os.environ.get("RATE_LIMIT_PASSWORD_RESET", "5/h"),
    "verify_email": os.environ.get("RATE_LIMIT_VERIFY_EMAIL", "5/h"),
    "enquiry": os.environ.get("RATE_LIMIT_ENQUIRY", "10/h"),
    "message": os.environ.get("RATE_LIMIT_MESSAGE", "30/h"),
    "review": os.environ.get("RATE_LIMIT_REVIEW", "10/h"),
    "tutor_application": os.environ.get("RATE_LIMIT_APPLICATION", "20/h"),
    "tutor_request": os.environ.get("RATE_LIMIT_TUTOR_REQUEST", "10/h"),
    "report": os.environ.get("RATE_LIMIT_REPORT", "10/h"),
    "upload": os.environ.get("RATE_LIMIT_UPLOAD", "20/h"),
    "save_tutor": os.environ.get("RATE_LIMIT_SAVE_TUTOR", "60/h"),
}
