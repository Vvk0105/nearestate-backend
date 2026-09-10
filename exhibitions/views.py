from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import (
    ExhibitorProfile, Exhibition, ExhibitionImage, ExhibitorApplication,
    VisitorRegistration, Property, PropertyImage,
    EventRecap, RecapImage, RecapVideo, RecapSocialLink, ExhibitionPriceTier,
    ExhibitionSchedule,
)
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from accounts.permissions import IsAdminUserRole, IsExhibitorWithProfile
from .serializers import (
    ExhibitionSerializer, PropertySerializer,
    ExhibitorProfileSerializer, ExhibitorApplicationSerializer,
    EventRecapSerializer,
)
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404
from rest_framework import status
from exhibitions.utils.tasks import (
    send_event_email, send_exhibitor_approval_email, send_visitor_qr_email,
    send_exhibitor_registration_email, send_exhibitor_booth_assigned_email,
)
from accounts.models import User
from exhibitions.utils.image_tasks import compress_model_image
from django.utils import timezone
from django.db.models import Case, When, Value, IntegerField, Q, Prefetch
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import logging
import stripe

stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')

logger = logging.getLogger(__name__)



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

        import json
        schedules_raw = request.data.get("schedules")
        schedules_list = []
        if schedules_raw:
            try:
                schedules_list = json.loads(schedules_raw) if isinstance(schedules_raw, str) else schedules_raw
                schedules_list = sorted(schedules_list, key=lambda x: x.get("date", ""))
            except Exception as e:
                logger.exception("Failed to parse schedules raw data")

        if schedules_list:
            start_date = schedules_list[0]["date"]
            end_date = schedules_list[-1]["date"]
        else:
            start_date = data["start_date"]
            end_date = data["end_date"]

        exhibition = Exhibition.objects.create(
            name=data["name"],
            description=data["description"],
            start_date=start_date,
            end_date=end_date,
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
            currency_code=data.get("currency_code", "INR"),
            map_image=data.get("map_image"),
        )

        if schedules_list:
            try:
                for sched in schedules_list:
                    ExhibitionSchedule.objects.create(
                        exhibition=exhibition,
                        date=sched["date"],
                        start_time=sched["start_time"],
                        end_time=sched["end_time"],
                    )
            except Exception as e:
                logger.exception("Failed to save schedules for new exhibition %s", exhibition.id)

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

        exhibitions = Exhibition.objects.all().prefetch_related(
            'images', 'price_tiers', 'schedules',
            'recap', 'recap__images', 'recap__videos', 'recap__social_links',
        )

        if query:
            exhibitions = exhibitions.filter(
                Q(name__icontains=query) |
                Q(state__icontains=query) |
                Q(city__icontains=query) |
                Q(country__icontains=query)
            )

        today = timezone.localdate()

        # Calculate counts based on current search query (before status filtering)
        all_count = exhibitions.count()
        ongoing_count = exhibitions.filter(start_date__lte=today, end_date__gte=today).count()
        upcoming_count = exhibitions.filter(start_date__gt=today).count()
        past_count = exhibitions.filter(end_date__lt=today).count()
        active_count = exhibitions.filter(is_active=True).count()
        inactive_count = exhibitions.filter(is_active=False).count()

        counts = {
            "all": all_count,
            "ongoing": ongoing_count,
            "upcoming": upcoming_count,
            "past": past_count,
            "active": active_count,
            "inactive": inactive_count,
        }

        # Apply specific status filtering
        if status_filter == 'ongoing':
            exhibitions = exhibitions.filter(start_date__lte=today, end_date__gte=today).order_by("start_date")
        elif status_filter == 'upcoming':
            exhibitions = exhibitions.filter(start_date__gt=today).order_by("start_date")
        elif status_filter == 'past':
            exhibitions = exhibitions.filter(end_date__lt=today).order_by("-start_date")
        elif status_filter == 'active':
            exhibitions = exhibitions.filter(is_active=True).order_by("-created_at")
        elif status_filter == 'inactive':
            exhibitions = exhibitions.filter(is_active=False).order_by("-created_at")
        else:  # 'all'
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
            "currency_symbol", "currency_code", "venue_link", "location_link"
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

        # ── Schedules (replace all on update) ──
        schedules_raw = request.data.get("schedules")
        if schedules_raw is not None:
            try:
                schedules_list = json.loads(schedules_raw) if isinstance(schedules_raw, str) else schedules_raw
                schedules_list = sorted(schedules_list, key=lambda x: x.get("date", ""))
                
                # Delete existing schedules
                ExhibitionSchedule.objects.filter(exhibition=exhibition).delete()
                
                # Create new schedules
                for sched in schedules_list:
                    ExhibitionSchedule.objects.create(
                        exhibition=exhibition,
                        date=sched["date"],
                        start_time=sched["start_time"],
                        end_time=sched["end_time"],
                    )
                
                # Update exhibition start_date & end_date based on updated schedules
                if schedules_list:
                    exhibition.start_date = schedules_list[0]["date"]
                    exhibition.end_date = schedules_list[-1]["date"]
            except Exception as e:
                logger.exception("Failed to update schedules for exhibition %s", exhibition.id)

        exhibition.save()

        return Response(ExhibitionSerializer(exhibition, context={'request': request}).data)

class AdminDeleteExhibitionView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def delete(self, request, pk):
        Exhibition.objects.filter(pk=pk).delete()
        return Response({"message": "Deleted"})


class AdminToggleExhibitionStatusView(APIView):
    """PATCH endpoint to toggle is_active for a given exhibition."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def patch(self, request, pk):
        exhibition = get_object_or_404(Exhibition, pk=pk)
        exhibition.is_active = not exhibition.is_active
        exhibition.save(update_fields=['is_active'])
        return Response({
            "id": exhibition.id,
            "is_active": exhibition.is_active,
            "message": f"Exhibition {'activated' if exhibition.is_active else 'deactivated'} successfully."
        })


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
            payment_screenshot=request.FILES.get("payment_screenshot"),
            transaction_id=request.data.get("transaction_id"),
        )

        compress_model_image.delay(
            "exhibitions",
            "ExhibitorApplication",
            app.id,
            "payment_screenshot",
        )

        return Response({"message": "Application submitted"})


# ─────────────────────────────────────────────────────────────────────────────
# Stripe: Web Checkout Session
# ─────────────────────────────────────────────────────────────────────────────

class ExhibitorCreateCheckoutSessionView(APIView):
    """
    POST /exhibitions/exhibitor/create-checkout-session/<exhibition_id>/
    Body: { "tier_id": <int> }
    Creates a Stripe Checkout Session and a PENDING ExhibitorApplication.
    Returns { "session_url": "https://checkout.stripe.com/..." }
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsExhibitorWithProfile]

    def post(self, request, exhibition_id):
        user = request.user
        if user.active_role not in ("EXHIBITOR", "ADMIN"):
            return Response({"error": "Only exhibitors can book"}, status=403)

        exhibition = get_object_or_404(Exhibition, id=exhibition_id, is_active=True)

        if exhibition.available_booths <= 0:
            return Response({"error": "No booths available"}, status=400)

        existing_app = ExhibitorApplication.objects.filter(user=user, exhibition=exhibition).first()
        if existing_app:
            if existing_app.status == 'APPROVED':
                return Response({"error": "You have already registered for this event"}, status=400)
            elif existing_app.status == 'PENDING':
                existing_app.delete()

        tier_id = request.data.get("tier_id")
        if not tier_id:
            return Response({"error": "tier_id is required"}, status=400)

        tier = get_object_or_404(ExhibitionPriceTier, id=tier_id, exhibition=exhibition)

        # Create the PENDING application now so we have an ID for metadata
        app = ExhibitorApplication.objects.create(
            user=user,
            exhibition=exhibition,
            selected_tier=tier,
            status="PENDING",
        )

        # Build Stripe Checkout Session
        frontend_base = getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:5173')
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': exhibition.currency_code.lower(),
                        'product_data': {
                            'name': f"{tier.name} – {exhibition.name}",
                            'description': tier.description or f"Exhibitor booth at {exhibition.name}",
                        },
                        'unit_amount': tier.fee * 100,   # Stripe expects cents/paise
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=f"{frontend_base}/exhibitor/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{frontend_base}/exhibitor/payment-cancel",
                metadata={
                    'application_id': str(app.id),
                    'exhibition_id':  str(exhibition.id),
                    'user_id':        str(user.id),
                    'tier_id':        str(tier.id),
                },
                customer_email=user.email,
            )
        except stripe.error.StripeError as e:
            # Rollback the pending application if Stripe fails
            app.delete()
            logger.exception("Stripe checkout session creation failed")
            return Response({"error": str(e.user_message)}, status=502)

        # Store session ID on the application
        app.stripe_session_id = session.id
        app.save(update_fields=['stripe_session_id'])

        return Response({"session_url": session.url}, status=200)


# ─────────────────────────────────────────────────────────────────────────────
# Stripe: Mobile PaymentIntent
# ─────────────────────────────────────────────────────────────────────────────

class ExhibitorCreatePaymentIntentView(APIView):
    """
    POST /exhibitions/exhibitor/create-payment-intent/<exhibition_id>/
    Body: { "tier_id": <int> }
    For mobile SDK (React Native / iOS / Android).
    Returns { "client_secret": "pi_xxx_secret_xxx", "application_id": 42 }
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsExhibitorWithProfile]

    def post(self, request, exhibition_id):
        user = request.user
        if user.active_role not in ("EXHIBITOR", "ADMIN"):
            return Response({"error": "Only exhibitors can book"}, status=403)

        exhibition = get_object_or_404(Exhibition, id=exhibition_id, is_active=True)

        if exhibition.available_booths <= 0:
            return Response({"error": "No booths available"}, status=400)

        existing_app = ExhibitorApplication.objects.filter(user=user, exhibition=exhibition).first()
        if existing_app:
            if existing_app.status == 'APPROVED':
                return Response({"error": "You have already registered for this event"}, status=400)
            elif existing_app.status == 'PENDING':
                existing_app.delete()

        tier_id = request.data.get("tier_id")
        if not tier_id:
            return Response({"error": "tier_id is required"}, status=400)

        tier = get_object_or_404(ExhibitionPriceTier, id=tier_id, exhibition=exhibition)

        app = ExhibitorApplication.objects.create(
            user=user,
            exhibition=exhibition,
            selected_tier=tier,
            status="PENDING",
        )

        try:
            intent = stripe.PaymentIntent.create(
                amount=tier.fee * 100,
                currency=exhibition.currency_code.lower(),
                receipt_email=user.email,
                metadata={
                    'application_id': str(app.id),
                    'exhibition_id':  str(exhibition.id),
                    'user_id':        str(user.id),
                    'tier_id':        str(tier.id),
                },
            )
        except stripe.error.StripeError as e:
            app.delete()
            logger.exception("Stripe PaymentIntent creation failed")
            return Response({"error": str(e.user_message)}, status=502)

        app.stripe_payment_intent = intent.id
        app.save(update_fields=['stripe_payment_intent'])

        return Response({
            "client_secret": intent.client_secret,
            "application_id": app.id,
        }, status=200)


# ─────────────────────────────────────────────────────────────────────────────
# Stripe: Webhook handler (no auth — verified via Stripe signature)
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name='dispatch')
class ExhibitorStripeWebhookView(APIView):
    """
    POST /exhibitions/stripe/webhook/
    Stripe calls this endpoint to confirm payment events.
    """
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        payload    = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
        webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except stripe.error.SignatureVerificationError:
            logger.warning("Stripe webhook signature verification failed")
            return Response({"error": "Invalid signature"}, status=400)
        except Exception as e:
            return Response({"error": str(e)}, status=400)

        event_type = event['type']
        data       = event['data']['object']

        if event_type == 'checkout.session.completed':
            self._handle_checkout_completed(data)

        elif event_type == 'checkout.session.expired':
            self._handle_checkout_expired(data)

        elif event_type == 'payment_intent.succeeded':
            self._handle_payment_intent_succeeded(data)

        elif event_type == 'payment_intent.payment_failed':
            self._handle_payment_intent_failed(data)

        return Response({"status": "ok"})

    def _handle_checkout_completed(self, session):
        session_id = session.id
        try:
            app = ExhibitorApplication.objects.select_related(
                'exhibition', 'user'
            ).get(stripe_session_id=session_id)
        except ExhibitorApplication.DoesNotExist:
            logger.error("Webhook checkout.session.completed: no app for session %s", session_id)
            return

        if app.status == 'APPROVED':
            return  # Idempotent: already processed

        app.status = 'APPROVED'
        app.exhibition.available_booths = max(0, app.exhibition.available_booths - 1)
        app.exhibition.save(update_fields=['available_booths'])
        app.save(update_fields=['status'])

        send_exhibitor_registration_email.delay(app.id)
        logger.info("checkout.session.completed: approved application %s", app.id)

    def _handle_checkout_expired(self, session):
        session_id = session.id
        try:
            app = ExhibitorApplication.objects.get(
                stripe_session_id=session_id, status='PENDING'
            )
            app.delete()
            logger.info("checkout.session.expired: removed pending application for session %s", session_id)
        except ExhibitorApplication.DoesNotExist:
            pass

    def _handle_payment_intent_succeeded(self, intent):
        intent_id = intent.id
        try:
            app = ExhibitorApplication.objects.select_related(
                'exhibition', 'user'
            ).get(stripe_payment_intent=intent_id)
        except ExhibitorApplication.DoesNotExist:
            logger.error("Webhook payment_intent.succeeded: no app for intent %s", intent_id)
            return

        if app.status == 'APPROVED':
            return

        app.status = 'APPROVED'
        app.exhibition.available_booths = max(0, app.exhibition.available_booths - 1)
        app.exhibition.save(update_fields=['available_booths'])
        app.save(update_fields=['status'])

        send_exhibitor_registration_email.delay(app.id)
        logger.info("payment_intent.succeeded: approved application %s", app.id)

    def _handle_payment_intent_failed(self, intent):
        intent_id = intent.id
        try:
            app = ExhibitorApplication.objects.get(
                stripe_payment_intent=intent_id, status='PENDING'
            )
            app.status = 'REJECTED'
            app.save(update_fields=['status'])
            logger.info("payment_intent.payment_failed: rejected application %s", app.id)
        except ExhibitorApplication.DoesNotExist:
            pass


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
        base_query = Exhibition.objects.prefetch_related(
            'images', 'price_tiers', 'schedules',
            'recap', 'recap__images', 'recap__videos', 'recap__social_links',
        ).filter(is_active=True)

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

        apps = ExhibitorApplication.objects.filter(user=user).select_related("exhibition")

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
        regs = VisitorRegistration.objects.filter(user=request.user).select_related("exhibition")

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
            reg = VisitorRegistration.objects.select_related("user", "exhibition").get(qr_code=qr)
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
        props = Property.objects.filter(exhibitor=request.user).prefetch_related("images").order_by("-created_at")
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
        props = Property.objects.filter(exhibitor_id=exhibitor_id).prefetch_related("images").order_by("-created_at")
        return Response(PropertySerializer(props, many=True, context={'request': request}).data)

class PublicExhibitionDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [AllowAny]

    def get(self, request, id):
        # Apply prefetch_related for images to avoid individual query evaluation limits
        query = Exhibition.objects.prefetch_related('images')
        
        # Only show active events to public users, but let admins see all
        if not request.user.is_authenticated or request.user.active_role != 'ADMIN':
            query = query.filter(is_active=True)
            
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
        from django.db.models import Count
        from django.utils import timezone
        from datetime import timedelta
        import calendar

        total_events = Exhibition.objects.count()
        active_events = Exhibition.objects.filter(is_active=True).count()

        unique_visitors = VisitorRegistration.objects.values('user').distinct().count()
        unique_exhibitors = ExhibitorApplication.objects.filter(status='APPROVED').values('user').distinct().count()

        total_registrations = VisitorRegistration.objects.count()
        checked_in = VisitorRegistration.objects.filter(is_checked_in=True).count()
        checkin_rate = round((checked_in / total_registrations * 100), 1) if total_registrations > 0 else 0

        # Per-event breakdown (top 10 by visitor count)
        events_breakdown = []
        events = Exhibition.objects.all().order_by('-created_at')[:10]
        for ev in events:
            v_count = VisitorRegistration.objects.filter(exhibition=ev).count()
            e_count = ExhibitorApplication.objects.filter(exhibition=ev, status='APPROVED').count()
            ci_count = VisitorRegistration.objects.filter(exhibition=ev, is_checked_in=True).count()
            events_breakdown.append({
                'id': ev.id,
                'name': ev.name,
                'visitor_count': v_count,
                'exhibitor_count': e_count,
                'checked_in_count': ci_count,
                'is_active': ev.is_active,
            })

        # Business type distribution
        btype_qs = (
            ExhibitorApplication.objects
            .filter(status='APPROVED')
            .select_related('user__exhibitorprofile')
        )
        btype_counts = {}
        for app in btype_qs:
            profile = getattr(app.user, 'exhibitorprofile', None)
            bt = profile.business_type if profile else 'OTHER_BUSINESSES'
            btype_counts[bt] = btype_counts.get(bt, 0) + 1
        business_type_distribution = [
            {'type': k, 'count': v}
            for k, v in sorted(btype_counts.items(), key=lambda x: -x[1])
        ]

        # Monthly visitor registrations (last 6 months)
        today = timezone.now()
        monthly_registrations = []
        for i in range(5, -1, -1):
            # Calculate year/month for i months ago
            month = today.month - i
            year = today.year
            while month <= 0:
                month += 12
                year -= 1
            month_name = calendar.month_abbr[month]
            count = VisitorRegistration.objects.filter(
                registered_at__year=year,
                registered_at__month=month
            ).count()
            monthly_registrations.append({
                'month': f"{month_name} {year}",
                'count': count,
            })

        return Response({
            "total_events": total_events,
            "active_events": active_events,
            "total_visitors": unique_visitors,
            "total_exhibitors": unique_exhibitors,
            "checkin_rate": checkin_rate,
            "total_checked_in": checked_in,
            "events_breakdown": events_breakdown,
            "business_type_distribution": business_type_distribution,
            "monthly_registrations": monthly_registrations,
        })

from django.db.models import Q

class AdminEventVisitorsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def get(self, request, exhibition_id):
        query = request.query_params.get('search', '')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('limit', 10))
        download = request.query_params.get('download', '').lower() == 'true'

        regs = VisitorRegistration.objects.filter(exhibition_id=exhibition_id).select_related('user')

        if query:
            regs = regs.filter(
                Q(user__username__icontains=query) |
                Q(user__email__icontains=query)
            )

        if download:
            import csv
            from django.http import HttpResponse
            import re
            
            exhibition = Exhibition.objects.get(id=exhibition_id)
            safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', exhibition.name)
            
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="visitors-{safe_name}.csv"'
            
            writer = csv.writer(response)
            writer.writerow(['ID', 'Visitor Name', 'Email', 'Registered At', 'Checked In', 'QR Code'])
            
            for r in regs:
                reg_at = r.registered_at.strftime('%Y-%m-%d %H:%M:%S') if hasattr(r, 'registered_at') and r.registered_at else 'N/A'
                writer.writerow([
                    r.id,
                    r.user.username,
                    r.user.email,
                    reg_at,
                    'Yes' if r.is_checked_in else 'No',
                    str(r.qr_code)
                ])
            return response

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
        download = request.query_params.get('download', '').lower() == 'true'

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

        if download:
            import csv
            from django.http import HttpResponse
            import re
            
            exhibition = Exhibition.objects.get(id=exhibition_id)
            safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', exhibition.name)
            
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="exhibitors-{safe_name}.csv"'
            
            writer = csv.writer(response)
            writer.writerow(['ID', 'Company Name', 'Email', 'Booth Number', 'Contact Number', 'Business Type', 'Council Area'])
            
            for app in apps:
                profile = getattr(app.user, 'exhibitorprofile', None)
                writer.writerow([
                    app.id,
                    profile.company_name if profile else app.user.username,
                    app.user.email,
                    app.booth_number or 'N/A',
                    profile.contact_number if profile else 'N/A',
                    profile.business_type if profile else 'N/A',
                    profile.council_area if profile else 'N/A'
                ])
            return response

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


class AdminUpdateExhibitorInEventView(APIView):
    """
    Admin endpoint to update exhibitor details for a specific event.
    PATCH /exhibitions/admin/exhibitions/<exhibition_id>/exhibitors/<application_id>/update/
    Accepts: booth_number, company_name, contact_number, business_type, council_area
    Also handles optional badge file upload.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def patch(self, request, exhibition_id, application_id):
        app = get_object_or_404(
            ExhibitorApplication,
            id=application_id,
            exhibition_id=exhibition_id,
            status='APPROVED'
        )

        # Update booth number on application
        booth_number      = request.data.get('booth_number')
        was_unassigned    = app.booth_number is None
        if booth_number is not None:
            app.booth_number = booth_number

        # Update badge if a file was explicitly uploaded by admin
        badge_file = request.FILES.get('badge')
        if badge_file:
            app.badge = badge_file

        app.save()

        # Update ExhibitorProfile fields
        profile = getattr(app.user, 'exhibitorprofile', None)
        if profile:
            for field in ['company_name', 'contact_number', 'business_type', 'council_area']:
                val = request.data.get(field)
                if val:
                    setattr(profile, field, val)
            profile.save()

        # Fire booth-assigned email when booth is newly assigned (no manual badge upload needed)
        if booth_number is not None and was_unassigned and not badge_file:
            send_exhibitor_booth_assigned_email.delay(app.id)

        return Response({
            "id": app.id,
            "booth_number": app.booth_number,
            "email": app.user.email,
            "company_name": profile.company_name if profile else app.user.username,
            "contact_number": profile.contact_number if profile else None,
            "business_type": profile.business_type if profile else None,
            "council_area": profile.council_area if profile else None,
            "badge": request.build_absolute_uri(app.badge.url) if app.badge else None,
        })


class AdminDeleteExhibitorInEventView(APIView):
    """
    Admin endpoint to remove an exhibitor from a specific event.
    DELETE /exhibitions/admin/exhibitions/<exhibition_id>/exhibitors/<application_id>/delete/
    Restores available_booths count on the exhibition.
    Does NOT delete the user account or ExhibitorProfile.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def delete(self, request, exhibition_id, application_id):
        app = get_object_or_404(
            ExhibitorApplication,
            id=application_id,
            exhibition_id=exhibition_id
        )

        try:
            exhibition = Exhibition.objects.get(id=exhibition_id)
        except Exhibition.DoesNotExist:
            return Response({'error': 'Exhibition not found'}, status=status.HTTP_404_NOT_FOUND)

        # Restore booth count only if the application was approved
        if app.status == 'APPROVED':
            exhibition.available_booths += 1
            exhibition.save()

        app.delete()

        return Response({'message': 'Exhibitor removed from event successfully'}, status=status.HTTP_200_OK)


class AdminUpdateVisitorInEventView(APIView):
    """
    Admin endpoint to update visitor details for a specific event.
    PATCH /exhibitions/admin/exhibitions/<exhibition_id>/visitors/<registration_id>/update/
    Accepts: name (username), is_checked_in
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def patch(self, request, exhibition_id, registration_id):
        reg = get_object_or_404(
            VisitorRegistration,
            id=registration_id,
            exhibition_id=exhibition_id
        )

        # Update visitor name (stored as username on User model)
        name = request.data.get('name')
        if name:
            reg.user.username = name
            reg.user.save(update_fields=['username'])

        # Allow manually overriding check-in status
        is_checked_in = request.data.get('is_checked_in')
        if is_checked_in is not None:
            reg.is_checked_in = str(is_checked_in).lower() in ('true', '1', 'yes')
            reg.save(update_fields=['is_checked_in'])

        return Response({
            "id": reg.id,
            "name": reg.user.username,
            "email": reg.user.email,
            "is_checked_in": reg.is_checked_in,
            "qr_code": str(reg.qr_code),
            "registered_at": reg.registered_at,
        })


class AdminDeleteVisitorInEventView(APIView):
    """
    Admin endpoint to remove a visitor registration from a specific event.
    DELETE /exhibitions/admin/exhibitions/<exhibition_id>/visitors/<registration_id>/delete/
    Restores available_visitors count on the exhibition.
    Does NOT delete the user account.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUserRole]

    def delete(self, request, exhibition_id, registration_id):
        reg = get_object_or_404(
            VisitorRegistration,
            id=registration_id,
            exhibition_id=exhibition_id
        )

        try:
            exhibition = Exhibition.objects.get(id=exhibition_id)
        except Exhibition.DoesNotExist:
            return Response({'error': 'Exhibition not found'}, status=status.HTTP_404_NOT_FOUND)

        # Restore visitor capacity slot
        exhibition.available_visitors += 1
        exhibition.save()

        reg.delete()

        return Response({'message': 'Visitor removed from event successfully'}, status=status.HTTP_200_OK)
