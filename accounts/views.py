from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.utils import timezone
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from rest_framework_simplejwt.tokens import RefreshToken

from .models import EmailOTP, User
from .utils import generate_otp
from .tasks import send_otp_email_task  # Celery async task — never blocks worker

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth import authenticate


class AdminLoginView(APIView):
    permission_classes = []

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response(
                {"error": "Email and password are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate email format
        try:
            validate_email(email)
        except ValidationError:
            return Response(
                {"error": "Please enter a valid email address"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = authenticate(
            request,
            username=email,
            password=password
        )

        if not user:
            return Response(
                {"error": "Invalid email or password"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if "ADMIN" not in user.roles:
            return Response(
                {"error": "Access denied. Admin role required"},
                status=status.HTTP_403_FORBIDDEN
            )

        user.active_role = "ADMIN"
        user.save()

        refresh = RefreshToken.for_user(user)

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "role": "ADMIN"
        })


class SendEmailOTPView(APIView):
    permission_classes = []

    def post(self, request):
        email = request.data.get("email")

        if not email:
            return Response(
                {"error": "Email is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate email format
        try:
            validate_email(email)
        except ValidationError:
            return Response(
                {"error": "Please enter a valid email address"},
                status=status.HTTP_400_BAD_REQUEST
            )
        if email == "playstore@nearestate.com":
            return Response({"message": "OTP sent successfully"})

        otp = generate_otp()

        EmailOTP.objects.update_or_create(
            email=email,
            defaults={
                "otp": otp,
                "is_verified": False,
                "created_at": timezone.now()
            }
        )

        # ✅ CRITICAL FIX: Use Celery — never call send_mail() directly in a request
        # handler. Synchronous SMTP hangs the gunicorn worker until the email server
        # responds, which can take minutes and permanently blocks all workers.
        send_otp_email_task.delay(email, otp)

        return Response({"message": "OTP sent successfully"})


class RefreshTokenView(APIView):
    permission_classes = []

    def post(self, request):
        refresh_token = request.data.get("refresh")

        if not refresh_token:
            return Response(
                {"error": "Refresh token is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            refresh = RefreshToken(refresh_token)
            access_token = str(refresh.access_token)
            
            return Response({
                "access": access_token,
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"error": "Invalid or expired refresh token", "detail": str(e)},
                status=status.HTTP_401_UNAUTHORIZED
            )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            
            if not refresh_token:
                return Response(
                    {"error": "Refresh token is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                token = RefreshToken(refresh_token)
                # ✅ FIX: token_blacklist must be in INSTALLED_APPS for this to work.
                # It is now added to settings.py. This blacklists the token properly.
                token.blacklist()
            except Exception as e:
                # Still return success — token will expire naturally via ACCESS_TOKEN_LIFETIME
                print(f"Token blacklist error (non-fatal): {e}")
            
            return Response(
                {"message": "Successfully logged out"},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": "Logout failed", "detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class VerifyEmailOTPView(APIView):
    permission_classes = []

    def post(self, request):
        email = request.data.get("email")
        otp = request.data.get("otp")

        if not email or not otp:
            return Response(
                {"error": "Email and OTP are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate OTP format (should be 6 digits)
        if not otp.isdigit() or len(otp) != 6:
            return Response(
                {"error": "OTP must be a 6-digit number"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if email == "playstore@nearestate.com" and otp == "123456":
            # Bypass OTP check for Play Store review
            pass
        else:
            try:
                otp_record = EmailOTP.objects.get(email=email, otp=otp)
                if otp_record.is_expired():
                    return Response(
                        {"error": "OTP expired"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                otp_record.is_verified = True
                otp_record.save()
            except EmailOTP.DoesNotExist:
                return Response(
                    {"error": "Invalid OTP"},
                    status=status.HTTP_400_BAD_REQUEST
                )


        user, created = User.objects.get_or_create(
            email=email,
            defaults={"username": email.split("@")[0]}
        )

        refresh = RefreshToken.for_user(user)

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "role": user.roles,
            "active_role": user.active_role,
            "is_new_user": created,
            "profile_completed": user.profile_completed
        })


class GoogleLoginView(APIView):
    permission_classes = []

    def post(self, request):
        token = request.data.get("token")

        if not token:
            return Response(
                {"error": "Token is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            idinfo = id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID
            )
        except ValueError:
            return Response(
                {"error": "Invalid Google token"},
                status=status.HTTP_400_BAD_REQUEST
            )

        email = idinfo.get("email")

        if not email:
            return Response(
                {"error": "Email not found in Google account"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": email.split("@")[0],
                "first_name": idinfo.get("given_name", ""),
                "last_name": idinfo.get("family_name", ""),
            }
        )

        refresh = RefreshToken.for_user(user)

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "role": user.roles,
            "active_role": user.active_role,
            "is_new_user": created,
            "profile_completed": user.profile_completed
        })

class SelectRoleView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        role = request.data.get("role")
        user = request.user

        if not role:
            return Response(
                {"error": "Role is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if role not in ["VISITOR", "EXHIBITOR"]:
            return Response(
                {"error": "Invalid role. Please select VISITOR or EXHIBITOR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if role not in user.roles:
            user.roles.append(role)

        user.active_role = role
        user.save()

        return Response({
            "message": "Role activated",
            "active_role": user.active_role,
            "roles": user.roles,
            "profile_completed": user.profile_completed
        })


class CurrentUserView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        return Response({
            "id": u.id,
            "email": u.email,
            "username": u.username,
            "roles": u.roles,
            "active_role": u.active_role,
            "profile_completed": u.profile_completed
        })


class SwitchRoleView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        role = request.data.get("role")
        user = request.user

        if not role:
            return Response(
                {"error": "Role is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if role not in ["VISITOR", "EXHIBITOR"]:
            return Response(
                {"error": "Invalid role. Please select VISITOR or EXHIBITOR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if role not in user.roles:
            return Response(
                {"error": "You do not have access to this role"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.active_role = role
        user.save()

        return Response({
            "message": "Role switched",
            "active_role": user.active_role,
            "profile_completed": user.profile_completed
        })

class UpdateProfileView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def put(self, request):
        user = request.user
        username = request.data.get("username")

        if not username:
            return Response(
                {"error": "Username is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(username.strip()) < 2:
            return Response(
                {"error": "Username must be at least 2 characters long"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.username = username
        try:
            user.save()
        except IntegrityError:
            # ✅ FIX: Username already taken — seen in logs as duplicate key IntegrityError
            return Response(
                {"error": "Username already taken. Please choose another."},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response({
            "message": "Profile updated",
            "username": user.username,
            "email": user.email,
        })


class DeleteAccountView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user
        
        # Additional cleanup if needed (e.g. invalidating tokens) can be done here.
        # But for now, hard delete is enough since tokens will become invalid when user is gone.
        user.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)

