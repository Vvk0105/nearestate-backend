from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import uuid

class User(AbstractUser):
    email = models.EmailField(unique=True)

    roles = models.JSONField(default=list)  
    active_role = models.CharField(
        max_length=20,
        choices=[
            ("ADMIN", "Admin"),
            ("EXHIBITOR", "Exhibitor"),
            ("VISITOR", "Visitor"),
        ],
        blank=True,
        null=True
    )
    profile_completed = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]



class EmailOTP(models.Model):
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(minutes=5)
