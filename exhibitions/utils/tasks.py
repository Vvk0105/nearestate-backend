from celery import shared_task
from django.core.mail import EmailMultiAlternatives, get_connection
from django.conf import settings
from django.template.loader import render_to_string
from email.mime.image import MIMEImage
import os
from django.utils import timezone
from datetime import date
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Feature 3 — Optimised bulk send helper
# ---------------------------------------------------------------------------

def _build_event_invitation_messages(subject, exhibition_data, recipients):
    """
    Build a list of EmailMultiAlternatives objects for event invitations.
    Rendering is done once; one Message object per recipient is created
    so the To: field is personalised, but all share the same connection.
    """
    html_content = render_to_string('emails/event_invitation.html', {
        'exhibition_name': exhibition_data.get('name'),
        'start_date': exhibition_data.get('start_date'),
        'end_date': exhibition_data.get('end_date'),
        'venue': exhibition_data.get('venue'),
        'city': exhibition_data.get('city'),
        'state': exhibition_data.get('state'),
        'country': exhibition_data.get('country'),
    })

    # Pre-load logo once (shared across all messages)
    logo_path = os.path.join(settings.STATIC_ROOT, 'emails', 'logo.png')
    logo_bytes = None
    if os.path.exists(logo_path):
        with open(logo_path, 'rb') as f:
            logo_bytes = f.read()

    messages = []
    for email in recipients:
        msg = EmailMultiAlternatives(
            subject=subject,
            body="Please view this email in an HTML-compatible email client.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
        )
        msg.attach_alternative(html_content, "text/html")

        if logo_bytes:
            logo_img = MIMEImage(logo_bytes)
            logo_img.add_header('Content-ID', '<logo>')
            logo_img.add_header('Content-Disposition', 'inline', filename='logo.png')
            msg.attach(logo_img)

        messages.append(msg)

    return messages


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10}
)
def send_event_email(self, subject, exhibition_data, recipients):
    """
    Send HTML event-invitation emails to all recipients using a single
    SMTP connection (chunked in batches of 50).

    Before: 100 emails = 100 separate SMTP connect/auth/send/disconnect cycles.
    After : 100 emails = 2 batches of 50 over ONE persistent connection.
    """
    if not recipients:
        return "No recipients — skipping."

    messages = _build_event_invitation_messages(subject, exhibition_data, recipients)

    BATCH_SIZE = 50
    sent_total = 0

    connection = get_connection(backend=settings.EMAIL_BACKEND)
    try:
        connection.open()
        for i in range(0, len(messages), BATCH_SIZE):
            batch = messages[i:i + BATCH_SIZE]
            sent_total += connection.send_messages(batch)
    finally:
        connection.close()

    logger.info("send_event_email: sent %d/%d invitation(s).", sent_total, len(messages))
    return f"Sent {sent_total} of {len(messages)} emails."


# ---------------------------------------------------------------------------
# Exhibitor approval email (unchanged logic, kept as-is)
# ---------------------------------------------------------------------------

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
    subject = f"Exhibitor Participation Confirmed – {exhibition_name}"

    html_content = render_to_string('emails/exhibitor_approval.html', {
        'exhibitor_name': exhibitor_name,
        'exhibition_name': exhibition_name,
        'booth_number': booth_number,
    })

    msg = EmailMultiAlternatives(
        subject=subject,
        body="Please view this email in an HTML-compatible email client.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    msg.attach_alternative(html_content, "text/html")

    # Attach badge PDF/image if provided
    if badge_path and os.path.exists(badge_path):
        msg.attach_file(badge_path)

    msg.send(fail_silently=False)


# ---------------------------------------------------------------------------
# Feature 2 — Visitor QR Code email
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
)
def send_visitor_qr_email(
    self,
    email,
    visitor_name,
    exhibition_name,
    exhibition_venue,
    exhibition_city,
    start_date,
    end_date,
    qr_code_uuid,
):
    """
    Generate a QR code image in-memory and send a registration confirmation
    email to the visitor with the QR embedded inline.
    """
    subject = f"Your Entry Pass – {exhibition_name}"

    # ---- Generate QR image in memory ----
    qr_image_bytes = None
    try:
        import qrcode
        from io import BytesIO

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_code_uuid)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = BytesIO()
        img.save(buf, format="PNG")
        qr_image_bytes = buf.getvalue()
    except ImportError:
        logger.warning(
            "send_visitor_qr_email: 'qrcode' package not installed. "
            "Email will be sent without embedded QR image."
        )

    # ---- Render HTML template ----
    html_content = render_to_string('emails/visitor_registration.html', {
        'visitor_name': visitor_name,
        'exhibition_name': exhibition_name,
        'exhibition_venue': exhibition_venue,
        'exhibition_city': exhibition_city,
        'start_date': start_date,
        'end_date': end_date,
        'qr_code_uuid': qr_code_uuid,
        'has_qr_image': qr_image_bytes is not None,
    })

    # ---- Build message ----
    msg = EmailMultiAlternatives(
        subject=subject,
        body=(
            f"Hello {visitor_name},\n\n"
            f"You are registered for {exhibition_name}.\n"
            f"Your QR code: {qr_code_uuid}\n\n"
            f"Show this code at the entrance.\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    msg.mixed_subtype = 'related'  # allows inline image embedding
    msg.attach_alternative(html_content, "text/html")

    # Embed QR image inline
    if qr_image_bytes:
        qr_img = MIMEImage(qr_image_bytes, _subtype="png")
        qr_img.add_header('Content-ID', '<qrcode>')
        qr_img.add_header('Content-Disposition', 'inline', filename='entry_pass.png')
        msg.attach(qr_img)

    msg.send(fail_silently=False)
    logger.info("send_visitor_qr_email: sent QR pass to %s for %s.", email, exhibition_name)


# ---------------------------------------------------------------------------
# Periodic task — deactivate expired events (unchanged)
# ---------------------------------------------------------------------------

@shared_task
def deactivate_expired_events():
    """
    Deactivate events where the end_date has passed.
    This task should be run periodically (e.g., daily) via Celery Beat.
    """
    from exhibitions.models import Exhibition

    today = date.today()

    expired_events = Exhibition.objects.filter(
        is_active=True,
        end_date__lt=today
    )

    count = expired_events.count()

    if count > 0:
        event_names = list(expired_events.values_list('name', flat=True))
        expired_events.update(is_active=False)
        logger.info(f"Deactivated {count} expired event(s): {', '.join(event_names)}")
        return f"Successfully deactivated {count} event(s)"
    else:
        logger.info("No expired events found to deactivate")
        return "No expired events to deactivate"
