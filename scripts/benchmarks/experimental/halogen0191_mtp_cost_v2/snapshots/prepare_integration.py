"""Prepare the finite combined RAW, trace and cost-rule source bundle only."""
import copy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIMARY = HERE.parent
Q8 = PRIMARY / 'next-mechanisms-1722/q8-candidate'
COST = PRIMARY / 'continuation-1904/cost-gate-candidate'
Q8_SHA = 'ecae649e6e437f71ddfd53a891aea4344629f361c712f5e67773df561a93c32b'
COST_SHA = 'aff4edf09486f6521fcc3f696321d3ebd877f7dc768db7cea683c6c17ffad827'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(path, expected):
    if not path.is_file() or path.is_symlink() or path.is_junction():
        raise ValueError('Missing or linked finite input ' + str(path))
    data = path.read_bytes()
    if sha(data) != expected:
        raise ValueError('Pinned input differs ' + str(path))
    return data


def prepare():
    q8 = json.loads(checked(Q8 / 'transition.json', Q8_SHA))
    cost = json.loads(checked(COST / 'transition.json', COST_SHA))
    if q8['baseline'] != cost['baseline']:
        raise ValueError('Combined source baselines differ')
    candidate = {name: checked(Q8 / 'candidate' / name, digest) for name, digest in q8['candidate'].items()}
    rollback = {name: checked(Q8 / 'rollback' / name, digest) for name, digest in q8['rollback_restore'].items()}
    candidate['scripts/speculation_policy.py'] = checked(COST / 'candidate/scripts/speculation_policy.py',
        cost['candidate']['scripts/speculation_policy.py'])
    service = candidate['scripts/service.py']
    cost_service = checked(COST / 'candidate/scripts/service.py', cost['candidate']['scripts/service.py'])
    start = cost_service.index(b'    policy = sp.validate(m.get(')
    end = cost_service.index(b"    for key in ('private_hsa', 'matmul_tuning'):", start)
    anchor = b'    cp.validate_manifest(m)\r\n'
    if service.count(anchor) != 1:
        raise ValueError('Combined service source anchor differs')
    candidate['scripts/service.py'] = service.replace(anchor, anchor + cost_service[start:end])
    manifest = json.loads(candidate['profiles/sources.json'])
    for name in ('scripts/service.py', 'scripts/speculation_policy.py'):
        compile(candidate[name], name, 'exec', dont_inherit=True)
        manifest['files'][name] = sha(candidate[name])
    candidate['profiles/sources.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    transition = copy.deepcopy(q8)
    for name in ('q8_controls', 'q8_delta_from_parent', 'preparation_source_pins'):
        transition.pop(name, None)
    transition.update(experiment='mtp_gate_cost', active=False, operation='prepare-only',
        candidate={name: sha(data) for name, data in candidate.items()},
        candidate_delta={name: sha(data) for name, data in candidate.items()
                         if name not in rollback or data != rollback[name]},
        input_transitions=dict(q8=Q8_SHA, cost=COST_SHA),
        cost_native_proof_pins=cost['native_proof_pins'], measured=False,
        preparation_source_sha256=sha(Path(__file__).read_bytes()))
    output = HERE / 'integration/root-bound'
    for folder, files in (('candidate', candidate), ('rollback', rollback)):
        for name, data in files.items():
            path = output / folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.read_bytes() != data:
                raise ValueError('Existing combined package differs ' + name)
            if not path.exists():
                path.write_bytes(data)
    data = (json.dumps(transition, indent=2) + '\n').encode()
    path = output / 'transition.json'
    if path.exists() and path.read_bytes() != data:
        raise ValueError('Existing combined transition differs')
    if not path.exists():
        path.write_bytes(data)
    print(json.dumps(dict(candidate_files=len(candidate), rollback_files=len(rollback),
        source_members=len(manifest['files']), transition_sha256=sha(data)), indent=2))


if __name__ == '__main__':
    prepare()
