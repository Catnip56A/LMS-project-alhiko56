#!/usr/bin/env python3
"""
Automatically translate .po files using LibreTranslate API
This script reads the messages.po files and populates translations
"""
import os
from dotenv import load_dotenv
load_dotenv()

from yonca import create_app
from yonca.translation_service import translation_service

# Use polib to robustly read/write .po files (handles multiline, plurals, headers)
try:
    import polib
except ImportError:
    polib = None

def update_po_file_with_polib(po_file_path, translations):
    """Update a .po file using polib: set entry.msgstr for untranslated entries."""
    if polib is None:
        raise RuntimeError("polib is required for safe PO editing. Install with 'pip install polib'.")

    po = polib.pofile(str(po_file_path))

    updated = 0
    for entry in po:
        # Skip header entry and entries without msgid
        if not entry.msgid:
            continue

        # For plurals, update msgstr_plural dict if empty
        if entry.msgid_plural:
            needs = any(not v for v in entry.msgstr_plural.values())
            if not needs:
                continue

            # Translate singular form then duplicate to plural indexes (translation service may handle plurals differently)
            translated = translations.get(entry.msgid) or translation_service.get_translation(entry.msgid, po.metadata.get('Language', ''))
            # Assign to all plural forms as a simple approach
            for idx in entry.msgstr_plural:
                entry.msgstr_plural[idx] = translated
            updated += 1
        else:
            if entry.translated():
                continue
            translated = translations.get(entry.msgid) or translation_service.get_translation(entry.msgid, po.metadata.get('Language', ''))
            entry.msgstr = translated
            updated += 1

    if updated:
        po.save()
    print(f"Updated {po_file_path} ({updated} entries changed)")

def translate_po_files():
    """Main function to translate all .po files"""
    app = create_app()
    
    languages = {
        'az': 'Azerbaijani',
        'ru': 'Russian'
    }
    
    base_path = 'yonca/translations'
    
    with app.app_context():
        for lang_code, lang_name in languages.items():
            po_file = os.path.join(base_path, lang_code, 'LC_MESSAGES', 'messages.po')

            if not os.path.exists(po_file):
                print(f"Warning: {po_file} not found, skipping...")
                continue

            print(f"\n{'='*60}")
            print(f"Translating to {lang_name} ({lang_code})")
            print(f"{'='*60}")

            if polib is None:
                print("Error: polib is not installed. Install it with 'pip install polib'. Skipping.")
                continue

            # Use polib to update untranslated entries. The updater will call
            # translation_service for entries when needed.
            try:
                update_po_file_with_polib(po_file, {})
                print(f"\n✓ Translations updated for {lang_name}")
            except Exception as e:
                print(f"✗ Error updating {po_file}: {e}")
        
        print(f"\n{'='*60}")
        print("Translation complete!")
        print("Now compiling .po files to .mo files...")
        print(f"{'='*60}\n")
        
        # Compile the translations
        import subprocess
        result = subprocess.run(['pybabel', 'compile', '-d', 'yonca/translations'], 
                              capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        
        print("\n✓ Done! Restart your Flask app to see the translations.")

if __name__ == '__main__':
    print("Starting automatic translation of .po files...")
    print("This will use LibreTranslate to translate all untranslated strings.")
    print("Make sure LibreTranslate is running on http://localhost:5000\n")
    
    try:
        translate_po_files()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        print("\nMake sure:")
        print("1. LibreTranslate is running: docker run -d -p 5000:5000 libretranslate/libretranslate")
        print("2. Your database is accessible")
        print("3. .env file is configured correctly")
