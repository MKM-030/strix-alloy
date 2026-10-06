"""One finite CPU external-history retrieval screen; no model or engine use."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import sys
import time


MANIFEST = "docs/research/halogen-independent-proposer-workload-20261006.json"
MANIFEST_SHA = "1f3a2fbfafe1a8fd90f99c23dac49f3f0028644d5f010fcd057edfcce26a4919"
CORPUS = "backends/halogen-wsl2/docs/benchmarks/responses-20260925.json"
CORPUS_SHA = "a2cbc6a9d07d098d619169eda74c0fa99349a503bf81d3d9cca4fff78c7c0dee"
TOKENIZER = "server/.local/article0162-20261003/tokenizer.json"
TOKENIZER_SHA = "0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3"
INVENTORY_SHA = "c2cdb1c5b429f31c6c6d8e73b053ce3d4be9a66fd323b9fe21154faa16f3bfd4"
RESPONSE_SHA = "d68ebb8971d89ab55b8aeddeffdc8b2bcda18dff764d96f9f1b66c153a8a1585"
MAX_ID = 248070


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checked(path: Path, digest: str, size: int | None = None) -> bytes:
    data = path.read_bytes()
    if len(data) > 32 * 2**20 or (size is not None and len(data) != size) or sha(data) != digest:
        raise ValueError("Frozen source mismatch: " + str(path))
    return data


def validate_ids(tokens: list[int] | tuple[int, ...]) -> None:
    if any(type(t) is not int or not 0 <= t < MAX_ID for t in tokens):
        raise ValueError("Unsupported token ID")


def read_ids(data: bytes) -> list[int]:
    if len(data) % 4:
        raise ValueError("Invalid int32 fixture")
    tokens = list(struct.unpack("<" + "i" * (len(data) // 4), data))
    validate_ids(tokens)
    return tokens


def id_hash(tokens: list[int] | tuple[int, ...]) -> str:
    return sha(struct.pack("<" + "i" * len(tokens), *tokens))


def external_index(documents: list[tuple[int, ...]]) -> dict[tuple[int, ...], list[tuple[int, int]]]:
    positions: dict[tuple[int, ...], list[tuple[int, int]]] = {}
    for document_id, tokens in enumerate(documents):
        # A source position must have a continuation inside its own document.
        for end in range(2, len(tokens) - 1):
            key = tokens[end - 2:end + 1]
            positions[key] = [(document_id, end)] + positions.get(key, [])[:3]
    return positions


def propose(query: list[int], documents: list[tuple[int, ...]],
            positions: dict[tuple[int, ...], list[tuple[int, int]]], cap: int) -> dict:
    candidates = positions.get(tuple(query[-3:]), [])
    best, best_length = None, 0
    current = len(query) - 1
    for document_id, end in candidates:
        source = documents[document_id]
        length = 0
        while length < 64 and length <= end and length <= current and source[end - length] == query[current - length]:
            length += 1
        if length > best_length:
            best, best_length = (document_id, end), length
    tokens: list[int] = []
    if best is not None and best_length >= 3:
        document_id, end = best
        tokens = list(documents[document_id][end + 1:end + 1 + min(cap, 3)])
    return dict(ids=tokens, backward_match=best_length, selected_position=best,
                keyed_positions=candidates, query_tail_sha256=id_hash(query[-64:]))


def leading_match(proposal: list[int], labels: list[int]) -> int:
    length = 0
    for proposed, actual in zip(proposal, labels):
        if proposed != actual:
            break
        length += 1
    return length


def replay(source_root: Path) -> dict:
    started = time.perf_counter_ns()
    manifest = json.loads(checked(source_root / MANIFEST, MANIFEST_SHA))
    collection = json.loads(checked(source_root / CORPUS, CORPUS_SHA, 33638))
    tokenizer_bytes = checked(source_root / TOKENIZER, TOKENIZER_SHA, 12809320)
    seed_record = manifest["seed_source"]
    trace_directory = (source_root / seed_record["file"]).parent
    response = json.loads(checked(trace_directory.parent / "response.json", RESPONSE_SHA, 1348))
    evaluation_created = response["created"]
    if type(evaluation_created) is not int:
        raise ValueError("Missing evaluation source date")

    # The fixed corpus predates the evaluated response. Deduplication and order
    # depend only on corpus bytes and retained source dates, never target labels.
    unique: dict[str, dict] = {}
    for index, sample in enumerate(collection["samples"]):
        created = sample["response"]["created"]
        message = sample["response"]["choices"][0]["message"]
        if type(created) is not int or created >= evaluation_created or message["role"] != "assistant":
            raise ValueError("Noncausal corpus record")
        text = message["content"]
        if not isinstance(text, str) or not text:
            raise ValueError("Invalid corpus text")
        digest = sha(text.encode("utf-8"))
        record = dict(text=text, text_sha256=digest, created=created, first_sample_index=index,
                      sources=[sample["sourceFile"]], prompt_hashes=[sample["promptUtf8Sha256"]])
        if digest not in unique:
            unique[digest] = record
        else:
            old = unique[digest]
            if old["text"] != text:
                raise ValueError("Corpus text digest collision")
            old["sources"].append(sample["sourceFile"])
            old["prompt_hashes"].append(sample["promptUtf8Sha256"])
    records = sorted(unique.values(), key=lambda x: (x["created"], x["first_sample_index"]))

    vendor = source_root / "server/.local/article0162-20261003/vendor"
    sys.path.insert(0, str(vendor))
    import tokenizers
    if tokenizers.__version__ != "0.23.2":
        raise ValueError("Unexpected installed tokenizer version")
    tokenizer = tokenizers.Tokenizer.from_str(tokenizer_bytes.decode("utf-8"))
    tokenizer.no_truncation()
    tokenizer.no_padding()
    tokenization_start = time.perf_counter_ns()
    documents = [tuple(tokenizer.encode(record["text"], add_special_tokens=False).ids) for record in records]
    for record, tokens in zip(records, documents):
        validate_ids(tokens)
        record["derived_id_count"] = len(tokens)
        record["derived_ids_sha256"] = id_hash(tokens)
        del record["text"]
    tokenization_ns = time.perf_counter_ns() - tokenization_start
    index_start = time.perf_counter_ns()
    positions = external_index(documents)
    index_ns = time.perf_counter_ns() - index_start

    seed = read_ids(checked(source_root / seed_record["file"], seed_record["sha256"], seed_record["bytes"]))
    committed: list[int] = []
    for record in manifest["authoritative_replay_files"]:
        tokens = read_ids(checked(source_root / record["file"], record["sha256"], record["bytes"]))
        if tokens != record["ids"]:
            raise ValueError("Authoritative fixture content mismatch")
        committed.extend(tokens)
    trace_record = manifest["trace"]
    trace = [json.loads(line) for line in checked(source_root / trace_record["file"],
             trace_record["sha256"], trace_record["bytes"]).splitlines()]
    entries = {x["index"]: x for x in trace if x.get("phase") == "entry"}
    exits = {x["index"]: x for x in trace if x.get("phase") == "exit"}
    inventory = json.loads(checked(trace_directory.parent / "trace-inventory.json", INVENTORY_SHA))["files"]
    image_base = int(exits[0]["caller"], 16) - 0x17DE236
    if len(seed) != 8192 or len(committed) != 37 or len(manifest["cases"]) != 15:
        raise ValueError("Unexpected retained workload extent")
    cases = []
    lookup_ns = 0
    for case in manifest["cases"]:
        offset = case["committed_output_offset"]
        history = seed + committed[:offset]
        scalar_index = case["trace_index"] - 1
        entry, exit = entries[scalar_index], exits[scalar_index]
        if (entry["count"] != 1 or exit["count"] != 1
                or entry["start_position"] != case["native_target_base"]
                or exit["start_position"] != case["native_target_base"]
                or entry["caller"] != exit["caller"]
                or int(entry["caller"], 16) - image_base != 0x17DCF49):
            raise ValueError("Pending MTP trace mismatch")
        scalar_name = f"{scalar_index:02d}-tokens-i32.bin"
        pin = inventory[scalar_name]
        scalar = read_ids(checked(trace_directory / scalar_name, pin["sha256"], pin["bytes"]))
        if scalar != [case["native_cached_first_id"]] or entry["draft_cache"][0] != scalar[0]:
            raise ValueError("Pending MTP input mismatch")
        pending = [scalar[0], exit["result"]]
        validate_ids(pending)
        query_start = time.perf_counter_ns()
        normal = propose(history, documents, positions, 3)
        hybrid = propose(history + pending, documents, positions, 1)
        lookup_ns += time.perf_counter_ns() - query_start
        # Future target labels and opening references enter only the evaluator.
        labels = case["expected_next_ids"]
        if labels != committed[offset:offset + len(labels)]:
            raise ValueError("Evaluation label mismatch")
        third_match = hybrid["ids"][0] == labels[2] if hybrid["ids"] and len(labels) == 3 else None
        cases.append(dict(base=case["native_target_base"], normal=normal, hybrid_after_observed_pending2=hybrid,
            observed_pending_ids=pending, normal_leading_matches=leading_match(normal["ids"], labels),
            normal_opening_reference_equal=normal["ids"][0] == case["native_cached_first_id"] if normal["ids"] else None,
            pending2_matches_labels=pending == labels[:2], hybrid_third_label_match=third_match,
            usable_hybrid_third_label_match=pending == labels[:2] and third_match is True,
            scored_label_count=len(labels), stock_accepted_drafts=case["stock_accepted_draft_count"]))
    package_binary = vendor / "tokenizers/tokenizers.pyd"
    return dict(schema="halogen.external-earlier-response-retrieval.v1",
        corpus=dict(source=CORPUS, source_sha256=CORPUS_SHA, sample_count=len(collection["samples"]),
                    unique_document_count=len(documents), total_derived_ids=sum(map(len, documents)),
                    created_min=min(x["created"] for x in records), created_max=max(x["created"] for x in records),
                    deduplication="Exact UTF-8 assistant text; first occurrence; chronological source-date order",
                    documents=records, derivation="Target tokenizer of assistant content only; no template, added specials, padding or truncation; derived retrieval input, not original emitted token truth"),
        tokenizer=dict(source=TOKENIZER, sha256=TOKENIZER_SHA, package_version=tokenizers.__version__,
                       installed_binary_sha256=sha(package_binary.read_bytes()), python=sys.version),
        workload_manifest_sha256=MANIFEST_SHA, evaluation_response_sha256=RESPONSE_SHA,
        evaluation_created=evaluation_created,
        policy=dict(key="exact token trigram", ways=4, min_match=3, max_backward_match=64,
                    max_normal_proposals=3, max_hybrid_extension=1,
                    source_continuation="Only inside the selected earlier-response document; committed request and pending MTP IDs are never indexed"),
        case_count=len(cases), complete_third_label_cases=sum(c["scored_label_count"] == 3 for c in cases),
        normal_candidate_cases=sum(bool(c["normal"]["ids"]) for c in cases),
        normal_leading_label_matches=sum(c["normal_leading_matches"] for c in cases),
        normal_opening_reference_equal_cases=sum(c["normal_opening_reference_equal"] is True for c in cases),
        hybrid_candidate_cases=sum(bool(c["hybrid_after_observed_pending2"]["ids"]) for c in cases),
        usable_hybrid_third_label_matches=sum(c["usable_hybrid_third_label_match"] for c in cases), cases=cases,
        cpu_screen_cost_ns=dict(tokenization=tokenization_ns, index=index_ns, lookup_all_cases=lookup_ns,
                               complete_replay=time.perf_counter_ns() - started),
        recorded_at_utc=datetime.now(timezone.utc).isoformat(), script_sha256=sha(Path(__file__).read_bytes()),
        future_labels_used_for_lookup=False, native_lookup_hit_count=None, native_acceptance=None,
        native_integration_qualified=False, serving_gain_qualified=False, model_loaded=False,
        engine_request_executed=False, GPU_NPU_executed=False,
        scope="One request family; normal external-corpus retrieval is independent of native draft IDs; pending2 extension is explicitly a native-MTP hybrid")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    output = args.output.resolve()
    worktree_root = Path(__file__).resolve().parents[2]
    if output.exists() or not output.is_relative_to(worktree_root):
        raise ValueError("Output must be a new file inside this worktree")
    result = replay(source_root)
    with output.open("x", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("case_count", "normal_candidate_cases",
          "normal_leading_label_matches", "hybrid_candidate_cases", "usable_hybrid_third_label_matches")}))


if __name__ == "__main__":
    main()
