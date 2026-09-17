from django.contrib.auth.views import PasswordResetDoneView
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.RateLimitedLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("post-login/", views.post_login_redirect, name="post_login"),
    path("register/", views.register_choice, name="register"),
    path("register/<str:role>/", views.register, name="register_role"),
    path("forgot-password/", views.RateLimitedPasswordResetView.as_view(), name="password_reset"),
    path(
        "forgot-password/sent/",
        PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "reset-password/<uidb64>/<token>/",
        views.RateLimitedPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("verify-email/<uidb64>/<token>/", views.verify_email, name="verify_email"),
    path("verify-email/resend/", views.resend_verification, name="resend_verification"),
    path("settings/", views.account_settings, name="settings"),
    path("settings/change-password/", views.change_password, name="change_password"),
    path("settings/deactivate/", views.deactivate_account, name="deactivate"),
]
