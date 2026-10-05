"""Offline per-instance GPU counter summaries from retained cohort artifacts.

No provider, process inventory, engine, or network calls. Counter instances are
kept separate; no sum across engines is computed. A strict request interior
means the entire counter acquisition QPC bracket lies inside one request's
Windows QPC calibration bracket. Cooked values are retained without clamping.
"""
import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import statistics


SAMPLE = 'halogen.windows-gpu-engine-sample.v1'
HEADER = 'halogen.windows-gpu-engine-header.v1'
TERMINAL = 'halogen.windows-gpu-engine-terminal.v1'
INSTANCE = re.compile(r'^pid_(\d+)_luid_(0x[0-9a-f]+_0x[0-9a-f]+)_phys_(\d+)_eng_(\d+)_engtype_(.+)$')
PATH_INSTANCE = re.compile(r'\\gpu engine\(([^)]+)\)\\utilization percentage$')


def require(value, message):
    if not value:
        raise ValueError(message)


def metadata(path):
    raw = path.read_bytes()
    require(len(raw) <= 2 * 1024**2, 'Metadata exceeds 2 MiB: ' + str(path))
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def distribution(values):
    require(bool(values), 'Nonempty distribution required')
    return dict(count=len(values), minimum=min(values), mean=statistics.fmean(values),
                median=statistics.median(values), maximum=max(values))


def analyze(directory):
    raw_path = directory / 'gpu-counters.jsonl'
    coverage, coverage_sha = metadata(directory / 'gpu-counter-coverage.json')
    measurement, measurement_sha = metadata(directory / 'measurement.json')
    records, digest, byte_count = [], hashlib.sha256(), 0
    with raw_path.open('rb') as stream:
        while line := stream.readline(8 * 1024**2 + 1):
            require(len(line) <= 8 * 1024**2 and line.endswith(b'\n'), 'Incomplete/oversized retained JSONL record')
            digest.update(line)
            byte_count += len(line)
            require(byte_count <= 256 * 1024**2, 'Raw evidence exceeds 256 MiB')
            records.append(json.loads(line))
    headers = [row for row in records if row['schema'] == HEADER]
    terminals = [row for row in records if row['schema'] == TERMINAL]
    samples = [row for row in records if row['schema'] == SAMPLE]
    require(len(headers) == len(terminals) == 1 and len(records) == len(samples) + 2, 'Unexpected raw record schemas')
    require(records[0]['schema'] == HEADER and records[-1]['schema'] == TERMINAL, 'Header/terminal ordering differs')
    header, terminal = headers[0], terminals[0]
    require(coverage['passed'] is True and digest.hexdigest() == coverage['raw_sha256'] and
            byte_count == coverage['raw_bytes'], 'Coverage/raw seal differs')
    require(terminal == coverage['terminal'] and terminal['reason'] == 'stopfile' and
            terminal['exit_code'] == 0 and terminal['samples_written'] == len(samples) == coverage['sample_count'],
            'Retained collector terminal differs')
    require(header['source_sha256'] == coverage['source_sha256'] and
            header['logger_pid'] == coverage['windows_identity']['pid'] == coverage['ready']['logger_pid'],
            'Retained collector source/owner differs')
    require([row['sample_index'] for row in samples] == list(range(len(samples))), 'Sample indices differ')
    boundaries = [dict(index=row['index'], phase=row['phase'],
                       before=row['clock_calibration']['before']['qpc'],
                       after=row['clock_calibration']['after']['qpc']) for row in measurement['samples']]
    require(boundaries == coverage['request_qpc_boundaries'], 'Request/coverage QPC boundaries differ')
    require([row['index'] for row in boundaries] == list(range(4)) and
            [row['phase'] for row in boundaries] == ['warmup', 'measured', 'measured', 'measured'],
            'Frozen request geometry differs')
    identities = {row['pid']: row for sample in samples for row in sample['first_seen_processes']}
    series = defaultdict(lambda: defaultdict(list))
    instance_metadata = {}
    request_counts = {row['index']: dict(interior=0, overlapping=0) for row in boundaries}
    invalid = nonfinite = query_errors = above_100 = negative = duplicate_name_extra_rows = 0
    query_seconds, cadence_seconds, between_query_seconds, timestamp_lag_seconds, native_time_offsets = [], [], [], [], []
    types, adapters, row_counts = set(), set(), []
    previous_end = previous_start = None
    for sample in samples:
        require(sample['qpc_frequency'] == header['qpc_frequency'] and sample['qpc_frequency'] > 0,
                'QPC frequency changed')
        start = sample['qpc_start'] / sample['qpc_frequency']
        end = sample['qpc_end'] / sample['qpc_frequency']
        require(start <= end and (previous_end is None or start >= previous_end), 'QPC brackets overlap/regress')
        query_seconds.append(end - start)
        if previous_start is not None:
            cadence_seconds.append(start - previous_start)
            between_query_seconds.append(start - previous_end)
        previous_start, previous_end = start, end
        request = next((row for row in boundaries if row['before'] <= start and end <= row['after']), None)
        for row in boundaries:
            if start < row['after'] and end > row['before']:
                request_counts[row['index']]['overlapping'] += 1
        if request:
            request_counts[request['index']]['interior'] += 1
        scopes = ['all']
        if request:
            scopes += ['request_' + str(request['index'])]
            if request['phase'] == 'measured':
                scopes += ['measured_interior']
        query_errors += len(sample['counter_query_errors'])
        row_counts.append(len(sample['counters']))
        unique, base_names = set(), set()
        for counter in sample['counters']:
            # PDH InstanceName strips duplicate suffixes such as #1. Preserve
            # the full path so distinct VM instances are never averaged together.
            key = counter['path']
            require(key not in unique, 'Duplicate full counter path within sample')
            unique.add(key)
            duplicate_name_extra_rows += counter['instance_name'] in base_names
            base_names.add(counter['instance_name'])
            matched = INSTANCE.fullmatch(counter['instance_name'])
            require(matched and int(matched[1]) == counter['pid'], 'Unparsed GPU instance/PID')
            path_match = PATH_INSTANCE.search(key)
            require(path_match, 'Unparsed GPU counter path')
            path_name, separator, duplicate_index = path_match[1].rpartition('#')
            if not separator:
                path_name, duplicate_index = path_match[1], None
            require(path_name == counter['instance_name'] and
                    (duplicate_index is None or duplicate_index.isdigit()), 'Path/instance mismatch')
            instance_metadata[key] = (matched, duplicate_index)
            adapters.add(matched[2] + '/phys_' + matched[3])
            types.add(counter['counter_type'])
            if counter['status'] != 0:
                invalid += 1
                continue
            value = counter['cooked_value']
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                nonfinite += 1
                continue
            above_100 += value > 100
            negative += value < 0
            for scope in scopes:
                series[key][scope].append(value)
        native_times = {int(counter['timestamp_100nsec']) for counter in sample['counters']}
        require(len(native_times) == 1, 'Multiple PDH timestamps within one sample')
        # Preserve an empirical check rather than treating Timestamp100NSec as
        # proven UTC: these artifacts expose a local-time-sized numeric offset.
        native_epoch_ns = (next(iter(native_times)) - 116444736000000000) * 100
        utc_times = {datetime.fromisoformat(counter['timestamp_utc'].replace('Z', '+00:00')).timestamp()
                     for counter in sample['counters']}
        require(len(utc_times) == 1, 'Multiple retained UTC PDH timestamps within one sample')
        utc_timestamp = next(iter(utc_times))
        timestamp_lag_seconds.append(sample['epoch_ns_end'] / 1e9 - utc_timestamp)
        native_time_offsets.append(native_epoch_ns / 1e9 - utc_timestamp)
    require(invalid == coverage['total_invalid_counter_rows'] and query_errors == coverage['total_query_errors'],
            'Coverage error counts differ')
    ready = coverage['ready']
    require(ready['first_sample_qpc_end'] / ready['qpc_frequency'] <= boundaries[0]['before'],
            'Readiness misses first warmup boundary')
    after = [sample for sample in samples if sample['qpc_start'] / sample['qpc_frequency'] >= boundaries[-1]['after']]
    require(bool(after), 'No post-response acquisition bracket')
    instances = []
    for key, scopes in series.items():
        matched, duplicate_index = instance_metadata[key]
        process = identities[int(matched[1])]
        instances.append(dict(path=key, instance=matched[0], duplicate_index=duplicate_index,
            pid=int(matched[1]), name=process['name'],
            identity_valid=process['identity_valid'], adapter=matched[2], physical_engine=int(matched[3]),
            engine=int(matched[4]), engine_type=matched[5],
            scopes={name: dict(distribution(values), positive_samples=sum(value > 0 for value in values),
                               above_100_samples=sum(value > 100 for value in values)) for name, values in scopes.items()}))
    # Drop fully zero series from the compact output; their count remains visible.
    active_instances = sorted([row for row in instances if row['scopes']['all']['maximum'] > 0],
                              key=lambda row: row['scopes'].get('measured_interior', row['scopes']['all'])['maximum'],
                              reverse=True)
    return dict(name=measurement['name'], directory=str(directory), raw_sha256=digest.hexdigest(),
        raw_bytes=byte_count, coverage_sha256=coverage_sha, measurement_sha256=measurement_sha,
        sample_count=len(samples), row_count=sum(row_counts), row_counts=distribution(row_counts),
        invalid_rows=invalid, nonfinite_rows=nonfinite, query_errors=query_errors,
        duplicate_instance_name_extra_rows=duplicate_name_extra_rows,
        above_100_rows=above_100, negative_rows=negative, counter_types=sorted(types),
        adapters=sorted(adapters), process_count=len(identities),
        process_identity_invalid=[dict(pid=pid, name=row['name'], errors=row['errors'])
                                  for pid, row in identities.items() if not row['identity_valid']],
        nonzero_instance_count=len(active_instances), zero_instance_count=len(instances)-len(active_instances),
        query_seconds=distribution(query_seconds), sample_start_cadence_seconds=distribution(cadence_seconds),
        between_query_seconds=distribution(between_query_seconds),
        retained_utc_timestamp_before_query_end_seconds=distribution(timestamp_lag_seconds),
        timestamp_100nsec_naive_utc_minus_retained_utc_seconds=distribution(native_time_offsets),
        ready_lead_seconds=boundaries[0]['before'] - ready['first_sample_qpc_end']/ready['qpc_frequency'],
        first_post_response_query_lead_seconds=after[0]['qpc_start']/after[0]['qpc_frequency'] - boundaries[-1]['after'],
        request_counts=request_counts, boundaries=boundaries,
        measured=dict(prefill_tps=measurement['prefill_tps'], decode_tps=measurement['decode_tps'],
            accepted=measurement['accepted'], drafted=measurement['drafted'],
            output_sha256=measurement['output_sha256'], request_sha256=measurement['request_sha256']),
        active_instances=active_instances)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('windows', type=Path, nargs='+', help='Completed window artifact directories')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    require(1 <= len(args.windows) <= 3, 'One to three completed windows required')
    result = dict(schema='halogen.gpu-counter-cohort-offline-analysis.v1',
        analysis_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        statistic='Unweighted arithmetic mean of recorded valid per-instance cooked values; engines are never summed',
        request_selection='Counter acquisition QPC bracket fully inside request QPC calibration bracket',
        hardware_provider_process_inventory_network_calls=0, windows=[analyze(path) for path in args.windows])
    text = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if args.output:
        with args.output.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
