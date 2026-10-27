"""Explicit standalone lookup qualification; stock configuration is never changed."""
import hashlib
import inspect
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_ROOTS = (ROOT / '.local', ROOT.parents[1] / 'server/.local')
OUTPUT_BYTES = 51200246144
PAYLOAD_BYTES = 51200245764
SOURCE_BYTES = 124068083904
SOURCE_SHA = '9c116bbc01f77b7a15464c1a124eb3325b286089b8a2a6f2856c9b246a235bd6'
TENSOR_NAME = 'layers.1.ple.ngram_embedding.weight'
IDENTITY_KEYS = ('size', 'device', 'inode', 'mtime_ns', 'ctime_ns')
MAX_RECEIPT_BYTES = 128 * 1024
CANONICAL_RECEIPT_SHA = 'df0dc1e5d2de921b58c4f18f988624687191ec6f80e2336c90c7de454144c7fb'
CANONICAL_RECEIPT_RELATIVE = 'server/.local/optimization9h-20261004/lookup-native-copy-9447b9641f964497980fcb281b18a5c3/extraction.receipt.json'
TRUSTED_CACHE_KEY = 'cad72bf989a3e695a74c64e83b5974ebd81dd9ee69483601a57243d67de3b9be'
TRUSTED_CACHE_SHA = 'f9f4c87a4e01eca7861221f19ccf7c3da87a7b45f602be29d4d0aa5d832d4d3d'
ENGINE_BINDING = {
    'version': '0.18.16',
    'image': 'ghcr.io/peonist-ai/halogen-flash-server@sha256:cde6ae91ab3497a470c848fd5c509b0f4af659a1dea7e74b8789df82cde0510e',
    'engine_sha256': 'ce1c375eb2d92a4c7b2b0e1d969acd865bb72bb248c52498eedb170cbaea8a89',
    'hgn_loader_function_sha256': '1c24f6ab85a7036a4a09cfd2ba711ffc9a02787c2bfdbdc8646f1a248be5c871',
}
NATIVE_MOUNT = '/candidate/ngram.hgn'
STOCK_MOUNT = '/ngram-w4b.hgn'


def reject_links(path):
    for node in (path, *path.parents):
        try:
            info = node.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Lookup paths cannot contain symlinks or reparse points')


def validate_configuration(value):
    if not isinstance(value, dict) or set(value) != {'receipt', 'receipt_sha256'}:
        raise ValueError('Lookup tuning requires exactly receipt and receipt_sha256')
    name, digest = value['receipt'], value['receipt_sha256']
    if (not isinstance(name, str) or not PureWindowsPath(name).is_absolute() or
            not re.match(r'^[A-Za-z]:[\\/]', name) or
            any(c in name[2:] for c in ':*?"<>|') or
            '..' in PureWindowsPath(name).parts or any(ord(c) < 32 for c in name)):
        raise ValueError('Lookup receipt must use an absolute Windows drive path')
    if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('Lookup receipt needs its independently reviewed SHA-256')
    path = Path(name)
    reject_links(path)
    path = path.resolve()
    if not any(path != root.resolve() and path.is_relative_to(root.resolve()) for root in RECEIPT_ROOTS):
        raise ValueError('Lookup receipt must stay under backend .local or server .local')
    canonical = (ROOT.parents[1] / CANONICAL_RECEIPT_RELATIVE).resolve()
    if path != canonical or digest != CANONICAL_RECEIPT_SHA:
        raise ValueError('Only the retained canonical native lookup receipt is admitted for 0.18.16')
    return {'receipt': str(path), 'receipt_sha256': digest}


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate lookup receipt key')
        value[key] = item
    return value


def identity(value, size):
    return (isinstance(value, dict) and set(value) == set(IDENTITY_KEYS) and
            all(type(value[key]) is int and value[key] >= 0 for key in IDENTITY_KEYS) and
            value['size'] == size)


def sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def linux_path(value):
    if (not isinstance(value, str) or not value.startswith('/') or value == '/' or
            any(c in value for c in ':,\\"\'\r\n\t\0') or
            any(ord(c) < 32 for c in value) or
            any(part in ('', '.', '..') for part in value.split('/')[1:])):
        raise ValueError('Lookup HGN paths must be unambiguous absolute Linux paths')
    return value


def read_receipt(configuration):
    configuration = validate_configuration(configuration)
    path = Path(configuration['receipt'])
    reject_links(path)
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_RECEIPT_BYTES:
            raise ValueError('Lookup receipt must be a bounded regular JSON file')
        content = stream.read(MAX_RECEIPT_BYTES + 1)
        after = os.fstat(stream.fileno())
    fields = lambda item: tuple(getattr(item, key) for key in
                               ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))
    reject_links(path)
    with path.open('rb') as current:
        current_identity = fields(os.fstat(current.fileno()))
    if fields(before) != fields(after) or fields(after) != current_identity:
        raise ValueError('Lookup receipt identity changed while reading')
    if hashlib.sha256(content).hexdigest() != configuration['receipt_sha256']:
        raise ValueError('Lookup receipt checksum does not match independent review')
    receipt = json.loads(content, object_pairs_hook=unique_object)
    if not isinstance(receipt, dict) or set(receipt) != {'schema', 'source', 'tensor', 'output', 'chunk_bytes'} or type(receipt['schema']) is not int or receipt['schema'] != 1:
        raise ValueError('Malformed lookup extraction receipt')
    source, tensor, output = (receipt[key] for key in ('source', 'tensor', 'output'))
    if (not isinstance(source, dict) or set(source) != {'path', 'sha256', 'identity', 'header_sha256'} or
            source['sha256'] != SOURCE_SHA or not identity(source['identity'], SOURCE_BYTES) or
            not sha(source['header_sha256'])):
        raise ValueError('Lookup receipt does not bind the pinned complete source')
    if (not isinstance(tensor, dict) or set(tensor) != {'name', 'storage', 'dimensions', 'variant',
            'source_offset', 'bytes', 'sha256', 'xor32', 'xor32_verified'} or
            tensor['name'] != TENSOR_NAME or type(tensor['storage']) is not int or tensor['storage'] != 10 or
            tensor['dimensions'] != [128, 2500012, 160] or
            not isinstance(tensor['dimensions'], list) or any(type(v) is not int for v in tensor['dimensions']) or tensor['variant'] != 0 or
            type(tensor['variant']) is not int or tensor['source_offset'] != 1882122624 or
            type(tensor['source_offset']) is not int or type(tensor['bytes']) is not int or tensor['bytes'] != PAYLOAD_BYTES or not sha(tensor['sha256']) or
            tensor['xor32'] != f'{4135773463:08x}' or tensor['xor32_verified'] is not True):
        raise ValueError('Lookup receipt tensor is not the canonical pinned lookup')
    if (not isinstance(output, dict) or set(output) != {'path', 'bytes', 'sha256', 'identity', 'data_offset'} or
            type(output['bytes']) is not int or output['bytes'] != OUTPUT_BYTES or not sha(output['sha256']) or
            not identity(output['identity'], OUTPUT_BYTES) or type(output['data_offset']) is not int or output['data_offset'] != 320):
        raise ValueError('Lookup receipt output is not the canonical standalone HGN')
    if type(receipt['chunk_bytes']) is not int or not 4 <= receipt['chunk_bytes'] <= 8 * 1024**2 or receipt['chunk_bytes'] % 4:
        raise ValueError('Lookup receipt has an invalid bounded extraction chunk size')
    linux_path(source['path']); linux_path(output['path'])
    if source['path'] == output['path']:
        raise ValueError('Standalone lookup cannot alias its original source')
    return receipt


# Each file contributes only its 104-byte header and one 160-byte tensor entry.
# The source entry index and extent were qualified in the retained header audit.
METADATA_CODE = r'''import hashlib,json,os,stat,struct,sys
def inspect(path,index):
    for parent in [path,*list(__import__('pathlib').Path(path).parents)]:
        if stat.S_ISLNK(os.lstat(parent).st_mode): raise ValueError('Linked lookup path')
    def ident(s): return dict(size=s.st_size,device=s.st_dev,inode=s.st_ino,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns)
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW),'rb',buffering=0) as f:
        before=ident(os.fstat(f.fileno()))
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode): raise ValueError('Nonregular lookup file')
        h=f.read(104); f.seek(104+160*index); e=f.read(160)
        if len(h)!=104 or len(e)!=160: raise ValueError('Truncated lookup metadata')
        if ident(os.fstat(f.fileno()))!=before or ident(os.stat(path))!=before: raise ValueError('Lookup identity changed')
    return before,h,e
source,output=sys.argv[1:3]
a,h,e=inspect(source,27); b,j,k=inspect(output,0)
if struct.unpack_from('<IIQQQQ',h)!=(0x314e4748,2,1198,104,191808,124068083904): raise ValueError('Unexpected complete source header')
if struct.unpack_from('<IIQQQQ',j)!=(0x314e4748,2,1,104,320,51200246144) or j[40:]!=h[40:]: raise ValueError('Noncanonical standalone header')
if e[:96].split(b'\0',1)[0]!=b'layers.1.ple.ngram_embedding.weight': raise ValueError('Unexpected lookup name')
if struct.unpack_from('<II',e,96)!=(10,3) or struct.unpack_from('<3q',e,104)!=(128,2500012,160): raise ValueError('Unexpected lookup shape/storage')
if struct.unpack_from('<QQII',e,136)!=(1882122624,51200245764,4135773463,0): raise ValueError('Unexpected lookup extent/checksum')
canonical=bytearray(e); struct.pack_into('<Q',canonical,136,320)
if k!=canonical: raise ValueError('Noncanonical standalone tensor entry')
print(json.dumps(dict(source=a,output=b,source_header_sha256=hashlib.sha256(h).hexdigest())))
'''


def metadata(machine, receipt):
    import portable
    result = json.loads(portable.wsl(machine['distro'], machine['user'], 'python3', '-B', '-c',
        METADATA_CODE, receipt['source']['path'], receipt['output']['path']))
    if (result.get('source') != receipt['source']['identity'] or
            result.get('output') != receipt['output']['identity'] or
            result.get('source_header_sha256') != receipt['source']['header_sha256']):
        raise ValueError('Lookup source/output identity or source header changed')
    return result


class ProgressGuard:
    """Only advancing host sequences renew a guest monotonic observation window."""
    def __init__(self, run_id, now=None):
        self.run_id = run_id
        self.started = time.monotonic() if now is None else now
        self.sequence = None
        self.last_progress = None
        self.renewed = False

    def observe(self, record, now=None):
        now = time.monotonic() if now is None else now
        if now < self.started:
            raise ValueError('Qualification monotonic clock moved backwards')
        if now - self.started >= 600:
            raise ValueError('Qualification guest monotonic deadline reached')
        if (type(record) is not dict or type(record.get('schema')) is not int or
                record['schema'] != 1 or record.get('run_id') != self.run_id or
                type(record.get('sequence')) is not int or record['sequence'] < 1 or
                type(record.get('frame')) is not dict):
            raise ValueError('Invalid qualification guard run identity or sequence')
        if any(type(record['frame'].get(key)) is not int or record['frame'][key] < 18 * 1024**3
               for key in ('available_bytes', 'commit_headroom_bytes')):
            raise ValueError('Qualification physical/commit reserve crossed')
        if self.last_progress is not None:
            if now < self.last_progress:
                raise ValueError('Qualification monotonic clock moved backwards')
            if now - self.last_progress >= 2:
                raise ValueError('Qualification guard expired without observed progress')
        sequence = record['sequence']
        if self.sequence is None:
            self.sequence, self.last_progress = sequence, now
        elif sequence < self.sequence:
            raise ValueError('Qualification guard sequence moved backwards')
        elif sequence > self.sequence:
            self.sequence, self.last_progress, self.renewed = sequence, now, True
        return self.renewed


def guarded_hash(machine, local, receipt):
    """Read back with bounded_hash; the guest checks fresh host reserve per block."""
    import host_frames
    import portable
    import checkpoint_integrity
    run_id = uuid.uuid4().hex
    guard = Path(local) / 'lookup-qualifications' / (run_id + '.guard.json')
    portable.reject_links(guard)
    stopped = threading.Event()
    snapshot_lock = threading.Lock()
    errors = []
    sequence = 0
    def snapshot():
        nonlocal sequence
        with snapshot_lock:
            frame = host_frames.frame()
            sequence += 1
            temporary = guard.with_suffix('.tmp')
            with temporary.open('w', encoding='utf-8') as stream:
                json.dump(dict(schema=1, run_id=run_id, sequence=sequence, time=time.time(), frame=frame), stream)
            deadline = time.monotonic() + .5
            while True:
                try:
                    temporary.replace(guard)
                    break
                except PermissionError:
                    # A guest read can briefly hold the Windows destination.
                    # Retries do not renew the guest's observed progress age.
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(.01)
            if any(type(frame.get(key)) is not int or frame[key] < 18 * 1024**3
                   for key in ('available_bytes', 'commit_headroom_bytes')):
                raise ValueError('Lookup qualification crossed the 18 GiB physical/commit reserve')
    def monitor():
        while not stopped.wait(.2):
            try: snapshot()
            except BaseException as error:
                errors.append(error)
                break
    snapshot()
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    try:
        guard_linux = portable.wsl(machine['distro'], machine['user'], 'wslpath', '-a', '-u', str(guard))
        code = 'import builtins,json,os,stat,sys,time\nfrom pathlib import Path\n' + inspect.getsource(ProgressGuard) + r'''
path,guard=sys.argv[1:3]
expected=json.loads(sys.argv[4])
tracker=ProgressGuard(sys.argv[5])
def check():
    with builtins.open(guard,'rb') as f: raw=f.read(16385)
    if len(raw)>16384: raise ValueError('Invalid qualification guard')
    return tracker.observe(json.loads(raw))
while not check(): time.sleep(.05)
class Reader:
    def __init__(self,path,mode,buffering=0):
        check()
        for parent in [path,*list(Path(path).parents)]:
            if stat.S_ISLNK(os.lstat(parent).st_mode): raise ValueError('Linked lookup readback path')
        self.f=os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW),mode,buffering=buffering)
        s=os.fstat(self.f.fileno())
        actual=dict(size=s.st_size,device=s.st_dev,inode=s.st_ino,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns)
        if not stat.S_ISREG(s.st_mode) or actual!=expected:
            self.f.close(); raise ValueError('Lookup readback identity changed before opening')
    def __enter__(self): return self
    def __exit__(self,*a): return self.f.__exit__(*a)
    def fileno(self): return self.f.fileno()
    def read(self,*a): check(); data=self.f.read(*a); check(); return data
namespace={'__name__':'lookup_readback'}
exec(sys.argv[3],namespace)
namespace['open']=Reader
print(json.dumps(namespace['hash_file'](path)))
'''
        result = json.loads(portable.wsl(machine['distro'], machine['user'],
            'timeout', '--signal=TERM', '--kill-after=5s', '610s', 'python3', '-B', '-c',
            code, receipt['output']['path'], guard_linux, checkpoint_integrity.HASH_CODE,
            json.dumps(receipt['output']['identity']), run_id, timeout=620))
        if errors: raise errors[0]
        snapshot()
        return result
    finally:
        stopped.set(); thread.join(timeout=2)


def _trusted_payload_seal(configuration, receipt):
    """Reuse only the exact previously read-back payload; never hash 50 GB here."""
    expected = dict(schema=1, configuration=configuration, source=receipt['source'], tensor=receipt['tensor'],
                    output=receipt['output'], read_mode='bounded-cache', reserve_gib=18)
    cache_key = hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if cache_key != TRUSTED_CACHE_KEY:
        raise ValueError('Canonical lookup payload identity no longer matches the trusted cache key')
    cache = ROOT.parent / 'halogen-wsl2-0.16.2/.local/lookup-qualifications' / (TRUSTED_CACHE_KEY + '.json')
    reject_links(cache)
    with cache.open('rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_RECEIPT_BYTES:
            raise ValueError('Trusted lookup cache must be a bounded regular file')
        data = stream.read(MAX_RECEIPT_BYTES + 1)
        after = os.fstat(stream.fileno())
    fields = lambda item: tuple(getattr(item, key) for key in
        ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))
    reject_links(cache)
    with cache.open('rb') as current:
        current_identity = fields(os.fstat(current.fileno()))
    if (fields(before) != fields(after) or fields(after) != current_identity or
            hashlib.sha256(data).hexdigest() != TRUSTED_CACHE_SHA or
            json.loads(data, object_pairs_hook=unique_object) != expected):
        raise ValueError('Trusted canonical lookup cache changed; no readback fallback is permitted')
    return {'cache_key': TRUSTED_CACHE_KEY, 'cache_sha256': TRUSTED_CACHE_SHA}


def _engine_binding():
    import portable
    if (portable.IMAGE != ENGINE_BINDING['image'] or
            portable.RELEASE.get('version') != ENGINE_BINDING['version'] or
            portable.RELEASE.get('engine_sha256') != ENGINE_BINDING['engine_sha256']):
        raise ValueError('Native lookup loader is bound only to the exact 0.18.16 engine')
    return dict(ENGINE_BINDING)


def _seal(configuration, receipt):
    return dict(schema=2, configuration=configuration, source=receipt['source'], tensor=receipt['tensor'],
        output=receipt['output'], read_mode='trusted-canonical-cache', reserve_gib=18,
        engine_binding=_engine_binding(), payload_qualification=_trusted_payload_seal(configuration, receipt),
        mount_binding=dict(destination=NATIVE_MOUNT, source=receipt['output']['path'], readonly=True,
                           stock_destination=STOCK_MOUNT, stock_source=receipt['source']['path']))


def validate_seal(seal):
    if type(seal) is not dict or 'configuration' not in seal:
        raise ValueError('Native lookup needs an explicit engine-bound qualification seal')
    configuration = validate_configuration(seal['configuration'])
    receipt = read_receipt(configuration)
    if seal != _seal(configuration, receipt):
        raise ValueError('Native lookup seal differs from the exact canonical engine/payload/mount binding')
    return receipt


def bind_manifest(manifest, seal):
    receipt = validate_seal(seal)
    if (manifest.get('version') != ENGINE_BINDING['version'] or
            manifest.get('image') != ENGINE_BINDING['image'] or manifest.get('checkpoint') != 'v2' or
            manifest['mounts'].get(STOCK_MOUNT) != receipt['source']['path'] or
            manifest['environment'].get('HALOGEN_NGRAM_TABLE') != STOCK_MOUNT):
        raise ValueError('Native lookup requires the unchanged qualified v2 stock source and exact engine')
    manifest['mounts'][NATIVE_MOUNT] = receipt['output']['path']
    manifest['environment']['HALOGEN_NGRAM_TABLE'] = NATIVE_MOUNT
    manifest['lookup_tuning'] = seal
    validate_manifest(manifest)


def validate_manifest(manifest):
    seal = manifest.get('lookup_tuning')
    if seal is None:
        if (NATIVE_MOUNT in manifest.get('mounts', {}) or
                manifest.get('environment', {}).get('HALOGEN_NGRAM_TABLE') == NATIVE_MOUNT):
            raise ValueError('Native lookup mount requires its qualification seal')
        return
    receipt = validate_seal(seal)
    if (manifest.get('version') != ENGINE_BINDING['version'] or
            manifest.get('image') != ENGINE_BINDING['image'] or manifest.get('checkpoint') != 'v2' or
            manifest.get('mounts', {}).get(STOCK_MOUNT) != receipt['source']['path'] or
            manifest.get('mounts', {}).get(NATIVE_MOUNT) != receipt['output']['path'] or
            manifest.get('environment', {}).get('HALOGEN_NGRAM_TABLE') != NATIVE_MOUNT):
        raise ValueError('Native lookup manifest engine, read-only mount plan or environment changed')


def qualify(machine, local, configuration):
    import checkpoint_integrity
    import portable
    configuration = validate_configuration(configuration)
    receipt = read_receipt(configuration)
    selected = machine.get('ngram_source') or machine['models'] + '/' + portable.MODELS[0][0]
    if receipt['source']['path'] != selected:
        raise ValueError('Lookup receipt source differs from the installed stock lookup')
    # Require the already qualified full-source receipt; never write it or rehash it.
    source_receipt = Path(local) / 'ngram-integrity.json'
    portable.reject_links(source_receipt)
    with source_receipt.open('rb') as stream:
        content = stream.read(MAX_RECEIPT_BYTES + 1)
    if len(content) > MAX_RECEIPT_BYTES or not checkpoint_integrity.receipt_matches(
            json.loads(content, object_pairs_hook=unique_object), receipt['source']['identity'],
            size=SOURCE_BYTES, sha=SOURCE_SHA, source=selected):
        raise ValueError('Lookup original source lacks a matching pinned stock integrity receipt')
    metadata(machine, receipt)
    # Payload correctness is inherited only from the pinned completed readback;
    # current file identities/header bytes above must still match it exactly.
    return _seal(configuration, receipt)


def revalidate(machine, seal):
    if seal is None: return
    receipt = validate_seal(seal)
    if (machine.get('ngram_source') or machine['models'] + '/qwen38-flash-next-w4b.hgn') != receipt['source']['path']:
        raise ValueError('Installed stock lookup changed after qualification')
    metadata(machine, receipt)
