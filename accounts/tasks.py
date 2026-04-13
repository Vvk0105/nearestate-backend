from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
)
def send_otp_email_task(self, email, otp):
    """
    ✅ CRITICAL: OTP email must ALWAYS be sent via Celery, never inline in a request.

    Calling send_mail() directly in a Django view blocks the Gunicorn worker thread
    for the entire duration of the SMTP connection. If the SMTP server is slow or
    unresponsive, the worker never returns — and after a few days all workers are
    permanently stuck, causing 504 timeouts on every endpoint.

    Moving it here means Celery handles the blocking I/O, and Gunicorn workers
    are freed immediately to handle the next request.
    """
    try:
        send_mail(
            subject="Your NearEstate Login OTP",
            message=f"Your OTP is {otp}. It is valid for 5 minutes.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
        logger.info(f"OTP email sent successfully to {email}")
    except Exception as exc:
        logger.error(f"Failed to send OTP email to {email}: {exc}")
        raise  # Celery will retry automatically (max 3 times)
