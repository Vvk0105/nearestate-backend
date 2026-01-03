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
        max_length=50,
        choices=[
            ("DEVELOPER", "Developer"),
            ("BROKER", "Broker"),
            ("LOAN", "Loan Provider"),
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

class ExhibitorApplication(models.Model):
    STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    exhibition = models.ForeignKey("Exhibition", on_delete=models.CASCADE)

    payment_screenshot = models.ImageField(
        upload_to="payments/screenshots/"
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
