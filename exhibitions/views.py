from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import (
    ExhibitorProfile, Exhibition, ExhibitionImage, ExhibitorApplication,
    VisitorRegistration, Property, PropertyImage,
    EventRecap, RecapImage, RecapVideo, RecapSocialLink, ExhibitionPriceTier,
)
from rest_framework.parsers import MultiPartParser, FormParser
from accounts.permissions import IsAdminUserRole, IsExhibitorWithProfile
from .serializers import (
    ExhibitionSerializer, PropertySerializer,
    ExhibitorProfileSerializer, ExhibitorApplicationSerializer,
    EventRecapSerializer,
)
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404
from rest_framework import status
from exhibitions.utils.tasks import send_event_email, send_exhibitor_approval_email, send_visitor_qr_email
from accounts.models import User
from exhibitions.utils.image_tasks import compress_model_image
from django.utils import timezone
from django.db.models import Case, When, Value, IntegerField, Q


class ExhibitorProfileView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.active_role != "EXHIBITOR" and user.active_role != "ADMIN":
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

        if user.active_role != "EXHIBITOR" and user.active_role != "ADMIN":
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

        # Mark profile as completed
        user.profile_completed = True
        user.save()

        serializer = ExhibitorProfileSerializer(profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def patch(self, request):
        user = request.user

        if user.active_role != "EXHIBITOR" and user.active_role != "ADMIN":
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
            venue_link=data.get("venue_link") or None,
            location_link=data.get("location_link") or None,
            city=data["city"],
            state=data["state"],
            country=data["country"],
            booth_capacity=data["booth_capacity"],
            visitor_capacity=data["visitor_capacity"],
            registration_fee=data.get("registration_fee"),
            currency_symbol=data.get("currency_symbol", "₹"),
            payment_details=data.get("payment_details"),
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

        # ── Price Tiers ──
        import json
        price_tiers_raw = request.data.get("price_tiers")
        if price_tiers_raw:
            try:
                tiers = json.loads(price_tiers_raw) if isinstance(price_tiers_raw, str) else price_tiers_raw
                for i, tier in enumerate(tiers):
                    ExhibitionPriceTier.objects.create(
                        exhibition=exhibition,
                        name=tier.get("name", ""),
                        fee=tier.get("fee", 0),
                        description=tier.get("description", ""),
                        order=i,
                    )
            except (json.JSONDecodeError, TypeError):
                pass

        users = User.objects.filter(is_active=True).exclude(email="")
        emails = list(users.values_list("email", flat=True))

        subject = f"Invitation: {exhibition.name} | {exhibition.city}"
        exhibition_data = {
            'name': exhibition.name,
            'start_date': exhibition.start_date,
            'end_date': exhibition.end_date,
            'venue': exhibition.venue,
            'city': exhibition.city,
            'state': exhibition.state,
            'country': exhibition.country,
        }

        if emails:
            send_event_email.delay(subject, exhibition_data, emails)

        return Response(
            ExhibitionSerializer(exhibition, context={'request': request}).data,
            status=201
        )

class AdminListExhibitionsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def get(self, request):
        query = request.query_params.get('search', '')
        status_filter = request.query_params.get('status', 'all')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('limit', 10))

        exhibitions = Exhibition.objects.all()

        if query:
            exhibitions = exhibitions.filter(
                Q(name__icontains=query) |
                Q(state__icontains=query) |
                Q(city__icontains=query) |
                Q(country__icontains=query)
            )

        today = timezone.localdate()

        # Calculate counts based on current search query
        all_count = exhibitions.count()
        ongoing_count = exhibitions.filter(start_date__lte=today, end_date__gte=today).count()
        upcoming_count = exhibitions.filter(start_date__gt=today).count()
        past_count = exhibitions.filter(end_date__lt=today).count()

        counts = {
            "all": all_count,
            "ongoing": ongoing_count,
            "upcoming": upcoming_count,
            "past": past_count
        }

        # Apply specific status filtering
        if status_filter == 'ongoing':
            exhibitions = exhibitions.filter(start_date__lte=today, end_date__gte=today).order_by("start_date")
        elif status_filter == 'upcoming':
            exhibitions = exhibitions.filter(start_date__gt=today).order_by("start_date")
        elif status_filter == 'past':
            exhibitions = exhibitions.filter(end_date__lt=today).order_by("-start_date")
        else: # 'all'
            # Prioritize: Ongoing (1), Upcoming (2), Past (3)
            exhibitions = (
                exhibitions
                .annotate(
                    status_priority=Case(
                        When(start_date__lte=today, end_date__gte=today, then=Value(1)),
                        When(start_date__gt=today, then=Value(2)),
                        When(end_date__lt=today, then=Value(3)),
                        default=Value(3),
                        output_field=IntegerField()
                    )
                )
                .order_by("status_priority", "start_date")
            )

        total = exhibitions.count()
        start = (page - 1) * page_size
        end = start + page_size
        exhibitions_page = exhibitions[start:end]

        return Response({
            "data": ExhibitionSerializer(exhibitions_page, many=True, context={'request': request}).data,
            "total": total,
            "page": page,
            "limit": page_size,
            "counts": counts
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
            "booth_capacity", "visitor_capacity", "registration_fee",
            "currency_symbol", "payment_details", "venue_link", "location_link"
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
                elif field in ("venue_link", "location_link"):
                    # Store empty strings as None so the field is truly cleared
                    setattr(exhibition, field, value.strip() or None)
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

        # ── Price Tiers (replace all on update) ──
        import json
        price_tiers_raw = request.data.get("price_tiers")
        if price_tiers_raw is not None:
            try:
                tiers = json.loads(price_tiers_raw) if isinstance(price_tiers_raw, str) else price_tiers_raw
                ExhibitionPriceTier.objects.filter(exhibition=exhibition).delete()
                for i, tier in enumerate(tiers):
                    ExhibitionPriceTier.objects.create(
                        exhibition=exhibition,
                        name=tier.get("name", ""),
                        fee=tier.get("fee", 0),
                        description=tier.get("description", ""),
                        order=i,
                    )
            except (json.JSONDecodeError, TypeError):
                pass

        exhibition.save()

        return Response(ExhibitionSerializer(exhibition, context={'request': request}).data)

class AdminDeleteExhibitionView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def delete(self, request, pk):
        Exhibition.objects.filter(pk=pk).delete()
        return Response({"message": "Deleted"})


class AdminEventRecapView(APIView):
    """GET / PUT the event recap for a past exhibition."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, exhibition_id):
        exhibition = get_object_or_404(Exhibition, pk=exhibition_id)
        try:
            recap = exhibition.recap
        except EventRecap.DoesNotExist:
            return Response({"detail": "No recap found"}, status=404)
        serializer = EventRecapSerializer(recap, context={'request': request})
        return Response(serializer.data)

    def put(self, request, exhibition_id):
        import json
        exhibition = get_object_or_404(Exhibition, pk=exhibition_id)
        recap, _ = EventRecap.objects.get_or_create(exhibition=exhibition)

        # ── Images ──
        # Remove deleted image IDs
        remove_img_ids_raw = request.data.get("remove_image_ids", "")
        if remove_img_ids_raw:
            ids = [int(x) for x in str(remove_img_ids_raw).split(",") if x.strip().isdigit()]
            RecapImage.objects.filter(id__in=ids, recap=recap).delete()

        # Add new images
        for img in request.FILES.getlist("recap_images"):
            obj = RecapImage.objects.create(recap=recap, image=img)
            compress_model_image.delay("exhibitions", "RecapImage", obj.id, "image")

        # ── Videos ──
        # Remove deleted video IDs
        remove_vid_ids_raw = request.data.get("remove_video_ids", "")
        if remove_vid_ids_raw:
            ids = [int(x) for x in str(remove_vid_ids_raw).split(",") if x.strip().isdigit()]
            RecapVideo.objects.filter(id__in=ids, recap=recap).delete()

        # Add new videos (JSON array: [{youtube_url, title}])
        new_videos_raw = request.data.get("new_videos")
        if new_videos_raw:
            try:
                new_videos = json.loads(new_videos_raw) if isinstance(new_videos_raw, str) else new_videos_raw
                existing_count = RecapVideo.objects.filter(recap=recap).count()
                for i, v in enumerate(new_videos):
                    RecapVideo.objects.create(
                        recap=recap,
                        youtube_url=v.get("youtube_url", ""),
                        title=v.get("title", ""),
                        order=existing_count + i,
                    )
            except (json.JSONDecodeError, TypeError):
                pass

        # ── Social Links ──
        # Remove deleted social link IDs
        remove_social_ids_raw = request.data.get("remove_social_ids", "")
        if remove_social_ids_raw:
            ids = [int(x) for x in str(remove_social_ids_raw).split(",") if x.strip().isdigit()]
            RecapSocialLink.objects.filter(id__in=ids, recap=recap).delete()

        # Add new social links (JSON array: [{title, url}])
        new_socials_raw = request.data.get("new_social_links")
        if new_socials_raw:
            try:
                new_socials = json.loads(new_socials_raw) if isinstance(new_socials_raw, str) else new_socials_raw
                existing_count = RecapSocialLink.objects.filter(recap=recap).count()
                for i, s in enumerate(new_socials):
                    RecapSocialLink.objects.create(
                        recap=recap,
                        title=s.get("title", ""),
                        url=s.get("url", ""),
                        order=existing_count + i,
                    )
            except (json.JSONDecodeError, TypeError):
                pass

        recap.save()
        serializer = EventRecapSerializer(recap, context={'request': request})
        return Response(serializer.data)

class ExhibitorApplyView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsExhibitorWithProfile]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, exhibition_id):
        user = request.user

        if user.active_role != "EXHIBITOR" and user.active_role != "ADMIN":
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
        apps = ExhibitorApplication.objects.filter(exhibition_id=exhibition_id).select_related('user', 'user__exhibitorprofile')

        serializer = ExhibitorApplicationSerializer(
            apps,
            many=True,
            context={"request": request}
        )
        return Response(serializer.data)

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
        # Add pagination to prevent server memory exhaustion and hanging requests
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('limit', 10))
        status_filter = request.query_params.get('status', 'all')
        query = request.query_params.get('search', '')

        today = timezone.localdate()

        # Build base active exhibitions query
        base_query = Exhibition.objects.prefetch_related('images').filter(is_active=True)

        if query:
            base_query = base_query.filter(
                Q(name__icontains=query) |
                Q(state__icontains=query) |
                Q(city__icontains=query) |
                Q(country__icontains=query)
            )

        # Calculate counts for all status types (all, ongoing, upcoming, past)
        all_count = base_query.count()
        ongoing_count = base_query.filter(start_date__lte=today, end_date__gte=today).count()
        upcoming_count = base_query.filter(start_date__gt=today).count()
        past_count = base_query.filter(end_date__lt=today).count()

        counts = {
            "all": all_count,
            "ongoing": ongoing_count,
            "upcoming": upcoming_count,
            "past": past_count
        }

        # Apply specific status filtering
        if status_filter == 'ongoing':
            exhibitions = base_query.filter(start_date__lte=today, end_date__gte=today).order_by("start_date")
        elif status_filter == 'upcoming':
            exhibitions = base_query.filter(start_date__gt=today).order_by("start_date")
        elif status_filter == 'past':
            exhibitions = base_query.filter(end_date__lt=today).order_by("-start_date")
        else: # 'all'
            # Prioritize: Ongoing (1), Upcoming (2), Past (3)
            exhibitions = (
                base_query
                .annotate(
                    status_priority=Case(
                        When(start_date__lte=today, end_date__gte=today, then=Value(1)),
                        When(start_date__gt=today, then=Value(2)),
                        When(end_date__lt=today, then=Value(3)),
                        default=Value(3),
                        output_field=IntegerField()
                    )
                )
                .order_by("status_priority", "start_date")
            )

        total = exhibitions.count()
        start = (page - 1) * page_size
        end = start + page_size
        exhibitions_page = exhibitions[start:end]

        return Response({
            "data": ExhibitionSerializer(exhibitions_page, many=True, context={'request': request}).data,
            "total": total,
            "page": page,
            "limit": page_size,
            "counts": counts
        })

class ExhibitorApplicationStatusView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.active_role != "EXHIBITOR" and user.active_role != "ADMIN":
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

        if user.active_role != "VISITOR" and user.active_role != "ADMIN":
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

        registration = VisitorRegistration.objects.create(
            user=user,
            exhibition=exhibition
        )

        exhibition.available_visitors -= 1
        exhibition.save()

        # Send QR confirmation email to the visitor (async via Celery)
        send_visitor_qr_email.delay(
            email=user.email,
            visitor_name=user.username,
            exhibition_name=exhibition.name,
            exhibition_venue=exhibition.venue,
            exhibition_city=exhibition.city,
            start_date=str(exhibition.start_date),
            end_date=str(exhibition.end_date),
            qr_code_uuid=str(registration.qr_code),
        )

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
    permission_classes = [IsExhibitorWithProfile]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, exhibition_id):
        user = request.user

        if user.active_role != "EXHIBITOR" and user.active_role != "ADMIN":
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
            PropertySerializer(prop, context={'request': request}).data,
            status=201
        )

class ExhibitorMyPropertiesView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsExhibitorWithProfile]

    def get(self, request):
        props = Property.objects.filter(exhibitor=request.user).order_by("-created_at")
        return Response(PropertySerializer(props, many=True, context={'request': request}).data)

class ExhibitorDeletePropertyView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsExhibitorWithProfile]

    def delete(self, request, property_id):
        prop = Property.objects.get(id=property_id)

        if prop.exhibitor != request.user:
            return Response({"error": "Forbidden"}, status=403)

        prop.delete()
        return Response({"message": "Deleted"})
    
class ExhibitorEditPropertyView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsExhibitorWithProfile]

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

        return Response(PropertySerializer(prop, context={'request': request}).data)

class PublicExhibitionPropertiesView(APIView):
    permission_classes = []

    def get(self, request, exhibitor_id):
        props = Property.objects.filter(exhibitor_id=exhibitor_id).order_by("-created_at")
        return Response(PropertySerializer(props, many=True, context={'request': request}).data)

class PublicExhibitionDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, id):
        # Apply prefetch_related for images to avoid individual query evaluation limits
        # and ensure only active events are fetchable publicly.
        query = Exhibition.objects.prefetch_related('images').filter(is_active=True)
        exhibition = get_object_or_404(query, id=id)
        serializer = ExhibitionSerializer(exhibition, context={'request': request})
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
            profile = getattr(app.user, "exhibitorprofile", None)

            data.append({
                "id": app.user.id,
                "company_name": profile.company_name if profile else app.user.username,
                "business_type": profile.business_type if profile else "N/A",
                "council_area": profile.council_area if profile else "N/A",
                "contact_number": profile.contact_number if profile else "N/A",
                "booth_number": app.booth_number,
            })

        return Response(data)


    def patch(self, request):
        user = request.user
        if user.active_role != "EXHIBITOR" and user.active_role != "ADMIN":
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


class AdminCheckExhibitorView(APIView):
    """
    Lookup endpoint for the admin 'Add Exhibitor' multi-step modal.
    Returns whether the email belongs to an existing user and whether they
    already have an ExhibitorProfile, along with the profile details.

    GET /exhibitions/admin/exhibitions/<id>/check-exhibitor/?email=...
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def get(self, request, exhibition_id):
        email = request.query_params.get("email", "").strip().lower()

        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({
                "user_exists": False,
                "profile_exists": False,
                "already_registered": False,
                "profile": None,
            })

        # Check if already registered for this event
        already_registered = ExhibitorApplication.objects.filter(
            user=user, exhibition_id=exhibition_id
        ).exists()

        profile = getattr(user, "exhibitorprofile", None)

        return Response({
            "user_exists": True,
            "profile_exists": profile is not None,
            "already_registered": already_registered,
            "profile": {
                "company_name": profile.company_name,
                "business_type": profile.business_type,
                "council_area": profile.council_area,
                "contact_number": profile.contact_number,
            } if profile else None,
        })


class AdminAddExhibitorView(APIView):
    """
    Admin-only endpoint to directly add (and auto-approve) an exhibitor for an event.

    Accepts multipart/form-data so an optional badge file can be uploaded.
    If the user already exists their account is reused. If an ExhibitorProfile
    already exists it is kept; otherwise one is created from the submitted data.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, exhibition_id):
        email = request.data.get("email", "").strip().lower()
        company_name = request.data.get("company_name", "").strip()
        council_area = request.data.get("council_area", "").strip()
        business_type = request.data.get("business_type", "").strip()
        contact_number = request.data.get("contact_number", "").strip()
        booth_number = request.data.get("booth_number")
        badge_file = request.FILES.get("badge")

        # --- Validate required fields ---
        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not booth_number:
            return Response({"error": "Booth number is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            exhibition = Exhibition.objects.get(id=exhibition_id)
        except Exhibition.DoesNotExist:
            return Response({"error": "Exhibition not found"}, status=status.HTTP_404_NOT_FOUND)

        # --- Check booth availability ---
        if exhibition.available_booths <= 0:
            return Response({"error": "No booths available for this event"}, status=status.HTTP_400_BAD_REQUEST)

        # --- Get or create user ---
        user, created = User.objects.get_or_create(
            email=email,
            defaults={"username": email.split("@")[0]}
        )

        # Append EXHIBITOR role if not already present
        if "EXHIBITOR" not in user.roles:
            user.roles.append("EXHIBITOR")
        user.active_role = "EXHIBITOR"
        user.profile_completed = True
        user.save()

        # --- Get or create ExhibitorProfile ---
        profile, profile_created = ExhibitorProfile.objects.get_or_create(
            user=user,
            defaults={
                "company_name": company_name or email.split("@")[0],
                "council_area": council_area or "N/A",
                "business_type": business_type or "OTHER_BUSINESSES",
                "contact_number": contact_number or "N/A",
            }
        )

        # If profile already existed but new values were submitted, update them
        if not profile_created:
            updated = False
            if company_name:
                profile.company_name = company_name
                updated = True
            if council_area:
                profile.council_area = council_area
                updated = True
            if business_type:
                profile.business_type = business_type
                updated = True
            if contact_number:
                profile.contact_number = contact_number
                updated = True
            if updated:
                profile.save()

        # --- Check for duplicate application ---
        if ExhibitorApplication.objects.filter(user=user, exhibition=exhibition).exists():
            return Response(
                {"error": "This exhibitor is already registered for this event"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # --- Create auto-approved application ---
        app = ExhibitorApplication.objects.create(
            user=user,
            exhibition=exhibition,
            status="APPROVED",
            booth_number=booth_number,
            payment_screenshot=None,
        )

        # Attach badge if provided
        if badge_file:
            app.badge = badge_file
            app.save()

        # --- Decrement available booths ---
        exhibition.available_booths -= 1
        exhibition.save()

        # --- Send approval email (async via Celery) ---
        send_exhibitor_approval_email.delay(
            email=user.email,
            exhibitor_name=profile.company_name,
            exhibition_name=exhibition.name,
            booth_number=booth_number,
            badge_path=app.badge.path if app.badge else None,
        )


        return Response({
            "message": "Exhibitor added and approved successfully",
            "user_created": created,
            "profile_created": profile_created,
            "booth_number": booth_number,
        }, status=status.HTTP_201_CREATED)


class AdminAddVisitorView(APIView):
    """
    Admin-only endpoint to directly register a visitor for an event.

    If the user already exists their account is reused and the VISITOR role is
    appended. A VisitorRegistration is created and the standard QR pass email
    is dispatched.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def post(self, request, exhibition_id):
        email = request.data.get("email", "").strip().lower()

        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            exhibition = Exhibition.objects.get(id=exhibition_id)
        except Exhibition.DoesNotExist:
            return Response({"error": "Exhibition not found"}, status=status.HTTP_404_NOT_FOUND)

        # --- Check visitor capacity ---
        if exhibition.available_visitors <= 0:
            return Response({"error": "Visitor capacity is full for this event"}, status=status.HTTP_400_BAD_REQUEST)

        # --- Get or create user ---
        user, created = User.objects.get_or_create(
            email=email,
            defaults={"username": email.split("@")[0]}
        )

        # Append VISITOR role if not already present
        if "VISITOR" not in user.roles:
            user.roles.append("VISITOR")
        # Only set active_role to VISITOR if user has no current active role
        if not user.active_role:
            user.active_role = "VISITOR"
        user.save()

        # --- Check for duplicate registration ---
        if VisitorRegistration.objects.filter(user=user, exhibition=exhibition).exists():
            return Response(
                {"error": "This visitor is already registered for this event"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # --- Create registration ---
        registration = VisitorRegistration.objects.create(
            user=user,
            exhibition=exhibition
        )

        # --- Decrement available visitors ---
        exhibition.available_visitors -= 1
        exhibition.save()

        # --- Send QR pass email (async via Celery) ---
        send_visitor_qr_email.delay(
            email=user.email,
            visitor_name=user.username,
            exhibition_name=exhibition.name,
            exhibition_venue=exhibition.venue,
            exhibition_city=exhibition.city,
            start_date=str(exhibition.start_date),
            end_date=str(exhibition.end_date),
            qr_code_uuid=str(registration.qr_code),
        )

        return Response({
            "message": "Visitor registered successfully",
            "user_created": created,
            "qr_code": str(registration.qr_code),
        }, status=status.HTTP_201_CREATED)

