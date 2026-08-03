from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

SOCIAL_FOOTER_HTML = """
<div style="background:#1e293b;padding:32px 24px 24px;text-align:center;font-family:Arial,sans-serif;">
  <p style="color:#94a3b8;font-size:11px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;margin:0 0 14px;">Follow us on</p>
  <div style="display:inline-block;margin-bottom:24px;">
    <a href="https://www.facebook.com/NearEstatecom" style="display:inline-block;margin:0 8px;text-decoration:none;" title="Follow NearEstate on Facebook" target="_blank">
      <span style="display:inline-block;width:42px;height:42px;border-radius:50%;background:#1877F2;text-align:center;line-height:42px;vertical-align:middle;">
        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="#fff" style="vertical-align:middle;margin-top:-1px;"><path d="M22 12c0-5.52-4.48-10-10-10S2 6.48 2 12c0 4.84 3.44 8.87 8 9.8V15H8v-3h2V9.5C10 7.57 11.57 6 13.5 6H16v3h-2c-.55 0-1 .45-1 1v2h3l-.5 3H13v6.8c4.56-.93 8-4.96 8-9.8z"/></svg>
      </span>
    </a>
    <a href="https://www.instagram.com/nearestate/" style="display:inline-block;margin:0 8px;text-decoration:none;" title="Follow NearEstate on Instagram" target="_blank">
      <span style="display:inline-block;width:42px;height:42px;border-radius:50%;background:linear-gradient(45deg,#f09433,#e6683c,#dc2743,#cc2366,#bc1888);text-align:center;line-height:42px;vertical-align:middle;">
        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="#fff" style="vertical-align:middle;margin-top:-1px;"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 1.366.062 2.633.336 3.608 1.311.975.975 1.249 2.242 1.311 3.608.058 1.266.07 1.646.07 4.85s-.012 3.584-.07 4.85c-.062 1.366-.336 2.633-1.311 3.608-.975.975-2.242 1.249-3.608 1.311-1.266.058-1.646.07-4.85.07s-3.584-.012-4.85-.07c-1.366-.062-2.633-.336-3.608-1.311-.975-.975-1.249-2.242-1.311-3.608C2.175 15.584 2.163 15.204 2.163 12s.012-3.584.07-4.85c.062-1.366.336-2.633 1.311-3.608.975-.975 2.242-1.249 3.608-1.311C8.416 2.175 8.796 2.163 12 2.163zm0-2.163C8.741 0 8.332.014 7.052.072 5.197.157 3.355.673 2.014 2.014.673 3.355.157 5.197.072 7.052.014 8.332 0 8.741 0 12c0 3.259.014 3.668.072 4.948.085 1.855.601 3.697 1.942 5.038 1.341 1.341 3.183 1.857 5.038 1.942C8.332 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 1.855-.085 3.697-.601 5.038-1.942 1.341-1.341 1.857-3.183 1.942-5.038.058-1.28.072-1.689.072-4.948 0-3.259-.014-3.668-.072-4.948-.085-1.855-.601-3.697-1.942-5.038C20.645.673 18.803.157 16.948.072 15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 1 0 0 12.324 6.162 6.162 0 0 0 0-12.324zm0 10.162a4 4 0 1 1 0-8 4 4 0 0 1 0 8zm6.406-11.845a1.44 1.44 0 1 0 0 2.881 1.44 1.44 0 0 0 0-2.881z"/></svg>
      </span>
    </a>
    <a href="https://www.linkedin.com/company/nearestate-com/" style="display:inline-block;margin:0 8px;text-decoration:none;" title="Follow NearEstate.com on LinkedIn" target="_blank">
      <span style="display:inline-block;width:42px;height:42px;border-radius:50%;background:#0A66C2;text-align:center;line-height:42px;vertical-align:middle;">
        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="#fff" style="vertical-align:middle;margin-top:-1px;"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
      </span>
    </a>
  </div>
  <p style="color:#94a3b8;font-size:11px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;margin:0 0 14px;">Download Our App</p>
  <div style="margin-bottom:20px;">
    <a href="https://play.google.com/store/apps/details?id=com.nearestate.events" style="display:inline-block;margin:4px 6px;text-decoration:none;background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px 16px;color:#f8fafc;font-size:13px;font-weight:600;vertical-align:middle;" title="Get NearEstate on Google Play" target="_blank">
      <span style="display:block;font-size:10px;font-weight:400;color:#94a3b8;text-transform:uppercase;letter-spacing:0.6px;">Get it on</span>&#9654; Google Play
    </a>
    <a href="https://apps.apple.com/au/app/near-estate/id6760655554" style="display:inline-block;margin:4px 6px;text-decoration:none;background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px 16px;color:#f8fafc;font-size:13px;font-weight:600;vertical-align:middle;" title="Download Near Estate on the App Store" target="_blank">
      <span style="display:block;font-size:10px;font-weight:400;color:#94a3b8;text-transform:uppercase;letter-spacing:0.6px;">Download on the</span> App Store
    </a>
  </div>
  <hr style="border:none;border-top:1px solid #334155;margin:16px auto;width:80%;" />
  <p style="color:#64748b;font-size:12px;line-height:1.7;margin-bottom:12px;">
    Need assistance? Contact <a href="mailto:info@nearestate.com" style="color:#60a5fa;text-decoration:none;">info@nearestate.com</a> or call <a href="tel:+61426535177" style="color:#60a5fa;text-decoration:none;">+61 426 535 177</a>.<br/>
    <a href="https://nearestate.com/" style="color:#60a5fa;font-weight:600;text-decoration:none;">NearEstate.com</a> &nbsp;|&nbsp; Pakenham, Victoria 3810, Australia
  </p>
  <p style="color:#475569;font-size:11px;">&#169; NearEstate &#8212; This is an automated message, please do not reply.</p>
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
