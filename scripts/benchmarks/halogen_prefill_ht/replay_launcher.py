"""Finite frozen QKV replay through the original managed Halogen lifecycle.

Default prepares a manifest only. Root owns admission, arm, bounded export,
normal stop and persistent stock restoration. This launches no request and
makes no serving-rate claim. Existing capture files remain unchanged.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / 'backends/halogen-wsl2-0.16.2'
IMAGE = 'ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a'
ENGINE_SHA = 'ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b'
PRELOAD = '/candidate/libhalogen0162-v2-preflight.so:/candidate/hip-register-private-rw.so'
SO_DEST = '/candidate/libhalogen0162-prefill-ht-replay.so'
RECEIPT_DEST = '/candidate/prefill-ht-replay.receipt'
FIXTURE_DEST = '/candidate/prefill-ht-fixture'
ARM_CONTENT = 'ordinary-qkv8192-v1-replay-ready\n'
FILES = {
    'packed.bin': ('packed_sha256', 13107200, True),
    'signs-u16.bin': ('signs_sha256', 5120, True),
    'scales-u16.bin': ('scales_sha256', 20480, True),
    'x-u16.bin': ('x_sha256', 41943040, True),
    'y-reference-u16.bin': ('y_sha256', 167772160, True),
    'descriptor-before.bin': ('descriptor_sha256', 120, True),
    'records.json': ('records_sha256', 16384, False),
    'complete.json': ('complete_sha256', 2048, False),
}
FIXED_OPTIONS = ['--checkpoint', 'v2', '--context-size', '262144', '--prompt-cache', 'Off',
                 '--draft-tokens', '2', '--prefill-chunk', '8192', '--max-prefill-tokens', '8192',
                 '--speculation-policy-json', '{"HALOGEN_PLD":"3,3"}',
                 '--serve-seconds', '0', '--startup-timeout', '900']


def require(value, message):
    if not value:
        raise ValueError(message)


def local_path(path):
    path = Path(path)
    require(path.is_absolute(), 'Absolute local path required')
    for item in (path, *path.parents):
        s = item.lstat()
        require(not stat.S_ISLNK(s.st_mode) and not getattr(s, 'st_file_attributes', 0) & 1024,
                'Linked local path refused: ' + str(item))
    return path


def identity(s):
    # Python3.12 Windows fstat/path stat disagree on deprecated ctime semantics.
    # Both expose the same explicit birth time; Linux retains metadata ctime.
    stamp = s.st_birthtime_ns if os.name == 'nt' else s.st_ctime_ns
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, stamp)


def unchanged_fd(before, after):
    # Comparing two snapshots from the same descriptor retains strict ctime.
    return identity(before) == identity(after) and before.st_ctime_ns == after.st_ctime_ns


def raw(path, limit):
    path = local_path(path)
    with path.open('rb') as f:
        before = os.fstat(f.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit, 'File extent differs')
        value = f.read(limit + 1)
        after = os.fstat(f.fileno())
    require(len(value) == before.st_size and unchanged_fd(before, after) and
            identity(before) == identity(path.stat()),
            'Local file changed during read')
    return value


def sha(path, limit=314572800):
    """Stream fixed-size chunks; never allocate a full160-MiB fixture copy."""
    path = local_path(path)
    with path.open('rb') as f:
        before = os.fstat(f.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit, 'Hash extent differs')
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
        after = os.fstat(f.fileno())
    require(unchanged_fd(before, after) and identity(before) == identity(path.stat()), 'File changed during hash')
    return digest


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def receipt_bytes(files):
    require(set(files) == set(FILES), 'Exactly eight frozen input bindings required')
    rows = ['schema=ordinary-qkv8192-replay-v1', 'stock_route=direct-original']
    for name, (key, extent, exact) in FILES.items():
        r = files[name]
        require(type(r['bytes']) is int and 0 < r['bytes'] <= extent and
                (not exact or r['bytes'] == extent) and
                isinstance(r['sha256'], str) and re.fullmatch('[0-9a-f]{64}', r['sha256']),
                'Frozen fixture binding differs: ' + name)
        rows.append(key + '=' + r['sha256'])
    return ('\n'.join(rows) + '\n').encode('ascii')


def load_plan(path, seal):
    require(isinstance(seal, str) and re.fullmatch('[0-9a-f]{64}', seal), 'Plan digest required')
    data = raw(path, 65536)
    require(hashlib.sha256(data).hexdigest() == seal, 'Replay plan changed')
    plan = json.loads(data)
    require(plan['schema'] == 'halogen.prefill-ht.replay-launch.v1' and
            plan['image'] == IMAGE and plan['engine_sha256'] == ENGINE_SHA,
            'Replay plan/image scope differs')
    require(plan['launcher_sha256'] == sha(Path(__file__).resolve()), 'Launcher source changed')
    require(plan['profile_sha256'] == sha(plan['profile']), 'Original profile changed')
    expected = receipt_bytes(plan['fixture_files'])
    require(raw(plan['receipt_local'], 4096) == expected and
            hashlib.sha256(expected).hexdigest() == plan['receipt']['sha256'] and
            plan['receipt']['bytes'] == len(expected), 'Canonical eight-hash receipt differs')
    directory = local_path(plan['fixture_local'])
    require(directory.is_dir(), 'Frozen local directory required')
    for name, record in plan['fixture_files'].items():
        file = directory / name
        require(file.stat().st_size == record['bytes'] and sha(file) == record['sha256'],
                'Frozen local fixture changed: ' + name)
    require(re.fullmatch('/home/revn/halogen-re/[A-Za-z0-9._-]+', plan['fixture_directory']),
            'Bounded native fixture directory required')
    for key in ('shared_object', 'receipt'):
        record = plan[key]
        require(re.fullmatch('/home/revn/halogen-re/[A-Za-z0-9._-]+', record['path']) and
                re.fullmatch('[0-9a-f]{64}', record['sha256']) and
                type(record['bytes']) is int and 0 < record['bytes'] <= 1 << 20,
                'Bounded Linux artifact identity required')
    for p, h in plan['source_pins'].items():
        require(sha(p) == h, 'Pinned replay dependency changed: ' + p)
    mandatory = {str(ROOT / 'server/controller.py'), str(ROOT / 'server/gateway.py'), str(BACKEND / 'Start.ps1'),
                 str(BACKEND / '.local/machine.json'), str(BACKEND / 'scripts/service.py'),
                 str(BACKEND / 'scripts/runner.py'), str(Path(__file__).resolve()),
                 str(Path(__file__).with_name('replay.c').resolve()),
                 str(Path(__file__).with_name('owned_replay.py').resolve())}
    require(mandatory <= set(plan['source_pins']), 'Missing mandatory source provenance')
    return plan


def import_service(plan):
    require(os.name == 'nt', 'Local Windows launcher required')
    sys.path.insert(0, str(BACKEND / 'scripts'))
    service = importlib.import_module('service')
    require(Path(service.__file__).resolve() == (BACKEND / 'scripts/service.py').resolve() and
            service.r.IMAGE == IMAGE and service.r.ENGINE_SHA == ENGINE_SHA and
            canonical(service.source_hashes()) == plan['backend_sources_sha256'],
            'Original managed backend identity changed')
    return service


def artifacts(service, plan):
    spec = json.dumps({k: plan[k] for k in ('shared_object', 'receipt', 'fixture_directory', 'fixture_files')},
                      separators=(',', ':'))
    code = r'''import hashlib,json,os,stat,sys
from pathlib import Path
spec=json.loads(sys.argv[1]);out={};fields=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
def verify(p,r,mode=None):
 for parent in (Path(p).parent,*Path(p).parent.parents):
  if not stat.S_ISDIR(parent.lstat().st_mode):raise ValueError('linked artifact parent')
 fd=os.open(p,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:
  a=os.fstat(f.fileno())
  if not stat.S_ISREG(a.st_mode) or a.st_nlink!=1 or a.st_size!=r['bytes']:raise ValueError('artifact extent')
  if mode is not None and (a.st_uid!=0 or a.st_mode&0o777!=mode):raise ValueError('artifact owner/mode')
  header=f.read(6);f.seek(0);digest=hashlib.file_digest(f,'sha256').hexdigest();b=os.fstat(f.fileno())
 if tuple(getattr(a,k) for k in fields)!=tuple(getattr(b,k) for k in fields) or digest!=r['sha256']:raise ValueError('artifact changed')
 return header
for key in ('shared_object','receipt'):
 r=spec[key];header=verify(r['path'],r,0o444 if key=='receipt' else None)
 if key=='shared_object' and header!=b'\x7fELF\x02\x01':raise ValueError('ELF64 LE required')
 out[key]={'bytes':r['bytes'],'sha256':r['sha256']}
p=Path(spec['fixture_directory']);s=p.lstat()
if not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or s.st_mode&0o777!=0o700:raise ValueError('native fixture owner/mode')
if {q.name for q in p.iterdir()}!=set(spec['fixture_files']):raise ValueError('native fixture file set')
for name,r in spec['fixture_files'].items():verify(str(p/name),r,0o600)
out['fixture_files']=len(spec['fixture_files'])
print(json.dumps(out))
'''
    require(service.r.MACHINE['distro'] == 'Ubuntu-24.04' and service.r.MACHINE['user'] == 'revn',
            'Reviewed Linux artifact namespace changed')
    # The immutable fixture is root0700/files0600, as required by replay.c.
    # Use root only for this bounded read-only verification. Backend launch
    # retains the installed revn user and all existing machine settings.
    verification = service.r.portable.wsl_command('Ubuntu-24.04', 'root', ['python3', '-c', code, spec])
    result = service.r.invoke(verification, timeout=60)
    require(len(result) <= 4096 and set(json.loads(result)) == {'shared_object', 'receipt', 'fixture_files'} and
            json.loads(result)['fixture_files'] == 8, 'Linux artifact verification failed')


def patch_manifest(service, plan):
    original = service.build_manifest

    def build(options, attempt, run_id):
        require(re.fullmatch('[0-9a-f]{32}', run_id), 'Invalid service run identity')
        require((options.checkpoint, options.context_size, options.prompt_cache, options.draft_tokens,
                 options.prefill_chunk, options.max_prefill_tokens, options.serve_seconds,
                 options.startup_timeout) == ('v2', 262144, 'Off', 2, 8192, 8192, 0, 900),
                'Fixed replay launch options changed')
        load_plan(plan['plan_path'], plan['plan_sha256']); artifacts(service, plan)
        m = original(options, attempt, run_id)
        require(m['image'] == IMAGE and m['version'] == '0.16.2' and m['slots'] == 1 and
                canonical(m['sources']) == plan['backend_sources_sha256'] and
                m['environment'].get('LD_PRELOAD') == PRELOAD and
                m['environment'].get('HALOGEN_PLD') == '3,3' and
                m['environment'].get('HALOGEN_HOST_RESERVE_GIB') == '18',
                'Original manifest scope changed')
        for key in ('HALOGEN_PREFILL_KEEP_TRUNK', 'HALOGEN_HT_TG_BLOCKS', 'HALOGEN_HT_TG_M128',
                    'HALOGEN_HT_TRUNK_GEMM', 'HALOGEN_PREFILL_HT_CAPTURE',
                    'HALOGEN_MTP_RAW_EMBEDDING_CAPTURE', 'HALOGEN_MTP_HIDDEN_RMS_TAP',
                    'HALOGEN_MTP_FULL_EVENT_TAP', 'HALOGEN_MTP_FC_QUALITY', 'HALOGEN_MTP_EMBEDDING_CACHE'):
            require(key not in m['environment'], 'Other benchmark/nondefault mode: ' + key)
        for destination in (SO_DEST, RECEIPT_DEST, FIXTURE_DEST):
            require(destination not in m['mounts'], 'Replay mount collision')
        m['mounts'][SO_DEST] = plan['shared_object']['path']
        m['mounts'][RECEIPT_DEST] = plan['receipt']['path']
        m['mounts'][FIXTURE_DEST] = plan['fixture_directory']
        m['environment']['LD_PRELOAD'] += ':' + SO_DEST
        trace = '/tmp/alloy-prefill-ht-replay-' + run_id
        m['environment'].update(HALOGEN_PREFILL_HT_REPLAY='ordinary-qkv8192-v1',
                                HALOGEN_PREFILL_HT_REPLAY_DIR=trace,
                                HALOGEN_PREFILL_HT_REPLAY_FIXTURE_DIR=FIXTURE_DEST,
                                HALOGEN_PREFILL_HT_REPLAY_MANIFEST_SHA256=plan['receipt']['sha256'])
        m['prefill_ht_replay'] = dict(plan_sha256=plan['plan_sha256'], trace_directory=trace,
                                    shared_object=plan['shared_object'], receipt=plan['receipt'],
                                    fixture_directory=plan['fixture_directory'], fixture_files=plan['fixture_files'],
                                    shape=[8192, 10240, 2560], run_limit=43, recapture=False,
                                    inference_gateway_blocked=True,
                                    token_rate_claim=False, leave_stock_open_afterward=True)
        command = service.command(m)
        require('--read-only' not in command and all(command.count('type=bind,src=' + source +
                ',dst=' + destination + ',readonly') == 1 for destination, source in (
                    (SO_DEST, plan['shared_object']['path']), (RECEIPT_DEST, plan['receipt']['path']),
                    (FIXTURE_DEST, plan['fixture_directory']))), 'Exact readonly replay mounts required')
        return m

    service.build_manifest = build


def install_controller_adapter(controller, plan_path, seal):
    plan = load_plan(plan_path, seal)
    require(Path(controller.__file__).resolve() == (ROOT / 'server/controller.py').resolve(),
            'Unexpected controller module')
    gateway = importlib.import_module('gateway')
    require(Path(gateway.__file__).resolve() == (ROOT / 'server/gateway.py').resolve() and
            controller.load_config is gateway.load_config and
            controller.load_config.__globals__['Gateway'] is gateway.Gateway and
            not getattr(gateway.Gateway, 'prefill_ht_replay_blocked', False),
            'Original measured-controller gateway factory required')
    original_gateway = gateway.Gateway

    class ReplayGateway(original_gateway):
        prefill_ht_replay_blocked = True

        async def inference(self, request):
            # Only this default-off measured controller is patched. Normal
            # restoration starts a fresh original controller without adapter.
            # Authentication, /health, /v1/models and backend probes are inherited.
            return gateway.web.json_response({'error': {'message': 'Measurement in progress'}},
                                             status=503, headers={'Retry-After': '1'})

    # load_config was imported by controller, but resolves Gateway from the
    # gateway module's globals when controller.run constructs this instance.
    gateway.Gateway = ReplayGateway
    profile = json.loads(raw(plan['profile'], 65536)); engine = profile['engine']
    require(profile['minimum_reserve_gib'] == 18 and profile['concurrency'] == 1 and
            engine == plan['original_engine'], 'Singleton original controller profile required')
    fixed = dict(kind='halogen', directory='backends/halogen-wsl2-0.16.2', checkpoint='v2',
                 context=262144, prompt_cache='Off', draft_tokens=2, prefill_chunk=8192,
                 max_prefill_tokens=8192, speculation_policy={'HALOGEN_PLD': '3,3'})
    require(all(engine.get(k) == v for k, v in fixed.items()) and
            set(engine) == set(fixed) | {'powershell'}, 'Exact stock8192 engine controls required')
    require(controller.validate_engine(engine, ROOT).resolve() == BACKEND.resolve(), 'Wrong backend')
    runtime = plan['runtime']
    require(Path(sys.executable).resolve() == Path(runtime['executable']).resolve() and
            sha(runtime['executable']) == runtime['executable_sha256'], 'Native interpreter changed')
    expected = [engine['powershell'], '-NoProfile', '-File', str(BACKEND / 'Start.ps1'),
                '-Checkpoint', 'v2', '-ContextSize', '262144', '-PromptCache', 'Off']
    expected += controller.halogen_draft_arguments(engine)
    for fn in (controller.halogen_kernel_arguments, controller.halogen_speculation_arguments,
               controller.halogen_matmul_arguments, controller.halogen_lookup_arguments,
               controller.halogen_private_hsa_arguments):
        expected += fn(engine, BACKEND)
    original = controller.JobChild
    replacement = [runtime['executable'], '-B', '-u', str(Path(__file__).resolve()),
                   '--plan', str(Path(plan_path).resolve()), '--plan-sha256', seal, '--run']

    class ReplayChild(original):
        def __init__(self, command, *, cwd, env, stdout_path, stderr_path):
            require(list(command) == expected and Path(cwd).resolve() == BACKEND.resolve() and
                    env.get('ALLOY_MANAGED') == '1', 'Unexpected original managed child')
            load_plan(plan_path, seal)
            super().__init__(replacement, cwd=cwd, env=env, stdout_path=stdout_path, stderr_path=stderr_path)

    controller.JobChild = ReplayChild


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True); p.add_argument('--plan-sha256', required=True)
    p.add_argument('--run', action='store_true')
    a = p.parse_args(); plan = load_plan(a.plan, a.plan_sha256)
    plan.update(plan_path=str(a.plan.resolve()), plan_sha256=a.plan_sha256)
    service = import_service(plan); service.r.configure(); patch_manifest(service, plan)
    if not a.run:
        with tempfile.TemporaryDirectory(prefix='alloy-prefill-ht-replay-review-') as temporary:
            attempt = Path(temporary)
            (attempt / 'entrypoint-service.sh').write_bytes(service.service_entrypoint((service.LOCAL / 'entrypoint-wsl.sh').read_bytes()))
            m = service.build_manifest(service.options(FIXED_OPTIONS), attempt, uuid.uuid4().hex)
            print(json.dumps(dict(launched=False, replay=m['prefill_ht_replay'], environment={
                k: v for k, v in m['environment'].items() if k.startswith('HALOGEN_PREFILL_HT') or k == 'LD_PRELOAD'})))
        return 0
    os.environ['ALLOY_MANAGED'] = '1'
    return service.main(FIXED_OPTIONS)


if __name__ == '__main__':
    raise SystemExit(main())
