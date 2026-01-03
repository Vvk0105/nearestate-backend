from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import ExhibitorProfile, Exhibition, ExhibitionImage, ExhibitorApplication, VisitorRegistration, Property, PropertyImage
from rest_framework.parsers import MultiPartParser, FormParser
from accounts.permissions import IsAdminUserRole
from .serializers import ExhibitionSerializer, PropertySerializer, ExhibitorProfileSerializer
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404
from rest_framework import status

class ExhibitorProfileView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.active_role != "EXHIBITOR":
            return Response(
                {"error": "Not an exhibitor"},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            profile = ExhibitorProfile.objects.select_related("user").get(user=user)
        except ExhibitorProfile.DoesNotExist:
            return Response(
                {"error": "Profile not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ExhibitorProfileSerializer(profile)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        user = request.user

        if user.active_role != "EXHIBITOR":
            return Response(
                {"error": "Not an exhibitor"},
                status=status.HTTP_403_FORBIDDEN
            )

        if hasattr(user, "exhibitorprofile"):
            return Response(
                {"error": "Profile already exists"},
                status=status.HTTP_400_BAD_REQUEST
            )

        profile = ExhibitorProfile.objects.create(
            user=user,
            company_name=request.data.get("company_name"),
            council_area=request.data.get("council_area"),
            business_type=request.data.get("business_type"),
            contact_number=request.data.get("contact_number"),
        )

        serializer = ExhibitorProfileSerializer(profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

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
            "venue", "city", "state", "country", "is_active", 
            "booth_capacity", "visitor_capacity"
        ]:
            if field in request.data:
                value = request.data[field]

                if field == "is_active":
                    value = str(value).lower() in ("true", "1", "yes", "on")

                setattr(exhibition, field, value)

        if "map_image" in request.FILES:
            exhibition.map_image = request.FILES["map_image"]
        
        exhibition.save()

        # Handle New Images
        for img in request.FILES.getlist("images"):
            ExhibitionImage.objects.create(exhibition=exhibition, image=img)

        # Handle Removed Images (expecting comma separated IDs or list)
        remove_ids = request.data.get("remove_image_ids")
        if remove_ids:
            # If standard FormData array behavior, getlist might be needed or split string
            if isinstance(remove_ids, str):
                ids = [int(x) for x in remove_ids.split(",") if x.isdigit()]
            else:
                ids = remove_ids
            
            ExhibitionImage.objects.filter(
                id__in=ids, exhibition=exhibition
            ).delete()

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
                "badge": app.badge.url if app.badge else None,
            })

        return Response(data)

class AdminUpdateExhibitorApplication(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]
    parser_classes = [MultiPartParser, FormParser]

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
            
            if "badge" in request.FILES:
                app.badge = request.FILES["badge"]

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
                "exhibition": app.exhibition.name,
                "exhibition_id": app.exhibition.id,
                "status": app.status,
                "booth_number": app.booth_number,
                "badge": app.badge.url if app.badge else None,
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

class ExhibitorCreatePropertyView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, exhibition_id):
        user = request.user

        if user.active_role != "EXHIBITOR":
            return Response({"error": "Not exhibitor"}, status=403)

        approved = ExhibitorApplication.objects.filter(
            user=user,
            exhibition_id=exhibition_id,
            status="APPROVED"
        ).exists()

        if not approved:
            return Response(
                {"error": "Not approved for this exhibition"},
                status=403
            )

        prop = Property.objects.create(
            exhibitor=user,
            exhibition_id=exhibition_id,
            title=request.data["title"],
            location=request.data["location"],
            price_from=request.data["price_from"],
            price_to=request.data["price_to"],
            description=request.data.get("description", ""),
        )

        for img in request.FILES.getlist("images"):
            PropertyImage.objects.create(property=prop, image=img)

        return Response(
            PropertySerializer(prop).data,
            status=201
        )

class ExhibitorMyPropertiesView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        props = Property.objects.filter(exhibitor=request.user)
        return Response(PropertySerializer(props, many=True).data)

class ExhibitorDeletePropertyView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, property_id):
        prop = Property.objects.get(id=property_id)

        if prop.exhibitor != request.user:
            return Response({"error": "Forbidden"}, status=403)

        prop.delete()
        return Response({"message": "Deleted"})
    
class ExhibitorEditPropertyView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, property_id):
        prop = Property.objects.get(id=property_id)

        if prop.exhibitor != request.user:
            return Response({"error": "Forbidden"}, status=403)

        for field in [
            "title",
            "location",
            "price_from",
            "price_to",
            "description"
        ]:
            if field in request.data:
                setattr(prop, field, request.data[field])

        prop.save()

        return Response(PropertySerializer(prop).data)

class PublicExhibitionPropertiesView(APIView):
    permission_classes = []

    def get(self, request, exhibitor_id):
        props = Property.objects.filter(exhibitor_id=exhibitor_id)
        return Response(PropertySerializer(props, many=True).data)

class PublicExhibitionDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, id):
        exhibition = get_object_or_404(Exhibition, id=id)
        serializer = ExhibitionSerializer(exhibition)
        return Response(serializer.data)

class PublicExhibitorsByExhibitionView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, id):
        applications = (
            ExhibitorApplication.objects
            .filter(exhibition_id=id, status="APPROVED")
            .select_related("user", "user__exhibitorprofile")
        )

        data = []
        for app in applications:
            profile = app.user.exhibitorprofile

            data.append({
                "id": app.user.id,
                "company_name": profile.company_name,
                "booth_number": app.booth_number,
            })

        return Response(data)


class VisitorMyRegistrationsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        regs = VisitorRegistration.objects.filter(
            user=request.user
        ).select_related("exhibition")

        data = []
        for r in regs:
            data.append({
                "event_id": r.exhibition.id,
                "event_name": r.exhibition.name,
                "start_date": r.exhibition.start_date,
                "end_date": r.exhibition.end_date,
                "qr_code": str(r.qr_code),
                "is_checked_in": r.is_checked_in,
            })

        return Response(data)
