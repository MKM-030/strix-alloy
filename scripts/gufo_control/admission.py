"""Pure pre-start accounting, not a reservation or runtime safety guarantee."""
import math
import re

GIB = 1 << 30
MAX_BYTES = (1 << 63) - 1
PRELAUNCH_FLOOR = 49 * GIB
RUNTIME_FLOOR = 24 * GIB
COMMIT_RESERVE = 12 * GIB
MAX_SAMPLE_AGE_SECONDS = 5.0
SOURCE_COMMIT = "cff564964e8506c0abb3e530cecb55332187ac6c"
SAMPLE_BYTES = ("available_physical_bytes", "commit_headroom_bytes",
                "dedicated_capacity_bytes", "adapter_dedicated_bytes",
                "adapter_shared_bytes")
ENVELOPE_BYTES = ("gpu_peak_bytes", "host_peak_bytes", "commit_peak_bytes")


def _bytes(value):
    return type(value) is int and 0 <= value <= MAX_BYTES


def _finite_time(value):
    try:
        return type(value) in (int, float) and value >= 0 and math.isfinite(value)
    except OverflowError:
        return False


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def evaluate_admission(sample: dict, envelope: dict, *, now: float) -> dict:
    """Evaluate trusted profile bounds against a fresh, scoped telemetry sample.

    The caller is responsible for binding qualified bounds to its exact model,
    build and request profile, and for proving the telemetry provider's scope.
    No model has been qualified merely because a synthetic fixture passes here.
    """
    reasons = []
    result = {"allowed": False, "reasons": reasons,
              "shared_spill_bytes": None, "predicted_available_bytes": None}
    if not isinstance(sample, dict) or not isinstance(envelope, dict):
        reasons.append("invalid_input")
        return result
    for key in SAMPLE_BYTES:
        if not _bytes(sample.get(key)):
            reasons.append("invalid_counter:" + key)
    for key in ENVELOPE_BYTES:
        if not _bytes(envelope.get(key)):
            reasons.append("invalid_envelope:" + key)
    captured = sample.get("captured_monotonic")
    if not _finite_time(now) or not _finite_time(captured):
        reasons.append("invalid_sample_time")
    elif not 0 <= now - captured <= MAX_SAMPLE_AGE_SECONDS:
        reasons.append("stale_or_future_sample")
    if sample.get("gpu_scope") != "adapter_aggregate" or sample.get("host_scope") != "host_global":
        reasons.append("invalid_counter_scope")
    if not _text(sample.get("adapter_luid")) or not _text(sample.get("provider")):
        reasons.append("missing_counter_identity")
    if sample.get("telemetry_ok") is not True:
        reasons.append("telemetry_unavailable")
    pids = sample.get("other_inference_pids")
    if not isinstance(pids, (list, tuple)) or any(type(p) is not int or p <= 0 for p in pids):
        reasons.append("invalid_process_inventory")
    elif pids:
        reasons.append("other_inference_active")
    if envelope.get("qualified") is not True or not _text(envelope.get("review_id")):
        reasons.append("unqualified_envelope")
    revision = envelope.get("model_revision")
    if envelope.get("source_commit") != SOURCE_COMMIT or not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        reasons.append("invalid_profile_identity")
    if reasons:
        return result
    gpu, host, commit = (envelope[k] for k in ENVELOPE_BYTES)
    if gpu == 0 or commit < gpu + host or gpu + host + COMMIT_RESERVE > MAX_BYTES:
        reasons.append("inconsistent_commit_bound")
    capacity = sample["dedicated_capacity_bytes"]
    local_used = sample["adapter_dedicated_bytes"]
    if capacity == 0 or local_used > capacity:
        reasons.append("inconsistent_dedicated_counter")
    if reasons:
        return result
    spill = max(0, gpu - (capacity - local_used))
    predicted = sample["available_physical_bytes"] - host - spill
    result["shared_spill_bytes"] = spill
    result["predicted_available_bytes"] = predicted
    if sample["available_physical_bytes"] < PRELAUNCH_FLOOR:
        reasons.append("prelaunch_physical_floor")
    if predicted < RUNTIME_FLOOR:
        reasons.append("predicted_physical_floor")
    if sample["commit_headroom_bytes"] - commit < COMMIT_RESERVE:
        reasons.append("commit_floor")
    result["allowed"] = not reasons
    return result
