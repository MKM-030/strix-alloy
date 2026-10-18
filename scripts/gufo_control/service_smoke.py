"""One finite foreground service-policy smoke. Only run can create owned work."""
import argparse
import json
import os

from . import operator_store, smoke_guard
from .benchmark_runtime import BoundPolicy
from .service_smoke_store import PINS, PROFILE_ID, ServiceStore, fixed_argv


def status(*, print_only=False):
    result = dict(profile=PROFILE_ID, argv=fixed_argv('[REDACTED]'),
        bounds=dict(PINS.bounds), source=PINS.source_commit,
        operator_source=PINS.operator_source_commit, model_revision=PINS.model_revision,
        admitted=False, admission='requires_fresh_run_baseline',
        runtime_qualified=False, persistent_service_qualified=False)
    for filename in ('attempt.json', 'incomplete.json'):
        result[filename] = dict(present=(PINS.evidence/filename).exists())
    if print_only:
        try:
            ServiceStore().verify_static()
            operator_store.child_environment(dict(os.environ))
            smoke_guard.check_port()
            result['static_qualified'] = True
        except Exception as error:
            result['static_qualified'] = False
            result['refused'] = type(error).__name__+':'+str(error)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Fixed one-attempt service-policy AR4k smoke')
    parser.add_argument('command', choices=('run', 'status', 'print-only'))
    args = parser.parse_args(argv)
    if args.command != 'run':
        result = status(print_only=args.command == 'print-only')
        print(json.dumps(result, allow_nan=False))
        return 2 if result.get('static_qualified') is False else 0
    if os.name != 'nt': parser.error('Windows required')
    result = smoke_guard._Guardian(store=ServiceStore(), policy_module=BoundPolicy(PINS),
        argv_builder=fixed_argv, profile_id=PROFILE_ID).run()
    print(json.dumps(result, allow_nan=False))
    return 0 if result['success'] else 2 if result['resumed_monotonic'] is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
