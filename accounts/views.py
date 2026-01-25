from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from rest_framework_simplejwt.tokens import RefreshToken

from .models import EmailOTP, User
from .utils import generate_otp

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

        otp = generate_otp()

        EmailOTP.objects.update_or_create(
            email=email,
            defaults={
                "otp": otp,
                "is_verified": False,
                "created_at": timezone.now()
            }
        )

        send_mail(
            subject="Your NearEstate Login OTP",
            message=f"Your OTP is {otp}. It is valid for 5 minutes.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )

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
                {"error": "Invalid or expired refresh token"},
                status=status.HTTP_401_UNAUTHORIZED
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

        try:
            otp_record = EmailOTP.objects.get(email=email, otp=otp)
        except EmailOTP.DoesNotExist:
            return Response(
                {"error": "Invalid OTP"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if otp_record.is_expired():
            return Response(
                {"error": "OTP expired"},
                status=status.HTTP_400_BAD_REQUEST
            )

        otp_record.is_verified = True
        otp_record.save()

        user, created = User.objects.get_or_create(
            email=email,
            defaults={"username": email.split("@")[0]}
        )

        refresh = RefreshToken.for_user(user)

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "role": user.roles,
            "is_new_user": created
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
            "is_new_user": created
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
            "roles": user.roles
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
            "active_role": u.active_role
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
            "active_role": user.active_role
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
        user.save()

        return Response({
            "message": "Profile updated",
            "username": user.username,
            "email": user.email, 
        })

