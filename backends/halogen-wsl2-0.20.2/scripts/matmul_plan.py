"""Read-only validator for the pinned Halogen 0.16.2 HGNTUNE3 envelope.

Layout comes from static inspection of ac123b7...f3b, not a public plan spec.
Records remain opaque: this validates no kernel index, floating-point field or
numerical quality. No library or accelerator is loaded. File identity is stable
over this read only; callers must revalidate immediately before using the seal.
The read-only flag describes metadata, not a proof about all users' write ACLs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys

MAGIC = b'HGNTUNE3'
HEADER = struct.Struct('<8sIii32s')
RECORD_BYTES = 64
MAX_RECORDS = 65536
MAX_BYTES = HEADER.size + RECORD_BYTES * MAX_RECORDS
DEFAULT_MAX_RECORDS = 4096
DEFAULT_MAX_BYTES = 1024 * 1024
MAX_LOG_BYTES = 16 * 1024 * 1024
NATIVE_REFUSALS = (
    'absent', 'cannot write', 'unreadable', 'older format', 'ignored',
    'tuned elsewhere', 'tuned on a', 'will be rewritten', 'will be written',
)


def file_identity(info):
    return dict(size=info.st_size, device=info.st_dev, inode=info.st_ino,
                mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns,
                mode=info.st_mode, attributes=getattr(info, 'st_file_attributes', 0))


def _safe_path(value):
    supplied = Path(value)
    if '..' in supplied.parts:
        raise ValueError('Parent traversal paths are refused')
    path = Path(os.path.abspath(supplied))
    for node in reversed((path, *path.parents)):
        info = node.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Symlink/reparse paths are refused')
    return path


def _read_bounded(path, maximum):
    path = _safe_path(path)
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    with os.fdopen(os.open(path, flags), 'rb', buffering=0) as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise ValueError('Not a regular file within the byte budget')
        data = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    if len(data) != before.st_size or file_identity(before) != file_identity(after):
        raise ValueError('File is truncated, growing or changed during validation')
    path = _safe_path(path)
    with os.fdopen(os.open(path, flags), 'rb', buffering=0) as stream:
        current = os.fstat(stream.fileno())
    if file_identity(after) != file_identity(current):
        raise ValueError('File path identity changed during validation')
    return data, file_identity(current)


def native_diagnostic_refusals(text):
    """Classify a complete captured log snapshot without reading a live file."""
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_LOG_BYTES:
        raise ValueError('Native log snapshot exceeds the byte budget')
    refusals = []
    for line in text.splitlines():
        lowered = line.lower()
        if 'hipblaslt tuning file' in lowered and any(word in lowered for word in NATIVE_REFUSALS):
            if len(refusals) < 16:
                refusals.append(line[:1024])
    return refusals


def check_native_diagnostics(log_paths):
    """Return refusal lines from bounded logs; this does not assert log completeness."""
    refusals = []
    paths = list(log_paths)
    if len(paths) > 8:
        raise ValueError('At most eight native logs are accepted')
    for path in paths:
        data, _ = _read_bounded(path, MAX_LOG_BYTES)
        refusals.extend(native_diagnostic_refusals(data.decode('utf-8', errors='replace')))
    refusals = refusals[:16]
    return refusals


def validate_plan(path, *, expected_architecture='gfx1151', expected_wgp_count=20,
                  expected_hipblaslt_version,
                  expected_sha256=None, expected_identity=None, frozen=False,
                  log_paths=(), max_records=DEFAULT_MAX_RECORDS,
                  max_bytes=DEFAULT_MAX_BYTES):
    """Validate an extracted/frozen plan and return a JSON-compatible seal.

    Frozen mode requires an expected digest and read-only metadata. It rejects
    native absent/stale/write/mismatch diagnostics when logs are supplied.
    Library identity is supplied by the caller; this function never queries HIP.
    Pinning the containing image/library bytes is additionally the caller's job.
    """
    if (not isinstance(expected_architecture, str) or
            not re.fullmatch(r'gfx[0-9a-z]{1,27}', expected_architecture)):
        raise ValueError('Expected architecture must be an explicit gfx name')
    for name, value, limit in (('WGP count', expected_wgp_count, 1024),
                               ('library version', expected_hipblaslt_version, 2**31 - 1),
                               ('record budget', max_records, MAX_RECORDS),
                               ('byte budget', max_bytes, MAX_BYTES)):
        if type(value) is not int or not 1 <= value <= limit:
            raise ValueError('Invalid explicit ' + name)
    if type(frozen) is not bool:
        raise ValueError('Frozen mode must be a boolean')
    if expected_sha256 is not None and (not isinstance(expected_sha256, str) or
                                       not re.fullmatch(r'[0-9a-f]{64}', expected_sha256)):
        raise ValueError('Expected SHA256 must be 64 lowercase hex characters')
    if frozen and expected_sha256 is None:
        raise ValueError('Frozen mode requires an expected SHA256')
    log_paths = list(log_paths)
    data, identity = _read_bounded(path, max_bytes)
    if len(data) < HEADER.size:
        raise ValueError('Short HGNTUNE3 header')
    magic, count, version, wgp, raw_arch = HEADER.unpack_from(data)
    if magic != MAGIC or not 1 <= count <= max_records:
        raise ValueError('Unexpected plan magic or bucket count')
    if len(data) != HEADER.size + RECORD_BYTES * count:
        raise ValueError('Plan length does not match its exact bucket count')
    # Native header construction zero-fills the full field before snprintf.
    arch_bytes = expected_architecture.encode('ascii')
    if raw_arch != arch_bytes + b'\0' * (32 - len(arch_bytes)):
        raise ValueError('Architecture or its zero padding does not match')
    if version != expected_hipblaslt_version or wgp != expected_wgp_count:
        raise ValueError('Unexpected hipBLASLt version or WGP count')
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError('Plan SHA256 does not match its seal')
    if expected_identity is not None and identity != expected_identity:
        raise ValueError('Plan file identity does not match its seal')
    readonly = bool(identity['attributes'] & 1) if os.name == 'nt' else not bool(identity['mode'] & 0o222)
    if frozen and not readonly:
        raise ValueError('Frozen plan lacks read-only file metadata')
    refusals = check_native_diagnostics(log_paths)
    if frozen and refusals:
        raise ValueError('Frozen plan native diagnostic refusal: ' + '; '.join(refusals))
    return dict(schema=1, validated=True, frozen=frozen, sha256=digest, size_bytes=len(data),
                identity=identity, readonly_metadata=readonly,
                header=dict(magic=MAGIC.decode(), bucket_count=count,
                            hipblaslt_version=version, wgp_count=wgp, architecture=expected_architecture),
                records_validation='opaque_envelope_only', native_refusals=refusals,
                logs_checked=len(log_paths),
                readonly_acl_effectiveness='unproven', numerical_quality='unqualified')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--expected-arch', required=True)
    parser.add_argument('--expected-wgp', type=int, required=True)
    parser.add_argument('--expected-library-version', type=int, required=True)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--expected-identity-json', type=Path)
    parser.add_argument('--frozen', action='store_true')
    parser.add_argument('--native-log', type=Path, action='append', default=[])
    parser.add_argument('--max-records', type=int, default=DEFAULT_MAX_RECORDS)
    parser.add_argument('--max-bytes', type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args(argv)
    try:
        expected_identity = None
        if args.expected_identity_json:
            raw, _ = _read_bounded(args.expected_identity_json, 65536)
            expected_identity = json.loads(raw)['identity']
        result = validate_plan(args.plan, expected_architecture=args.expected_arch,
                               expected_wgp_count=args.expected_wgp,
                               expected_hipblaslt_version=args.expected_library_version,
                               expected_sha256=args.expected_sha256,
                               expected_identity=expected_identity, frozen=args.frozen,
                               log_paths=args.native_log, max_records=args.max_records,
                               max_bytes=args.max_bytes)
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps(dict(schema=1, validated=False, error=str(error))), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
