from django.urls import path
from .views import SendEmailOTPView, VerifyEmailOTPView, RefreshTokenView, GoogleLoginView, SelectRoleView, CurrentUserView, UpdateProfileView, SwitchRoleView, AdminLoginView

urlpatterns = [
    path("admin/login/", AdminLoginView.as_view()),
    path("email-otp/send/", SendEmailOTPView.as_view()),
    path("email-otp/verify/", VerifyEmailOTPView.as_view()),
    path("token/refresh/", RefreshTokenView.as_view()),

    path("google/login/", GoogleLoginView.as_view()),
    path("select-role/", SelectRoleView.as_view()),
    path("me/", CurrentUserView.as_view()),
    path("profile/update/", UpdateProfileView.as_view()),
    path("switch-role/", SwitchRoleView.as_view()),

]
