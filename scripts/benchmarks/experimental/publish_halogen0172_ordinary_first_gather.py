"""Publish the completed, unqualified ordinary-first-gather fallback experiment.

CPU/file-only. First run analyze_comparison.py against the frozen work directory.
This script requires complete before/candidate/after evidence and the archived
zero-row coverage receipt. Without --publish it validates and prints the proposed
targets without writing. Public copies need an explicit --work argument.
"""

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


WORK = Path(__file__).resolve().parent
STEM = "halogen0172-ordinary-first-gather-20261008"
ANALYZER_NAME = "analyze_halogen0172_ordinary_first_gather.py"
PUBLISHER_NAME = "publish_halogen0172_ordinary_first_gather.py"
WINDOWS = ("before", "candidate", "after")
CELLS = ("p8192-serial-tg1", "p8192-mtp-tg128", "p8192-serial-tg128")
LABELS = {"before": "stock-before", "candidate": "candidate preload + stock fallback", "after": "stock-after"}
MAX_BYTES = 4 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(body):
    return hashlib.sha256(body).hexdigest()


def read(path):
    require(path.is_file() and path.stat().st_size <= MAX_BYTES, "Missing/oversized evidence: " + str(path))
    return path.read_bytes()


def load(path):
    return json.loads(read(path))


def repository(work):
    for parent in work.parents:
        if (parent / "scripts" / "benchmarks").is_dir() and (parent / "server").is_dir():
            return parent
    raise ValueError("Cannot identify repository from frozen work directory")


def relative(path, repo):
    path = Path(path).resolve()
    require(path.is_relative_to(repo), "Public evidence pin outside repository")
    return path.relative_to(repo).as_posix()


def sanitize(value, repo):
    if isinstance(value, dict):
        return {key: relative(item, repo) if key == "path" else sanitize(item, repo)
                for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item, repo) for item in value]
    return value


def settings(work, contract):
    selected = {}
    for name in WINDOWS:
        identity = load(work / name / "identity.json")
        profile = identity["profile"]
        engine, backend = profile["engine"], profile["backend"]
        # Explicit allowlist: never copy credential paths or full profiles.
        selected[name] = {
            "engine_version": contract["engine_version"], "backend": identity["backend"],
            "model": backend["model"], "checkpoint": engine["checkpoint"], "context": identity["context"],
            "expected_slot_context": backend["expected"]["slot_ctx"],
            "expected_kv_pool_positions": backend["expected"]["kv_pool_positions"],
            "expected_slots": backend["expected"]["slots"], "concurrency": profile["concurrency"],
            "cache": engine["prompt_cache"], "draft_tokens_profile_setting": engine["draft_tokens"],
            "speculation_policy": engine["speculation_policy"],
            "prefill_chunk": engine["prefill_chunk"], "max_prefill_tokens": engine["max_prefill_tokens"],
            "console_trace_profile_setting": profile.get("console_trace", False),
            "request_thinking": contract["Thinking"], "temperature": contract["temperature"],
            "seed": contract["seed"], "actual_input_tokens": contract["actual_input_tokens"],
            "output_tokens": contract["output_tokens"], "measured_repetitions": 3, "excluded_warmups": 1,
        }
    return selected


def pooled_stock(report):
    result = {}
    for key in CELLS:
        before = report["windows"]["before"]["cells"][key]
        after = report["windows"]["after"]["cells"][key]
        comparison = report["before_after_variance_and_candidate_changes"][key]
        accepted = sum(cell["native_api_combined_acceptance"]["accepted"] for cell in (before, after))
        drafted = sum(cell["native_api_combined_acceptance"]["drafted"] for cell in (before, after))
        result[key] = {"measured_n": 6,
                       "metrics": {metric: None if comparison[metric] is None else comparison[metric]["pooled_stock_samples"]
                                   for metric in before["metrics"]},
                       "combined_api_mtp_pld_acceptance": {"accepted": accepted, "drafted": drafted,
                                                           "ratio": accepted / drafted if drafted else None}}
    return result


def rate(metric, digits=2):
    return "n/a" if metric is None else f"{metric['mean']:.{digits}f} ± {metric['sample_stdev']:.{digits}f}"


def accepted_text(value):
    return "n/a (0/0)" if value["ratio"] is None else f"{value['accepted']}/{value['drafted']} = {100 * value['ratio']:.2f}%"


def markdown(public):
    lines = ["# Halogen 0.17.2 ordinary-first-gather experiment — 2026-10-08", "",
             "The candidate ran as **preload + stock fallback**. Its exact-version attachment marker was recorded, but **zero completed-row markers** were recorded. Copied-row execution and a serving improvement are unqualified. Numerically higher decode values remain diagnostic and are not attributed to the ordinary-first-gather path.", "",
             "Halogen engine 0.17.2; backend `halogen-v2`, Qwen3.8 Flash Next checkpoint v2; context 262144, expected slot context/KV positions 262144, one expected slot and concurrency 1. Frozen requests use 8192 actual input tokens, 1 or 128 output tokens, serial/MTP drafter, Cache Off, Thinking Off, temperature 0 and seed 1. Profiles request `draft_tokens=2`, `HALOGEN_PLD=3,3`, prefill chunk 8192 and maximum prefill tokens 8192. The draft_tokens setting does not independently establish a fixed per-round MTP depth.", "",
             "## Measured requests", "",
             "Each window/workload has three measured repetitions (rep1–3). Rep0 warmups are excluded. Rates use the frozen harness clock calibration; spread is sample standard deviation (n−1).", "",
             "| Window | Workload | Prefill tok/s | Decode tok/s | Request wall s | Combined API MTP+PLD acceptance |",
             "|---|---|---:|---:|---:|---:|"]
    for name in WINDOWS:
        for key in CELLS:
            cell = public["windows"][name]["cells"][key]
            metrics = cell["metrics"]
            lines.append(f"| {LABELS[name]} | {key} | {rate(metrics['pp_tps'])} | {rate(metrics['decode_tps'])} | {rate(metrics['wall_seconds'], 4)} | {accepted_text(cell['native_api_combined_acceptance'])} |")
    lines += ["", "API `timings.draft_n_accepted` / `timings.draft_n` equals the saved harness accepted/drafted counters. Acceptance is the sum of accepted tokens divided by the sum of drafted tokens across measured requests; it combines MTP and PLD. Native head-only acceptance is unavailable.", "",
              "## Pooled stock before + after", "",
              "The stock pool uses six measured rows per workload. Its sample spread includes within-window variation and between-window drift. Candidate values above describe the fallback experiment.", "",
              "| Workload | Stock pooled prefill tok/s | Stock pooled decode tok/s | Stock pooled request wall s | Stock pooled MTP+PLD acceptance | After vs before prefill / decode / wall |",
              "|---|---:|---:|---:|---:|---:|"]
    for key in CELLS:
        pooled = public["stock_pooled_before_after"][key]
        metrics = pooled["metrics"]
        changes = public["before_after_variance_and_candidate_changes"][key]
        drift = ["n/a" if changes[metric] is None else f"{changes[metric]['after_vs_before_percent']:+.2f}%"
                 for metric in ("pp_tps", "decode_tps", "wall_seconds")]
        lines.append(f"| {key} | {rate(metrics['pp_tps'])} | {rate(metrics['decode_tps'])} | {rate(metrics['wall_seconds'], 4)} | {accepted_text(pooled['combined_api_mtp_pld_acceptance'])} | {' / '.join(drift)} |")
    lines += ["", "## Raw API rates and clocks", "",
              "The frozen harness multiplies each raw API rate by its whole-request monotonic/raw factor. These factors do not independently establish phase-specific correction. The raw/QPC checks passed the existing helper allowance. Both raw and calibrated values are retained to expose this distinction.", "",
              "| Window | Workload | Raw prefill tok/s | Raw decode tok/s | Measured monotonic/raw factor range |",
              "|---|---|---:|---:|---:|"]
    for name in WINDOWS:
        for key in CELLS:
            cell = public["windows"][name]["cells"][key]
            metrics, factors = cell["metrics"], cell["clock_monotonic_per_raw"]
            lines.append(f"| {LABELS[name]} | {key} | {rate(metrics['api_raw_pp_tps'])} | {rate(metrics['api_raw_decode_tps'])} | {factors['min']:.9f}–{factors['max']:.9f} |")
    lines += ["", "## Excluded warmups", "",
              "One rep0 per window/workload is retained here separately. Warmups contribute no measured mean, pooled stock result, or measured acceptance ratio.", "",
              "| Window | Workload | Calibrated prefill tok/s | Calibrated decode tok/s | Request wall s | Accepted/drafted |",
              "|---|---|---:|---:|---:|---:|"]
    for name in WINDOWS:
        for key in CELLS:
            value = public["windows"][name]["cells"][key]["excluded_warmup"]
            decode = "n/a" if value["decode_tps"] is None else f"{value['decode_tps']:.2f}"
            lines.append(f"| {LABELS[name]} | {key} | {value['pp_tps']:.2f} | {decode} | {value['wall_seconds']:.4f} | {value['accepted']}/{value['drafted']} |")
    lines += ["", "## Parity and evidence", "",
              "| Matching workload | Request hash parity | Prompt hash parity | Measured output hash parity |",
              "|---|---|---|---|"]
    for key in CELLS:
        parity = public["parity_by_matching_workload"][key]
        lines.append(f"| {key} | {parity['request_parity']} | {parity['prompt_parity']} | {parity['output_parity']} |")
    lines += ["", "All windows also match serial/MTP measured output hashes for the 128-token workload. Exact parity does not qualify copied-row coverage. No NPU execution, NPU serving gain, long-input improvement, or sustained/generalized improvement is established by this experiment.", "",
              f"Numerical evidence, hash pins, clock factors, sample variances and runtime qualification are in [{STEM}.json]({STEM}.json). Public CPU-only sources: [analyzer](../../scripts/benchmarks/experimental/{ANALYZER_NAME}) and [publisher](../../scripts/benchmarks/experimental/{PUBLISHER_NAME}). Pass the private frozen work directory with `--work`; run the analyzer first, then the publisher with `--publish`. No benchmark, engine, or lifecycle module is imported by either source.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    work = args.work.resolve()
    repo = repository(work)
    report = load(work / "result-analysis" / "analysis.json")
    require(report["schema"] == "halogen0172-ordinary-first-gather-analysis.v1" and
            report["state"] == "complete-series" and report["missing_windows"] == [] and
            set(report["windows"]) == set(WINDOWS), "Full before/candidate/after analysis required; publication refused")
    require(report["full_series_parity_gates_pass"] is True, "Full-series parity gates did not pass")
    for pin in report["source_pins"]:
        path = Path(pin["path"]).resolve()
        require(path.is_relative_to(work), "Analysis source pin outside frozen work directory")
        body = read(path)
        require(len(body) == pin["bytes"] and digest(body) == pin["sha256"], "Stale analysis pin: " + str(path))
    coverage = load(work / "candidate" / "coverage.json")
    qualification = report["runtime_qualification"]["candidate"]
    require(coverage["backend_run_id"] == report["windows"]["candidate"]["halogen_run_id"] and
            len(coverage["attached"]) >= 1 and coverage["complete"] == [] and
            coverage["completed_rows_qualified"] is False and coverage["serving_gain_qualified"] is False and
            qualification["classification"] == "preload-plus-stock-fallback" and
            qualification["completed_row_marker_count"] == 0 and qualification["serving_gain_qualified"] is False and
            qualification["qualified_improvement"] is False and qualification["coverage_evidence"] == coverage,
            "Expected archived zero-row fallback qualification required")
    require(all(report["windows"][name]["cells"][key]["measured_n"] == 3 for name in WINDOWS for key in CELLS),
            "Three measured rows per cell required")
    contract = load(work / "contract.json")
    public = copy.deepcopy(report)
    public.update(public_schema="halogen0172-ordinary-first-gather-public.v1",
                  published_utc=datetime.now(timezone.utc).isoformat(),
                  candidate_classification="preload-plus-stock-fallback", qualified_improvement=False,
                  settings_by_window=settings(work, contract), stock_pooled_before_after=pooled_stock(report))
    public = sanitize(public, repo)
    sources = {
        repo / "scripts" / "benchmarks" / "experimental" / ANALYZER_NAME: read(work / "analyze_comparison.py"),
        repo / "scripts" / "benchmarks" / "experimental" / PUBLISHER_NAME: read(Path(__file__).resolve()),
    }
    public["public_source_pins"] = [{"path": relative(path, repo), "bytes": len(body), "sha256": digest(body)}
                                    for path, body in sources.items()]
    targets = {
        repo / "docs" / "benchmarks" / (STEM + ".json"): (json.dumps(public, indent=2, allow_nan=False) + "\n").encode(),
        repo / "docs" / "benchmarks" / (STEM + ".md"): markdown(public).encode(),
        **sources,
    }
    for path in targets:
        require(path.resolve().is_relative_to(repo), "Publication target outside repository")
    if args.publish:
        for path, body in targets.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
    print(json.dumps({"published": args.publish, "candidate_classification": public["candidate_classification"],
                      "qualified_improvement": False,
                      "targets": [{"path": relative(path, repo), "bytes": len(body), "sha256": digest(body)}
                                  for path, body in targets.items()]}))


if __name__ == "__main__":
    main()
