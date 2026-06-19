#!/usr/bin/env python3
"""
Translate .po files using the core translation engine.

Dev-time tool — no Flask app context, no database required.
Reads LIBRETRANSLATE_URL from the environment (set via .env / just).
"""
import os
import sys
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
CHUNK_SIZE = 50
SOURCE_LANG = 'en'


def translate_po_file(po_file_path: str, lang_code: str) -> None:
    po = polib.pofile(po_file_path)

    # For the source language just copy msgid → msgstr — no API call needed.
    if lang_code == SOURCE_LANG:
        updated = 0
        cleared = 0
        for entry in po:
            if not entry.msgid or entry.msgid_plural:
                continue
            if not entry.msgstr:
                entry.msgstr = entry.msgid
                updated += 1
            elif 'fuzzy' in entry.flags:
                entry.flags.remove('fuzzy')
                cleared += 1
        if updated or cleared:
            po.save()
        print(f"  {os.path.relpath(po_file_path)}: {updated} entries copied, {cleared} fuzzy flag(s) cleared (source lang)")
        return

    # Collect entries that still need translation (msgstr is empty).
    # Fuzzy entries with a non-empty msgstr are kept as-is; only their fuzzy
    # flag is cleared so pybabel compile picks them up.
    untranslated = []
    cleared_fuzzy = 0
    for e in po:
        if not e.msgid:
            continue
        if e.msgid_plural:
            if not all(v for v in e.msgstr_plural.values()):
                untranslated.append(e)
        else:
            if not e.msgstr:
                untranslated.append(e)
            elif 'fuzzy' in e.flags:
                e.flags.remove('fuzzy')
                cleared_fuzzy += 1

    if cleared_fuzzy and not untranslated:
        po.save()
        print(f"  {os.path.relpath(po_file_path)}: cleared {cleared_fuzzy} fuzzy flag(s), nothing to translate")
        return

    if not untranslated:
        print(f"  {os.path.relpath(po_file_path)}: already complete")
        return

    print(f"  {os.path.relpath(po_file_path)}: translating {len(untranslated)} entries...", flush=True)

    texts = [e.msgid for e in untranslated]
    translated_texts = _core_translator.translate_batch(
        texts,
        lang_code,
        libretranslate_url=LIBRE_URL,
        chunk_size=CHUNK_SIZE,
    )

    for entry, translated in zip(untranslated, translated_texts):
        if entry.msgid_plural:
            for idx in entry.msgstr_plural:
                entry.msgstr_plural[idx] = translated
        else:
            entry.msgstr = translated

    po.save()
    print(f"  {os.path.relpath(po_file_path)}: done ({len(untranslated)} entries)")


def main() -> None:
    print("Translating .po files...")
    if LIBRE_URL:
        print(f"  LibreTranslate: {LIBRE_URL}")
    else:
        print("  WARNING: LIBRETRANSLATE_URL not set — translations will be skipped")
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
