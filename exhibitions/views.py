from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import ExhibitorProfile, Exhibition, ExhibitionImage
from rest_framework.parsers import MultiPartParser, FormParser
from accounts.permissions import IsAdminUserRole
from .serializers import ExhibitionSerializer


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

class AdminCreateExhibitionView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        data = request.data.copy()

        exhibition = Exhibition.objects.create(
            name=data["name"],
            description=data["description"],
            start_date=data["start_date"],
            end_date=data["end_date"],
            venue=data["venue"],
            city=data["city"],
            state=data["state"],
            country=data["country"],
            booth_capacity=data["booth_capacity"],
            visitor_capacity=data["visitor_capacity"],
            map_image=data.get("map_image"),
        )

        for img in request.FILES.getlist("images"):
            ExhibitionImage.objects.create(
                exhibition=exhibition, image=img
            )

        return Response(
            ExhibitionSerializer(exhibition).data,
            status=201
        )

class AdminListExhibitionsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def get(self, request):
        exhibitions = Exhibition.objects.all().order_by("-created_at")
        return Response(
            ExhibitionSerializer(exhibitions, many=True).data
        )

class AdminUpdateExhibitionView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]
    parser_classes = [MultiPartParser, FormParser]

    def put(self, request, pk):
        exhibition = Exhibition.objects.get(pk=pk)

        for field in [
            "name", "description", "start_date", "end_date",
            "venue", "city", "state", "country", "is_active"
        ]:
            if field in request.data:
                setattr(exhibition, field, request.data[field])

        exhibition.save()
        return Response(ExhibitionSerializer(exhibition).data)

class AdminDeleteExhibitionView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def delete(self, request, pk):
        Exhibition.objects.filter(pk=pk).delete()
        return Response({"message": "Deleted"})
