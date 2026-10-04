"""Template for a root-owned gather-row-copy cache replay.

The separate gather preparer binds the independently compiled binary/source
pins and writes new wrapper/runner files. This unbound template refuses use.

Root alone runs this after checking real handles. The bounded component
container uses2GiB, admission22GiB, continuous18GiB reserve and a retained
Windows job. Any colleague change/busy state cancels only our container.
No model/checkpoint or NPU is mounted/started; component times do not qualify
acceptance, decode, complete-head behavior or end-to-end throughput.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL_OWNER_SHA = "4377babdf8befd0481bd27e68a0c963e580a4285e0d0874c2700c03ac1a92152"
helper_path = Path(__file__).resolve().with_name("halogen0162_fc_owned_run.py")
if not stat.S_ISREG(helper_path.lstat().st_mode) or helper_path.stat().st_size > 1 << 20:
    raise RuntimeError("bounded original owned-runner helper required")
with helper_path.open("rb") as helper_stream:
    if hashlib.file_digest(helper_stream, "sha256").hexdigest() != ORIGINAL_OWNER_SHA:
        raise RuntimeError("pinned original owned-runner helper changed")
sys.path.insert(0, str(helper_path.parent))
import halogen0162_fc_owned_run as envelope

WORK, BACKEND, FIXTURES, HSACO, IMAGE = envelope.WORK, envelope.BACKEND, envelope.FIXTURES, envelope.HSACO, envelope.IMAGE
sha, capture, frame, OwnedProcess, backend = envelope.sha, envelope.capture, envelope.frame, envelope.OwnedProcess, envelope.backend
SOURCE = ROOT / "scripts/benchmarks/halogen0162_embedding_cache_gather_replay.c"
CACHE_C = ROOT / "scripts/benchmarks/halogen0162_mtp_embedding_cache.c"
CACHE_H = ROOT / "scripts/benchmarks/halogen0162_mtp_embedding_cache.h"
ORACLE = ROOT / "scripts/benchmarks/halogen0162_fc_replay.c"
WRAPPER = ROOT / "scripts/benchmarks/halogen0162_embedding_cache_gather_image_wrapper.py"
WRAPPER_HELPER = ROOT / "scripts/benchmarks/halogen0162_fc_image_wrapper.py"
SOURCE_SHA = "ROOT_SUPPLIES_REVIEWED_GATHER_HARNESS_SHA256"
CACHE_C_SHA = "4de8014f186ce7bc9e4507f127543b69564ee88d01ab97779aedc73fac4436d4"
CACHE_H_SHA = "2b167c486a744cd0d78b2124da93f383778951bf6f11a9318c717a0c9263d309"
ORACLE_SHA = "8535dbe608b49f8bbad8a962359de59e78df1bd0b9cae922045277b6a1d77826"
WRAPPER_HELPER_SHA = "c1120b8ca7d50c508e94affafe7bf59ed329d3d72c751b9407cf1cb4383b7542"
BINARY = "ROOT_SUPPLIES_NEW_COMPILED_GATHER_BINARY_PATH"
BINARY_SHA = "ROOT_SUPPLIES_NEW_COMPILED_GATHER_BINARY_SHA256"
SERVER_RUN = "c4b3c8be6b584d4c901b43e54cc6e8d8"
SERVER_PID = 28488
SERVER_PROFILE = "39faa5d1c98289be76d76a396aafd6ae4fe44cba673e61354a8d63f4540b3de7"
SERVER_CONTAINER = "dd1b0e0acdeb18831bb12267a1bb87f7cc756a3658a2c1f17d311a46082a8c2e"
ENGINE_SHA = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
CODE_SHA = "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
MANIFEST_SHA = "ae61a7924d985b1fd35e5d87eabd47736dbf20b91958bd5d7003dcf1cdb84f11"
PREPARER_SHA = "1fadd3b89872e6a1f9c1d5fecfd459e20c556b2d9039581ca2469ae1a435500c"
WEIGHT_SHA = "ec6ac9d2e6111b3cf9df7cc408afd555cd33ac291e5613d4000d58cd8a51107d"
INPUT_SHA = {"A": "97079c27ab56da44c2ab29780c856be79803d402caf754acfbf7d187fbe34892",
             "B": "8104e72375af48ab130c04b01fe68399e1d6c84951f9aa45c67a54b7d00db6ce"}
OUTPUT_SHA = {"A": "e474b8c6a93ccc515d7c2e96b1bda4305fd64147d1ed622594953dd260ee9e88",
              "B": "c3625f78e90423e54aec273ca8aa9a8580dde1e4ce3edb45c1feb4b036678c31"}


def valid_sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def preserved_server():
    state = json.loads((ROOT / "server/.local/current.json").read_text(encoding="utf-8-sig"))
    age = time.time() - state.get("heartbeat", 0)
    if (state.get("run_id") != SERVER_RUN or state.get("pid") != SERVER_PID or state.get("phase") != "ready" or
            state.get("active_requests") != 0 or not 0 <= age <= 10 or state.get("profile_sha256") != SERVER_PROFILE):
        raise RuntimeError("Preserved colleague changed/busy; cancel only own replay")


def idle():
    preserved_server()
    if backend.docker("ps", "-q", "--no-trunc").split() != [SERVER_CONTAINER]:
        raise RuntimeError("Unexpected running container; preserve colleague and refuse replay")


def validate_receipts(replay, runtime, fixture, wrapper_sha):
    required = dict(schema="halogen0162.original-q8-embedding-cache-gather-replay.v1", passed=True,
        successful_process_exit_required=True, engine_sha256=ENGINE_SHA, codeobject_sha256=CODE_SHA,
        frozen_replay_source_sha256=ORACLE_SHA, compile_time_cache_source_sha256=CACHE_C_SHA,
        compile_time_cache_header_sha256=CACHE_H_SHA, capacity=1, cache_row_GPU_bytes=5120,
        event_driver_memory_excluded=True, warmup_cycles=1, measured_cycles=2, shared_core_only=True,
        paired_order="original_then_cache", selected_hit_rate_is_synthetic=True, synthetic_token_keys=True,
        checkpoint_loaded=False, server_restarted=False, embedding_gather_RMS_qualified=False,
        head_integration_qualified=False, pending_lookup_behavior_qualified=False, live_model_lifetime_qualified=False,
        acceptance_claim=False, end_to_end_throughput_qualified=False, NPU_executed=False,
        original_GPU_outputs_verified=2, completed_calls=24, launch_attempts=38, launches_ok=38,
        input_validation_copies=128, immutable_files_rechecked=True, cleanup_errors=0,
        own_allocations=4, own_frees=4, module_loads=1, module_unloads=1,
        cache_copy_method="original-k_embed_gather-fixed-zero-token",
        copy_kernel="_ZN7halogen12_GLOBAL__N_114k_embed_gatherEPKtPKiPt",
        copy_grid=[1, 1, 1], copy_block=[256, 1, 1], copy_default_stream=True,
        copy_shared_bytes=0, fixed_zero_token_bytes=4, copy_launch_attempts=24, copy_launches_ok=24,
        copy_kernarg_bytes=280, copy_kernarg_alignment=8, copy_wave_size=32,
        copy_user_argument_offsets=[0, 8, 16], copy_hidden_dispatch_arguments=True,
        original_m1_launch_counter_only=True,
        timing_event_creates=2, timing_event_destroys=2, timing_event_records=96,
        timing_event_waits=48, timing_event_elapsed=48, cache_closed=True, error="", error_code=0)
    if any(replay.get(key) != value for key, value in required.items()):
        raise RuntimeError("Exact shared-core replay/counter/scope receipt differs")
    counts = dict(calls=24, hits=12, misses=12, original_calls=12, captures=12, pending_fallbacks=0,
        evictions=6, failures=0, resets=5, stream_drains=6, copy_enqueues=24, event_queries=18,
        allocations=1, frees=1, events_created=1, events_destroyed=1)
    if replay.get("cache_stats") != counts:
        raise RuntimeError("Exact cache operations and cleanup evidence required")
    runtime_required = dict(schema="halogen0162.embedding-cache-gather-image-binding.v1", phase="validated-before-exec",
        fixture_manifest_sha256=MANIFEST_SHA, fixture_preparer_sha256=PREPARER_SHA,
        outer_idle_server_gpu_guard_acknowledged=True, outer_owned_job_guard_required=True,
        host_server_observation_performed=False, admission_gib=22, reserve_gib=18,
        read_only_image_required=True, candidate_fixture_mounts_read_only_required=True,
        models_required=False, model_reads_performed=False, halogen_lq8_wave="1", shared_core_only=True,
        cache_copy_method="original-k_embed_gather-fixed-zero-token",
        embedding_gather_RMS_qualified=False, head_integration_qualified=False, acceptance_claim=False,
        end_to_end_throughput_qualified=False, NPU_executed=False, selected_hit_rate_is_synthetic=True,
        arithmetic_fitting=False, tolerance_adjustment=False)
    if any(runtime.get(key) != value for key, value in runtime_required.items()):
        raise RuntimeError("Image wrapper guard/scope binding differs")
    bindings = runtime["file_bindings"]
    fixed = {"wrapper": ("/candidate/wrapper.py", wrapper_sha),
        "wrapper_helper": ("/candidate/halogen0162_fc_image_wrapper.py", WRAPPER_HELPER_SHA),
        "fc_source": ("/candidate/halogen0162_fc_replay.c", ORACLE_SHA),
        "harness": ("/candidate/halogen0162_embedding_cache_gather_replay.c", SOURCE_SHA),
        "cache_source": ("/candidate/halogen0162_mtp_embedding_cache.c", CACHE_C_SHA),
        "cache_header": ("/candidate/halogen0162_mtp_embedding_cache.h", CACHE_H_SHA),
        "replay": ("/candidate/replay", BINARY_SHA),
        "bridge": ("/usr/lib/librocdxg.so", "0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6"),
        "engine": ("/candidate/flash_serve", ENGINE_SHA),
        "codeobject": ("/candidate/engine-gfx1151.hsaco", CODE_SHA),
        "fixtures": ("/fixtures/fixtures.json", MANIFEST_SHA),
        "e_weight": ("/fixtures/e-weight.q8g64", WEIGHT_SHA),
        "A_e": ("/fixtures/A-e-norm.u16", INPUT_SHA["A"]), "B_e": ("/fixtures/B-e-norm.u16", INPUT_SHA["B"])}
    if any((bindings[key]["path"], bindings[key]["sha256"]) != value for key, value in fixed.items()):
        raise RuntimeError("Exact root/source/binary/frozen fixture file binding differs")
    if (fixture["preparer_sha256"] != PREPARER_SHA or fixture["raw_weights"]["e"]["sha256"] != WEIGHT_SHA or
            any(fixture["inputs"][label]["e"]["sha256"] != INPUT_SHA[label] for label in ("A", "B"))):
        raise RuntimeError("Frozen fixture lineage differs")
    hip_sha = replay["runtime_sha256"]
    if (not valid_sha(hip_sha) or runtime["sha256"] != hip_sha or bindings["hip"]["sha256"] != hip_sha or
            bindings["hip"]["path"] != runtime["library"]):
        raise RuntimeError("Installed HIP path/hash differs")
    command = ["/candidate/replay", "/candidate/flash_serve", "/candidate/engine-gfx1151.hsaco", runtime["library"], hip_sha]
    for key in ("e_weight", "A_e", "B_e"):
        command.extend([bindings[key]["path"], bindings[key]["sha256"]])
    command.append("/result/native")
    if runtime["command"] != command or len(command) != 12 or len(replay.get("rows", [])) != 24:
        raise RuntimeError("Exact11 arguments/24 output checks required")
    labels, keys = ("A", "A", "B", "B", "A", "A", "B", "B"), (11, 11, 22, 22, 11, 11, 11, 11)
    for index, row in enumerate(replay["rows"]):
        cycle, step = divmod(index, 8)
        expected_hit, label = bool(step % 2), labels[step]
        expected = dict(cycle=cycle, step=step, label=label, measured=cycle != 0, token=keys[step],
            expected_hit=expected_hit, actual_hit=expected_hit, original_callback_delta=0 if expected_hit else 1,
            original_output_sha256=OUTPUT_SHA[label], cache_output_sha256=OUTPUT_SHA[label], byte_equal=True)
        if any(row.get(key) != value for key, value in expected.items()):
            raise RuntimeError("Frozen native/cache output hash/memcmp/order/callback evidence differs")
        if any(not isinstance(row.get(key), (int, float)) or not math.isfinite(row[key]) or row[key] < 0
               for key in ("original_gpu_ms", "cache_gpu_ms", "original_host_ms", "cache_host_ms")):
            raise RuntimeError("Finite nonnegative component timing required")


def component_summary(replay, replay_sha, runtime_sha):
    measured = [row for row in replay["rows"] if row["measured"]]
    groups = {}
    for name, rows in (("hits", [row for row in measured if row["actual_hit"]]),
                       ("misses", [row for row in measured if not row["actual_hit"]]),
                       ("synthetic_50_percent_hits", measured)):
        groups[name] = dict(calls=len(rows), times={key: dict(mean=sum(row[key] for row in rows) / len(rows),
            minimum=min(row[key] for row in rows), maximum=max(row[key] for row in rows))
            for key in ("original_gpu_ms", "cache_gpu_ms", "original_host_ms", "cache_host_ms")})
    return dict(schema="halogen0162.embedding-cache-gather-component-summary.v1", measured_calls=16,
        warmup_calls=8, groups=groups, timing_scope=replay["timing_scope"], output_parity=True,
        replay_sha256=replay_sha, runtime_binding_sha256=runtime_sha, colleague_server_preserved=True,
        synthetic_token_keys=True, selected_hit_rate_is_synthetic=True, paired_order="original_then_cache",
        cache_copy_method="original-k_embed_gather-fixed-zero-token",
        live_model_hit_rate_qualified=False, acceptance_claim=False, NPU_executed=False,
        head_integration_qualified=False, end_to_end_throughput_qualified=False)


def run(wrapper_sha, own_sha):
    if not valid_sha(wrapper_sha) or not valid_sha(own_sha):
        raise ValueError("Independently supplied wrapper/runner hashes required")
    if not valid_sha(SOURCE_SHA) or not valid_sha(BINARY_SHA) or not BINARY.startswith("/home/revn/halogen-re/"):
        raise ValueError("Unbound template: root must run gather preparer with independent compile/source pins")
    pins = {SOURCE: SOURCE_SHA, CACHE_C: CACHE_C_SHA, CACHE_H: CACHE_H_SHA, ORACLE: ORACLE_SHA,
        WRAPPER: wrapper_sha, WRAPPER_HELPER: WRAPPER_HELPER_SHA, helper_path: ORIGINAL_OWNER_SHA,
        Path(__file__).resolve(): own_sha, HSACO: CODE_SHA, BACKEND / ".local/flash_serve": ENGINE_SHA,
        FIXTURES / "fixtures.json": MANIFEST_SHA,
        ROOT / "server/host_frames.py": "417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8",
        ROOT / "server/winjob.py": "3d2db1c5c8ea3846152a0073dd4ed324a47ffd36ac63bf8f48cc52e39b0d4d4c"}
    for path, expected in pins.items():
        if sha(path) != expected:
            raise ValueError("Reviewed source/input changed: " + str(path))
    preserved_server()
    backend.configure()
    idle()
    binary_sha = backend.invoke(backend.WSL + ["sha256sum", BINARY], timeout=20).split()[0]
    if binary_sha != BINARY_SHA:
        raise ValueError("Root-compiled cache replay binary changed")
    fixture_raw, _ = capture(FIXTURES / "fixtures.json", 1 << 20, MANIFEST_SHA)
    fixture = json.loads(fixture_raw)
    identity = uuid.uuid4().hex
    name = "alloy-embedding-cache-gather-" + identity
    out = WORK / name
    out.mkdir(exist_ok=False)

    def write(filename, value):
        with (out / filename).open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)

    cid = owner = None
    error = None
    memory = []
    closed = cleanup = False
    stop = threading.Event()
    watch_error = []
    cleanup_lock = threading.Lock()
    create_attempted = create_identity_recovered = False

    def reserve(floor):
        preserved_server()
        value = dict(time=time.time(), **frame())
        memory.append(value)
        if min(value["available_bytes"], value["commit_headroom_bytes"]) < floor * 2**30:
            raise RuntimeError("Host reserve below " + str(floor) + "GiB")
        return value

    def verify_container():
        info = backend.inspect(cid)
        if (info["Id"] != cid or info["Name"] != "/" + name or info["Config"]["Image"] != IMAGE or
                info["Config"]["Labels"].get("strix-alloy.embedding-cache-gather") != identity):
            raise RuntimeError("Owned small replay container identity differs")
        return info

    def recover_created_identity():
        found = backend.docker("ps", "-aq", "--no-trunc", "--filter", "name=^/" + name + "$",
            "--filter", "label=strix-alloy.embedding-cache-gather=" + identity, timeout=20).split()
        if not found:
            return None
        if len(found) != 1:
            raise RuntimeError("Ambiguous exact own-container recovery")
        info = backend.inspect(found[0])
        if (info["Id"] != found[0] or info["Name"] != "/" + name or info["Config"]["Image"] != IMAGE or
                info["Config"]["Labels"].get("strix-alloy.embedding-cache-gather") != identity):
            raise RuntimeError("Recovered container ownership differs")
        return found[0]

    def watch():
        try:
            with (out / "memory.jsonl").open("x") as stream:
                while not stop.is_set():
                    stream.write(json.dumps(reserve(18)) + "\n")
                    stream.flush()
                    stop.wait(.25)
        except BaseException as exc:
            watch_error.append(type(exc).__name__ + ": " + str(exc))
            with cleanup_lock:
                if cid and not cleanup:
                    try:
                        if verify_container()["State"]["Running"]:
                            backend.docker("stop", "-t", "0", cid, timeout=30)
                    except BaseException as shutdown:
                        watch_error.append("own guard stop: " + str(shutdown))

    monitor = threading.Thread(target=watch, daemon=True)
    try:
        reserve(22)
        monitor.start()
        mounts = {"/candidate/replay": BINARY,
            "/candidate/halogen0162_embedding_cache_gather_replay.c": backend.linux_path(SOURCE),
            "/candidate/halogen0162_mtp_embedding_cache.c": backend.linux_path(CACHE_C),
            "/candidate/halogen0162_mtp_embedding_cache.h": backend.linux_path(CACHE_H),
            "/candidate/halogen0162_fc_replay.c": backend.linux_path(ORACLE),
            "/candidate/halogen0162_fc_image_wrapper.py": backend.linux_path(WRAPPER_HELPER),
            "/candidate/flash_serve": backend.linux_path(BACKEND / ".local/flash_serve"),
            "/candidate/engine-gfx1151.hsaco": backend.linux_path(HSACO),
            "/candidate/wrapper.py": backend.linux_path(WRAPPER), "/fixtures": backend.linux_path(FIXTURES),
            "/usr/lib/libdxcore.so": "/usr/lib/wsl/lib/libdxcore.so", "/usr/lib/librocdxg.so": backend.MACHINE["dxg"],
            "/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib/librocroller.so.1":
                backend.linux_path(BACKEND / ".local/librocroller-compat.so.1")}
        args = ["create", "--name", name, "--network=none", "--restart=no", "--read-only", "--device=/dev/dxg",
            "--memory=2g", "--memory-swap=2g", "--pids-limit=128", "--ipc=private", "--shm-size=64m",
            "--ulimit=core=0:0", "--ulimit=memlock=-1:-1", "--security-opt=seccomp=unconfined",
            "--security-opt=label=disable", "--tmpfs=/tmp:rw,size=64m", "--label=strix-alloy.embedding-cache-gather=" + identity]
        for destination, source in sorted(mounts.items()):
            args += ["--mount", "type=bind,src=" + source + ",dst=" + destination + ",readonly"]
        args += ["--mount", "type=bind,src=" + backend.linux_path(out) + ",dst=/result",
            "--env=PYTHONDONTWRITEBYTECODE=1", "--env=HSA_ENABLE_DXG_DETECTION=1", "--env=HSA_ENABLE_SDMA=1",
            "--env=HALOGEN_LQ8_WAVE=1", "--env=HSA_DISABLE_COREDUMP_ON_EXCEPTION=1",
            "--env=LD_LIBRARY_PATH=/usr/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib",
            "--entrypoint=timeout", IMAGE, "--signal=TERM", "--kill-after=5s", "60s", "python3", "/candidate/wrapper.py",
            "--source-sha256", wrapper_sha, "--replay-sha256", BINARY_SHA, "--harness-sha256", SOURCE_SHA,
            "--cache-source-sha256", CACHE_C_SHA, "--cache-header-sha256", CACHE_H_SHA, "--outer-idle-server-gpu-guard"]
        write("plan.json", dict(schema=1, identity=identity, image=IMAGE, source_pins={str(p): v for p, v in pins.items()},
            binary_sha256=binary_sha, command=args, original_kernel_launches_expected=38,
            copy_kernel_launches_expected=24, models_mounted=False,
            NPU_executed=False, shared_core_only=True, end_to_end_throughput_qualified=False,
            admission_gib=22, runtime_reserve_gib=18, colleague_run_id=SERVER_RUN, colleague_container=SERVER_CONTAINER))
        idle()
        create_attempted = True
        cid = backend.docker(*args, timeout=30)
        verify_container()
        write("container.json", dict(id=cid, name=name))
        reserve(22)
        try:
            owner = OwnedProcess([r"C:\Windows\System32\wsl.exe", *backend.WSL[1:], "docker", "start", "-a", cid],
                cwd=ROOT, env=dict(os.environ), stdout_path=out / "stdout.txt", stderr_path=out / "stderr.txt")
        except BaseException as exc:
            owner = getattr(exc, "owner", None)
            raise
        write("retained-process.json", owner.identity)
        owner.verify_live_identity()
        idle()
        reserve(22)
        if watch_error or not monitor.is_alive():
            raise RuntimeError("Reserve monitor failed before child resume")
        owner.resume()
        print("CACHE_REPLAY_STARTED " + str(out) + " pid=" + str(owner.identity["pid"]), flush=True)
        until = time.monotonic() + 90
        while owner.exit_code() is None:
            if watch_error:
                raise RuntimeError(watch_error[0])
            if time.monotonic() > until:
                raise TimeoutError("Owned small cache replay deadline")
            stop.wait(.1)
        exit_code = owner.exit_code()
        info = verify_container()
        write("terminal.json", info["State"])
        if exit_code != 0 or info["State"]["Running"] or info["State"]["ExitCode"] != 0 or info["State"]["OOMKilled"]:
            raise RuntimeError("Cache replay/container process failed: " + str(exit_code))
        replay_raw, replay_sha = capture(out / "native/cache-replay.json", 65536)
        replay = json.loads(replay_raw)
        runtime_raw, runtime_sha = capture(out / "runtime.json", 65536)
        runtime = json.loads(runtime_raw)
        validate_receipts(replay, runtime, fixture, wrapper_sha)
        summary = component_summary(replay, replay_sha, runtime_sha)
        capture(out / "native/cache-replay.json", 65536, replay_sha)
        capture(out / "runtime.json", 65536, runtime_sha)
        write("component-summary.json", summary)
        for path, expected in pins.items():
            if sha(path) != expected:
                raise RuntimeError("Reviewed source/input changed during replay")
    except BaseException as exc:
        error = type(exc).__name__ + ": " + str(exc)
    finally:
        try:
            with cleanup_lock:
                if create_attempted and not cid:
                    cid = recover_created_identity()
                    create_identity_recovered = cid is not None
                    if not cid:
                        raise RuntimeError("Create outcome remains unproven; exact recovery found no ID")
                if cid:
                    info = verify_container()
                    if info["State"]["Running"]:
                        backend.docker("stop", "-t", "0", cid, timeout=30)
                    info = verify_container()
                    if info["State"]["Running"] or info["State"]["Pid"] != 0:
                        raise RuntimeError("Own small replay container still running")
                    backend.docker("rm", cid, timeout=30)
                    cleanup = True
                    if create_identity_recovered:
                        write("recovered-container.json", dict(id=cid, name=name, identity=identity,
                            ambiguous_create_preserved=True, container_removed_before_evidence_write=True))
        except BaseException as exc:
            error = (error + "; " if error else "") + "own container cleanup: " + str(exc)
        try:
            if owner:
                owner.close(timeout_ms=5000)
                closed = bool(owner._closed)
        except BaseException as exc:
            error = (error + "; " if error else "") + "own job cleanup: " + str(exc)
        stop.set()
        if monitor.is_alive():
            monitor.join(2)
        if monitor.is_alive():
            error = (error + "; " if error else "") + "reserve monitor remains active"
        try:
            final = frame()
            preserved_server()
        except BaseException as exc:
            final = dict(error=type(exc).__name__ + ": " + str(exc))
            error = (error + "; " if error else "") + "final host/colleague observation: " + str(exc)
        if watch_error:
            error = (error + "; " if error else "") + "; ".join(watch_error)
        write("result.json", dict(passed=error is None and cleanup and closed, error=error,
            own_container_removed=cleanup, own_job_closed=closed, monitor_stopped=not monitor.is_alive(),
            create_attempted=create_attempted, create_identity_recovered=create_identity_recovered,
            cleanup_pending=create_attempted and not cleanup, container_name=name, container_id=cid, ownership_label=identity,
            physical_minimum_gib=min((x["available_bytes"] / 2**30 for x in memory), default=None),
            commit_minimum_gib=min((x["commit_headroom_bytes"] / 2**30 for x in memory), default=None), final_memory=final,
            component_timing_only=True, NPU_executed=False, acceptance_claim=False, end_to_end_throughput_qualified=False))
        print("CACHE_REPLAY_FINISHED " + str(out) + " error=" + str(error), flush=True)
    return 0 if error is None and cleanup and closed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wrapper-sha256", required=True)
    parser.add_argument("--source-sha256", required=True)
    cli = parser.parse_args()
    raise SystemExit(run(cli.wrapper_sha256, cli.source_sha256))
