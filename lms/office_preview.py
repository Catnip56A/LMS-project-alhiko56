"""
Headless Office-document-to-PDF conversion — no Flask/DB dependency, same convention as
gemini_client.py/r2_client.py. Used by every ingestion path that needs a browser-viewable
preview of an uploaded .doc/.docx/.ppt/.pptx/.xls/.xlsx (direct upload, Picker import, the
Drive-to-R2 backfill): browsers render PDF/images/video/audio natively, but have no built-in
renderer for Office formats. Google Drive's own `/preview` handled this by converting the file
server-side before returning it — R2 has no equivalent, so this app does the conversion itself
via headless LibreOffice (already installed in the image, see Dockerfile).
"""
import logging
import os
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)

# Excel specifically gets an interactive table view instead of a flat PDF (Phase 8) — see
# file_viewer.html's 'spreadsheet' file_type, which parses the raw bytes client-side via
# SheetJS rather than using the PDF preview these MIMEs would otherwise get below.
SPREADSHEET_MIME_TYPES = {
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}

# Every other Office MIME this app accepts on upload (see upload_validation.ALLOWED_MIME_TYPES)
# that has no native browser renderer — legacy binary formats included, since LibreOffice
# converts those to PDF just as well as the modern XML-based ones.
OFFICE_MIME_TYPES = {
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
} | SPREADSHEET_MIME_TYPES

_CONVERT_TIMEOUT_SECONDS = 120


def needs_pdf_preview(mime: str | None) -> bool:
    return bool(mime) and mime in OFFICE_MIME_TYPES


def convert_to_pdf(local_path: str) -> str | None:
    """Convert an Office document at local_path to PDF via headless LibreOffice. Returns the
    path to the generated PDF (in a fresh temp directory the caller is responsible for
    cleaning up), or None on failure/timeout. Safe to call concurrently — each invocation gets
    its own isolated LibreOffice user profile directory, avoiding the lock-file contention
    headless LibreOffice hits when two conversions share a profile.
    """
    out_dir = tempfile.mkdtemp()
    profile_dir = tempfile.mkdtemp()
    try:
        result = subprocess.run(
            [
                'soffice', '--headless', '--norestore',
                f'-env:UserInstallation=file://{profile_dir}',
                '--convert-to', 'pdf', '--outdir', out_dir, local_path,
            ],
            capture_output=True, timeout=_CONVERT_TIMEOUT_SECONDS, check=False,
        )
        if result.returncode != 0:
            logger.error(f'LibreOffice conversion failed for {local_path}: {result.stderr.decode(errors="replace")}')
            return None

        base = os.path.splitext(os.path.basename(local_path))[0]
        pdf_path = os.path.join(out_dir, f'{base}.pdf')
        if not os.path.exists(pdf_path):
            logger.error(f'LibreOffice reported success but no PDF found for {local_path}')
            return None
        return pdf_path
    except subprocess.TimeoutExpired:
        logger.error(f'LibreOffice conversion timed out for {local_path}')
        return None
    except OSError as e:
        logger.error(f'LibreOffice conversion error for {local_path}: {e}')
        return None
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)


def generate_and_upload_preview(local_path: str, mime: str | None, original_r2_key: str) -> str | None:
    """If `mime` needs a PDF preview (see needs_pdf_preview), convert local_path and upload
    the result into R2 at a key derived from original_r2_key. Returns the preview's R2 key, or
    None if no preview was needed or the conversion/upload failed — a failed preview degrades
    to "no preview" (the original still uploaded fine), never raises, never blocks the
    original upload from succeeding.

    Shared by every ingestion path that can introduce an Office document: the direct upload
    route, Picker import, and the Drive-to-R2 backfill script.
    """
    if not needs_pdf_preview(mime):
        return None
    pdf_path = convert_to_pdf(local_path)
    if not pdf_path:
        return None
    try:
        from lms import r2_client
        preview_key = f'{original_r2_key}.preview.pdf'
        return preview_key if r2_client.upload_file(pdf_path, preview_key, content_type='application/pdf') else None
    finally:
        shutil.rmtree(os.path.dirname(pdf_path), ignore_errors=True)
