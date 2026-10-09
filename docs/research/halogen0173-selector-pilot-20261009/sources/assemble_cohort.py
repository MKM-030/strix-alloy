"""Offline assembly of root-owned request/asset/native evidence; no runtime calls.

Reads completed capture artifacts and any completed normal bookends. It never
imports lifecycle controls, reads credentials, rehashes large model weights,
assigns metadata to the native decoder, or executes a predictor. The separate
check_cohort.py reviewer remains required before fitting the collected manifest.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct

WORK = Path(__file__).resolve().parent
PREP = WORK.parent
ROOT = PREP.parents[3]
CORPUS = PREP / "selector-real-request-provenance-20261009"
BACKEND = ROOT / "backends/halogen-wsl2-0.17.3"
CORPUS_SHA = "76de0b548bfb48f028e50bf8517e8f9514d2cbbc03eb48668d445b834b59960c"
ROOT_RECORDED_CLIENT_SHA = "55d95c1f287a7c9e7a6f02dd59ce1f93a23b9d467f86a8a442d0895858ca2bd3"
RUNTIME_SHA = "af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7"
EVENT = struct.Struct("<II6QIiQ4I6iIiII8Q64i16i")
EVENT_FIELDS = ("kind", "flags", "seq", "birth", "cookie", "epoch", "round", "wire_id",
                "source", "status", "dropped", "context_total", "context_count", "offer_total",
                "offer_count", "current_id", "opening_id", "depth_low", "depth_high", "stock_width",
                "native_allowance", "transported_count", "model_position", "adaptive", "reserved")
MAX_FILE = 128 << 20


def require(condition, message):
    if not condition:
        raise ValueError(message)


def data(path):
    path = Path(path)
    before = path.stat()
    require(path.is_file() and before.st_size <= MAX_FILE, "Missing/unbounded evidence: " + str(path))
    value = path.read_bytes()
    after = path.stat()
    require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns) and
            len(value) == before.st_size, "Evidence changed while read: " + str(path))
    return value


def read(path):
    return json.loads(data(path))


def reference(path):
    path = Path(path).resolve(strict=True)
    value = data(path)
    return dict(path=str(path), bytes=len(value), sha256=hashlib.sha256(value).hexdigest())


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def retain(source, destination):
    """Copy external mutable log/receipt paths to fresh immutable local evidence."""
    value = data(source)
    if destination.exists():
        require(data(destination) == value, "Retained evidence already differs: " + str(destination))
    else:
        with destination.open("xb") as stream:
            stream.write(value)
    return reference(destination)


def verified_input(ref, owner):
    path = Path(ref["path"])
    path = path if path.is_absolute() else owner / path
    actual = reference(path)
    require(actual["sha256"] == ref["sha256"] and actual["bytes"] == ref["bytes"], "Frozen input differs")
    return actual


def native_events(journal):
    require(len(journal) >= 128 and journal[:8] == b"H0173SL1" and
            struct.unpack_from("<II", journal, 8) == (1, 512) and
            journal[16:80] == RUNTIME_SHA.encode() and (len(journal)-128) % 512 == 0,
            "Native journal contract differs")
    require((len(journal)-128)//512 <= 65536, "Native journal exceeds bounded collection budget")
    events = [dict(zip(EVENT_FIELDS, EVENT.unpack_from(journal, offset)[:25]))
              for offset in range(128, len(journal), 512)]
    return journal[80:96].hex(), events


def stable_native(before, after):
    keys = ("pid", "start_ticks", "exe")
    first = before["mounted"]["native_processes"]
    second = after["mounted"]["native_processes"]
    require(len(first) == len(second) == 1, "Expected one actual native engine process")
    identity = {key: first[0][key] for key in keys}
    require(identity == {key: second[0][key] for key in keys} and
            Path(identity["exe"]).name == "flash_serve", "Native engine identity changed")
    return dict(container_id=before["container_id"], **identity)


def loaded_assets(before, after, ready, startup, nonce, events, evidence, output):
    assets = read(CORPUS / "loaded-assets-receipt-template.json")
    for key in ("controller_run_id", "backend_run_id", "container_id", "manifest_path", "profile_path",
                "identities", "environment", "mounts"):
        require(before[key] == after[key], "Asset snapshot binding changed: " + key)
    require(before["phase"] == "before" and after["phase"] == "after", "Wrong snapshot phases")
    require(before["controller_run_id"] == ready["controller"]["run_id"] and
            before["backend_run_id"] == ready["backend"]["run_id"] and
            before["container_id"] == ready["backend"]["container_id"] and
            before["identities"] == ready["identities"], "Capture readiness differs from actual asset snapshots")
    native = stable_native(before, after)
    frontend = deepcopy(before["identities"]["controller"])
    frontend["scope"] = "Windows private gateway controller; container frontend identity not sampled"
    manifest_ref = retain(Path(before["manifest_path"]), evidence / "capture-backend-manifest.json")
    profile_ref = retain(Path(before["profile_path"]), evidence / "capture-profile.json")
    manifest = read(manifest_ref["path"])
    profile = read(profile_ref["path"])
    require(manifest["run_id"] == before["backend_run_id"] and manifest["version"] == "0.17.3" and
            manifest.get("owned_shadow_capture", {}).get("enabled") is True and
            profile["engine"]["draft_tokens"] == 2 and profile["engine"]["prompt_cache"] == "Off",
            "Actual loaded capture manifest/profile differs")
    require(reference(Path(before["profile_path"]))["sha256"] == ready["controller"]["profile_sha256"],
            "Gateway profile hash differs")
    for key, value in before["environment"].items():
        require(manifest["environment"].get(key) == value, "Inspected container environment differs: " + key)
    require(before["environment"]["HALOGEN_MTP_DEPTH"] == "2" and
            before["environment"]["HALOGEN_PLD"] == "3,3" and
            before["environment"]["HALOGEN_TOKENIZER"] == "/models/tokenizer", "Wrong actual native controls")
    require(all(manifest["mounts"].get(key) == value for key, value in before["mounts"].items()),
            "Actual inspected model mounts differ")
    assets.update(status="root-owned-observed-mounted-assets", session_nonce=nonce,
                  controller_run_id=before["controller_run_id"], backend_run_id=before["backend_run_id"],
                  container_id=before["container_id"], frontend_process_identity=frontend,
                  native_process_identity=native, manifest=manifest_ref, profile=profile_ref,
                  snapshots=dict(before=reference(WORK / "assets-before.json"), after=reference(WORK / "assets-after.json")))
    assets["runtime"]["startup_receipt"] = reference(WORK / "native-capture/startup-status.json")
    require(startup["runtime_sha256"] == RUNTIME_SHA, "Startup runtime pin differs")
    for role, filename in (("checkpoint", "v2-integrity.json"), ("ngram", "ngram-integrity.json")):
        receipt_ref = retain(BACKEND / ".local" / filename, evidence / filename)
        integrity = read(receipt_ref["path"])
        item = assets[role]
        require(before["source"][role] == after["source"][role] == integrity["identity"] and
                before["mounted"][role] == after["mounted"][role] and
                integrity["sha256"] == item["complete_file_sha256"] and
                integrity["identity"]["size"] == item["bytes"], "Bound complete-file role identity differs: " + role)
        require({key: value for key, value in before["mounted"][role].items() if key != "device"} ==
                {key: value for key, value in before["source"][role].items() if key != "device"},
                "Mounted/source model identity differs: " + role)
        item.update(integrity_receipt=receipt_ref, identity_before=before["source"][role],
                    identity_after=after["source"][role], mounted_identity_before=before["mounted"][role],
                    mounted_identity_after=after["mounted"][role], loaded_path_evidence=dict(
                        snapshots=assets["snapshots"], inspected_mounts=before["mounts"],
                        inspected_environment=before["environment"], native_process_identity=native,
                        native_loaded_maps_before=before["mounted"]["native_processes"][0]["loaded_maps"],
                        native_loaded_maps_after=after["mounted"]["native_processes"][0]["loaded_maps"],
                        attribution_scope="Root-owned launch/mount/stat bindings; no inprocess GPU-byte attestation"))
    tokenizer = assets["frontend_tokenizer"]
    files = before["mounted"]["tokenizer_files"]
    require(files == after["mounted"]["tokenizer_files"] == before["source"]["tokenizer_files"] ==
            after["source"]["tokenizer_files"] and files, "Tokenizer file sets differ")
    require(before["source"]["tokenizer_identity"] == after["source"]["tokenizer_identity"] and
            before["mounted"]["tokenizer_identity"] == after["mounted"]["tokenizer_identity"],
            "Tokenizer identity changed")
    canonical = json.dumps(sorted(({key: item[key] for key in ("path", "bytes", "sha256")} for item in files),
                                  key=lambda item: item["path"]), sort_keys=True, separators=(",", ":")).encode()
    tokenizer.update(files=files, asset_set_sha256=hashlib.sha256(canonical).hexdigest(),
        identity_before=before["source"]["tokenizer_identity"], identity_after=after["source"]["tokenizer_identity"],
        mounted_identity_before=before["mounted"]["tokenizer_identity"], mounted_identity_after=after["mounted"]["tokenizer_identity"],
        loaded_directory_evidence=dict(snapshots=assets["snapshots"], manifest=manifest_ref,
            actual_inspected_tokenizer_directory=before["environment"]["HALOGEN_TOKENIZER"],
            source_mount=before["mounts"]["/models"], file_set_matched_before_after=True,
            container_frontend_inprocess_tokenizer_equivalence_observed=False),
        tokenization_receipt=dict(scope="Actual API prompt usage and copied native Begin IDs; no independent full prompt tokenization"))
    begins = [event for event in events if event["kind"] == 5 and event["source"] == 1]
    require(begins and all(event["depth_low"] == 2 and event["adaptive"] == 0 for event in begins),
            "Actual causal neural Begin contradicts fixed depth2/adaptive0")
    assets["fixed_engine_policy"].update(adaptive=0,
        manifest_environment=dict(reference=manifest_ref, inspected_values=before["environment"]),
        begin_depth_low_values=sorted({event["depth_low"] for event in begins}),
        begin_depth_high_values=sorted({event["depth_high"] for event in begins}),
        begin_adaptive_values=sorted({event["adaptive"] for event in begins}))
    assets["limits"].update(container_frontend_inprocess_tokenizer_equivalence_observed=False,
        frontend_identity_scope="Windows private gateway controller",
        large_checkpoint_payloads_rehashed_during_assembly=False)
    write(output, assets)
    return assets, reference(output)


def observed_response(folder, request_id):
    result, response = read(folder / "result.json"), read(folder / "response.json")
    require(result["request_id"] == request_id and result["passed"] is True, "Request result incomplete")
    message = response["choices"][0]["message"]["content"]
    require(isinstance(message, str), "Response content is not text")
    usage, timing = response["usage"], response["timings"]
    require(usage["prompt_tokens"] == result["prompt_tokens"] and usage["completion_tokens"] == result["completion_tokens"] and
            timing["draft_n_accepted"] == result["metrics"]["accepted"] and timing["draft_n"] == result["metrics"]["drafted"],
            "Response/result usage or counters differ")
    require(timing["cache_n"] == timing["disk_restore_n"] == 0 and
            usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0) == 0, "Request controls differ")
    return result, response, hashlib.sha256(message.encode("utf-8")).hexdigest()


def assemble(args):
    require(reference(CORPUS / "manifest.json")["sha256"] == CORPUS_SHA, "Original16-request corpus changed")
    manifest = read(CORPUS / "manifest.json")
    require(len(manifest["requests"]) == 16, "Exact16 requests required")
    output = args.output_directory.resolve()
    output.mkdir(parents=True, exist_ok=True)
    require(not (output / "loaded-assets-receipt.json").exists() and not (output / "collected-manifest.json").exists(),
            "Existing assembled receipt/manifest refused; preserve prior assembly")
    evidence = output / "evidence"
    evidence.mkdir(exist_ok=True)
    provenance_directory = output / "request-provenance"
    provenance_directory.mkdir(exist_ok=True)
    before, after, ready = (read(WORK / name) for name in ("assets-before.json", "assets-after.json", "capture-ready.json"))
    startup, close, decoded = (read(WORK / "native-capture" / name) for name in
                               ("startup-status.json", "close-receipt.json", "decoded.json"))
    journal = data(WORK / "native-capture/journal.h0173sl")
    nonce, events = native_events(journal)
    require(nonce == startup["session_nonce"] == close["session_nonce"] == decoded["header"]["session_nonce"] and
            decoded["dataset_complete"] and decoded["round_costs_complete"] and decoded["cost_close_verified"],
            "Incomplete/different native or clock capture")
    require(all(close[key] is True for key in ("closed", "qualified_close", "cost_capture_enabled", "cost_closed", "cost_qualified_close")) and
            all(close[key] == 0 for key in ("dropped_cumulative", "live_owners", "pending_rounds", "relay_inflight", "cost_timing_failures")) and
            len(events) == close["written_events"], "Native/cost closure not qualified")
    capture_summary = read(WORK / "capture/summary.json")
    require(capture_summary["completed"] and len(capture_summary["requests"]) == 16, "Capture cohort incomplete")
    engine_log_ref = retain(Path(ready["backend"]["log_file"]), evidence / "capture-engine.log")
    engine_log = data(engine_log_ref["path"])
    assets, assets_ref = loaded_assets(before, after, ready, startup, nonce, events, evidence, output / "loaded-assets-receipt.json")
    normal_terminal = read(WORK / "normal-terminal.json")
    capture_launch = read(WORK / "capture-launch.json")
    require(normal_terminal["own_processes_terminal"] and normal_terminal["outcome"]["cleanup"] and normal_terminal["outcome"]["recovery"],
            "Prior normal gateway terminal evidence missing")
    require(capture_launch["previous_controller_run_id"] == normal_terminal["controller"]["run_id"] and
            capture_launch["previous_backend_run_id"] == normal_terminal["backend"]["run_id"] and
            normal_terminal["utc"] <= before["utc"], "Stopped normal run is not the capture predecessor")
    seal = read(WORK / "capture-seal.json")
    parent_client_ref = reference(WORK / "collect_requests.py")
    require(any(Path(item["path"]).resolve() == Path(parent_client_ref["path"]) and
                item["sha256"] == parent_client_ref["sha256"] and item["bytes"] == parent_client_ref["bytes"]
                for item in seal["inputs"]), "Original parent client differs from historical launch seal")
    collector_ref = retain(WORK / "collect_requests_v2.py", evidence / "root-executed-collect-requests-v2.py")
    require(collector_ref["sha256"] == ROOT_RECORDED_CLIENT_SHA, "Root-recorded actual v2 client source differs")
    template = read(CORPUS / "provenance-receipt-template.json")
    common_evidence = dict(journal=reference(WORK / "native-capture/journal.h0173sl"),
        cost_sidecar=reference(WORK / "native-capture/journal.h0173sc"),
        startup=reference(WORK / "native-capture/startup-status.json"), close=reference(WORK / "native-capture/close-receipt.json"),
        loaded_assets=assets_ref, profile=assets["profile"], engine_log=engine_log_ref,
        capture_ready=reference(WORK / "capture-ready.json"), capture_source=collector_ref,
        historical_launch_sealed_parent_client=parent_client_ref,
        capture_seal=reference(WORK / "capture-seal.json"), normal_terminal=reference(WORK / "normal-terminal.json"))
    owned = set()
    parity_rows = []
    for request in manifest["requests"]:
        request_id = request["request_id"]
        folder = WORK / "capture" / request_id
        result, response, output_sha = observed_response(folder, request_id)
        intent = read(folder / "intent.json")
        require(intent["controller_run_id"] == before["controller_run_id"] and
                intent["backend_run_id"] == before["backend_run_id"] and intent["request_sent_once"] is True,
                "Request belongs to another capture run")
        lo, hi = result["journal_before_bytes"], result["journal_after_bytes"]
        require(type(lo) is int and type(hi) is int and 128 <= lo < hi <= len(journal) and
                (lo-128) % 512 == (hi-128) % 512 == 0, "Request native byte interval invalid")
        interval_events = events[(lo-128)//512:(hi-128)//512]
        births = [event for event in interval_events if event["kind"] == 1]
        retires = [event for event in interval_events if event["kind"] == 4]
        require(len(births) == len(retires) == 1, "Request owner interval ambiguous")
        birth, retire = births[0], retires[0]
        require((birth["birth"], birth["wire_id"]) == (retire["birth"], retire["wire_id"]) and
                all(result["birth"][key] == birth[key] and result["retire"][key] == retire[key]
                    for key in ("kind", "seq", "birth", "wire_id")), "Captured request/native owner differs")
        wire, owner = birth["wire_id"], birth["birth"]
        require((nonce, wire, owner) not in owned, "Native owner duplicated")
        owned.add((nonce, wire, owner))
        log_lo, log_hi = result["native_log_before_bytes"], result["native_log_after_bytes"]
        require(0 <= log_lo < log_hi <= len(engine_log), "Native log interval outside retained log")
        wires = sorted({int(value) % (1 << 64) for value in re.findall(rb"flash_serve:\s+req\s+(-?\d+)\b", engine_log[log_lo:log_hi])})
        require(wires == result["native_log_wire_ids"] == [wire], "Native request log is not exclusive")
        health_before, health_after = read(folder / "health-before.json"), read(folder / "health-after.json")
        require(all(value["status"] == "ok" and value["active_requests"] == 0 and not value["draining"]
                    for value in (health_before, health_after)) and health_after["completed"]-health_before["completed"] == 1 and
                health_after["cancelled"]-health_before["cancelled"] == 0, "Gateway request boundary ambiguous")
        rows = [row for row in decoded["rows"] if row["session_nonce"] == nonce and
                row["wire_request_id"] == wire and row["owner_birth"] == owner]
        require(rows and all(birth["seq"] < row["begin_seq"] < row["outcome_seq"] < retire["seq"] for row in rows),
                "Decoded rows outside request owner")
        neural = [event for event in interval_events if event["kind"] == 5 and event["source"] == 1]
        require(neural and all(event["depth_low"] == 2 and event["adaptive"] == 0 for event in neural),
                "Request causal depth/adaptive configuration differs")
        payload_ref, document_ref = (verified_input(request[key], CORPUS) for key in ("payload", "document"))
        payload = read(payload_ref["path"])
        require(payload["messages"] == [dict(role="user", content=data(document_ref["path"]).decode())], "Request/document differs")
        receipt = deepcopy(template)
        receipt.update(status="observed-root-owned-collection", request_id=request_id, document_ids=request["document_ids"],
            split=request["split"], session_nonce=nonce, wire_request_id=wire, owner_birth=owner,
            payload=payload_ref, document=document_ref, decoded=reference(WORK / "native-capture/decoded.json"))
        receipt["evidence"].update(common_evidence, response=reference(folder / "response.json"),
            health_before=reference(folder / "health-before.json"), health_after=reference(folder / "health-after.json"),
            request_result=reference(folder / "result.json"), request_intent=reference(folder / "intent.json"))
        receipt["interval"].update(journal_before_bytes=lo, journal_after_bytes=hi, birth_seq=birth["seq"], retire_seq=retire["seq"],
            native_log_before_bytes=log_lo, native_log_after_bytes=log_hi, native_log_wire_ids=wires,
            gateway_completed_delta=1, gateway_cancelled_delta=0)
        receipt["process_binding"].update(controller_run_id=before["controller_run_id"], backend_run_id=before["backend_run_id"],
            container_id=before["container_id"], frontend_process_identity=assets["frontend_process_identity"],
            native_process_identity=assets["native_process_identity"], private_credentials_used=True,
            normal_gateway_down_during_collection=True)
        timing, usage = response["timings"], response["usage"]
        receipt["observed_request"].update(http_status=200, frontend_response_id=response["id"],
            prompt_tokens=usage["prompt_tokens"], completion_tokens=usage["completion_tokens"],
            reasoning_tokens=usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0),
            cache_n=timing["cache_n"], disk_restore_n=timing["disk_restore_n"],
            draft_n=timing["draft_n"], draft_n_accepted=timing["draft_n_accepted"],
            finish_reason=response["choices"][0]["finish_reason"], output_sha256=output_sha,
            request_started_utc=result["request_started_utc"], request_finished_utc=result["request_finished_utc"],
            host_request_seconds=result["host_request_seconds"])
        receipt["fixed_engine_policy"].update(adaptive=0, profile_source=assets["profile"],
            causal_depth_low_from_begin=sorted({event["depth_low"] for event in neural}),
            causal_depth_high_from_begin=sorted({event["depth_high"] for event in neural}))
        normal_folder = WORK / "normal" / request_id
        normal_complete = all((normal_folder / name).is_file() for name in
                              ("response.json", "result.json", "health-before.json", "health-after.json"))
        parity = receipt["output_parity"]
        parity.update(observed=False, passed=False, capture_output_sha256=output_sha,
                      accepted_and_drafted_capture=[timing["draft_n_accepted"], timing["draft_n"]])
        if normal_complete:
            normal_result, normal_response, normal_sha = observed_response(normal_folder, request_id)
            normal_counters = [normal_response["timings"]["draft_n_accepted"], normal_response["timings"]["draft_n"]]
            passed = normal_sha == output_sha and normal_counters == parity["accepted_and_drafted_capture"]
            parity.update(scope="paired-normal-response-text-and-native-api-counter-parity", observed=True, passed=passed,
                          reference_output_sha256=normal_sha, accepted_and_drafted_reference=normal_counters)
            receipt["evidence"].update(normal_response=reference(normal_folder / "response.json"),
                normal_result=reference(normal_folder / "result.json"),
                normal_health_before=reference(normal_folder / "health-before.json"), normal_health_after=reference(normal_folder / "health-after.json"))
        else:
            parity["scope"] = "not-observed-normal-bookend-incomplete"
            receipt["review"]["notes"].append("Missing complete normal bookend; output/counter parity is unobserved.")
            if (normal_folder / "response.json").is_file():
                receipt["evidence"]["partial_normal_response"] = reference(normal_folder / "response.json")
        receipt["review"].update(round_costs="Qualified unchanged-v1 native journal plus exact-joined CLOCK_MONOTONIC_RAW sidecar; observed stock only",
            native_inprocess_asset_attestation=False, container_frontend_inprocess_tokenizer_equivalence_observed=False)
        receipt["review"].update(code_source_scope="root-recorded execution, derivative source not launch-sealed",
            actual_client=collector_ref, historical_launch_sealed_parent_client=parent_client_ref)
        receipt["review"]["notes"].append("HTTP200/private credentials/normal-port exclusion and unchanged process/run/container checks derive from root-recorded v2 execution and separately pinned derivative source; the original launch seal covers v1 only. No new runtime probe.")
        provenance_path = provenance_directory / (request_id + ".json")
        write(provenance_path, receipt)
        request.update(session_nonce=nonce, wire_request_id=wire, owner_birth=owner, payload=payload_ref,
                       document=document_ref, decoded=receipt["decoded"], provenance=reference(provenance_path))
        parity_rows.append(dict(request_id=request_id, observed=parity["observed"], passed=parity["passed"]))
    manifest.update(status="observed-collected-pilot-awaiting-offline-review", collection_executed=True,
        qualification="Hash-bound root evidence assembled; run independent check_cohort before fitting",
        assembled_utc=datetime.now(timezone.utc).isoformat(), original_manifest=reference(CORPUS / "manifest.json"),
        loaded_assets=assets_ref, assembly_source=reference(Path(__file__)), normal_parity=parity_rows,
        actual_client=collector_ref, client_source_scope="root-recorded execution, derivative source not launch-sealed",
        historical_launch_sealed_parent_client=parent_client_ref,
        all_normal_parity_observed=all(item["observed"] for item in parity_rows),
        all_normal_parity_passed=all(item["passed"] for item in parity_rows),
        raw_decoded_metadata_unchanged=True, performance_cohort=False, NPU_executed=False)
    write(output / "collected-manifest.json", manifest)
    print(json.dumps(dict(collected_manifest=reference(output / "collected-manifest.json"), requests=16,
        parity_observed=sum(item["observed"] for item in parity_rows), parity_passed=sum(item["passed"] for item in parity_rows),
        native_decode_unchanged=True, root_offline_review_required=True)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, default=WORK)
    assemble(parser.parse_args())
