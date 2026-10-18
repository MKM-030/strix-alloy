"""Activate only reviewed idle Native; no model/other-app/service changes."""
import datetime, hashlib, importlib.util, json, os, subprocess, sys, time
from pathlib import Path
import psutil

ROOT=Path(r'C:\Projects\strix-alloy-scc-voice')
NATIVE=ROOT/'voice/native-bridge'
STAGE=NATIVE/'.ice-candidate-20261014'
LIVE=NATIVE/'native_bridge.py'
CONFIG=NATIVE/'config.example.json'
OWNER=ROOT/'voice/native-start/runtime/native-owner.json'
BASE='0b7c6705488b81e5e93f192154dbb670d3cfd1d70011282245398f54a9a5647d'
NEW='91d61c8dae3055bad64bde48f7e62a6864449c0cb8246058445bfdaa1107a943'
PLAN_SHA='0db22c748e9f57696f1245f8e6a07e5139fa2c1174e1deaf0d6ca0bee78ec772'
TEST_SHA='ba1ff18e2ccce46b9c851039ba17a20d5da897eb03b3cc1c07cef4bc6bf81cdd'
TEST_REPORT=STAGE/'ICE-VALIDATION-20261014.json'

def require(value,reason):
    if not value: raise RuntimeError(reason)
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);sys.modules[name]=value;spec.loader.exec_module(value);return value
def ident(p):
    return {'pid':p.pid,'created':p.create_time(),'exe_sha256':hashlib.sha256(p.exe().encode()).hexdigest(),
            'cmd_sha256':hashlib.sha256(json.dumps(p.cmdline()).encode()).hexdigest()}

def main():
    require(sys.argv[1:]==['--activate-reviewed'],'EXPLICIT_ACTIVATION_ARGUMENT_REQUIRED')
    require(digest(STAGE/'activation-plan.json')==PLAN_SHA,'PLAN_CHANGED')
    plan=json.loads((STAGE/'activation-plan.json').read_text())
    require(plan['native']['pid']==3704 and plan['native_parent']['pid']==27084,'REVIEWED_OWNER_CHANGED')
    require(plan['source_sha256']==BASE and plan['candidate_sha256']==NEW,'REVIEWED_SOURCE_PLAN_CHANGED')
    require(digest(TEST_REPORT)==TEST_SHA,'TEST_REPORT_CHANGED')
    tests=json.loads(TEST_REPORT.read_text())
    transport=tests.get('candidate_transport',{});regression=tests.get('regression',{})
    require(tests.get('baseline_sha256')==BASE and tests.get('candidate_sha256')==NEW
        and transport.get('result')=='passed' and transport.get('count')==2
        and transport.get('real_rtp_two_way') is True and transport.get('server_srflx_candidates',0)>0
        and transport.get('authorization_denied_invalid_token') is True
        and regression.get('result')=='passed' and regression.get('count')==50,'TEST_GATE_FAILED')
    test_summary={'passed':True,'test_count':52,'report_sha256':TEST_SHA,'candidate_sha256':NEW,
        'transport_tests':2,'regression_tests':50,'real_rtp_two_way':True,'invalid_auth_denied':True}
    start=module('ice_native_start',ROOT/'voice/native-start/start_services.py')
    status=module('ice_native_status',ROOT/'voice/native-speech-validation/stack_status.py')
    old=psutil.Process(3704);parent=psutil.Process(27084)
    args=parent.cmdline();worker_args=old.cmdline();old_exe=old.exe()
    require(args[1:]==worker_args[1:] and str(LIVE) in args,'NATIVE_ARGUMENTS_CHANGED')
    require(args[-2:]==['--config',str(CONFIG)] and '--probe-backend' not in args,'PRODUCTION_CONFIG_REQUIRED')
    receipt={'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'before_sha256':BASE,
             'after_sha256':NEW,'tests':test_summary,'preflight':[],'scope':'Owned Native only'}
    def protected():
        for port,item in plan['protected'].items():
            require({c.pid for c in start.listeners(int(port))}=={item['pid']},'PROTECTED_LISTENER_CHANGED')
            require(ident(psutil.Process(item['pid']))==item,'PROTECTED_PROCESS_CHANGED')
        for path,key in [(ROOT/'server/gateway.py','gateway_source_sha256'),
                         (ROOT/'server/.local/scc-gateway.json','gateway_config_sha256'),
                         (ROOT/'server/.local/scc-gateway-state.json','gateway_state_sha256')]:
            require(digest(path)==plan[key],'PROTECTED_GATEWAY_SOURCE_CONFIG_STATE_CHANGED')
    def native_health(): return status.health(8860)
    def idle():
        n=native_health();m=status.health(8731,token=status.MODEL.read_text(encoding='utf-8-sig').strip())
        g=status.health(8841,token=status.credential(status.GATEWAY))
        require(n.get('http_status')==200 and n.get('nativeSessions')==0 and n.get('auth_mode')=='servicenow','NATIVE_NOT_IDLE')
        require(m.get('http_status')==200 and m.get('expected_model') is True and m.get('version_matches') is True
                and m.get('busy') is False and m.get('in_flight')==0 and m.get('queued')==0,'MODEL_NOT_IDLE_OR_EXPECTED')
        require(g.get('http_status')==200 and g.get('active_requests')==0 and g.get('queued_requests')==0
                and g.get('draining') is False,'GATEWAY_NOT_IDLE')
        require(status.memory().get('above_runtime_floor') is True,'MEMORY_FLOOR_FAILED')
        receipt['preflight'].append({'native':n,'model':m,'gateway':g})
    def gate():
        protected()
        require(digest(LIVE)==BASE and digest(STAGE/'native_bridge.py')==NEW,'SOURCE_CAS_CHANGED')
        require(digest(CONFIG)==plan['config_sha256'] and digest(OWNER)==plan['owner_sha256'],'CONFIG_OWNER_CAS_CHANGED')
        require(start.owned_listener(8860,args)==3704,'NATIVE_LISTENER_CHANGED')
        require(ident(old)==plan['native'] and ident(parent)==plan['native_parent'] and old.parent().pid==27084,'NATIVE_IDENTITY_CHANGED')
        own=json.loads(OWNER.read_text());require(own['pid']==old.pid and own['created']==old.create_time()
            and own['exe']==old.exe() and own['cmdline']==old.cmdline(),'NATIVE_OWNER_RECEIPT_CHANGED')
        cfg=json.loads(CONFIG.read_text(encoding='utf-8-sig'))
        require(cfg.get('auth_mode')=='servicenow' and not cfg.get('development_token')
                and not cfg.get('development_token_file'),'PINNED_AUTH_REQUIRED')
        idle()
    fresh_child=None
    def spawn():
        nonlocal fresh_child
        runtime=ROOT/'voice/native-start/runtime'
        with (runtime/'native.stdout.log').open('ab') as out,(runtime/'native.stderr.log').open('ab') as err:
            fresh_child=subprocess.Popen(args,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=out,stderr=err,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.DETACHED_PROCESS)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            pid=start.owned_listener(8860,args)
            if pid:
                p=psutil.Process(pid);require(p.exe()==old_exe and p.cmdline()[1:]==worker_args[1:]
                    and p.parent().pid==fresh_child.pid,'NEW_NATIVE_IDENTITY_CHANGED')
                info=native_health();require(info.get('http_status')==200 and info.get('nativeSessions')==0
                    and info.get('auth_mode')=='servicenow','NEW_NATIVE_HEALTH_FAILED')
                temporary=OWNER.with_suffix('.tmp');temporary.write_text(json.dumps({'pid':p.pid,
                    'created':p.create_time(),'exe':p.exe(),'cmdline':p.cmdline()}),encoding='utf-8');os.replace(temporary,OWNER)
                return p,info
            if fresh_child.poll() is not None:raise RuntimeError('NEW_NATIVE_LAUNCHER_EXITED')
            time.sleep(.1)
        raise RuntimeError('NEW_NATIVE_START_TIMEOUT')
    temp=LIVE.with_name('native_bridge.ice-activation.tmp');backup=STAGE/'native-before.py'
    stopped=False
    with start.startup_lock():
        gate();time.sleep(.3);gate()
        require(not backup.exists(),'ACTIVATION_ALREADY_STARTED')
        backup.write_bytes(LIVE.read_bytes());require(digest(backup)==BASE,'BACKUP_HASH_FAILED')
        (STAGE/'owner-before.json').write_bytes(OWNER.read_bytes())
        temp.write_bytes((STAGE/'native_bridge.py').read_bytes());require(digest(temp)==NEW,'STAGED_HASH_FAILED')
        (STAGE/'activation-before.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        gate()
        try:
            old.terminate();old.wait(timeout=8);stopped=True;parent.wait(timeout=8)
            os.replace(temp,LIVE)
            fresh,info=spawn();protected();require(digest(CONFIG)==plan['config_sha256'] and digest(LIVE)==NEW,'POST_ACTIVATION_CAS_CHANGED')
            receipt.update({'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'new_owner':ident(fresh),'new_launcher_pid':fresh_child.pid,'native_after':info,
                'protected_processes_unchanged':True,'config_unchanged':True,'live_sha256':digest(LIVE)})
            (STAGE/'activation-complete.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
            print(json.dumps(receipt),flush=True)
        except Exception:
            if stopped:
                try:
                    protected();require(digest(CONFIG)==plan['config_sha256'] and digest(LIVE) in {BASE,NEW},'ROLLBACK_CAS_FAILED')
                    pid=start.owned_listener(8860,args)
                    if pid:
                        p=psutil.Process(pid);require(fresh_child is not None and p.parent().pid==fresh_child.pid,'ROLLBACK_FOREIGN_OWNER')
                        n=native_health();require(n.get('http_status')==200 and n.get('nativeSessions')==0,'ROLLBACK_NATIVE_ACTIVE_OR_UNKNOWN')
                        p.terminate();p.wait(timeout=8);fresh_child.wait(timeout=8)
                    elif fresh_child is not None:require(fresh_child.poll() is not None,'ROLLBACK_LAUNCHER_STILL_LOADING')
                    temp.write_bytes(backup.read_bytes());os.replace(temp,LIVE)
                    rollback,info=spawn();protected();require(digest(LIVE)==BASE,'ROLLBACK_HASH_FAILED')
                    receipt.update({'rollback_completed':True,'rollback_owner':ident(rollback),'rollback_health':info})
                except Exception as e:receipt.update({'rollback_completed':False,'rollback_error_type':type(e).__name__,
                    'rollback_reason':str(e) if isinstance(e,RuntimeError) else 'external-operation-failed'})
                (STAGE/'activation-failed.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
            raise

try:main()
except Exception as error:
    import traceback
    print(json.dumps({'operation':'activate-urgent-browser-ice','error_type':type(error).__name__,
        'reason':str(error) if isinstance(error,RuntimeError) else 'external-operation-failed',
        'safe_frames':[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name}
                       for f in traceback.extract_tb(error.__traceback__)]}),flush=True)
    raise SystemExit(3)
