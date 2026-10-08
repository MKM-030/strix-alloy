"""CPU-only validator for scalar_async.c V1 live receipts; no runtime imports.

Observed append counts do not establish footer coverage or GPU completion.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import struct


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "scalar_async.c"
HEADER = struct.Struct("<8sIIIIQQQQII")
RECORD = struct.Struct("<6QiiII")
MAGIC = b"HGSC0172"
CLOCK = "linux_CLOCK_BOOTTIME_ns"
CAP = 1024 * 1024
CALLER_RVA = 0x17B91BE
GUARD_RVA = 0x17B91A5
GUARD_BYTES = 49
UINT64_MAX = (1 << 64) - 1


def source_ref(path: Path) -> dict:
    result = {"path": str(path.resolve()), "exists": path.is_file()}
    if result["exists"]:
        raw = path.read_bytes()
        result.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    return result


def interval_union_ns(intervals) -> int:
    ordered = sorted((lo, hi) for lo, hi in intervals if hi > lo)
    if not ordered:
        return 0
    lo, hi = ordered[0]
    total = 0
    for left, right in ordered[1:]:
        if left > hi:
            total += hi - lo
            lo, hi = left, right
        else:
            hi = max(hi, right)
    return total + hi - lo


def duration_stats(values) -> dict | None:
    ordered = sorted(values)
    if not ordered:
        return None
    n = len(ordered)
    return {"count": n, "min_ns": ordered[0], "max_ns": ordered[-1],
            "mean_ns": sum(ordered) / n,
            "median_ns": (ordered[(n - 1) // 2] + ordered[n // 2]) / 2,
            "p95_nearest_rank_ns": ordered[max(0, math.ceil(n * .95) - 1)]}


def summary(records: list[dict], start=None, end=None, pid=None) -> dict:
    rows, intervals = [], []
    for record in records:
        if pid is not None and record["pid"] != pid:
            continue
        lo = record["start_ns"] if start is None else max(start, record["start_ns"])
        hi = record["end_ns"] if end is None else min(end, record["end_ns"])
        point = record["start_ns"] == record["end_ns"] and (start is None or start <= record["start_ns"] < end)
        if hi <= lo and not point:
            continue
        rows.append((record, lo, hi))
        intervals.append((lo, hi))
    result = {"observed_appended_substitution_attempts": len(rows),
              "observed_success_result_attempts": sum(record["result"] == 0 for record, _, _ in rows),
              "observed_error_result_attempts": sum(record["result"] != 0 for record, _, _ in rows),
              "observed_error_path_fences": sum(bool(record["flags"] & 4) for record, _, _ in rows),
              "result_code_counts": dict(Counter(str(record["result"]) for record, _, _ in rows)),
              "error_fence_result_code_counts": dict(Counter(str(record["fence_result"]) for record, _, _ in rows if record["flags"] & 4)),
              "thread_counts": dict(Counter(str(record["tid"]) for record, _, _ in rows)),
              "full_fill_host_duration_sum_ns": sum(record["end_ns"] - record["start_ns"] for record, _, _ in rows),
              "clipped_fill_host_duration_sum_ns": sum(max(0, hi - lo) for _, lo, hi in rows),
              "clipped_fill_host_interval_union_ns": interval_union_ns(intervals),
              "full_fill_host_duration_stats": duration_stats(record["end_ns"] - record["start_ns"] for record, _, _ in rows)}
    if start is not None and end is not None:
        duration = end - start
        result.update(start_ns=start, end_ns=end, window_duration_ns=duration,
                      inclusive_fill_union_percent_of_window=100 * result["clipped_fill_host_interval_union_ns"] / duration,
                      inclusive_fill_sum_percent_of_window=100 * result["clipped_fill_host_duration_sum_ns"] / duration)
    return result


def parse_receipt(path: Path) -> tuple[list[dict], dict]:
    evidence = {"source": source_ref(path), "header_valid": False,
                "record_integrity_passed": False, "full_records": 0,
                "valid_records": 0, "invalid_records": 0,
                "invalid_examples": [], "integrity_issues": [],
                "footer_present": False, "highest_attempted_substitution_known": False,
                "capture_complete_independently_established": False}
    if not path.is_file():
        evidence["parse_error"] = "Receipt is missing; unavailable is not zero substitutions."
        return [], evidence
    if path.stat().st_size > CAP:
        evidence["parse_error"] = "Receipt exceeds the sealed 1 MiB cap; refusing unsupported data."
        return [], evidence
    raw = path.read_bytes()
    evidence["source"].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    if len(raw) < HEADER.size:
        evidence["parse_error"] = f"Partial header: {len(raw)} bytes; expected {HEADER.size}."
        return [], evidence
    (magic, version, header_size, record_size, clock_id, main_base,
     cap, caller, guard, pid, flags) = HEADER.unpack_from(raw)
    evidence["header"] = {"magic_hex": magic.hex(), "version": version,
                          "header_size": header_size, "record_size": record_size,
                          "clock_id": clock_id, "clock_domain": CLOCK if clock_id == 7 else None,
                          "main_load_base": f"0x{main_base:x}", "base_zero_is_valid": True,
                          "max_file_bytes": cap, "caller_rva": f"0x{caller:x}",
                          "guard_rva": f"0x{guard:x}", "pid": pid, "flags": flags}
    if (magic != MAGIC or version != 1 or header_size != 64 or record_size != 64 or
            clock_id != 7 or cap != CAP or caller != CALLER_RVA or guard != GUARD_RVA or
            pid < 1 or flags != 7 or main_base > UINT64_MAX - GUARD_RVA - GUARD_BYTES):
        evidence["parse_error"] = "Header does not match exact scalar V1 magic, sizes, clock, flags, caller, guard, PID, base range and cap."
        return [], evidence
    evidence["header_valid"] = True
    full_records, trailing = divmod(len(raw) - HEADER.size, RECORD.size)
    evidence.update(full_records=full_records, trailing_partial_record_bytes=trailing,
                    file_at_cap=len(raw) == CAP, max_complete_records=(CAP - HEADER.size) // RECORD.size)
    if trailing:
        evidence["integrity_issues"].append(f"Trailing partial record: {trailing} raw bytes retained; no silent truncation.")
    if len(raw) == CAP:
        evidence["integrity_issues"].append("Receipt is at its cap; a subsequent substitution would fail closed. No terminal coverage is inferred.")
    records = []
    expected_errors = 0
    sequence_mismatches = counter_mismatches = error_counter_mismatches = 0
    last_encoded = None
    for index in range(full_records):
        (sequence, start_ns, end_ns, tid, substituted_total, error_total,
         result, fence_result, record_flags, reserved) = RECORD.unpack_from(raw, HEADER.size + index * RECORD.size)
        # C increments error_total iff record flag 2 is set. Validate that flag
        # independently against result, without silently repairing either field.
        expected_errors += bool(record_flags & 2)
        sequence_mismatches += sequence != index + 1
        counter_mismatches += substituted_total != index + 1
        error_counter_mismatches += error_total != expected_errors
        last_encoded = {"sequence": sequence, "substituted_total": substituted_total, "error_total": error_total}
        row = {"file_record_index": index + 1, "sequence": sequence, "pid": pid,
               "start_ns": start_ns, "end_ns": end_ns, "tid": tid,
               "substituted_total": substituted_total, "error_total": error_total,
               "result": result, "fence_result": fence_result,
               "flags": record_flags, "reserved": reserved}
        reasons = []
        if sequence != index + 1:
            reasons.append("sequence must equal one-based append index")
        if substituted_total != index + 1 or substituted_total != sequence:
            reasons.append("substituted_total must equal sequence and one-based append index")
        if error_total != expected_errors or error_total > substituted_total:
            reasons.append("error_total must match cumulative flagged errors and not exceed substitutions")
        if end_ns < start_ns or tid < 1:
            reasons.append("invalid timestamp interval or TID")
        if reserved != 0:
            reasons.append("reserved record field must be zero")
        if result == 0 and (record_flags != 1 or fence_result != 0):
            reasons.append("successful fill requires flags1 and nonapplicable fence_result0")
        if result != 0 and record_flags != 7:
            reasons.append("error fill requires flags7, including recorded error-path fence")
        if reasons:
            evidence["invalid_records"] += 1
            if len(evidence["invalid_examples"]) < 10:
                evidence["invalid_examples"].append({"file_record_index": index + 1,
                                                     "sequence": sequence, "errors": reasons})
        else:
            records.append(row)
    evidence.update(valid_records=len(records), sequence_file_index_mismatches=sequence_mismatches,
                    substitution_counter_mismatches=counter_mismatches,
                    error_counter_mismatches=error_counter_mismatches,
                    last_encoded_counters=last_encoded)
    if evidence["invalid_records"]:
        evidence["integrity_issues"].append(f"{evidence['invalid_records']} invalid full records excluded from metrics; raw bytes remain unchanged.")
    evidence["record_integrity_passed"] = trailing == 0 and evidence["invalid_records"] == 0
    evidence["counter_scope"] = "Encoded counters describe attempted substitutions completed through append, including fill errors. They are not an attempted-call footer or GPU completion counter."
    return records, evidence


def attribute_requests(records: list[dict], path: Path, pid: int | None) -> dict:
    result = {"source": source_ref(path), "requests": []}
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(document, dict):
            raise ValueError("Boundary root must be an object")
        entries = document.get("requests", [document])
        if not isinstance(entries, list):
            raise ValueError("requests must be a list")
        for index, entry in enumerate(entries):
            row = {"name": str(entry.get("name", f"request-{index}")) if isinstance(entry, dict)
                   else f"request-{index}", "valid_boundary": False}
            result["requests"].append(row)
            try:
                if not isinstance(entry, dict):
                    raise ValueError("Request boundary must be an object")
                if entry.get("clock_domain", document.get("clock_domain")) != CLOCK or entry.get("clock_alignment_valid", document.get("clock_alignment_valid")) is not True:
                    raise ValueError("Attribution requires explicit calibrated linux_CLOCK_BOOTTIME_ns alignment")
                start, end = entry["request_start_ns"], entry["request_end_ns"]
                if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int) or not 0 < start < end:
                    raise ValueError("Boundary timestamps must be positive integer ns with start<end")
                requested_pid = entry.get("target_process_id", document.get("target_process_id"))
                if requested_pid is not None and requested_pid != pid:
                    raise ValueError("Boundary PID does not match receipt header PID")
                row.update(valid_boundary=True, mapping_uncertainty_ns=entry.get("mapping_uncertainty_ns", document.get("mapping_uncertainty_ns")))
                if records:
                    row["observed"] = summary(records, start, end, pid)
                else:
                    row["attribution_unavailable"] = "No valid records; no request coverage inferred."
            except (ValueError, KeyError) as error:
                row["boundary_error"] = str(error)
    except (OSError, UnicodeError, ValueError) as error:
        result["boundary_error"] = str(error)
    return result


def build_report(path: Path, boundaries: Path | None = None) -> dict:
    try:
        records, evidence = parse_receipt(path)
    except OSError as error:
        records, evidence = [], {"source": {"path": str(path.resolve())}, "parse_error": str(error),
                                "header_valid": False, "record_integrity_passed": False,
                                "valid_records": 0, "capture_complete_independently_established": False}
    status = "observed-substitution-receipts" if records else "no-valid-substitution-receipts"
    if evidence.get("parse_error"):
        status = "receipt-unavailable-or-invalid"
    elif not evidence["record_integrity_passed"]:
        status = "partial-or-invalid-substitution-receipts"
    report = {"schema": "halogen0172.scalar-async-receipt-analysis.v1",
              "analyzedUTC": datetime.now(timezone.utc).isoformat(), "status": status,
              "receipt": evidence, "analyzer_source": source_ref(Path(__file__)),
              "current_C_source_reference": source_ref(SOURCE),
              "observed": summary(records) if records else None,
              "valid_records": records,
              "capture_complete_independently_established": False,
              "GPU_completion_established": False, "serving_gain_established": False,
              "scope_notes": [
                  "Substitution attempts include failed fill calls; result0 is a HIP enqueue result, not GPU completion.",
                  "Header flags assert the source guard/byte-value legacy-stream contract; this parser does not independently verify the loaded binary/library hash.",
                  "Measured timestamps surround hipMemsetD32Async only; source-value read, receipt append and error-path fence durations are excluded.",
                  "Append order is lock order and need not be timestamp order across threads.",
                  "No footer exists. Live-export EOF and matching counters do not prove all substitutions or requests were captured.",
                  "The current C source hash is a reference, not proof it produced this receipt; root build/export receipts supply that provenance.",
                  "Raw files are read-only; partial bytes/invalid rows are explicit and never silently repaired."]}
    if boundaries is not None:
        report["request_attribution"] = attribute_requests(records, boundaries, evidence.get("header", {}).get("pid"))
    return report


def markdown(report: dict) -> str:
    lines = ["# Scalar async live receipt", "", f"Status: **{report['status']}**.", ""]
    observed = report["observed"]
    if observed is None:
        lines += ["No valid observed substitutions are available; unavailable is not zero coverage.", ""]
    else:
        lines += [f"Observed appended attempts: **{observed['observed_appended_substitution_attempts']}**; success-result attempts: {observed['observed_success_result_attempts']}; error-result attempts: {observed['observed_error_result_attempts']}; error-path fences: {observed['observed_error_path_fences']}.", "",
                  f"Fill host duration sum {observed['full_fill_host_duration_sum_ns']/1e6:.6f} ms; interval union {observed['clipped_fill_host_interval_union_ns']/1e6:.6f} ms. Error-path fence and receipt append time are excluded.", ""]
    lines += ["Complete capture, GPU completion and serving gain are unestablished. There is no footer.", "", "## Integrity", "", "```json", json.dumps(report["receipt"], indent=2), "```", "", "## Scope", ""]
    lines.extend(f"- {note}" for note in report["scope_notes"])
    lines.append("")
    if "request_attribution" in report:
        lines += ["## Optional request attribution", "", "```json", json.dumps(report["request_attribution"], indent=2), "```", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--boundaries", type=Path)
    parser.add_argument("--output-prefix", type=Path)
    args = parser.parse_args()
    prefix = args.output_prefix if args.output_prefix is not None else args.receipt.with_suffix("").with_name(args.receipt.stem + "-analysis")
    outputs = [Path(str(prefix) + suffix) for suffix in (".json", ".md")]
    inputs = {args.receipt.resolve(), SOURCE.resolve(), Path(__file__).resolve()}
    if args.boundaries is not None:
        inputs.add(args.boundaries.resolve())
    if any(path.resolve() in inputs for path in outputs):
        parser.error("Outputs may not replace raw inputs or source files")
    report = build_report(args.receipt, args.boundaries)
    for path, content in zip(outputs, (json.dumps(report, indent=2) + "\n", markdown(report))):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    print(json.dumps({"status": report["status"], "observed": report["observed"],
                      "outputs": [str(path) for path in outputs]}))
    return 0 if report["receipt"]["header_valid"] and report["receipt"]["record_integrity_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
