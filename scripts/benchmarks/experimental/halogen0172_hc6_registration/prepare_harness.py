"""Derive a separate frozen comparison; never edit the completed HC6 series."""
import hashlib
import json
from pathlib import Path

WORK = Path(__file__).resolve().parent
OLD = WORK.parent/'hc6-register-remap-v1'

def derive(name, replacements):
    source = OLD/name
    text = source.read_text()
    for before, after in replacements:
        assert before in text, (name,before)
        text = text.replace(before,after)
    dest = WORK/name
    assert not dest.exists(),dest
    dest.write_text(text,encoding='utf-8',newline='\n')
    return dict(file=name,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                derived_sha256=hashlib.sha256(dest.read_bytes()).hexdigest())

if __name__ == '__main__':
    shared=[('active0172_hc6_remap_comparison','active0172_hc6_registration_comparison')]
    entries=[derive('control.py',shared),derive('final_stock.py',shared),
             derive('window.py',[("manifest['hc6_register_remap_candidate']['enabled'] and manifest['environment']['HG0172_HC6_REMAP_CODE']=='/candidate/hc6-register-remap.hsaco'",
                 "manifest['hc6_registration_candidate']['enabled'] and manifest['environment']['HG0172_HC6_REGISTER_REMAP']=='1'")])]
    (WORK/'harness-derivation.json').write_text(json.dumps(entries,indent=2)+'\n')
    print(json.dumps(dict(derived=len(entries),frozen_workload_unchanged=True)))
