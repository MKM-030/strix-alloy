"""Offline audit of retained PLD sample gaps; never measures a live engine.

The samples include observer work. They are not producer deadlines, isolated
verification times, counterfactual savings, or serving token rates.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct


PINS = {
    "decoded.json": "6e4036db6dc008c206badac7101c28fcf46cda90033f5a44723a00668751bd67",
    "journal.h0173sc": "e065d4d415b1b9e67174d8715822faab4c145b8d7f82e2dd253d8e6bb167ac34",
}
FIELDS = ("kind flags seq birth cookie epoch round wire_id raw_ns dropped "
          "source native_flags error reserved tail_reserved").split()
FORMAT = struct.Struct("<II8QIIiIQ")
KEY = ("session_nonce", "owner_birth", "slot_cookie", "slot_epoch", "round")


def audit(directory):
    blobs = {}
    inputs = {}
    for name, pin in PINS.items():
        path = directory / name
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("Retained input size exceeded")
        blob = path.read_bytes()
        if hashlib.sha256(blob).hexdigest() != pin:
            raise ValueError("Retained input pin differs: " + name)
        blobs[name] = blob
        inputs[name] = {"sha256": pin, "bytes": len(blob)}
    decoded = json.loads(blobs["decoded.json"])
    blob = blobs["journal.h0173sc"]
    assert blob[:8] == b"H0173SC1"
    assert struct.unpack_from("<II", blob, 8) == (1, 96)
    assert blob[80:96].hex() == decoded["header"]["session_nonce"]
    assert (len(blob) - 128) % FORMAT.size == 0
    assert all(decoded[k] for k in
               ("dataset_complete", "cost_close_verified", "round_costs_complete"))
    events = [dict(zip(FIELDS, FORMAT.unpack_from(blob, offset)))
              for offset in range(128, len(blob), FORMAT.size)]
    assert all(e["flags"] == 1 and e["error"] == e["dropped"] ==
               e["reserved"] == e["tail_reserved"] == 0 for e in events)
    assert all(a["seq"] < b["seq"] for a, b in zip(events, events[1:]))
    byseq = {e["seq"]: e for e in events}
    rows = {tuple(r[k] for k in KEY): r for r in decoded["rows"]}
    assert len(rows) == len(decoded["rows"])

    def stamp(row, field, kind):
        e = byseq[row[field]]
        assert (e["kind"], e["birth"], e["cookie"], e["epoch"],
                e["round"], e["wire_id"], e["source"]) == (
            kind, row["owner_birth"], row["slot_cookie"], row["slot_epoch"],
            row["round"], row["wire_request_id"],
            {"neural": 1, "pld": 2}[row["source"]])
        return e["raw_ns"]

    pairs = []
    previous_sources = Counter()
    for key, row in rows.items():
        if row["source"] != "pld":
            continue
        prev = rows[key[:-1] + (key[-1] - 1,)]
        begin = stamp(row, "begin_seq", 5)
        prior_begin = stamp(prev, "begin_seq", 5)
        prior_outcome = stamp(prev, "outcome_seq", 6)
        assert prev["outcome_seq"] < row["begin_seq"]
        assert prior_begin <= prior_outcome <= begin
        previous_sources[prev["source"]] += 1
        pairs.append({"begin_seq": row["begin_seq"],
                      "previous_outcome_seq": prev["outcome_seq"],
                      "outcome_to_next_begin_ns": begin - prior_outcome,
                      "begin_to_next_begin_ns": begin - prior_begin})

    def stats(field):
        values = sorted(p[field] for p in pairs)
        return {"count": len(values), "minimum_ns": min(values),
                "median_ns": statistics.median(values),
                "p95_nearest_rank_ns": values[math.ceil(.95 * len(values)) - 1],
                "maximum_ns": max(values)}

    assert len(pairs) == 96 and len(events) == 1714 and len(rows) == 797
    return {"schema": "halogen0173.retained-pld-gaps.v1", "inputs": inputs,
            "clock": "CLOCK_MONOTONIC_RAW", "input_tokens_range": [550, 734],
            "complete_rows": len(rows), "cost_records": len(events),
            "excluded_censored_pairs": decoded["summary"]["censored_pairs"],
            "previous_sources": dict(previous_sources),
            "outcome_to_next_begin": stats("outcome_to_next_begin_ns"),
            "begin_to_next_begin": stats("begin_to_next_begin_ns"),
            "pairs": pairs, "observer_overhead_included": True,
            "natural16k_deadline_measured": False,
            "real_producer_or_serving_gain_qualified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.directory)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "pairs"}))
