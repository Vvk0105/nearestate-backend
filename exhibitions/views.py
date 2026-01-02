from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import ExhibitorProfile, Exhibition, ExhibitionImage, ExhibitorApplication, VisitorRegistration
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

class ExhibitorApplyView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, exhibition_id):
        user = request.user

        if user.active_role != "EXHIBITOR":
            return Response(
                {"error": "Only exhibitors can apply"},
                status=403
            )

        exhibition = Exhibition.objects.get(id=exhibition_id)

        if exhibition.available_booths <= 0:
            return Response(
                {"error": "No booths available"},
                status=400
            )

        if ExhibitorApplication.objects.filter(
            user=user, exhibition=exhibition
        ).exists():
            return Response(
                {"error": "Already applied"},
                status=400
            )

        ExhibitorApplication.objects.create(
            user=user,
            exhibition=exhibition,
            payment_screenshot=request.FILES["payment_screenshot"],
            transaction_id=request.data.get("transaction_id"),
        )

        return Response({"message": "Application submitted"})

class AdminListExhibitorApplications(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def get(self, request, exhibition_id):
        apps = ExhibitorApplication.objects.filter(
            exhibition_id=exhibition_id
        )
        data = []

        for app in apps:
            data.append({
                "id": app.id,
                "company": app.user.username,
                "email": app.user.email,
                "status": app.status,
                "transaction_id": app.transaction_id,
                "booth_number": app.booth_number,
                "payment_screenshot": app.payment_screenshot.url,
            })

        return Response(data)

class AdminUpdateExhibitorApplication(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def post(self, request, application_id):
        action = request.data.get("action")
        booth_number = request.data.get("booth_number")

        app = ExhibitorApplication.objects.get(id=application_id)
        exhibition = app.exhibition

        if action == "APPROVE":
            if exhibition.available_booths <= 0:
                return Response(
                    {"error": "No booths left"},
                    status=400
                )

            app.status = "APPROVED"
            app.booth_number = booth_number

            exhibition.available_booths -= 1
            exhibition.save()

        elif action == "REJECT":
            app.status = "REJECTED"

        app.save()
        return Response({"message": "Updated"})

class PublicExhibitionListView(APIView):
    permission_classes = []

    def get(self, request):
        exhibitions = Exhibition.objects.filter(is_active=True)
        return Response(
            ExhibitionSerializer(exhibitions, many=True).data
        )

class ExhibitorApplicationStatusView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.active_role != "EXHIBITOR":
            return Response([], status=200)

        apps = ExhibitorApplication.objects.filter(user=user)

        data = []
        for app in apps:
            data.append({
                "exhibition_id": app.exhibition.id,
                "status": app.status,
                "booth_number": app.booth_number,
            })

        return Response(data)

class VisitorRegisterView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, exhibition_id):
        user = request.user

        if user.active_role != "VISITOR":
            return Response(
                {"error": "Only visitors can register"},
                status=403
            )

        exhibition = Exhibition.objects.get(id=exhibition_id)

        if exhibition.available_visitors <= 0:
            return Response(
                {"error": "Visitor capacity full"},
                status=400
            )

        if VisitorRegistration.objects.filter(
            user=user, exhibition=exhibition
        ).exists():
            return Response(
                {"error": "Already registered"},
                status=400
            )

        VisitorRegistration.objects.create(
            user=user,
            exhibition=exhibition
        )

        exhibition.available_visitors -= 1
        exhibition.save()

        return Response({"message": "Registered successfully"})

class VisitorQRListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        regs = VisitorRegistration.objects.filter(user=request.user)

        data = []
        for r in regs:
            data.append({
                "exhibition": r.exhibition.name,
                "qr_code": str(r.qr_code),
                "is_checked_in": r.is_checked_in,
            })

        return Response(data)

class AdminQRScanView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def post(self, request):
        qr = request.data.get("qr_code")

        try:
            reg = VisitorRegistration.objects.get(qr_code=qr)
        except VisitorRegistration.DoesNotExist:
            return Response(
                {"error": "Invalid QR"},
                status=400
            )

        if reg.is_checked_in:
            return Response(
                {"error": "Already checked in"},
                status=400
            )

        reg.is_checked_in = True
        reg.save()

        return Response({
            "message": "Entry allowed",
            "visitor": reg.user.email,
            "exhibition": reg.exhibition.name
        })
