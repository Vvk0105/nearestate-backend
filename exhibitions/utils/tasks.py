from celery import shared_task
from django.core.mail import send_mass_mail
from django.conf import settings

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10}
)
def send_event_email(self, subject, message, recipients):
    emails = [
        (subject, message, settings.DEFAULT_FROM_EMAIL, [email])
        for email in recipients
    ]
    send_mass_mail(emails, fail_silently=False)
