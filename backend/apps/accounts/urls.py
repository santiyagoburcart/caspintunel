from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    ChangePasswordView,
    EmailVerifyConfirmView,
    EmailVerifyResendView,
    LegacyImportView,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
    TelegramMiniAppLoginView,
)

app_name = "accounts"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("telegram/miniapp/", TelegramMiniAppLoginView.as_view(), name="telegram-miniapp"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("password/change/", ChangePasswordView.as_view(), name="password-change"),
    path("password/reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path("password/reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("email/verify/resend/", EmailVerifyResendView.as_view(), name="email-verify-resend"),
    path("email/verify/confirm/", EmailVerifyConfirmView.as_view(), name="email-verify-confirm"),
    path("legacy/import/", LegacyImportView.as_view(), name="legacy-import"),
]
