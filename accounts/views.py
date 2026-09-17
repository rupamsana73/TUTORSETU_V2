"""Authentication & account views with mandatory rate limiting."""
import logging

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView, PasswordResetConfirmView, PasswordResetView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from core.ratelimits import RATE_LIMITS
from core.utils import audit, get_client_ip

from .forms import (
    LoginForm, ParentRegistrationForm, StudentRegistrationForm, TutorRegistrationForm,
)
from .models import User, UserRole
from .services import create_profile_for_user, send_verification_email

logger = logging.getLogger("tutorsetu")


class RateLimitedLoginView(LoginView):
    form_class = LoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    @method_decorator(
        ratelimit(key="ip", rate=RATE_LIMITS["login"], method="POST", block=True)
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.get_user()
        if user.is_account_blocked:
            messages.error(self.request, "This account is restricted. Contact support.")
            return redirect("accounts:login")
        user.last_login_ip = get_client_ip(self.request)
        user.save(update_fields=["last_login_ip"])
        audit(self.request, "LOGIN", target=user.email, user=user)
        return super().form_valid(form)


@require_POST
def logout_view(request):
    """POST-only logout (prevents CSRF logout attacks)."""
    if request.user.is_authenticated:
        audit(request, "LOGOUT", target=request.user.email)
    logout(request)
    messages.info(request, "You have been signed out.")
    return redirect("core:home")


@login_required
def post_login_redirect(request):
    return redirect(request.user.dashboard_url_name())


REGISTRATION_FORMS = {
    "student": (StudentRegistrationForm, "accounts/register_student.html"),
    "parent": (ParentRegistrationForm, "accounts/register_parent.html"),
    "tutor": (TutorRegistrationForm, "accounts/register_tutor.html"),
}


def register_choice(request):
    return render(request, "accounts/register_choice.html")


@ratelimit(key="ip", rate=RATE_LIMITS["register"], method="POST", block=True)
def register(request, role):
    """Role-scoped registration. ADMIN registration is impossible here."""
    if role not in REGISTRATION_FORMS:
        return redirect("accounts:register")
    form_class, template = REGISTRATION_FORMS[role]
    if request.user.is_authenticated:
        return redirect(request.user.dashboard_url_name())
    if request.method == "POST":
        form = form_class(request.POST)
        if form.is_valid():
            user = form.save()
            create_profile_for_user(user, form.cleaned_data)
            audit(request, "REGISTER", target=user.email, user=user)
            email_sent = send_verification_email(request, user)
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            if email_sent:
                messages.success(
                    request,
                    "Welcome to TutorSetu! Please verify your email — a link was sent to your inbox.",
                )
            else:
                messages.error(
                    request,
                    "Your account was created but we could not send the verification email. Please request a fresh one or contact support.",
                )
            return redirect(user.dashboard_url_name())
    else:
        form = form_class()
    return render(request, template, {"form": form})


@ratelimit(key="user_or_ip", rate=RATE_LIMITS["verify_email"], method="POST", block=True)
@login_required
def resend_verification(request):
    if request.user.email_verified:
        messages.info(request, "Your email is already verified.")
    else:
        send_verification_email(request, request.user)
        messages.success(request, "Verification email sent. Please check your inbox.")
    return redirect(request.user.dashboard_url_name())


def verify_email(request, uidb64, token):
    from django.utils.encoding import force_str
    from django.utils.http import urlsafe_base64_decode

    from .tokens import email_verification_token

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    if user and email_verification_token.check_token(user, token):
        if not user.email_verified:
            user.email_verified = True
            user.save(update_fields=["email_verified"])
            audit(request, "EMAIL_VERIFIED", target=user.email, user=user)
        messages.success(request, "Your email has been verified.")
    else:
        messages.error(request, "This verification link is invalid or has expired.")
    return redirect("accounts:login")


class RateLimitedPasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/emails/password_reset_email.html"
    subject_template_name = "accounts/emails/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")

    @method_decorator(
        ratelimit(key="ip", rate=RATE_LIMITS["password_reset"], method="POST", block=True)
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        # Response never reveals whether the email exists.
        messages.success(
            self.request,
            "If an account exists for that email, reset instructions have been sent.",
        )
        return super().form_valid(form)


class RateLimitedPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:login")

    def form_valid(self, form):
        messages.success(self.request, "Your password has been reset. Please log in.")
        return super().form_valid(form)


@login_required
def change_password(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            audit(request, "PASSWORD_CHANGED", target=user.email)
            messages.success(request, "Your password was changed.")
            return redirect("accounts:settings")
    else:
        form = PasswordChangeForm(request.user)
    return render(request, "accounts/change_password.html", {"form": form})


@login_required
def account_settings(request):
    return render(request, "accounts/settings.html")


@require_POST
@login_required
def deactivate_account(request):
    user = request.user
    if not user.check_password(request.POST.get("password", "")):
        messages.error(request, "Password confirmation failed. Account unchanged.")
        return redirect("accounts:settings")
    user.is_active = False
    user.save(update_fields=["is_active"])
    audit(request, "ACCOUNT_DEACTIVATED", target=user.email)
    logout(request)
    messages.info(request, "Your account has been deactivated.")
    return redirect("core:home")
