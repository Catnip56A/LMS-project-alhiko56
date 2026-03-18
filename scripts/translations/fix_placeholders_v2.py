#!/usr/bin/env python3
"""
Fix placeholder name mismatches by reprocessing .po files with proper parsing.
"""
import re
from pathlib import Path


def fix_po_content(content):
    """Fix placeholder names in .po file content."""
    lines = content.split('\n')
    result = []
    i = 0
    fixes_made = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Match msgid_plural or msgid
        msgid_match = re.match(r'(msgid_plural|msgid)\s+"(.+)"', line)
        if msgid_match:
            is_plural = msgid_match.group(1) == 'msgid_plural'
            msgid_base = msgid_match.group(1)
            msgid_content = msgid_match.group(2)
            
            # Append the msgid line
            result.append(line)
            i += 1
            
            # Handle multiline msgid
            while i < len(lines) and lines[i].startswith('"') and not lines[i].startswith('msgstr'):
                msgid_content += lines[i]
                result.append(lines[i])
                i += 1
            
            # Extract placeholders from msgid
            placeholder_pattern = r'%\(([a-zA-Z_][a-zA-Z0-9_]*)\)s'
            orig_placeholders = re.findall(placeholder_pattern, msgid_content)
            
            # Process corresponding msgstr
            if i < len(lines) and re.match(r'msgstr(\[\d+\])?\s+"', lines[i]):
                # Handle potentially multiple msgstr (for plurals)
                while i < len(lines) and re.match(r'msgstr', lines[i]):
                    msgstr_line = lines[i]
                    msgstr_match = re.match(r'(msgstr(?:\[\d+\])?)\s+"(.+)"', msgstr_line)
                    
                    if msgstr_match:
                        msgstr_base = msgstr_match.group(1)
                        msgstr_content = msgstr_match.group(2)
                        
                        # Collect multiline msgstr
                        i += 1
                        while i < len(lines) and lines[i].startswith('"'):
                            msgstr_content += lines[i]
                            i += 1
                        
                        # Find mismatched placeholders in msgstr
                        msgstr_placeholders = re.findall(placeholder_pattern, msgstr_content)
                        
                        # Fix each mismatch
                        for idx, msgstr_ph in enumerate(msgstr_placeholders):
                            if idx < len(orig_placeholders) and msgstr_ph != orig_placeholders[idx]:
                                old_ph = f'%({msgstr_ph})s'
                                new_ph = f'%({orig_placeholders[idx]})s'
                                msgstr_content = msgstr_content.replace(old_ph, new_ph, 1)
                                fixes_made += 1
                        
                        # Reconstruct msgstr line(s)
                        # Split content by lines if it's very long
                        if len(msgstr_content) > 100:
                            # Wrap long lines
                            parts = [msgstr_content[i:i+80] for i in range(0, len(msgstr_content), 80)]
                            result.append(f'{msgstr_base} "{parts[0]}"')
                            for part in parts[1:]:
                                result.append(f'"{part}"')
                        else:
                            result.append(f'{msgstr_base} "{msgstr_content}"')
                    else:
                        result.append(msgstr_line)
                        i += 1
            else:
                # No msgstr found, just continue
                pass
        else:
            result.append(line)
            i += 1
    
    return '\n'.join(result), fixes_made


# Fix all .po files
po_dir = Path('yonca/translations')
total_fixes = 0

for po_file in po_dir.glob('*/LC_MESSAGES/messages.po'):
    print(f'Fixing: {po_file}')
    
    with open(po_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    fixed_content, fixes = fix_po_content(content)
    total_fixes += fixes
    
    with open(po_file, 'w', encoding='utf-8') as f:
        f.write(fixed_content)
    
    print(f'  ✓ Fixed {fixes} placeholder issues')

print(f'\n✓ Total fixes made: {total_fixes}')
