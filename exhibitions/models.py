from django.db import models
from accounts.models import User

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
