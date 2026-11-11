"""Freeze the fresh source-only NPU cohort; Root seals only after review."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(r'C:\Projects\strix-alloy-clean')
HERE = Path(__file__).resolve().parent
PRIMARY = HERE.parent
OLD = ROOT / 'server/.local/halogen-update-20261110/primary0201'
ORIGINAL = OLD / 'stateful1012-core-append-v1/bindings-root-executed-v1.json'


def pin(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def prepare(output):
    if output.exists(): raise FileExistsError('Preserve existing binding')
    old = json.loads(ORIGINAL.read_bytes())
    transition_path = HERE / 'overlay-v2/transition.json'
    transition = json.loads(transition_path.read_bytes())
    producer = old['producer']
    producer['service'] = str(HERE / 'producer/service_request_scoped_v4.py')
    producer['terminal_schema'] = 'halogen0202.stateful1012-request-scoped-producer-process.v4'
    paths = [transition_path, HERE / 'cohort_campaign_core_append_v1.py',
             HERE / 'measure_helpers.py', HERE / 'prepare_overlay.py', Path(__file__)]
    for directory in ('cohort', 'producer', 'api', 'raw/collector', 'raw/observer', 'consumer-native'):
        paths += [p for p in (HERE / directory).iterdir()
                  if p.is_file() and p.suffix in ('.py', '.h', '.hpp', '.c', '.cpp', '.S', '.json', '.map', '.sh')]
    for section in ('candidate', 'rollback'):
        paths += [p for p in (HERE / 'overlay-v2' / section).rglob('*') if p.is_file()]
    paths += [Path(row['path']) for row in producer['required_modules'].values()]
    paths += [PRIMARY / 'serving0202-text32k-8192.json',
        PRIMARY / 'npu-consumer-seam-v1/native-contract.json',
        PRIMARY / 'npu-consumer-seam-v1/raw-binding.json',
        HERE / 'root-cpu-build-v2/libhgn0202-stream.so',
        HERE / 'raw/observer/libhgn0202_raw_side.so']
    # These unchanged files provide generic owned lifecycle, logging, cleanup,
    # module enumeration and native MTP log accounting, never old ELF hooks.
    retained = [OLD / name for name in (
        'prefill4096-cohort-prep/root_campaign.py',
        'prefill4096-cohort-prep/coordinator_skeleton.py',
        'prefill8192-cohort-prep-v2/mtp_trace.py',
        'prefill8192-cohort-prep-v2/gpu_admission.py',
        'cost-cohort-prep-v5/await_owned.py',
        'oracle-cohort-prep/oracle_campaign.py',
        'oracle-cohort-prep/oracle_evidence.py',
        'oracle-cohort-prep/oracle_trace.py',
        'stateful1012-prep/run_owned_stateful.py')]
    paths += retained
    indexed = {str(p.resolve()): pin(p) for p in paths}
    base = '/candidate/libhgn0202_raw_side.so:/candidate/libhalogen0202-v2-preflight.so:/candidate/hip-register-private-rw.so'
    cfg_sha = pin(HERE / 'overlay-v2/candidate/profiles/hdo2-qualified.json')['sha256']
    environment = {}
    for arm in ('before', 'candidate', 'after'):
        env = {key.replace('0201', '0202'): value.replace('0201', '0202')
               for key, value in old['native_environment'][arm].items()}
        env['HGN0202_STREAM_CONFIG_SHA256'] = cfg_sha
        env['LD_PRELOAD'] = ('/candidate/libhgn0202-stream.so:' if arm == 'candidate' else '') + base
        environment[arm] = env
    value = dict(schema='halogen0202.real-NPU-cohort-bindings.v1', root_sealed=False,
        source_freeze_complete=True, oracle_future_IDs=False, real_NPU_prediction=True,
        transition=str(transition_path), pins=list(indexed.values()), producer=producer,
        native_environment=environment, retained_generic_framework=[pin(p) for p in retained],
        original_qualified_NPU_binding=pin(ORIGINAL),
        artifacts=[dict(target='.local/libhgn0202-stream.so', source=pin(HERE / 'root-cpu-build-v2/libhgn0202-stream.so')['path']),
                   dict(target='.local/libhgn0202_raw_side.so', source=pin(HERE / 'raw/observer/libhgn0202_raw_side.so')['path'])],
        normal_source_manifest=transition['normal_source_manifest'],
        acceptance_denominator_policy='Report native head and HDO2 separately;0/0 is undefined',
        NPU_phase_metrics='Report producer seed/prefill/catchup/READY timing separately from measured GPU native RAW and HTTP QPC')
    output.write_text(json.dumps(value, indent=2) + '\n')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--output', type=Path, default=HERE / 'bindings-prepared-v1.json')
    args = parser.parse_args()
    if not args.prepare:
        print(json.dumps(dict(source_only=True, hardware=False, root_sealed=False)))
        return 0
    result = prepare(args.output)
    print(json.dumps(dict(binding=pin(args.output), pins=len(result['pins']), root_sealed=False)))
    return 0


if __name__ == '__main__': raise SystemExit(main())
