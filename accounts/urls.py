from django.urls import path
from .views import SendEmailOTPView, VerifyEmailOTPView

urlpatterns = [
    path("email-otp/send/", SendEmailOTPView.as_view()),
    path("email-otp/verify/", VerifyEmailOTPView.as_view()),
]
