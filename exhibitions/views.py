from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import ExhibitorProfile

class ExhibitorProfileView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        if user.active_role != "EXHIBITOR":
            return Response({"error": "Not an exhibitor"}, status=403)

        if hasattr(user, "exhibitorprofile"):
            return Response({"error": "Profile already exists"}, status=400)

        profile = ExhibitorProfile.objects.create(
            user=user,
            company_name=request.data["company_name"],
            council_area=request.data["council_area"],
            business_type=request.data["business_type"],
            contact_number=request.data["contact_number"],
        )

        return Response({"message": "Profile created"})

class ExhibitorProfileStatusView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        exists = ExhibitorProfile.objects.filter(user=user).exists()

        return Response({
            "exists": exists
        })
