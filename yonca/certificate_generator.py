"""
Certificate image and PDF generation using Pillow + qrcode + img2pdf.

Template image and fonts must be placed at:
  yonca/static/certificates/moxo_template.jpeg  (or .jpg / .png)
  yonca/static/certificates/fonts/GreatVibes-Regular.ttf
  yonca/static/certificates/fonts/OpenSans-Regular.ttf

Per-course x/y tuning is stored in:
  yonca/static/certificates/tuning.json
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont
import qrcode

_HERE = os.path.dirname(__file__)
STATIC_CERTS = os.path.join(_HERE, 'static', 'certificates')
TUNING_PATH = os.path.join(STATIC_CERTS, 'tuning.json')
FONT_SCRIPT = os.path.join(STATIC_CERTS, 'fonts', 'GreatVibes-Regular.ttf')
FONT_BODY = os.path.join(STATIC_CERTS, 'fonts', 'OpenSans-Regular.ttf')
FONT_COURSE = os.path.join(STATIC_CERTS, 'fonts', 'CormorantSC-Bold.ttf')
FONT_META = os.path.join(STATIC_CERTS, 'fonts', 'CormorantGaramond-Regular.ttf')
OUTPUT_DIR = os.path.join(STATIC_CERTS, 'generated')

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


def load_tuning(course_id=None) -> dict:
    """Return merged tuning: defaults → file defaults → per-course override."""
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
    """Persist per-course tuning values to the JSON file."""
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


_IMAGE_EXTS = {'.jpeg', '.jpg', '.png'}
_EXCLUDED = {'tuning.json'}


def list_templates() -> list[str]:
    """Return filenames of image files directly inside STATIC_CERTS (no subdirs)."""
    try:
        return sorted(
            f for f in os.listdir(STATIC_CERTS)
            if os.path.splitext(f)[1].lower() in _IMAGE_EXTS
            and f not in _EXCLUDED
            and os.path.isfile(os.path.join(STATIC_CERTS, f))
        )
    except OSError:
        return []


def _find_template():
    for ext in ('jpeg', 'jpg', 'png'):
        p = os.path.join(STATIC_CERTS, f'moxo_template.{ext}')
        if os.path.exists(p):
            return p
    return os.path.join(STATIC_CERTS, 'moxo_template.jpeg')


def _resolve_template(tuning: dict) -> str:
    """Return absolute path to the template, using tuning['template_file'] if set and valid."""
    name = tuning.get('template_file') or ''
    # Sanitise: only a bare filename, no path traversal
    name = os.path.basename(name)
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


def generate_certificate_image(certificate) -> str:
    """
    Render a certificate image for the given certificate object.
    Tuning values are loaded from tuning.json for the certificate's course.
    Returns the absolute path to the generated PNG.
    """
    t = load_tuning(certificate.course_id)

    template_path = _resolve_template(t)
    if not os.path.exists(template_path):
        raise FileNotFoundError(
            f"Certificate template not found. Place an image file in {STATIC_CERTS}/"
        )

    img = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    W, H = img.size

    # Student name in script font
    font_name = _load_font(FONT_SCRIPT, int(H * t['font_name_size']))
    name_text = certificate.student_name
    bbox = draw.textbbox((0, 0), name_text, font=font_name)
    x_name = (W - (bbox[2] - bbox[0])) / 2
    draw.text((x_name, H * t['y_name']), name_text, font=font_name,
              fill=tuple(t['name_color']))

    # Course name — Cormorant SC Bold, centered around x_course
    font_course = _load_font(FONT_COURSE, int(H * t['font_course_size']))
    course_text = t.get('course_label') or certificate.course.title
    bbox = draw.textbbox((0, 0), course_text, font=font_course)
    x_course = W * t['x_course'] - (bbox[2] - bbox[0]) / 2
    draw.text((x_course, H * t['y_course']), course_text, font=font_course,
              fill=tuple(t['course_color']))

    # Date and cert ID — Cormorant Garamond
    font_meta = _load_font(FONT_META, int(H * 0.022))
    date_str = certificate.issued_at.strftime("%-d %B %Y")
    draw.text((W * t['x_meta'], H * t['y_date']), f"Issued: {date_str}",
              font=font_meta, fill=tuple(t['date_color']))
    draw.text((W * t['x_cert_id'], H * t['y_cert_id']), f"Certificate ID: {certificate.cert_id_display}",
              font=font_meta, fill=tuple(t['cert_id_color']))

    # QR code
    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data(certificate.verify_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
    qr_size = int(H * t['qr_size'])
    qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS)
    img.paste(qr_img, (int(W * t['x_qr']), int(H * t['y_qr'])), qr_img)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"{certificate.id}.png")
    img.convert("RGB").save(out_path, "PNG", quality=95)
    return out_path


def get_or_generate_image(certificate) -> str:
    path = os.path.join(OUTPUT_DIR, f"{certificate.id}.png")
    if not os.path.exists(path):
        generate_certificate_image(certificate)
    return path


def get_certificate_pdf_path(certificate) -> str:
    import img2pdf
    img_path = get_or_generate_image(certificate)
    pdf_path = os.path.join(OUTPUT_DIR, f"{certificate.id}.pdf")
    with open(pdf_path, "wb") as f:
        f.write(img2pdf.convert(img_path))
    return pdf_path


def generate_preview_bytes(tuning: dict, student_name: str = "Sample Student",
                           cert_display_id: str = "YONCA-2026-DEMO1",
                           verify_url: str = "https://yonca-sdc.com/certificate/preview") -> bytes:
    """Render a certificate with arbitrary tuning values and return PNG bytes (no disk write)."""
    import io
    from datetime import datetime

    t = tuning
    template_path = _resolve_template(t)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Certificate template not found in {STATIC_CERTS}/")

    img = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    W, H = img.size

    font_name = _load_font(FONT_SCRIPT, int(H * t['font_name_size']))
    bbox = draw.textbbox((0, 0), student_name, font=font_name)
    x_name = (W - (bbox[2] - bbox[0])) / 2
    draw.text((x_name, H * t['y_name']), student_name, font=font_name, fill=tuple(t['name_color']))

    font_course = _load_font(FONT_COURSE, int(H * t['font_course_size']))
    course_text = t.get('course_label') or "Sample Course"
    bbox = draw.textbbox((0, 0), course_text, font=font_course)
    x_course = W * t['x_course'] - (bbox[2] - bbox[0]) / 2
    draw.text((x_course, H * t['y_course']), course_text, font=font_course,
              fill=tuple(t['course_color']))

    font_meta = _load_font(FONT_META, int(H * 0.022))
    date_str = datetime.utcnow().strftime("%-d %B %Y")
    draw.text((W * t['x_meta'], H * t['y_date']), f"Issued: {date_str}",
              font=font_meta, fill=tuple(t['date_color']))
    draw.text((W * t['x_cert_id'], H * t['y_cert_id']), f"Certificate ID: {cert_display_id}",
              font=font_meta, fill=tuple(t['cert_id_color']))

    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data(verify_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
    qr_size = int(H * t['qr_size'])
    qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS)
    img.paste(qr_img, (int(W * t['x_qr']), int(H * t['y_qr'])), qr_img)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG", quality=95)
    buf.seek(0)
    return buf.read()


def delete_certificate_files(certificate_id: str) -> None:
    for ext in ('png', 'pdf'):
        path = os.path.join(OUTPUT_DIR, f"{certificate_id}.{ext}")
        if os.path.exists(path):
            os.remove(path)
