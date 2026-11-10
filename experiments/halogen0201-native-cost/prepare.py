"""Verify/export an inert CPU-only candidate into a NEW directory outside this repo.

No model execution, compilation, installation, credential copying or lifecycle API.
"""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
PATCH_SHA256 = '4dbf44a0cdaded91706ecb2d52dc840235c8a209513af7cea37cb8da409944ef'
RULE = 'HALOGEN_MTP_GATE_RULE'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    path = Path(path)
    if not path.is_file() or any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise ValueError('Source must be an ordinary unlinked file: ' + str(path))
    return path.read_bytes()


def candidate_bytes(source):
    source = Path(source).resolve()
    patch_raw = regular(HERE / 'changes.json')
    if digest(patch_raw) != PATCH_SHA256:
        raise ValueError('Experiment byte-patch metadata changed')
    patch = json.loads(patch_raw)
    manifest_raw = regular(source / 'profiles/sources.json')
    if digest(manifest_raw) != patch['baseline_source_manifest_sha256']:
        raise ValueError('Require the exact original 0.20.1 source manifest')
    manifest = json.loads(manifest_raw)
    if manifest['version'] != '0.20.1' or len(manifest['files']) != 47:
        raise ValueError('Unexpected source inventory')
    files = {}
    for name, expected in manifest['files'].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or not relative.parts or relative.parts[0] == '.local':
            raise ValueError('Unsafe source member')
        raw = regular(source / name)
        if digest(raw) != expected:
            raise ValueError('Baseline source bytes changed: ' + name)
        files[name] = raw
    for op in patch['operations']:
        raw = files[op['path']]
        if digest(raw) != op['before_sha256'] or len(raw) != op['before_bytes']:
            raise ValueError('Patch baseline differs')
        remove = base64.b64decode(op['remove_base64'], validate=True)
        insert = base64.b64decode(op['insert_base64'], validate=True)
        offset = op['offset']
        if type(offset) is not int or not 0 <= offset <= len(raw) or raw[offset:offset + len(remove)] != remove:
            raise ValueError('Patch byte range differs')
        raw = raw[:offset] + insert + raw[offset + len(remove):]
        if digest(raw) != op['after_sha256'] or len(raw) != op['after_bytes']:
            raise ValueError('Patched source bytes differ')
        files[op['path']] = raw
        manifest['files'][op['path']] = digest(raw)
    files['profiles/sources.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    if digest(files['profiles/sources.json']) != patch['candidate_source_manifest_sha256']:
        raise ValueError('Regenerated candidate manifest differs')
    return files


def export_candidate(source, output):
    # Verify everything before creating even the output directory.
    source = Path(source).resolve()
    output = Path(output).resolve()
    files = candidate_bytes(source)
    if (output.exists() or output.is_relative_to(source) or source.is_relative_to(output)
            or output.is_relative_to(REPOSITORY) or any(p.name.lower() == 'backends' for p in (output, *output.parents))):
        raise ValueError('Output must be a new experiment directory outside repositories/backends')
    output.mkdir(parents=True)
    for name, raw in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return files


def profile_for_arm(current, arm):
    if arm not in ('before', 'candidate', 'after'):
        raise ValueError('Unknown experiment arm')
    result = copy.deepcopy(current)
    result['engine']['kernel_controls']['HALOGEN_DRAFT_VOCAB_Q8'] = 0
    result['engine']['speculation_policy'][RULE] = 'cost' if arm == 'candidate' else 'gate'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--write-output', type=Path)
    args = parser.parse_args()
    files = (export_candidate(args.source, args.write_output) if args.write_output
             else candidate_bytes(args.source))
    print(json.dumps(dict(source_members=47, candidate_files=len(files), active=False,
        written=args.write_output is not None, candidate_manifest_sha256=digest(files['profiles/sources.json']))))


if __name__ == '__main__':
    main()
