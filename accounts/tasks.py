from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

SOCIAL_FOOTER_HTML = """
<div style="background:#f7f7f7;padding:32px 24px 28px;text-align:center;font-family:Arial,sans-serif;border-top:1px solid #e8e8e8;">
  <p style="color:#888888;font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;margin:0 0 16px;">Follow us on</p>
  <div style="margin-bottom:28px;">
    <a href="https://www.facebook.com/NearEstatecom" style="display:inline-block;margin:0 6px;text-decoration:none;" title="Follow NearEstate on Facebook" target="_blank">
      <img src="https://img.icons8.com/color/48/facebook-new.png" width="44" height="44" alt="Facebook" style="display:inline-block;border:0;" />
    </a>
    <a href="https://www.instagram.com/nearestate/" style="display:inline-block;margin:0 6px;text-decoration:none;" title="Follow NearEstate on Instagram" target="_blank">
      <img src="https://img.icons8.com/color/48/instagram-new.png" width="44" height="44" alt="Instagram" style="display:inline-block;border:0;" />
    </a>
    <a href="https://www.linkedin.com/company/nearestate-com/" style="display:inline-block;margin:0 6px;text-decoration:none;" title="Follow NearEstate.com on LinkedIn" target="_blank">
      <img src="https://img.icons8.com/color/48/linkedin.png" width="44" height="44" alt="LinkedIn" style="display:inline-block;border:0;" />
    </a>
  </div>
  <p style="color:#888888;font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;margin:0 0 16px;">Download Our App</p>
  <div style="margin-bottom:24px;">
    <a href="https://play.google.com/store/apps/details?id=com.nearestate.events" style="display:inline-block;margin:4px 8px;text-decoration:none;" title="Get NearEstate on Google Play" target="_blank">
      <img src="https://play.google.com/intl/en_us/badges/static/images/badges/en_badge_web_generic.png" height="52" alt="Get it on Google Play" style="display:inline-block;border:0;" />
    </a>
    <a href="https://apps.apple.com/au/app/near-estate/id6760655554" style="display:inline-block;margin:4px 8px;text-decoration:none;" title="Download Near Estate on the App Store" target="_blank">
      <img src="https://tools.applemediaservices.com/api/badges/download-on-the-app-store/black/en-us?size=250x83" height="52" alt="Download on the App Store" style="display:inline-block;border:0;" />
    </a>
  </div>
  <hr style="border:none;border-top:1px solid #e0e0e0;margin:16px auto;width:80%;" />
  <p style="color:#666666;font-size:12px;line-height:1.8;margin:0 0 8px;">
    Need assistance? Contact <a href="mailto:info@nearestate.com" style="color:#1d4ed8;text-decoration:none;">info@nearestate.com</a> or call <a href="tel:+61426535177" style="color:#1d4ed8;text-decoration:none;">+61 426 535 177</a>.<br/>
    <a href="https://nearestate.com/" style="color:#1d4ed8;font-weight:700;text-decoration:none;">NearEstate.com</a> &nbsp;|&nbsp; Pakenham, Victoria 3810, Australia
  </p>
  <p style="color:#aaaaaa;font-size:11px;margin:8px 0 0;">&#169; NearEstate &#8212; This is an automated message, please do not reply.</p>
</div>
"""


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
        text_body = (
            f"Your NearEstate OTP is {otp}. It is valid for 5 minutes.\n\n"
            "Need help? Contact info@nearestate.com or call +61 426 535 177.\n"
            "NearEstate.com | Pakenham, Victoria 3810, Australia"
        )
        html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Your NearEstate Login OTP</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Arial,sans-serif;color:#1e293b;">
  <div style="max-width:520px;margin:40px auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
    <div style="background:linear-gradient(135deg,#1d4ed8 0%,#4f46e5 100%);padding:32px;text-align:center;">
      <h1 style="color:#fff;font-size:22px;margin:0 0 6px;font-weight:700;">&#128272; Your Login OTP</h1>
      <p style="color:rgba(255,255,255,0.82);font-size:14px;margin:0;">NearEstate Account Verification</p>
    </div>
    <div style="padding:36px 32px;">
      <p style="font-size:15px;color:#374151;margin-bottom:20px;">
        Use the one-time password below to complete your login. It expires in <strong>5 minutes</strong>.
      </p>
      <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:24px;text-align:center;margin-bottom:28px;">
        <p style="font-size:36px;font-weight:800;letter-spacing:10px;color:#1d4ed8;margin:0;">{otp}</p>
      </div>
      <div style="background:#eff6ff;border-left:4px solid #3b82f6;border-radius:0 8px 8px 0;padding:14px 16px;font-size:13px;color:#1d4ed8;">
        &#128274; Never share this OTP with anyone. NearEstate staff will never ask for it.
      </div>
    </div>
    {SOCIAL_FOOTER_HTML}
  </div>
</body>
</html>"""

        msg = EmailMultiAlternatives(
            subject="Your NearEstate Login OTP",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"OTP email sent successfully to {email}")
    except Exception as exc:
        logger.error(f"Failed to send OTP email to {email}: {exc}")
        raise  # Celery will retry automatically (max 3 times)
