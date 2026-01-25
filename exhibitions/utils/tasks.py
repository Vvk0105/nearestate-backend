from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.template.loader import render_to_string
from email.mime.image import MIMEImage
import os

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10}
)
def send_event_email(self, subject, exhibition_data, recipients):
    """
    Send HTML email for event invitation.
    exhibition_data should contain: name, start_date, end_date, venue, city, state, country
    """
    # Render HTML template
    html_content = render_to_string('emails/event_invitation.html', {
        'exhibition_name': exhibition_data.get('name'),
        'start_date': exhibition_data.get('start_date'),
        'end_date': exhibition_data.get('end_date'),
        'venue': exhibition_data.get('venue'),
        'city': exhibition_data.get('city'),
        'state': exhibition_data.get('state'),
        'country': exhibition_data.get('country'),
    })
    
    # Send to each recipient
    for email in recipients:
        msg = EmailMultiAlternatives(
            subject=subject,
            body="Please view this email in an HTML-compatible email client.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
        )
        msg.attach_alternative(html_content, "text/html")
        
        # Embed logo
        logo_path = os.path.join(settings.STATIC_ROOT, 'emails', 'logo.png')
        if os.path.exists(logo_path):
            with open(logo_path, 'rb') as f:
                logo_img = MIMEImage(f.read())
                logo_img.add_header('Content-ID', '<logo>')
                logo_img.add_header('Content-Disposition', 'inline', filename='logo.png')
                msg.attach(logo_img)
        
        msg.send(fail_silently=False)

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
    
    # Render HTML template
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
    
    # Embed logo
    logo_path = os.path.join(settings.STATIC_ROOT, 'emails', 'logo.png')
    if os.path.exists(logo_path):
        with open(logo_path, 'rb') as f:
            logo_img = MIMEImage(f.read())
            logo_img.add_header('Content-ID', '<logo>')
            logo_img.add_header('Content-Disposition', 'inline', filename='logo.png')
            msg.attach(logo_img)
    
    # Attach badge if provided
    if badge_path and os.path.exists(badge_path):
        msg.attach_file(badge_path)
    
    msg.send(fail_silently=False)
