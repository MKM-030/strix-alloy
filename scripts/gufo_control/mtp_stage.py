"""One fixed, private native MTP correctness request; imports never execute it."""
import argparse
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import os

from . import (benchmark_guard, benchmark_recipes, operator_store, smoke_guard,
               smoke_http, smoke_store)
from .benchmark_runtime import BoundPolicy, BoundStore
from .model_identity import MTP_SIDECAR
from .mtp_stage_http import start_stage


PROFILE_ID = smoke_store.MTP_4K
SIDECAR = MTP_SIDECAR.path
PROMPT = ('Answer in two lines, without Markdown. EN: Explain in one short sentence '
          'how a backup helps after accidental file deletion. DE: Explain the same '
          'in one short German sentence.')
RENDERED = '<|im_start|>user\n' + PROMPT + '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
RENDERED_BYTES = 243
REVIEWED_SOURCE = 'cff564964e8506c0abb3e530cecb55332187ac6c'


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def request_fixture():
    request = deepcopy(smoke_http.REQUEST)
    request['messages'] = [{'role': 'user', 'content': PROMPT}]
    return request


_FIXTURE = request_fixture()
_BODY = _canonical(_FIXTURE)


def validate_request(request):
    """Exact type, content, and source-proven rendered-byte check before prefill."""
    def exact(actual, expected):
        if type(actual) is not type(expected):
            return False
        if isinstance(expected, dict):
            return actual.keys() == expected.keys() and all(
                exact(actual[key], value) for key, value in expected.items())
        if isinstance(expected, list):
            return len(actual) == len(expected) and all(
                exact(item, value) for item, value in zip(actual, expected))
        return actual == expected

    if not exact(request, _FIXTURE):
        raise ValueError('mtp_request_mismatch')
    rendered = '<|im_start|>user\n' + request['messages'][0]['content'] + (
        '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n')
    if (rendered != RENDERED or not rendered.isascii()
            or len(rendered.encode('utf-8')) != RENDERED_BYTES
            or RENDERED_BYTES > 512 or request['max_tokens'] != 64):
        raise ValueError('mtp_rendered_input_mismatch')
    return RENDERED_BYTES


def experiment_definition():
    return dict(profile_id=PROFILE_ID,
        recipe_sha256=recipe_sha256(), context_tokens=4096, max_prompt_tokens=512,
        max_output_tokens=64, max_requests=1, sessions=1, max_connections=16,
        max_request_bytes=262144, max_response_bytes=1048576,
        request_seconds=60, startup_seconds=480, lifetime_seconds=600,
        speculative=True, disk_cache=False, draft_tokens=1, min_draft_tokens=1,
        mtp_policy='length', mtp_draft_vocab='full')


def recipe_definition():
    validate_request(_FIXTURE)
    return dict(request=deepcopy(_FIXTURE), request_canonical=_BODY,
        request_sha256=sha256(_BODY.encode('utf-8')).hexdigest().upper(),
        rendered_input=RENDERED, rendered_input_bytes=RENDERED_BYTES,
        rendered_token_upper_bound=RENDERED_BYTES, source_commit=REVIEWED_SOURCE,
        model_revision=smoke_store.AR4K_PINS.revision,
        sidecar_descriptor_sha256=MTP_SIDECAR.descriptor_sha256,
        semantic_approval='independent_review_required')


def recipe_sha256():
    return sha256(_canonical(recipe_definition()).encode('utf-8')).hexdigest().upper()


def profile_pins():
    parent = benchmark_guard.profile_pins(benchmark_recipes.PROFILE_16K)
    if parent.predecessors[0].result_sha256 != smoke_store.MTP_PREDECESSOR_SHA256:
        raise ValueError('mtp_predecessor_identity_invalid')
    reports = smoke_store.ROOT / 'reports'
    return replace(parent, profile_id=PROFILE_ID,
        evidence=reports/'gufo-mtp4k-stage-v1-runs',
        qualification=reports/'gufo-mtp4k-stage-v1-qualification.json',
        margin_report=reports/'gufo-mtp4k-staged-envelope-review-20260926.md',
        margin_sha256=smoke_store.MTP_MARGIN_SHA256,
        bounds=dict(smoke_store.MTP_BOUNDS), sidecar=MTP_SIDECAR,
        experiment_json=_canonical(experiment_definition()))


def build_argv(secret):
    argv = smoke_guard.fixed_argv(secret)
    for flag, value in (('--context', '4096'), ('--sessions', '1'),
                        ('--max-tokens', '64'), ('--max-connections', '16'),
                        ('--max-request-bytes', '262144'), ('--speculative', 'mtp')):
        argv[argv.index(flag)+1] = value
    argv.extend(['--mtp-model', str(SIDECAR), '--draft-tokens', '1',
                 '--min-draft-tokens', '1', '--mtp-policy', 'length',
                 '--mtp-draft-vocab', 'full'])
    return argv


def make_guardian():
    validate_request(request_fixture())
    pins = profile_pins()
    guardian = smoke_guard._Guardian(store=BoundStore(pins), policy_module=BoundPolicy(pins),
        profile_id=PROFILE_ID, argv_builder=build_argv)

    def http_start(**kwargs):
        if guardian.run_dir is None:
            raise ValueError('guardian_run_dir_missing')
        return start_stage(evidence_dir=guardian.run_dir, **kwargs)

    guardian.http_start = http_start
    return guardian


def status(*, print_only=False):
    result = dict(profile=PROFILE_ID, admitted=False,
        admission='requires_fresh_run_baseline', argv=build_argv('[REDACTED]'),
        bounds=dict(smoke_store.MTP_BOUNDS), recipe=recipe_definition())
    try:
        pins = profile_pins()
        result['experiment'] = json.loads(pins.experiment_json)
        for name in ('attempt.json', 'incomplete.json'):
            path = pins.evidence/name
            result[name] = dict(present=path.exists())
        if print_only:
            BoundStore(pins).verify_static()
            operator_store.child_environment(dict(os.environ))
            smoke_guard.check_port()
            result['static_qualified'] = True
    except Exception as error:
        result.update(static_qualified=False, refused=type(error).__name__+':'+str(error))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Fixed one-request native MTP correctness stage')
    parser.add_argument('command', choices=('status', 'print-only', 'run'))
    args = parser.parse_args(argv)
    if args.command == 'run':
        if os.name != 'nt':
            parser.error('Windows required')
        try:
            result = make_guardian().run()
            code = 0 if result['success'] else 2 if result['resumed_monotonic'] is None else 1
        except Exception as error:
            result = dict(profile=PROFILE_ID, success=False,
                          refused=type(error).__name__+':'+str(error))
            code = 2
    else:
        result = status(print_only=args.command == 'print-only')
        code = 2 if result.get('static_qualified') is False else 0
    print(json.dumps(result, allow_nan=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
