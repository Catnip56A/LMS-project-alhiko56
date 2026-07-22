#!/usr/bin/env python3
"""
Fix placeholder name mismatches in translated .po files.

After auto-translation, placeholder names like %(username)s or {count} may
be translated by the engine. This script restores the original names by
matching placeholders positionally. Skips entries where the placeholder
count differs between msgid and msgstr (can't fix safely).
"""
import re
import sys
from pathlib import Path

try:
    import polib
except ImportError:
    print("Error: polib is required. Install with: uv add polib")
    sys.exit(1)


_PY_PH = re.compile(r'%\(([a-zA-Z_][a-zA-Z0-9_]*)\)s')
_JINJA_PH = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')
# Matches leftover protection artifacts from old {PROTECTED_N} / {PROTECTED N} scheme
_BROKEN_PROTECTED = re.compile(r'\{PROTECTED[_\s]*\d+\}')


def fix_msgstr(msgid: str, msgstr: str) -> tuple[str, int]:
    """Restore placeholder names in msgstr to match those in msgid.

    Returns (fixed_msgstr, number_of_fixes).
    """
    if not msgstr:
        return msgstr, 0

    fixes = 0

    for pattern in (_PY_PH, _JINJA_PH):
        correct = pattern.findall(msgid)
        wrong = pattern.findall(msgstr)

        if not correct or len(correct) != len(wrong):
            continue

        for src, dst in zip(wrong, correct):
            if src == dst:
                continue
            if pattern is _PY_PH:
                msgstr = msgstr.replace(f'%({src})s', f'%({dst})s')
            else:
                msgstr = msgstr.replace(f'{{{src}}}', f'{{{dst}}}')
            fixes += 1

    return msgstr, fixes


def fix_protected_artifacts(msgstr: str) -> tuple[str, int]:
    """Replace leftover {PROTECTED N} / {PROTECTED_N} artifacts with 'Yonca'."""
    count = len(_BROKEN_PROTECTED.findall(msgstr))
    return _BROKEN_PROTECTED.sub('Yonca', msgstr), count


def fix_po_file(po_path: Path) -> int:
    po = polib.pofile(str(po_path))
    total = 0

    for entry in po:
        if not entry.msgid or not entry.translated():
            continue

        if entry.msgstr_plural:
            for idx, msgstr in entry.msgstr_plural.items():
                s, n1 = fix_protected_artifacts(msgstr)
                s, n2 = fix_msgstr(entry.msgid, s)
                entry.msgstr_plural[idx] = s
                total += n1 + n2
        else:
            s, n1 = fix_protected_artifacts(entry.msgstr)
            s, n2 = fix_msgstr(entry.msgid, s)
            entry.msgstr = s
            total += n1 + n2

    if total:
        po.save()

    return total


def main() -> None:
    po_dir = Path(__file__).parent.parent.parent / 'lms' / 'translations'
    grand_total = 0

    for po_file in sorted(po_dir.glob('*/LC_MESSAGES/messages.po')):
        rel = po_file.relative_to(po_dir.parent.parent)
        print(f'Checking: {rel}')
        fixes = fix_po_file(po_file)
        grand_total += fixes
        print(f'  {"fixed " + str(fixes) + " placeholder(s)" if fixes else "nothing to fix"}')

    print(f'\nTotal fixes: {grand_total}')


if __name__ == '__main__':
    main()
