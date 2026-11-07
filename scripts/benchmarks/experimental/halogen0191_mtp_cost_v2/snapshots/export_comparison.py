"""Offline sanitized comparison export. Public files require explicit --write."""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import statistics
import sys

COST_HERE = Path(__file__).resolve().parent
HERE = COST_HERE.parent / 'raw-phase-prep'
ROOT = HERE.parents[4]
PUBLIC_DIR = ROOT / 'docs/benchmarks'
PUBLIC_REFERENCE = PUBLIC_DIR / 'halogen0191-natural-8k16k-20261107.json'
PUBLIC_REFERENCE_SHA = '50dd53a9b083b536837f743034fb9face3e968cd6ff293bc92d988f86f9639c6'
ARMS = ('before', 'candidate', 'after')
CASES = dict(pld34=('real-code-numbered-rewrite', 'natural8192', 'natural16384',
                   'real-code-plain-rewrite', 'real-log-json-quote'),
             prefill4096=('natural8192', 'natural16384'),
             pld34log=('real-log-json-quote',),
             pld34log_reference=('real-log-json-quote',),
             draft_vocab_q8=('natural8192', 'natural16384'),
             mtp_gate_cost=('natural8192', 'natural16384'))
COST_PROFILE = HERE.parent / 'serving0191-text32k-one-slot-2048.json'
COST_PROFILE_SHA = '69b91ddae6daa21b7c4d7666077847e4913fd9b59aedd149201c9d0ccd994b84'
COST_ROOT_SHA = 'f6ffa51f7fd9c310a3abe75fee151a209189aa22bcef6a467876ff2ef11e84a1'
COST_TRACE_SHA = 'b88df08b942b14b00a3a51b6f3876b1263948991d4494664913949997237ea1e'
COST_TRANSITION_SHA = 'a2de768efb642b5a375cdf60d81de4d5a4395a215f46662160f2327370d1f880'
COST_MODULES = {
    'root_campaign.py': (COST_ROOT_SHA, COST_HERE / 'root_campaign.py'),
    'mtp_cost_trace.py': (COST_TRACE_SHA, COST_HERE / 'mtp_cost_trace.py'),
}
Q8_ROOT_SHA = 'ece8bcf39b35369bf28fb1d04137c510d4e0643d11dfba3625f5b589fa1300f3'
Q8_TRACE_SHA = 'e4913dc3275d661aee578dea3a165534419794b648442db4eb948db6ca5da4ae'
Q8_TRANSITION_SHA = 'ecae649e6e437f71ddfd53a891aea4344629f361c712f5e67773df561a93c32b'
RAW_TRANSITION_SHA = '9716172db462f965d4d18decb5b107a616a56115815e08e517b26a235a31e2ca'
TRANSITIONS = {
    RAW_TRANSITION_SHA: HERE / 'integration/root-bound/transition.json',
    Q8_TRANSITION_SHA: HERE.parent / 'next-mechanisms-1722/q8-candidate/transition.json',
    COST_TRANSITION_SHA: COST_HERE / 'integration/root-bound/transition.json',
}
Q8_REQUESTS = {
    'natural8192': (8192, '2e26413988ce75fcf745a1a143aa3647297349c1516f9d18968e9d1b4da0632d'),
    'natural16384': (16384, '0d9cd3c7820d39ebb3c6f8ec4b712b8301e91d2eb2b97c52d9be678699ce6b3d'),
}
LOG_EXPERIMENTS = ('pld34log', 'pld34log_reference')
REFERENCE_DIR = HERE.parent / 'pld34log-reference-freeze'
REFERENCE_MANIFEST_SHA = 'c920c79bd7950d9daa462fba9864daf55306c1129656af281e612a40f3f1347c'
REFERENCE_PLAN_PINS = {
    'markdown': ('halogen0191-log-serial-reference-plan-20261107.md',
                 '2178ba3f2b810c742dffd44af3c0300f63f922817a76a226e5e48d3a9994c260'),
    'json': ('halogen0191-log-serial-reference-plan-20261107.json',
             'b6fdfb35aa2dc80cc4fa8a49de94c37f308f31cd072881459cb6b5592e7a3b9f'),
}
SOURCE_NAMES = {'root_campaign.py', 'collect_epoch.py', 'qpc_audit.py',
                'transition.json', 'root-dso-pin.json'}
ROOT_CAMPAIGN_VERSIONS = {
    'c060b40c183be03355a9b5de1b5874b448bc4fbb19b78583d61c402e70308226':
        (1, HERE / 'root_campaign.v1.py'),
    'a52d8dda1ea6cf1fe65592b2a507abaced4babbc77b630e5379f028fbd2c0c98':
        (2, HERE / 'root_campaign.v2.py'),
    '3fc8c98cbde1daa75c0d4660cd0c6313a61c1bb16db2aa3a30c0ac28add69e82':
        (3, HERE / 'root_campaign.v3.py'),
    '9b97b91e2e71e2737a23f14948aded503598bd0d2004ebc58182e66f21712ac6':
        (4, HERE / 'root_campaign.v4.py'),
    '24d6db8fda1e6c57bc52127bc073d0128db0b8d2a0a617ef05509dbc368bc19a':
        (5, HERE / 'root_campaign.v5.py'),
    Q8_ROOT_SHA: (6, HERE / 'root_campaign.py'),
}
COLLECTOR_VERSIONS = {
    'a009965bbec1ce23034e43b3f73e75e57cad388b1c63f19a79f60f1258f18ea4':
        (1, HERE / 'collector/collect_epoch.v1.py'),
    '3a91d4d8e03e5ccfd889033edef2cac976c243f7740a5aaf7ff200fc5a736010':
        (2, HERE / 'collector/collect_epoch.v2.py'),
    '098f8b88d10e2b1dece7f602765da568ac2b9fec06591c4792c3e1da183f6896':
        (3, HERE / 'collector/collect_epoch.py'),
}
sys.path.insert(0, str(HERE / 'observer'))
sys.path.insert(0, str(HERE / 'collector'))
from validate_cohort import validate_cohort
from qpc_audit import audit_qpc


def need(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None,
         'Invalid SHA256 evidence')
    return value


def number(value):
    need(type(value) in (int, float) and math.isfinite(value) and value >= 0,
         'Invalid numeric observation')
    return value


def error_type(value):
    value = value.get('error', {}).get('type', value.get('type', ''))
    return value if type(value) is str and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,63}', value) else None


def terminal_handle(path):
    value = read(path)
    for key in ('terminal', 'completed', 'restored'):
        need(type(value.get(key)) is bool, 'Campaign requires explicit ' + key + ' state')
    need(value['terminal'] is True and value['restored'] is True,
         'Only terminal restored campaigns can be exported')
    experiment = value.get('experiment')
    need(experiment in CASES and value.get('schema') == 'halogen0191.' + experiment + '-raw-campaign.v1',
         'Unknown campaign schema or experiment')
    need(set(value.get('results', {})).issubset(ARMS), 'Unknown campaign arm')
    return value


def public_identity(path):
    need(sha(path) == PUBLIC_REFERENCE_SHA, 'Immutable public 0.19.1 reference changed')
    value = read(path)
    need(value['version'] == '0.19.1', 'Wrong public source version')
    pins = {key: digest(item) for key, item in value['artifact_sha256'].items()}
    return {key: value[key] for key in ('version', 'image', 'upstream_public_commit',
                                      'image_engine_revision')} | dict(
        artifact_sha256=pins, public_reference_file=PUBLIC_REFERENCE.name,
        public_reference_sha256=PUBLIC_REFERENCE_SHA)


def executed_sources(folder, required, experiment=None):
    path = folder / 'executed-source-pins.json'
    if not path.is_file():
        need(not required, 'Successful campaign requires executed source pins')
        return {}
    rows = read(path)['files']
    result = {}
    q8 = experiment == 'draft_vocab_q8'
    cost = experiment == 'mtp_gate_cost'
    roles = SOURCE_NAMES | ({'mtp_cost_trace.py'} if cost else {'vocab_trace.py'} if q8 else set())
    local = dict(zip(('root_campaign.py', 'collect_epoch.py', 'qpc_audit.py',
                      'transition.json', 'root-dso-pin.json'),
                     (HERE / 'root_campaign.py', HERE / 'collector/collect_epoch.py',
                      HERE / 'collector/qpc_audit.py', HERE / 'integration/root-bound/transition.json',
                      HERE / 'observer/root-dso-pin.json')))
    if q8:
        local['vocab_trace.py'] = HERE / 'vocab_trace.py'
    if cost:
        local.update({name: path for name, (_, path) in COST_MODULES.items()})
        local['transition.json'] = TRANSITIONS[COST_TRANSITION_SHA]
    for name, pin in rows.items():
        logical = PureWindowsPath(name).name
        need(logical in roles and logical not in result, 'Unexpected executed source role')
        need(type(pin.get('bytes')) is int and pin['bytes'] >= 0, 'Invalid executed source size')
        result[logical] = dict(sha256=digest(pin['sha256']), bytes=pin['bytes'])
        if logical == 'root_campaign.py':
            versions = {COST_ROOT_SHA: (8, COST_HERE / 'root_campaign.py')} if cost else ROOT_CAMPAIGN_VERSIONS
            need(pin['sha256'] in versions, 'Unknown executed root campaign version')
            version, root_source = versions[pin['sha256']]
            local[logical] = root_source
            result[logical].update(implementation_version=version, selected_source_file=root_source.name)
        if logical == 'collect_epoch.py':
            need(pin['sha256'] in COLLECTOR_VERSIONS, 'Unknown executed collector version')
            version, collector_path = COLLECTOR_VERSIONS[pin['sha256']]
            local[logical] = collector_path
            result[logical]['implementation_version'] = version
        if logical == 'transition.json':
            need(pin['sha256'] in TRANSITIONS, 'Unknown executed transition source')
            local[logical] = TRANSITIONS[pin['sha256']]
            expected_transition = COST_TRANSITION_SHA if cost else Q8_TRANSITION_SHA if q8 else RAW_TRANSITION_SHA
            need(pin['sha256'] == expected_transition,
                 'Executed transition differs from the experiment')
        if logical == 'vocab_trace.py':
            need(pin['sha256'] == Q8_TRACE_SHA, 'Unknown executed vocabulary trace source')
        if logical == 'mtp_cost_trace.py':
            need(pin['sha256'] == COST_TRACE_SHA, 'Unknown executed MTP cost trace source')
        need(sha(local[logical]) == pin['sha256'] and local[logical].stat().st_size == pin['bytes'],
             'Executed source identity differs from source used for recomputation')
    need(not required or set(result) == roles, 'Incomplete executed source pins')
    if q8 and required:
        need(result['root_campaign.py']['sha256'] == Q8_ROOT_SHA
             and result['collect_epoch.py']['implementation_version'] == 3,
             'Q8 requires its frozen Root and collector source pins')
    if cost and required:
        need(result['root_campaign.py']['sha256'] == COST_ROOT_SHA
             and result['collect_epoch.py']['implementation_version'] == 3,
             'Cost requires its frozen Root and collector source pins')
    return result


def accounting_for_sources(sources):
    if not sources:
        return None
    identity = sources['collect_epoch.py']['sha256']
    version, path = COLLECTOR_VERSIONS[identity]
    need(sha(path) == identity, 'Matched collector implementation changed')
    spec = importlib.util.spec_from_file_location('halogen0191_export_accounting_v' + str(version), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.account_response


def trace_qualifier_for_sources(sources):
    pin = sources.get('vocab_trace.py', {})
    path = HERE / 'vocab_trace.py'
    need(pin.get('sha256') == Q8_TRACE_SHA and sha(path) == Q8_TRACE_SHA
         and path.stat().st_size == pin.get('bytes'), 'Q8 vocabulary trace source pins differ')
    spec = importlib.util.spec_from_file_location('halogen0191_export_vocab_trace', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.qualify_trace


def cost_module(logical, sources):
    expected, path = COST_MODULES[logical]
    pin = sources.get(logical, {})
    need(pin.get('sha256') == expected == sha(path)
         and pin.get('bytes') == path.stat().st_size, 'Cost source identity differs')
    spec = importlib.util.spec_from_file_location('halogen0191_export_cost_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cost_registration(folder, sources):
    saved = read(folder / 'executed-source-pins.json')
    need(saved.get('schema') == 'halogen0191.mtp-gate-cost-executed-sources.v1'
         and type(saved.get('registration')) is dict,
         'Cost executed source registration schema differs')
    module = cost_module('root_campaign.py', sources)
    recomputed = module.registered_sources(saved.get('registration'), repository=ROOT)
    expected = {PureWindowsPath(name).name: pin for name, pin in recomputed['files'].items()}
    actual = {name: {key: pin[key] for key in ('sha256', 'bytes')} for name, pin in sources.items()}
    need(recomputed['registration'] == saved.get('registration') and expected == actual,
         'Cost registered source pins differ')
    return recomputed['registration']


def reference_public_documents():
    plan = {}
    pilot = {}
    for role, (filename, expected_sha) in REFERENCE_PLAN_PINS.items():
        path = PUBLIC_DIR / filename
        need(sha(path) == expected_sha, 'Premeasurement public reference plan changed')
        plan[role] = dict(file=filename, sha256=expected_sha)
        suffix = '.md' if role == 'markdown' else '.json'
        pilot_file = 'halogen0191-pld34log-raw-20261107' + suffix
        pilot_path = PUBLIC_DIR / pilot_file
        available = pilot_path.is_file()
        pilot[role] = dict(file=pilot_file, available=available,
                           sha256=sha(pilot_path) if available else None)
    plan['premeasurement_anchor_commit'] = '076babf'
    return dict(public_plan=plan, original_failed_pilot_report=pilot)


def reference_study():
    manifest_path = REFERENCE_DIR / 'manifest.json'
    need(sha(manifest_path) == REFERENCE_MANIFEST_SHA, 'Frozen serial reference manifest changed')
    manifest = read(manifest_path)
    need(manifest.get('schema') == 'halogen0191.log-serial-reference-freeze.v1'
         and manifest.get('frozen_before_candidate_execution') is True
         and manifest.get('canonical_task_passed') is False
         and manifest.get('required_prompt_tokens') == 3539
         and manifest.get('required_output_tokens') == 1259
         and manifest.get('output_cap') == 8192
         and manifest.get('required_finish_reason') == 'stop'
         and manifest.get('native_token_sequence_identity_claimed') is False,
         'Frozen serial reference contract differs')
    original = HERE.parent / 'pld34log-raw-comparison'
    original_case = original / 'before/real-log-json-quote'
    paths = dict(request=HERE.parent / 'pld-npu-concept/workload/real-log-json-quote.request.json',
        serial_request=original_case / 'serial-request.json',
        recorded_serial_response=original_case / 'serial.response.json',
        canonical_task_expected=original_case / 'expected-output.utf8',
        reference=REFERENCE_DIR / 'serial-visible-output.utf8',
        original_failed_campaign=original / 'handle.json')
    for role, path in paths.items():
        pin = manifest[role]
        need(sha(path) == digest(pin['sha256']) and path.stat().st_size == pin['bytes'],
             'Frozen serial reference evidence differs')
    reference = paths['reference'].read_bytes()
    canonical = paths['canonical_task_expected'].read_bytes()
    need(len(reference) == 4933 and len(canonical) == 4934 and canonical == reference + b'\n',
         'Recorded canonical final-LF failure differs')
    request = read(paths['request'])
    serial_request = read(paths['serial_request'])
    need(serial_request.get('drafter') == 'serial' and {**serial_request, 'drafter': 'mtp'} == request,
         'Frozen serial request differs beyond its drafter')
    serial_response = read(paths['recorded_serial_response'])
    choice, = serial_response['choices']
    text = choice.get('text', choice.get('message', {}).get('content'))
    need(type(text) is str and text.encode('utf-8') == reference and choice['finish_reason'] == 'stop'
         and serial_response['usage']['prompt_tokens'] == 3539
         and serial_response['usage']['completion_tokens'] == 1259,
         'Recorded API-visible serial reference differs')
    failed = terminal_handle(paths['original_failed_campaign'])
    need(failed['completed'] is False, 'Original canonical failed study changed')
    return dict(reference_kind='APIvisible_recorded_serial', performance_only=True,
        original_canonical_task_passed=False, original_canonical_failure='Exactly one final LF missing',
        native_token_sequence_identity_claimed=False,
        reference_provenance=dict(manifest_sha256=REFERENCE_MANIFEST_SHA,
            request_sha256=manifest['request']['sha256'],
            serial_request_sha256=manifest['serial_request']['sha256'],
            recorded_serial_response_sha256=manifest['recorded_serial_response']['sha256'],
            original_failed_campaign_sha256=manifest['original_failed_campaign']['sha256'],
            reference_output_sha256=manifest['reference']['sha256'], reference_output_bytes=4933,
            canonical_expected_sha256=manifest['canonical_task_expected']['sha256'],
            canonical_expected_bytes=4934, required_prompt_tokens=3539,
            required_output_tokens=1259, output_cap=8192), **reference_public_documents())


def verify_reference_declaration(value, reference):
    provenance = reference['reference_provenance']
    need(type(value) is dict and value.get('original_canonical_task_passed') is False
         and value.get('original_canonical_failure') == 'Exactly one final LF missing'
         and value.get('reference_kind') == 'API-visible UTF-8 bytes of recorded serial response'
         and value.get('serial_reference_drafter') == 'serial'
         and value.get('native_token_sequence_identity_claimed') is False
         and value.get('NPU_or_CPU_numeric_tolerances_changed') is False
         and value.get('NPU_benefit_claimed') is False and value.get('full_goal_achieved') is False,
         'Reference study declaration differs from the frozen performance-only scope')
    for role, sha_key, size in (
            ('manifest', 'manifest_sha256', 3064),
            ('reference', 'reference_output_sha256', 4933),
            ('canonical_task_expected', 'canonical_expected_sha256', 4934),
            ('original_failed_campaign', 'original_failed_campaign_sha256', 76427)):
        pin = value.get(role)
        need(type(pin) is dict and pin.get('sha256') == provenance[sha_key]
             and type(pin.get('bytes')) is int and pin['bytes'] == size,
             'Reference study declaration evidence differs')


def cost_profile_value(rule):
    need(type(rule) is str and rule in ('gate', 'cost'), 'Invalid native MTP gate rule')
    need(sha(COST_PROFILE) == COST_PROFILE_SHA, 'Selected cost baseline profile differs')
    value = read(COST_PROFILE)
    value['engine']['kernel_controls'].update(
        HALOGEN_PHASE_RAW=1, HALOGEN_SERVE_TRACE=1, HALOGEN_DRAFT_VOCAB_Q8=0)
    value['engine']['speculation_policy']['HALOGEN_MTP_GATE_RULE'] = rule
    return value


def safe_profile(path, expected_sha, experiment=None):
    need(sha(path) == digest(expected_sha), 'Measured profile SHA256 differs')
    value = read(path)
    engine = value['engine']
    slots = engine['slots']
    need(type(slots) is int and slots in (1, 2) and value['concurrency'] == slots,
         'Measured profile capacity differs')
    need(engine['prompt_cache'] == 'Off' and engine['disable_vision'] is True
         and engine['kernel_controls'].get('HALOGEN_PHASE_RAW') == 1
         and engine['speculation_policy']['HALOGEN_PLD'] in ('3,3', '3,4')
         and engine['speculation_policy']['HALOGEN_MTP_GATE_P'] == '0.90',
         'Measured profile observation or speculation policy differs')
    result = dict(sha256=expected_sha, concurrency=slots,
        context=number(engine['context']), slots=slots,
        kv_pool_positions=number(engine['kv_pool_positions']),
        prefill_chunk=number(engine['prefill_chunk']),
        max_prefill_tokens=number(engine['max_prefill_tokens']),
        prompt_cache='Off', disable_vision=engine['disable_vision'] is True,
        pld=engine['speculation_policy']['HALOGEN_PLD'],
        mtp_gate=engine['speculation_policy']['HALOGEN_MTP_GATE_P'],
        raw_observer_enabled=engine['kernel_controls'].get('HALOGEN_PHASE_RAW') == 1)
    if experiment == 'draft_vocab_q8':
        controls = engine['kernel_controls']
        need(all(type(controls.get(key)) is int and controls[key] in (0, 1)
                 for key in ('HALOGEN_DRAFT_VOCAB_Q8', 'HALOGEN_SERVE_TRACE'))
             and type(value['concurrency']) is int
             and type(controls.get('HALOGEN_PHASE_RAW')) is int
             and 'HALOGEN_DRAFT_VOCAB_Q8' not in engine['speculation_policy'],
             'Q8 profile requires exact integer native controls')
        result.update(draft_vocab_q8=controls['HALOGEN_DRAFT_VOCAB_Q8'],
                      serve_trace=controls['HALOGEN_SERVE_TRACE'])
    if experiment == 'mtp_gate_cost':
        rule = engine['speculation_policy'].get('HALOGEN_MTP_GATE_RULE')
        expected = cost_profile_value(rule)
        need(json.dumps(value, sort_keys=True) == json.dumps(expected, sort_keys=True),
             'Cost profile differs from the exact selected profile projection')
        result.update(mtp_gate_rule=rule, draft_vocab_q8=0, serve_trace=1, decode_prefetch=0)
    return result


def arm_profile(profile, arm, experiment):
    slots = 1 if experiment in ('prefill4096', 'draft_vocab_q8', 'mtp_gate_cost') or experiment in LOG_EXPERIMENTS else 2
    chunk = 4096 if experiment == 'prefill4096' and arm == 'candidate' else 2048
    pld = '3,4' if experiment in ('pld34', *LOG_EXPERIMENTS) and arm == 'candidate' else '3,3'
    need(profile['context'] == 32768 and profile['slots'] == slots
         and profile['kv_pool_positions'] == slots * 32768
         and profile['prefill_chunk'] == profile['max_prefill_tokens'] == chunk
         and profile['pld'] == pld, 'Profile differs from the declared experiment arm')
    if experiment == 'draft_vocab_q8':
        need(type(profile.get('draft_vocab_q8')) is int
             and profile['draft_vocab_q8'] == int(arm == 'candidate')
             and type(profile.get('serve_trace')) is int and profile['serve_trace'] == 1,
             'Q8 profile differs from the declared experiment arm')
    if experiment == 'mtp_gate_cost':
        need(profile.get('mtp_gate_rule') == ('cost' if arm == 'candidate' else 'gate'),
             'Cost profile rule differs from the declared experiment arm')
    return profile


def private_observation_pins(sources):
    if not sources:
        return None
    pin = read(HERE / 'observer/root-dso-pin.json')
    binary = Path(pin['path'])
    need(sha(binary) == digest(pin['sha256']) and binary.stat().st_size == pin['bytes'],
         'Measured observer binary identity differs')
    binding = read(HERE / 'binding.json')
    identity = sources['transition.json']['sha256']
    need(identity in TRANSITIONS and sha(TRANSITIONS[identity]) == identity,
         'Selected transition identity differs')
    transition = read(TRANSITIONS[identity])
    need(transition['dso_input']['sha256'] == pin['sha256']
         and transition['dso_input']['bytes'] == pin['bytes']
         and all(transition['candidate']['scripts/' + name] ==
                 transition['api_fragment']['mounts']['/candidate/' + name]['sha256']
                 for name in ('api_observation.py', 'auth_api.py')),
         'Selected transition API or observer binding differs')
    return dict(observer_sha256=pin['sha256'], observer_bytes=pin['bytes'],
        binding_sha256=digest(pin['source_pins']['observer/binding.json']),
        provider_sha256=digest(binding['provider']['sha256']),
        private_api_adapter_sha256=digest(transition['candidate']['scripts/api_observation.py']),
        private_auth_wrapper_sha256=digest(transition['candidate']['scripts/auth_api.py']),
        common_api_native_identity_observation=True)


def draft_vocab_trace(folder, result, samples, profile, qualifier):
    path = folder / 'draft-vocab-trace.json'
    log = folder / 'native-vocab-log.txt'
    need(path.is_file() and log.is_file(), 'Q8 requires saved vocabulary trace and log evidence')
    trace = read(path)
    need(trace == result.get('draft_vocab_trace'), 'Embedded vocabulary trace differs')
    pin = trace.get('log', {})
    need(type(pin.get('bytes')) is int and 0 <= pin['bytes'] <= 64 * 1024 * 1024
         and log.stat().st_size == pin['bytes'] and sha(log) == digest(pin.get('sha256')),
         'Native vocabulary log identity differs')
    recomputed = qualifier(log.read_bytes().decode('utf-8'), samples)
    need(all(trace.get(key) == value for key, value in recomputed.items())
         and type(trace.get('declared_precision_bits')) is int
         and trace['declared_precision_bits'] == (8 if profile['draft_vocab_q8'] else 4)
         and trace.get('direct_dispatch_dtype_observed') is False
         and trace.get('precision_evidence') == 'Manifest plus pinned native loader and consumer branch',
         'Saved vocabulary trace qualification differs')
    return dict(**recomputed, declared_precision_bits=trace['declared_precision_bits'],
        precision_evidence=trace['precision_evidence'],
        log_sha256=pin['sha256'], log_bytes=pin['bytes'],
        trace_sha256=sha(path), qualifier_sha256=Q8_TRACE_SHA)


def mtp_cost_trace(folder, result, samples, profile, qualifier):
    path = folder / 'mtp-cost-trace.json'
    need(path.is_file(), 'Cost requires saved native trace evidence')
    trace = read(path)
    need(trace == result.get('mtp_cost_trace'), 'Embedded cost trace differs')
    files = {'log': folder / 'native-cost-log.txt',
             'manifest': folder / 'service-manifest.json'}
    for role, artifact in files.items():
        pin = trace.get(role, {})
        need(artifact.is_file() and type(pin.get('bytes')) is int
             and 0 <= pin['bytes'] <= 64 * 1024 * 1024
             and artifact.stat().st_size == pin['bytes']
             and sha(artifact) == digest(pin.get('sha256')), 'Native cost ' + role + ' identity differs')
    rule = profile['mtp_gate_rule']
    expected_environment = dict(HALOGEN_MTP_GATE_RULE=rule, HALOGEN_MTP_GATE_P='0.90',
        HALOGEN_DRAFT_VOCAB_Q8='0', HALOGEN_SERVE_TRACE='1', HALOGEN_DECODE_PREFETCH='0',
        HALOGEN_PLD='3,3', HGN0191_RAW_ENABLE='1')
    manifest = read(files['manifest'])
    environment = manifest.get('environment', {})
    capacity = {key: manifest.get(key) for key in ('checkpoint', 'context', 'slots', 'kv_pool_positions')}
    expected_capacity = dict(checkpoint='v2', context=32768, slots=1, kv_pool_positions=32768)
    need(type(environment) is dict and all(environment.get(key) == value
         for key, value in expected_environment.items())
         and not any(key in environment for key in
             ('HALOGEN_MTP_GATE_LINE', 'HALOGEN_MTP_DEPTH', 'HALOGEN_MTP_DEPTH_HI'))
         and manifest.get('speculation_policy') == cost_profile_value(rule)['engine']['speculation_policy']
         and json.dumps(capacity, sort_keys=True) == json.dumps(expected_capacity, sort_keys=True)
         and trace.get('manifest_environment') == expected_environment,
         'Native cost manifest controls differ from the measured profile')
    recomputed = qualifier(files['log'].read_bytes().decode('utf-8'), samples, rule)
    declared = {key: trace.get(key) for key in recomputed}
    need(json.dumps(declared, sort_keys=True) == json.dumps(recomputed, sort_keys=True),
         'Saved cost trace qualification differs')
    return dict(**recomputed, manifest_environment=expected_environment,
        log_sha256=trace['log']['sha256'], log_bytes=trace['log']['bytes'],
        manifest_sha256=trace['manifest']['sha256'], manifest_bytes=trace['manifest']['bytes'],
        trace_sha256=sha(path), qualifier_sha256=COST_TRACE_SHA)


def sample_public(sample, raw):
    scoped = {}
    for name in ('head', 'lookup', 'grammar'):
        scoped[name] = {key: number(sample['scoped'][name][key])
                        for key in ('rounds', 'drafted', 'accepted')}
    timing_keys = ('prompt_n', 'predicted_n', 'prompt_ms', 'predicted_ms',
                   'prompt_per_second', 'predicted_per_second', 'cache_n')
    durations = {name + '_' + suffix: number(raw[name + '_' + suffix])
                 for name in ('prefill', 'decode')
                 for suffix in ('native_ns', 'raw_lower_ns', 'raw_upper_ns',
                                'native_tps', 'raw_tps_lower', 'raw_tps_upper', 'raw_tps_mid')}
    return dict(ordinal=sample['ordinal'], phase=sample['phase'],
        native_request_id=raw['request_id'], native_slot=raw['native_slot'],
        actual_input_tokens=sample['actual_input_tokens'],
        actual_output_tokens=sample['actual_output_tokens'],
        processed_prompt_tokens=raw['processed_prompt'], output_cap=raw['output_cap'],
        generated_begin=raw['generated_begin'], generated_delta=raw['generated_delta'],
        decode_numerator=raw['decode_numerator'], finish_reason=sample['finish_reason'],
        output_sha256=digest(sample['output_sha256']),
        response_sha256=digest(raw['response_sha256']), journal_sha256=digest(raw['journal_sha256']),
        http_qpc_seconds=number(sample['http_qpc_seconds']), scoped=scoped,
        api_reported_timings={key: number(sample['timings'].get(key, 0)) for key in timing_keys},
        api_phase_clock_qualified=False, **durations)


def summarize(samples):
    measured = samples[1:]
    raw = {name: {metric: statistics.mean(row[name + '_raw_tps_' + metric] for row in measured)
                  for metric in ('lower', 'mid', 'upper')} for name in ('prefill', 'decode')}
    native = {name + '_mean_tps': statistics.mean(row[name + '_native_tps'] for row in measured)
              for name in ('prefill', 'decode')}
    api = {name + '_mean_tps': statistics.mean(row['api_reported_timings'][key] for row in measured)
           for name, key in (('prefill', 'prompt_per_second'), ('decode', 'predicted_per_second'))}
    scopes = {}
    for name in ('head', 'lookup', 'grammar'):
        values = {key: sum(row['scoped'][name][key] for row in measured)
                  for key in ('rounds', 'drafted', 'accepted')}
        values['acceptance_fraction'] = values['accepted'] / values['drafted'] if values['drafted'] else None
        scopes[name] = values
    return dict(excluded_warmups=1, measured_repetitions=3, mean_raw_tps=raw,
        native_clock_observations=native, api_reported_observations=api,
        actual_input_tokens=[row['actual_input_tokens'] for row in measured],
        actual_output_tokens=[row['actual_output_tokens'] for row in measured],
        output_caps=[row['output_cap'] for row in measured],
        mean_http_qpc_seconds=statistics.mean(row['http_qpc_seconds'] for row in measured),
        pooled_scoped_counters=scopes, api_phase_clock_qualified=False)


def complete_cohort(folder, result, source, accounting, reference=None, q8_case=None, cost_case=None):
    natural_case = q8_case or cost_case
    if reference is not None:
        verify_reference_declaration(result.get('reference_study'), reference)
    handle = read(folder / 'handle.json')
    need(handle == result['collector'], 'Embedded collector differs from terminal artifact')
    if reference is not None:
        need(type(handle.get('expected_output_tokens')) is int and handle['expected_output_tokens'] == 1259,
             'Reference study collector expected output count differs')
    if natural_case is not None:
        need(type(handle.get('expected_output_tokens')) is int and handle['expected_output_tokens'] == 128,
             'Natural collector requires expected output count 128')
    need(handle.get('terminal') is True and handle.get('completed') is True
         and handle.get('completed_requests') == 4 and handle.get('RAW_validated') is True
         and handle.get('QPC_audit_passed') is True and handle.get('restart_required') is False
         and handle.get('unsupported') is False, 'Collector cohort is incomplete or failed')
    samples = [read(folder / f'sample-{ordinal}.json') for ordinal in range(4)]
    need(samples == result['samples'], 'Embedded samples differ from persisted samples')
    request_sha = sha(folder / 'request.json')
    need(request_sha == handle['request_sha256'], 'Frozen request evidence differs')
    epoch = int(handle['epoch_nonce'], 16)
    responses = [folder / f'response-{ordinal}.json' for ordinal in range(4)]
    oracle_path = folder / 'expected-output.utf8'
    oracle = oracle_path.read_bytes() if oracle_path.is_file() else None
    request = read(folder / 'request.json')
    accounting_options = dict(oracle_bytes=oracle)
    if reference is not None:
        provenance = reference['reference_provenance']
        need(request_sha == provenance['request_sha256'], 'Reference study request bytes changed')
        need(oracle is not None and oracle == (REFERENCE_DIR / 'serial-visible-output.utf8').read_bytes(),
             'Reference study requires the exact frozen API-visible serial output')
        accounting_options['expected_output_tokens'] = provenance['required_output_tokens']
    if natural_case is not None:
        need(request_sha == Q8_REQUESTS[natural_case][1], 'Frozen natural request identity differs')
        accounting_options['expected_output_tokens'] = 128
    for sample, response in zip(samples, responses):
        accounted = accounting(response.read_bytes(), request, **accounting_options)
        need(all(sample.get(key) == item for key, item in accounted.items()),
             'Saved accounting differs from exact response bytes')
        if reference is not None:
            need(accounted['actual_input_tokens'] == 3539 and accounted['actual_output_tokens'] == 1259
                 and accounted['output_cap'] == 8192, 'Reference study actual counts differ')
        if natural_case is not None:
            need(accounted['actual_input_tokens'] == Q8_REQUESTS[natural_case][0]
                 and accounted['actual_output_tokens'] == accounted['output_cap'] == 128,
                 'Natural actual input or 128 output/cap counts differ')
    original = read(folder / 'raw-report.json')
    ready = read(folder / 'ready-before.json')
    arm_file = Path(ready['inner']['attempt']) / 'raw-phase/arm'
    recomputed = validate_cohort(folder / 'journals/capture', responses, folder / 'request.json',
                                epoch, arm_file, require_cold=True)
    need(original == recomputed == result['raw_report'], 'RAW cohort evidence differs')
    need(recomputed['engine_sha256'] == source['artifact_sha256']['engine_sha256'],
         'RAW engine identity differs from public source')
    audit = audit_qpc(recomputed, samples, request_sha)
    need(audit == read(folder / 'qpc-audit.json') == result['qpc_audit'] and audit['valid'] is True,
         'QPC audit evidence differs or fails')
    if cost_case is not None:
        need(audit.get('serial_qpc_boundaries_verified') is True,
             'Cost requires exact serial whole-HTTP QPC boundaries')
    rows = [sample_public(sample, raw) for sample, raw in zip(samples, recomputed['samples'])]
    need(len({row['output_sha256'] for row in rows}) == 1, 'Within-cohort greedy output differs')
    cohort = dict(status='complete', complete_cohort=True, phase_measurement_qualified=True,
        included_in_comparison=False,
        epoch_nonce=handle['epoch_nonce'], request_sha256=request_sha,
        profile_sha256=handle['profile_sha256'], samples=rows, summary=summarize(rows),
        evidence=dict(collector_handle_sha256=sha(folder / 'handle.json'),
            raw_report_sha256=sha(folder / 'raw-report.json'), qpc_audit_sha256=sha(folder / 'qpc-audit.json'),
            request_sha256=request_sha, binding_sha256=recomputed['binding_sha256']))
    if reference is not None:
        cohort.update(reference_kind='APIvisible_recorded_serial', reference_matched=True,
                      canonical_task_passed=False)
    return cohort


def partial_cohort(folder, failure, arm):
    path = folder / 'handle.json'
    handle = read(path) if path.is_file() else {}
    samples = sorted(folder.glob('sample-[0-3].json')) if folder.is_dir() else []
    responses = sorted(folder.glob('response-[0-3].json')) if folder.is_dir() else []
    journals = sorted((folder / 'journals').glob('capture-*.bin')) if folder.is_dir() else []
    actual_failure = failure if failure and failure.get('arm') == arm else None
    attempted = bool(handle or samples or responses or journals)
    status = 'failed_or_partial' if attempted or actual_failure else 'not_started'
    if not attempted and failure and failure.get('arm') == 'before' and arm != 'before':
        status = 'excluded_after_baseline_failure'
    completed = handle.get('completed_requests', 0)
    need(type(completed) is int and 0 <= completed <= 4, 'Invalid partial completed request count')
    serial_paths = {name: folder / name for name in ('serial-request.json', 'serial.response.json',
                    'serial.transport.json', 'expected-output.utf8')}
    sample_rows = [read(path) for path in samples]
    return dict(status=status, complete_cohort=False,
        phase_measurement_qualified=False, included_in_comparison=False, summary=None,
        collector_reported_completed_requests=completed,
        saved_samples=len(samples), saved_responses=len(responses), saved_journals=len(journals),
        fully_flushed_journals=sum(path.stat().st_size == 8768 for path in journals),
        excluded_warmup_only=len(sample_rows) == 1 and sample_rows[0].get('ordinal') == 0
            and sample_rows[0].get('phase') == 'warmup_excluded',
        unsupported=handle.get('unsupported') is True,
        restart_required=handle.get('restart_required') is True,
        error_type=error_type(handle) or error_type(actual_failure or {}),
        evidence=dict(handle_sha256=sha(path) if path.is_file() else None,
            sample_sha256=[sha(item) for item in samples], response_sha256=[sha(item) for item in responses],
            journal_sha256=[sha(item) for item in journals],
            journal_bytes=[item.stat().st_size for item in journals],
            serial_oracle_sha256={name: sha(path) for name, path in serial_paths.items() if path.is_file()}))


def qualification(arms, names, campaign_complete, experiment='pld34'):
    result = {}
    q8_traces = experiment == 'draft_vocab_q8' and all(
        arms[arm][name].get('draft_vocab_trace', {}).get('selected_bank_tokens_correlated') is True
        for arm in ARMS for name in names)
    if experiment == 'mtp_gate_cost':
        cost_traces = all(arms[arm][name]['complete_cohort']
            and arms[arm][name].get('mtp_cost_trace', {}).get('native_rule_activation_observed') is True
            for arm in ARMS for name in names)
        arm_ids = [[row['native_request_id'] for name in names
                    for row in arms[arm][name].get('samples', [])] for arm in ARMS]
        cost_ids = all(len(ids) == len(set(ids)) == 8 for ids in arm_ids)
        case_rows = {name: [row for arm in ARMS
                     for row in arms[arm][name].get('samples', [])] for name in names}
        all_rows = [row for rows in case_rows.values() for row in rows]
        cost_outputs = all(len(rows) == 12 and len({row['output_sha256'] for row in rows}) == 1
                           for rows in case_rows.values())
        cost_finish = (len(all_rows) == 24 and len({row['finish_reason'] for row in all_rows}) == 1
                       and {row['output_cap'] for row in all_rows} == {128})
    for name in names:
        cohorts = [arms[arm][name] for arm in ARMS]
        complete = all(cohort['complete_cohort'] for cohort in cohorts)
        rows = [sample for cohort in cohorts for sample in cohort.get('samples', [])]
        checks = dict(all_three_arms_complete=complete,
            same_request_sha256=complete and len({cohort['request_sha256'] for cohort in cohorts}) == 1,
            same_output_sha256=complete and len({row['output_sha256'] for row in rows}) == 1,
            same_actual_input_tokens=complete and len({row['actual_input_tokens'] for row in rows}) == 1,
            same_actual_output_tokens=complete and len({row['actual_output_tokens'] for row in rows}) == 1)
        if experiment in LOG_EXPERIMENTS:
            checks['lookup_mechanism_exercised'] = complete and all(
                cohort['summary']['pooled_scoped_counters']['lookup']['drafted'] > 0
                and cohort['summary']['pooled_scoped_counters']['lookup']['accepted'] > 0
                for cohort in cohorts)
        if experiment == 'draft_vocab_q8':
            checks['all_q8_case_arm_traces_qualified'] = q8_traces
        if experiment == 'mtp_gate_cost':
            checks.update(all_cost_case_arm_traces_qualified=cost_traces,
                all_cost_arm_native_ids_unique=cost_ids, all_cost_cases_output_matched=cost_outputs,
                all_cost_finish_and_cap_semantics_matched=cost_finish)
        qualified = campaign_complete and all(checks.values())
        result[name] = dict(qualified=qualified, **checks)
        for cohort in cohorts:
            cohort['included_in_comparison'] = qualified
    return result


def first_attempt_summary(path):
    value = terminal_handle(path)
    need(value['completed'] is False, 'First failed attempt must remain separately classified')
    return dict(terminal=True, completed=False, restored=True,
        no_measurement_requests=value.get('no_measurement_requests') is True,
        error_type=error_type(value), source_handle_sha256=sha(path),
        included_in_comparison=False, summary=None)


def build_report(handle_path, *, first_attempt=None, public_reference=PUBLIC_REFERENCE):
    handle_path = Path(handle_path)
    handle = terminal_handle(handle_path)
    experiment, folder = handle['experiment'], handle_path.parent
    source = public_identity(Path(public_reference))
    names = CASES[experiment]
    need(set(handle.get('failed_cases', {})).issubset(names), 'Unknown failed case')
    for arm in ARMS:
        need(set(handle.get('results', {}).get(arm, {})).issubset(names), 'Unknown result case')
    successful = any(handle.get('results', {}).get(arm) for arm in ARMS)
    sources = executed_sources(folder, required=successful, experiment=experiment)
    cost = experiment == 'mtp_gate_cost'
    registration = cost_registration(folder, sources) if cost and sources else None
    accounting = accounting_for_sources(sources)
    trace_qualifier = (trace_qualifier_for_sources(sources)
                       if experiment == 'draft_vocab_q8' and successful else None)
    if cost and successful:
        trace_qualifier = cost_module('mtp_cost_trace.py', sources).qualify_trace
    reference = reference_study() if experiment == 'pld34log_reference' else None
    if reference is not None:
        verify_reference_declaration(handle.get('reference_study'), reference)
    if reference is not None and successful:
        need(sources['collect_epoch.py']['implementation_version'] == 3,
             'Reference study requires the expected-output-count collector version')
    profiles, arms = {}, {}
    for arm in ARMS:
        entries = handle.get('results', {}).get(arm, {})
        arms[arm] = {}
        profile_path = folder / f'{arm}.profile.json'
        if profile_path.is_file():
            profiles[arm] = arm_profile(safe_profile(profile_path, sha(profile_path), experiment), arm, experiment)
        for name in names:
            result = entries.get(name)
            case_dir = folder / arm / name
            if result is not None and result.get('collector', {}).get('completed') is True:
                cohort = complete_cohort(case_dir, result, source, accounting, reference,
                    q8_case=name if experiment == 'draft_vocab_q8' else None,
                    cost_case=name if cost else None)
                profile = safe_profile(folder / f'{arm}.profile.json', cohort['profile_sha256'], experiment)
                arm_profile(profile, arm, experiment)
                need(arm not in profiles or profiles[arm] == profile, 'Arm profile changed between cases')
                need(all(row['native_slot'] < profile['slots'] for row in cohort['samples']),
                     'Native journal slot exceeds the measured profile')
                profiles[arm] = profile
                if experiment == 'draft_vocab_q8':
                    cohort['draft_vocab_trace'] = draft_vocab_trace(
                        case_dir, result, result['samples'], profile, trace_qualifier)
                if cost:
                    cohort['mtp_cost_trace'] = mtp_cost_trace(
                        case_dir, result, result['samples'], profile, trace_qualifier)
                    measured = cohort['samples'][1:]
                    cohort['summary']['whole_http_output_tps'] = (
                        sum(row['actual_output_tokens'] for row in measured)
                        / sum(row['http_qpc_seconds'] for row in measured))
            else:
                cohort = partial_cohort(case_dir, handle.get('failed_cases', {}).get(name), arm)
            arms[arm][name] = cohort
    comparisons = qualification(arms, names, handle['completed'], experiment)
    final = handle.get('final')
    if cost:
        need(type(final) is dict
             and handle.get('baseline', {}).get('profile', {}).get('sha256') == COST_PROFILE_SHA
             and final.get('profile', {}).get('sha256') == COST_PROFILE_SHA
             and final.get('outer', {}).get('phase') == final.get('inner', {}).get('phase') == 'ready'
             and final.get('native', {}).get('status') == 'ok'
             and final.get('native', {}).get('version') == dict(api='0.19.1', engine='0.19.1', match=True)
             and final['native']['version']['match'] is True
             and json.dumps({key: final.get('native', {}).get(key)
                             for key in ('context', 'slots', 'kv_pool_positions')}, sort_keys=True) == json.dumps(
                 dict(context=32768, slots=1, kv_pool_positions=32768), sort_keys=True),
             'Cost restored readiness or selected profile differs')
    final_public = dict(restored=True, readiness_available=type(final) is dict)
    if type(final) is dict:
        need(final['profile']['sha256'] == handle['baseline']['profile']['sha256'],
             'Restored profile differs from initial profile')
        final_public.update(profile_sha256=digest(final['profile']['sha256']),
            context=number(final['native']['context']), slots=number(final['native']['slots']),
            kv_pool_positions=number(final['native']['kv_pool_positions']))
    report = dict(schema='halogen0191.' + experiment + '-raw-comparison.public.v1',
        experiment=experiment, version='0.19.1', campaign_completed=handle['completed'],
        terminal=True, restored=True, immutable_source=source, executed_source_pins=sources,
        response_accounting_implementation_version=sources.get('collect_epoch.py', {}).get('implementation_version'),
        private_observation_pins=private_observation_pins(sources),
        methodology=dict(requests_per_complete_cohort=4, excluded_warmups_per_cohort=1,
            measured_repetitions_per_cohort=3, requests_sent_serially=True,
            raw_clock='Direct CLOCK_MONOTONIC_RAW syscalls bracket one original steady-clock call.',
            native_clock='Untouched native steady-clock values from the exact verified provider.',
            http_clock='Windows QPC before posting through complete response.read, before persistence.',
            raw_aggregation='Arithmetic mean of three per-request midpoint, lower and upper rates.',
            raw_numerators='Processed prompt tokens and actual native/API generated output total.',
            native_decode_begin_count=1, generated_delta_retained_separately=True,
            adjustment='None. Observer overhead is retained with no scaling or subtraction.',
            api_phase_clock_qualified=False, full_responses_kept_private=True,
            headline_requires_three_complete_matching_arms=True),
        profiles=profiles, arms=arms, comparison_qualification=comparisons,
        qualified_cases=[name for name in names if comparisons[name]['qualified']],
        single_condition_qualified_cohorts=[dict(arm=arm, case=name)
            for arm in ARMS for name in names if arms[arm][name]['complete_cohort']],
        first_preoverlay_attempt=first_attempt_summary(Path(first_attempt)) if first_attempt else None,
        final_runtime=final_public, evidence=dict(campaign_handle_sha256=sha(handle_path),
            executed_source_manifest_sha256=sha(folder / 'executed-source-pins.json')
                if (folder / 'executed-source-pins.json').is_file() else None),
        exporter_sha256=sha(Path(__file__)))
    if reference is not None:
        report.update(reference)
    if cost:
        report['registration'] = registration
        report['methodology'].update(planned_cohort_requests=24, planned_measured_requests=18,
            planned_excluded_warmups=6, startup_validation_requests_included_in_cohort=False,
            fixed_draft_precision_bits=4, rule_by_arm=dict(before='gate', candidate='cost', after='gate'),
            whole_http_output_aggregation='Measured useful output token total divided by measured whole-HTTP QPC total.',
            all_cases_and_arms_required=True, per_decision_policy_observed=False)
    return report


def render_markdown(report):
    lines = ['# Halogen 0.19.1 ' + report['experiment'] + ' RAW comparison', '',
        'The campaign is terminal and the normal serving profile was restored.', '',
        'RAW bounds include observer overhead. Native clock and API rates are separate observations. '
        'API phase clocks remain unqualified.', '', '## Profiles', '',
        '| Arm | Native slots | Prefill chunk | Max prefill tokens | KV pool positions | PLD |',
        '| --- | --- | --- | --- | --- | --- |']
    if report['experiment'] == 'pld34log_reference':
        plan = report['public_plan']['markdown']
        pilot = report['original_failed_pilot_report']['markdown']
        pilot_statement = (
            f'The original failed pilot has a separate report. [Failed canonical pilot]({pilot["file"]}).'
            if pilot['available'] else
            f'The original failed pilot report is planned and currently unavailable. '
            f'[Planned failed canonical pilot]({pilot["file"]}).')
        lines[2:2] = [
            '**Performance-only study against the recorded API-visible serial response. '
            'That recorded response failed the canonical final-LF requirement.**', '',
            'The frozen recorded output has 4933 UTF-8 bytes. The canonical expected output has '
            '4934 bytes and includes one final LF absent from the recorded output. '
            'Native token-sequence identity is unverified.', '',
            f'The public plan was registered before measurements. [Study plan]({plan["file"]}).', '',
            pilot_statement, '']
    for arm, profile in report['profiles'].items():
        lines.append(f'| {arm} | {profile["slots"]} | {profile["prefill_chunk"]} | '
                     f'{profile["max_prefill_tokens"]} | {profile["kv_pool_positions"]} | {profile["pld"]} |')
    if report['experiment'] == 'draft_vocab_q8':
        lines.extend(['', '| Arm | Draft vocabulary Q8 flag | Declared precision bits | Serve trace |',
                      '| --- | --- | --- | --- |'])
        for arm, profile in report['profiles'].items():
            lines.append(f'| {arm} | {profile["draft_vocab_q8"]} | '
                         f'{8 if profile["draft_vocab_q8"] else 4} | {profile["serve_trace"]} |')
        lines.extend(['', 'Precision follows the manifest and pinned native loader and consumer branch. '
            'Direct dtype per dispatch remains unobserved. A speed comparison requires matching '
            'saved native traces with positive selected-bank and MTP head activity, zero lookup '
            'activity and pinned qualifier source for both cases in all three arms.'])
    if report['experiment'] == 'mtp_gate_cost':
        lines.extend(['', '| Arm | Native MTP gate rule | Draft vocabulary Q8 flag | Serve trace |',
                      '| --- | --- | --- | --- |'])
        for arm, profile in report['profiles'].items():
            lines.append(f'| {arm} | {profile["mtp_gate_rule"]} | '
                         f'{profile["draft_vocab_q8"]} | {profile["serve_trace"]} |')
        lines.extend(['', 'The fixed-Q4 gate/cost/gate design has 24 cohort requests across two workloads '
            'and three arms, including six excluded warmups. Startup correctness requests are outside '
            'the cohort and timing means. Native startup rule activation and matching per-request '
            'head counters are observed. Individual cost decisions remain unobserved. Full-vocabulary '
            'fallback is valid. Both workloads in all three arms must qualify together.'])
    workload_description = (
        'The real-log-json-quote workload uses frozen log records and an exact output oracle. '
        'A mechanism comparison requires positive measured lookup drafted and accepted totals in every arm.'
        if report['experiment'] in LOG_EXPERIMENTS else
        'Natural8192 and natural16384 use genuine War and Peace prose. Native input counts include '
        'the frozen task and prompt framing.')
    lines.extend(['', '## Workloads', '', workload_description, '', '## Complete cohorts', '',
        'Each complete cohort contains one excluded warmup and three measured requests. '
        'The table summarizes those three measured requests.', '',
        '| Arm | Case | Native input tokens | Actual output tokens | Head accepted/drafted | '
        'RAW prefill t/s, midpoint [lower, upper] | RAW decode t/s, midpoint [lower, upper] | '
        'HTTP QPC seconds | Matched comparison |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- |'])
    complete = 0
    for arm in ARMS:
        for name, cohort in report['arms'][arm].items():
            if not cohort['complete_cohort']:
                continue
            complete += 1
            summary = cohort['summary']
            cells = []
            for phase in ('prefill', 'decode'):
                rates = summary['mean_raw_tps'][phase]
                cells.append(f'{rates["mid"]:.3f} [{rates["lower"]:.3f}, {rates["upper"]:.3f}]')
            counts = []
            for key in ('actual_input_tokens', 'actual_output_tokens'):
                values = summary[key]
                counts.append(str(values[0]) if len(set(values)) == 1 else ', '.join(map(str, values)))
            head = summary['pooled_scoped_counters']['head']
            acceptance = f'{head["accepted"]}/{head["drafted"]}'
            if head['acceptance_fraction'] is not None:
                acceptance += f' ({head["acceptance_fraction"] * 100:.3f}%)'
            lines.append(f'| {arm} | {name} | {counts[0]} | {counts[1]} | {acceptance} | {cells[0]} | {cells[1]} | '
                         f'{summary["mean_http_qpc_seconds"]:.6f} | {cohort["included_in_comparison"]} |')
    if not complete:
        lines.extend(['', 'There are no complete measured cohorts.'])
    if not report['qualified_cases']:
        lines.extend(['', 'No three-arm comparison qualified.'])
    if report['experiment'] == 'mtp_gate_cost':
        lines.extend(['', '## Whole-HTTP useful output', '',
            'Useful output token totals are divided by the matching measured whole-HTTP QPC totals. '
            'RAW phase rates and pooled head acceptance retain their separate summaries.', '',
            '| Arm | Case | Whole-HTTP useful-output t/s |', '| --- | --- | --- |'])
        for arm in ARMS:
            for name, cohort in report['arms'][arm].items():
                if cohort['complete_cohort']:
                    lines.append(f'| {arm} | {name} | {cohort["summary"]["whole_http_output_tps"]:.3f} |')
    lines.extend(['', '## Native and API observations', '',
        '| Arm | Case | Native prefill t/s | Native decode t/s | API prefill t/s | API decode t/s |',
        '| --- | --- | --- | --- | --- | --- |'])
    for arm in ARMS:
        for name, cohort in report['arms'][arm].items():
            if cohort['complete_cohort']:
                summary = cohort['summary']
                native, api = summary['native_clock_observations'], summary['api_reported_observations']
                lines.append(f'| {arm} | {name} | {native["prefill_mean_tps"]:.3f} | '
                    f'{native["decode_mean_tps"]:.3f} | {api["prefill_mean_tps"]:.3f} | {api["decode_mean_tps"]:.3f} |')
    lines.extend(['', '## Failed, partial and unstarted cohorts', '',
        '| Arm | Case | Status | Saved samples | Saved responses | Error type |',
        '| --- | --- | --- | --- | --- | --- |'])
    for arm in ARMS:
        for name, cohort in report['arms'][arm].items():
            if not cohort['complete_cohort']:
                lines.append(f'| {arm} | {name} | {cohort["status"]} | {cohort["saved_samples"]} | '
                             f'{cohort["saved_responses"]} | {cohort["error_type"] or ""} |')
    first = report['first_preoverlay_attempt']
    if first is not None:
        request_statement = ('No measurement requests were recorded.' if first['no_measurement_requests']
                             else 'The attempt has no qualified comparison.')
        if report['experiment'] == 'mtp_gate_cost':
            lines.extend(['', '## Earlier failed counter-qualification attempt', '',
                f'The earlier attempt stopped after overlay application and four cohort requests because '
                f'counter qualification failed ({first["error_type"] or "unrecorded"}). '
                'None of its timing samples is included in this comparison.'])
        else:
            lines.extend(['', '## First pre-overlay attempt', '',
                f'The separate attempt completed no comparison. Its error type was {first["error_type"] or "unrecorded"}. '
                + request_statement])
    lines.extend(['', 'The accompanying JSON retains actual token counts, pooled head, lookup and grammar '
        'counters, qualification checks and source, request, response and journal hashes. '
        'Full response bodies remain private.', ''])
    return '\n'.join(lines)


def write_outputs(report, name=None, *, write=False):
    name = name or ('halogen0191-' + report['experiment'].replace('_', '-') + '-raw-20261107'
                    + ('-v2' if report['experiment'] == 'mtp_gate_cost' else ''))
    need(type(name) is str and re.fullmatch('[a-z0-9][a-z0-9-]{0,100}', name) is not None,
         'Public output name must be one lowercase basename')
    paths = [PUBLIC_DIR / (name + suffix) for suffix in ('.json', '.md')]
    need(all(not path.exists() and not path.is_symlink() for path in paths), 'Public output already exists')
    payloads = [(json.dumps(report, indent=2, allow_nan=False) + '\n').encode(),
                render_markdown(report).encode()]
    if write:
        streams = []
        created = []
        try:
            for path in paths:
                stream = path.open('xb')
                streams.append(stream)
                stat = os.fstat(stream.fileno())
                created.append((path, stat.st_dev, stat.st_ino))
            for stream, payload in zip(streams, payloads):
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            for stream in streams:
                stream.close()
            for path, device, inode in created:
                if path.is_file() and (path.stat().st_dev, path.stat().st_ino) == (device, inode):
                    path.unlink()
            raise
        finally:
            for stream in streams:
                stream.close()
    return dict(written=write, outputs=[dict(file=path.name, sha256=hashlib.sha256(payload).hexdigest())
        for path, payload in zip(paths, payloads)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--handle', type=Path, required=True)
    parser.add_argument('--first-attempt', type=Path)
    parser.add_argument('--name')
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    report = build_report(args.handle, first_attempt=args.first_attempt)
    print(json.dumps(write_outputs(report, args.name, write=args.write), indent=2))


if __name__ == '__main__':
    main()
