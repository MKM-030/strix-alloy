#!/usr/bin/env python3
"""Benchmark Halogen over its OpenAI-compatible HTTP API.

The context sweep reports Halogen's engine-side prefill and generation rates.
The concurrency sweep proves that independent requests can run together and
reports both per-session rates and aggregate delivered output throughput.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import pathlib
import statistics
import time
import urllib.request
import uuid


FILLER = (
    "The unified memory architecture changes how inference engines schedule "
    "work across the accelerator and the host processor. "
)


def parse_positive_ints(value: str) -> list[int]:
    result = [int(part.strip()) for part in value.split(",") if part.strip()]
    if not result or any(item <= 0 for item in result):
        raise ValueError("expected one or more comma-separated positive integers")
    return result


def request_json(url: str, body: dict | None = None, timeout: int = 3600) -> tuple[dict, float]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {} if body is None else {"content-type": "application/json"}
    request = urllib.request.Request(url, data=data, headers=headers)
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read())
    return payload, time.perf_counter() - started


def chat_request(api: str, prompt: str, max_tokens: int, timeout: int = 3600) -> tuple[dict, float]:
    return request_json(
        api.rstrip("/") + "/v1/chat/completions",
        {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0,
            "enable_thinking": False,
            "reasoning_effort": "low",
        },
        timeout=timeout,
    )


def calibrate_prompt(api: str) -> dict:
    base, _ = chat_request(api, "x", 1)
    expanded, _ = chat_request(api, "x" + FILLER * 20, 1)
    overhead = int(base["usage"]["prompt_tokens"])
    per_unit = max(
        1e-6,
        (int(expanded["usage"]["prompt_tokens"]) - overhead) / 20.0,
    )
    return {"overhead_tokens": overhead, "tokens_per_filler": per_unit}


def build_prompt(target_tokens: int, calibration: dict, instruction: str) -> str:
    overhead = float(calibration["overhead_tokens"])
    per_unit = float(calibration["tokens_per_filler"])
    # A unique prefix prevents the prefix cache from turning later repetitions
    # into cache benchmarks. The server reports the exact resulting token count.
    need = max(0.0, target_tokens - overhead)
    units = max(1, round(need / per_unit))
    return instruction + "\n" + FILLER * units


def extract_measurement(response: dict, wall_seconds: float, session_label: str) -> dict:
    timings = response.get("timings")
    if not isinstance(timings, dict):
        raise ValueError("response is missing Halogen engine timings")
    usage = response.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("response is missing usage")
    choices = response.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        raise ValueError("response is missing choices")
    content = choices[0].get("message", {}).get("content", "")
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    draft = timings.get("draft_n")
    accepted = timings.get("draft_n_accepted")
    return {
        "request_id": response.get("id"),
        "session_label": session_label,
        "wall_seconds": round(float(wall_seconds), 6),
        "prompt_tokens": int(usage.get("prompt_tokens", 0)),
        "completion_tokens": int(usage.get("completion_tokens", 0)),
        "prompt_ms": float(timings.get("prompt_ms", 0.0)),
        "generation_ms": float(timings.get("predicted_ms", 0.0)),
        "prompt_tokens_per_second": float(timings.get("prompt_per_second", 0.0)),
        "generation_tokens_per_second": float(timings.get("predicted_per_second", 0.0)),
        "cache_tokens": (int(timings["cache_n"]) if "cache_n" in timings else None),
        "draft_tokens": draft,
        "accepted_draft_tokens": accepted,
        "draft_acceptance": (accepted / draft if draft and accepted is not None else None),
        "delivered_tokens_per_second": (
            int(usage.get("completion_tokens", 0)) / wall_seconds if wall_seconds > 0 else None
        ),
        "nonempty": bool(content.strip()),
        "marker_present": session_label.lower() in content.lower(),
        "content": content,
    }


def mean(values: list[float]) -> float:
    return round(statistics.fmean(values), 3) if values else 0.0


def summarize_context(target_tokens: int, rows: list[dict]) -> dict:
    return {
        "target_context_tokens": target_tokens,
        "actual_prompt_tokens_mean": mean([row["prompt_tokens"] for row in rows]),
        "prompt_tokens_per_second_mean": mean(
            [row["prompt_tokens_per_second"] for row in rows]
        ),
        "generation_tokens_per_second_mean": mean(
            [row["generation_tokens_per_second"] for row in rows]
        ),
        "completion_tokens_mean": mean([row["completion_tokens"] for row in rows]),
        "cache_tokens_max": (
            max((row["cache_tokens"] for row in rows), default=0)
            if all(row["cache_tokens"] is not None for row in rows) else None
        ),
        "all_nonempty": all(row["nonempty"] for row in rows),
        "all_markers_present": bool(rows) and all(row.get("marker_present", False) for row in rows),
        "samples": rows,
    }


def summarize_concurrent(rows: list[dict], group_wall_seconds: float, expected: int) -> dict:
    successful = [row for row in rows if not row.get("error") and row.get("nonempty")]
    unique_outputs = len({row.get("content", "") for row in successful})
    marker_checks = [row.get("marker_present", False) for row in successful]
    completion_tokens = sum(int(row.get("completion_tokens", 0)) for row in successful)
    return {
        "requested_sessions": expected,
        "successful_sessions": len(successful),
        "unique_outputs": unique_outputs,
        "group_wall_seconds": round(float(group_wall_seconds), 6),
        "aggregate_generation_tokens_per_second": round(
            completion_tokens / group_wall_seconds if group_wall_seconds > 0 else 0.0,
            3,
        ),
        "per_session_generation_tokens_per_second_mean": mean(
            [float(row["generation_tokens_per_second"]) for row in successful]
        ),
        "all_sessions_succeeded": (
            len(successful) == expected
            and unique_outputs == expected
            and all(marker_checks)
        ),
        "sessions": rows,
    }


def run_context_sweep(
    api: str,
    contexts: list[int],
    max_tokens: int,
    reps: int,
    calibration: dict,
) -> list[dict]:
    output = []
    for target in contexts:
        samples = []
        for rep in range(reps):
            label = f"CTX-{target}-REP-{rep + 1}-{uuid.uuid4().hex[:12]}"
            instruction = (
                f"Begin the response with {label}, then give a detailed technical "
                "analysis of the supplied text. Continue until the output budget is "
                "reached; do not end early."
            )
            prompt = build_prompt(target, calibration, instruction)
            response, wall = chat_request(api, prompt, max_tokens)
            measurement = extract_measurement(response, wall, label)
            if not measurement["nonempty"]:
                raise RuntimeError(f"empty response for context target {target}")
            samples.append(measurement)
        output.append(summarize_context(target, samples))
        print(
            f"context {target}: prompt {output[-1]['actual_prompt_tokens_mean']:.0f}, "
            f"prefill {output[-1]['prompt_tokens_per_second_mean']:.2f} t/s, "
            f"generation {output[-1]['generation_tokens_per_second_mean']:.2f} t/s",
            flush=True,
        )
    return output


def run_concurrency_group(
    api: str,
    sessions: int,
    context_tokens: int,
    max_tokens: int,
    calibration: dict,
) -> dict:
    def one(index: int) -> dict:
        label = f"SESSION-{index + 1:02d}-{uuid.uuid4().hex[:12]}"
        instruction = (
            f"Begin your response with the exact marker {label}. Then give a detailed "
            "technical explanation of why independent inference sessions matter. "
            "Continue until the output budget is reached; do not end early."
        )
        prompt = build_prompt(context_tokens, calibration, instruction)
        try:
            response, wall = chat_request(api, prompt, max_tokens)
            return extract_measurement(response, wall, label)
        except Exception as error:  # Captured in the result instead of hiding a partial failure.
            return {"session_label": label, "error": repr(error), "nonempty": False}

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=sessions) as executor:
        rows = list(executor.map(one, range(sessions)))
    group = summarize_concurrent(rows, time.perf_counter() - started, sessions)
    group["context_target_tokens"] = context_tokens
    print(
        f"concurrency {sessions}: {group['successful_sessions']}/{sessions} succeeded, "
        f"aggregate {group['aggregate_generation_tokens_per_second']:.2f} t/s",
        flush=True,
    )
    return group


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8731")
    parser.add_argument("--contexts", default="512,2048,8192,16384,32768,65536")
    parser.add_argument("--context-max-tokens", type=int, default=128)
    parser.add_argument("--reps", type=int, default=2)
    parser.add_argument("--concurrency", default="1,2,4")
    parser.add_argument("--session-context", type=int, default=8192)
    parser.add_argument("--session-max-tokens", type=int, default=128)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    contexts = parse_positive_ints(args.contexts)
    concurrencies = parse_positive_ints(args.concurrency)
    health, _ = request_json(args.api.rstrip("/") + "/health", timeout=30)
    calibration = calibrate_prompt(args.api)
    result = {
        "schema": "halogen-wsl-benchmark-v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "api": args.api,
        "health": health,
        "configuration": {
            "contexts": contexts,
            "context_max_tokens": args.context_max_tokens,
            "repetitions": args.reps,
            "concurrency": concurrencies,
            "session_context": args.session_context,
            "session_max_tokens": args.session_max_tokens,
        },
        "calibration": calibration,
    }
    result["context_sweep"] = run_context_sweep(
        args.api, contexts, args.context_max_tokens, args.reps, calibration
    )
    result["concurrency_sweep"] = [
        run_concurrency_group(
            args.api,
            sessions,
            args.session_context,
            args.session_max_tokens,
            calibration,
        )
        for sessions in concurrencies
    ]
    result["passed"] = (
        all(item["all_nonempty"] and item["all_markers_present"] for item in result["context_sweep"])
        and all(item["all_sessions_succeeded"] for item in result["concurrency_sweep"])
    )

    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"result: {output}", flush=True)
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
