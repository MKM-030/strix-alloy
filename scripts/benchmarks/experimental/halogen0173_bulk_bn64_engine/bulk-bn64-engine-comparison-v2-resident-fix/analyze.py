"""Analyze frozen 0.17.3 BN64 engine summaries and audit snapshots; no runtime access."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics

WORK = Path(__file__).resolve().parent
ARMS = ("before", "candidate", "after")
TOLERANCE = 0.001  # Existing HC6 clock comparability threshold: 0.1 percent.
COUNTERS = ("started", "committed", "rolled_back", "rejected", "failures")


def reference(path, data):
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def load(path):
    data = path.read_bytes()
    return json.loads(data), reference(path, data)


def positive(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Native rates and clock ratios must be finite and positive")
    return value


def stats(values):
    return {"mean": statistics.fmean(values), "stdev": statistics.stdev(values) if len(values) > 1 else 0,
            "minimum": min(values), "maximum": max(values), "runs": len(values)}


def valid_hash(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def summarize(arm):
    measured = [row for row in arm["rows"] if row["phase"] == "measured"]
    if not measured:
        raise ValueError("A summary has no measured rows")
    native_prefill = [positive(row["timings"]["prompt_per_second"]) for row in measured]
    native_decode = [positive(row["timings"]["predicted_per_second"]) for row in measured]
    accepted, drafted = sum(row["accepted"] for row in measured), sum(row["drafted"] for row in measured)
    if any(not 0 <= row["accepted"] <= row["drafted"] or row["drafted"] <= 0 for row in measured):
        raise ValueError("Invalid acceptance counters")
    return {"native_prefill_tps": stats(native_prefill), "native_decode_tps": stats(native_decode),
            "acceptance": {"accepted": accepted, "drafted": drafted},
            "measured_native_prefill_tps": native_prefill, "measured_native_decode_tps": native_decode,
            "monotonic_per_raw": [positive(row["clock_calibration"]["monotonic_per_raw"]) for row in measured],
            "raw_per_qpc": [positive(row["clock_calibration"]["raw_per_qpc"]) for row in measured]}


def clock_check(metrics, names):
    mono = [value for name in names for value in metrics[name]["monotonic_per_raw"]]
    qpc = [value for name in names for value in metrics[name]["raw_per_qpc"]]
    spread = max(mono) / min(mono) - 1
    qpc_ok = all(abs(value - 1) < TOLERANCE for value in qpc)
    return {"monotonic_per_raw_min": min(mono), "monotonic_per_raw_max": max(mono),
            "monotonic_per_raw_relative_spread": spread, "raw_per_qpc_within_0_1_percent": qpc_ok,
            "comparable_within_0_1_percent": qpc_ok and spread < TOLERANCE}


def audit_check():
    paths = [WORK / "candidate-audit-before.jsonl", WORK / "candidate-audit-after.jsonl"]
    refs, records, blobs, issues = [], [], [], []
    for path in paths:
        if not path.exists():
            return {"qualified": False, "issues": ["Missing native audit snapshot: " + path.name], "evidence": refs}
        data = path.read_bytes()
        refs.append(reference(path, data))
        blobs.append(data)
        if not data or not data.endswith(b"\n"):
            issues.append(path.name + " is empty or ends with an incomplete record")
        try:
            rows = [json.loads(line) for line in data.splitlines()]
            if not rows or any(not isinstance(row, dict) for row in rows):
                raise ValueError("Empty or non-object audit records")
            if any(any(not isinstance(row.get(key), int) or row[key] < 0 for key in COUNTERS) for row in rows):
                raise ValueError("Invalid cumulative counters")
            records.append(rows)
        except (ValueError, KeyError, TypeError) as exc:
            return {"qualified": False, "issues": issues + [path.name + ": " + str(exc)], "evidence": refs}
    before, after = records
    if not blobs[1].startswith(blobs[0]):
        issues.append("After audit is not an exact continuation of the before snapshot")
    appended = after[len(before):]
    delta = {key: after[-1][key] - before[-1][key] for key in COUNTERS}
    hits = [row for row in appended if row.get("type") == "committed_native64_bulk"]
    if any(value < 0 for value in delta.values()):
        issues.append("Audit counters regressed")
    if delta["committed"] <= 0:
        issues.append("No native64 bulk transaction committed in the candidate window")
    if delta["started"] != delta["committed"] or len(hits) != delta["committed"]:
        issues.append("Started/committed deltas or logged commit count disagree")
    if [row["committed"] for row in hits] != list(range(before[-1]["committed"] + 1, after[-1]["committed"] + 1)):
        issues.append("Commit records are not contiguous")
    if any(row["rolled_back"] or row["failures"] or row.get("result") != 0 for row in after):
        issues.append("Native audit reports rollback, failure, or nonzero result")
    if any(row["started"] != row["committed"] or row.get("phase") != 0 for row in hits + [before[-1], after[-1]]):
        issues.append("An audit endpoint or committed transaction has an unfinished prefix")
    return {"qualified": not issues, "issues": issues, "counter_delta": delta,
            "actual_affected_transactions": len(hits), "before_counters": {key: before[-1][key] for key in COUNTERS},
            "after_counters": {key: after[-1][key] for key in COUNTERS}, "evidence": refs,
            "coverage_scope": "Positive complete logged bounded transactions; no universal or all-layer hit claim",
            "rejected_scope": "Stock-forwarded launches; rejected is not an error counter"}


def render(result):
    checks, metrics = result["qualification"], result["arms"]
    lines = ["# 0.17.3 native bulk BN64 engine cohort", "",
             "Frozen synthetic pseudoprose: 8192 input tokens from 116 repeated calibration units, "
             "128 ordinary output tokens, one excluded warmup and three measured requests per arm. "
             "This is not a natural long-input result and no NPU execution is claimed.", "",
             "| Arm | Native prefill tokens/s | Native decode tokens/s | Accepted/drafted |",
             "|---|---:|---:|---:|"]
    for name in ARMS:
        arm, acceptance = metrics[name], metrics[name]["acceptance"]
        lines.append(f"| {name} | {arm['native_prefill_tps']['mean']:.3f} | {arm['native_decode_tps']['mean']:.3f} | "
                     f"{acceptance['accepted']}/{acceptance['drafted']} |")
    lines += ["", "Rates are means of measured native API response timings. Acceptance counters combine native MTP and PLD "
              "and are reported separately from Prefill and Decode rates.", "",
              f"Request/output hashes and acceptance identical: {checks['identical_request_output_acceptance']}. "
              f"Complete matched windows: {checks['complete_matched_windows']}. Native hit logs qualified: {checks['native_hit_logs']}. "
              f"Three-arm clocks comparable within 0.1%: {checks['three_arm_clocks']}. "
              f"Three-arm comparison qualified: {checks['three_arm_comparison_qualified']}.", "",
              f"Actual affected native64 transactions: {result['native_audit'].get('actual_affected_transactions', 'unavailable')}. "
              "No rollback or failure is allowed for qualification; stock-forwarded rejected launches are reported separately.", ""]
    for name, delta in result["candidate_vs_each_stock_delta_percent"].items():
        lines.append(f"Candidate versus {name}: prefill {delta['prefill']:+.3f}%, decode {delta['decode']:+.3f}%. "
                     f"Pair comparison qualified: {checks['candidate_stock_pair_comparison_qualified'][name]}.")
    pooled = result["candidate_vs_combined_stock_delta_percent"]
    lines += [f"Candidate versus the six pooled stock runs: prefill {pooled['prefill']:+.3f}%, decode {pooled['decode']:+.3f}%.", "",
              "If clock or parity/log qualification fails, raw deltas remain descriptive arithmetic. No clock normalization is applied. "
              "Component evidence justifies this trial; only the bounded full-engine cohort addresses net serving behavior. "
              "These measurements do not independently authorize candidate activation or qualify the broader goal."]
    if result["qualification_issues"]:
        lines += ["", "Qualification issues: " + "; ".join(result["qualification_issues"]) + "."]
    return "\n".join(lines) + "\n"


def main():
    paths = {name: WORK / name / "summary.json" for name in ARMS}
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        raise SystemExit("Summaries are not complete; no analysis written: " + ", ".join(missing))
    arms, evidence = {}, []
    for name, path in paths.items():
        arms[name], ref = load(path)
        evidence.append(ref)
    metrics = {name: summarize(arm) for name, arm in arms.items()}
    all_rows = [row for arm in arms.values() for row in arm["rows"]]
    hashes = [arm.get("request_sha256") for arm in arms.values()]
    outputs = [row.get("output_sha256") for row in all_rows]
    counters = [(row["accepted"], row["drafted"]) for row in all_rows]
    parity = (all(valid_hash(value) for value in hashes + outputs) and len(set(hashes)) == 1
              and len(set(outputs)) == 1 and len(set(counters)) == 1)
    complete = all(arm.get("passed") is True and arm.get("version") == "0.17.3"
                   and arm.get("actual_input_tokens") == 8192 and arm.get("output_tokens") == 128
                   and arm.get("excluded_warmups") == 1 and arm.get("measured_repetitions") == 3
                   and [row.get("phase") for row in arm["rows"]] == ["warmup", "measured", "measured", "measured"]
                   for arm in arms.values())
    ordinary = all(row["usage"]["prompt_tokens"] == 8192 and row["usage"]["completion_tokens"] == 128
                   and row["usage"].get("completion_tokens_details", {}).get("reasoning_tokens", 0) == 0
                   for row in all_rows)
    complete = complete and ordinary
    clocks = clock_check(metrics, ARMS)
    pairs = {name: clock_check(metrics, ("candidate", name)) for name in ("before", "after")}
    audit = audit_check()
    base = parity and complete and audit["qualified"]
    qualified = base and clocks["comparable_within_0_1_percent"]
    stock_pp = [rate for name in ("before", "after") for rate in metrics[name]["measured_native_prefill_tps"]]
    stock_tg = [rate for name in ("before", "after") for rate in metrics[name]["measured_native_decode_tps"]]
    candidate = metrics["candidate"]
    def delta(pp, tg):
        return {"prefill": 100 * (candidate["native_prefill_tps"]["mean"] / pp - 1),
                "decode": 100 * (candidate["native_decode_tps"]["mean"] / tg - 1)}
    issues = []
    if not parity: issues.append("Request/output hashes or acceptance differ")
    if not complete: issues.append("Frozen windows are incomplete, unsuccessful, or do not match the workload")
    issues.extend(audit["issues"])
    if not clocks["comparable_within_0_1_percent"]: issues.append("Three-arm clocks are not comparable within 0.1 percent")
    result = {"schema": "halogen0173.bulk-bn64-engine.cohort.v2-resident-fix", "utc": datetime.now(timezone.utc).isoformat(),
              "version": "0.17.3", "workload": {"type": "synthetic pseudoprose", "actual_input_tokens": 8192,
              "repeated_calibration_units": 116, "output_tokens": 128, "ordinary_output": True,
              "non_repetitive_natural": False, "warmups_per_arm": 1, "measured_runs_per_arm": 3},
              "rate_basis": "Measured native API response.timings rates; no clock normalization",
              "acceptance_scope": "Combined native API MTP+PLD, not isolated MTP", "arms": metrics,
              "request_sha256": hashes[0], "reference_output_sha256": outputs[0], "summary_evidence": evidence,
              "clock_scaling": clocks, "candidate_stock_pair_clock_scaling": pairs, "native_audit": audit,
              "qualification": {"identical_request_output_acceptance": parity, "complete_matched_windows": complete,
              "native_hit_logs": audit["qualified"], "three_arm_clocks": clocks["comparable_within_0_1_percent"],
              "three_arm_comparison_qualified": qualified,
              "candidate_stock_pair_comparison_qualified": {name: base and check["comparable_within_0_1_percent"] for name, check in pairs.items()}},
              "qualification_issues": issues, "stock_combined_native_rates": {"prefill": stats(stock_pp), "decode": stats(stock_tg)},
              "candidate_vs_combined_stock_delta_percent": delta(statistics.fmean(stock_pp), statistics.fmean(stock_tg)),
              "candidate_vs_each_stock_delta_percent": {name: delta(metrics[name]["native_prefill_tps"]["mean"], metrics[name]["native_decode_tps"]["mean"]) for name in ("before", "after")},
              "delta_scope": "Qualified bounded comparison" if qualified else "Descriptive raw arithmetic; three-arm comparison unqualified",
              "component_evidence_scope": "Justifies trial; does not establish full-engine equality or net serving gain",
              "candidate_activation_decision": "Root-owned; this analyzer does not activate the candidate",
              "full_goal_completed": False, "NPU_executed": False}
    destinations = (WORK / "cohort-analysis.json", WORK / "cohort-report.md")
    if any(path.exists() for path in destinations):
        raise SystemExit("Analysis output already exists; preserve the frozen receipt")
    with destinations[0].open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    with destinations[1].open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(render(result))
    print(json.dumps({"qualification": result["qualification"], "native_audit_delta": audit.get("counter_delta"),
                      "candidate_vs_stock_delta_percent": result["candidate_vs_each_stock_delta_percent"],
                      "outputs": [str(path) for path in destinations]}))


if __name__ == "__main__":
    main()
