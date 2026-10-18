"""Private v0.1.1 AR4K release binding; never qualifies on import."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from dataclasses import asdict
import subprocess
import argparse
import os
import time
import ntpath
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from gufo_control import smoke_guard, smoke_http, smoke_store
from gufo_control import admission, operator_policy, operator_store, smoke_policy, benchmark_suite
from gufo_control.telemetry import collect_snapshot
from .review_pin import QUALIFICATION_SHA256

PROFILE = 'native-v011-windows-ar4k-smoke-20260929'
ROOT = Path('C:/Projects/strix-alloy-research')
BUILD = ROOT / 'runtimes/gufo-native-v011-stable-port-therock10.2'
SOURCE = ROOT / 'sources/gufo-release-20260929'
SOURCE_COMMIT = 'b0f8673470a3dcc2b5e9c9546c48a40b82b5ff31'
RUNTIME_MANIFEST_SHA256 = '4C4D329C0D7EB0395153D1ECBDB8BC511A71ED94C8C4FA5F5BDE5B7CD3F6B8ED'
EXE_SHA256 = 'F72443ECE330684185F8A240C3B4271321B4C6171D52377DE0EC8DDC7B4C81B4'
BUILD_DIFF_SHA256 = 'AAA33F64F74DF74674CCACDF2C58B6F0DA8A2DAE0C64931F6EB278B7D0015853'
BUILD_UNTRACKED_SHA256 = 'C17C18E77B3524BFBD9887BE270EA083B0A60EEEB3410A7EE73166CA55167EE7'
BUILD_UNTRACKED_PATHS = '''compat/win32/hip_include/cmath
compat/win32/include/arpa/inet.h
compat/win32/include/fcntl.h
compat/win32/include/gufo_posix_time.h
compat/win32/include/gufo_posix_types.h
compat/win32/include/gufo_posix.h
compat/win32/include/gufo_socket.h
compat/win32/include/gufo_win32_unmacro.h
compat/win32/include/netdb.h
compat/win32/include/netinet/in.h
compat/win32/include/netinet/tcp.h
compat/win32/include/poll.h
compat/win32/include/pthread.h
compat/win32/include/sched.h
compat/win32/include/signal.h
compat/win32/include/spawn.h
compat/win32/include/strings.h
compat/win32/include/sys/file.h
compat/win32/include/sys/mman.h
compat/win32/include/sys/resource.h
compat/win32/include/sys/socket.h
compat/win32/include/sys/stat.h
compat/win32/include/sys/syscall.h
compat/win32/include/sys/time.h
compat/win32/include/sys/types.h
compat/win32/include/sys/utsname.h
compat/win32/include/sys/wait.h
compat/win32/include/time.h
compat/win32/include/unistd.h
compat/win32/posix.cpp
compat/win32/spawn.cpp
docs/WINDOWS.md
src/core/platform/device_memory.cpp
src/core/platform/device_memory.hpp
src/core/platform/socket.hpp
src/core/platform/tuning.hpp
src/models/qwen38_flash_next/prompt_lookup.hpp
tests/core/platform_tuning_test.cpp
tests/models/qwen38_flash_next/iq_experts_ops_test.cpp
tests/models/qwen38_flash_next/prompt_lookup_test.cpp
tools/windows/build.ps1
tools/windows/check.ps1
tools/windows/run-flash-next.ps1'''.splitlines()
# Candidate allowances only. Independent review must bind these exact fields.
BOUNDS = dict(gpu_gib=68, host_gib=4, shared_gib=20, commit_gib=76,
              prelaunch_gib=49, runtime_gib=24, commit_reserve_gib=12)
PROMPTS = ('What is 6 times 7? Reply with the number only.',
           'Antworte exakt mit diesem einen Wort, ohne Satzzeichen: Grün')
ANSWERS = ('42', 'Grün')
EVIDENCE = ROOT / 'reports/native-v011-ar4k-smoke-20260929-runs'
QUALIFICATION = ROOT / 'reports/native-v011-ar4k-smoke-20260929-qualification.json'
PROBE = ROOT / 'build/gufo-telemetry-native-20260927-v2/gufo-memory-probe.exe'
PROBE_SHA256 = 'C2A655EFACD774EEF2DC941CABAF591D902706677583181C3447A7A219C8A392'
PROBE_MANIFEST_SHA256 = 'C9C0BA33F77416BAC04F221117416B27C96C884747EBF0FE8BCD53B624FFE18D'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def fixed_argv(secret):
    args = smoke_guard.fixed_argv(secret)
    args[0] = str(BUILD / 'gufo.exe')
    return args


def recipe_definition(profile_id):
    if profile_id != PROFILE:
        raise ValueError('unknown_release_profile')
    return dict(profile_id=PROFILE, context_tokens=4096, max_prompt_tokens=512,
        max_requests=2, thinking=False, speculative=False,
        schedule=[dict(ordinal=i, case=str(i), kind='correctness', mode='greedy',
            repetition=0, target_prompt_tokens=None, cache_prompt=False,
            output_budget=64) for i in range(2)],
        prompts=list(PROMPTS), answers=list(ANSWERS))


def recipe_json(profile_id):
    return canonical(recipe_definition(profile_id))


def request_for(row, calibration=None):
    index = row['ordinal']
    if type(index) is not int or index not in (0, 1):
        raise ValueError('invalid_release_request')
    expected = recipe_definition(PROFILE)['schedule'][index]
    if any(row.get(key) != value for key, value in expected.items()):
        raise ValueError('invalid_release_request')
    request = deepcopy(smoke_http.REQUEST)
    request.update(messages=[dict(role='user', content=PROMPTS[index])], stream=False)
    request.pop('stream_options')
    return request


def assess(row, observation, definition):
    errors = []
    if observation.get('success') is not True:
        errors.append('request_failed')
    if observation.get('visible_answer', '').strip() != ANSWERS[row['ordinal']]:
        errors.append('wrong_exact_answer')
    if observation.get('finish_reason') != 'stop':
        errors.append('incomplete_finish')
    count = observation.get('metrics', {}).get('logical_prompt_tokens')
    if type(count) is not int or not 0 < count <= 512:
        errors.append('prompt_count_unknown_or_excessive')
    # The existing finite suite calls custom assessors its "matched" seam.
    # Supply only that seam's summary fields; this is no performance comparison.
    observation['matched_evidence'] = dict(quality_failed=bool(errors), fatal_kind=None)
    return dict(state='failed' if errors else 'passed'), errors


def qualification_record(identity, review_id):
    return dict(profile=PROFILE, identity=identity, bounds=dict(BOUNDS),
        recipe=sha256(recipe_json(PROFILE).encode()).hexdigest().upper(),
        review_id=review_id, scope='one-attempt-two-answers-controlled-cleanup')


def validate_qualification(value, identity):
    if not isinstance(value, dict) or not isinstance(value.get('review_id'), str) or not value['review_id'].strip():
        raise ValueError('release_qualification_missing')
    if canonical(value) != canonical(qualification_record(identity, value['review_id'])):
        raise ValueError('release_qualification_mismatch')


class ReleasePolicy:
    owned_inventory_frame = staticmethod(smoke_policy.owned_inventory_frame)
    stricter_runtime_baseline = staticmethod(smoke_policy.stricter_runtime_baseline)
    recovery_reasons = staticmethod(operator_policy.recovery_reasons)

    def __init__(self):
        self.profile = None

    def profile_from_manifest(self, manifest):
        validate_qualification(manifest['qualification'], manifest['identity'])
        q = manifest['qualification']
        self.profile = smoke_policy.SmokeProfile(profile_id=PROFILE,
            gpu_peak_bytes=BOUNDS['gpu_gib']*admission.GIB,
            host_peak_bytes=BOUNDS['host_gib']*admission.GIB,
            shared_physical_allowance_bytes=BOUNDS['shared_gib']*admission.GIB,
            commit_peak_bytes=BOUNDS['commit_gib']*admission.GIB,
            source_commit=SOURCE_COMMIT, qualified=True, review_id=q['review_id'],
            shared_allowance_review_id=q['review_id'], qualification_json=canonical(q))
        return self.profile

    def _common(self, profile, base, frame, now, now_utc, max_age):
        if self.profile is None or profile != self.profile:
            return ['unqualified_profile']
        if not operator_policy._base_valid(base):
            return ['invalid_baseline']
        reasons = operator_policy._frame_reasons(frame, now=now, now_utc=now_utc, max_age=max_age)
        if reasons:
            return reasons
        if operator_policy._identity(frame.snapshot) != base.identity:
            return ['adapter_changed']
        if frame.query_start < base.last_end:
            return ['sample_before_baseline']
        return []

    def frame_numeric_reasons(self, profile, base, frame, *, now, now_utc):
        reasons = self._common(profile, base, frame, now, now_utc, operator_policy.MAX_SAMPLE_AGE_SECONDS)
        if reasons:
            return reasons
        s = frame.snapshot
        if s['available_physical_bytes'] < admission.RUNTIME_FLOOR:
            reasons.append('runtime_physical_floor')
        if s['commit_headroom_bytes'] < admission.COMMIT_RESERVE:
            reasons.append('commit_floor')
        if base.available_min-s['available_physical_bytes'] > profile.host_peak_bytes+profile.shared_physical_allowance_bytes:
            reasons.append('physical_envelope')
        if s['host_committed_bytes']-base.committed_max > profile.commit_peak_bytes:
            reasons.append('commit_envelope')
        for key, maximum, allowance in zip(operator_policy.GPU_FIELDS, base.gpu_max,
                (profile.gpu_peak_bytes, profile.shared_physical_allowance_bytes, profile.gpu_peak_bytes)):
            if s[key]-maximum > allowance:
                reasons.append('gpu_envelope:'+key)
        return reasons

    def admission_decision(self, profile, base, frame, *, now, now_utc):
        reasons = self._common(profile, base, frame, now, now_utc, operator_policy.MAX_PRELAUNCH_AGE_SECONDS)
        result = dict(allowed=False, reasons=reasons)
        if not reasons:
            result = admission._evaluate_admission(frame.snapshot, dict(profile.envelope),
                                                   now=now, source_commit=SOURCE_COMMIT)
            result['reasons'] = list(dict.fromkeys(result['reasons'] + self.frame_numeric_reasons(
                profile, base, frame, now=now, now_utc=now_utc)))
            result['allowed'] = not result['reasons']
        return result

    def admission_reasons(self, *args, **kwargs):
        return self.admission_decision(*args, **kwargs)['reasons']

    def runtime_decision(self, profile, base, frame, owned, *, now, now_utc):
        try:
            scoped = self.owned_inventory_frame(frame, owned)
        except ValueError:
            return dict(allowed=False, reasons=['owned_identity_unverified'])
        reasons = self.frame_numeric_reasons(profile, base, scoped, now=now, now_utc=now_utc)
        reasons += owned_sample_reasons(scoped.snapshot)
        return dict(allowed=not reasons, reasons=reasons,
                    owned_inventory_proof=scoped.snapshot['owned_inventory_proof'])


def source_paths():
    result = subprocess.run(['git', '-C', str(SOURCE), 'ls-files', '-z', '--cached',
        '--others', '--exclude-standard'], check=True, capture_output=True, timeout=10)
    return [SOURCE / name.decode('utf-8') for name in sorted(set(result.stdout.split(b'\0'))) if name]


def identity_inventory():
    """Read-only content identity, including uncommitted and untracked port files."""
    head = subprocess.run(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'],
                          check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    if head != SOURCE_COMMIT:
        raise ValueError('release_source_base_changed')
    diff = subprocess.check_output(['git', '-C', str(SOURCE), 'diff', '--no-ext-diff', '--binary'], timeout=10)
    if sha256(diff).hexdigest().upper() != BUILD_DIFF_SHA256:
        raise ValueError('release_source_diff_not_built')
    # Fixed receipt order avoids PowerShell 5/7 culture-sort differences.
    names = subprocess.check_output(['git', '-C', str(SOURCE), 'ls-files', '--others',
                                    '--exclude-standard'], timeout=10).decode().splitlines()
    if set(names) != set(BUILD_UNTRACKED_PATHS):
        raise ValueError('release_untracked_inventory_not_built')
    untracked = ''.join(name+'|'+operator_store.artifact_record(SOURCE/name)['sha256'].lower()+'\n'
                        for name in BUILD_UNTRACKED_PATHS)
    if sha256(untracked.encode()).hexdigest().upper() != BUILD_UNTRACKED_SHA256:
        raise ValueError('release_untracked_sources_not_built')
    runtime = operator_store.artifact_record(BUILD / 'runtime-manifest.json')
    if runtime['sha256'] != RUNTIME_MANIFEST_SHA256:
        raise ValueError('release_runtime_manifest_changed')
    payload = operator_store.read_json(BUILD / 'runtime-manifest.json')['files']
    expected_paths = {item['path'].replace('\\', '/') for item in payload} | {'runtime-manifest.json'}
    actual_paths = {p.relative_to(BUILD).as_posix() for p in BUILD.rglob('*') if p.is_file()}
    if len(expected_paths) != len(payload)+1 or actual_paths != expected_paths:
        raise ValueError('release_runtime_inventory_changed')
    records = [runtime]
    for item in payload:
        path = BUILD / item['path']
        if path.is_symlink() or not path.resolve().is_relative_to(BUILD.resolve()):
            raise ValueError('release_runtime_escape')
        record = operator_store.artifact_record(path)
        if (record['stamp'][1], record['sha256']) != (item['size_bytes'], item['sha256']):
            raise ValueError('release_runtime_payload_changed')
        if item['path'] == 'gufo.exe' and record['sha256'] != EXE_SHA256:
            raise ValueError('release_executable_changed')
        records.append(record)
    sources = source_paths()
    source_records = []
    for path in sources:
        if path.is_symlink() or not path.resolve().is_relative_to(SOURCE.resolve()):
            raise ValueError('release_source_escape')
        source_records.append(operator_store.artifact_record(path))
    records.extend(source_records)
    model = smoke_store.validate_ar4k_model(smoke_store.FIRST_SHARD)
    model_stamps = [operator_store.stamp(model.first_shard.parent/p.filename)
                    for p in smoke_store.AR4K_PINS.shards]
    controller_root = Path(__file__).resolve().parents[2]/'scripts/gufo_control'
    controller_paths = sorted(p for p in controller_root.iterdir() if p.suffix in ('.py', '.ps1', '.cs'))
    controller_paths += [Path(__file__).resolve()]
    controller_records = [operator_store.artifact_record(path) for path in controller_paths]
    records.extend(controller_records)
    for path, expected in ((PROBE, PROBE_SHA256), (PROBE.with_name('build-manifest.json'), PROBE_MANIFEST_SHA256)):
        record = operator_store.artifact_record(path)
        if record['sha256'] != expected:
            raise ValueError('release_probe_identity_changed')
        records.append(record)
    records.append(operator_store.artifact_record(Path(__file__).with_name('review_pin.py')))
    records.append(smoke_store._checked_artifact(smoke_store.PINS.host_openmp,
        smoke_store.PINS.host_openmp_pin, 'host_openmp'))
    identity = dict(source_base=head,
        source_tree_sha256=sha256(canonical(source_records).encode()).hexdigest().upper(),
        runtime_manifest_sha256=runtime['sha256'], executable_sha256=EXE_SHA256,
        model_revision=model.revision, model_stamps=model_stamps,
        controller_sha256=sha256(canonical(controller_records).encode()).hexdigest().upper(),
        probe_sha256=PROBE_SHA256, probe_build_sha256=PROBE_MANIFEST_SHA256)
    return dict(identity=identity, artifacts=records, runtime_paths=sorted(actual_paths),
                source_paths=[str(p) for p in sources], model_stamps=model_stamps)


class ReleaseStore:
    BUILD = BUILD
    EVIDENCE = EVIDENCE

    def verify_static(self):
        if QUALIFICATION_SHA256 is None:
            raise ValueError('independent_release_qualification_missing')
        q_record = operator_store.artifact_record(QUALIFICATION)
        if q_record['sha256'] != QUALIFICATION_SHA256:
            raise ValueError('release_qualification_changed')
        manifest = identity_inventory()
        q = operator_store.read_json(QUALIFICATION)
        validate_qualification(q, manifest['identity'])
        manifest.update(profile=PROFILE, qualification=q, qualification_stamp=q_record)
        self.recheck_static(manifest)
        return manifest

    def recheck_static(self, manifest, *, current_run=None):
        validate_qualification(manifest['qualification'], manifest['identity'])
        if operator_store.artifact_record(QUALIFICATION) != manifest['qualification_stamp']:
            raise ValueError('release_qualification_changed')
        if [str(p) for p in source_paths()] != manifest['source_paths']:
            raise ValueError('release_source_inventory_changed')
        if sorted(p.relative_to(BUILD).as_posix() for p in BUILD.rglob('*') if p.is_file()) != manifest['runtime_paths']:
            raise ValueError('release_runtime_inventory_changed')
        for record in manifest['artifacts']:
            path = Path(record['stamp'][0])
            if path.is_symlink() or operator_store.stamp(path) != record['stamp']:
                raise ValueError('release_artifact_changed')
        for stamp in manifest['model_stamps']:
            if operator_store.stamp(stamp[0]) != stamp:
                raise ValueError('release_model_changed')
        smoke_store.validate_ar4k_model(smoke_store.FIRST_SHARD)
        # Historical uncertainty still blocks this new attempt. Historical
        # success is never read or promoted as release correctness evidence.
        smoke_store._incomplete_latches(smoke_store.PINS)
        for name in ('attempt.json', 'incomplete.json'):
            path = EVIDENCE/name
            if current_run is None:
                if path.exists():
                    raise ValueError('prior_release_attempt_or_incomplete')
            elif operator_store.read_json(path).get('run') != str(current_run):
                raise ValueError('release_run_marker_mismatch')

    def load_original_operator_baseline(self):
        # The original sequence is a stricter numeric/recovery reference only.
        return smoke_store.load_original_operator_baseline()

    def begin_run(self, run_dir, manifest, baseline):
        self.recheck_static(manifest)
        if run_dir.resolve().parent != EVIDENCE.resolve() or not run_dir.is_dir():
            raise ValueError('release_run_directory')
        for name in ('attempt.json', 'incomplete.json'):
            with (EVIDENCE/name).open('x', encoding='utf-8') as stream:
                json.dump(dict(run=str(run_dir), profile=PROFILE), stream)
                stream.flush()
                os.fsync(stream.fileno())
        operator_store.atomic_json(run_dir/'manifest.json', manifest)

    def finish_run(self, run_dir, result):
        for name in ('attempt.json', 'incomplete.json'):
            if operator_store.read_json(EVIDENCE/name).get('run') != str(run_dir):
                raise ValueError('release_run_marker_mismatch')
        operator_store.atomic_json(run_dir/'result.json', result)
        # Keep every failed attempt latched, even if cleanup succeeded.
        if result.get('success') is True and result.get('cleanup_confirmed') is True:
            (EVIDENCE/'incomplete.json').unlink()


def make_guardian():
    guardian = smoke_guard._Guardian(store=ReleaseStore(), policy_module=ReleasePolicy(),
        profile_id=PROFILE, argv_builder=fixed_argv)
    latest = {}
    def request_validator(row, request):
        inspection = guardian.inspection.snapshot(now=time.monotonic()) if guardian.inspection else {}
        ready_evidence_check(latest, inspection, time.monotonic())
        if request != request_for(row):
            raise ValueError('release_request_changed')
    def http_start(**kwargs):
        return benchmark_suite.start_suite(profile_id=PROFILE, evidence_dir=guardian.run_dir,
            recipe_provider=sys.modules[__name__], response_assessor=assess,
            request_validator=request_validator, **kwargs)
    guardian.http_start = http_start
    seen_owned_counters = False
    def collect():
        nonlocal seen_owned_counters, latest
        request = None
        if guardian.child is not None and guardian.resumed_at is not None and not guardian.exited:
            request = dict(guardian.child.verify_live_identity(), adapter_luid=guardian.current.identity[0])
        if operator_store.artifact_record(PROBE)['sha256'] != PROBE_SHA256:
            raise ValueError('release_probe_changed')
        snapshot = collect_snapshot(owned=request, probe_executable=PROBE)
        if request is not None:
            counters = snapshot.get('owned_counters', {})
            seen_owned_counters |= counters.get('available') is True
            snapshot['release_owned_requested'] = True
            snapshot['release_owned_required'] = seen_owned_counters
        latest = deepcopy(snapshot)
        return snapshot
    guardian.collect = collect
    return guardian


def owned_sample_reasons(snapshot):
    if not snapshot.get('release_owned_requested') and not snapshot.get('release_owned_required'):
        return []  # Initial suspended-child sample, still bounded by aggregate age.
    counters = snapshot.get('owned_counters', {})
    if counters.get('available') is True:
        return []  # The existing telemetry parser authenticated all fields and times.
    if not snapshot.get('release_owned_required') and counters.get('reason') == 'owned_instance_missing':
        return []  # Explicit unknown before WDDM registers a per-process instance.
    return ['release_owned_counters_unavailable']


def ready_evidence_check(snapshot, inspection, now):
    if (snapshot.get('owned_counters', {}).get('available') is not True or
            not 0 <= now-snapshot.get('captured_monotonic', float('-inf')) <= 5):
        raise ValueError('release_owned_counters_not_ready')
    if inspection.get('status') != 'verified':
        raise ValueError('release_module_inspection_not_ready')
    expected = {name.lower(): ntpath.normcase(str(BUILD/name))
                for name in (*smoke_store.SDK_DLLS, *smoke_store.VCPKG_DLLS)}
    expected['libomp140.x86_64.dll'] = ntpath.normcase(str(smoke_store.PINS.host_openmp))
    for path in inspection.get('modules', []):
        name = ntpath.basename(path).lower()
        if name in expected and ntpath.normcase(path) != expected[name]:
            raise ValueError('release_runtime_module_outside_closure')


def main(argv=None):
    parser = argparse.ArgumentParser(description='One private release AR4K smoke')
    parser.add_argument('command', choices=('identity', 'print-only', 'run'))
    args = parser.parse_args(argv)
    try:
        if args.command == 'identity':
            print(canonical(identity_inventory()['identity']))
            return 0
        if args.command == 'print-only':
            manifest = ReleaseStore().verify_static()
            print(canonical(dict(profile=PROFILE, argv=fixed_argv('[REDACTED]'),
                identity=manifest['identity'], admitted=False)))
            return 0
        if os.name != 'nt':
            raise ValueError('Windows_required')
        result = make_guardian().run()
        print(canonical(result))
        return 0 if result['success'] else 2
    except Exception as error:
        print(canonical(dict(profile=PROFILE, admitted=False,
            refused=type(error).__name__+':'+str(error))))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
