"""Fresh standard-server proof and current continuation identities."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from datetime import datetime,timezone

WORK=Path(__file__).resolve().parent
PREP=WORK.parent
ROOT=PREP.parents[3]
STATE=PREP.parent/'continuation-current.json'
PROFILE=PREP/'halogen0173-migration-20261009/thinking-latest-profile.json'
sys.path.insert(0,str(ROOT/'server'))
from controller import atomic,read
spec=importlib.util.spec_from_file_location('sdma_control',WORK/'control.py')
control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)

def main():
    for name in ('before','candidate','after'):
        assert read(WORK/name/'summary.json')['passed']
    for name in ('before','candidate'):
        assert read(WORK/(name+'-stop.json'))['own_handles_closed']
    latest=control.checkpoint('after')
    console=read(WORK/'after-visible-launch.json')['console_identity']
    assert control.migration.identity(console['pid'])==console
    current=latest['controller'];inner=latest['backend'];ids=latest['identities']
    health=control.migration.health(read(PROFILE))
    assert health['completed']==latest['health']['completed'] and health['cancelled']==0
    manifest=read(Path(inner['attempt'])/'manifest.json')
    assert manifest['environment']['HSA_ENABLE_SDMA']=='1' and 'sdma0_candidate' not in manifest
    record=dict(verified_utc=datetime.now(timezone.utc).isoformat(),controller_identity=ids['controller'],
        backend_identity=ids['backend'],console_identity=console,controller_run_id=current['run_id'],
        backend_run_id=inner['run_id'],container_id=inner['container_id'],version='0.17.3',health=health,
        SDMA='1',original_ready_open=True,own_measurement_helpers_closed=True,
        NPU_executed=False,automation_pause_preserved=True,full_goal_completed=False)
    atomic(WORK/'final-ready-open.json',record)
    s=read(STATE)
    s['current_user_server']=dict(phase='ready',controller_pid=current['pid'],controller_run_id=current['run_id'],
        backend_controller_pid=inner['controller_pid'],backend_run_id=inner['run_id'],container_id=inner['container_id'],
        controller_identity=ids['controller'],backend_identity=ids['backend'],foreground_console_identity=console,
        context=262144,endpoint='http://127.0.0.1:8840/v1',keep_open_after_trial=True,npu_integrated=False,
        version='0.17.3',console_trace=True,profile=str(PROFILE),profile_sha256=current['profile_sha256'],
        prefill_chunk=8192,max_prefill_tokens=8192,api_defaults=read(PROFILE)['engine']['api_defaults'],
        original_ready_open=True,latest_ready_open=True,latest_verified_utc=record['verified_utc'],latest_observation=str(WORK/'final-ready-open.json'))
    s['active_engine_sessions']=[dict(role='normal',version='0.17.3',phase='ready',
        controller=dict(pid=current['pid'],run_id=current['run_id'],identity=ids['controller']),
        backend=dict(pid=inner['controller_pid'],run_id=inner['run_id'],identity=ids['backend']),
        console_identity=console,tool_session_id=None)]
    s['active_session']=dict(role='normal',controller_pid=current['pid'],controller_run_id=current['run_id'],
        backend_pid=inner['controller_pid'],backend_run_id=inner['run_id'],console_pid=console['pid'],
        engine_session_id=None,observer_session_id=None,benchmark_session_id=None)
    s['active_measurement_identities']=[];s['active_optimization_children']=[]
    s['active0173_sdma0_comparison']=dict(phase='terminal-standard-ready-open',directory=str(WORK),
        engine_tool_session=None,observer_tool_session=None,benchmark_tool_session=None,
        all_three_cohorts_complete=True,unchanged_repeat=False,candidate_remains_off=True,
        final_receipt=str(WORK/'final-ready-open.json'),full_goal_completed=False)
    s['latest0173_sdma0_result']=dict(analysis=str(WORK/'analysis.json'),report='docs/research/halogen0173-normal-sdma0-20261009.md',
        evidence='docs/research/halogen0173-normal-sdma0-20261009.json',serving_gain_adopted=False,NPU_executed=False)
    s['latest0173_npu_selector_scope']=dict(decision=str(PREP/'npu-confidence-selector-scope-20261009/decision.md'),
        source_only=True,trained=False,live_callback_implemented=False,NPU_executed=False,
        distinct_hypothesis='token-only prefix-survival/offer-width selector',full_goal_completed=False)
    s['active_goal']='Active, unachieved: normal0.17.3 restored ready/open. Distinct normal SDMA1/0/1 screen completed with parity; no speed candidate adopted. NPU token-only selector source contract saved, live owned callback/training absent.'
    s['this_goal_turn_classification']='progress';s['timestamp_utc']=record['verified_utc']
    atomic(STATE,s)
    print(json.dumps(record))

if __name__=='__main__':main()
