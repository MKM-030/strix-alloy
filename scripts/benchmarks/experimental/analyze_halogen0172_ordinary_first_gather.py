"""CPU/file-only evidence analysis for the frozen ordinary-first-gather series.

This module imports only Python's standard library. It never imports a benchmark,
backend, or controller, and never launches a process or performs a network call.
Run with --allow-partial while the series is being collected. A final report
requires all three windows, three measured repetitions per workload, and one
excluded rep0 warmup per workload. No outliers are removed.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics


WORK = Path(__file__).resolve().parent
WINDOWS = ("before", "candidate", "after")
CELLS = ((8192, 1, "serial"), (8192, 128, "mtp"), (8192, 128, "serial"))
SHA = re.compile(r"[0-9a-f]{64}\Z")
METRICS = ("pp_tps", "decode_tps", "wall_seconds", "api_raw_pp_tps", "api_raw_decode_tps")
MAX_EVIDENCE_BYTES = 4 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_evidence(path, pins):
    require(path.stat().st_size <= MAX_EVIDENCE_BYTES, "Evidence size limit: " + str(path))
    data = path.read_bytes()
    pins.append({"path": str(path), "bytes": len(data), "sha256": digest(data)})
    return data


def load_json(path, pins):
    return json.loads(read_evidence(path, pins))


def number(value, label, positive=False):
    require(type(value) in (int, float) and math.isfinite(value), "Invalid number: " + label)
    require(value > 0 if positive else value >= 0, "Out-of-range number: " + label)
    return value


def close(actual, expected, label):
    require(type(actual) in (int, float) and math.isclose(actual, expected, rel_tol=1e-11, abs_tol=1e-9),
            "Stored/derived mismatch: " + label)


def cell_name(cell):
    size, output, drafter = cell
    return f"p{size}-{drafter}-tg{output}"


def stats(values):
    if all(value is None for value in values):
        return None
    require(all(value is not None for value in values), "Partially missing metric")
    mean = statistics.fmean(values)
    variance = statistics.variance(values)
    stdev = math.sqrt(variance)
    return {"n": len(values), "mean": mean, "median": statistics.median(values),
            "sample_variance": variance, "sample_stdev": stdev,
            "coefficient_of_variation_percent": 100 * stdev / mean if mean else None,
            "min": min(values), "max": max(values), "values": values}


def request_hash(prompt, output, drafter):
    body = {"model": "halogen-v2", "messages": [{"role": "user", "content": prompt}],
            "temperature": 0, "seed": 1, "stream": False, "cache_prompt": False,
            "enable_thinking": False, "reasoning_effort": "none",
            "chat_template_kwargs": {"enable_thinking": False}, "max_tokens": output,
            "drafter": drafter}
    return digest(json.dumps(body, sort_keys=True).encode())


def clock_check(row, label):
    value = row["clock_calibration"]
    first, last = value["before"], value["after"]
    mono, raw, qpc = (number(last[key] - first[key], label + ": clock " + key, True)
                      for key in ("mono", "raw", "qpc"))
    uncertainty = (number(first["roundtrip"], label + ": before roundtrip") +
                   number(last["roundtrip"], label + ": after roundtrip")) / 2
    close(value["monotonic_per_raw"], mono / raw, label + ": monotonic/raw ratio")
    close(value["raw_per_qpc"], raw / qpc, label + ": raw/QPC ratio")
    close(value["window_seconds"], qpc, label + ": clock window")
    close(value["handshake_uncertainty_seconds"], uncertainty, label + ": clock uncertainty")
    # Reuse the frozen ClockProbe.compare allowance; introduce no new timing gate.
    require(abs(raw - qpc) <= max(0.01, uncertainty + 0.002 * qpc),
            label + ": calibration exceeds frozen helper allowance")
    return value["monotonic_per_raw"]


def load_window(name, path, contract, pins):
    summary = load_json(path / "summary.json", pins)
    identity = load_json(path / "identity.json", pins)
    rows = [json.loads(line) for line in read_evidence(path / "samples.jsonl", pins).decode().splitlines()
            if line.strip()]
    prompt = read_evidence(path / "prompt-8192-prose.txt", pins).decode("utf-8")
    prompt = prompt.replace("\r\n", "\n").replace("\r", "\n")
    prompt_sha = digest(prompt.encode())
    require(prompt_sha == contract["prompt"]["sha256"], name + ": copied prompt text differs")
    require(not (path / "failure.json").exists(), name + ": failure receipt present")
    require(summary["passed"] is True, name + ": stored summary did not pass")
    require(summary["backend"] == identity["backend"] == "halogen-v2" and
            summary["context"] == identity["context"] == 262144, name + ": backend/context differs")
    require(summary["run_id"] == identity["managed_run_id"] and identity["halogen_run_id"],
            name + ": missing/mismatched run identity")
    require(summary["harness_sha256"] == identity["client_sha256"] == contract["benchmark_client"]["sha256"],
            name + ": frozen client differs")
    profile_pin = contract["candidate_profile" if name == "candidate" else "stock_profile"]["sha256"]
    require(identity["profile_sha256"] == profile_pin, name + ": frozen profile differs")
    require(summary["cache"] == contract["cache"] == "Off" and
            summary["route"] == "http://127.0.0.1:8840/v1/chat/completions", name + ": cache/route differs")
    require(len(rows) == 12 and summary["samples"] == 9 and len(summary["rows"]) == 3,
            name + ": expected twelve rows, nine measured, three workloads")
    observed_keys = []
    for row in rows:
        cell = (row["size"], row["output"], row["drafter"])
        rep = row["rep"]
        label = name + ": " + cell_name(cell) + ": rep" + str(rep)
        require(cell in CELLS and type(rep) is int and rep in range(4), label + ": unexpected workload/rep")
        require(row["phase"] == ("warmup" if rep == 0 else "measured"), label + ": phase/rep mismatch")
        observed_keys.append((*cell, rep))
        timing, usage = row["timings"], row["usage"]
        require(usage["prompt_tokens"] == timing["prompt_n"] == row["size"] and
                usage["completion_tokens"] == timing["predicted_n"] == row["output"] and
                usage["total_tokens"] == row["size"] + row["output"], label + ": token counts differ")
        require(timing.get("cache_n", 0) == timing.get("disk_restore_n", 0) == 0 and
                usage.get("cached_tokens", 0) == usage.get("prompt_tokens_details", {}).get("cached_tokens", 0) == 0 and
                "max_tokens_clamped_from" not in timing, label + ": cache/clamp observed")
        require(row["prompt_sha256"] == prompt_sha and
                row["request_sha256"] == request_hash(prompt, row["output"], row["drafter"]),
                label + ": request/prompt hash differs from frozen request")
        require(SHA.fullmatch(row["output_sha256"]) is not None and row["finish_reason"] == "length" and
                row["reasoning_present"] is False and
                usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0) == 0,
                label + ": output/thinking state differs")
        factor = clock_check(row, label)
        row["api_raw_pp_tps"] = number(timing["prompt_per_second"], label + ": raw PP", True)
        close(row["pp_tps"], row["api_raw_pp_tps"] * factor, label + ": calibrated PP")
        number(timing["prompt_ms"], label + ": prompt_ms", True)
        number(row["wall_seconds"], label + ": wall", True)
        if row["output"] > 1:
            row["api_raw_decode_tps"] = number(timing["predicted_per_second"], label + ": raw decode", True)
            close(row["decode_tps"], row["api_raw_decode_tps"] * factor, label + ": calibrated decode")
            number(timing["predicted_ms"], label + ": predicted_ms", True)
        else:
            row["api_raw_decode_tps"] = None
            require(row["decode_tps"] is None, label + ": TG1 decode should be unavailable")
        drafted, accepted = row["drafted"], row["accepted"]
        require(type(drafted) is type(accepted) is int and 0 <= accepted <= drafted and
                drafted == timing["draft_n"] and accepted == timing["draft_n_accepted"],
                label + ": native API/harness draft counters differ")
        if row["drafter"] == "mtp":
            require(drafted > 0, label + ": no MTP proposals")
            close(row["acceptance"], accepted / drafted, label + ": acceptance ratio")
        else:
            require(accepted == drafted == 0 and row["acceptance"] is None, label + ": serial acceptance differs")
    expected = {(*cell, rep) for cell in CELLS for rep in range(4)}
    require(len(set(observed_keys)) == len(observed_keys) and set(observed_keys) == expected,
            name + ": missing or duplicate row")

    cells = {}
    for cell in CELLS:
        chosen = sorted((row for row in rows if (row["size"], row["output"], row["drafter"]) == cell),
                        key=lambda row: row["rep"])
        warmup, measured = chosen[0], chosen[1:]
        require(len(measured) == 3 and [row["rep"] for row in measured] == [1, 2, 3],
                name + ": three measured repetitions required")
        metrics = {field: stats([row[field] for row in measured]) for field in METRICS}
        matches = [entry for entry in summary["rows"] if (entry["size"], entry["output"], entry["drafter"]) == cell]
        require(len(matches) == 1 and matches[0]["n"] == 3, name + ": stored workload summary differs")
        stored = matches[0]
        for prefix, metric in (("pp", "pp_tps"), ("decode", "decode_tps")):
            derived = metrics[metric]
            if derived is None:
                require(stored[prefix + "_mean"] is stored[prefix + "_stdev"] is None,
                        name + ": missing TG1 rate differs")
            else:
                close(stored[prefix + "_mean"], derived["mean"], name + ": " + prefix + " mean")
                close(stored[prefix + "_stdev"], derived["sample_stdev"], name + ": " + prefix + " stdev")
        accepted = sum(row["timings"]["draft_n_accepted"] for row in measured)
        drafted = sum(row["timings"]["draft_n"] for row in measured)
        ratio = accepted / drafted if drafted else None
        if ratio is None:
            require(stored["acceptance"] is None, name + ": serial summary acceptance differs")
        else:
            close(stored["acceptance"], ratio, name + ": combined summary acceptance")
        hashes = {field: sorted({row[field] for row in measured})
                  for field in ("request_sha256", "prompt_sha256", "output_sha256")}
        cells[cell_name(cell)] = {
            "workload": {"input_tokens": cell[0], "output_tokens": cell[1], "drafter": cell[2]},
            "measured_n": 3, "measured_repetitions": [1, 2, 3], "excluded_warmup_repetitions": [0],
            "metrics": metrics, "hashes": hashes,
            "within_window_measured_output_parity": len(hashes["output_sha256"]) == 1,
            "warmup_matches_measured_output": hashes["output_sha256"] == [warmup["output_sha256"]],
            "native_api_combined_acceptance": {"accepted": accepted, "drafted": drafted, "ratio": ratio,
                                               "per_measured_row": [{"rep": row["rep"], "accepted": row["accepted"],
                                               "drafted": row["drafted"], "ratio": row["acceptance"]} for row in measured]},
            "native_mtp_head_only_acceptance": {"available": False, "reason": "No native head/PLD split in samples"},
            "clock_monotonic_per_raw": stats([row["clock_calibration"]["monotonic_per_raw"] for row in measured]),
            "excluded_warmup": {field: warmup[field] for field in (*METRICS, "accepted", "drafted", "acceptance")},
        }
    output_parity = cells[cell_name(CELLS[1])]["hashes"]["output_sha256"] == cells[cell_name(CELLS[2])]["hashes"]["output_sha256"]
    return {"state": "complete", "measured_n": 9, "excluded_warmup_n": 3,
            "managed_run_id": identity["managed_run_id"], "halogen_run_id": identity["halogen_run_id"],
            "profile_sha256": identity["profile_sha256"], "harness_sha256": summary["harness_sha256"],
            "measured_at": summary["measured_at"], "cells": cells,
            "serial_mtp_measured_output_parity": output_parity}


def compare(loaded):
    parity, changes = {}, {}
    names = [name for name in WINDOWS if name in loaded]
    for cell in CELLS:
        key = cell_name(cell)
        selected = {name: loaded[name]["cells"][key] for name in names}
        parity[key] = {"windows_compared": names, "full_series": len(names) == 3,
                      **{field.replace("_sha256", "_parity"): len({value for entry in selected.values()
                           for value in entry["hashes"][field]}) == 1
                         for field in ("request_sha256", "prompt_sha256", "output_sha256")}}
        if not all(name in loaded for name in ("before", "after")):
            continue
        before, after = selected["before"], selected["after"]
        entry = {}
        for metric in METRICS:
            first, last = before["metrics"][metric], after["metrics"][metric]
            if first is None:
                entry[metric] = None
                continue
            reference = (first["mean"] + last["mean"]) / 2
            detail = {"before_mean": first["mean"], "after_mean": last["mean"], "stock_bookend_mean": reference,
                      "after_minus_before": last["mean"] - first["mean"],
                      "after_vs_before_percent": 100 * (last["mean"] / first["mean"] - 1),
                      "before_sample_stdev": first["sample_stdev"], "after_sample_stdev": last["sample_stdev"],
                      "pooled_stock_samples": stats(first["values"] + last["values"])}
            if "candidate" in selected:
                current = selected["candidate"]["metrics"][metric]
                detail.update(candidate_mean=current["mean"], candidate_sample_stdev=current["sample_stdev"],
                              candidate_vs_before_percent=100 * (current["mean"] / first["mean"] - 1),
                              candidate_vs_after_percent=100 * (current["mean"] / last["mean"] - 1),
                              candidate_vs_stock_bookend_mean_percent=100 * (current["mean"] / reference - 1))
            entry[metric] = detail
        acceptance = {name: entry["native_api_combined_acceptance"] for name, entry in selected.items()}
        first_ratio, last_ratio = acceptance["before"]["ratio"], acceptance["after"]["ratio"]
        entry["native_api_combined_acceptance"] = {"windows": acceptance}
        if first_ratio is not None:
            reference = (first_ratio + last_ratio) / 2
            entry["native_api_combined_acceptance"].update(
                stock_bookend_mean_ratio=reference, after_vs_before_percentage_points=100 * (last_ratio - first_ratio))
            if "candidate" in acceptance:
                entry["native_api_combined_acceptance"]["candidate_vs_stock_bookend_mean_percentage_points"] = 100 * (acceptance["candidate"]["ratio"] - reference)
        changes[key] = entry
    return parity, changes


def runtime_qualification(work, candidate_dir, loaded, pins):
    path = work / candidate_dir / "coverage.json"
    if "candidate" not in loaded or not path.is_file():
        return {"candidate": {"classification": "runtime-coverage-unavailable",
                              "completed_rows_qualified": False, "serving_gain_qualified": False,
                              "qualified_improvement": False}}
    coverage = load_json(path, pins)
    require(coverage["backend_run_id"] == loaded["candidate"]["halogen_run_id"],
            "Candidate coverage belongs to a different engine run")
    attached, completed = coverage["attached"], coverage["complete"]
    require(type(attached) is type(completed) is list and
            all(type(marker) is str for marker in attached + completed), "Invalid candidate coverage markers")
    require(type(coverage["completed_rows_qualified"]) is type(coverage["serving_gain_qualified"]) is bool,
            "Invalid runtime qualification flags")
    zero_rows = len(completed) == 0
    return {"candidate": {
        "classification": "preload-plus-stock-fallback" if attached and zero_rows else "runtime-coverage-unqualified",
        "backend_run_id": coverage["backend_run_id"], "observed_utc": coverage["utc"],
        "attachment_marker_count": len(attached), "completed_row_marker_count": len(completed),
        "completed_rows_qualified": coverage["completed_rows_qualified"],
        "serving_gain_qualified": False, "qualified_improvement": False,
        "measured_rates_attributable_to_ordinary_page_order": False,
        "reason": "Attachment recorded; zero completed-row coverage; candidate used stock fallback" if zero_rows else
                  "Runtime coverage does not by itself qualify an improvement",
        "coverage_evidence": coverage,
    }}


def markdown(report):
    lines = ["# Ordinary-first-gather frozen workload evidence", "",
             "State: " + report["state"] + ". All rates below exclude rep0 warmups; each reported cell uses exactly three measured rows.", "",
             "Candidate runtime classification: " + report["runtime_qualification"]["candidate"]["classification"] +
             ". No qualified improvement; measured rates are diagnostic.", "",
             "| Window | Workload | Prefill tok/s mean ± sample SD | Decode tok/s mean ± sample SD | Request wall seconds mean ± sample SD | Combined API MTP+PLD acceptance |",
             "|---|---|---:|---:|---:|---:|"]
    def formatted(metric, digits=2):
        return "unavailable" if metric is None else f"{metric['mean']:.{digits}f} ± {metric['sample_stdev']:.{digits}f}"
    for name in WINDOWS:
        if name not in report["windows"]:
            continue
        for key, cell in report["windows"][name]["cells"].items():
            metrics, accepted = cell["metrics"], cell["native_api_combined_acceptance"]
            rate = "not applicable (0/0)" if accepted["ratio"] is None else f"{accepted['accepted']}/{accepted['drafted']} = {100 * accepted['ratio']:.2f}%"
            lines.append(f"| {name} | {key} | {formatted(metrics['pp_tps'])} | {formatted(metrics['decode_tps'])} | {formatted(metrics['wall_seconds'], 4)} | {rate} |")
    lines += ["", "The native API fields `timings.draft_n_accepted` and `timings.draft_n` equal the saved harness accepted/drafted counters. Their measured aggregate is sum accepted divided by sum drafted; this combines MTP and PLD. Head-only native MTP acceptance is unavailable in these samples.", "",
              "The frozen harness multiplies raw API rates by each whole-request monotonic/raw clock factor. The following values preserve the raw rates and factor variation; these saved whole-request factors do not independently establish phase-specific correction.", "",
              "| Window | Workload | Raw API prefill mean tok/s | Raw API decode mean tok/s | Measured monotonic/raw factor range |",
              "|---|---|---:|---:|---:|"]
    for name in WINDOWS:
        if name not in report["windows"]:
            continue
        for key, cell in report["windows"][name]["cells"].items():
            metrics, factors = cell["metrics"], cell["clock_monotonic_per_raw"]
            raw_decode = metrics["api_raw_decode_tps"]
            decode_text = "unavailable" if raw_decode is None else f"{raw_decode['mean']:.3f}"
            lines.append(f"| {name} | {key} | {metrics['api_raw_pp_tps']['mean']:.3f} | {decode_text} | {factors['min']:.9f}–{factors['max']:.9f} |")
    lines += ["", "Sample variance, medians, minima/maxima, raw API rates, clock factors, warmup values, hashes and source file pins are retained in analysis.json.", "",
              "| Workload | Windows present | Request parity | Prompt parity | Measured output parity |",
              "|---|---|---|---|---|"]
    for key, parity in report["parity_by_matching_workload"].items():
        lines.append(f"| {key} | {', '.join(parity['windows_compared'])} | {parity['request_parity']} | {parity['prompt_parity']} | {parity['output_parity']} |")
    if report["before_after_variance_and_candidate_changes"]:
        lines += ["", "| Workload / metric | Stock after vs before | Candidate vs stock bookend mean |",
                  "|---|---:|---:|"]
        for key, changes in report["before_after_variance_and_candidate_changes"].items():
            for metric in ("pp_tps", "decode_tps", "wall_seconds"):
                value = changes[metric]
                if value is None:
                    continue
                candidate_delta = value.get("candidate_vs_stock_bookend_mean_percent")
                candidate_text = "unavailable" if candidate_delta is None else f"{candidate_delta:+.2f}%"
                lines.append(f"| {key} / {metric} | {value['after_vs_before_percent']:+.2f}% | {candidate_text} |")
    lines += ["", report["claim_scope"], ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--candidate-dir", default="candidate")
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    require(Path(args.candidate_dir).name == args.candidate_dir, "Candidate directory must be a single name")
    work = args.work.resolve()
    output = (args.out or work / "result-analysis").resolve()
    require(output.is_relative_to(work), "Outputs must stay within comparison work directory")
    pins = []
    read_evidence(Path(__file__).resolve(), pins)
    contract = load_json(work / "contract.json", pins)
    require(contract["schema"] == "halogen0172-ordinary-first-gather-comparison.v1" and
            contract["actual_input_tokens"] == 8192 and contract["output_tokens"] == [1, 128] and
            contract["measured_repetitions"] == 3 and contract["excluded_warmups"] == 1 and
            contract["Thinking"] is False and contract["temperature"] == 0 and contract["seed"] == 1,
            "Frozen contract geometry/control differs")
    loaded, missing = {}, []
    for name in WINDOWS:
        path = work / (args.candidate_dir if name == "candidate" else name)
        if all((path / filename).is_file() for filename in ("summary.json", "identity.json", "samples.jsonl", "prompt-8192-prose.txt")):
            loaded[name] = load_window(name, path, contract, pins)
        else:
            missing.append(name)
    require(loaded, "No complete cohort evidence available")
    require(args.allow_partial or not missing, "Missing complete cohort evidence: " + ", ".join(missing))
    parity, changes = compare(loaded)
    qualification = runtime_qualification(work, args.candidate_dir, loaded, pins)
    complete = not missing
    gates_pass = complete and all(all(item[field] for field in ("request_parity", "prompt_parity", "output_parity")) for item in parity.values()) and all(window["serial_mtp_measured_output_parity"] and all(cell["within_window_measured_output_parity"] for cell in window["cells"].values()) for window in loaded.values())
    report = {"schema": "halogen0172-ordinary-first-gather-analysis.v1",
              "generated_utc": datetime.now(timezone.utc).isoformat(),
              "state": "complete-series" if complete else "partial-series", "missing_windows": missing,
              "measured_only": True, "required_measured_rows_per_cell": 3, "excluded_rep": [0],
              "statistics_scope": "Arithmetic means; sample variance/stdev (n-1); no outlier removal; descriptive comparison of one frozen workload and three measured repetitions per cell",
              "acceptance_definition": "Sum native API timings.draft_n_accepted / sum native API timings.draft_n over measured MTP requests; combined MTP+PLD; identical saved harness counters",
              "native_mtp_head_only_acceptance_available": False,
              "windows": loaded, "parity_by_matching_workload": parity,
              "before_after_variance_and_candidate_changes": changes, "full_series_parity_gates_pass": gates_pass,
              "runtime_qualification": qualification,
              "claim_scope": "No serving speed or acceptance gain is claimed by this file-only analysis. " +
                ("Full-series descriptive deltas are available; candidate runtime coverage remains unqualified. They do not establish long-input generalization, sustained behavior, or an NPU gain." if complete else
                 "The series is incomplete; absent windows: " + ", ".join(missing) + ". Candidate runtime qualification is also required for attribution."),
              "source_pins": pins}
    output.mkdir(parents=True, exist_ok=True)
    (output / "analysis.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output / "analysis.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"state": report["state"], "missing_windows": missing,
                      "full_series_parity_gates_pass": gates_pass, "output_directory": str(output)}))


if __name__ == "__main__":
    main()
