"""Bind one finite original-kernel preparation comparison in the pinned image.

Only Root runs it under an exclusive GPU/job/reserve guard. No model, engine
replacement, NPU, GEMM, serving throughput or acceptance measurement occurs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

CANDIDATE, FIXTURES, RESULT = Path('/candidate'), Path('/fixtures'), Path('/result')
BINARY_SHA = '69142bb40b6434df6abeb9388c2c0bc4ec8dfaaadf221cce2a8ea94b6329bf4b'
SOURCE_SHA = '0fe60be21173d1f2395725da4ea83aa1210b5d492f3e871927b4e00941d89e5b'
ENGINE_SHA = 'ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b'
CODE_SHA = '45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83'
HIP_SHA = '6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5'
BRIDGE_SHA = '0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6'
INPUTS = {
    'packed.bin': (13107200, 'd27fc76fab0646ba5b675f9dd9137c342a39f70aa980acf62f6959f5fdf0245d'),
    'signs-u16.bin': (5120, '0866b9d9d28380f5f6ea3fdc0fa78a5643db9629c8a3e0094eb01f5b3e33cd7c'),
    'scales-u16.bin': (20480, 'dad8e70f72ce13f67692a184cac608e71986d740d43f72201ee52acc4146061e'),
}
IDENTITY_FIELDS = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(value):
    require(isinstance(value, str) and len(value) == 64 and
            all(c in '0123456789abcdef' for c in value), 'Pinned lowercase SHA256 required')
    return value


def binding(path, expected, exact=None, maximum=128 << 20):
    path = Path(path)
    require(path.is_absolute(), 'Absolute file path required')
    sha(expected)
    identity = lambda v: tuple(getattr(v, k) for k in IDENTITY_FIELDS)
    before_path = path.lstat()
    require(stat.S_ISREG(before_path.st_mode), 'Regular file required: ' + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(identity(before) == identity(before_path) and 0 < before.st_size <= maximum and
                (exact is None or before.st_size == exact), 'Pinned file extent/identity differs')
        digest, count = hashlib.sha256(), 0
        while count <= maximum:
            chunk = os.read(fd, min(1 << 20, maximum + 1 - count))
            if not chunk:
                break
            digest.update(chunk)
            count += len(chunk)
        require(count == before.st_size and digest.hexdigest() == expected and
                identity(before) == identity(os.fstat(fd)) == identity(path.lstat()),
                'File bytes or identity changed: ' + str(path))
        return dict(path=str(path), bytes=count, sha256=expected)
    finally:
        os.close(fd)


def installed_hip():
    # The retained image receipt binds a regular .so.7 file. The package does
    # not provide the unversioned symlink assumed by the initial launcher.
    path = Path('/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib/libamdhip64.so.7')
    require(stat.S_ISREG(path.lstat().st_mode), 'Original regular HIP target required')
    return path


def run(args):
    require(os.name == 'posix' and args.outer_exclusive_gpu_guard,
            'Pinned Linux image and Root exclusive guard required')
    require(stat.S_ISDIR(RESULT.lstat().st_mode) and not any(RESULT.iterdir()),
            'Fresh result directory required')
    pins = {}
    pins['wrapper'] = binding(Path(__file__).absolute(), sha(args.wrapper_sha256), maximum=1 << 20)
    pins['source'] = binding(CANDIDATE / 'replay.c', sha(SOURCE_SHA), maximum=1 << 20)
    pins['binary'] = binding(CANDIDATE / 'replay', sha(BINARY_SHA), maximum=8 << 20)
    require(os.access(CANDIDATE / 'replay', os.X_OK), 'Executable replay required')
    pins['engine'] = binding(CANDIDATE / 'flash_serve', ENGINE_SHA, 26052768)
    pins['codeobject'] = binding(CANDIDATE / 'engine-gfx1151.hsaco', CODE_SHA, 17704408)
    pins['bridge'] = binding(Path('/usr/lib/librocdxg.so'), BRIDGE_SHA, maximum=32 << 20)
    library = installed_hip()
    pins['hip'] = binding(library, HIP_SHA)
    for name, (length, digest) in INPUTS.items():
        pins[name] = binding(FIXTURES / name, digest, length)
    command = [str(CANDIDATE / 'replay'), pins['engine']['path'], pins['codeobject']['path'],
               str(library), pins['packed.bin']['path'], pins['signs-u16.bin']['path'],
               pins['scales-u16.bin']['path'], str(RESULT / 'native')]
    require(len(command) == 8, 'Exactly seven native arguments required')
    record = dict(schema='halogen.prefill-deq.runtime-binding.v1', bindings=pins, command=command,
                  outer_exclusive_gpu_guard_acknowledged=True, no_model=True, NPU_executed=False,
                  serving_prefill_tok_s=None, serving_decode_tok_s=None, native_acceptance=None)
    fd = os.open(RESULT / 'runtime.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(record, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.execv(command[0], command)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wrapper-sha256', required=True)
    parser.add_argument('--outer-exclusive-gpu-guard', action='store_true')
    run(parser.parse_args())
