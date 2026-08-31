#!/usr/bin/env python3
"""SessionStart hook: if .claude/handoff.md exists (written by /handoff at the end of a prior
session), inject its content as additional context so the new session picks up where the last
one left off without the user having to say "read the handoff file" manually.

Reads relative to the current working directory, which Claude Code sets to the project root
before running SessionStart hooks.
"""
import json
import os

path = os.path.join('.claude', 'handoff.md')

if os.path.isfile(path):
    with open(path, encoding='utf-8') as f:
        content = f.read()
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'SessionStart',
            'additionalContext': 'Session handoff from a previous session (.claude/handoff.md):\n\n' + content,
        }
    }))
else:
    print('{}')
