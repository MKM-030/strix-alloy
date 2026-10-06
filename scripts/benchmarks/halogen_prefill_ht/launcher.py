"""Finite QKV capture through the original managed Halogen lifecycle.

Default is manifest preparation only. The root coordinator owns admission,
the single unchanged request, export, normal stop and persistent stock restore.
Only build_manifest and the exact controller child command are adapted.
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
SO_DEST = '/candidate/libhalogen0162-prefill-ht-capture.so'
RECEIPT_DEST = '/candidate/prefill-ht-tensor.receipt'
FIXED_OPTIONS = ['--checkpoint', 'v2', '--context-size', '262144', '--prompt-cache', 'Off',
                 '--draft-tokens', '2', '--prefill-chunk', '8192', '--max-prefill-tokens', '8192',
                 '--speculation-policy-json', '{"HALOGEN_PLD":"3,3"}',
                 '--serve-seconds', '0', '--startup-timeout', '900']


def require(value, message):
    if not value:
        raise ValueError(message)


def raw(path, limit):
    path = Path(path)
    require(path.is_absolute(), 'Absolute local path required')
    for item in (path, *path.parents):
        s = item.lstat()
        require(not stat.S_ISLNK(s.st_mode) and not getattr(s, 'st_file_attributes', 0) & 1024,
                'Linked local file refused: ' + str(item))
    with path.open('rb') as f:
        before = os.fstat(f.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit, 'File extent differs')
        value = f.read(limit + 1)
        after = os.fstat(f.fileno())
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    require(len(value) == before.st_size and
            tuple(getattr(before, k) for k in fields) == tuple(getattr(after, k) for k in fields),
            'Local file changed during read')
    return value


def sha(path):
    return hashlib.sha256(raw(path, 64 << 20)).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def load_plan(path, seal):
    require(isinstance(seal, str) and re.fullmatch('[0-9a-f]{64}', seal), 'Plan digest required')
    data = raw(path, 65536)
    require(hashlib.sha256(data).hexdigest() == seal, 'Capture plan changed')
    plan = json.loads(data)
    require(plan['schema'] == 'halogen.prefill-ht.capture-launch.v1' and
            plan['image'] == IMAGE and plan['engine_sha256'] == ENGINE_SHA,
            'Capture plan/image scope differs')
    require(plan['launcher_sha256'] == sha(Path(__file__).resolve()), 'Launcher source changed')
    require(plan['profile_sha256'] == sha(plan['profile']), 'Original profile changed')
    require(sha(plan['receipt_local']) == plan['receipt']['sha256'], 'Tensor receipt changed')
    for record in (plan['shared_object'], plan['receipt']):
        require(re.fullmatch('/home/revn/halogen-re/[A-Za-z0-9._-]+', record['path']) and
                re.fullmatch('[0-9a-f]{64}', record['sha256']) and
                type(record['bytes']) is int and 0 < record['bytes'] <= 1 << 20,
                'Bounded Linux artifact identity required')
    for p, h in plan['source_pins'].items():
        require(sha(p) == h, 'Pinned capture dependency changed: ' + p)
    mandatory = {str(ROOT / 'server/controller.py'), str(BACKEND / 'Start.ps1'),
                 str(BACKEND / '.local/machine.json'), str(BACKEND / 'scripts/service.py'),
                 str(BACKEND / 'scripts/runner.py'), str(Path(__file__).resolve()),
                 str(Path(__file__).with_name('capture.c').resolve())}
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
    spec = json.dumps({k: plan[k] for k in ('shared_object', 'receipt')}, separators=(',', ':'))
    code = r'''import hashlib,json,os,stat,sys
spec=json.loads(sys.argv[1]);out={}
for key,r in spec.items():
 p=r['path']
 from pathlib import Path
 for parent in (Path(p).parent,*Path(p).parent.parents):
  if not stat.S_ISDIR(parent.lstat().st_mode):raise ValueError('linked artifact parent')
 fd=os.open(p,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:
  a=os.fstat(f.fileno())
  if not stat.S_ISREG(a.st_mode) or a.st_nlink!=1 or a.st_size!=r['bytes']:raise ValueError('artifact identity/extent')
  if key=='receipt' and (a.st_uid!=0 or a.st_mode&0o777!=0o444):raise ValueError('receipt owner/mode')
  data=f.read(r['bytes']+1);b=os.fstat(f.fileno())
 if tuple(getattr(a,k) for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns'))!=tuple(getattr(b,k) for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')):raise ValueError('artifact changed')
 if len(data)!=r['bytes'] or hashlib.sha256(data).hexdigest()!=r['sha256']:raise ValueError('artifact digest')
 if key=='shared_object' and data[:6]!=b'\x7fELF\x02\x01':raise ValueError('ELF64 LE required')
 out[key]={'bytes':len(data),'sha256':r['sha256']}
print(json.dumps(out))
'''
    require(service.r.MACHINE['distro'] == 'Ubuntu-24.04' and service.r.MACHINE['user'] == 'revn',
            'Reviewed Linux artifact namespace changed')
    result = service.r.invoke(service.r.WSL + ['python3', '-c', code, spec], timeout=30)
    require(len(result) <= 4096 and set(json.loads(result)) == {'shared_object', 'receipt'},
            'Linux artifact verification failed')


def patch_manifest(service, plan):
    original = service.build_manifest

    def build(options, attempt, run_id):
        require(re.fullmatch('[0-9a-f]{32}', run_id), 'Invalid service run identity')
        require((options.checkpoint, options.context_size, options.prompt_cache, options.draft_tokens,
                 options.prefill_chunk, options.max_prefill_tokens, options.serve_seconds,
                 options.startup_timeout) == ('v2', 262144, 'Off', 2, 8192, 8192, 0, 900),
                'Fixed capture launch options changed')
        load_plan(plan['plan_path'], plan['plan_sha256'])
        artifacts(service, plan)
        m = original(options, attempt, run_id)
        require(m['image'] == IMAGE and m['version'] == '0.16.2' and m['slots'] == 1 and
                canonical(m['sources']) == plan['backend_sources_sha256'] and
                m['environment'].get('LD_PRELOAD') == PRELOAD and
                m['environment'].get('HALOGEN_PLD') == '3,3' and
                m['environment'].get('HALOGEN_HOST_RESERVE_GIB') == '18',
                'Original manifest scope changed')
        require(SO_DEST not in m['mounts'] and RECEIPT_DEST not in m['mounts'], 'Capture mount collision')
        m['mounts'][SO_DEST] = plan['shared_object']['path']
        m['mounts'][RECEIPT_DEST] = plan['receipt']['path']
        m['environment']['LD_PRELOAD'] += ':' + SO_DEST
        trace = '/tmp/alloy-prefill-ht-capture-' + run_id
        m['environment'].update(HALOGEN_PREFILL_HT_CAPTURE='ordinary-qkv8192-v1',
                                HALOGEN_PREFILL_HT_CAPTURE_DIR=trace,
                                HALOGEN_PREFILL_HT_CAPTURE_RECEIPT_SHA256=plan['receipt']['sha256'])
        m['prefill_ht_capture'] = dict(plan_sha256=plan['plan_sha256'], trace_directory=trace,
                                     shared_object=plan['shared_object'], receipt=plan['receipt'],
                                     shape=[8192, 10240, 2560], original_output_unchanged=True,
                                     timing_claims=False, leave_stock_open_afterward=True)
        command = service.command(m)
        require('--read-only' not in command and
                command.count('type=bind,src=' + plan['shared_object']['path'] + ',dst=' + SO_DEST + ',readonly') == 1 and
                command.count('type=bind,src=' + plan['receipt']['path'] + ',dst=' + RECEIPT_DEST + ',readonly') == 1,
                'Exact readonly capture mounts required')
        return m

    service.build_manifest = build


def install_controller_adapter(controller, plan_path, seal):
    plan = load_plan(plan_path, seal)
    require(Path(controller.__file__).resolve() == (ROOT / 'server/controller.py').resolve(),
            'Unexpected controller module')
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
    for fn in (controller.halogen_draft_arguments,):
        expected += fn(engine)
    for fn in (controller.halogen_kernel_arguments, controller.halogen_speculation_arguments,
               controller.halogen_matmul_arguments, controller.halogen_lookup_arguments,
               controller.halogen_private_hsa_arguments):
        expected += fn(engine, BACKEND)
    original = controller.JobChild
    replacement = [runtime['executable'], '-B', '-u', str(Path(__file__).resolve()),
                   '--plan', str(Path(plan_path).resolve()), '--plan-sha256', seal, '--run']

    class CaptureChild(original):
        def __init__(self, command, *, cwd, env, stdout_path, stderr_path):
            require(list(command) == expected and Path(cwd).resolve() == BACKEND.resolve() and
                    env.get('ALLOY_MANAGED') == '1', 'Unexpected original managed child')
            load_plan(plan_path, seal)
            super().__init__(replacement, cwd=cwd, env=env, stdout_path=stdout_path, stderr_path=stderr_path)

    controller.JobChild = CaptureChild


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--plan-sha256', required=True)
    p.add_argument('--run', action='store_true')
    a = p.parse_args(); plan = load_plan(a.plan, a.plan_sha256)
    plan.update(plan_path=str(a.plan.resolve()), plan_sha256=a.plan_sha256)
    service = import_service(plan); service.r.configure(); patch_manifest(service, plan)
    if not a.run:
        with tempfile.TemporaryDirectory(prefix='alloy-prefill-ht-review-') as temporary:
            attempt = Path(temporary)
            (attempt / 'entrypoint-service.sh').write_bytes(service.service_entrypoint((service.LOCAL / 'entrypoint-wsl.sh').read_bytes()))
            m = service.build_manifest(service.options(FIXED_OPTIONS), attempt, uuid.uuid4().hex)
            print(json.dumps(dict(launched=False, capture=m['prefill_ht_capture'], environment={k: v for k, v in m['environment'].items() if k.startswith('HALOGEN_PREFILL_HT') or k == 'LD_PRELOAD'})))
        return 0
    os.environ['ALLOY_MANAGED'] = '1'
    return service.main(FIXED_OPTIONS)


if __name__ == '__main__':
    raise SystemExit(main())
