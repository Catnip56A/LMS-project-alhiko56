#!/usr/bin/env python3
"""
Translate .po files using the core translation engine.

Dev-time tool — no Flask app context, no database required.
Reads LIBRETRANSLATE_URL from the environment (set via .env / just).
"""
import os
import sys
import time
import importlib.util

# Add project root to path so we can import yonca modules
_project_root = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, _project_root)

# Load core_translator directly from its file to avoid triggering
# yonca/__init__.py, which requires DATABASE_URL and SECRET_KEY at import time.
_spec = importlib.util.spec_from_file_location(
    "core_translator",
    os.path.join(os.path.dirname(__file__), '..', '..', 'yonca', 'core_translator.py'),
)
_core_translator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_core_translator)

# Load constants directly to avoid importing yonca/__init__.py
_const_spec = importlib.util.spec_from_file_location(
    "constants",
    os.path.join(os.path.dirname(__file__), '..', '..', 'yonca', 'constants.py'),
)
_constants = importlib.util.module_from_spec(_const_spec)
_const_spec.loader.exec_module(_constants)

try:
    import polib
except ImportError:
    print("Error: polib is required. Install with: uv add polib")
    sys.exit(1)

SUPPORTED_LANGUAGES = _constants.SUPPORTED_LANGUAGES
LANGUAGE_NAMES = _constants.LANGUAGE_NAMES

LANGUAGES = {lang: LANGUAGE_NAMES.get(lang, lang) for lang in SUPPORTED_LANGUAGES}
TRANSLATIONS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'yonca', 'translations')
LIBRE_URL = os.environ.get('LIBRETRANSLATE_URL') or None
# Seconds between API calls — keeps us under Google's unofficial rate limit
REQUEST_DELAY = 0.2


def translate_po_file(po_file_path: str, lang_code: str) -> None:
    po = polib.pofile(po_file_path)
    updated = 0

    for entry in po:
        if not entry.msgid:
            continue

        if entry.msgid_plural:
            if not any(not v for v in entry.msgstr_plural.values()):
                continue
            translated = _core_translator.translate_text(
                entry.msgid, lang_code, libretranslate_url=LIBRE_URL
            )
            for idx in entry.msgstr_plural:
                entry.msgstr_plural[idx] = translated
            updated += 1
        else:
            if entry.translated():
                continue
            translated = _core_translator.translate_text(
                entry.msgid, lang_code, libretranslate_url=LIBRE_URL
            )
            entry.msgstr = translated
            updated += 1

        time.sleep(REQUEST_DELAY)

    if updated:
        po.save()
    print(f"  {os.path.relpath(po_file_path)}: {updated} entries translated")


def main() -> None:
    print("Translating .po files...")
    if LIBRE_URL:
        print(f"  LibreTranslate: {LIBRE_URL}")
    else:
        print("  LibreTranslate not configured — using GoogleTranslator only")
    print()

    for lang_code, lang_name in LANGUAGES.items():
        po_file = os.path.join(TRANSLATIONS_DIR, lang_code, 'LC_MESSAGES', 'messages.po')
        if not os.path.exists(po_file):
            print(f"Warning: {po_file} not found, skipping...")
            continue
        print(f"{lang_name} ({lang_code})")
        translate_po_file(po_file, lang_code)

    print("\nDone.")


if __name__ == '__main__':
    main()
