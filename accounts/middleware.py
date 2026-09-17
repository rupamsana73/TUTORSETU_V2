"""Enforce account status: suspended/banned users are signed out."""
from django.contrib.auth import logout
from django.contrib import messages


class AccountStatusMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.is_account_blocked:
            logout(request)
            messages.error(
                request,
                "Your account access has been restricted. Contact support for help.",
            )
        return self.get_response(request)
