"""One CPU-only frozen-novel third-ID complement screen; no engine or model.

Derive ONE frozen War and Peace prefix with the existing exact local tokenizer.
Look up the exact suffix AFTER two observed native MTP IDs. Freeze frequency
mode/tie policy before scoring labels. No corpus or candidate is label selected.
"""
from __future__ import annotations

from array import array
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import sys
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]
PREP = OUT.parent
NATURAL = ROOT / "server/.local/long-input-admission-source-20261005"
NATURAL_PREP = NATURAL / "prepared-exact-35fa357dd1ce4d148da75bda2fe994c1"
WORKLOAD = ROOT / "docs/research/halogen-independent-proposer-workload-20261006.json"
WORKLOAD_SHA = "1f3a2fbfafe1a8fd90f99c23dac49f3f0028644d5f010fcd057edfcce26a4919"
TOKENIZER = ROOT / "server/.local/article0162-20261003/tokenizer.json"
TOKENIZER_SHA = "0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3"
TEMPLATE = Path("C:/AI/models/halogen-flashnext/tokenizer/chat_template.jinja")
TEMPLATE_SHA = "c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041"
REQUEST_SHA = "5bd5e9f41aaa89182716d939f2848c66c136f97f403898ceb9d2219de2417046"
REQUEST_CONTENT_SHA = "0fb44189491024eb0c3f1715828303dd6ba6073641d08ce7a8261f9a3a22c3a1"
BODY_SHA = "353693ee8384aaba6ae2b78c75936bd668230d3cec8d7ac2c648351204bc1d23"
INVENTORY_SHA = "c2cdb1c5b429f31c6c6d8e73b053ce3d4be9a66fd323b9fe21154faa16f3bfd4"
MAX_EXTRA = 128 * 1024**2
POLICY = dict(key="exact trailing trigram after observed native pending2",
              continuation="one following token within ONE independently frozen novel prefix",
              source_selection="260000-input natural preparation's longest existing prefix; no label-based selection",
              minimum_observations=1, candidate="maximum continuation frequency",
              tie_rule="lowest numeric raw token ID", backoff=False,
              committed_or_pending_ids_indexed=False, future_labels_indexed=False)


class Memory(C.Structure):
    _fields_ = [("cb", C.c_uint32), ("PageFaultCount", C.c_uint32)] + [(name, C.c_size_t) for name in
                ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                 "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]


kernel = C.WinDLL("kernel32", use_last_error=True)
kernel.GetCurrentProcess.restype = C.c_void_p
process = kernel.GetCurrentProcess()
psapi = C.WinDLL("psapi", use_last_error=True)
psapi.GetProcessMemoryInfo.argtypes = [C.c_void_p, C.c_void_p, C.c_uint32]


def memory() -> dict:
    value = Memory(); value.cb = C.sizeof(value)
    if not psapi.GetProcessMemoryInfo(process, C.byref(value), value.cb):
        raise OSError(C.get_last_error(), "memory counters unavailable")
    return {name: getattr(value, name) for name in ("PrivateUsage", "PeakPagefileUsage", "WorkingSetSize", "PeakWorkingSetSize")}


def memory_limit(baseline: dict) -> int:
    class Basic(C.Structure):
        _fields_ = [("PerProcessUserTimeLimit", C.c_int64), ("PerJobUserTimeLimit", C.c_int64),
                    ("LimitFlags", C.c_uint32), ("MinimumWorkingSetSize", C.c_size_t),
                    ("MaximumWorkingSetSize", C.c_size_t), ("ActiveProcessLimit", C.c_uint32),
                    ("Affinity", C.c_size_t), ("PriorityClass", C.c_uint32), ("SchedulingClass", C.c_uint32)]
    class Io(C.Structure):
        _fields_ = [(name, C.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
    class Extended(C.Structure):
        _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", Io), ("ProcessMemoryLimit", C.c_size_t),
                    ("JobMemoryLimit", C.c_size_t), ("PeakProcessMemoryUsed", C.c_size_t), ("PeakJobMemoryUsed", C.c_size_t)]
    kernel.CreateJobObjectW.restype = C.c_void_p
    kernel.SetInformationJobObject.argtypes = [C.c_void_p, C.c_int, C.c_void_p, C.c_uint32]
    kernel.AssignProcessToJobObject.argtypes = [C.c_void_p, C.c_void_p]
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise OSError(C.get_last_error(), "CPU memory job unavailable")
    info = Extended(); info.BasicLimitInformation.LimitFlags = 0x100
    info.ProcessMemoryLimit = baseline["PrivateUsage"] + MAX_EXTRA
    if not kernel.SetInformationJobObject(job, 9, C.byref(info), C.sizeof(info)) or not kernel.AssignProcessToJobObject(job, process):
        raise OSError(C.get_last_error(), "CPU memory cap unavailable")
    return job  # keep handle alive; no subprocess, process termination, or lifecycle call


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checked(path: Path, expected: str, size: int | None = None) -> bytes:
    if not path.is_file() or not 0 < path.stat().st_size <= 16 * 1024**2:
        raise ValueError("bounded source missing: " + str(path))
    data = path.read_bytes()
    if sha(data) != expected or (size is not None and len(data) != size):
        raise ValueError("source pin differs: " + str(path))
    return data


def ids(data: bytes) -> list[int]:
    if len(data) % 4:
        raise ValueError("raw int32 extent differs")
    values = list(struct.unpack(f"<{len(data)//4}i", data))
    if any(not 0 <= t < 248070 for t in values):
        raise ValueError("token outside defined native vocabulary")
    return values


def publish(name: str, data: bytes) -> None:
    with (OUT / name).open("xb") as stream:
        stream.write(data)


def main() -> None:
    if any((OUT / name).exists() for name in ("result.json", "corpus-ids.i32", "screen-started.json")):
        raise FileExistsError("one screen already retained; no repeat/overwrite")
    baseline = memory(); job = memory_limit(baseline)
    start = time.perf_counter_ns()
    workload = json.loads(checked(WORKLOAD, WORKLOAD_SHA))
    natural_receipt_path = NATURAL_PREP / "offline-preparation-receipt.json"
    natural_receipt_raw = natural_receipt_path.read_bytes()
    natural_receipt = json.loads(natural_receipt_raw)
    source_case = next(c for c in natural_receipt["cases"] if c["actual_input_tokens"] == 260000)
    current_pin_path = PREP / "arena16384-comparison/prompts/manifest.json"
    current_pin_raw = current_pin_path.read_bytes()
    if json.loads(current_pin_raw)["tokenizer_sha256"] != TOKENIZER_SHA:
        raise ValueError("current0172 tokenizer receipt differs")
    checked(TOKENIZER, TOKENIZER_SHA, 12809320)
    template_raw = checked(TEMPLATE, TEMPLATE_SHA, 8952)
    if natural_receipt["chat_template_text_sha256"] != TEMPLATE_SHA:
        raise ValueError("actual local target template differs from frozen binding")
    if natural_receipt["tokenizer_file_pins"]["/home/revn/halogen-models-native/tokenizer/tokenizer.json"] != TOKENIZER_SHA:
        raise ValueError("frozen natural tokenizer differs")
    body = checked(NATURAL / "war-and-peace-body.txt", BODY_SHA)
    corpus_text = body.decode("utf-8")[:source_case["source_prefix_characters"]]
    corpus_utf8 = corpus_text.encode("utf-8")
    del body
    vendor = ROOT / "server/.local/article0162-20261003/vendor"
    sys.path.insert(0, str(vendor))
    import tokenizers
    if tokenizers.__version__ != "0.23.2":
        raise ValueError("already installed CPU package version differs")
    tokenizer = tokenizers.Tokenizer.from_file(str(TOKENIZER))
    tokenizer.no_padding(); tokenizer.no_truncation()
    after_tokenizer_memory = memory()
    seed_rec = workload["seed_source"]
    seed_path = ROOT / seed_rec["file"]
    trace_dir = seed_path.parent
    seed = ids(checked(seed_path, seed_rec["sha256"], seed_rec["bytes"]))
    request_path = trace_dir.parent / "request.json"
    request_raw = checked(request_path, REQUEST_SHA); request = json.loads(request_raw)
    if len(request["messages"]) != 1 or request["messages"][0]["role"] != "user" or not isinstance(request["messages"][0]["content"], str) or request.get("tools") or request.get("enable_thinking") is not False or request.get("chat_template_kwargs", {}).get("enable_thinking") is not False:
        raise ValueError("actual old request is outside the pinned single-user template branch")
    old_content = request["messages"][0]["content"]
    if sha(old_content.encode("utf-8")) != REQUEST_CONTENT_SHA:
        raise ValueError("actual old content differs from recorded calibration")
    # Actual target template lines103/109/164-166: render_content(... )|trim,
    # user opener/end, then thinking-off assistant opener. The actual retained
    # old request is rendered; no natural request text or guessed ID is used.
    rendered = "<|im_start|>user\n" + old_content.strip() + "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
    old_prompt_ids = tokenizer.encode(rendered, add_special_tokens=False).ids
    if len(old_prompt_ids) != len(seed) or old_prompt_ids[1:] != seed[:-1]:
        first_diff = next((i for i,(a,b) in enumerate(zip(old_prompt_ids[1:],seed[:-1])) if a != b), None)
        raise ValueError("exact target tokenizer/old raw native seed mapping not verified: " + str(dict(rendered_tokens=len(old_prompt_ids), native_seed_tokens=len(seed), first_difference=first_diff, rendered_start=old_prompt_ids[:20], native_seed_start=seed[:19])))
    after_mapping_memory = memory()
    # Exclusive marker permits only ONE derivation even if a later step fails.
    publish("screen-started.json", (json.dumps(dict(policy=POLICY, mapping_compared_ids=len(seed)-1,
            old_request_sha256=REQUEST_SHA, target_template_sha256=TEMPLATE_SHA,
            corpus_prefix_characters=source_case["source_prefix_characters"],
            memory_before_derivation=after_mapping_memory), indent=2)+"\n").encode())
    # Corpus contains novel text only: no frame, task, current request, labels,
    # native future outputs, or tokenized teacher continuation is appended.
    tokenize_start = time.perf_counter_ns()
    corpus_encoding = tokenizer.encode(corpus_text, add_special_tokens=False)
    corpus_ids = array("i", corpus_encoding.ids)
    del corpus_encoding, tokenizer, old_prompt_ids, rendered, request, old_content, corpus_text
    if sys.byteorder != "little":
        corpus_ids.byteswap()
    corpus_raw = corpus_ids.tobytes()
    if not 100000 < len(corpus_ids) <= 260000 or min(corpus_ids) < 0 or max(corpus_ids) >= 248070:
        raise ValueError("derived corpus token extent/vocabulary differs")
    tokenize_ns = time.perf_counter_ns() - tokenize_start
    after_corpus_memory = memory()
    trace_rec = workload["trace"]
    trace = [json.loads(line) for line in checked(ROOT / trace_rec["file"], trace_rec["sha256"], trace_rec["bytes"]).splitlines()]
    entries = {r["index"]: r for r in trace if r.get("phase") == "entry"}
    exits = {r["index"]: r for r in trace if r.get("phase") == "exit"}
    inventory = json.loads(checked(trace_dir.parent / "trace-inventory.json", INVENTORY_SHA))["files"]
    image_base = int(exits[0]["caller"], 16) - 0x17DE236
    committed = []
    for rec in workload["authoritative_replay_files"]:
        actual = ids(checked(ROOT / rec["file"], rec["sha256"], rec["bytes"]))
        if actual != rec["ids"]:
            raise ValueError("authoritative committed update differs")
        committed.extend(actual)
    cases = []
    for rec in workload["cases"]:
        offset = rec["committed_output_offset"]
        history_last = committed[offset-1] if offset else seed[-1]
        n = rec["trace_index"] - 1
        entry, exit = entries[n], exits[n]
        if entry["count"] != 1 or exit["count"] != 1 or entry["start_position"] != rec["native_target_base"] or exit["start_position"] != rec["native_target_base"] or entry["caller"] != exit["caller"] or int(entry["caller"], 16)-image_base != 0x17DCF49:
            raise ValueError("actual pending MTP causal record differs")
        name = f"{n:02d}-tokens-i32.bin"; pin = inventory[name]
        pending_first = ids(checked(trace_dir / name, pin["sha256"], pin["bytes"]))
        if pending_first != [rec["native_cached_first_id"]] or entry["draft_cache"][0] != pending_first[0]:
            raise ValueError("actual native cached opening differs")
        if history_last != entry["draft_cache"][1] or entry["draft_cache"][2] != rec["native_target_base"] or rec["native_target_base"] != 8192 + offset:
            raise ValueError("causal committed last ID or pending-cache base differs")
        pending = pending_first + [exit["result"]]
        if any(not 0 <= t < 248070 for t in pending):
            raise ValueError("pending ID outside vocabulary")
        cases.append(dict(base=rec["native_target_base"], query=[history_last]+pending, observed_pending2=pending))
    # Query-aware frequency collection uses no labels and is equivalent to
    # querying a full corpus trigram-frequency table at these exact 15 keys.
    modes = {tuple(c["query"]): {} for c in cases}
    scan_start = time.perf_counter_ns()
    for at in range(3, len(corpus_ids)):
        key = (corpus_ids[at-3], corpus_ids[at-2], corpus_ids[at-1])
        dist = modes.get(key)
        if dist is not None:
            following = corpus_ids[at]; dist[following] = dist.get(following, 0) + 1
    scan_ns = time.perf_counter_ns() - scan_start
    for c in cases:
        dist = modes[tuple(c["query"])]
        selected = min(dist, key=lambda token: (-dist[token], token)) if dist else None
        c.update(candidate_third_id=selected, corpus_occurrences=sum(dist.values()),
                 continuation_counts={str(k): dist[k] for k in sorted(dist)},
                 mode_count=dist[selected] if selected is not None else None)
    # All 15 candidates are now frozen. Only this separate evaluator reads labels.
    for c, rec in zip(cases, workload["cases"]):
        labels = rec["expected_next_ids"]
        offset = rec["committed_output_offset"]
        if labels != committed[offset:offset+len(labels)]:
            raise ValueError("retained evaluation label differs")
        third_match = c["candidate_third_id"] == labels[2] if len(labels) == 3 and c["candidate_third_id"] is not None else None
        c.update(label_count=len(labels), pending2_matches_labels=c["observed_pending2"] == labels[:2],
                 first_pending_matches_label=c["observed_pending2"][0] == labels[0],
                 third_label_match=third_match,
                 usable_third_label_match=c["observed_pending2"] == labels[:2] and third_match is True,
                 evaluator_labels=labels)
    def aggregate(group: list[dict]) -> dict:
        return dict(cases=len(group), candidates=sum(c["candidate_third_id"] is not None for c in group),
                    third_label_matches=sum(c["third_label_match"] is True for c in group),
                    joint_usable_third_matches=sum(c["usable_third_label_match"] for c in group))
    denominators = dict(all_cases=aggregate(cases),
        complete_third_labels=aggregate([c for c in cases if c["label_count"] == 3]),
        correct_pending2_and_complete=aggregate([c for c in cases if c["pending2_matches_labels"] and c["label_count"] == 3]),
        wrong_pending2_and_complete=aggregate([c for c in cases if not c["pending2_matches_labels"] and c["label_count"] == 3]),
        missing_third_label=aggregate([c for c in cases if c["label_count"] != 3]),
        wrong_pending2_all=aggregate([c for c in cases if not c["pending2_matches_labels"]]))
    result = dict(schema="halogen.external-natural-corpus-third-draft.v1", policy=POLICY,
                  corpus=dict(title="War and Peace", source_body_sha256=BODY_SHA,
                      source_prefix_characters=source_case["source_prefix_characters"], utf8_bytes=len(corpus_utf8),
                      text_sha256=sha(corpus_utf8), derived_id_count=len(corpus_ids), derived_ids_sha256=sha(corpus_raw),
                      no_template_or_task=True, independently_frozen_source=True),
                  sources=dict(workload_sha256=WORKLOAD_SHA, tokenizer_sha256=TOKENIZER_SHA,
                      actual_target_template_file=str(TEMPLATE), actual_target_template_sha256=sha(template_raw), old_request_content_sha256=REQUEST_CONTENT_SHA,
                      natural_receipt_sha256=sha(natural_receipt_raw), native0172_tokenizer_receipt_sha256=sha(current_pin_raw),
                      seed_sha256=seed_rec["sha256"], old_request_sha256=sha(request_raw),
                      package_version=tokenizers.__version__, package_binary_sha256=sha((vendor/"tokenizers/tokenizers.pyd").read_bytes())),
                  native_seed_mapping=dict(exact=True, compared_native_ids=len(seed)-1,
                      actual_request_render="pinned target single-user template branch; content.strip() implements explicit |trim",
                      relation="rendered actual old request IDs[1:] == native shifted seed[:-1]; first target output not used as mapping label"),
                  case_count=len(cases), complete_third_label_cases=sum(c["label_count"]==3 for c in cases),
                  candidate_cases=sum(c["candidate_third_id"] is not None for c in cases),
                  usable_third_label_matches=sum(c["usable_third_label_match"] for c in cases), denominators=denominators, cases=cases,
                  cpu_screen_ns=dict(tokenize=tokenize_ns, corpus_scan=scan_ns, complete=time.perf_counter_ns()-start),
                  memory=dict(baseline=baseline, after_tokenizer=after_tokenizer_memory, after_mapping=after_mapping_memory,
                      after_corpus=after_corpus_memory, max_extra_bytes=MAX_EXTRA, job_cap_enforced=True),
                  native_observation_version="0.16.2", source_tokenizer_binding_version="0.17.2",
                  corpus_candidates_label_selected=False, future_output_ids_indexed=False,
                  native0172_acceptance=None, serving_gain_qualified=False, engine_or_hardware_called=False,
                  script_sha256=sha(Path(__file__).read_bytes()))
    end_memory = memory()
    if end_memory["PeakPagefileUsage"] - baseline["PrivateUsage"] > MAX_EXTRA or end_memory["PeakWorkingSetSize"] - baseline["WorkingSetSize"] > MAX_EXTRA:
        raise MemoryError("128MiB extra CPU memory budget exceeded")
    result["memory"]["final"] = end_memory
    publish("corpus-prefix.txt", corpus_utf8)
    publish("corpus-ids.i32", corpus_raw)
    publish("result.json", (json.dumps(result, indent=2, allow_nan=False)+"\n").encode())
    completion_memory = memory()
    if completion_memory["PeakPagefileUsage"] - baseline["PrivateUsage"] > MAX_EXTRA or completion_memory["PeakWorkingSetSize"] - baseline["WorkingSetSize"] > MAX_EXTRA:
        raise MemoryError("128MiB extra CPU memory budget exceeded after publication")
    completion = dict(schema="halogen.external-natural-corpus-third-draft.cpu-memory-completion.v1",
        baseline=baseline, after_result_publication=completion_memory, max_extra_bytes=MAX_EXTRA,
        extra_peak_private_bytes=completion_memory["PeakPagefileUsage"]-baseline["PrivateUsage"],
        extra_peak_working_set_bytes=completion_memory["PeakWorkingSetSize"]-baseline["WorkingSetSize"],
        job_cap_enforced=True, budget_passed=True)
    publish("memory-completion.json", (json.dumps(completion, indent=2)+"\n").encode())
    print(json.dumps({key:result[key] for key in ("case_count","complete_third_label_cases","candidate_cases","usable_third_label_matches")})+"\n"+json.dumps(result["memory"]))
    assert job


if __name__ == "__main__":
    main()
