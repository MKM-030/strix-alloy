#!/usr/bin/env python3
import json
import os

base = r'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results'
pr = json.load(open(os.path.join(base, 'pr28941.json'), encoding='utf-8-sig'))
print('title   :', pr['title'])
print('state   :', pr['state'], ' merged:', pr.get('merged'))
print('base    :', pr['base']['ref'], ' head_sha:', pr['head']['sha'][:12])
print('files   :', pr['changed_files'], f"+{pr['additions']} -{pr['deletions']}")
print('mergeable:', pr.get('mergeable'), ' draft:', pr.get('draft'))
print('--- body ---')
print((pr.get('body') or '')[:2500])
print('--- files ---')
for f in json.load(open(os.path.join(base, 'pr28941-files.json'), encoding='utf-8-sig')):
    print(f"  {f['filename']}  +{f['additions']} -{f['deletions']}")
    if f.get('patch'):
        print('    ' + f['patch'].replace('\n', '\n    ')[:1500])
