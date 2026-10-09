"""Compose a sealed, default-off capture with the normal0.17.3 lifecycle."""
import hashlib
import json
from pathlib import Path
import re
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PREP=ROOT/'server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008'
WORK=PREP/'scratchfree-moe-20261009'
ENGINE_SHA='af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def apply_manifest(service,manifest):
    seal=json.loads((WORK/'delivery-seal.json').read_text(encoding='utf-8'))
    assert manifest['version']=='0.17.3' and service.r.ENGINE_SHA==ENGINE_SHA
    assert manifest['checkpoint']=='v2' and re.fullmatch('[0-9a-f]{32}',manifest['run_id'])
    mounts=manifest['mounts'];env=manifest['environment']
    prior=env.get('LD_PRELOAD','');tokens=prior.replace(':',' ').split()
    assert '/candidate/libhalogen0173-v2-preflight.so' in tokens and '/candidate/hip-register-private-rw.so' in tokens
    assert not any(k.startswith('ALLOY0173_FL_') for k in env)
    assert not manifest.get('scratchfree_fl_capture')
    delivered={
        '/candidate/libhalogen0173-fl-capture.so':Path(seal['artifacts']['capture']['path']),
        '/candidate/libhalogen0173-fl-replay.so':Path(seal['artifacts']['replay']['path']),
        '/candidate/owner512.hsaco':Path(seal['artifacts']['candidate']['path']),
        '/candidate/native0173-fl.hsaco':Path(seal['artifacts']['native']['path']),
        '/candidate/invoke_real_fl.py':HERE/'invoke_replay.py',
        '/candidate/capture_format.py':HERE/'capture_format.py',
        '/candidate/fl-delivery-seal.json':WORK/'delivery-seal.json',
    }
    for item in seal['sources']:
        assert sha(Path(item['path']))==item['sha256'],'Sealed source changed'
    for role,item in seal['artifacts'].items():
        assert sha(Path(item['path']))==item['sha256'],'Sealed '+role+' changed'
    for dest,path in delivered.items():
        assert dest not in mounts;mounts[dest]=service.r.linux_path(path)
    output='/tmp/alloy0173-real-fl-'+manifest['run_id']+'.flop'
    env['LD_PRELOAD']='/candidate/libhalogen0173-fl-capture.so:'+prior
    env.update(ALLOY0173_FL_CAPTURE_ENABLE='1',ALLOY0173_FL_CAPTURE_PATH=output)
    manifest['scratchfree_fl_capture']=dict(enabled=True,default_off=True,operation='first exact native N=3 FL',
        output_path=output,engine_sha256=ENGINE_SHA,capture_sha256=seal['artifacts']['capture']['sha256'],
        whole_stock_launch_forwarded=True,candidate_executed=False,selected_weight_max_bytes=25344000,
        entry_available_and_commit_floor_gib=22,runtime_available_and_commit_floor_gib=18,
        export_before_normal_stop=True,serving_gain_qualified=False)
    return manifest
def install(service):
    original=service.build_manifest
    def captured(options,attempt,run_id):return apply_manifest(service,original(options,attempt,run_id))
    service.build_manifest=captured
    return original
