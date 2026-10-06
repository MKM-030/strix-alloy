"""Frozen owned-ID lookup policy replay. No model, service, hook or hardware use.

Suffix lookup adapted from Strata v0.1.40, commit
1735d6471df29b42c26170efaac1f1446a58640f (src/spec/suffix_drafter.cpp).

MIT License
Copyright (c) 2026 Niko1221 and the Strata contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
MASK = (1 << 64) - 1
MANIFEST = ROOT / "docs/research/halogen-independent-proposer-workload-20261006.json"
MANIFEST_SHA = "1f3a2fbfafe1a8fd90f99c23dac49f3f0028644d5f010fcd057edfcce26a4919"
INVENTORY_SHA = "c2cdb1c5b429f31c6c6d8e73b053ce3d4be9a66fd323b9fe21154faa16f3bfd4"


def checked(path: Path, digest: str, size: int | None = None) -> bytes:
    data = path.read_bytes()
    if len(data) > 2**20 or (size is not None and len(data) != size):
        raise ValueError("Frozen fixture length mismatch: " + str(path))
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Frozen fixture hash mismatch: " + str(path))
    return data


def ids(data: bytes) -> list[int]:
    if len(data) % 4:
        raise ValueError("Invalid int32 fixture")
    result = list(struct.unpack("<" + "i" * (len(data) // 4), data))
    if any(t < 0 or t >= 248070 for t in result):
        raise ValueError("Unsupported token ID")
    return result


def native_hash(window: list[int]) -> int:
    value = 0x14650FB0739D0383
    for token in window:
        value = ((value ^ token) * 0x100000001B3) & MASK
        value ^= value >> 29
    return value


def mix(value: int) -> int:
    value ^= value >> 33
    value = (value * 0xFF51AFD7ED558CCD) & MASK
    value ^= value >> 33
    value = (value * 0xC4CEB9FE1A85EC53) & MASK
    return value ^ (value >> 33)


def strata_key(window: list[int]) -> int:
    a, b, c = window
    return mix(((a * 0x9E3779B97F4A7C15) & MASK) ^ mix(b + 0x632BE59BD9B4E019) ^ (c << 1)) | 1


def indexes(history: list[int]) -> tuple[dict[int, int], dict[int, list[int]]]:
    newest = {}
    ways = {}
    for end in range(2, len(history)):
        key = strata_key(history[end - 2:end + 1])
        ways[key] = [end] + ways.get(key, [])[:3]
        if end < len(history) - 1:
            newest[native_hash(history[end - 2:end + 1])] = end + 1
    return newest, ways


def propose(history: list[int], ways: dict[int, list[int]], pending: list[int], cap: int) -> dict:
    query = history + pending  # pending IDs are never added to the index
    cur = len(query) - 1
    best_end, best_length = -1, 0
    positions = ways.get(strata_key(query[-3:]), [])
    for end in positions:
        if end >= cur:
            continue
        length = 0
        while length < 64 and length <= end and query[end - length] == query[cur - length]:
            length += 1
        if length > best_length:
            best_end, best_length = end, length
    tokens = query[best_end + 1:min(cur + 1, best_end + 1 + cap)] if best_length >= 3 else []
    return dict(ids=tokens, backward_match=best_length, keyed_positions=positions)


def replay() -> dict:
    manifest = json.loads(checked(MANIFEST, MANIFEST_SHA))
    seed = manifest["seed_source"]
    seed_path = ROOT / seed["file"]
    trace_dir = seed_path.parent
    history_seed = ids(checked(seed_path, seed["sha256"], seed["bytes"]))
    assert len(history_seed) == 8192
    trace_record = manifest["trace"]
    trace = [json.loads(line) for line in checked(ROOT / trace_record["file"],
        trace_record["sha256"], trace_record["bytes"]).splitlines()]
    inventory = json.loads(checked(trace_dir.parent / "trace-inventory.json", INVENTORY_SHA))["files"]
    entries = {x["index"]: x for x in trace if x.get("phase") == "entry"}
    exits = {x["index"]: x for x in trace if x.get("phase") == "exit"}
    image_base = int(exits[0]["caller"], 16) - 0x17DE236
    committed = []
    for record in manifest["authoritative_replay_files"]:
        actual = ids(checked(ROOT / record["file"], record["sha256"], record["bytes"]))
        assert actual == record["ids"]
        committed.extend(actual)
    assert len(committed) == 37 and len(manifest["cases"]) == 15
    cases = []
    for case in manifest["cases"]:
        offset = case["committed_output_offset"]
        history = history_seed + committed[:offset]  # no future labels supplied
        newest, ways = indexes(history)
        native_j = newest.get(native_hash(history[-3:]))
        normal = propose(history, ways, [], 3)
        scalar_index = case["trace_index"] - 1
        entry, exit = entries[scalar_index], exits[scalar_index]
        assert entry["count"] == exit["count"] == 1
        assert entry["start_position"] == exit["start_position"] == case["native_target_base"]
        assert int(entry["caller"], 16) - image_base == 0x17DCF49
        assert entry["caller"] == exit["caller"]
        scalar_file = f"{scalar_index:02d}-tokens-i32.bin"
        scalar_pin = inventory[scalar_file]
        scalar_input = ids(checked(trace_dir / scalar_file, scalar_pin["sha256"], scalar_pin["bytes"]))
        assert scalar_input == [case["native_cached_first_id"]]
        assert entry["draft_cache"][0] == scalar_input[0]
        pending = [scalar_input[0], exit["result"]]
        assert all(0 <= t < 248070 for t in pending)
        hybrid = propose(history, ways, pending, 1)
        # Evaluation happens only after the history-only proposal is complete.
        expected = case["expected_next_ids"]
        assert expected == committed[offset:offset + len(expected)]
        earlier_match = pending == expected[:2]
        third_matches = hybrid["ids"][0] == expected[2] if hybrid["ids"] and len(expected) == 3 else None
        cases.append(dict(base=case["native_target_base"], known_history_tokens=len(history),
            native_known_history_ids=history[native_j:native_j+3] if native_j is not None else [],
            strata_same_prefix=normal, observed_native_mtp_pending=pending,
            strata_after_two_pending=hybrid, prior_two_match_labels=earlier_match,
            extension_matches_third_label=third_matches,
            usable_third_label_match=earlier_match and third_matches is True,
            omitted_first_trigram_exact_match_possible_normal=history_seed[:2] == history[-2:],
            omitted_first_trigram_exact_match_possible_after_two_pending=history_seed[:2] == pending[-2:]))
    return dict(schema="halogen.strata-owned-lookup-replay.v1", request_families=1,
        cases=cases, case_count=15, complete_third_label_cases=14,
        manifest_sha256=MANIFEST_SHA, script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        native_known_history_candidates=sum(bool(c["native_known_history_ids"]) for c in cases),
        strata_same_prefix_candidates=sum(bool(c["strata_same_prefix"]["ids"]) for c in cases),
        after_two_pending_candidates=sum(bool(c["strata_after_two_pending"]["ids"]) for c in cases),
        usable_third_label_matches=sum(c["usable_third_label_match"] for c in cases),
        scope="Frozen owned-token arithmetic reconstruction, including declared native MTP inputs; not an independent neural producer or native execution",
        original_prompt_first_id_guessed=False, future_labels_used_for_lookup=False,
        native_lookup_hit_count=None, native_acceptance=None, prefill_tok_s=None, decode_tok_s=None,
        serving_gain_qualified=False, GPU_NPU_executed=False, engine_request_executed=False,
        controller_integration_qualified=False, policy_timing_measured=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output.resolve()
    if output.exists() or not output.is_relative_to(ROOT):
        raise ValueError("Output must be a new workspace file")
    result = replay()
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("case_count", "native_known_history_candidates",
        "strata_same_prefix_candidates", "after_two_pending_candidates", "usable_third_label_matches")}))


if __name__ == "__main__":
    main()
