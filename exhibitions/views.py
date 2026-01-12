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
from exhibitions.utils.tasks import send_event_email, send_exhibitor_approval_email
from accounts.models import User
from exhibitions.utils.image_tasks import compress_model_image


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

    def patch(self, request):
        user = request.user

        if user.active_role != "EXHIBITOR":
            return Response(
                {"error": "Not an exhibitor"},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            profile = ExhibitorProfile.objects.get(user=user)
        except ExhibitorProfile.DoesNotExist:
            return Response(
                {"error": "Profile not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        for field in ["company_name", "council_area", "business_type", "contact_number"]:
            if field in request.data:
                setattr(profile, field, request.data[field])

        profile.save()
        serializer = ExhibitorProfileSerializer(profile)
        return Response(serializer.data, status=status.HTTP_200_OK)

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
            image_obj = ExhibitionImage.objects.create(
                exhibition=exhibition, image=img
            )

            compress_model_image.delay(
                "exhibitions",
                "ExhibitionImage",
                image_obj.id,
                "image",
            )

        users = User.objects.filter(is_active=True).exclude(email="")
        emails = list(users.values_list("email", flat=True))

        subject = f"New Exhibition: {exhibition.name}"
        message = f"""
A new real estate exhibition has been announced!

Event: {exhibition.name}
Date: {exhibition.start_date} to {exhibition.end_date}
Location: {exhibition.city}

Login to NearEstate to view details and register.
"""

        if emails:
            send_event_email.delay(subject, message, emails)

        return Response(
            ExhibitionSerializer(exhibition).data,
            status=201
        )

class AdminListExhibitionsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def get(self, request):
        query = request.query_params.get('search', '')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('limit', 10))

        exhibitions = Exhibition.objects.all().order_by("-created_at")

        if query:
            exhibitions = exhibitions.filter(name__icontains=query)

        total = exhibitions.count()
        start = (page - 1) * page_size
        end = start + page_size
        exhibitions = exhibitions[start:end]

        return Response({
            "data": ExhibitionSerializer(exhibitions, many=True).data,
            "total": total,
            "page": page,
            "limit": page_size
        })

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

                # Handle Capacity Changes - Update Availability
                if field == "booth_capacity":
                    try:
                        new_cap = int(value)
                        delta = new_cap - exhibition.booth_capacity
                        exhibition.available_booths += delta
                        setattr(exhibition, field, new_cap)
                    except ValueError:
                        pass # Ignore invalid int
                        
                elif field == "visitor_capacity":
                    try:
                        new_cap = int(value)
                        delta = new_cap - exhibition.visitor_capacity
                        exhibition.available_visitors += delta
                        setattr(exhibition, field, new_cap)
                    except ValueError:
                        pass
                else:
                    setattr(exhibition, field, value)

        # 🔹 Remove map image
        if request.data.get("remove_map_image") == "true":
            if exhibition.map_image:
                exhibition.map_image.delete(save=False)
            exhibition.map_image = None

        # 🔹 Replace map image
        if "map_image" in request.FILES:
            if exhibition.map_image:
                exhibition.map_image.delete(save=False)

            exhibition.map_image = request.FILES["map_image"]

            compress_model_image.delay(
                "exhibitions",
                "Exhibition",
                exhibition.id,
                "map_image",
            )

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

        app = ExhibitorApplication.objects.create(
            user=user,
            exhibition=exhibition,
            payment_screenshot=request.FILES["payment_screenshot"],
            transaction_id=request.data.get("transaction_id"),
        )

        compress_model_image.delay(
            "exhibitions",
            "ExhibitorApplication",
            app.id,
            "payment_screenshot",
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
            app.save()

            send_exhibitor_approval_email.delay(
                email=app.user.email,
                exhibitor_name=app.user.username,
                exhibition_name=exhibition.name,
                booth_number=booth_number,
                badge_path=app.badge.path if app.badge else None,
            )

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

    def get(self, request, exhibition_id):
        user = request.user

        is_registered = VisitorRegistration.objects.filter(
            user=user,
            exhibition_id=exhibition_id
        ).exists()

        return Response({
            "is_registered": is_registered
        })

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
            image_obj = PropertyImage.objects.create(property=prop, image=img)

            compress_model_image.delay(
                "exhibitions",
                "PropertyImage",
                image_obj.id,
                "image",
            )
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

        # Handle New Images
        for img in request.FILES.getlist("images"):
            PropertyImage.objects.create(property=prop, image=img)

        # Handle Removed Images
        remove_ids = request.data.get("remove_image_ids")
        if remove_ids:
            if isinstance(remove_ids, str):
                ids = [int(x) for x in remove_ids.split(",") if x.isdigit()]
            else:
                ids = remove_ids
            
            PropertyImage.objects.filter(
                id__in=ids, property=prop
            ).delete()

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
                "business_type": profile.business_type,
                "council_area": profile.council_area,
                "contact_number": profile.contact_number,
                "booth_number": app.booth_number,
            })

        return Response(data)


    def patch(self, request):
        user = request.user
        if user.active_role != "EXHIBITOR":
            return Response({"error": "Not an exhibitor"}, status=403)

        profile = get_object_or_404(ExhibitorProfile, user=user)

        for field in ["company_name", "council_area", "business_type", "contact_number"]:
            if field in request.data:
                setattr(profile, field, request.data[field])
        
        profile.save()
        return Response(ExhibitorProfileSerializer(profile).data)

class AdminDashboardStatsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def get(self, request):
        total_events = Exhibition.objects.count()
        active_events = Exhibition.objects.filter(is_active=True).count()

        unique_visitors = VisitorRegistration.objects.values('user').distinct().count()
        unique_exhibitors = ExhibitorApplication.objects.filter(status='APPROVED').values('user').distinct().count()

        return Response({
            "total_events": total_events,
            "active_events": active_events,
            "total_visitors": unique_visitors,
            "total_exhibitors": unique_exhibitors
        })

from django.db.models import Q

class AdminEventVisitorsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def get(self, request, exhibition_id):
        query = request.query_params.get('search', '')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('limit', 10))

        regs = VisitorRegistration.objects.filter(exhibition_id=exhibition_id).select_related('user')

        if query:
            regs = regs.filter(
                Q(user__username__icontains=query) |
                Q(user__email__icontains=query)
            )

        total = regs.count()
        start = (page - 1) * page_size
        end = start + page_size
        regs = regs[start:end]

        data = []
        for r in regs:
            data.append({
                "id": r.id,
                "name": r.user.username,
                "email": r.user.email,
                "registered_at": r.registered_at if hasattr(r, 'registered_at') else None,
                "is_checked_in": r.is_checked_in,
                "qr_code": str(r.qr_code)
            })
        
        return Response({
            "data": data,
            "total": total,
            "page": page,
            "limit": page_size
        })

class AdminEventExhibitorsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def get(self, request, exhibition_id):
        query = request.query_params.get('search', '')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('limit', 10))

        apps = ExhibitorApplication.objects.filter(
            exhibition_id=exhibition_id, 
            status='APPROVED'
        ).select_related('user', 'user__exhibitorprofile')

        if query:
            apps = apps.filter(
                Q(user__username__icontains=query) |
                Q(user__email__icontains=query) |
                Q(user__exhibitorprofile__company_name__icontains=query)
            )

        total = apps.count()
        start = (page - 1) * page_size
        end = start + page_size
        apps = apps[start:end]

        data = []
        for app in apps:
            profile = getattr(app.user, 'exhibitorprofile', None)
            data.append({
                "id": app.id,
                "company_name": profile.company_name if profile else app.user.username,
                "email": app.user.email,
                "booth_number": app.booth_number,
                "badge": app.badge.url if app.badge else None,
                # Additional details for "Eye" icon if needed, though they can be fetched individually or here
                "contact_number": profile.contact_number if profile else None,
                "business_type": profile.business_type if profile else None,
                "council_area": profile.council_area if profile else None
            })
            
        return Response({
            "data": data,
            "total": total,
            "page": page,
            "limit": page_size
        })

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
                "city": r.exhibition.city,
                "venue": r.exhibition.venue,
                "is_active": r.exhibition.is_active,
                "qr_code": str(r.qr_code),
                "is_checked_in": r.is_checked_in,
            })

        return Response(data)

class AdminToggleVisitorCheckInView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def post(self, request, visitor_id):
        reg = get_object_or_404(VisitorRegistration, id=visitor_id)
        reg.is_checked_in = not reg.is_checked_in
        reg.save()
        return Response({"id": reg.id, "is_checked_in": reg.is_checked_in})
