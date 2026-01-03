from celery import shared_task
from django.core.mail import send_mass_mail, EmailMessage
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

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
)
def send_exhibitor_approval_email(
    self,
    email,
    exhibitor_name,
    exhibition_name,
    booth_number,
    badge_path=None,
):
    subject = f"Exhibitor Approved – {exhibition_name}"

    body = f"""
Hello {exhibitor_name},

Your exhibitor application has been APPROVED.

Event: {exhibition_name}
Booth Number: {booth_number}

Please find your badge attached (if provided).

Regards,
NearEstate Team
"""

    mail = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )

    if badge_path:
        mail.attach_file(badge_path)

    mail.send(fail_silently=False)