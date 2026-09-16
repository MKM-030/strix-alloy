#!/usr/bin/env python3
import json
import os

base = r'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results'
print('=== comments ===')
for c in json.load(open(os.path.join(base, 'pr28941-comments.json'), encoding='utf-8-sig')):
    print(f"[{c['user']['login']}] {(c.get('body') or '')[:700]}")
    print()
print('=== events (why closed?) ===')
for e in json.load(open(os.path.join(base, 'pr28941-events.json'), encoding='utf-8-sig')):
    if e.get('event') in ('closed', 'merged', 'commented', 'review_requested'):
        print(f"  {e.get('event')}  by {e.get('actor',{}).get('login')}  {e.get('created_at','')}")
        if e.get('commit_id'):
            print(f"     commit {e['commit_id'][:12]}")
