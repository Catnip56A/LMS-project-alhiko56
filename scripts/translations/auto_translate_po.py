#!/usr/bin/env python3
"""
Translate .po files using the core translation engine.

Dev-time tool — no Flask app context, no database required.
Reads LIBRETRANSLATE_URL from the environment (set via .env / just).
"""
import os
import sys
import time

# Load core_translator directly from its file to avoid triggering
# yonca/__init__.py, which requires DATABASE_URL and SECRET_KEY at import time.
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "core_translator",
    os.path.join(os.path.dirname(__file__), '..', '..', 'yonca', 'core_translator.py'),
)
core_translator = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(core_translator)

try:
    import polib
except ImportError:
    print("Error: polib is required. Install with: uv add polib")
    sys.exit(1)

LANGUAGES = {'az': 'Azerbaijani', 'ru': 'Russian'}
BASE_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'yonca', 'translations')
)
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
            translated = core_translator.translate_text(
                entry.msgid, lang_code, libretranslate_url=LIBRE_URL
            )
            for idx in entry.msgstr_plural:
                entry.msgstr_plural[idx] = translated
            updated += 1
        else:
            if entry.translated():
                continue
            translated = core_translator.translate_text(
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
        po_file = os.path.join(BASE_PATH, lang_code, 'LC_MESSAGES', 'messages.po')
        if not os.path.exists(po_file):
            print(f"Warning: {po_file} not found, skipping...")
            continue
        print(f"{lang_name} ({lang_code})")
        translate_po_file(po_file, lang_code)

    print("\nDone.")


if __name__ == '__main__':
    main()
