"""
A6 PDF Badge Generator for NearEstate Exhibitors.
A6 size: 105mm × 148mm = 297.6pt × 419.5pt
"""

import io
import os
import qrcode
from qrcode.image.pil import PilImage
from PIL import Image as PILImage
from reportlab.lib.pagesizes import A6
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# ── Brand colours ──────────────────────────────────────────────────────────────
DARK_NAVY   = colors.HexColor('#1a1a2e')
ACCENT_BLUE = colors.HexColor('#1d4ed8')
LIGHT_GRAY  = colors.HexColor('#f4f4f4')
WHITE       = colors.white
GREEN       = colors.HexColor('#16a34a')

PAGE_W, PAGE_H = A6   # 297.6pt × 419.5pt


def _build_qr_bytes(data: str) -> bytes:
    """Return a PNG QR code as raw bytes."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=8,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white', image_factory=PilImage)

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def generate_exhibitor_badge(application) -> bytes:
    """
    Generate an A6 PDF badge for the given ExhibitorApplication.

    Returns badge content as bytes (PDF).
    Also saves the badge file to application.badge and calls application.save().

    Fields used:
        application.user.get_full_name() or username
        application.user.email
        application.exhibition  (Exhibition instance)
        application.booth_number   (may be None → shows "To be assigned")
        application.selected_tier  (may be None)
    """
    user        = application.user
    exhibition  = application.exhibition
    profile     = getattr(user, 'exhibitorprofile', None)

    exhibitor_name   = user.get_full_name() or user.username or user.email
    exhibitor_email  = user.email
    company_name     = profile.company_name if profile else "—"
    booth_number     = str(application.booth_number) if application.booth_number else "To be assigned"
    event_name       = exhibition.name
    event_dates      = f"{exhibition.start_date.strftime('%d %b')} – {exhibition.end_date.strftime('%d %b %Y')}"
    event_venue      = f"{exhibition.venue}, {exhibition.city}"
    tier_name        = application.selected_tier.name if application.selected_tier else ""

    # QR data: application id
    qr_data = str(application.id)

    buf = io.BytesIO()
    c   = canvas.Canvas(buf, pagesize=A6)

    # ── Background ──────────────────────────────────────────────────────────────
    c.setFillColor(WHITE)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    # ── Header band ─────────────────────────────────────────────────────────────
    header_h = 22 * mm
    c.setFillColor(DARK_NAVY)
    c.rect(0, PAGE_H - header_h, PAGE_W, header_h, fill=1, stroke=0)

    c.setFillColor(WHITE)
    c.setFont('Helvetica-Bold', 13)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 12 * mm, 'NearEstate Events')
    c.setFont('Helvetica', 7)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 17 * mm, 'EXHIBITOR BADGE')

    # ── Accent stripe ────────────────────────────────────────────────────────────
    stripe_h = 2 * mm
    c.setFillColor(ACCENT_BLUE)
    c.rect(0, PAGE_H - header_h - stripe_h, PAGE_W, stripe_h, fill=1, stroke=0)

    # ── Event name block ─────────────────────────────────────────────────────────
    y = PAGE_H - header_h - stripe_h - 8 * mm
    c.setFillColor(DARK_NAVY)
    c.setFont('Helvetica-Bold', 9)
    _draw_wrapped(c, event_name, PAGE_W / 2, y, PAGE_W - 10 * mm, 'centre', 'Helvetica-Bold', 9, DARK_NAVY)
    y -= 5 * mm

    c.setFillColor(colors.HexColor('#555555'))
    c.setFont('Helvetica', 7)
    c.drawCentredString(PAGE_W / 2, y, event_dates)
    y -= 4 * mm
    c.drawCentredString(PAGE_W / 2, y, event_venue)
    y -= 7 * mm

    # ── Divider ──────────────────────────────────────────────────────────────────
    _divider(c, y + 3 * mm)
    y -= 2 * mm

    # ── Exhibitor details ────────────────────────────────────────────────────────
    _label_value(c, 'Name',    exhibitor_name,  y);  y -= 6 * mm
    _label_value(c, 'Email',   exhibitor_email, y);  y -= 6 * mm
    _label_value(c, 'Company', company_name,    y);  y -= 6 * mm
    if tier_name:
        _label_value(c, 'Plan', tier_name, y);       y -= 6 * mm

    # ── Divider ──────────────────────────────────────────────────────────────────
    _divider(c, y + 2 * mm)
    y -= 4 * mm

    # ── Booth number ─────────────────────────────────────────────────────────────
    c.setFillColor(colors.HexColor('#444444'))
    c.setFont('Helvetica', 7)
    c.drawCentredString(PAGE_W / 2, y, 'BOOTH NUMBER')
    y -= 5 * mm

    booth_color = ACCENT_BLUE if application.booth_number else colors.HexColor('#999999')
    c.setFillColor(booth_color)
    c.setFont('Helvetica-Bold', 16)
    c.drawCentredString(PAGE_W / 2, y, booth_number)
    y -= 9 * mm

    # ── QR code ──────────────────────────────────────────────────────────────────
    qr_bytes = _build_qr_bytes(qr_data)
    qr_img   = PILImage.open(io.BytesIO(qr_bytes))
    qr_tmp   = io.BytesIO()
    qr_img.save(qr_tmp, format='PNG')
    qr_tmp.seek(0)

    qr_size = 22 * mm
    qr_x    = (PAGE_W - qr_size) / 2
    qr_y    = y - qr_size

    from reportlab.lib.utils import ImageReader
    c.drawImage(ImageReader(qr_tmp), qr_x, qr_y, width=qr_size, height=qr_size)
    y = qr_y - 4 * mm

    # ── Footer ───────────────────────────────────────────────────────────────────
    footer_h = 8 * mm
    c.setFillColor(LIGHT_GRAY)
    c.rect(0, 0, PAGE_W, footer_h, fill=1, stroke=0)
    c.setFillColor(colors.HexColor('#888888'))
    c.setFont('Helvetica', 6)
    c.drawCentredString(PAGE_W / 2, 3 * mm, 'nearestate.com  |  This badge must be presented at the event entrance')

    c.save()
    pdf_bytes = buf.getvalue()

    # ── Persist to application.badge ─────────────────────────────────────────────
    _save_badge_to_application(application, pdf_bytes)

    return pdf_bytes


# ── Helpers ────────────────────────────────────────────────────────────────────

def _label_value(c, label, value, y):
    margin = 8 * mm
    c.setFillColor(colors.HexColor('#888888'))
    c.setFont('Helvetica', 6.5)
    c.drawString(margin, y, label.upper() + ':')

    c.setFillColor(DARK_NAVY)
    c.setFont('Helvetica-Bold', 7.5)
    # Truncate long values
    max_chars = 38
    if len(value) > max_chars:
        value = value[:max_chars - 1] + '…'
    c.drawString(margin + 20 * mm, y, value)


def _divider(c, y):
    margin = 8 * mm
    c.setStrokeColor(colors.HexColor('#e0e0e0'))
    c.setLineWidth(0.5)
    c.line(margin, y, PAGE_W - margin, y)


def _draw_wrapped(c, text, x, y, max_width, align, font, size, color):
    """Very simple single-line truncating draw (wrapping not needed for event names at this size)."""
    c.setFont(font, size)
    c.setFillColor(color)
    if align == 'centre':
        c.drawCentredString(x, y, text)
    else:
        c.drawString(x, y, text)


def _save_badge_to_application(application, pdf_bytes: bytes):
    """Save PDF bytes to the application.badge FileField."""
    from django.core.files.base import ContentFile
    filename = f"badge_{application.id}.pdf"
    application.badge.save(filename, ContentFile(pdf_bytes), save=True)
    logger.info("Badge saved for application %s → %s", application.id, filename)
