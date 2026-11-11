"""Prepare fresh private source only; never install or contact a runtime."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(r'C:\Projects\strix-alloy-clean')
HERE = Path(__file__).resolve().parent
PRIMARY = HERE.parent
NORMAL = ROOT / 'backends/halogen-wsl2-0.20.3'
PROFILE = PRIMARY / 'serving0203-text32k-8192.json'
OLD = ROOT / 'server/.local/halogen-update-20261110/primary0201/stateful1012-live-prep/consumer/overlay-prep/prepared-raw-reverse-v3'
OLD_TRANSITION_SHA = '815f2cd06e272b0cc8a600ec051dad1db034f61892620aafe44b9c975d7baa55'
ENGINE = 'bf84053705d1e89c214ff64c79ad1276c5fe353d80a9bb0f38ef3bac6645b97c'
API = '7f529cd224e973265237d70e8b9157350302a19faffdc70c05eee3a884e2f4f4'
CONSUMER = HERE / 'root-cpu-build-v1/libhgn0203-stream.so'
CONSUMER_SHA = None
RAW = HERE / 'raw/observer/libhgn0203_raw_side.so'
RAW_SHA = None
BUILD = HERE / 'root-cpu-build-v1/handle.json'
EXISTING = ('scripts/auth_api.py', 'scripts/kernel_controls.py',
            'scripts/service.py', 'scripts/startup_guard.py')


def need(ok, message):
    if not ok: raise ValueError(message)


def read(path): return json.loads(Path(path).read_bytes())
def digest(data): return hashlib.sha256(data).hexdigest()


def safe(path):
    path = Path(path)
    need(path.is_file() and not any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)),
         'Missing or linked source: ' + str(path))
    return path.read_bytes()


def pin(path):
    data = safe(path)
    return dict(path=str(Path(path).resolve()), bytes=len(data), sha256=digest(data))


def encoded(value): return (json.dumps(value, indent=2) + '\n').encode()


def rebase(data):
    # Explicit identity changes only. The entire rebased old normal source must
    # match actual current source before its retained source delta can be used.
    values = ((b'0.20.1', b'0.20.3'), (b'0201', b'0203'),
        (b'7a72e138f0090008d171e41358a23f86a875fe92fadbcbc5daf2d3225e426577', ENGINE.encode()),
        (b'b2d1d6df7580d69baf9952feb9383682387db20ec1211620437e78c3d2ee9e30', API.encode()))
    for before, after in values: data = data.replace(before, after)
    return data.replace(b'\r\n', b'\n')


def constant(source, name, value):
    text, count = re.subn(r'^' + name + r' = .+$', name + ' = ' + repr(value), source.decode(), flags=re.M)
    need(count == 1, 'Exact binding assignment missing: ' + name)
    return text.encode()


def bind_native_products(build_sha256):
    global CONSUMER_SHA, RAW_SHA
    need(type(build_sha256) is str and re.fullmatch('[a-f0-9]{64}', build_sha256),
         'Explicit completed fresh Root CPU build SHA256 required')
    need(pin(BUILD)['sha256'] == build_sha256, 'Fresh Root CPU build receipt changed')
    build = read(BUILD)
    need(build.get('completed') is True and build.get('terminal') is True
         and build.get('engine_or_GPU_NPU_executed') is False,
         'Fresh terminal CPU-only Root build required')
    outputs = {str(Path(row['path']).resolve()): row for row in build['outputs']}
    need(set(outputs) == {str(CONSUMER.resolve()), str(RAW.resolve())},
         'Exactly fresh consumer and RAW output paths required')
    for path in (CONSUMER, RAW):
        need(pin(path) == outputs[str(path.resolve())], 'Fresh Root-built product changed')
    CONSUMER_SHA = outputs[str(CONSUMER.resolve())]['sha256']
    RAW_SHA = outputs[str(RAW.resolve())]['sha256']
    return pin(BUILD)


def prepare(output, build_sha256):
    output = Path(output).resolve()
    need(output.is_relative_to(HERE) and not output.exists(), 'Preserve prior private preparation')
    need(pin(OLD / 'transition.json')['sha256'] == OLD_TRANSITION_SHA, 'Retained source delta changed')
    old = read(OLD / 'transition.json')
    manifest = read(NORMAL / 'profiles/sources.json')
    need(manifest['version'] == '0.20.3' and len(manifest['files']) == 47, 'Exact fresh stock source required')
    normal = {name: safe(NORMAL / name) for name in manifest['files']}
    need(all(digest(data) == manifest['files'][name] for name, data in normal.items()), 'Normal source changed')
    normal['profiles/sources.json'] = safe(NORMAL / 'profiles/sources.json')
    for name in EXISTING:
        need(digest(safe(OLD / 'rollback' / name)) == old['baseline'][name]
             and digest(safe(OLD / 'candidate' / name)) == old['candidate'][name], 'Old delta identity changed')
        need(rebase(safe(OLD / 'rollback' / name)) == normal[name].replace(b'\r\n', b'\n'),
             'New source has an unreviewed structural difference: ' + name)
    build_pin = bind_native_products(build_sha256)
    need(isinstance(CONSUMER_SHA, str) and pin(CONSUMER)['sha256'] == CONSUMER_SHA,
         'Fresh Root-built consumer differs')
    need(pin(RAW)['sha256'] == RAW_SHA, 'Fresh Root-built RAW differs')
    config = read(PROFILE)
    engine = config['engine']
    need(engine['directory'] == 'backends/halogen-wsl2-0.20.3' and engine['context'] == 32768
         and engine['slots'] == 1 and engine['kv_pool_positions'] == 32768
         and engine['prefill_chunk'] == engine['max_prefill_tokens'] == 8192
         and engine['prompt_cache'] == 'Off', 'Current frozen serving policy differs')
    release = read(NORMAL / 'profiles/release.json')
    stock_entrypoint = safe(NORMAL / '.local/entrypoint-wsl.sh')
    need(digest(stock_entrypoint) == release['adapted_entrypoint_sha256'], 'Stock entrypoint changed')
    need(stock_entrypoint.count(b'/halogen/tools/serve_api.py') == 5, 'Fresh API launch sites differ')
    service_entrypoint = stock_entrypoint.replace(b'/halogen/tools/serve_api.py', b'/candidate/auth_api.py')
    candidate = dict(normal)
    for name in EXISTING: candidate[name] = rebase(safe(OLD / 'candidate' / name))
    for name in old['added']:
        need(digest(safe(OLD / 'candidate' / name)) == old['candidate'][name], 'Retained added source changed')
        candidate[name] = rebase(safe(OLD / 'candidate' / name))
    for name in ('api_stream_feedback.py', 'token_feedback.py', 'api_observation.py',
                 'stream_publisher_v2.py', 'reverse_stream_publisher_v2.py', 'wire.py'):
        candidate['scripts/' + name] = safe(HERE / 'api' / name)
    for name in ('stream_consumer.c', 'stream_consumer.h', 'stream_relay.S', 'native_pins.h',
                 'cold_addresses.h', 'sha256_core.h'):
        candidate['patches/' + name] = safe(HERE / 'consumer-native' / name)
    candidate['patches/stream_cold_install.c'] = safe(HERE / 'consumer-native/cold_install.c')
    candidate['scripts/reverse_stream_binding.py'] = constant(
        candidate['scripts/reverse_stream_binding.py'], 'BASE_ENTRYPOINT_SHA', digest(service_entrypoint))
    auth_sha = digest(candidate['scripts/auth_api.py'])
    helper = candidate['scripts/phase_raw_binding.py']
    values = dict(DSO_SHA=RAW_SHA, DSO_BYTES=pin(RAW)['bytes'],
        MACHINE_SHA=pin(NORMAL / '.local/machine.json')['sha256'],
        INSTALL_SHA=pin(NORMAL / '.local/install-manifest.json')['sha256'],
        RELEASE_SHA=pin(NORMAL / 'profiles/release.json')['sha256'],
        AUTH_SHA=auth_sha, API_SHA=digest(candidate['scripts/api_observation.py']))
    for name, value in values.items(): helper = constant(helper, name, value)
    candidate['scripts/phase_raw_binding.py'] = helper
    candidate['scripts/startup_guard.py'] = candidate['scripts/startup_guard.py'].replace(
        b'f82f6a4f2bb1a3d970578d590dfa617f18c81c03b674eaa8be97f7a9e5ad1aa3', RAW_SHA.encode())
    cfg = json.loads(candidate['profiles/hdo2-qualified.json'])
    cfg.update(native_dso=dict(bytes=pin(CONSUMER)['bytes'], sha256=CONSUMER_SHA), runtime_bound=True,
               fresh_native_contract=pin(HERE / 'consumer-native/native-contract.json'),
               fresh_RAW_binding=pin(HERE / 'raw/binding.json'),
               original_CPU_route_proof_reused_not_reexecuted=True,
               actual_candidate_Docker_mapping_verified=False)
    candidate['profiles/hdo2-qualified.json'] = encoded(cfg)
    cm = json.loads(candidate['profiles/sources.json'])
    cm['files'] = {name: digest(data) for name, data in candidate.items() if name != 'profiles/sources.json'}
    cm['integration_status'] = 'Private fresh native-T/RAW/HDO2 cohort source; runtime unqualified'
    candidate['profiles/sources.json'] = encoded(cm)
    for name, data in candidate.items():
        if name.endswith('.py'): ast.parse(data, filename=name)
    output.mkdir()
    for section, files in (('candidate', candidate), ('rollback', normal)):
        for name, data in files.items():
            target = output / section / name
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
    for arm in ('before', 'candidate', 'after'):
        profile = json.loads(json.dumps(config))
        profile['engine']['kernel_controls'].update(HALOGEN_PHASE_RAW=1, HALOGEN_SERVE_TRACE=1,
            HALOGEN_DECODE_PREFETCH=0, HALOGEN_EXTERNAL_STREAM=int(arm == 'candidate'))
        (output / (arm + '.profile.json')).write_bytes(encoded(profile))
    changed = [name for name in normal if candidate[name] != normal[name]]
    added = [name for name in candidate if name not in normal]
    transition = dict(schema='halogen0203.RAW-reverse-HDO2-private-source-overlay.v1',
        source_only=True, runtime_bound=True, normal_package=str(NORMAL),
        normal_source_manifest=pin(NORMAL / 'profiles/sources.json'), normal_source_members=47,
        baseline={name: digest(data) for name, data in normal.items()},
        candidate={name: digest(data) for name, data in candidate.items()},
        changed_existing=changed, added=added, current_normal_untouched=True,
        common_RAW_observer_all_arms=True, watchdog_timers_and_uptime_body_byte_identical=True,
        retained_source_delta=pin(OLD / 'transition.json'),
        explicit_rebased_normal_structural_parity=list(EXISTING),
        root_built_consumer=pin(CONSUMER), root_built_RAW=pin(RAW),
        fresh_native_contract=pin(HERE / 'consumer-native/native-contract.json'),
        fresh_RAW_binding=pin(HERE / 'raw/binding.json'), normal_profile=pin(PROFILE),
        fresh_Root_CPU_build=build_pin,
        public_models_credentials_or_state_modified=False, hardware_used=False)
    (output / 'transition.json').write_bytes(encoded(transition))
    need(all(digest(safe(NORMAL / name)) == digest(data) for name, data in normal.items()), 'Normal changed during preparation')
    return transition


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--build-sha256', help='Exact completed fresh Root CPU build receipt SHA256')
    parser.add_argument('--output', type=Path, default=HERE / 'overlay-v2')
    args = parser.parse_args()
    if not args.prepare:
        print(json.dumps(dict(source_only=True, hardware=False, requires='--prepare', output=str(args.output))))
        return 0
    result = prepare(args.output, args.build_sha256)
    print(json.dumps(dict(prepared=True, normal_untouched=True,
        transition=pin(args.output / 'transition.json'), source_files=len(result['candidate']))))
    return 0


if __name__ == '__main__': raise SystemExit(main())
