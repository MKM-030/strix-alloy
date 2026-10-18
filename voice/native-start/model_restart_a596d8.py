"""One incident only; verify evidence or archive its dead lock. Never starts/stops WSL/model.
Historical failed/recovery=false records remain untouched. The user-requested
36 GiB restart admission is a new gate after confirmed owned terminal cleanup;
it does not reclassify the historical baseline-recovery failure.
"""
import argparse, datetime, hashlib, importlib.util, json, os, pathlib, subprocess, sys, time, urllib.request, uuid
Path = pathlib.Path
CLEAN = Path(r'C:\Projects\strix-alloy-clean')
BASE = CLEAN/'backends/halogen-wsl2-0.18.1'
START = Path(__file__).resolve().parent
OUT = START.parent/'native-speech-validation/runtime'
POLICY = START/'model-start-policy.json'
POLICY_SHA = '1a9e2392f765f800bb6e23f596d41db8fbe0b02d798c1050d328b5d975408e25'
ADMISSION_SHA = 'a14f0ec5894464ce46daf9f7adaf3b725111dddc4981a27e9dd3b6450c7e48a1'
RUN = 'a596d8b7119f4875b07ea1fedbc9768b'
OUTER = 'ac678e51cef84d819a8fd276dcb93271'
ATTEMPT = BASE/'.local/services'/RUN
LOCK = BASE/'.local/runner.lock'
PROFILE = CLEAN/'server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/halogen0181-version-bracket-20261012/serving0181-full262-exact-cache-candidate-20261013.json'
PROFILE_SHA = 'f62b654bd0cfd0bcd00b4ced7416b64584ca530e6be8120e5d61dc45b931c323'
PINS = {'C:\\Projects\\strix-alloy-clean\\server\\.local\\current.json': '9ca4615541571469068bb3f12c3d9985ce9764207fe3bc538e7db41a6e9f65bd', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\.local\\current-service.json': '3e6a2be74f255ba888ced78a4763d17a6a16b7dfe1324308329474812ce5962f', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\.local\\runner.lock': 'a264c6bf508cba9ba2d31501a6c66eb6605f07d24ff9c6bbd21d206d6884fba3', 'C:\\Projects\\strix-alloy-clean\\server\\.local\\optimization9h-20261004\\halogen0172-backend-preparation-20261008\\halogen0181-version-bracket-20261012\\serving0181-full262-exact-cache-candidate-20261013.json': 'f62b654bd0cfd0bcd00b4ced7416b64584ca530e6be8120e5d61dc45b931c323', 'C:\\Projects\\strix-alloy-clean\\server\\controller.py': 'a76f5078391f42a8203692c5c12c3d27d849e606fec345f25642c33124897d4b', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\.local\\services\\a596d8b7119f4875b07ea1fedbc9768b\\guard-failure.json': 'b7302049a4bd15e04fa4434705bfa98bd4733e517864b45ca93ab1f0da8d9b69', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\.local\\services\\a596d8b7119f4875b07ea1fedbc9768b\\outcome.json': '6c13cadbbc1cd92c1b781fcc451d338dfb359d2fd1dfded9b03e7396a7464e88', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\.local\\services\\a596d8b7119f4875b07ea1fedbc9768b\\terminal.json': '977f1b51164d4fc23a04653f10b5d1613247b33c165bc7fe62a276df92414b20', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\.local\\services\\a596d8b7119f4875b07ea1fedbc9768b\\recovery.json': 'd7029241c57500c678507ce50b17aec29bbd58ef9b5d7fe20aa4abffce07090f', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\.local\\services\\a596d8b7119f4875b07ea1fedbc9768b\\manifest.json': 'a53d398732cba09d25500ae5b4bb1dee369e511aafdbe1c902155783515d48ee', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\.local\\services\\a596d8b7119f4875b07ea1fedbc9768b\\container.json': '1b451735c8a2fc9893dab94ca854348c98c2259cff8023531cdf1b503f2eb75f'}
SOURCE_PINS = {'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\api_defaults.py': '129edc21c5aebb52b1df297bb5320b8298b527027a2e5c644c731981e6ea42c1', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\auth_api.py': 'd0a8cf1293f5e8846000b67668f6533b77a42053d04f6ef331210d4f99ea2a89', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\bounded_hash.py': '047043c45539b50d3f56253849db3fcc2ea8f3d0dc87105c65a29558e2a0f6e2', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\bridge_adapter.py': '41d30736779133555236d1a5de08775df4723b5dba58b1427ecbfc9a75bb834d', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\checkpoint_integrity.py': 'aa25634534ba11865113403648b8c667eed65529d7f10f508787416d47ef30ea', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\entrypoint_adapter.py': '1a64c6690f6ef05bbd6198c7e90a3c6c8a5ccab0bcc85bb5bfa458dad318198e', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\halogen0181_hip_probe.c': 'c9d39e16f87c990c7c3b93ece1c951704e9a24c551a14177537b805f7a4b6533', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\host_frames.py': '07460f02449429d47652bb774900d639e27faebdee0255b10f412343cbaa546e', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\kernel_controls.py': '800298b12d5f16b426eab0a9fb4b318ef2936d4448f4d2a902e8fb782c038d6a', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\lease_supervisor.py': '8c7c5f594e1b9ea0808f4546f877cbc38c3c636459268a8b8877df2328f885de', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\lookup_source.py': '3bb61c4a8b2007e43ba9b61b8b6c79d02a38b6830b7f77ded7292b4678761426', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\matmul_plan.py': '4baff6a9205688b052937d02e4dfaae8396668fbe416c5894bfea4dfe48667bd', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\matmul_tuning.py': '8e4b1aa275dab9d226745faed7b4fe36008f263d6044bbf97eca109ad488de37', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\memory_budget.py': '93548f9fd7a4eb991402829c6969dc0f311e5f3b256981cf3be4d6a4f39963c8', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\portable.py': '5769860ec17ab1f32751e28c8891684d24801e5e69bfd4219cc44b1dee8007e3', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\private_hsa.py': 'a06db99959de29ecb3414817b77e28315fbc98100aabbe33ce7624eaec200861', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\runner.py': '015832a15c97aaab1de06ab531f46f6dc08361e3a7a5bcc405e7747752083224', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\sample.ps1': 'f959c1528e002b94adfe3f01bf53693b62c9e09b70dfa363bbe1f38b0aaf414d', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\service.py': 'df7bfb62d9a52db4a200aa320f3712877718296931f1bb57a302de40a620c638', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\speculation_policy.py': '1ddfefd2bc6431b22c93fc8444afe6ff70a1cb6314413924c91d3533b124202a', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\startup_cache.py': 'a675031453e5eec9dfc6aae0d697b03bf74c2838a12f13ddafe76ebdb1c57977', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\startup_guard.py': '230b9ba7e7c751211dc14e239962ecae69689ad9a3118343568db09f0164b1eb', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\startup_monitor.py': 'c45677fd83e30e722e7079a26584111802da99e711881b894ccf01f707ed54f0', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\state_io.py': '12ce7b1fa75e1024087f1dadf90f4adeca19c7a79df62e71f595ce6f904f1347', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\patches\\halogen-preflight-bridge.c': 'f921bd8a0ca21403f2ca42c49b099c6ca8b27aa2de6a80227aa82e6cb11ad21b', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\patches\\halogen-preflight-trampoline.S': '77f30756961d2e1680af8e162c2634e57b1e638ac2cf963796ad1f5fc409aa99', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\patches\\hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\patches\\hip-register-hybrid.c': 'e1127efa886359c6ac568f53468df86b1b00e1e17519f539fbb2d12bcd8dc526', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\patches\\hip-register-private-rw.c': '59cc8a080f7e6c37b08f09aa703a031df251217df848a1ec49d1bd7d6d1e1a7a', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\profiles\\release.json': 'd350e258c5264b0b3464b4dd3c6802fd62d55daeeec23ec60e90968688dd4781', 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\profiles\\sources.json': 'c8e6e14cd7fc12e8e455594139ff95ce2283f14b657375991b4695f61aa06a68'}
SOURCE_PINS.update({str(CLEAN/'server'/name):value for name,value in {'gateway.py': '0f7795d5ef66871d1c0f84abdd6e60f73d1d5b2a518e09709d6ca26070123b71', 'console_trace.py': 'a20796432f760e09f1f3e701e638510d7a11a7210fdc62798e26a019100901ca', 'draft_profiles.py': '66e8eebbe4691a8f1fffa974ec44889eea50024ca9bbb6400a32679e99046250', 'gufo_serial_profile.py': 'f26b06abc6be7c77bbcf8b574028ef62971ac087a2f84b28104f501251516c9f', 'host_frames.py': '417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8', 'owned_child.py': '6f75520f65c76941ec4306915929fd529ec7f46bd0fd20bd6f01f82afb749f10', 'winjob.py': '3d2db1c5c8ea3846152a0073dd4ed324a47ffd36ac63bf8f48cc52e39b0d4d4c'}.items()})
SOURCE_PINS.update({str(POLICY):POLICY_SHA,str(START/'model_admission.py'):ADMISSION_SHA})
APPROVED_SOURCE_AUDIT = {'approval': 'Root full-current-source audit approved repinning these two files in this session; no claim that atomic replacement is the sole historical service difference.', 'reviewed_full_service_sha256': 'df7bfb62d9a52db4a200aa320f3712877718296931f1bb57a302de40a620c638', 'registry_difference': 'Only files.scripts/service.py hash changed; substituting the original hash reconstructs the exact original registry SHA256.', 'updates': [{'path': 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\scripts\\service.py', 'original_sha256': 'dc0ae3602967accaded3a9a8e4cadc7dd16d6ffcc468026cde9ce20f39ef1e6e', 'approved_sha256': 'df7bfb62d9a52db4a200aa320f3712877718296931f1bb57a302de40a620c638'}, {'path': 'C:\\Projects\\strix-alloy-clean\\backends\\halogen-wsl2-0.18.1\\profiles\\sources.json', 'original_sha256': 'a35a376365d8cac9a256546f763ace11df17fcf166e62688ea8a062fea42dc5a', 'approved_sha256': 'c8e6e14cd7fc12e8e455594139ff95ce2283f14b657375991b4695f61aa06a68'}]}
def require(ok, message):
    if not ok: raise ValueError(message)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):
    require(path.stat().st_size <= 8*1024*1024, 'Oversized evidence file')
    return json.loads(path.read_text(encoding='utf-8-sig'))
def hashes():
    actual={path:sha(Path(path)) for path in PINS}
    require(actual==PINS,'Pinned run/profile/lock/evidence drift; no reconciliation')
    require(all(sha(Path(p))==h for p,h in SOURCE_PINS.items()),'Pinned runtime source drift')
    return actual

def no_owners():
    # Output primitive fields only: never serialize CIM objects/annotated Get-Content strings.
    command = r'''$ErrorActionPreference='Stop'
$bad=@(Get-CimInstance Win32_Process | Where-Object {
 $_.Name -match '^(python(w)?|py)\.exe$' -and $_.CommandLine -and
 ($_.CommandLine -match '(controller|service|runner|startup_guard|host_frames)\.py' -or
  $_.CommandLine -like '*strix-alloy-clean\backends\halogen-wsl2-0.18.1*')
} | ForEach-Object { [ordered]@{pid=[int]$_.ProcessId;parent=[int]$_.ParentProcessId;name=[string]$_.Name;created_utc=$_.CreationDate.ToUniversalTime().ToString('o')} })
$dead=@(Get-CimInstance Win32_Process -Filter 'ProcessId=24916 OR ProcessId=24684' | ForEach-Object { [ordered]@{pid=[int]$_.ProcessId;name=[string]$_.Name} })
# 8841 is the separate surviving queued gateway, not this model controller.
$ports=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object {$_.LocalPort -in 8731,8840} | ForEach-Object { [ordered]@{port=[int]$_.LocalPort;pid=[int]$_.OwningProcess} })
[ordered]@{processes=$bad;listeners=$ports;dead_owned_pids=$dead}|ConvertTo-Json -Compress -Depth 4
'''
    done=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,check=True,timeout=15)
    require(len(done.stdout)<65536,'Unexpected owner output size')
    state=json.loads(done.stdout)
    require(not state['processes'],'Controller/service/guard/runner process remains')
    require(not state['listeners'],'Model/controller listener remains')
    require(not state['dead_owned_pids'],'A pinned formerly owned PID is now present')
    wsl=subprocess.run(['wsl.exe','--list','--running','--quiet'],capture_output=True,check=True,timeout=10)
    text=wsl.stdout.decode('utf-16-le' if b'\x00' in wsl.stdout else 'utf-8',errors='strict').lstrip('\ufeff').strip()
    require(not text,'WSL running or listing ambiguous; no start/stop/inspect attempted')
    state['wsl_running']=[]
    return state

def admission_policy():
    require(sha(POLICY)==POLICY_SHA and sha(START/'model_admission.py')==ADMISSION_SHA,'Requested admission policy/source drift')
    spec=importlib.util.spec_from_file_location('scc_model_admission',START/'model_admission.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module,module.load_policy(POLICY)

def verify():
    require(os.name=='nt','This verifier is Windows-only')
    initial=hashes()
    admission,policy=admission_policy()
    outer=load(CLEAN/'server/.local/current.json'); current=load(BASE/'.local/current-service.json')
    outcome=load(ATTEMPT/'outcome.json'); recovery=load(ATTEMPT/'recovery.json')
    terminal=load(ATTEMPT/'terminal.json'); manifest=load(ATTEMPT/'manifest.json')
    cid=load(ATTEMPT/'container.json')['id']
    require(outer['run_id']==OUTER and outer['phase']=='failed' and outer['pid']==24916 and outer['profile_sha256']==PROFILE_SHA,'Outer run mismatch')
    require(current['run_id']==RUN and current['phase']=='failed' and current['prompt_cache']=='Exact' and current['context']==262144 and current['slots']==1 and current['controller_pid']==24684 and current['attempt']==str(ATTEMPT) and current['container_id']==cid,'Backend run mismatch')
    require(cid=='b9461a83736380ee84f2b3aaee05abf4fed894b7b09400753bdf506ede1e95be','Exact container changed')
    require(recovery['baseline_available_bytes']==52297777152 and recovery['required_available_bytes']==50150293504,'Original recovery baseline changed')
    guard=load(ATTEMPT/'guard-failure.json')
    require(guard['sample_age']==0.0 and guard['last_frame']['available_bytes']==18848247808 and guard['last_frame']['commit_headroom_bytes']==116149338112,'Historical guard failure changed')
    require(LOCK.read_text(encoding='utf-8').strip()==RUN,'Lock content mismatch')
    require(outcome['cleanup'] is True and outcome['recovery'] is False and recovery['passed'] is False,'Expected historical cleanup/recovery facts changed')
    sys.path.insert(0,str(BASE/'scripts'))
    import runner as r, service, host_frames
    service.owned(terminal,cid,manifest); r.validate_terminal(terminal['State'])
    require(terminal['State'].get('Pid')==0,'Terminal still has an engine PID')
    before=no_owners()
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open('http://127.0.0.1:8860/health',timeout=5) as resp:
        require(resp.status==200 and json.loads(resp.read(65536))['nativeSessions']==0,'Native session active')
    frames=[]; sample_ages=[]
    for i in range(5):
        begin=time.monotonic(); frame=host_frames.frame(); age=time.monotonic()-begin
        r.check_frame(frame,age=age); frames.append(frame); sample_ages.append(age)
        # New user-requested physical admission; managed runtime guards stay unchanged.
        admission.check_start_frame(frame,policy,age=age,restart=True)
        if i<4: time.sleep(1)
    require(admission.terminal_restart_passed(frames,policy,cleanup_confirmed=outcome['cleanup']),f'Requested terminal restart gate requires {policy["terminal_restart_physical_gib"]:g} GiB physical and {policy["start_commit_headroom_gib"]:g} GiB commit; safety lock unchanged.')
    after=no_owners(); require(hashes()==initial,'Evidence changed during verification')
    # Repeat the requested restart gate after slow OS owner/hash checks.
    begin=time.monotonic(); frame=host_frames.frame(); age=time.monotonic()-begin
    r.check_frame(frame,age=age); frames.append(frame); sample_ages.append(age)
    admission.check_start_frame(frame,policy,age=age,restart=True)
    require(admission.terminal_restart_passed(frames,policy,cleanup_confirmed=outcome['cleanup']),'Final requested terminal restart gate failed')
    final_sample_unix=time.time()
    return {'schema':1,'run':RUN,'outer_run':OUTER,'verified_unix':time.time(),
      'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'final_sample_unix':final_sample_unix,'final_sample_monotonic':time.monotonic(),
      'source_sha256':sha(Path(__file__)), 'protected_hashes':initial,'source_pins':SOURCE_PINS,'controller_lease_held':True,
      'owners_before':before,'owners_after':after,'container_id':cid,'container_name':terminal['Name'],
      'terminal_state':terminal['State'],'terminal_source':'pinned persisted owned terminal + all WSL stopped; no live docker call',
      'fresh_frames':frames,'sample_ages_seconds':sample_ages,'requested_restart_gate_passed':True,'admission_policy':policy,'admission_policy_sha256':POLICY_SHA,
      'required_available_bytes':int(policy['terminal_restart_physical_gib']*r.GIB),'historical_required_available_bytes':recovery['required_available_bytes'],
      'historical_cleanup':True,'historical_recovery':False,'historical_records_unchanged':True,
      'approved_source_audit':APPROVED_SOURCE_AUDIT,'source_predicate':'user-requested physical restart policy after confirmed owned terminal cleanup', 'model_started':False,'wsl_modified':False}

def write_new(path,record):
    with path.open('x',encoding='utf-8') as stream:
        json.dump(record,stream,indent=2); stream.flush(); os.fsync(stream.fileno())

def archive_lock(destination):
    require(not destination.exists(),'Archive target exists')
    require(sha(LOCK)==PINS[str(LOCK)] and LOCK.read_text().strip()==RUN,'Final lock drift')
    LOCK.rename(destination)  # Windows rename refuses overwriting an existing destination.
    require(not LOCK.exists() and sha(destination)==PINS[str(LOCK)],'Archive verification failed')
    require(all(sha(Path(p))==h for p,h in PINS.items() if p!=str(LOCK)),'Protected evidence changed')

def reconcile(mode,prior_path):
    prior=None
    if mode=='archive':
        require(prior_path is not None,'--archive requires --verified-receipt')
        prior=load(prior_path)
        require(prior.get('schema')==1 and prior.get('mode')=='verify' and prior.get('phase')=='verified' and prior.get('run')==RUN and prior.get('outer_run')==OUTER and prior.get('archived') is False and prior.get('requested_restart_gate_passed') is True and prior.get('admission_policy_sha256')==POLICY_SHA and prior.get('historical_recovery') is False and prior.get('protected_hashes')==PINS and prior.get('source_pins')==SOURCE_PINS,'Not a successful exact verify receipt')
        require(0<=time.time()-prior['verified_unix']<=180,'Verification receipt older than 180 seconds')
        require(prior['source_sha256']==sha(Path(__file__)),'Verifier source changed')
    result=verify()
    if prior is not None:
        require(result['protected_hashes']==prior['protected_hashes'],'Receipt evidence drift')
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    receipt=OUT/f'reconciliation-{RUN}-{mode}-{stamp}.json'
    result.update(archived=False,phase='verified',receipt=str(receipt),mode=mode)
    if mode=='archive':
        destination=OUT/f'{RUN}-{stamp}.runner.lock'
        result.update(archive_destination=str(destination),prior_verify_receipt=str(prior_path))
        # Preserve an immutable receipt BEFORE the sole mutation; final receipt is a new file.
        write_new(receipt,result)
        require(0<=time.monotonic()-result['final_sample_monotonic']<=2,'Final direct memory sample older than two seconds')
        archive_lock(destination)
        result.update(archived=True,phase='archived')
        receipt=receipt.with_name(receipt.stem+'-complete.json'); result['receipt']=str(receipt)
    write_new(receipt,result)
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    mode=ap.add_mutually_exclusive_group(required=True); mode.add_argument('--verify',action='store_true'); mode.add_argument('--archive',action='store_true')
    ap.add_argument('--verified-receipt',type=Path); args=ap.parse_args()
    require(args.archive or args.verified_receipt is None,'Receipt is only accepted for --archive')
    hashes()  # Pin imported package code before executing it.
    sys.path.insert(0,str(CLEAN/'server')); import controller
    with controller.lease(CLEAN/'server/.local/controller.lock'):
        result=reconcile('archive' if args.archive else 'verify',args.verified_receipt)
    print(json.dumps({k:result[k] for k in ('run','receipt','archived','requested_restart_gate_passed','historical_recovery','model_started','wsl_modified')},indent=2))
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,RuntimeError,subprocess.SubprocessError) as exc:
        print('REFUSED: '+str(exc),file=sys.stderr);raise SystemExit(2)
