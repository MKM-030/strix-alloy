"""Bind a Windows N-Gram hash receipt to its exact WSL file projection."""

import json
import os
from pathlib import Path
import re
import tempfile

import portable
from state_io import read_json


RECEIPT_NAME = 'ngram-ntfs-integrity.json'
MOUNT = '/ngram-w4b.hgn'
IDENTITY_FIELDS = ('device', 'inode', 'size', 'mtime_ns', 'ctime_ns')
PROOF_MODES = ('full_sha256', 'ntfs_receipt')
MAX_RECEIPT_BYTES = 16 * 1024

_OBSERVE = r"""
import json, os, pathlib, stat, subprocess, sys

path = sys.argv[1]
if str(pathlib.Path(path).resolve(strict=True)) != path:
    raise ValueError('N-Gram source must use its canonical DrvFS path')

def identity(result):
    if not stat.S_ISREG(result.st_mode):
        raise ValueError('N-Gram source must be a regular file')
    return dict(size=result.st_size, device=result.st_dev, inode=result.st_ino,
                mtime_ns=result.st_mtime_ns, ctime_ns=result.st_ctime_ns)

fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
try:
    before = identity(os.fstat(fd))
    mount, = json.loads(subprocess.check_output(
        ['findmnt', '--json', '--first-only', '--target', path,
         '--output', 'SOURCE,TARGET,FSTYPE,FSROOT'], text=True, timeout=5))['filesystems']
    windows_path = subprocess.check_output(['wslpath', '-w', path], text=True, timeout=5).rstrip('\r\n')
    if identity(os.fstat(fd)) != before or identity(os.stat(path, follow_symlinks=False)) != before:
        raise ValueError('N-Gram source changed during DrvFS observation')
    print(json.dumps(dict(identity=before, mount=mount, windows_path=windows_path)))
finally:
    os.close(fd)
"""


def drvfs_path(source):
    match = re.fullmatch(r'/mnt/([a-z])/([^:*?<>|]+)', source)
    if match is None:
        return None
    drive = match[1].upper() + ':\\'
    return drive + match[2].replace('/', '\\'), {
        'source': drive, 'target': '/mnt/' + match[1], 'fstype': '9p', 'fsroot': '/',
    }


def valid_identity(identity, size):
    return (type(identity) is dict and identity.keys() == set(IDENTITY_FIELDS)
            and all(type(value) is int and value > 0 for value in identity.values())
            and identity['size'] == size)


def observe(machine, source, projection, size):
    windows_path, mount = projection
    result = json.loads(portable.wsl(machine['distro'], machine['user'], 'python3', '-B', '-c',
                                     _OBSERVE, source, timeout=16))
    if (type(result) is not dict or result.get('windows_path') != windows_path
            or result.get('mount') != mount or not valid_identity(result.get('identity'), size)):
        raise ValueError('N-Gram path does not resolve to the expected local DrvFS source')
    return result['identity']


def read_receipt(path):
    portable.reject_links(path)
    def load():
        with path.open('rb') as stream:
            data = stream.read(MAX_RECEIPT_BYTES + 1)
        if len(data) > MAX_RECEIPT_BYTES:
            raise ValueError('N-Gram receipt exceeds its byte limit')
        return data
    try:
        return True, read_json(path, load=load)
    except FileNotFoundError:
        return False, None
    except (OSError, ValueError):
        return True, None


def write_receipt(path, receipt):
    portable.reject_links(path)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(receipt, stream, indent=2)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def matches(receipt, source, sha, mount, identity, generation):
    return (type(receipt) is dict and type(receipt.get('schema')) is int and receipt['schema'] == 1
            and receipt.get('source') == source and receipt.get('sha256') == sha
            and receipt.get('mount') == mount and receipt.get('ntfs') == generation
            and valid_identity(receipt.get('identity'), identity['size'])
            and all(receipt['identity'][key] == identity[key] for key in IDENTITY_FIELDS if key != 'device'))


def binding_identity(manifest):
    if 'ngram_ntfs_binding' not in manifest:
        return None
    binding = manifest['ngram_ntfs_binding']
    source = binding.get('source') if type(binding) is dict else None
    if (type(source) is not str or drvfs_path(portable.linux_path(source)) is None
            or binding.keys() != {'source', 'identity', 'mode'}
            or binding['mode'] not in PROOF_MODES or not valid_identity(binding['identity'], portable.MODELS[0][1])
            or manifest['checkpoint'] != 'v2' or 'lookup_tuning' in manifest
            or manifest['mounts'].get(MOUNT) != source
            or manifest['environment'].get('HALOGEN_NGRAM_TABLE') != MOUNT):
        raise ValueError('N-Gram proof does not bind the selected v2 read-only mount')
    return binding['identity']
