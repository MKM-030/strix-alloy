"""Verify the inert source delta and exact reused-file references; no runtime."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
TEXT_SUFFIXES = {'.py', '.c', '.h', '.hpp', '.S', '.json', '.md', '.sh', '.map'}


def checked(root, relative):
    path = root / relative
    if (not path.is_file() or not path.resolve().is_relative_to(root.resolve())
            or any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)()
                   for p in (path, *path.parents))):
        raise ValueError('Missing, linked or escaping source: ' + str(path))
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    manifest_path = checked(HERE, 'source-manifest.json')
    manifest = json.loads(manifest_path.read_bytes())
    if (manifest['source_only'] is not True or manifest['default_enabled'] is not False
            or manifest['standalone_installer'] is not False):
        raise ValueError('Archive must remain inactive source only')
    total = 0
    for relative, expected in manifest['members'].items():
        path = checked(HERE, relative)
        if ((path.suffix not in TEXT_SUFFIXES and path.name != '.gitattributes')
                or digest(path) != expected):
            raise ValueError('Archive source identity/type differs: ' + relative)
        path.read_bytes().decode('utf-8')
        total += path.stat().st_size
    references = manifest['referenced_unchanged_sources']
    targets = set(manifest['members'])
    saved_bytes = 0
    for row in references:
        path = checked(ROOT, row['existing_archive_source'])
        if (digest(path) != row['sha256'] or path.stat().st_size != row['bytes']
                or row['materialize_as'] in targets):
            raise ValueError('Reused source identity/target differs: ' + row['materialize_as'])
        targets.add(row['materialize_as'])
        saved_bytes += row['bytes']
    excluded = {'source-manifest.json', 'verification-result.json'}
    actual = {p.relative_to(HERE).as_posix() for p in HERE.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'
              and p.relative_to(HERE).as_posix() not in excluded}
    if actual != set(manifest['members']):
        raise ValueError('Unlisted or missing archive payload')
    partial = manifest['actual_cohort']
    if (partial['excluded_stock_warmups'] != 1 or partial['measured_requests'] != 0
            or partial['NPU_helper_started'] is not False
            or partial['qualified_NPU_on_off_comparison'] is not False):
        raise ValueError('Actual partial cohort must not become a qualified result')
    return dict(schema='halogen0203.source-delta-verification.v1', valid=True,
                source_members=len(manifest['members']), source_bytes=total,
                exact_reused_references=len(references), duplicate_bytes_avoided=saved_bytes,
                source_manifest_sha256=digest(manifest_path), compiler_or_engine_run=False,
                hardware_or_HTTP_called=False, binaries_models_credentials_or_runtime_files_copied=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if not args.verify:
        print(json.dumps(dict(source_only=True, verified=False, runtime_calls=0, files_written=0)))
        return 0
    result = verify()
    if args.output is not None:
        output = args.output.resolve()
        if output != HERE / 'verification-result.json':
            raise ValueError('Only the archive local verification result may be written')
        with output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
