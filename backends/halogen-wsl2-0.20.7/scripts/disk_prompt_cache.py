"""Bind the optional on-disk cache to one private native WSL directory."""

import json
from pathlib import PurePosixPath

import portable


DIRECTORY = '.strix-alloy-halogen-prompt-cache'
DESTINATION = '/var/lib/halogen-private-prompt-cache'
BUDGET_GIB = 1
ENVIRONMENT = {
    'HALOGEN_CACHE_DIR': DESTINATION,
    'HALOGEN_CACHE_DISK_GIB': str(BUDGET_GIB),
    'HALOGEN_CACHE_PRUNE_OLD': '0',
}
RECORD_FIELDS = {'path', 'uid', 'gid', 'dev', 'ino'}

_DIRECTORY_PROBE = r"""
import json, os, pwd, stat, subprocess, sys
from pathlib import Path

home = Path(pwd.getpwuid(os.geteuid()).pw_dir)
if not home.is_absolute() or home.resolve(strict=True) != home:
    raise ValueError("WSL home must be a real directory")
path = home / sys.argv[1]
if sys.argv[2] == "prepare":
    path.mkdir(mode=0o700, exist_ok=True)
fd = os.open(path, os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
try:
    info = os.fstat(fd)
    if stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.geteuid():
        raise ValueError("Prompt cache directory must be owned by the WSL user and have mode 0700")
    if path.resolve(strict=True) != path or not os.access(path, os.W_OK | os.X_OK):
        raise ValueError("Prompt cache directory must be writable and unaliased")
    mount, = json.loads(subprocess.check_output(
        ["findmnt", "--json", "--first-only", "--target", str(path), "--output", "FSTYPE,OPTIONS"],
        text=True, timeout=5))["filesystems"]
    if mount["fstype"] != "ext4" or "rw" not in mount["options"].split(","):
        raise ValueError("Persistent prompt cache requires a writable native WSL ext4 directory")
    end = path.stat(follow_symlinks=False)
    if (end.st_dev, end.st_ino) != (info.st_dev, info.st_ino):
        raise ValueError("Prompt cache directory changed during validation")
    print(json.dumps(dict(path=str(path), uid=info.st_uid, gid=info.st_gid, dev=info.st_dev, ino=info.st_ino)))
finally:
    os.close(fd)
"""

_BOUND_DIRECTORY_STAT = r"""
import json, os, stat, sys

info = os.stat(sys.argv[1], follow_symlinks=False)
if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
    raise ValueError("Unexpected bound prompt cache directory")
print(json.dumps(dict(uid=info.st_uid, gid=info.st_gid, dev=info.st_dev, ino=info.st_ino)))
"""


def validate_scope(checkpoint, context, mode, disable_vision, prefill_chunk, max_prefill_tokens, explicit_capacity):
    if not (checkpoint == 'v2' and context == 32768 and mode == 'Flexible'
            and disable_vision is True and prefill_chunk == max_prefill_tokens == 8192
            and not explicit_capacity):
        raise ValueError('Persistent prompt cache requires v2, Flexible, text-only 32K, and paired 8192 prefill')


def validate_record(record):
    if type(record) is not dict or record.keys() != RECORD_FIELDS:
        raise ValueError('Invalid prompt cache directory record')
    source = portable.linux_path(record['path'], native=True)
    if PurePosixPath(source).name != DIRECTORY:
        raise ValueError('Unexpected prompt cache directory')
    if any(type(record[key]) is not int or record[key] < 0 for key in ('uid', 'gid', 'dev', 'ino')) \
            or not record['ino']:
        raise ValueError('Invalid prompt cache directory identity')
    return source


def _observe(machine, prepare=False):
    command = portable.wsl_command(machine['distro'], machine['user'], [
        'python3', '-B', '-c', _DIRECTORY_PROBE, DIRECTORY, 'prepare' if prepare else 'observe',
    ])
    record = json.loads(portable.run(command, timeout=12))
    validate_record(record)
    return record


def bind(manifest, machine):
    if ENVIRONMENT.keys() & manifest['environment'].keys():
        raise ValueError('Duplicate prompt cache environment')
    manifest['disk_prompt_cache'] = _observe(machine, prepare=True)
    manifest['environment'].update(ENVIRONMENT)
    validate_manifest(manifest)


def validate_manifest(manifest):
    env = manifest.get('environment', {})
    mounts = manifest.get('mounts', {})
    if 'disk_prompt_cache' not in manifest:
        if ENVIRONMENT.keys() & env.keys() or DESTINATION in mounts:
            raise ValueError('Persistent prompt cache requires an admitted directory')
        return None
    source = validate_record(manifest['disk_prompt_cache'])
    if (manifest.get('checkpoint') != 'v2' or manifest.get('context') != 32768
            or manifest.get('slots') != 1 or 'kv_pool_positions' in manifest
            or env.get('HALOGEN_PROMPT_CACHE') != '2' or env.get('HALOGEN_VISION_TOWER')
            or env.get('HALOGEN_PREFILL_CHUNK') != '8192' or env.get('HALOGEN_MAX_TOK') != '8192'
            or env.get('HALOGEN_CACHE_FILE')
            or any(env.get(key) != value for key, value in ENVIRONMENT.items())):
        raise ValueError('Unexpected persistent prompt cache settings')
    if (any(dest == DESTINATION or dest.startswith(DESTINATION + '/') or DESTINATION.startswith(dest + '/')
            for dest in mounts)
            or any(path == source or path.startswith(source + '/') or source.startswith(path + '/')
                   for path in mounts.values())):
        raise ValueError('Prompt cache overlaps a read-only mount')
    return source


def revalidate(manifest, machine):
    if validate_manifest(manifest) is not None and _observe(machine) != manifest['disk_prompt_cache']:
        raise ValueError('Prompt cache directory identity changed')


def verify_binding(manifest, docker, container_id):
    source = manifest['disk_prompt_cache']
    bound = json.loads(docker('exec', container_id, 'python3', '-B', '-c',
                              _BOUND_DIRECTORY_STAT, DESTINATION, timeout=12))
    if bound != {key: source[key] for key in ('uid', 'gid', 'dev', 'ino')}:
        raise ValueError('Bound prompt cache directory identity changed')


def check_cache_stats(value):
    disk = value.get('disk') if isinstance(value, dict) else None
    if not isinstance(disk, dict) or disk.get('on') is not True or disk.get('budget_bytes') != (BUDGET_GIB << 30):
        raise ValueError('Halogen did not enable the configured disk prompt cache')
    root = value.get('cache_root')
    root_path = PurePosixPath(portable.linux_path(root, native=True))
    if str(root_path.parent) != DESTINATION:
        raise ValueError('Halogen reported an unexpected disk prompt cache path')
    return {'cache_root': root, 'disk': disk}
