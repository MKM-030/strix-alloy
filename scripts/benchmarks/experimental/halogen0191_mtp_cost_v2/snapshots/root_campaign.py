"""Root 8 cost-gate companion. Source-only by default with exact normal restoration."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import traceback

ROOT = Path('C:/Projects/strix-alloy-clean')
HERE = Path(__file__).resolve().parent
PRIMARY = HERE.parent
RAW_PREP = PRIMARY / 'raw-phase-prep'
PACKAGE = ROOT / 'backends/halogen-wsl2-0.19.1'
BOUND = HERE / 'integration/root-bound'
NORMAL = PRIMARY / 'serving0191-text32k-one-slot-2048.json'
NORMAL_SHA256 = '69b91ddae6daa21b7c4d7666077847e4913fd9b59aedd149201c9d0ccd994b84'
OUT = PRIMARY / 'mtp_gate_cost-raw-comparison'
PLAN_PATH = 'docs/benchmarks/halogen0191-mtp-cost-gate-plan-20261107-v2.json'
REGISTRATION = HERE / 'registration.json'
EXPORTER_SOURCE = HERE / 'export_comparison.py'
CASE_NAMES = ('natural8192', 'natural16384')
STATE = ROOT / 'server/.local/optimization9h-20261004/continuation-current.json'
LOG_REQUEST_SHA = '01cc7e91b876efb6a40b531e15716be3a0c8d15f72aef3f994b5f67d15ff26d9'
LOG_EXPECTED_SHA = 'c4cbbcd81d735ad71e43bf99d87a8e5f8080646bc90db8e55e5a45dc2e1a58ee'
LOG_SERIAL_REQUEST_SHA = 'c4d9d4ce2af9ce4a5cdf0b888318db5c85f62ae3939c18562162bf8c21739519'
LOG_REFERENCE_MANIFEST_SHA = 'c920c79bd7950d9daa462fba9864daf55306c1129656af281e612a40f3f1347c'
LOG_REFERENCE_SHA = '0465ec6c46f28e1379673e13ce0fe67d55bf2fac36ee66d76a42b77141d53e50'


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite_path(root, relative):
    path = root / relative
    if (Path(relative).is_absolute() or not path.resolve().is_relative_to(root.resolve())
            or any(part.is_symlink() or part.is_junction() for part in (path, *path.parents))):
        raise ValueError('Nonfinite or linked transition path ' + relative)
    return path


def campaign_output(experiment, attempt=None):
    name = experiment + '-raw-comparison'
    if attempt is not None:
        if type(attempt) is not str or re.fullmatch(r'[a-z0-9-]{1,40}', attempt) is None:
            raise ValueError('Attempt must contain 1 to 40 lowercase letters, digits or hyphens')
        name += '-' + attempt
    return finite_path(PRIMARY, name)


def campaign_paths(experiment):
    if experiment == 'mtp_gate_cost':
        return (PRIMARY / 'serving0191-text32k-one-slot-2048.json', HERE / 'integration/root-bound')
    if experiment == 'draft_vocab_q8':
        return (PRIMARY / 'serving0191-text32k-one-slot-2048.json',
                PRIMARY / 'next-mechanisms-1722/q8-candidate')
    return (PRIMARY / 'serving0191-text32k-two-slot-2048.json',
            HERE / 'integration/root-bound')


def source_rows():
    paths = ((HERE / 'root_campaign.py', None),
        (RAW_PREP / 'collector/collect_epoch.py', '098f8b88d10e2b1dece7f602765da568ac2b9fec06591c4792c3e1da183f6896'),
        (RAW_PREP / 'collector/qpc_audit.py', 'cddbca2a95c0a20511e68838e4f6ad3b2ca222e0546f0bdca5aa890b08415b18'),
        (BOUND / 'transition.json', 'a2de768efb642b5a375cdf60d81de4d5a4395a215f46662160f2327370d1f880'),
        (RAW_PREP / 'observer/root-dso-pin.json', '5364ea9f20aaab052916488a26b139b222acea223f7048a929fb3c9f6a292187'),
        (HERE / 'mtp_cost_trace.py', None))
    result = {}
    for path, expected in paths:
        if not path.is_file() or any(part.is_symlink() or part.is_junction() for part in (path, *path.parents)):
            raise ValueError('Missing or linked finite executed source')
        identity = digest(path)
        if expected is not None and identity != expected:
            raise ValueError('Finite executed source differs ' + path.name)
        result[str(path)] = dict(sha256=identity, bytes=path.stat().st_size)
    return result


def verify_normal_profile():
    if (not NORMAL.is_file()
            or any(part.is_symlink() or part.is_junction() for part in (NORMAL, *NORMAL.parents))
            or digest(NORMAL) != NORMAL_SHA256):
        raise ValueError('Canonical normal profile differs')


def registered_sources(registration=None, *, repository=ROOT):
    if registration is None:
        if not REGISTRATION.is_file():
            raise ValueError('Cost campaign requires its committed preregistration')
        registration = json.loads(REGISTRATION.read_bytes())
    if (type(registration) is not dict
            or set(registration) != {'schema', 'commit', 'plan_path', 'plan_sha256'}
            or registration['schema'] != 'halogen0191.mtp-gate-cost-registration.v1'
            or type(registration['commit']) is not str
            or re.fullmatch('[a-f0-9]{40}', registration['commit']) is None
            or registration['plan_path'] != PLAN_PATH
            or type(registration['plan_sha256']) is not str
            or re.fullmatch('[a-f0-9]{64}', registration['plan_sha256']) is None):
        raise ValueError('Invalid finite cost preregistration')
    path = finite_path(Path(repository), PLAN_PATH)
    if not path.is_file() or digest(path) != registration['plan_sha256']:
        raise ValueError('Working preregistered plan differs')
    committed = subprocess.run(['git', 'show', registration['commit'] + ':' + PLAN_PATH],
        cwd=repository, capture_output=True, check=False, timeout=30, shell=False)
    if (committed.returncode != 0 or committed.stdout != path.read_bytes()
            or hashlib.sha256(committed.stdout).hexdigest() != registration['plan_sha256']):
        raise ValueError('Committed preregistered plan differs')
    plan = json.loads(committed.stdout)
    rows = source_rows()
    logical = {Path(name).name: pin for name, pin in rows.items()}
    pins = plan.get('executed_source_pins')
    if (plan.get('schema') != 'halogen0191.mtp-cost-gate-plan.v1'
            or plan.get('experiment') != 'mtp_gate_cost' or type(pins) is not dict
            or set(pins) != set(logical)
            or any(type(pin) is not dict or set(pin) != {'sha256', 'bytes'}
                   or type(pin['bytes']) is not int for pin in pins.values()) or pins != logical):
        raise ValueError('Preregistered executed source pins differ')
    exporter = plan.get('exporter_source_pin')
    if (type(exporter) is not dict or set(exporter) != {'sha256', 'bytes'}
            or type(exporter['bytes']) is not int or not EXPORTER_SOURCE.is_file()
            or exporter != dict(sha256=digest(EXPORTER_SOURCE), bytes=EXPORTER_SOURCE.stat().st_size)):
        raise ValueError('Preregistered companion exporter source differs')
    return dict(schema='halogen0191.mtp-gate-cost-executed-sources.v1',
                registration=dict(registration), files=rows)


def native_environment(rule):
    return dict(HALOGEN_MTP_GATE_RULE=rule, HALOGEN_MTP_GATE_P='0.90', HALOGEN_DRAFT_VOCAB_Q8='0',
        HALOGEN_SERVE_TRACE='1', HALOGEN_DECODE_PREFETCH='0', HALOGEN_PLD='3,3', HGN0191_RAW_ENABLE='1')


def qualify_arm_ids(arm_results, samples):
    ids = [sample['native_request_id'] for result in arm_results.values() for sample in result['samples']]
    ids += [sample['native_request_id'] for sample in samples]
    if len(ids) != len(set(ids)):
        raise ValueError('Native request ID repeated across cases in the same engine arm')


def save_cost_trace(runtime, active, profile, output, report, arm_results):
    from mtp_cost_trace import qualify_trace
    qualify_arm_ids(arm_results, report['samples'])
    rule = runtime.ops.read(profile)['engine']['speculation_policy']['HALOGEN_MTP_GATE_RULE']
    attempt = Path(active['inner']['attempt'])
    manifest_bytes = (attempt / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    expected = native_environment(rule)
    actual = {key: manifest['environment'].get(key) for key in expected}
    if (actual != expected or manifest.get('speculation_policy', {}).get('HALOGEN_MTP_GATE_RULE') != rule
            or any(key in manifest['environment'] for key in
                   ('HALOGEN_MTP_GATE_LINE', 'HALOGEN_MTP_DEPTH', 'HALOGEN_MTP_DEPTH_HI'))):
        raise ValueError('Native cost-rule manifest environment differs')
    log_path = attempt / 'engine.log'
    if log_path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Native cost log exceeds the finite cohort budget')
    log_bytes = log_path.read_bytes()
    trace = qualify_trace(log_bytes.decode('utf-8'), report['samples'], rule)
    saved_log = output / 'native-cost-log.txt'
    saved_manifest = output / 'service-manifest.json'
    for path, data in ((saved_log, log_bytes), (saved_manifest, manifest_bytes)):
        with path.open('xb') as stream:
            stream.write(data)
    trace.update(log=runtime.ops.pin(saved_log), manifest=runtime.ops.pin(saved_manifest),
                 manifest_environment=actual)
    runtime.ops.atomic(output / 'mtp-cost-trace.json', trace)
    report['mtp_cost_trace'] = trace


def all_cohorts_complete(results):
    for arm in ('before', 'candidate', 'after'):
        entries = results.get(arm, {})
        if any(name not in entries or entries[name].get('collector', {}).get('completed') is not True
               or len(entries[name].get('samples', [])) != 4
               or entries[name].get('mtp_cost_trace', {}).get('native_rule_activation_observed') is not True
               for name in CASE_NAMES):
            return False
        ids = [sample['native_request_id'] for name in CASE_NAMES for sample in entries[name]['samples']]
        if len(set(ids)) != 8:
            return False
    return True


def check_files(root, pins):
    for relative, expected in pins.items():
        path = finite_path(root, relative)
        if not path.is_file() or digest(path) != expected:
            raise ValueError('Transition source drift ' + str(path))


def copy_exact(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=target.name + '.', suffix='.root-transition.tmp', dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(source.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def apply_overlay(package, bound, plan):
    check_files(package, plan['baseline']['files'])
    check_files(bound / 'candidate', plan['candidate'])
    check_files(bound / 'rollback', plan['rollback_restore'])
    for relative in plan['rollback_remove']:
        if finite_path(package, relative).exists():
            raise ValueError('Candidate addition already exists ' + relative)
    for relative in plan['candidate_delta']:
        copy_exact(finite_path(bound / 'candidate', relative), finite_path(package, relative))
    check_files(package, plan['candidate'])


def restore_overlay(package, bound, plan):
    check_files(bound / 'rollback', plan['rollback_restore'])
    # Validate the entire mixed state before touching any file after a partial apply.
    for relative, baseline in plan['rollback_restore'].items():
        path = finite_path(package, relative)
        allowed = {baseline, plan['candidate'].get(relative)}
        if not path.is_file() or digest(path) not in allowed:
            raise ValueError('Foreign source during rollback ' + relative)
    for relative, expected in plan['rollback_remove'].items():
        path = finite_path(package, relative)
        if path.exists() and digest(path) != expected:
            raise ValueError('Foreign addition during rollback ' + relative)
    for relative in plan['rollback_restore']:
        copy_exact(finite_path(bound / 'rollback', relative), finite_path(package, relative))
    for relative in plan['rollback_remove']:
        path = finite_path(package, relative)
        if path.exists():
            path.unlink()
    check_files(package, plan['baseline']['files'])


def private_profile(baseline, arm, experiment='pld34'):
    if arm not in ('before', 'candidate', 'after'):
        raise ValueError('Unknown arm')
    if experiment not in ('pld34', 'prefill4096', 'pld34log', 'pld34log_reference', 'draft_vocab_q8', 'mtp_gate_cost'):
        raise ValueError('Unknown experiment')
    value = json.loads(json.dumps(baseline))
    value['engine']['kernel_controls']['HALOGEN_PHASE_RAW'] = 1
    if experiment == 'mtp_gate_cost':
        value['engine']['kernel_controls'].update(HALOGEN_DRAFT_VOCAB_Q8=0, HALOGEN_SERVE_TRACE=1,
                                                  HALOGEN_DECODE_PREFETCH=0)
        value['engine']['speculation_policy'].update(HALOGEN_PLD='3,3', HALOGEN_MTP_GATE_P='0.90',
            HALOGEN_MTP_GATE_RULE='cost' if arm == 'candidate' else 'gate')
        return value
    if experiment in ('prefill4096', 'pld34log', 'pld34log_reference', 'draft_vocab_q8'):
        chunk = 4096 if experiment == 'prefill4096' and arm == 'candidate' else 2048
        value['concurrency'] = 1
        value['engine'].update(context=32768, slots=1, kv_pool_positions=32768,
                               prefill_chunk=chunk, max_prefill_tokens=chunk)
        value['backend']['context'] = 32768
        value['backend']['expected'].update(context=32768, slot_ctx=32768,
                                            slots=1, kv_pool_positions=32768)
        value['engine']['speculation_policy'].update(HALOGEN_PLD='3,3', HALOGEN_MTP_GATE_P='0.90')
        if experiment == 'draft_vocab_q8':
            value['engine']['prompt_cache'] = 'Off'
            value['engine']['kernel_controls']['HALOGEN_DRAFT_VOCAB_Q8'] = 1 if arm == 'candidate' else 0
            value['engine']['kernel_controls']['HALOGEN_SERVE_TRACE'] = 1
        if experiment in ('pld34log', 'pld34log_reference'):
            value['engine']['prompt_cache'] = 'Off'
            value['engine']['speculation_policy']['HALOGEN_PLD'] = '3,4' if arm == 'candidate' else '3,3'
    else:
        value['engine']['speculation_policy']['HALOGEN_PLD'] = '3,4' if arm == 'candidate' else '3,3'
    return value


def support():
    sys.path.insert(0, str(ROOT / 'server/.local/halogen-update-20261101/primary01822'))
    import run_cache_followup_finite as previous
    _, runtime = previous.support()
    runtime.OUT = OUT
    previous.OUT = OUT
    runtime.checkpoint = lambda stage, **kw: runtime.ops.atomic(OUT / 'stage.json', dict(utc=utc(), stage=stage, **kw))
    runtime.gpu_receipt = lambda label: previous.gpu_gate(runtime, label, frames=1)
    return previous, runtime


def process_absent(pid):
    # Existing helper distinguishes ERROR_INVALID_PARAMETER from access denial.
    from launch_once import absent
    return absent(pid)


def terminal(runtime, baseline, owned, bindings=None):
    outer = runtime.ops.read(ROOT / 'server/.local/current.json')
    inner = runtime.ops.read(PACKAGE / '.local/current-service.json')
    if outer['run_id'] not in {baseline['outer']['run_id'], *owned}:
        raise RuntimeError('Foreign lifecycle is not adopted')
    if outer['phase'] not in ('stopped', 'failed') or inner['phase'] not in ('stopped', 'failed'):
        raise RuntimeError('Observe existing live transition before mutation')
    bound = baseline if outer['run_id'] == baseline['outer']['run_id'] else (bindings or {}).get(outer['run_id'])
    if bound is not None:
        if inner['run_id'] != bound['inner']['run_id']:
            raise RuntimeError('Captured inner run changed')
        if any(runtime.previous.identity_live(identity) for identity in bound['identities'].values()):
            raise RuntimeError('Captured creation-time owner still lives')
    # A signaled captured HANDLE proves exit even while Windows retains the PID.
    # identity_live checks creation FILETIME and WaitForSingleObject together.
    if bound is None and (not process_absent(outer['pid']) or not process_absent(inner['controller_pid'])):
        raise RuntimeError('Terminal publication still owns live process')
    if runtime.ops.docker('ps', '-q').strip() or (PACKAGE / '.local/runner.lock').exists():
        raise RuntimeError('Live container or runner remains')
    return dict(utc=utc(), outer=outer, inner=inner, published_pids_absent=True if bound is None else None,
                captured_owners_absent=True if bound is not None else None)


def compare_outputs(results):
    comparisons = {}
    shared = set.intersection(*(set(results.get(arm, {})) for arm in ('before', 'candidate', 'after')))
    for name in sorted(shared):
        samples = [sample for arm in ('before', 'candidate', 'after')
                   for sample in results[arm][name]['samples']]
        comparisons[name] = dict(
            matched_output_bytes=len({sample['output_sha256'] for sample in samples}) == 1,
            matched_output_tokens=len({sample['actual_output_tokens'] for sample in samples}) == 1,
            matched_input_tokens=len({sample['actual_input_tokens'] for sample in samples}) == 1)
    return comparisons


def ready_status(restored, profile, proof):
    return dict(ready=True, version='0.19.1', profile=restored['profile'],
                identities=restored['identities'], controller_run_id=restored['outer']['run_id'],
                backend_run_id=restored['inner']['run_id'], fresh_readiness=proof,
                context=restored['native']['context'], slots=restored['native']['slots'],
                kv_pool_positions=restored['native']['kv_pool_positions'],
                prefill_chunk=profile['engine']['prefill_chunk'],
                max_prefill_tokens=profile['engine']['max_prefill_tokens'], verified_utc=restored['utc'])


def all_cases_closed_by_baseline_oracle(frozen, failures):
    closed = {name for name, failure in failures.items()
              if failure.get('arm') == 'before' and failure.get('type') == 'OracleMismatch'}
    return bool(frozen) and all(case['name'] in closed for case in frozen)


def log_reference_case():
    manifest_path = finite_path(PRIMARY, 'pld34log-reference-freeze/manifest.json')
    manifest_bytes = manifest_path.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != LOG_REFERENCE_MANIFEST_SHA:
        raise ValueError('Frozen serial reference manifest drift')
    manifest = json.loads(manifest_bytes)
    paths, contents = {}, {}
    for name in ('request', 'serial_request', 'recorded_serial_response',
                 'canonical_task_expected', 'reference', 'original_failed_campaign'):
        pin = manifest[name]
        relative = str(Path(pin['path']).relative_to(PRIMARY))
        path = finite_path(PRIMARY, relative)
        data = path.read_bytes()
        if len(data) != pin['bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
            raise ValueError('Frozen serial reference source drift ' + name)
        paths[name], contents[name] = path, data
    for name, expected in (('request', LOG_REQUEST_SHA), ('serial_request', LOG_SERIAL_REQUEST_SHA),
                           ('canonical_task_expected', LOG_EXPECTED_SHA), ('reference', LOG_REFERENCE_SHA)):
        if manifest[name]['sha256'] != expected:
            raise ValueError('Original frozen log or serial reference identity differs ' + name)
    if (manifest['frozen_before_candidate_execution'] is not True
            or manifest['canonical_task_passed'] is not False
            or manifest['native_token_sequence_identity_claimed'] is not False
            or manifest['required_prompt_tokens'] != 3539
            or manifest['required_output_tokens'] != 1259):
        raise ValueError('Frozen serial reference study contract differs')
    request, serial = json.loads(contents['request']), json.loads(contents['serial_request'])
    if serial.get('drafter') != 'serial' or {**serial, 'drafter': 'mtp'} != request:
        raise ValueError('Serial reference request must differ only by drafter')
    response = json.loads(contents['recorded_serial_response'])
    choices = response.get('choices', [])
    usage = response.get('usage', {})
    if (len(choices) != 1 or choices[0].get('finish_reason') != 'stop'
            or choices[0].get('message', {}).get('content', '').encode('utf-8') != contents['reference']
            or usage.get('prompt_tokens') != 3539 or usage.get('completion_tokens') != 1259):
        raise ValueError('Recorded serial response differs from exact visible reference')
    if (contents['reference'].endswith(b'\n')
            or contents['reference'] + b'\n' != contents['canonical_task_expected']):
        raise ValueError('Original canonical final-LF failure differs')
    failed = json.loads(contents['original_failed_campaign'])
    if (failed.get('experiment') != 'pld34log' or failed.get('terminal') is not True
            or failed.get('completed') is not False or failed.get('restored') is not True
            or failed.get('all_cases_closed_by_baseline_oracle') is not True
            or not all_cases_closed_by_baseline_oracle([dict(name='real-log-json-quote')],
                                                      failed.get('failed_cases', {}))):
        raise ValueError('Original canonical log campaign must remain closed and failed')
    study = dict(
        manifest=dict(path=str(manifest_path), bytes=len(manifest_bytes), sha256=LOG_REFERENCE_MANIFEST_SHA),
        reference=manifest['reference'], reference_kind=manifest['reference_kind'],
        canonical_task_expected=manifest['canonical_task_expected'], original_canonical_task_passed=False,
        original_canonical_failure=manifest['canonical_failure'], serial_reference_drafter='serial',
        original_failed_campaign=manifest['original_failed_campaign'],
        comparison_scope='Exact API-visible UTF-8 bytes and reported token counts against the frozen serial reference',
        native_token_sequence_identity_claimed=False, NPU_or_CPU_numeric_tolerances_changed=False,
        NPU_benefit_claimed=False, full_goal_achieved=False)
    return dict(name='real-log-json-quote', request=paths['request'], request_sha256=LOG_REQUEST_SHA,
                route='/v1/chat/completions', oracle=paths['reference'],
                oracle_request=paths['serial_request'], oracle_request_sha256=LOG_SERIAL_REQUEST_SHA,
                prompt_tokens=3539, expected_output_tokens=1259, reference_study=study)


def cases(experiment='pld34'):
    if experiment == 'pld34log_reference':
        return [log_reference_case()]
    if experiment not in ('pld34', 'prefill4096', 'pld34log', 'draft_vocab_q8', 'mtp_gate_cost'):
        raise ValueError('Unknown experiment')
    novel8 = PRIMARY / 'natural8192-prep/request-natural8192.json'
    novel16 = ROOT / 'server/.local/halogen-update-20261025/primary01816/measurement-20261026T1903Z/plain-packet/request-natural16k.json'
    natural = [dict(name='natural8192', request=novel8, prompt_tokens=8192,
                    route='/v1/completions', request_sha256='2e26413988ce75fcf745a1a143aa3647297349c1516f9d18968e9d1b4da0632d'),
               dict(name='natural16384', request=novel16, prompt_tokens=16384,
                    route='/v1/completions', request_sha256='0d9cd3c7820d39ebb3c6f8ec4b712b8301e91d2eb2b97c52d9be678699ce6b3d')]
    result = natural
    if experiment in ('draft_vocab_q8', 'mtp_gate_cost'):
        for case in result:
            case['expected_output_tokens'] = 128
    if experiment in ('pld34', 'pld34log'):
        concept = PRIMARY / 'pld-npu-concept'
        manifest = json.loads((concept / 'workload-manifest.json').read_bytes())
        review = json.loads((concept / 'independent-workload-review.json').read_bytes())
        reviewed = {row['case']: row for row in review['cases']}
        result = []
        # Primary lookup-bearing task first, then independent natural and secondary cases.
        names = (('real-log-json-quote',) if experiment == 'pld34log'
                 else ('real-code-numbered-rewrite', 'real-code-plain-rewrite', 'real-log-json-quote'))
        for name in names:
            row = next(row for row in manifest['cases'] if row['name'] == name)
            if experiment == 'pld34log' and (row['request_sha256'] != LOG_REQUEST_SHA
                                            or row['expected_sha256'] != LOG_EXPECTED_SHA):
                raise ValueError('Original frozen log workload identity differs')
            request = concept / 'workload' / row['request']
            oracle = concept / 'workload' / row['expected']
            if digest(request) != row['request_sha256'] or digest(oracle) != row['expected_sha256']:
                raise ValueError('Frozen workload drift ' + name)
            result.append(dict(name=name, request=request, request_sha256=row['request_sha256'],
                               route='/v1/chat/completions', oracle=oracle,
                               oracle_request=concept / 'workload' / row['serial_request'],
                               oracle_request_sha256=digest(concept / 'workload' / row['serial_request']),
                               prompt_tokens=reviewed[name]['offline_rendered_prompt_tokens']))
        if experiment == 'pld34':
            result[1:1] = natural
    for case in result:
        if digest(case['request']) != case['request_sha256']:
            raise ValueError('Frozen request drift ' + case['name'])
    return result


def main():
    global OUT, NORMAL, BOUND
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--experiment', choices=('mtp_gate_cost',), default='mtp_gate_cost')
    parser.add_argument('--attempt')
    args = parser.parse_args()
    OUT = campaign_output(args.experiment, args.attempt)
    NORMAL, BOUND = campaign_paths(args.experiment)
    plan = json.loads((BOUND / 'transition.json').read_bytes())
    dso = json.loads((RAW_PREP / 'observer/root-dso-pin.json').read_bytes())
    check_files(RAW_PREP, dso['source_pins'])
    if digest(Path(dso['path'])) != dso['sha256']:
        raise ValueError('Built observer drift')
    check_files(PACKAGE, plan['baseline']['files'])
    check_files(BOUND / 'candidate', plan['candidate'])
    check_files(BOUND / 'rollback', plan['rollback_restore'])
    frozen = cases(args.experiment)
    source_rows()
    if not args.run:
        prepared = dict(prepared=True, experiment=args.experiment, output=str(OUT),
                        cases=[c['name'] for c in frozen], hardware_started=False,
                        cohort_comparison_requests=24, inherited_startup_smokes_excluded_from_cohort_means=True)
        if args.experiment == 'pld34log_reference':
            prepared['reference_study'] = frozen[0]['reference_study']
        if args.attempt is not None:
            prepared['attempt'] = args.attempt
        print(json.dumps(prepared))
        return
    verify_normal_profile()
    executed = registered_sources()
    if OUT.exists():
        raise RuntimeError('Observe retained real campaign handle before continuation')
    previous, runtime = support()
    previous.allowed(runtime)
    baseline = runtime.verify(NORMAL, 8840, require_idle=True)
    baseline_config = runtime.ops.read(NORMAL)
    baseline_profile_sha = baseline['profile']['sha256']
    if baseline_profile_sha != NORMAL_SHA256:
        raise ValueError('Live normal profile differs from canonical normal profile')
    expected = runtime.ops.read(STATE)['latest_halogen0191_runtime_status']['identities']
    if baseline['identities'] != expected:
        raise RuntimeError('Current runtime identities differ from continuation seal')
    if args.experiment == 'mtp_gate_cost':
        sys.path.insert(0, str(RAW_PREP / 'collector'))
        import collect_epoch
        collect_epoch.m.check_reserve(runtime, 22)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 18840))
    if source_rows() != executed['files']:
        raise ValueError('Registered executed sources changed before output creation')
    verify_normal_profile()
    OUT.mkdir()
    runtime.ops.atomic(OUT / 'executed-source-pins.json', executed)
    record = dict(schema='halogen0191.' + args.experiment + '-raw-campaign.v1',
                  experiment=args.experiment, utc=utc(), terminal=False,
                  completed=False, restored=False, identity=runtime.ops.ident.process_identity(os.getpid()),
                  baseline=baseline, owned_runs=[], owned_bindings={}, failed_cases={}, results={}, hardware_owner='root')
    if args.experiment == 'pld34log_reference':
        record['reference_study'] = frozen[0]['reference_study']
    if args.attempt is not None:
        record['attempt'] = args.attempt

    def save(phase, **details):
        record.update(phase=phase, **details)
        runtime.ops.atomic(OUT / 'handle.json', record)
        state = runtime.ops.read(STATE)
        state['current_work'] = dict(scope='halogen0191_' + args.experiment + '_raw_finite', phase=phase,
            handle=str(OUT / 'handle.json'), identity=record['identity'], hardware_owner='root',
            server_restore_required=not record['restored'], do_not_duplicate_live_handles=True,
            lifecycle_receipt=record.get('lifecycle_receipt'), goal_achieved=False)
        if record['restored']:
            state['latest_halogen0191_runtime_status'] = ready_status(
                record['final'], baseline_config, runtime.ops.pin(OUT / 'ready-left-online.json'))
        runtime.ops.atomic(STATE, state)

    active = baseline

    def launch(profile, label, port):
        receipt = OUT / (label + '-launch.json')
        save(label + '_launching', lifecycle_receipt=str(receipt), launch_result=None, launch_observed=False)
        arguments = argparse.Namespace(profile=profile, receipt=receipt, version='0.19.1',
                                       port=port, visible=(port == 8840), admission_wait=180)
        result = runtime.lifecycle.launch(arguments)
        save(label + '_launch_returned', launch_result=result)
        if result != 0:
            raise RuntimeError('Existing normal startup admission failed')
        ready = runtime.await_ready(profile, port, receipt)
        record['owned_runs'].append(ready['outer']['run_id'])
        record['owned_bindings'][ready['outer']['run_id']] = ready
        save(label + '_ready', active=ready, launch_observed=True)
        return ready

    save('normal_verified')
    overlay_attempted = False
    with runtime.previous.wsl_stdin_lease(OUT):
        try:
            previous.gpu_gate(runtime, 'before-stop', frames=2)
            runtime.stop_owned(active, 'normal-stop')
            active = None
            runtime.ops.atomic(OUT / 'normal-terminal.json', terminal(runtime, baseline, record['owned_runs'], record['owned_bindings']))
            overlay_attempted = True
            apply_overlay(PACKAGE, BOUND, plan)
            save('private_source_applied')
            sys.path.insert(0, str(RAW_PREP / 'collector'))
            import collect_epoch
            for arm_index, arm in enumerate(('before', 'candidate', 'after')):
                if arm_index and all_cases_closed_by_baseline_oracle(frozen, record['failed_cases']):
                    save('all_cases_closed_by_baseline_oracle', all_cases_closed_by_baseline_oracle=True,
                         completed=False, stop_reason='all_cases_closed_by_baseline_oracle')
                    break
                profile = OUT / (arm + '.profile.json')
                if digest(NORMAL) != baseline_profile_sha:
                    raise RuntimeError('Selected normal profile changed during comparison')
                runtime.ops.atomic(profile, private_profile(baseline_config, arm, args.experiment))
                active = launch(profile, arm, 18840)
                raw_dir = Path(active['inner']['attempt']) / 'raw-phase'
                for case_index, case in enumerate(frozen):
                    if case['name'] in record['failed_cases']:
                        continue
                    save('collecting', arm=arm, case=case['name'])
                    output = OUT / arm / case['name']
                    try:
                        report = asyncio.run(collect_epoch.collect_epoch(
                            profile=profile, port=18840, expected=active,
                            request_bytes=case['request'].read_bytes(), request_sha256=case['request_sha256'],
                            route=case['route'], raw_dir=raw_dir,
                            epoch=0x0191000000000001 + case_index, output=output,
                            oracle_bytes=case['oracle'].read_bytes() if 'oracle' in case else None,
                            oracle_request_bytes=case['oracle_request'].read_bytes() if arm_index == 0 and 'oracle_request' in case else None,
                            oracle_request_sha256=case.get('oracle_request_sha256') if arm_index == 0 else None,
                            expected_prompt_tokens=case['prompt_tokens'],
                            expected_output_tokens=case.get('expected_output_tokens'), runtime=runtime))
                        if 'reference_study' in case:
                            report['reference_study'] = case['reference_study']
                        save_cost_trace(runtime, active, profile, output, report, record['results'].get(arm, {}))
                        record['results'].setdefault(arm, {})[case['name']] = report
                    except collect_epoch.OracleMismatch as error:
                        record['failed_cases'][case['name']] = dict(arm=arm, type=type(error).__name__, message=str(error))
                        save('oracle_failed_case_closed')
                        epoch_prefix = f"capture-{0x0191000000000001 + case_index:016x}-"
                        failed = runtime.ops.read(output / 'handle.json')
                        if (failed.get('restart_required') is not False
                                or failed.get('unsupported') is not False
                                or (output / 'arm-created.json').exists()
                                or any(raw_dir.glob(epoch_prefix + '*'))):
                            raise RuntimeError('Armed oracle failed, stop engine and restore without another epoch') from error
                runtime.stop_owned(active, arm + '-stop')
                active = None
                runtime.ops.atomic(OUT / (arm + '-terminal.json'), terminal(runtime, baseline, record['owned_runs'], record['owned_bindings']))
            record['cross_arm_outputs'] = compare_outputs(record['results'])
            record['completed'] = all_cohorts_complete(record['results'])
        except BaseException as error:
            save('error', error=dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc()))
            raise
        finally:
            current = runtime.ops.read(ROOT / 'server/.local/current.json')
            if active is None and record.get('lifecycle_receipt'):
                receipt_path = Path(record['lifecycle_receipt'])
                if receipt_path.exists():
                    receipt = runtime.ops.read(receipt_path)
                    if current['phase'] in ('starting', 'ready'):
                        # Keep observing the exact published launch through timeouts.
                        active = runtime.await_ready(Path(receipt['profile']['path']), receipt['port'], receipt_path)
                        if active['outer']['run_id'] not in record['owned_runs']:
                            record['owned_runs'].append(active['outer']['run_id'])
                        record['owned_bindings'][active['outer']['run_id']] = active
                    else:
                        if runtime.previous.identity_live(receipt['launcher_identity']) and not record.get('launch_observed'):
                            raise RuntimeError('Unpublished live launcher must be observed before restoration')
                        if receipt.get('controller_run'):
                            if current['run_id'] != receipt['controller_run']:
                                raise RuntimeError('Terminal launch receipt differs from current publication')
                            if runtime.previous.identity_live(receipt['controller_identity']):
                                raise RuntimeError('Terminal published launch owner still lives')
                            if current['run_id'] not in record['owned_runs']:
                                record['owned_runs'].append(current['run_id'])
                elif record.get('launch_result') not in (2,):
                    raise RuntimeError('Unresolved launch without receipt, inspect real handles before any new start')
            current = runtime.ops.read(ROOT / 'server/.local/current.json')
            if (not overlay_attempted and active is baseline and current['phase'] == 'ready'
                    and current['run_id'] == baseline['outer']['run_id']):
                restored = runtime.verify(NORMAL, 8840, require_idle=False)
                if restored['identities'] != baseline['identities']:
                    raise RuntimeError('Original runtime changed after preflight rejection')
            else:
                if active is not None:
                    current = runtime.ops.read(ROOT / 'server/.local/current.json')
                    if current['phase'] in ('starting', 'ready'):
                        runtime.stop_owned(active, 'final-private-stop')
                    active = None
                runtime.ops.atomic(OUT / 'rollback-terminal.json', terminal(runtime, baseline, record['owned_runs'], record['owned_bindings']))
                if overlay_attempted:
                    restore_overlay(PACKAGE, BOUND, plan)
                save('normal_source_restored')
                restored = launch(NORMAL, 'restore-normal', 8840)
            # Refresh the persistent consumer using its existing selection contract.
            sys.path.insert(0, str(ROOT / 'voice/native-start'))
            import controller_consumer
            if digest(NORMAL) != baseline_profile_sha or restored['profile']['sha256'] != baseline_profile_sha:
                raise RuntimeError('Restored selected profile differs from initial exact seal')
            selected = dict(profile_path=NORMAL, profile_sha256=restored['profile']['sha256'],
                            profile=runtime.ops.read(NORMAL))
            credential = controller_consumer.token(NORMAL, selected['profile'])
            health = controller_consumer.request('/health', credential)
            models = controller_consumer.request('/v1/models', credential)
            if health['status'] != 'ok' or 'halogen-v2' not in [item['id'] for item in models['data']]:
                raise RuntimeError('Final authenticated controller discovery differs')
            controller_consumer.remember(selected, ROOT / 'server/.local/voice-deployment/controller-selection.local.json')
            runtime.ops.atomic(OUT / 'ready-left-online.json', restored)
            save('complete_normal_online', restored=True, final=restored, terminal=True, ended_utc=utc())
    print(json.dumps(dict(completed=record['completed'], restored=record['restored'],
                          failed_cases=record['failed_cases'], identities=record['final']['identities'])), flush=True)


if __name__ == '__main__':
    main()
