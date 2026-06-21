"""
Certificate image and PDF generation using Pillow + qrcode + img2pdf.

Generated files are cached in CACHE_DIR (default: data/certificates/ at the
project root, which should be a persistent Docker volume).  The first request
for a certificate renders it and writes it to the cache; subsequent requests
read from disk.  Call invalidate_cache(cert_id) to evict a single entry (e.g.
on revoke or after a tuning change).

Template image and fonts must be placed at:
  yonca/static/certificates/moxo_template.jpeg  (or .jpg / .png)
  yonca/static/certificates/fonts/GreatVibes-Regular.ttf
  yonca/static/certificates/fonts/CormorantSC-Bold.ttf
  yonca/static/certificates/fonts/CormorantGaramond-Regular.ttf

Per-course x/y tuning is stored in:
  yonca/static/certificates/tuning.json
"""
import io
import json
import os

import qrcode
from PIL import Image, ImageDraw, ImageFont

_HERE = os.path.dirname(__file__)
STATIC_CERTS = os.path.join(_HERE, 'static', 'certificates')
TUNING_PATH = os.path.join(STATIC_CERTS, 'tuning.json')
FONT_SCRIPT = os.path.join(STATIC_CERTS, 'fonts', 'GreatVibes-Regular.ttf')
FONT_COURSE = os.path.join(STATIC_CERTS, 'fonts', 'CormorantSC-Bold.ttf')
FONT_META   = os.path.join(STATIC_CERTS, 'fonts', 'CormorantGaramond-Regular.ttf')

# Persistent cache directory — override with CERT_CACHE_DIR env var.
# In Docker this should be a volume mount so the cache survives redeploys.
CACHE_DIR = os.environ.get(
    'CERT_CACHE_DIR',
    os.path.join(os.path.dirname(_HERE), 'data', 'certificates'),
)

_IMAGE_EXTS = {'.jpeg', '.jpg', '.png'}

_DEFAULTS = {
    "y_name": 0.345,
    "font_name_size": 0.09,
    "name_color": [30, 30, 80],
    "course_label": "",
    "x_course": 0.5,
    "y_course": 0.395,
    "font_course_size": 0.028,
    "course_color": [40, 40, 40],
    "x_meta": 0.265,
    "y_date": 0.910,
    "date_color": [40, 40, 40],
    "x_cert_id": 0.265,
    "y_cert_id": 0.933,
    "cert_id_color": [40, 40, 40],
    "x_qr": 0.033,
    "y_qr": 0.775,
    "qr_size": 0.18,
}


# ── Tuning helpers ────────────────────────────────────────────────────────────

def load_tuning(course_id=None) -> dict:
    """Return merged tuning: hardcoded defaults → JSON defaults → per-course override."""
    try:
        with open(TUNING_PATH, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {}
    tuning = {**_DEFAULTS, **data.get('default', {})}
    if course_id is not None:
        tuning.update(data.get(str(course_id), {}))
    return tuning


def save_tuning(course_id, values: dict) -> None:
    try:
        with open(TUNING_PATH, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {'default': {**_DEFAULTS}}
    if course_id == 'default':
        data['default'] = {**data.get('default', {}), **values}
    else:
        data[str(course_id)] = values
    with open(TUNING_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


# ── Template helpers ──────────────────────────────────────────────────────────

def list_templates() -> list[str]:
    """Return sorted image filenames directly inside STATIC_CERTS (no subdirs)."""
    try:
        return sorted(
            f for f in os.listdir(STATIC_CERTS)
            if os.path.splitext(f)[1].lower() in _IMAGE_EXTS
            and os.path.isfile(os.path.join(STATIC_CERTS, f))
        )
    except OSError:
        return []


def _find_template() -> str:
    for ext in ('jpeg', 'jpg', 'png'):
        p = os.path.join(STATIC_CERTS, f'moxo_template.{ext}')
        if os.path.exists(p):
            return p
    return os.path.join(STATIC_CERTS, 'moxo_template.jpeg')


def _resolve_template(tuning: dict) -> str:
    name = os.path.basename(tuning.get('template_file') or '')
    if name and os.path.splitext(name)[1].lower() in _IMAGE_EXTS:
        candidate = os.path.join(STATIC_CERTS, name)
        if os.path.exists(candidate):
            return candidate
    return _find_template()


def _load_font(path, size):
    try:
        return ImageFont.truetype(path, size=size)
    except (OSError, IOError):
        return ImageFont.load_default()


# ── Core drawing (shared by real certs and preview) ───────────────────────────

def _draw_onto(img, t: dict, student_name: str, course_text: str,
               date_str: str, cert_display_id: str, verify_url_str: str) -> None:
    draw = ImageDraw.Draw(img)
    W, H = img.size

    # Student name — Great Vibes script, horizontally centred
    font_name = _load_font(FONT_SCRIPT, int(H * t['font_name_size']))
    bbox = draw.textbbox((0, 0), student_name, font=font_name)
    x_name = (W - (bbox[2] - bbox[0])) / 2
    draw.text((x_name, H * t['y_name']), student_name,
              font=font_name, fill=tuple(t['name_color']))

    # Course name — Cormorant SC Bold, centred around x_course
    font_course = _load_font(FONT_COURSE, int(H * t['font_course_size']))
    bbox = draw.textbbox((0, 0), course_text, font=font_course)
    x_course = W * t['x_course'] - (bbox[2] - bbox[0]) / 2
    draw.text((x_course, H * t['y_course']), course_text,
              font=font_course, fill=tuple(t['course_color']))

    # Date and cert ID — Cormorant Garamond
    font_meta = _load_font(FONT_META, int(H * 0.022))
    draw.text((W * t['x_meta'],    H * t['y_date']),    f"Issued: {date_str}",
              font=font_meta, fill=tuple(t['date_color']))
    draw.text((W * t['x_cert_id'], H * t['y_cert_id']), f"Certificate ID: {cert_display_id}",
              font=font_meta, fill=tuple(t['cert_id_color']))

    # QR code
    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data(verify_url_str)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
    qr_size = int(H * t['qr_size'])
    qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS)
    img.paste(qr_img, (int(W * t['x_qr']), int(H * t['y_qr'])), qr_img)


def _open_template(t: dict) -> Image.Image:
    path = _resolve_template(t)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Certificate template not found. Place an image file in {STATIC_CERTS}/"
        )
    return Image.open(path).convert("RGBA")


def _to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG", quality=95)
    buf.seek(0)
    return buf.read()


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_path(cert_id, ext='png') -> str:
    return os.path.join(CACHE_DIR, f"{cert_id}.{ext}")


def invalidate_cache(cert_id) -> None:
    """Delete cached PNG and PDF for a certificate (call on revoke or tuning change)."""
    for ext in ('png', 'pdf'):
        try:
            os.remove(_cache_path(cert_id, ext))
        except OSError:
            pass


def get_cached_png_bytes(certificate) -> bytes:
    """Return PNG bytes from cache, generating and caching on first call."""
    path = _cache_path(certificate.id)
    if os.path.exists(path):
        with open(path, 'rb') as f:
            return f.read()
    png = generate_certificate_bytes(certificate)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, 'wb') as f:
        f.write(png)
    return png


def get_cached_pdf_bytes(certificate) -> bytes:
    """Return PDF bytes from cache, generating and caching on first call."""
    import img2pdf
    path = _cache_path(certificate.id, 'pdf')
    if os.path.exists(path):
        with open(path, 'rb') as f:
            return f.read()
    png = get_cached_png_bytes(certificate)
    pdf = img2pdf.convert(io.BytesIO(png))
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, 'wb') as f:
        f.write(pdf)
    return pdf


# ── Public API ────────────────────────────────────────────────────────────────

def generate_certificate_bytes(certificate) -> bytes:
    """Render a certificate for a Certificate model instance. Returns PNG bytes."""
    t = load_tuning(certificate.course_id)
    img = _open_template(t)
    _draw_onto(
        img, t,
        student_name=certificate.student_name,
        course_text=t.get('course_label') or certificate.course.title,
        date_str=certificate.issued_at.strftime("%-d %B %Y"),
        cert_display_id=certificate.cert_id_display,
        verify_url_str=certificate.verify_url,
    )
    return _to_png_bytes(img)


def generate_certificate_pdf_bytes(certificate) -> bytes:
    """Render a certificate and convert to PDF. Returns PDF bytes."""
    import img2pdf
    png = generate_certificate_bytes(certificate)
    return img2pdf.convert(io.BytesIO(png))


def generate_preview_bytes(tuning: dict, student_name: str = "Sample Student",
                           cert_display_id: str = "YONCA-2026-DEMO1",
                           verify_url: str = "https://yonca-sdc.com/certificate/preview") -> bytes:
    """Render a certificate with arbitrary tuning for the admin preview. Returns PNG bytes."""
    from datetime import datetime
    t = tuning
    img = _open_template(t)
    _draw_onto(
        img, t,
        student_name=student_name,
        course_text=t.get('course_label') or "Sample Course",
        date_str=datetime.utcnow().strftime("%-d %B %Y"),
        cert_display_id=cert_display_id,
        verify_url_str=verify_url,
    )
    return _to_png_bytes(img)
