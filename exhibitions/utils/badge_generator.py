"""
A4 PDF Badge Generator for NearEstate Exhibitors.
Produces a print-ready A4 document with 4 panels (2×2 grid):

  ┌────────────────┬────────────────┐
  │  TOP-LEFT      │  TOP-RIGHT     │  ← Printed UPSIDE-DOWN (back face when folded)
  │  [Badge]       │  [Details]     │
  ├────────────────┼────────────────┤  ← FOLD 1: A4 → A5 (horizontal)
  │  BOTTOM-LEFT   │  BOTTOM-RIGHT  │  ← Normal orientation (front face when folded)
  │  [Check-in]    │  [Confirmed]   │
  └────────────────┴────────────────┘
           │
           └── FOLD 2: A5 → A6 (vertical)

When folded:
  Front cover = BOTTOM-RIGHT (dark navy "Registration Confirmed")
  Back cover  = TOP-LEFT     (Badge panel - person name, company, event)
  Inside L    = BOTTOM-LEFT  (Event & Check-in)
  Inside R    = TOP-RIGHT    (Exhibitor Details form)
"""

import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# ── Brand colours ──────────────────────────────────────────────────────────────
DARK_NAVY    = colors.HexColor('#0f1f3d')
ORANGE       = colors.HexColor('#F47B20')
LIGHT_GRAY   = colors.HexColor('#f4f6f8')
MID_GRAY     = colors.HexColor('#6b7280')
BORDER_GRAY  = colors.HexColor('#e5e7eb')
WHITE        = colors.white

# A4 dimensions
PAGE_W, PAGE_H = A4           # 595.3pt × 841.9pt
PANEL_W = PAGE_W / 2          # one column
PANEL_H = PAGE_H / 2          # one row

MARGIN = 8 * mm


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def generate_exhibitor_badge(application) -> bytes:
    """
    Generate an A4 4-panel PDF badge for the given ExhibitorApplication.
    Saves to application.badge and returns raw PDF bytes.
    """
    user       = application.user
    exhibition = application.exhibition
    profile    = getattr(user, 'exhibitorprofile', None)

    # ── Data extraction ───────────────────────────────────────────────────────
    person_name  = user.get_full_name() or user.username or user.email
    company_name = profile.company_name if profile else ""
    email        = user.email
    website      = profile.website or "" if profile else ""  # from ExhibitorProfile
    job_title    = ""                    # add later when field exists
    booth_number = str(application.booth_number) if application.booth_number else ""
    package      = application.selected_tier.name.upper() if application.selected_tier else ""
    booking_ref  = application.booking_ref or f"NE-{exhibition.id:04d}-{application.id:04d}"

    event_name   = exhibition.name.upper()
    start_date   = exhibition.start_date
    # date string e.g. "SATURDAY\n19 SEP 2026"
    day_name     = start_date.strftime('%A').upper()
    date_str     = start_date.strftime('%d %b %Y').upper()

    # Times from first schedule if available
    schedules = exhibition.schedules.all().order_by('date')
    if schedules.exists():
        sched = schedules.first()
        start_t = sched.start_time.strftime('%I:%M %p').lstrip('0')
        end_t   = sched.end_time.strftime('%I:%M %p').lstrip('0')
        time_str    = f"{start_t} - {end_t}"
        checkin_str = f"from {start_t}"  # check-in time = event start time
    else:
        time_str    = ""
        checkin_str = ""

    venue_name   = exhibition.venue
    venue_city   = f"{exhibition.city}, {exhibition.state}" if exhibition.state else exhibition.city

    # ── Draw ──────────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    c   = canvas.Canvas(buf, pagesize=A4)

    _draw_bottom_right_confirmed(c, person_name, company_name, event_name)
    _draw_bottom_left_checkin(c, day_name, date_str, time_str, venue_name, venue_city, checkin_str)
    _draw_top_left_badge(c, person_name, company_name, job_title, event_name, date_str)
    _draw_top_right_details(c, company_name, person_name, email, website, package, booking_ref)
    _draw_fold_lines(c)

    c.save()
    pdf_bytes = buf.getvalue()

    _save_badge_to_application(application, pdf_bytes)
    return pdf_bytes


# ─────────────────────────────────────────────────────────────────────────────
# PANEL 1 — BOTTOM-RIGHT: "Registration Confirmed" (FRONT COVER when folded)
# Origin: (PANEL_W, 0)
# ─────────────────────────────────────────────────────────────────────────────

def _draw_bottom_right_confirmed(c, person_name, company_name, event_name):
    ox, oy = PANEL_W, 0  # panel origin

    # Dark navy background
    c.setFillColor(DARK_NAVY)
    c.rect(ox, oy, PANEL_W, PANEL_H, fill=1, stroke=0)

    # NE logo square
    sq = 9 * mm
    c.setFillColor(ORANGE)
    c.roundRect(ox + MARGIN, oy + PANEL_H - MARGIN - sq, sq, sq, 2, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont('Helvetica-Bold', 8)
    c.drawCentredString(ox + MARGIN + sq / 2, oy + PANEL_H - MARGIN - sq + 2.5 * mm, 'NE')

    y = oy + PANEL_H - MARGIN - sq - 12 * mm

    # REGISTRATION heading
    c.setFillColor(WHITE)
    c.setFont('Helvetica-Bold', 18)
    c.drawString(ox + MARGIN, y, 'REGISTRATION')
    y -= 10 * mm

    # CONFIRMED in orange
    c.setFillColor(ORANGE)
    c.setFont('Helvetica-Bold', 18)
    c.drawString(ox + MARGIN, y, 'CONFIRMED')
    y -= 14 * mm

    # Dear ...
    c.setFillColor(WHITE)
    c.setFont('Helvetica-Bold', 9)
    greeting = f"Dear {person_name}," if person_name else "Dear Exhibitor,"
    c.drawString(ox + MARGIN, y, greeting)
    y -= 8 * mm

    c.setFont('Helvetica', 8.5)
    c.setFillColor(colors.HexColor('#c7cdd6'))
    lines = [
        f"Thank you for joining the",
        f"{event_name}.",
        "",
        f"Your exhibitor space is recorded under",
    ]
    for line in lines:
        c.drawString(ox + MARGIN, y, line)
        y -= 5.5 * mm

    # Company in orange
    if company_name:
        c.setFillColor(ORANGE)
        c.setFont('Helvetica-Bold', 8.5)
        c.drawString(ox + MARGIN, y, f"{company_name}.")
    y -= 8 * mm

    c.setFillColor(colors.HexColor('#c7cdd6'))
    c.setFont('Helvetica', 8.5)
    c.drawString(ox + MARGIN, y, "Please reply if any correction is required.")
    y -= 20 * mm

    # Footer
    c.setFillColor(colors.HexColor('#2d3a52'))
    c.rect(ox, oy, PANEL_W, 16 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(ox + MARGIN, oy + 10 * mm, 'NearEstate Exhibitions')
    c.setFont('Helvetica', 7)
    c.setFillColor(colors.HexColor('#8899bb'))
    c.drawString(ox + MARGIN, oy + 5 * mm, 'nearestate.com  •  @nearestate')


# ─────────────────────────────────────────────────────────────────────────────
# PANEL 2 — BOTTOM-LEFT: Event & Check-in (INSIDE LEFT when folded)
# Origin: (0, 0)
# ─────────────────────────────────────────────────────────────────────────────

def _draw_bottom_left_checkin(c, day_name, date_str, time_str, venue_name, venue_city, checkin_str):
    ox, oy = 0, 0

    # White background
    c.setFillColor(WHITE)
    c.rect(ox, oy, PANEL_W, PANEL_H, fill=1, stroke=0)

    # NE logo + NearEstate
    sq = 9 * mm
    c.setFillColor(ORANGE)
    c.roundRect(ox + MARGIN, oy + PANEL_H - MARGIN - sq, sq, sq, 2, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont('Helvetica-Bold', 8)
    c.drawCentredString(ox + MARGIN + sq / 2, oy + PANEL_H - MARGIN - sq + 2.5 * mm, 'NE')

    c.setFillColor(DARK_NAVY)
    c.setFont('Helvetica-Bold', 11)
    c.drawString(ox + MARGIN + sq + 3 * mm, oy + PANEL_H - MARGIN - sq + 2 * mm, 'NearEstate')

    y = oy + PANEL_H - MARGIN - sq - 10 * mm

    # EVENT & CHECK-IN heading
    c.setFillColor(DARK_NAVY)
    c.setFont('Helvetica-Bold', 13)
    c.drawString(ox + MARGIN, y, 'EVENT & CHECK-IN')
    y -= 10 * mm

    # Day name in orange
    c.setFillColor(ORANGE)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(ox + MARGIN, y, day_name)
    y -= 7 * mm

    # Date large
    c.setFillColor(DARK_NAVY)
    c.setFont('Helvetica-Bold', 18)
    c.drawString(ox + MARGIN, y, date_str)
    y -= 9 * mm

    # Time
    if time_str:
        c.setFillColor(MID_GRAY)
        c.setFont('Helvetica', 9)
        c.drawString(ox + MARGIN, y, time_str)
    y -= 12 * mm

    # Venue name
    c.setFillColor(DARK_NAVY)
    c.setFont('Helvetica-Bold', 9)
    c.drawString(ox + MARGIN, y, venue_name)
    y -= 6 * mm

    # Venue city
    c.setFillColor(MID_GRAY)
    c.setFont('Helvetica', 8)
    c.drawString(ox + MARGIN, y, venue_city)
    y -= 12 * mm

    # Check-in line
    c.setFillColor(DARK_NAVY)
    c.setFont('Helvetica-Bold', 8)
    checkin_label = f"Exhibitor check-in: {checkin_str}" if checkin_str else "Exhibitor check-in details to be confirmed."
    c.drawString(ox + MARGIN, y, checkin_label)
    y -= 6 * mm

    c.setFillColor(MID_GRAY)
    c.setFont('Helvetica', 7.5)
    c.drawString(ox + MARGIN, y, 'Bring this badge or show the PDF on your phone.')

    # Footer
    c.setFillColor(colors.HexColor('#f0f2f5'))
    c.rect(ox, oy, PANEL_W, 12 * mm, fill=1, stroke=0)
    c.setFillColor(ORANGE)
    c.setFont('Helvetica', 7)
    c.drawString(ox + MARGIN, oy + 7 * mm, 'info@nearestate.com')
    c.setFillColor(MID_GRAY)
    c.drawString(ox + MARGIN, oy + 3 * mm, 'nearestate.com')


# ─────────────────────────────────────────────────────────────────────────────
# PANEL 3 — TOP-LEFT: Badge (BACK COVER when folded) — drawn UPSIDE DOWN
# Origin: (0, PANEL_H)  →  rotated 180° around its centre
# ─────────────────────────────────────────────────────────────────────────────

def _draw_top_left_badge(c, person_name, company_name, job_title, event_name, date_str):
    # We draw this panel upside-down so it reads correctly after folding.
    # Save state, translate+rotate 180° around the panel centre, draw, restore.
    c.saveState()
    cx = PANEL_W / 2
    cy = PANEL_H + PANEL_H / 2
    c.translate(cx, cy)
    c.rotate(180)
    c.translate(-PANEL_W / 2, -PANEL_H / 2)

    ox, oy = 0, 0   # local origin after transform

    # White background
    c.setFillColor(WHITE)
    c.rect(ox, oy, PANEL_W, PANEL_H, fill=1, stroke=0)

    # Light rounded rect border
    c.setStrokeColor(BORDER_GRAY)
    c.setLineWidth(0.8)
    c.roundRect(ox + 4 * mm, oy + 4 * mm, PANEL_W - 8 * mm, PANEL_H - 8 * mm, 4, fill=0, stroke=1)

    y = oy + PANEL_H - 4 * mm - 10 * mm

    # Date top (small)
    c.setFillColor(MID_GRAY)
    c.setFont('Helvetica', 7)
    c.drawCentredString(ox + PANEL_W / 2, y, date_str)
    y -= 8 * mm

    # Event name (2 lines max)
    c.setFillColor(DARK_NAVY)
    c.setFont('Helvetica-Bold', 10)
    _draw_centered_wrapped(c, event_name, ox + PANEL_W / 2, y, PANEL_W - 20 * mm, 12 * mm)
    y -= 18 * mm

    # Company name in orange
    c.setFillColor(ORANGE)
    c.setFont('Helvetica-Bold', 9)
    _truncate_draw(c, company_name or "", ox + PANEL_W / 2, y, align='center')
    y -= 7 * mm

    # Job title
    if job_title:
        c.setFillColor(MID_GRAY)
        c.setFont('Helvetica', 7.5)
        _truncate_draw(c, job_title, ox + PANEL_W / 2, y, align='center')
    y -= 7 * mm

    # PERSON NAME very large
    c.setFillColor(DARK_NAVY)
    c.setFont('Helvetica-Bold', 22)
    _truncate_draw(c, person_name.upper() if person_name else "", ox + PANEL_W / 2, y, align='center', max_chars=22, size=22)
    y -= 30 * mm

    # Footer strip with logo + EXHIBITOR badge
    footer_h = 18 * mm
    c.setFillColor(colors.HexColor('#f7f9fc'))
    c.rect(ox + 4 * mm, oy + 4 * mm, PANEL_W - 8 * mm, footer_h, fill=1, stroke=0)

    # NE logo
    sq = 9 * mm
    c.setFillColor(ORANGE)
    c.roundRect(ox + 8 * mm, oy + 4 * mm + (footer_h - sq) / 2, sq, sq, 2, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont('Helvetica-Bold', 8)
    c.drawCentredString(ox + 8 * mm + sq / 2, oy + 4 * mm + (footer_h - sq) / 2 + 2.5 * mm, 'NE')

    c.setFillColor(DARK_NAVY)
    c.setFont('Helvetica-Bold', 9)
    c.drawString(ox + 8 * mm + sq + 3 * mm, oy + 4 * mm + (footer_h - sq) / 2 + 2 * mm, 'NearEstate')

    # EXHIBITOR pill button (right side)
    pill_w, pill_h = 24 * mm, 8 * mm
    pill_x = ox + PANEL_W - 4 * mm - MARGIN - pill_w
    pill_y = oy + 4 * mm + (footer_h - pill_h) / 2
    c.setFillColor(ORANGE)
    c.roundRect(pill_x, pill_y, pill_w, pill_h, 3, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont('Helvetica-Bold', 7)
    c.drawCentredString(pill_x + pill_w / 2, pill_y + 2.5 * mm, 'EXHIBITOR')

    c.restoreState()


# ─────────────────────────────────────────────────────────────────────────────
# PANEL 4 — TOP-RIGHT: Exhibitor Details form — also UPSIDE DOWN
# Origin: (PANEL_W, PANEL_H)
# ─────────────────────────────────────────────────────────────────────────────

def _draw_top_right_details(c, company_name, person_name, email, website, package, booking_ref):
    c.saveState()
    cx = PANEL_W + PANEL_W / 2
    cy = PANEL_H + PANEL_H / 2
    c.translate(cx, cy)
    c.rotate(180)
    c.translate(-PANEL_W / 2, -PANEL_H / 2)

    ox, oy = 0, 0

    # Light background
    c.setFillColor(colors.HexColor('#f7f9fc'))
    c.rect(ox, oy, PANEL_W, PANEL_H, fill=1, stroke=0)

    y = oy + PANEL_H - MARGIN - 6 * mm

    # EXHIBITOR DETAILS heading
    c.setFillColor(DARK_NAVY)
    c.setFont('Helvetica-Bold', 12)
    c.drawString(ox + MARGIN, y, 'EXHIBITOR DETAILS')
    y -= 5 * mm

    c.setFillColor(MID_GRAY)
    c.setFont('Helvetica', 7)
    c.drawString(ox + MARGIN, y, 'Please verify before printing.')
    y -= 8 * mm

    # Details rows
    rows = [
        ('COMPANY',      company_name),
        ('CONTACT PERSON', person_name),
        ('EMAIL',        email),
        ('WEBSITE',      website),
        ('PACKAGE',      package),
        ('BOOKING REF.', booking_ref),
    ]

    for label, value in rows:
        _detail_row(c, label, value or '', ox, y, PANEL_W)
        y -= 16 * mm

    c.restoreState()


def _detail_row(c, label, value, ox, y, panel_w):
    """Draw a labeled detail row with a bottom border."""
    row_h = 14 * mm

    c.setFillColor(MID_GRAY)
    c.setFont('Helvetica', 6.5)
    c.drawRightString(ox + panel_w - MARGIN, y, label)

    c.setFillColor(DARK_NAVY)
    c.setFont('Helvetica-Bold', 8)
    c.drawRightString(ox + panel_w - MARGIN, y - 5 * mm, value)

    # Thin bottom border
    c.setStrokeColor(BORDER_GRAY)
    c.setLineWidth(0.5)
    c.line(ox + MARGIN, y - 8 * mm, ox + panel_w - MARGIN, y - 8 * mm)


# ─────────────────────────────────────────────────────────────────────────────
# FOLD LINES
# ─────────────────────────────────────────────────────────────────────────────

def _draw_fold_lines(c):
    c.setStrokeColor(colors.HexColor('#cccccc'))
    c.setLineWidth(0.5)
    c.setDash([3, 4])  # dashed

    # Horizontal fold (Fold 1: A4 → A5)
    c.line(0, PANEL_H, PAGE_W, PANEL_H)

    # Vertical fold (Fold 2: A5 → A6)
    c.line(PANEL_W, 0, PANEL_W, PAGE_H)

    c.setDash([])  # reset

    # Fold labels
    c.setFillColor(MID_GRAY)
    c.setFont('Helvetica', 5.5)
    c.drawRightString(PAGE_W - 2 * mm, PANEL_H + 1 * mm, '← FOLD 1: A4 → A5')
    # Vertical label (rotated)
    c.saveState()
    c.translate(PANEL_W + 1.5 * mm, 15 * mm)
    c.rotate(90)
    c.drawString(0, 0, 'FOLD 2: A5 → A6')
    c.restoreState()


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _truncate_draw(c, text, x, y, align='left', max_chars=35, size=None):
    if len(text) > max_chars:
        text = text[:max_chars - 1] + '…'
    if align == 'center':
        c.drawCentredString(x, y, text)
    else:
        c.drawString(x, y, text)


def _draw_centered_wrapped(c, text, cx, y, max_width, line_height):
    """Draw up to 2 lines of centered text, breaking at spaces."""
    words = text.split()
    lines, current = [], []
    for word in words:
        test = ' '.join(current + [word])
        if c.stringWidth(test, c._fontname, c._fontsize) > max_width and current:
            lines.append(' '.join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(' '.join(current))
    lines = lines[:2]
    for line in lines:
        c.drawCentredString(cx, y, line)
        y -= line_height


def _save_badge_to_application(application, pdf_bytes: bytes):
    from django.core.files.base import ContentFile
    filename = f"badge_{application.id}.pdf"
    application.badge.save(filename, ContentFile(pdf_bytes), save=True)
    logger.info("Badge saved for application %s → %s", application.id, filename)
