#!/usr/bin/env python3
"""Extract readable text from a saved domSnapshot JSON artifact (handles real newlines)."""
import json
import re
import sys

path = sys.argv[1]
raw = open(path, 'r', encoding='utf-8', errors='ignore').read()
try:
    obj = json.loads(raw)
except Exception as e:
    print('json load failed:', e)
    print(raw[:500])
    sys.exit(0)

text = obj if isinstance(obj, str) else json.dumps(obj)
drop = re.compile(r'(/url:|Skip to|Sign Up|Log In|Expand user menu|button "(Upvote|Downvote|Reply|Share|Give award|Open user actions|Back|Sort by|Search Comments)|img "|avatar|redditinc|alb\.reddit\.com|Privacy Policy|User Agreement|Accessibility|Impressum|Cookie|cookie|Continue with|iframe|dialog|placeholder)')
lines = []
for line in text.splitlines():
    s = line.rstrip()
    if not s.strip() or drop.search(s):
        continue
    lines.append(s)
print('\n'.join(lines))
