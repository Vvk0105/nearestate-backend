from django.db import models
from accounts.models import User
from django.db import models
from django.conf import settings
import uuid

User = settings.AUTH_USER_MODEL

class ExhibitorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    company_name = models.CharField(max_length=255)
    council_area = models.CharField(max_length=255)
    business_type = models.CharField(
        max_length=60,
        choices=[
            ("DEVELOPER", "Real Estate Developer"),
            ("BROKER", "Real Estate Agent / Broker"),
            ("LOAN", "Mortgage / Loan Provider"),
            ("PROPERTY_REAL_ESTATE", "Property & Real Estate"),
            ("BUILDERS_CONSTRUCTION", "Builders & Construction"),
            ("TRADES_CONTRACTORS", "Trades & Contractors"),
            ("ARCHITECTURE_DESIGN_ENGINEERING", "Architecture, Design & Engineering"),
            ("FINANCE_BANKING", "Finance & Banking"),
            ("LEGAL_COMPLIANCE", "Legal & Compliance"),
            ("INSPECTION_CERTIFICATION", "Inspection & Certification"),
            ("PROPERTY_SERVICES", "Property Services"),
            ("TECHNOLOGY_PROPTECH", "Technology & PropTech"),
            ("FURNITURE_FITOUT_LIFESTYLE", "Furniture, Fitout & Lifestyle"),
            ("GOVERNMENT_COMMUNITY", "Government & Community"),
            ("EDUCATION_MEDIA", "Education & Media"),
            ("TELECOM_INFRASTRUCTURE", "Telecom & Infrastructure"),
            ("RETAIL_MISCELLANEOUS", "Retail & Miscellaneous"),
            ("HOSPITALITY_CATERING", "Hospitality & Catering"),
            ("HEALTH_WELLNESS", "Health & Wellness"),
            ("SUSTAINABILITY_ENERGY", "Sustainability & Energy"),
            ("TRANSPORT_LOGISTICS", "Transport & Logistics"),
            ("RECRUITMENT_HR", "Recruitment & HR"),
            ("MARKETING_ADVERTISING", "Marketing & Advertising"),
            ("EVENTS_ENTERTAINMENT", "Events & Entertainment"),
            ("SECURITY_SAFETY", "Security & Safety"),
            ("MANUFACTURING_INDUSTRIAL", "Manufacturing & Industrial"),
            ("INVESTMENT_WEALTH_MANAGEMENT", "Investment & Wealth Management"),
            ("TRAINING_PROFESSIONAL_DEVELOPMENT", "Training & Professional Development"),
            ("HOME_LIVING", "Home & Living"),
            ("OTHER_BUSINESSES", "Other Businesses"),
        ],
    )
    contact_number = models.CharField(max_length=15)

    def __str__(self):
        return self.company_name

class Exhibition(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField()

    venue = models.CharField(max_length=255)
    venue_link = models.URLField(max_length=500, blank=True, null=True, help_text="Optional link to the venue website or event page")
    location_link = models.URLField(max_length=500, blank=True, null=True, help_text="Optional Google Maps or location link for the venue")
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100)

    booth_capacity = models.PositiveIntegerField()
    visitor_capacity = models.PositiveIntegerField()

    available_booths = models.PositiveIntegerField()
    available_visitors = models.PositiveIntegerField()

    map_image = models.ImageField(upload_to="exhibitions/maps/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    registration_fee = models.PositiveIntegerField(blank=True, null=True)
    currency_symbol = models.CharField(max_length=10, default='₹')
    payment_details = models.TextField(
        blank=True,
        null=True,
        help_text="Free-text payment instructions shown to exhibitors (e.g. Account No, IFSC, IBAN, SWIFT)"
    )

    def save(self, *args, **kwargs):
        if not self.pk:
            self.available_booths = self.booth_capacity
            self.available_visitors = self.visitor_capacity
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ExhibitionImage(models.Model):
    exhibition = models.ForeignKey(
        Exhibition, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="exhibitions/images/")

class ExhibitionSchedule(models.Model):
    exhibition = models.ForeignKey(
        Exhibition, on_delete=models.CASCADE, related_name="schedules"
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.exhibition.name} - {self.date}: {self.start_time} to {self.end_time}"

class ExhibitorApplication(models.Model):
    STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    exhibition = models.ForeignKey("Exhibition", on_delete=models.CASCADE)

    payment_screenshot = models.ImageField(
        upload_to="payments/screenshots/",
        blank=True,
        null=True,
    )
    transaction_id = models.CharField(
        max_length=100, blank=True, null=True
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="PENDING"
    )

    booth_number = models.PositiveIntegerField(
        blank=True, null=True
    )
    badge = models.FileField(
        upload_to="exhibitors/badges/", blank=True, null=True
    )

    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "exhibition")

    def __str__(self):
        return f"{self.user} - {self.exhibition}"

class VisitorRegistration(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    exhibition = models.ForeignKey("Exhibition", on_delete=models.CASCADE)

    qr_code = models.UUIDField(default=uuid.uuid4, unique=True)
    is_checked_in = models.BooleanField(default=False)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "exhibition")

    def __str__(self):
        return f"{self.user} - {self.exhibition}"

class Property(models.Model):
    exhibitor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    exhibition = models.ForeignKey(
        Exhibition,
        on_delete=models.CASCADE
    )

    title = models.CharField(max_length=255)
    location = models.CharField(max_length=255)

    price_from = models.PositiveIntegerField()
    price_to = models.PositiveIntegerField()

    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class PropertyImage(models.Model):
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="images"
    )
    image = models.ImageField(upload_to="properties/")


# ─────────────────────────────────────────────
# Event Recap (for past events)
# ─────────────────────────────────────────────

class EventRecap(models.Model):
    """One recap per exhibition, created after the event ends."""
    exhibition = models.OneToOneField(
        Exhibition, on_delete=models.CASCADE, related_name="recap"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Recap: {self.exhibition.name}"


class RecapImage(models.Model):
    recap = models.ForeignKey(EventRecap, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="recap/images/")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Image #{self.order} – {self.recap}"


class RecapVideo(models.Model):
    recap = models.ForeignKey(EventRecap, on_delete=models.CASCADE, related_name="videos")
    youtube_url = models.URLField(max_length=500)
    title = models.CharField(max_length=255, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.title or self.youtube_url


class RecapSocialLink(models.Model):
    recap = models.ForeignKey(EventRecap, on_delete=models.CASCADE, related_name="social_links")
    title = models.CharField(max_length=100)   # e.g. "Instagram", "Facebook"
    url = models.URLField(max_length=500)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.title} – {self.url}"


# ─────────────────────────────────────────────
# Multiple Pricing Tiers (per exhibition)
# ─────────────────────────────────────────────

class ExhibitionPriceTier(models.Model):
    """Named pricing tier for an exhibition (e.g. Standard, Premium)."""
    exhibition = models.ForeignKey(
        Exhibition, on_delete=models.CASCADE, related_name="price_tiers"
    )
    name = models.CharField(max_length=100)          # e.g. "Standard", "Premium"
    fee = models.PositiveIntegerField()
    description = models.CharField(max_length=255, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.name} – {self.fee}"

