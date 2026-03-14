#!/usr/bin/env python3
"""
Clear all translations from .po files
This script removes all msgstr translations while keeping msgid entries intact
Useful for regenerating translations from scratch
"""
import os
import re
import sys
from pathlib import Path

def clear_po_translations(po_file_path):
    """Clear all translations (msgstr values) from a .po file"""
    print(f"Processing: {po_file_path}")
    
    with open(po_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split content into lines for processing
    lines = content.split('\n')
    new_lines = []
    in_header = True
    skip_next = False
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Keep header block (first msgid/msgstr pair which is empty)
        if in_header and line.strip().startswith('msgstr'):
            # This is the header msgstr, keep it and all its continuation lines
            new_lines.append(line)
            i += 1
            # Keep all continuation lines (lines starting with ")
            while i < len(lines) and lines[i].strip().startswith('"') and not lines[i].strip().startswith('msgid'):
                new_lines.append(lines[i])
                i += 1
            in_header = False
            continue
        
        # For regular translations, clear msgstr values
        if line.strip().startswith('msgstr'):
            # Check if this is a plural form (msgstr[0], msgstr[1], etc.)
            if '[' in line and ']' in line:
                # Plural form - clear the value but keep the index
                match = re.match(r'(msgstr\[\d+\])\s+".*"', line)
                if match:
                    new_lines.append(f'{match.group(1)} ""')
                else:
                    new_lines.append(line)
            else:
                # Regular msgstr - clear the value
                new_lines.append('msgstr ""')
            
            # Skip any continuation lines (lines starting with ")
            i += 1
            while i < len(lines) and lines[i].strip().startswith('"') and not lines[i].strip().startswith('msgid'):
                i += 1
            continue
        
        # Keep all other lines (comments, msgid, etc.)
        new_lines.append(line)
        i += 1
    
    # Write back to file
    with open(po_file_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))
    
    print(f"✓ Cleared translations in: {po_file_path}")

def find_po_files(base_path):
    """Find all .po files in the translations directory"""
    po_files = []
    # Prefer the package translations directory, but allow a project-level
    # `translations` folder as a fallback. This mirrors other scripts.
    candidates = [
        Path(base_path) / 'yonca' / 'translations',
        Path(base_path) / 'translations',
    ]

    translations_path = None
    for cand in candidates:
        if cand.exists():
            translations_path = cand
            break

    if translations_path is None:
        print(f"Error: Translations directory not found. Checked: {', '.join(str(p) for p in candidates)}")
        return po_files

    # Find all .po files under the chosen translations directory
    for po_file in translations_path.rglob('*.po'):
        po_files.append(po_file)
    
    return po_files

def main():
    """Main function to clear all translations from .po files"""
    # Get the base path (project root)
    base_path = Path(__file__).parent
    
    print("=" * 60)
    print("Clearing all translations from .po files")
    print("=" * 60)
    
    # Find all .po files
    po_files = find_po_files(base_path)
    
    if not po_files:
        print("No .po files found!")
        return
    
    print(f"\nFound {len(po_files)} .po file(s):")
    for po_file in po_files:
        print(f"  - {po_file.relative_to(base_path)}")
    
    # Ask for confirmation
    response = input("\nAre you sure you want to clear all translations? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Operation cancelled.")
        return
    
    print("\nClearing translations...")
    # Process each .po file
    for po_file in po_files:
        try:
            clear_po_translations(po_file)
        except Exception as e:
            print(f"✗ Error processing {po_file}: {e}")
    
    print("\n" + "=" * 60)
    print("Done! All translations have been cleared.")
    print("=" * 60)

if __name__ == '__main__':
    main()
