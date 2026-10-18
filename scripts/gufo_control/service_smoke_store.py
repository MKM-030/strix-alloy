"""Closed candidate identity adapter; no qualification is ever created here."""
from copy import deepcopy
from dataclasses import replace
import subprocess

from . import operator_store, runtime_package, smoke_store, smoke_http
from .benchmark_runtime import BoundStore

PROFILE_ID = smoke_store.SERVICE_SMOKE
SOURCE_TREE = '273d84974a604c81023dae15d379a9bfc0b1c29b'
RUNTIME_VARIANT = 'service-ar4k-v1'
RUNTIME_POLICY_SHA256 = '5AA64C7E718619E4654DCF4B5997D77AAE47B41611DCAA897020224FD0F0A5E8'
PINS = replace(smoke_store.PINS, profile_id=PROFILE_ID,
    source=smoke_store.ROOT/'engine/gufo-ar4k-service',
    source_commit='139aa9c58dadcb75c1bd0741aad0823fc65a0547',
    operator_source_commit=operator_store.SOURCE_COMMIT,
    build=smoke_store.ROOT/'runtimes/gufo-native-service-139aa9c-therock10.2',
    executable=(42439168, '66798D3BCAD27B7E2BEC16980B225F83CC3F017FAD9088ADA8D64D604BC4F209'),
    evidence=smoke_store.ROOT/'reports/gufo-service-policy-smoke-v1-runs',
    qualification=smoke_store.ROOT/'reports/gufo-service-policy-smoke-v1-qualification.json',
    margin_report=smoke_store.ROOT/'reports/gufo-service-policy-margin-delta-review-20260927.md',
    margin_sha256='857FDC17EBABD7717E0274661C3FD190DBA2C8910C279845DE32F331F842CBC8')


def fixed_argv(secret):
    p = PINS
    return [str(p.build/p.executable_name), 'serve', '--host', '127.0.0.1',
        '--port', '8836', '--sessions', '1', '--max-connections', '3',
        '--max-request-bytes', '16384', '--api-key', secret, 'llm', '--model',
        str(p.first_shard), '--served-model-name', 'gufo-flash-next', '--context',
        '4096', '--max-tokens', '64', '--think', 'off', '--speculative', 'off',
        '--max-pending', '1', '--max-pending-per-client', '1',
        '--request-timeout-ms', '60000', '--max-output-bytes', '1048576',
        '--request-policy', 'ar4k-service-v1', '--preserve-thinking', 'off']


def service_binding(pins):
    if pins != PINS or any(type(pins.bounds[k]) is not int for k in PINS.bounds):
        raise ValueError('service_identity_invalid')
    return {'service': dict(source_tree=SOURCE_TREE, source_path=str(pins.source),
        operator_source=pins.operator_source_commit, runtime_path=str(pins.build),
        runtime_variant=RUNTIME_VARIANT, runtime_policy_sha256=RUNTIME_POLICY_SHA256,
        workload=dict(argv=fixed_argv('[PRIVATE-PER-RUN]'), request=deepcopy(smoke_http.REQUEST),
            max_prompt_tokens=512, max_output_tokens=64, context_tokens=4096,
            max_ready_polls=240, model_queries=1, generation_posts=1,
            startup_seconds=480, request_seconds=60, lifetime_seconds=600,
            cleanup_seconds=10, recovery_seconds=60, recovery_samples=5,
            sessions=1, pending=1, pending_per_client=1, sole_client=True,
            private_per_run_key=True, max_connections=3, max_request_bytes=16384,
            max_response_bytes=1048576, mtp=False, sidecar=False, lookup=False,
            vision=False, thinking=False, preserve_thinking=False, effort=False,
            cache_lookup=False, disk_cache=False))}


def source_identity():
    def git(*args):
        result = subprocess.run(['git', '-C', str(PINS.source), *args],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise ValueError('source_identity_unavailable')
        return result.stdout.strip()
    if (git('rev-parse', 'HEAD') != PINS.source_commit
            or git('rev-parse', 'HEAD^{tree}') != SOURCE_TREE
            or git('status', '--porcelain')):
        raise ValueError('source_identity_changed')


class ServiceStore(BoundStore):
    def __init__(self):
        super().__init__(PINS)

    def verify_static(self):
        package = runtime_package.verify_runtime(self.BUILD, variant=RUNTIME_VARIANT)
        result = smoke_store._verify_static(self.PINS, source_validator=source_identity,
                                           model_validator=smoke_store.validate_ar4k_model)
        result['runtime_package'] = package
        result['runtime_manifest'] = operator_store.artifact_record(self.BUILD/'runtime-manifest.json')
        return result

    def recheck_static(self, manifest, *, current_run=None):
        package = runtime_package.verify_runtime(self.BUILD, variant=RUNTIME_VARIANT)
        if (package != manifest.get('runtime_package') or
                operator_store.artifact_record(self.BUILD/'runtime-manifest.json') !=
                manifest.get('runtime_manifest')):
            raise ValueError('service_runtime_changed')
        smoke_store._recheck_static(manifest, self.PINS, source_validator=source_identity,
                                   current_run=current_run)
