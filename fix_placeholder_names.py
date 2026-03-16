#!/usr/bin/env python3
"""
Fix placeholder name mismatches in .po files.
Preserves translated text but restores English placeholder names.
"""
import re
from pathlib import Path


def extract_placeholders(text):
    """Extract all named placeholders from a string (e.g., %(name)s)."""
    return set(re.findall(r'%\([a-zA-Z_][a-zA-Z0-9_]*\)s', text))


def replace_placeholders(text, original_text):
    """Replace placeholders in text with those from original_text, preserving translation."""
    original_placeholders = extract_placeholders(original_text)
    text_placeholders = extract_placeholders(text)
    
    if not original_placeholders or not text_placeholders:
        return text
    
    # If placeholders match, no fix needed
    if original_placeholders == text_placeholders:
        return text
    
    # Create a mapping from position to fix
    # We'll replace non-English placeholders with English ones
    result = text
    for placeholder in text_placeholders:
        if placeholder not in original_placeholders:
            # This placeholder doesn't match the original
            # Try to find the corresponding one by position
            result = result.replace(placeholder, list(original_placeholders)[0], 1)
    
    return result


def fix_po_file(po_file_path):
    """Fix all placeholder mismatches in a .po file."""
    with open(po_file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    fixed_lines = []
    i = 0
    fixes_made = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Check if this is a msgid line
        if line.startswith('msgid "'):
            msgid_value = line[7:-2]  # Extract content between quotes
            
            # Collect multi-line msgid if needed
            i += 1
            while i < len(lines) and lines[i].startswith('"'):
                msgid_value += lines[i][1:-2]
                i += 1
            
            i -= 1  # Back up one since we'll increment at the end of loop
            fixed_lines.append(f'msgid "{msgid_value}"\n')
            
            # Now check for msgstr
            i += 1
            if i < len(lines) and lines[i].startswith('msgstr "'):
                msgstr_value = lines[i][8:-2]
                
                # Collect multi-line msgstr if needed
                i += 1
                while i < len(lines) and lines[i].startswith('"'):
                    msgstr_value += lines[i][1:-2]
                    i += 1
                
                # Fix placeholders
                fixed_msgstr = replace_placeholders(msgstr_value, msgid_value)
                if fixed_msgstr != msgstr_value:
                    fixes_made += 1
                
                fixed_lines.append(f'msgstr "{fixed_msgstr}"\n')
                i -= 1  # Back up one since we'll increment at the end of loop
            
            i += 1
            continue
        
        fixed_lines.append(line)
        i += 1
    
    # Write back
    with open(po_file_path, 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)
    
    return fixes_made


# Fix all .po files
po_dir = Path('yonca/translations')
total_fixes = 0

for po_file in po_dir.glob('*/LC_MESSAGES/messages.po'):
    print(f'Fixing: {po_file}')
    fixes = fix_po_file(po_file)
    total_fixes += fixes
    print(f'  ✓ Fixed {fixes} placeholder issues')

print(f'\n✓ Total fixes made: {total_fixes}')
