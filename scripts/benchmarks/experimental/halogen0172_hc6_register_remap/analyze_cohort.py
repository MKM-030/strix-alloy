"""CPU-only validation of the completed native HC6 stock/candidate/stock cohort.

Reads retained JSON/binary evidence only. No inference, HIP, lifecycle, network,
clock normalization, or theoretical-resource-to-rate conversion is performed.
All three complete arms are required. A failed/incomplete cohort cannot qualify
an advantage. This script is intentionally prepared before the cohort finishes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct
import sys

ARMS = ("before", "candidate", "after")
PROFILE_SHA = "b5d3692b2623034f5a9c4a5f90b234ba6b792793196963fc0e7b474b3937c839"
PROMPT_SHA = "0fb44189491024eb0c3f1715828303dd6ba6073641d08ce7a8261f9a3a22c3a1"
REQUEST_SHA = "243037d0ad3993ab3ad57f9a22ac182ecc7b50e6e6320089d7ba98bd3a7ae00b"
OUTPUT_SHA = "0fbe27247d33d2829aa90b66964ff3bb946679be7ce79b379e2555f60ec74fa6"
CODE_SHA = "39053af36ed652892f7082af4eca5cd153b593260448b3c91a67f277cd0f1259"
ENGINE_SHA = "ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913"
MODEL = "halogen-qwen3.8-flash-next"
IMAGE = "ghcr.io/peonist-ai/halogen-flash-server@sha256:0c83ef1093520f0d5b5a00285e59e7ac6b85b1922917fc4a3df95ac5a2638cdd"
CLIENTS = {
    "before": ("window-before-health.py", "d8397f096b8470f4aa3bc3fcebbeb97baba601bdef06779dc6129e1af9dc43f9"),
    "candidate": ("window.py", "143b4deb76bf5897f55e50224876270be492649d044deccf267811babd360601"),
    "after": ("window.py", "143b4deb76bf5897f55e50224876270be492649d044deccf267811babd360601"),
}
MEMORY_FLOOR = 18 * 2**30
NAMES = (
    "hook_calls", "eligible", "candidate_attempts", "stock_calls", "ineligible",
    "busy_or_reentrant", "candidate_errors", "stock_errors", "state", "reason",
    "load_status", "lookup_status", "last_candidate_status", "last_stock_status",
    "get_device_status", "device", "capture_status", "capture_state", "module_loaded",
    "function_resolved", "engine_verified", "code_verified", "init_attempts",
    "disabled_after_error", "code_bytes", "eligible_stock_fallback",
    "reserved26", "reserved27", "reserved28",
)
SIGNED = (
    "load_status", "lookup_status", "last_candidate_status", "last_stock_status",
    "get_device_status", "device", "capture_status", "capture_state",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def read_json(path, pins):
    raw = path.read_bytes()
    pins[str(path)] = {"bytes": len(raw), "sha256": sha(raw)}
    return json.loads(raw)


def read_source(path, expected_sha, pins):
    raw = path.read_bytes()
    pins[str(path)] = {"bytes": len(raw), "sha256": sha(raw)}
    require(sha(raw) == expected_sha, f"pinned measured client source changed: {path.name}")


def healthy_idle(health, label):
    require(health.get("status") == "ok" and health.get("active_requests") == 0
            and health.get("draining") is False and health.get("backend") == "halogen-v2"
            and health.get("checkpoint") == "v2" and health.get("context") == 262144,
            f"health boundary is not idle/healthy on the frozen profile: {label}")
    require(type(health.get("completed")) is int and health["completed"] >= 0
            and type(health.get("cancelled")) is int and health["cancelled"] >= 0,
            f"invalid health request accounting: {label}")


def load_health_boundaries(evidence, arm, record, pins):
    if arm == "before":
        paths = (
            evidence.parent / "gpu-event-attribution-20261009" / "final-ready-open.json",
            evidence / "control-stop-af6dcdd4b42d4b55926fe1e26b04cd97.json",
        )
        receipts = [read_json(path, pins) for path in paths]
        for receipt, label in zip(receipts, ("ready-open", "pre-stop"), strict=True):
            require(receipt.get("profile_sha256") == PROFILE_SHA
                    and receipt["controller"].get("run_id") == record["summary"]["controller_run_id"]
                    and receipt["backend"].get("run_id") == record["summary"]["backend_run_id"]
                    and receipt["controller"].get("phase") == receipt["backend"].get("phase") == "ready",
                    f"before lifecycle health receipt run/profile mismatch: {label}")
        first, final = (receipt["health"] for receipt in receipts)
        source = "retained matching-run ready-open and pre-stop lifecycle receipts"
    else:
        folder = evidence / arm
        first = read_json(folder / "health-before.json", pins)
        final = read_json(folder / "health-after.json", pins)
        require(first == record["summary"].get("first_health")
                and final == record["summary"].get("final_health"),
                f"client health files/summary mismatch: {arm}")
        source = "client GET health boundaries outside timed POSTs"
    healthy_idle(first, arm + " before")
    healthy_idle(final, arm + " after")
    require(final["completed"] - first["completed"] == 4
            and final["cancelled"] == first["cancelled"],
            f"health exclusivity failed (four completions, no cancellations): {arm}")
    return {"first": first, "final": final, "completed_delta": 4,
            "cancelled_delta": 0, "source": source, "qualified": True}


def positive(value, label):
    require(type(value) in (int, float) and math.isfinite(value) and value > 0,
            f"invalid positive native rate: {label}")
    return float(value)


def close(left, right, label):
    require(type(right) in (int, float) and math.isfinite(right) and
            math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-9),
            f"summary does not match native sample calculation: {label}")


def response_contract(response, label):
    require(response.get("model") == MODEL and response.get("object") == "chat.completion",
            f"wrong response model/object: {label}")
    choices, usage, timings = response["choices"], response["usage"], response["timings"]
    require(len(choices) == 1 and choices[0].get("index") == 0 and
            choices[0].get("finish_reason") == "length" and
            choices[0]["message"].get("role") == "assistant", f"wrong choices: {label}")
    require(usage.get("prompt_tokens") == 8192 and usage.get("completion_tokens") == 128
            and usage.get("total_tokens") == 8320 and
            usage.get("completion_tokens_details", {}).get("reasoning_tokens") == 0,
            f"wrong actual token usage: {label}")
    require(timings.get("prompt_n") == 8192 and timings.get("predicted_n") == 128
            and timings.get("cache_n") == 0 and timings.get("disk_restore_n") == 0
            and timings.get("disk_restore_ms") == 0
            and usage.get("cached_tokens", 0) == 0
            and usage.get("prompt_tokens_details", {}).get("cached_tokens", 0) == 0
            and not usage.get("gufo", {}).get("cache_hit")
            and not usage.get("gufo", {}).get("cache_disk_hit")
            and "max_tokens_clamped_from" not in timings,
            f"cached/clamped/inconsistent request: {label}")
    require(type(timings.get("draft_n")) is int and timings["draft_n"] == 113 and
            type(timings.get("draft_n_accepted")) is int and timings["draft_n_accepted"] == 70,
            f"wrong frozen acceptance counters: {label}")
    message = choices[0]["message"]
    text = (message.get("reasoning_content") or "") + (message.get("content") or "")
    require(sha(text.encode()) == OUTPUT_SHA, f"frozen output changed: {label}")
    prefill = positive(timings["prompt_per_second"], label + " prefill")
    decode = positive(timings["predicted_per_second"], label + " decode")
    positive(timings["prompt_ms"], label + " prompt_ms")
    positive(timings["predicted_ms"], label + " predicted_ms")
    # IDs, creation times and native timings intentionally vary by request.
    exact = {"choices": choices, "model": response["model"], "usage": usage}
    return exact, timings, prefill, decode


def load_arm(evidence, arm, pins):
    folder = evidence / arm
    summary = read_json(folder / "summary.json", pins)
    identity = read_json(folder / "identity.json", pins)
    samples = read_json(folder / "samples.json", pins)
    require(summary.get("window") == identity.get("window") == arm,
            f"arm identity mismatch: {arm}")
    require(summary.get("passed") is True and summary.get("version") == "0.17.2"
            and summary.get("actual_input_tokens") == 8192 and summary.get("output_tokens") == 128
            and summary.get("excluded_warmups") == 1 and summary.get("measured_repetitions") == 3,
            f"incomplete/unqualified summary: {arm}")
    require(identity.get("profile_sha256") == PROFILE_SHA and
            identity.get("prompt_sha256") == PROMPT_SHA and
            identity.get("request_sha256") == summary.get("request_sha256") == REQUEST_SHA,
            f"frozen request/prompt/profile mismatch: {arm}")
    require(samples == summary["rows"] and len(samples) == 4,
            f"sample/summary mismatch or incomplete cohort: {arm}")
    controller, backend, manifest = identity["controller"], identity["backend"], identity["manifest"]
    require(controller.get("phase") == backend.get("phase") == "ready" and
            controller.get("profile_sha256") == PROFILE_SHA and backend.get("model") == MODEL,
            f"wrong recorded ready engine/profile/model: {arm}")
    require(summary.get("controller_run_id") == controller.get("run_id") and
            summary.get("backend_run_id") == backend.get("run_id") == manifest.get("run_id")
            and manifest.get("version") == "0.17.2" and manifest.get("image") == IMAGE
            and manifest.get("slots") == backend.get("slots") == 1,
            f"recorded run/manifest mismatch: {arm}")
    env = dict(manifest["environment"])
    if arm == "candidate":
        candidate = manifest["hc6_register_remap_candidate"]
        require(candidate.get("enabled") is True and candidate.get("engine_sha256") == ENGINE_SHA
                and candidate.get("code_sha256") == CODE_SHA and candidate.get("code_bytes") == 17765424,
                "wrong recorded native candidate pin")
        expected = {
            "_hg_flash_serve": "/candidate/hc6-launch.sh",
            "HG0172_HC6_REMAP_CODE": "/candidate/hc6-register-remap.hsaco",
            "HG0172_HC6_REMAP_SHA": CODE_SHA,
            "HG0172_HC6_REMAP_ENGINE_SHA": ENGINE_SHA,
            "HG0172_HC6_REMAP_STATS": candidate["stats_path"],
        }
        for key, value in expected.items():
            require(env.pop(key, None) == value, f"wrong candidate environment: {key}")
    else:
        require("hc6_register_remap_candidate" not in manifest and "_hg_flash_serve" not in env,
                f"candidate marker in stock arm: {arm}")
    require(not any(k.startswith(("HG0172_", "PLE0172_")) for k in env),
            f"unexpected experimental environment: {arm}")
    exact_responses, native_prefill, native_decode = [], [], []
    for rep, row in enumerate(samples):
        label = f"{arm}[{rep}]"
        require(row.get("rep") == rep and row.get("phase") == ("warmup" if rep == 0 else "measured"),
                f"wrong warmup/measured partition: {label}")
        response = read_json(folder / f"response-{rep}.json", pins)
        exact, timings, prefill, decode = response_contract(response, label)
        exact_responses.append(exact)
        require(row.get("timings") == timings and row.get("usage") == response["usage"] and
                row.get("pp_tps") == timings["prompt_per_second"] and
                row.get("decode_tps") == timings["predicted_per_second"],
                f"row rates are not direct native API rates: {label}")
        require(row.get("output_sha256") == OUTPUT_SHA and row.get("finish_reason") == "length"
                and row.get("accepted") == 70 and row.get("drafted") == 113,
                f"row frozen-response accounting mismatch: {label}")
        close(70 / 113, row.get("acceptance"), label + " acceptance")
        minima = row["observed_minimum_memory_bytes"]
        require(all(type(minima.get(k)) is int and minima[k] >= MEMORY_FLOOR
                    for k in ("available_bytes", "commit_headroom_bytes")),
                f"memory floor failed: {label}")
        if rep:
            native_prefill.append(prefill)
            native_decode.append(decode)
    require(all(exact == exact_responses[0] for exact in exact_responses),
            f"choices/model/usage changed within arm: {arm}")
    measured = samples[1:]
    accepted, drafted = sum(r["accepted"] for r in measured), sum(r["drafted"] for r in measured)
    require((accepted, drafted) == (210, 339), f"combined acceptance changed: {arm}")
    close(accepted / drafted, summary.get("acceptance"), arm + " combined acceptance")
    metrics = {}
    for metric, values in (("prefill", native_prefill), ("decode", native_decode)):
        mean, stdev = statistics.fmean(values), statistics.stdev(values)
        close(mean, summary.get(metric + "_mean"), arm + " " + metric + " mean")
        close(stdev, summary.get(metric + "_stdev"), arm + " " + metric + " stdev")
        metrics[metric] = {"native_api_rates_tps": values, "mean_tps": mean,
                           "sample_stdev_tps": stdev, "min_tps": min(values), "max_tps": max(values)}
    return {"identity": identity, "summary": summary, "normalized_environment": env,
            "exact_response": exact_responses[0], "metrics": metrics,
            "accepted": accepted, "drafted": drafted}


def load_stats(evidence, candidate, pins):
    receipt = read_json(evidence / "candidate-stats.json", pins)
    raw = (evidence / "candidate-stats.bin").read_bytes()
    pins[str(evidence / "candidate-stats.bin")] = {"bytes": len(raw), "sha256": sha(raw)}
    require(len(raw) == receipt.get("bytes") == 256 and sha(raw) == receipt.get("sha256"),
            "raw candidate stats receipt mismatch")
    magic, version, size, pid = struct.unpack_from("<8sIIQ", raw)
    require((magic, version, size) == (b"HGHC6R01", 1, 256) and pid == receipt.get("engine_pid") and pid > 0,
            "candidate stats ABI/pid mismatch")
    counters = dict(zip(NAMES, struct.unpack_from("<29Q", raw, 24), strict=True))
    for name in SIGNED:
        if counters[name] >= 2**63:
            counters[name] -= 2**64
    require(counters == receipt.get("counters"), "raw/decoded candidate stats mismatch")
    summary, identity = candidate["summary"], candidate["identity"]
    require(receipt.get("backend_run_id") == summary["backend_run_id"] and
            receipt.get("controller_run_id") == summary["controller_run_id"] and
            receipt.get("manifest_candidate") == identity["manifest"]["hc6_register_remap_candidate"],
            "candidate stats are not bound to the measured candidate engine")
    require(receipt.get("two_identical_idle_reads") is True
            and receipt.get("live_namespace_engine_pid_verified") is True,
            "candidate stats lack stable idle reads or live engine ownership verification")
    health = receipt["health"]
    healthy_idle(health, "candidate stats export")
    require(health.get("status") == "ok" and health.get("active_requests") == 0
            and health.get("draining") is False and receipt.get("inference_performed") is False,
            "candidate stats not exported while idle/healthy")
    require(health["completed"] == candidate["health_boundaries"]["final"]["completed"]
            and health["cancelled"] == candidate["health_boundaries"]["final"]["cancelled"],
            "candidate stats export health accounting differs from completed candidate window")
    require(counters["state"] == 3 and counters["candidate_attempts"] > 0 and
            counters["candidate_attempts"] == counters["eligible"],
            "candidate not READY or no complete native redirect hit accounting")
    for name in ("candidate_errors", "stock_errors", "eligible_stock_fallback", "disabled_after_error", "reason",
                 "busy_or_reentrant", "load_status", "lookup_status", "last_candidate_status",
                 "get_device_status", "device", "capture_status", "capture_state", "reserved26", "reserved27", "reserved28"):
        require(counters[name] == 0, f"candidate error/fallback/nondefault status: {name}")
    require(counters["last_stock_status"] == (0 if counters["stock_calls"] else -1),
            "stock launch status inconsistent with called/not-called accounting")
    for name in ("module_loaded", "function_resolved", "engine_verified", "code_verified", "init_attempts"):
        require(counters[name] == 1, f"candidate initialization not qualified: {name}")
    require(counters["code_bytes"] == 17765424 and
            counters["hook_calls"] == counters["candidate_attempts"] + counters["stock_calls"] and
            counters["hook_calls"] == counters["eligible"] + counters["ineligible"] and
            counters["stock_calls"] == counters["ineligible"], "candidate stats launch balances failed")
    return {"engine_pid": pid, "counters": counters,
            "two_identical_idle_reads": True, "live_namespace_engine_pid_verified": True,
            "scope": "process lifetime, including startup/warmup; not per measured request", "qualified": True}


def compare_metric(arms, metric):
    before, candidate, after = (arms[a]["metrics"][metric] for a in ARMS)
    comparisons = {}
    for arm, stock in (("before", before), ("after", after)):
        delta = candidate["mean_tps"] - stock["mean_tps"]
        comparisons[arm] = {"delta_tps": delta, "delta_percent": 100 * delta / stock["mean_tps"],
                            "candidate_range_above_stock_range": candidate["min_tps"] > stock["max_tps"],
                            "candidate_range_below_stock_range": candidate["max_tps"] < stock["min_tps"]}
    drift = after["mean_tps"] - before["mean_tps"]
    positive_both = all(c["delta_tps"] > 0 for c in comparisons.values())
    above_spread = all(c["candidate_range_above_stock_range"] for c in comparisons.values())
    exceeds_drift = min(c["delta_tps"] for c in comparisons.values()) > abs(drift)
    advantage = positive_both and above_spread and exceeds_drift
    regression = all(c["delta_tps"] < 0 and c["candidate_range_below_stock_range"]
                     for c in comparisons.values()) and min(-c["delta_tps"] for c in comparisons.values()) > abs(drift)
    return {"candidate_vs_stock": comparisons,
            "stock_after_minus_before_tps": drift,
            "stock_after_vs_before_percent": 100 * drift / before["mean_tps"],
            "advantage_outside_observed_spread": advantage,
            "regression_outside_observed_spread": regression,
            "decision": "advantage_outside_this_cohort_spread" if advantage else
                        "regression_outside_this_cohort_spread" if regression else "not_qualified_outside_spread"}


def analyze(evidence):
    pins = {}
    arms = {arm: load_arm(evidence, arm, pins) for arm in ARMS}
    baseline = arms["before"]
    for arm in ARMS:
        record = arms[arm]
        client_file, expected_client_sha = CLIENTS[arm]
        read_source(evidence / client_file, expected_client_sha, pins)
        require(record["identity"]["client_sha256"] == expected_client_sha,
                f"recorded measured client source hash differs: {arm}")
        require(record["normalized_environment"] == baseline["normalized_environment"],
                f"stock profile environment differs: {arm}")
        record["health_boundaries"] = load_health_boundaries(evidence, arm, record, pins)
        require(record["exact_response"] == baseline["exact_response"],
                f"exact choices/model/usage parity failed: {arm}")
        for key in ("version", "image", "checkpoint", "context", "slots", "sources", "speculation_policy", "api_defaults"):
            require(record["identity"]["manifest"].get(key) == baseline["identity"]["manifest"].get(key),
                    f"normal manifest contract differs: {arm}: {key}")
    stats = load_stats(evidence, arms["candidate"], pins)
    metrics = {metric: compare_metric(arms, metric) for metric in ("prefill", "decode")}
    return {"schema": "halogen0172.hc6-register-remap.cohort-analysis.v1",
            "complete": True, "validated": True, "exact_choices_model_usage_parity": True,
            "request_sha256": REQUEST_SHA, "profile_sha256": PROFILE_SHA, "prompt_sha256": PROMPT_SHA,
            "output_sha256": OUTPUT_SHA,
            "client_sha256_by_arm": {a: CLIENTS[a][1] for a in ARMS},
            "allowed_client_delta": "explicit audit-only health-before/after GETs and four-completion/no-cancellation checks outside timed POSTs; request/timing code unchanged",
            "candidate_sha256": CODE_SHA,
            "rate_basis": "native API response.timings rates; no clock normalization",
            "excluded_warmups_per_arm": 1, "measured_repetitions_per_arm": 3,
            "acceptance_each_arm": {"accepted": 210, "drafted": 339, "fraction": 210 / 339},
            "arms": {a: {"controller_run_id": arms[a]["summary"]["controller_run_id"],
                          "backend_run_id": arms[a]["summary"]["backend_run_id"],
                          "completed_utc": arms[a]["summary"]["completed_utc"],
                          "metrics": arms[a]["metrics"],
                          "health_boundaries": arms[a]["health_boundaries"]} for a in ARMS},
            "comparison": metrics, "candidate_stats": stats,
            "prefill_advantage_qualified_for_this_cohort": metrics["prefill"]["advantage_outside_observed_spread"],
            "serving_adoption_qualified": False,
            "qualification_rule": "mean above both stocks, candidate measured range entirely above both stock ranges, minimum mean delta larger than absolute paired stock mean drift",
            "limitations": ["three measured repetitions per arm; no significance/confidence claim",
                            "observed spread is a bounded screen, not a general performance guarantee",
                            "theoretical allocation/residency is not converted to measured rates",
                            "normal final restoration is separately owned and verified by root"],
            "evidence_pins": pins}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    evidence = args.evidence_dir.resolve()
    output = args.output or evidence / "cohort-analysis.json"
    try:
        result = analyze(evidence)
    except (ValueError, KeyError, IndexError, TypeError, OSError, json.JSONDecodeError) as exc:
        result = {"schema": "halogen0172.hc6-register-remap.cohort-analysis.v1",
                  "complete": False, "validated": False,
                  "prefill_advantage_qualified_for_this_cohort": False,
                  "serving_adoption_qualified": False,
                  "error": type(exc).__name__ + ": " + str(exc)}
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result))
        return 2
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"complete": True, "validated": True, "output": str(output),
                      "arms": result["arms"], "comparison": result["comparison"],
                      "prefill_advantage_qualified_for_this_cohort": result["prefill_advantage_qualified_for_this_cohort"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
