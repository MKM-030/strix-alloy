"""CPU-only analysis of the durable direct HIP observer; raw inputs stay untouched."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import sys


HERE = Path(__file__).resolve().parent
BASE_ANALYZER = HERE / "analyze_host_calls.py"
spec = importlib.util.spec_from_file_location("hip_host_coverage_cpu", BASE_ANALYZER)
coverage = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = coverage
spec.loader.exec_module(coverage)
CLOCK = coverage.CLOCK
COPY_SITES = (0x17BD966, 0x17BD98A, 0x17BD9B3, 0x17BD9DC)
OBSERVER_SOURCE = HERE / "host_census.c"
HEADER = struct.Struct("<8sIIIIQQIIQQ")
WIRE_RECORD = struct.Struct("<10QiiII")
UINT64_MAX = (1 << 64) - 1
MAX_BYTES = 64 * 1024 * 1024
API_NAMES = {1: "hipMemcpy", 2: "hipMemcpyAsync", 3: "hipDeviceSynchronize",
             4: "hipStreamSynchronize", 5: "hipModuleLaunchKernel", 6: "hipLaunchKernel"}
DIRECTIONS = {0: "H2H", 1: "H2D", 2: "D2H", 3: "D2D", 4: "Default", 1024: "D2DNoCU"}


@dataclass(frozen=True, slots=True)
class Record:
    sequence: int
    function: str
    process: int
    thread: int
    start: int
    end: int
    caller: int | None
    caller_offset: int | None
    image_base: int | None
    copy_bytes: int | None
    direction: int | None
    result: int
    source_address: int
    destination_address: int
    stream: int
    kernel_function: int
    flags: int

    def call(self):
        return coverage.Call(self.function, self.process, self.thread, self.start, self.end)


def parse_trace(path: Path) -> tuple[list[Record], dict]:
    receipt = {"source": coverage.source_ref(path), "layout_valid": False,
               "valid_records": 0, "invalid_records": 0, "invalid_examples": [],
               "integrity_issues": [], "observer_source": coverage.source_ref(OBSERVER_SOURCE)}
    if not path.is_file():
        receipt["parse_error"] = "Trace was not exported or is missing; unavailable is not zero calls."
        return [], receipt
    if path.stat().st_size > MAX_BYTES:
        receipt["parse_error"] = "Trace exceeds observer's sealed 64 MiB cap; refusing unsupported layout."
        return [], receipt
    raw = path.read_bytes()
    receipt["source"].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    if len(raw) < HEADER.size:
        receipt["parse_error"] = f"Partial header: {len(raw)} bytes; expected {HEADER.size}."
        return [], receipt
    (magic, version, header_size, record_size, clock_id, main_base, max_file_bytes,
     pid, reserved32, flags, reserved64) = HEADER.unpack_from(raw)
    receipt["header"] = {"magic_hex": magic.hex(), "version": version, "header_size": header_size,
                         "record_size": record_size, "clock_id": clock_id,
                         "clock_domain": CLOCK if clock_id == 7 else None,
                         "main_load_base": f"0x{main_base:x}", "main_load_base_zero_is_valid": True,
                         "max_file_bytes": max_file_bytes, "pid": pid,
                         "reserved32": reserved32, "flags": flags, "reserved64": reserved64}
    if (magic != b"HGHC0172" or version != 1 or header_size != HEADER.size or
            record_size != WIRE_RECORD.size or clock_id != 7 or flags != 7 or
            max_file_bytes != MAX_BYTES or pid < 1 or reserved32 != 0 or reserved64 != 0):
        receipt["parse_error"] = "Header does not match the sealed little-endian version1, BOOTTIME, validated-main, locked-sequence schema."
        return [], receipt
    receipt["layout_valid"] = True
    payload_bytes = len(raw) - HEADER.size
    full_records, tail = divmod(payload_bytes, WIRE_RECORD.size)
    receipt.update(record_payload_bytes=payload_bytes, full_records_in_file=full_records,
                   trailing_partial_record_bytes=tail, footer_present=False,
                   file_at_declared_cap=len(raw) == max_file_bytes,
                   live_snapshot_completeness_established=False)
    if tail:
        receipt["integrity_issues"].append(f"Trailing partial record: {tail} bytes retained in raw file.")
    if len(raw) == max_file_bytes:
        receipt["integrity_issues"].append("Declared observer cap reached; collection may have stopped silently.")
    records, sequences = [], []
    sequence_mismatches = []
    for index in range(full_records):
        (sequence, start, end, caller_rva, tid, size_bytes, src, dst, stream,
         kernel_function, result, direction, api, record_flags) = WIRE_RECORD.unpack_from(
             raw, HEADER.size + index * WIRE_RECORD.size)
        sequences.append(sequence)
        if sequence != index + 1 and len(sequence_mismatches) < 10:
            sequence_mismatches.append({"file_record_index": index + 1, "sequence": sequence})
        try:
            if sequence < 1 or start < 1 or end < start or tid < 1:
                raise ValueError("Invalid sequence, timestamp interval or TID")
            if api not in API_NAMES:
                raise ValueError(f"Unknown API enum {api}")
            if record_flags not in (0, 1):
                raise ValueError(f"Unsupported record flags {record_flags}")
            if (record_flags == 1) != (caller_rva == UINT64_MAX):
                raise ValueError("Caller sentinel disagrees with external-caller flag")
            offset = caller_rva if record_flags == 0 else None
            if offset is not None and main_base + offset > UINT64_MAX:
                raise ValueError("Qualified caller plus main base overflows uint64")
            is_copy = api in (1, 2)
            if not is_copy and (direction != -1 or size_bytes != 0 or src != 0 or dst != 0):
                raise ValueError("Non-copy API has nonapplicable copy fields")
            if api in (1, 2, 3, 4) and kernel_function != 0:
                raise ValueError("Non-launch API has a kernel-function field")
            if api in (1, 3) and stream != 0:
                raise ValueError("Non-stream API has a stream field")
            records.append(Record(sequence, API_NAMES[api], pid, tid, start, end,
                                  main_base + offset if offset is not None else None,
                                  offset, main_base, size_bytes if is_copy else None,
                                  direction if is_copy else None, result, src, dst,
                                  stream, kernel_function, record_flags))
        except ValueError as error:
            receipt["invalid_records"] += 1
            if len(receipt["invalid_examples"]) < 10:
                receipt["invalid_examples"].append({"file_record_index": index + 1,
                                                     "sequence": sequence, "error": str(error)})
    mismatched = sum(sequence != index + 1 for index, sequence in enumerate(sequences))
    duplicates = len(sequences) - len(set(sequences))
    receipt["sequence"] = {
        "semantics": "Assigned under append lock after HIP return; begins1 and follows successful record file order.",
        "first": sequences[0] if sequences else None,
        "last": sequences[-1] if sequences else None,
        "maximum": max(sequences) if sequences else None,
        "records_not_equal_to_one_based_file_index": mismatched,
        "duplicate_sequence_records": duplicates,
        "ordered_contiguous_from_one": mismatched == 0,
        "mismatch_examples": sequence_mismatches,
        "highest_attempted_sequence_known": False}
    if mismatched:
        receipt["integrity_issues"].append(f"{mismatched} sequence/file-index mismatches; no records silently repaired or renumbered.")
    if receipt["invalid_records"]:
        receipt["integrity_issues"].append(f"{receipt['invalid_records']} invalid full records excluded from attribution; raw bytes retained.")
    receipt["valid_records"] = len(records)
    receipt["unknown_direction_copy_records"] = sum(record.copy_bytes is not None and
                                                    record.direction not in DIRECTIONS for record in records)
    receipt["observed_API_counts"] = dict(Counter(record.function for record in records))
    receipt["record_time_envelope"] = {"earliest_start_ns": min(record.start for record in records),
                                        "latest_end_ns": max(record.end for record in records)} if records else None
    receipt["observer_loss_accounting"] = "No footer or attempted/written counters; cap/clock/write failures can silently stop observation, and in-flight calls may not yet have records."
    return records, receipt


def intersecting(records, start=None, end=None, pid=None):
    for record in records:
        if pid is not None and record.process != pid:
            continue
        lo = record.start if start is None else max(record.start, start)
        hi = record.end if end is None else min(record.end, end)
        point = record.start == record.end and (start is None or start <= record.start < end)
        if hi > lo or point:
            yield record, lo, hi


def copy_groups(records, start=None, end=None, pid=None) -> dict:
    rows = [(record, lo, hi) for record, lo, hi in intersecting(records, start, end, pid)
            if record.copy_bytes is not None]
    grouped = defaultdict(list)
    for record, lo, hi in rows:
        key = (record.function, record.caller_offset, record.copy_bytes,
               record.direction, record.result)
        grouped[key].append((record, lo, hi))
    groups = []
    for (function, offset, size, direction, result), entries in grouped.items():
        known = offset is not None
        groups.append({
            "function": function,
            "caller_relative_offset": f"0x{offset:x}" if known else None,
            "caller_rva_qualified": known,
            "matches_one_of_four_copy_sites": known and offset in COPY_SITES,
            "copy_bytes_per_call": size,
            "direction_code": direction,
            "direction_label": DIRECTIONS.get(direction, f"Unknown({direction})"),
            "result_code": result,
            "calls_intersecting": len(entries),
            "attempted_copy_bytes": size * len(entries),
            "success_result_copy_argument_bytes": size * len(entries) if result == 0 else 0,
            "full_host_duration_sum_ns": sum(record.end - record.start for record, _, _ in entries),
            "clipped_host_duration_sum_ns": sum(max(0, hi - lo) for _, lo, hi in entries),
            "clipped_host_interval_union_ns": coverage.interval_union_ns((lo, hi) for _, lo, hi in entries),
            "observed_absolute_callers": sorted({f"0x{record.caller:x}" for record, _, _ in entries
                                                   if record.caller is not None}),
            "observed_image_bases": sorted({f"0x{record.image_base:x}" for record, _, _ in entries
                                            if record.image_base is not None}),
            "distinct_source_addresses": len({record.source_address for record, _, _ in entries}),
            "distinct_destination_addresses": len({record.destination_address for record, _, _ in entries}),
        })
    groups.sort(key=lambda group: (-group["clipped_host_duration_sum_ns"],
                                   group["caller_relative_offset"] or "", group["function"]))
    known_count = sum(record.caller_offset is not None for record, _, _ in rows)
    unknown_count = len(rows) - known_count
    by_site = []
    for offset in COPY_SITES:
        matches = [group for group in groups if group["caller_relative_offset"] == f"0x{offset:x}"]
        by_site.append({"caller_relative_offset": f"0x{offset:x}",
                        "observed_matching_calls": sum(group["calls_intersecting"] for group in matches)
                        if known_count else None,
                        "groups": matches,
                        "qualification": "Counts only records with observer-qualified main-image caller offsets; external/unqualified callers are excluded."
                        if known_count else "No copy record has a qualified image-relative offset; no site count inferred."})
    return {"copy_calls_intersecting": len(rows), "qualified_relative_offset_copy_calls": known_count,
            "unqualified_relative_offset_copy_calls": unknown_count, "groups": groups,
            "four_copy_sites": by_site,
            "scope": "Observed calls only, never extrapolated to unobserved iterations. Sizes are API arguments; failed calls do not establish transferred bytes. Direction is the recorded API kind, not inferred pointer residency."}


def duration_stats(values) -> dict | None:
    ordered = sorted(values)
    if not ordered:
        return None
    count = len(ordered)
    return {"count": count, "min_ns": ordered[0], "max_ns": ordered[-1],
            "mean_ns": sum(ordered) / count,
            "median_ns": (ordered[(count - 1) // 2] + ordered[count // 2]) / 2,
            "p95_nearest_rank_ns": ordered[max(0, math.ceil(count * .95) - 1)]}


def quartet_replay(records, start=None, end=None, pid=None) -> dict:
    quartets = []
    candidate_starts = 0
    incomplete = 0
    for index, record in enumerate(records):
        if record.copy_bytes is None or record.caller_offset != COPY_SITES[0]:
            continue
        if pid is not None and record.process != pid:
            continue
        if not list(intersecting([record], start, end, pid)):
            continue
        candidate_starts += 1
        rows = records[index:index + 4]
        if (len(rows) != 4 or tuple(item.caller_offset for item in rows) != COPY_SITES or
                any(item.copy_bytes is None or item.function != record.function or
                    item.thread != record.thread or item.process != record.process or
                    item.sequence != record.sequence + position
                    for position, item in enumerate(rows))):
            incomplete += 1
            continue
        quartets.append(rows)
    all_intervals, last3_intervals = [], []
    patterns = Counter()
    examples = []
    full_spans, full_sums, full_last3 = [], [], []
    clipped_sum = 0
    clipped_last3_sum = 0
    fully_contained = 0
    for rows in quartets:
        intervals = list(intersecting(rows, start, end, pid))
        intervals_last3 = list(intersecting(rows[1:], start, end, pid))
        all_intervals.extend((lo, hi) for _, lo, hi in intervals)
        last3_intervals.extend((lo, hi) for _, lo, hi in intervals_last3)
        group_sum = sum(item.end - item.start for item in rows)
        group_last3 = sum(item.end - item.start for item in rows[1:])
        first_start, last_end = min(item.start for item in rows), max(item.end for item in rows)
        group_span = last_end - first_start
        group_union = coverage.interval_union_ns((item.start, item.end) for item in rows)
        full_spans.append(group_span)
        full_sums.append(group_sum)
        full_last3.append(group_last3)
        clipped_sum += sum(max(0, hi - lo) for _, lo, hi in intervals)
        clipped_last3_sum += sum(max(0, hi - lo) for _, lo, hi in intervals_last3)
        is_contained = (start is None or first_start >= start) and (end is None or last_end <= end)
        fully_contained += is_contained
        signature = tuple((item.copy_bytes, item.direction, item.result) for item in rows)
        patterns[signature] += 1
        if len(examples) < 20:
            examples.append({"first_sequence": rows[0].sequence, "last_sequence": rows[-1].sequence,
                             "thread": rows[0].thread, "start_ns": first_start, "end_ns": last_end,
                             "fully_contained_in_window": is_contained,
                             "full_temporal_span_ns": group_span, "full_host_duration_sum_ns": group_sum,
                             "full_host_interval_union_ns": group_union,
                             "span_outside_observed_host_calls_ns": group_span - group_union,
                             "individual_host_duration_ns": [item.end - item.start for item in rows],
                             "bytes_per_call": [item.copy_bytes for item in rows],
                             "direction_codes": [item.direction for item in rows],
                             "result_codes": [item.result for item in rows]})
    union = coverage.interval_union_ns(all_intervals)
    last3_union = coverage.interval_union_ns(last3_intervals)
    result = {"definition": "Four consecutive successful-file-order records, same thread/process/API, qualified sites in exact 966/98a/9b3/9dc order. Starts must intersect the window; no unobserved loop iteration is inferred.",
              "candidate_first_site_starts": candidate_starts,
              "complete_observed_groups": len(quartets), "incomplete_or_interleaved_candidates": incomplete,
              "fully_contained_groups": fully_contained, "boundary_crossing_groups": len(quartets) - fully_contained,
              "full_group_temporal_span_stats": duration_stats(full_spans),
              "full_group_host_duration_sum_stats": duration_stats(full_sums),
              "full_last_three_host_duration_sum_stats": duration_stats(full_last3),
              "clipped_quartet_host_duration_sum_ns": clipped_sum,
              "clipped_quartet_host_interval_union_ns": union,
              "clipped_last_three_host_duration_sum_ns": clipped_last3_sum,
              "clipped_last_three_host_interval_union_ns": last3_union,
              "patterns": [{"count": count, "bytes_per_call": [part[0] for part in signature],
                            "direction_codes": [part[1] for part in signature],
                            "direction_labels": [DIRECTIONS.get(part[1], f"Unknown({part[1]})") for part in signature],
                            "result_codes": [part[2] for part in signature]}
                           for signature, count in patterns.most_common()],
              "first_twenty_by_sequence": examples,
              "ceiling_qualification": "Last-three inclusive host intervals provide an optimistic standalone time-reduction bound only. They can contain GPU wait and dependency time that moves to a later synchronization if copies change; no removable CPU overhead, GPU busy time or serving gain is established. Group temporal gaps also include observer append work and remain unclassified."}
    if start is not None and end is not None:
        result["last_three_inclusive_union_percent_of_request"] = 100 * last3_union / (end - start)
        result["quartet_inclusive_union_percent_of_request"] = 100 * union / (end - start)
    return result


def make_window(records, start=None, end=None, pid=None) -> dict:
    result = coverage.attribute([record.call() for record in records], start, end, pid)
    result["copy_calls"] = copy_groups(records, start, end, pid)
    result["quartet_replay"] = quartet_replay(records, start, end, pid)
    selected = [record for record, _, _ in intersecting(records, start, end, pid)]
    result["result_code_counts"] = dict(Counter(str(record.result) for record in selected))
    return result


def build_report(trace_path: Path, boundaries_path: Path) -> dict:
    try:
        records, trace = parse_trace(trace_path)
    except (OSError, ValueError) as error:
        records, trace = [], {"source": coverage.source_ref(trace_path), "parse_error": str(error),
                              "valid_records": 0, "layout_valid": False}
    report = {"schema": "halogen0172.hip-host-direct-analysis.v1",
              "analyzedUTC": datetime.now(timezone.utc).isoformat(), "trace": trace,
              "boundaries_source": coverage.source_ref(boundaries_path),
              "base_analyzer_source": coverage.source_ref(BASE_ANALYZER),
              "direct_analyzer_source": coverage.source_ref(Path(__file__)),
              "observed_API_scope": list(API_NAMES.values()),
              "whole_HIP_runtime_coverage_established": False,
              "status": "observed-direct-host-records" if records else "trace-unavailable-or-invalid",
              "capture_complete_independently_established": False,
              "GPU_execution_time_established": False, "serving_gain_established": False,
              "whole_trace": make_window(records) if records else None, "requests": [],
              "scope_notes": [
                  "Selected six engine host APIs only; this is not a whole HIP runtime census.",
                  "Host API intervals include submission and possible blocking wait; they are not GPU execution.",
                  "Overlapping duration sums can exceed wall time; interval unions clip each overlap once.",
                  "Uncovered request time remains unclassified.",
                  "Four-site counts use observer-qualified main-image caller offsets, including valid base0, without loop extrapolation.",
                  "Export before normal stop is a live snapshot; no footer/complete-capture claim is inferred.",
                  "Prepended observer sees engine calls; existing preload internal RTLD_NEXT calls bypass this earlier observer."]}
    if records and trace.get("integrity_issues"):
        report["status"] = "partial-direct-host-records"
    try:
        document = json.loads(boundaries_path.read_text(encoding="utf-8-sig"))
        if not isinstance(document, dict):
            raise ValueError("Boundary root must be an object")
        report["capture_complete_as_declared"] = document.get("capture_complete")
        entries = document.get("requests", [document])
        if not isinstance(entries, list):
            raise ValueError("requests must be a list")
        for index, entry in enumerate(entries):
            request = {"name": str(entry.get("name", f"request-{index}")) if isinstance(entry, dict)
                       else f"request-{index}", "valid_boundary": False,
                       "phases": {}, "phase_status": "No valid prefill/decode boundary supplied."}
            report["requests"].append(request)
            try:
                if not isinstance(entry, dict):
                    raise ValueError("Request boundary must be an object")
                if entry.get("clock_domain", document.get("clock_domain")) != CLOCK:
                    raise ValueError("Request and observer clocks must explicitly share linux_CLOCK_BOOTTIME_ns")
                if entry.get("clock_alignment_valid", document.get("clock_alignment_valid")) is not True:
                    raise ValueError("Calibrated clock alignment is not explicitly valid")
                start = coverage.integer(entry["request_start_ns"], "request_start_ns", 1)
                end = coverage.integer(entry["request_end_ns"], "request_end_ns", 1)
                if end <= start:
                    raise ValueError("Request end must follow start")
                pid_value = entry.get("target_process_id", document.get("target_process_id"))
                pid = coverage.integer(pid_value, "PID", 1) if pid_value is not None else None
                if records and pid is not None and pid != trace["header"]["pid"]:
                    raise ValueError("Boundary target PID differs from the observer file header PID")
                request.update(valid_boundary=True, clock_domain=CLOCK,
                               mapping_uncertainty_ns=entry.get("mapping_uncertainty_ns", document.get("mapping_uncertainty_ns")),
                               request_status=entry.get("request_status"))
                if not records:
                    request["attribution_unavailable"] = "No valid exported records; no zero-call or percentage inference."
                    continue
                request["whole_request"] = make_window(records, start, end, pid)
                if pid is None:
                    request["PID_warning"] = "No target PID filter supplied."
                if not request["whole_request"]["calls_intersecting"]:
                    request["coverage_warning"] = "No matching records intersect this request; not proof of no HIP work."
                split = entry.get("prefill_end_ns")
                if split is not None and entry.get("prefill_boundary_valid") is True:
                    split = coverage.integer(split, "prefill_end_ns", 1)
                    if not start < split < end:
                        raise ValueError("Explicit prefill boundary must lie strictly within request")
                    request["phases"] = {"prefill": make_window(records, start, split, pid),
                                         "decode": make_window(records, split, end, pid)}
                    request["phase_status"] = "Uses explicitly qualified prefill/decode boundary."
            except (ValueError, KeyError) as error:
                request["boundary_error"] = str(error)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        report["boundary_error"] = str(error)
    report["all_requests_have_valid_attribution"] = bool(report["requests"]) and all(
        request.get("valid_boundary") and "whole_request" in request and not request.get("boundary_error")
        for request in report["requests"])
    return report


def markdown(report: dict) -> str:
    lines = ["# Durable direct HIP host census", "", f"Status: **{report['status']}**.", "",
             "These records cover the selected six engine host APIs. They do not establish whole HIP runtime coverage. Host intervals are submission and possible waiting. Sums may overlap; unions count elapsed covered time once. GPU busy time and serving gain remain unqualified.", ""]
    for label, window in [("Whole exported trace", report["whole_trace"])]:
        if window:
            lines += [f"{label}: {window['calls_intersecting']} calls; duration sum {window['host_duration_sum_ns']/1e6:.6f} ms; interval union {window['host_interval_union_ns']/1e6:.6f} ms.", ""]
    for request in report["requests"]:
        lines += [f"## {request['name']}", ""]
        window = request.get("whole_request")
        if window is None:
            lines += [request.get("attribution_unavailable", request.get("boundary_error", "Boundary unavailable.")), ""]
            continue
        lines += [f"Window {window['window_duration_ns']/1e6:.6f} ms; {window['calls_intersecting']} calls; host duration sum {window['host_duration_sum_ns']/1e6:.6f} ms ({window['host_duration_sum_percent_of_window']:.3f}%); host interval union {window['host_interval_union_ns']/1e6:.6f} ms ({window['host_union_percent_of_window']:.3f}%).", "",
                  "| API | Calls | Clipped sum ms | Clipped union ms | Union % |",
                  "| --- | ---: | ---: | ---: | ---: |"]
        for group in window["by_function"]:
            lines.append(f"| {group['function']} | {group['calls_intersecting']} | {group['clipped_host_duration_sum_ns']/1e6:.6f} | {group['clipped_host_interval_union_ns']/1e6:.6f} | {group['union_percent_of_window']:.3f} |")
        copies = window["copy_calls"]
        lines += ["", f"Copies: {copies['copy_calls_intersecting']} observed; {copies['qualified_relative_offset_copy_calls']} with qualified main-image caller, {copies['unqualified_relative_offset_copy_calls']} external/unqualified.", "",
                  "| Four-copy site | API | Bytes per call | Kind | Result | Observed calls | Sum ms | Union ms |",
                  "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for site in copies["four_copy_sites"]:
            if not site["groups"]:
                count = site["observed_matching_calls"]
                lines.append(f"| {site['caller_relative_offset']} | unobserved/unknown | — | — | — | {count if count is not None else 'unqualified'} | — | — |")
            for group in site["groups"]:
                lines.append(f"| {site['caller_relative_offset']} | {group['function']} | {group['copy_bytes_per_call']} | {group['direction_label']} ({group['direction_code']}) | {group['result_code']} | {group['calls_intersecting']} | {group['clipped_host_duration_sum_ns']/1e6:.6f} | {group['clipped_host_interval_union_ns']/1e6:.6f} |")
        lines += ["", copies["scope"], "", request["phase_status"], "",
                  f"Mapping uncertainty ns: {request.get('mapping_uncertainty_ns')}.", ""]
        replay = window["quartet_replay"]
        lines += [f"Strict by-sequence quartets: {replay['complete_observed_groups']} complete, {replay['incomplete_or_interleaved_candidates']} incomplete/interleaved; {replay['fully_contained_groups']} fully within the request. Last-three inclusive union {replay['clipped_last_three_host_interval_union_ns']/1e6:.6f} ms ({replay['last_three_inclusive_union_percent_of_request']:.4f}% of request).", "", replay["ceiling_qualification"], ""]
    lines += ["## Integrity", "", "```json", json.dumps(report["trace"], indent=2), "```", "",
              "Raw source hashes and all observed copy signatures remain in the JSON. Capture completeness is not independently established.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, default=HERE / "host-census.bin")
    parser.add_argument("--boundaries", type=Path, default=HERE / "request-boundaries.json")
    parser.add_argument("--output-prefix", type=Path, default=HERE / "host-direct-analysis")
    args = parser.parse_args()
    outputs = [Path(str(args.output_prefix) + suffix) for suffix in (".json", ".md")]
    inputs = (args.trace.resolve(), args.boundaries.resolve(), BASE_ANALYZER.resolve())
    if any(output.resolve() in inputs for output in outputs):
        parser.error("Outputs may not replace raw inputs or analyzer source")
    report = build_report(args.trace, args.boundaries)
    for output, payload in zip(outputs, (json.dumps(report, indent=2) + "\n", markdown(report))):
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_name(output.name + f".tmp-{os.getpid()}")
        temp.write_text(payload, encoding="utf-8")
        temp.replace(output)
    print(json.dumps({"status": report["status"], "records": report["trace"].get("valid_records", 0),
                      "outputs": [str(output) for output in outputs]}))
    return 0 if report["status"] == "observed-direct-host-records" and report["all_requests_have_valid_attribution"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
