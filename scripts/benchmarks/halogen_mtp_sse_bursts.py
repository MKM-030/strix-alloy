"""Reconcile client-side Halogen completion bursts with head-only MTP totals."""

import argparse
import base64
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path


THRESHOLD_NS = (3_000_000, 10_000_000)
COUNTERS = ("rounds", "drafted", "accepted")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_events(capture):
    dispatch, header, eof = (capture[key] for key in ("dispatch_qpc_ns", "http_header_qpc_ns", "eof_qpc_ns"))
    require(capture["http_status"] == 200 and all(type(t) is int for t in (dispatch, header, eof))
            and 0 <= dispatch <= header < eof, "Invalid HTTP timing envelope")
    events = []
    previous = header
    done = False
    for row in capture["lines"]:
        time = row["qpc_ns"]
        require(type(time) is int and previous <= time <= eof, "Invalid QPC arrival order")
        previous = time
        line = base64.b64decode(row["base64"], validate=True).strip()
        if not line or line.startswith(b":"):
            continue
        require(line.startswith(b"data: ") and not done, "Unexpected completion SSE line")
        payload = line[6:]
        if payload == b"[DONE]":
            done = True
        else:
            event = json.loads(payload)
            require(type(event) is dict and "error" not in event, "Unexpected completion SSE payload")
            events.append((time, event))
    require(done and len(events) > 2, "Missing or incomplete completion stream")
    return events


def burst_sizes(arrivals, threshold_ns):
    sizes = [1]
    for before, after in zip(arrivals, arrivals[1:]):
        if after - before > threshold_ns:
            sizes.append(1)
        else:
            sizes[-1] += 1
    return sizes


def audit_capture(capture, fixed_depth=None):
    """Return a delivery inference, without assigning native per-round timestamps."""
    events = read_events(capture)
    identities = {event["id"] for _, event in events}
    require(len(identities) == 1 and all(isinstance(value, str) and value for value in identities),
            "Expected one completion identity")
    finish, final = (event for _, event in events[-2:])
    end, = finish["choices"]
    require(end["index"] == 0 and end["finish_reason"] == "length" and end["text"] == "" and final["choices"] == []
            and finish["timings"] == final["timings"], "Expected both matching length-finish and usage frames")

    usage = final["usage"]
    timings = final["timings"]
    input_tokens, output_tokens = (usage[key] for key in ("prompt_tokens", "completion_tokens"))
    require(type(input_tokens) is int and input_tokens > 0 and type(output_tokens) is int
            and output_tokens == len(events) - 2 == timings["predicted_n"]
            and input_tokens == timings["prompt_n"] and timings["cache_n"] == timings.get("disk_restore_n", 0) == 0
            and usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0) == 0,
            "Expected one completion event per token with no prompt reuse or reasoning")

    speculation = timings["speculation"]
    head = speculation["head"]
    rounds, drafted, accepted = (head[key] for key in COUNTERS)
    require(speculation["drafter"] == "mtp" and speculation["rounds"] == rounds
            and all(type(n) is int for n in (rounds, drafted, accepted))
            and rounds > 0 and drafted >= accepted >= 0
            and timings["draft_n"] == drafted and timings["draft_n_accepted"] == accepted
            and all(type(speculation[scope][key]) is int and speculation[scope][key] == 0
                    for scope in ("lookup", "grammar") for key in COUNTERS),
            "Expected head-only MTP accounting")

    arrivals = []
    text = []
    for time, event in events[:-2]:
        choice, = event["choices"]
        require(choice["index"] == 0 and choice["finish_reason"] is None and isinstance(choice["text"], str),
                "Unexpected completion token event")
        arrivals.append(time)
        text.append(choice["text"])
    sizes = burst_sizes(arrivals, THRESHOLD_NS[0])
    require(sizes == burst_sizes(arrivals, THRESHOLD_NS[1]),
            "Delivery groupings differ across the threshold range")
    residual = output_tokens - rounds - accepted
    require(residual in (1, 2) and len(sizes) == rounds + residual and sizes[0] == 1
            and (residual == 1 or sizes[-1] == 1),
            "Delivery groups do not reconcile with native aggregate and singleton boundaries")
    middle = sizes[1:len(sizes) - (residual - 1)]
    inferred = [size - 1 for size in middle]
    require(sum(inferred) == accepted, "Delivery groups do not reconcile with native accepted count")
    if fixed_depth is not None:
        require(type(fixed_depth) is int and fixed_depth >= 1
                and drafted == fixed_depth * rounds and max(inferred) <= fixed_depth,
                "Observed totals or delivery groups do not fit the configured fixed depth")

    return {
        "actual_input": input_tokens, "actual_output": output_tokens, "fixed_depth": fixed_depth,
        "output_sha256": sha256("".join(text).encode()).hexdigest(), "empty_deltas": text.count(""),
        "head": {key: head[key] for key in COUNTERS},
        "threshold_ns": THRESHOLD_NS, "burst_sizes": sizes, "boundary_singletons": residual,
        "inferred_accepted_per_round": inferred,
        "inferred_accepted_count_histogram": dict(sorted(Counter(inferred).items())),
        "inferred_rounds_at_least_rank": [sum(value >= rank for value in inferred)
                                          for rank in range(1, (fixed_depth or max(inferred)) + 1)],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", nargs="+", type=Path)
    parser.add_argument("--fixed-depth", type=int, help="Use only with separately verified fixed-depth activation")
    opts = parser.parse_args()
    rows = []
    for path in opts.captures:
        try:
            raw = path.read_bytes()
            values = audit_capture(json.loads(raw), fixed_depth=opts.fixed_depth)
        except (OSError, KeyError, TypeError, ValueError) as error:
            parser.exit(1, f"{path}: {error}\n")
        rows.append({"capture": str(path), "capture_sha256": sha256(raw).hexdigest(), **values})
    print(json.dumps({"scope": "Client delivery groups reconciled to native aggregate, without native rank attribution",
                      "captures": rows}, indent=2))


if __name__ == "__main__":
    main()
