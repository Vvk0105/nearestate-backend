from django.urls import path
from .views import SendEmailOTPView, VerifyEmailOTPView, GoogleLoginView, SelectRoleView, CurrentUserView

urlpatterns = [
    path("email-otp/send/", SendEmailOTPView.as_view()),
    path("email-otp/verify/", VerifyEmailOTPView.as_view()),

    path("google/login/", GoogleLoginView.as_view()),
    path("select-role/", SelectRoleView.as_view()),
    path("me/", CurrentUserView.as_view()),
]
