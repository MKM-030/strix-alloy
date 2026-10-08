"""Read-only ROCprof HIP host-call attribution; no device/runtime imports.

CSV timestamps and calibrated request boundaries must share CLOCK_BOOTTIME.
Host API intervals describe submission and possibly waiting, never GPU busy time.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path


CLOCK = "linux_CLOCK_BOOTTIME_ns"
FIELDS = ("Domain", "Function", "Process_Id", "Thread_Id", "Correlation_Id",
          "Start_Timestamp", "End_Timestamp")


@dataclass(frozen=True, slots=True)
class Call:
    function: str
    process: int
    thread: int
    start: int
    end: int


def integer(value, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{name} must be an integer")
    number = int(value)
    if isinstance(value, str) and str(number) != value.strip():
        raise ValueError(f"{name} must be a plain integer")
    if number < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return number


def source_ref(path: Path) -> dict:
    result = {"path": str(path.resolve()), "exists": path.is_file()}
    if result["exists"]:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        result.update(bytes=path.stat().st_size, sha256=digest.hexdigest())
    return result


def read_trace(path: Path) -> tuple[list[Call], dict]:
    receipt = {"source": source_ref(path), "rows_seen": 0, "invalid_rows": 0,
               "invalid_examples": [], "parse_error": None, "schema_valid": False}
    if not path.is_file():
        receipt["parse_error"] = "Trace was not exported or is missing; unavailable is not zero calls."
        return [], receipt
    calls = []
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            fields = reader.fieldnames or []
            receipt["header"] = fields
            if any(fields.count(field) != 1 for field in FIELDS):
                raise ValueError("Expected the seven qualified ROCprof HIP CSV fields exactly once")
            receipt["schema_valid"] = True
            for row in reader:
                receipt["rows_seen"] += 1
                try:
                    if None in row or any(row[field] is None for field in FIELDS):
                        raise ValueError("Incomplete or extra CSV columns")
                    if not row["Domain"].startswith("HIP_") or not row["Function"].strip():
                        raise ValueError("Not a named HIP host API record")
                    start = integer(row["Start_Timestamp"], "start", 1)
                    end = integer(row["End_Timestamp"], "end", 1)
                    if end < start:
                        raise ValueError("End timestamp precedes start")
                    integer(row["Correlation_Id"], "correlation")
                    calls.append(Call(row["Function"], integer(row["Process_Id"], "PID", 1),
                                      integer(row["Thread_Id"], "TID", 1), start, end))
                except (ValueError, KeyError) as error:
                    receipt["invalid_rows"] += 1
                    if len(receipt["invalid_examples"]) < 10:
                        receipt["invalid_examples"].append({"csv_line": reader.line_num,
                                                            "error": str(error)})
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        receipt["parse_error"] = str(error)
    receipt["valid_rows"] = len(calls)
    receipt["observed_process_counts"] = dict(Counter(str(call.process) for call in calls))
    return calls, receipt


def interval_union_ns(intervals) -> int:
    ordered = sorted((start, end) for start, end in intervals if end > start)
    if not ordered:
        return 0
    left, right = ordered[0]
    total = 0
    for start, end in ordered[1:]:
        if start > right:
            total += right - left
            left, right = start, end
        else:
            right = max(right, end)
    return total + right - left


def attribute(calls: list[Call], start: int | None = None,
              end: int | None = None, pid: int | None = None) -> dict:
    grouped = defaultdict(list)
    all_intervals = []
    window = start is not None and end is not None
    duration = end - start if window else None
    for call in calls:
        if pid is not None and call.process != pid:
            continue
        lo, hi = max(call.start, start) if window else call.start, min(call.end, end) if window else call.end
        point_inside = window and call.start == call.end and start <= call.start < end
        if hi <= lo and not point_inside and call.start != call.end:
            continue
        if window and hi <= lo and not point_inside:
            continue
        clipped = max(0, hi - lo)
        grouped[call.function].append((call, lo, hi, clipped))
        if clipped:
            all_intervals.append((lo, hi))
    groups = []
    for name, rows in grouped.items():
        total_full = sum(call.end - call.start for call, _, _, _ in rows)
        total_clipped = sum(clipped for _, _, _, clipped in rows)
        union = interval_union_ns((lo, hi) for _, lo, hi, clipped in rows if clipped)
        group = {"function": name, "calls_intersecting": len(rows),
                 "full_host_duration_sum_ns": total_full,
                 "clipped_host_duration_sum_ns": total_clipped,
                 "clipped_host_interval_union_ns": union,
                 "max_full_host_duration_ns": max(call.end - call.start for call, _, _, _ in rows),
                 "mean_full_host_duration_ns": total_full / len(rows)}
        if window:
            group.update(union_percent_of_window=100 * union / duration,
                         duration_sum_percent_of_window=100 * total_clipped / duration,
                         calls_starting_inside=sum(start <= call.start < end for call, _, _, _ in rows))
        groups.append(group)
    groups.sort(key=lambda group: (-group["clipped_host_duration_sum_ns"], group["function"]))
    union = interval_union_ns(all_intervals)
    total = sum(group["clipped_host_duration_sum_ns"] for group in groups)
    result = {"calls_intersecting": sum(group["calls_intersecting"] for group in groups),
              "target_process_id": pid, "host_duration_sum_ns": total,
              "host_interval_union_ns": union, "by_function": groups}
    if window:
        result.update(start_ns=start, end_ns=end, window_duration_ns=duration,
                      host_union_percent_of_window=100 * union / duration,
                      host_duration_sum_percent_of_window=100 * total / duration,
                      outside_observed_host_API_intervals_ns=duration - union)
    return result


def build_report(csv_path: Path, boundary_path: Path) -> dict:
    calls, trace = read_trace(csv_path)
    result = {"schema": "halogen0172.hip-host-call-analysis.v1",
              "analyzedUTC": datetime.now(timezone.utc).isoformat(),
              "trace": trace, "boundaries_source": source_ref(boundary_path),
              "status": "observed-host-records" if calls else "trace-unavailable-or-empty",
              "GPU_execution_time_established": False,
              "serving_speed_or_acceptance_gain_established": False,
              "scope_notes": [
                  "HIP host durations include submission and possibly blocking wait; they are not GPU execution.",
                  "Summed durations are not elapsed wall time when threads or nested APIs overlap.",
                  "Interval unions clip to the supplied request; per-function unions are not additive.",
                  "Time outside observed host API intervals is unclassified, not GPU time or CPU overhead.",
                  "No copy direction/bytes or kernel identity is inferred from an API-name-only trace.",
                  "Capture completeness needs external export/loss evidence; surviving rows can be analyzed after a crash."]}
    result["whole_trace"] = attribute(calls) if calls else None
    result["requests"] = []
    try:
        document = json.loads(boundary_path.read_text(encoding="utf-8-sig"))
        if not isinstance(document, dict):
            raise ValueError("Boundary root must be an object")
        result["capture_complete_as_declared"] = document.get("capture_complete")
        result["capture_complete_independently_established"] = False
        result["profiler_loss_accounting"] = document.get("profiler_loss_accounting")
        entries = document.get("requests", [document])
        if not isinstance(entries, list):
            raise ValueError("requests must be a list")
        for index, request in enumerate(entries):
            analyzed = {"name": str(request.get("name", f"request-{index}")) if isinstance(request, dict) else f"request-{index}",
                        "valid_boundary": False, "phases": {}, "phase_status": "No valid prefill/decode boundary supplied."}
            result["requests"].append(analyzed)
            try:
                if not isinstance(request, dict):
                    raise ValueError("Request boundary must be an object")
                if request.get("clock_domain", document.get("clock_domain")) != CLOCK:
                    raise ValueError("Request and ROCprof clocks must be explicitly linux_CLOCK_BOOTTIME_ns")
                if request.get("clock_alignment_valid", document.get("clock_alignment_valid")) is not True:
                    raise ValueError("Calibrated clock alignment is not explicitly valid")
                start = integer(request["request_start_ns"], "request_start_ns", 1)
                end = integer(request["request_end_ns"], "request_end_ns", 1)
                if end <= start:
                    raise ValueError("Request end must follow start")
                pid_value = request.get("target_process_id", document.get("target_process_id"))
                pid = integer(pid_value, "target_process_id", 1) if pid_value is not None else None
                analyzed.update(valid_boundary=True, clock_domain=CLOCK,
                                mapping_uncertainty_ns=request.get("mapping_uncertainty_ns", document.get("mapping_uncertainty_ns")),
                                request_status=request.get("request_status"))
                if not calls:
                    analyzed["attribution_unavailable"] = "No valid exported trace rows; no zero-call or percentage inference."
                    continue
                analyzed["complete"] = attribute(calls, start, end, pid)
                if pid is None:
                    analyzed["PID_warning"] = "No target PID filter; attribution includes every traced process."
                if analyzed["complete"]["calls_intersecting"] == 0:
                    analyzed["coverage_warning"] = "No matching records intersect this request; not proof of no HIP work."
                split = request.get("prefill_end_ns")
                if split is not None and request.get("prefill_boundary_valid") is True:
                    split = integer(split, "prefill_end_ns", 1)
                    if not start < split < end:
                        raise ValueError("Prefill boundary must lie strictly within request")
                    analyzed["phases"] = {"prefill": attribute(calls, start, split, pid),
                                          "decode": attribute(calls, split, end, pid)}
                    analyzed["phase_status"] = "Uses explicitly valid prefill_end_ns; no phase inferred from aggregate API timings."
            except (ValueError, KeyError) as error:
                analyzed["boundary_error"] = str(error)
                if not analyzed["valid_boundary"]:
                    analyzed.pop("complete", None)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        result["boundary_error"] = str(error)
    if trace["invalid_rows"] or trace["parse_error"]:
        result["status"] = "partial-or-invalid-trace" if calls else "trace-unavailable-or-invalid"
    return result


def markdown(report: dict) -> str:
    lines = ["# HIP host API census", "", f"Status: **{report['status']}**.", "",
             "These are HIP host-call durations and interval coverage. GPU execution, copy bytes/direction, "
             "kernel busy time and serving improvement are unqualified. Overlapping duration sums are not wall time.", ""]
    if report.get("boundary_error"):
        lines += [f"Boundary unavailable: {report['boundary_error']}", ""]
    for request in report["requests"]:
        lines += [f"## {request['name']}", ""]
        if not request.get("complete"):
            lines += [f"No request percentages: {request.get('attribution_unavailable', request.get('boundary_error', 'boundary unavailable'))}", ""]
            continue
        for label, window in [("Whole request", request["complete"]), *request["phases"].items()]:
            lines += [f"{label}: {window['window_duration_ns'] / 1e6:.6f} ms; "
                      f"{window['calls_intersecting']} intersecting calls; "
                      f"host interval union {window['host_interval_union_ns'] / 1e6:.6f} ms "
                      f"({window['host_union_percent_of_window']:.3f}%); "
                      f"duration sum {window['host_duration_sum_ns'] / 1e6:.6f} ms.", "",
                      "| API | Intersecting calls | Clipped duration sum ms | Clipped union ms | Union % of window |",
                      "| --- | ---: | ---: | ---: | ---: |"]
            for group in window["by_function"]:
                name = group["function"].replace("|", "\\|")
                lines.append(f"| {name} | {group['calls_intersecting']} | "
                             f"{group['clipped_host_duration_sum_ns'] / 1e6:.6f} | "
                             f"{group['clipped_host_interval_union_ns'] / 1e6:.6f} | "
                             f"{group['union_percent_of_window']:.3f} |")
            lines.append("")
        lines += [request["phase_status"], "",
                  f"Mapping uncertainty ns: {request.get('mapping_uncertainty_ns')}; "
                  f"request status: {request.get('request_status')}.", ""]
        for key in ("boundary_error", "coverage_warning", "PID_warning"):
            if request.get(key):
                lines += [request[key], ""]
    lines += [f"Valid trace rows: {report['trace'].get('valid_rows', 0)}; "
              f"invalid rows: {report['trace']['invalid_rows']}; "
              f"capture complete as declared: {report.get('capture_complete_as_declared')}. "
              "Completeness is not independently established.", "",
              "Whole-trace counts/durations, source hashes and parsing evidence are in the JSON. Raw files are untouched.", ""]
    return "\n".join(lines)


def main() -> int:
    work = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=work / "stock8k_hip_api_trace.csv")
    parser.add_argument("--boundaries", type=Path, default=work / "request-boundaries.json")
    parser.add_argument("--output-prefix", type=Path, default=work / "host-call-analysis")
    args = parser.parse_args()
    outputs = [Path(str(args.output_prefix) + suffix) for suffix in (".json", ".md")]
    if any(output.resolve() in (args.csv.resolve(), args.boundaries.resolve()) for output in outputs):
        parser.error("Outputs may not overwrite raw inputs")
    report = build_report(args.csv, args.boundaries)
    payloads = [json.dumps(report, indent=2) + "\n", markdown(report)]
    for output, payload in zip(outputs, payloads):
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + f".tmp-{os.getpid()}")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(output)
    print(json.dumps({"status": report["status"], "valid_rows": report["trace"].get("valid_rows", 0),
                      "requests": len(report["requests"]), "outputs": [str(path) for path in outputs]}))
    return 0 if report["trace"].get("valid_rows", 0) else 2


if __name__ == "__main__":
    raise SystemExit(main())
