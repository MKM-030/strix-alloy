"""Verify checkpoints once per file identity; never trust file length alone."""
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess

import ngram_ntfs
import portable

SIZE=66687678432
SHA='71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687'
DRAFTER_NAME='qwen38-flash-next-drafter-r2-ht4.hgn'
DRAFTER_SIZE=1488276864
DRAFTER_SHA='f9aa330800cc921fe20f4cf997d660f519c67b0052af0c8078b6b648972b07e6'
VISION_NAME='qwen38-flash-next-vision.hgn'
VISION_SIZE=897916416
VISION_SHA='d62e0ae553fe88afd3833733d4a4c669f34d20fd8dfce4b9610525bed2134b10'
NGRAM_NAME,NGRAM_SIZE,NGRAM_SHA=portable.MODELS[0]
STAT_CODE="""import json,os,sys
s=os.stat(sys.argv[1])
print(json.dumps(dict(size=s.st_size,device=s.st_dev,inode=s.st_ino,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns)))"""
HASH_CODE=Path(__file__).with_name('bounded_hash.py').read_text(encoding='utf-8')
HASH_MIN_BYTES_PER_SECOND=64*1024**2
HASH_TIMEOUT_FLOOR=600
HASH_TIMEOUT_OVERHEAD=120
HASH_TIMEOUT_CEILING=3600


def hash_timeout(size):
    """Bound full-file hashing by size while allowing slow Windows-mounted media."""
    if type(size) is not int or size <= 0:
        raise ValueError('Hash input size must be a positive integer')
    transfer=(size+HASH_MIN_BYTES_PER_SECOND-1)//HASH_MIN_BYTES_PER_SECOND
    return min(HASH_TIMEOUT_CEILING,
               max(HASH_TIMEOUT_FLOOR,transfer+HASH_TIMEOUT_OVERHEAD))


def receipt_matches(receipt, identity, *, size=SIZE, sha=SHA, source=None):
    return (isinstance(identity,dict)
            and all(type(identity.get(key)) is int for key in ('size','device','inode','mtime_ns','ctime_ns'))
            and isinstance(receipt,dict) and receipt.get('sha256')==sha
            and receipt.get('identity')==identity and identity.get('size')==size
            and (source is None or receipt.get('source')==source))


def _verify_hash(machine, model, identity, size, sha, label, source):
    print('Verifying the complete '+label+' SHA-256 before GPU allocation.',flush=True)
    receipt=json.loads(portable.wsl(machine['distro'],machine['user'],
        'python3','-c',HASH_CODE,model,timeout=hash_timeout(size)))
    if source is not None and isinstance(receipt,dict): receipt['source']=source
    if not receipt_matches(receipt,identity,size=size,sha=sha,source=source):
        raise ValueError(label+' checksum or file identity does not match the pinned checkpoint')
    return receipt


def _verify_file(machine, local, model, name, size, sha, label, bind_source=False, *, force_hash=False):
    receipt_path=Path(local)/name
    portable.reject_links(receipt_path)
    source=model if bind_source else None
    identity=json.loads(portable.wsl(machine['distro'],machine['user'],
        'python3','-c',STAT_CODE,model,timeout=30))
    if not isinstance(identity,dict) or identity.get('size')!=size:
        raise ValueError(label+' is incomplete or has the wrong size')
    if not force_hash and receipt_path.exists():
        receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
        if receipt_matches(receipt,identity,size=size,sha=sha,source=source): return receipt
    receipt=_verify_hash(machine,model,identity,size,sha,label,source)
    temporary=receipt_path.with_suffix('.tmp')
    portable.reject_links(temporary)
    temporary.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    temporary.replace(receipt_path)
    return receipt


def verify(machine, local):
    return _verify_file(machine,local,machine['models']+'/qwen38-flash-next-v2.hgn',
                        'v2-integrity.json',SIZE,SHA,'v2 checkpoint')


def verify_drafter(machine, local):
    return _verify_file(machine,local,machine['models']+'/'+DRAFTER_NAME,
                        'r2-integrity.json',DRAFTER_SIZE,DRAFTER_SHA,'r2 draft head')


def verify_vision(machine, local):
    return _verify_file(machine,local,machine['models']+'/'+VISION_NAME,
                        'vision-integrity.json',VISION_SIZE,VISION_SHA,'vision tower')


def _verify_ngram_ntfs(machine, local, source, startup_leases):
    from ntfs_file_generation import NtfsGenerationUnavailable, open_read_lease

    projection = ngram_ntfs.drvfs_path(source)
    if projection is None:
        return None, False
    windows_path, mount = projection
    native_path = Path(local) / ngram_ntfs.RECEIPT_NAME
    legacy_path = Path(local) / 'ngram-integrity.json'
    native_exists, previous = ngram_ntfs.read_receipt(native_path)
    with ExitStack() as candidate:
        try:
            identity = ngram_ntfs.observe(machine, source, projection, NGRAM_SIZE)
            if not native_exists:
                _, legacy = ngram_ntfs.read_receipt(legacy_path)
                if receipt_matches(legacy, identity, size=NGRAM_SIZE, sha=NGRAM_SHA, source=source):
                    # The Linux-only receipt already proves this exact WSL generation.
                    return legacy, False
            lease = candidate.enter_context(open_read_lease(windows_path))
            generation = lease.snapshot()
        except (NtfsGenerationUnavailable, OSError, ValueError, subprocess.TimeoutExpired) as exc:
            cause = exc.__cause__ if isinstance(exc, NtfsGenerationUnavailable) else exc
            if getattr(cause, 'winerror', None) in (32, 33):
                raise ValueError('Windows N-Gram source is open for writing or locked') from exc
            return None, native_exists

        if generation.get('eof') != NGRAM_SIZE:
            raise ValueError('Windows N-Gram size disagrees with the verified WSL source')
        if ngram_ntfs.matches(previous, source, NGRAM_SHA, mount, identity, generation):
            verified = dict(sha256=NGRAM_SHA, source=source, identity=identity)
            mode = 'ntfs_receipt'
        else:
            # A legacy receipt can never seed the Windows proof retroactively.
            verified = _verify_hash(machine, source, identity, NGRAM_SIZE, NGRAM_SHA, 'N-gram source', source)
            mode = 'full_sha256'

        if ngram_ntfs.observe(machine, source, projection, NGRAM_SIZE) != identity or lease.snapshot() != generation:
            raise ValueError('N-Gram source generation changed during NTFS verification')

        if mode == 'full_sha256':
            ngram_ntfs.write_receipt(legacy_path, verified)
            ngram_ntfs.write_receipt(native_path, dict(schema=1, source=source, sha256=NGRAM_SHA,
                mount=mount, identity=identity, ntfs=generation))
        else:
            print('Verified the pinned N-Gram SHA-256 receipt against the current NTFS source.',flush=True)
        startup_leases.enter_context(candidate.pop_all())
        return dict(verified, ntfs_mount_binding=dict(source=source, identity=identity, mode=mode)), False


def verify_ngram(machine, local, *, startup_leases=None):
    source=portable.linux_path(machine.get('ngram_source') or machine['models']+'/'+NGRAM_NAME)
    force_hash = False
    if startup_leases is not None and machine.get('ngram_source'):
        # Once a native receipt exists, unavailable journal evidence must not
        # revive a Linux-only fast path for an older native file generation.
        result, force_hash = _verify_ngram_ntfs(machine, local, source, startup_leases)
        if result is not None:
            return result
    return _verify_file(machine,local,source,'ngram-integrity.json',
                        NGRAM_SIZE,NGRAM_SHA,'N-gram source',bind_source=True,force_hash=force_hash)
