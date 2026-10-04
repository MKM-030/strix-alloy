"""One owned native hidden-RMS observation, explicitly HALOGEN_MTP_WIRE=D.

Root compiles/reviews the new observer separately and supplies its source/SO
seals. --prepare-only starts no engine. Normal mode uses the retained native
service controller, one calibrated cold 8K/16 greedy MTP request, post-response
harvest/export, ordinary stop, and verified cleanup plus direct RAM recovery.
This intrusive observer supplies no throughput or native/NPU speedup claim.
"""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import uuid


ROOT = Path(r"C:\Projects\strix-alloy-clean")
SOURCE = ROOT / "scripts/benchmarks/halogen0162_mtp_hidden_rms_tap.c"
SELF = ROOT / "scripts/benchmarks/halogen0162_mtp_hidden_rms_tap_launcher.py"
BACKEND = ROOT / "backends/halogen-wsl2-0.16.2"
WORK = ROOT / "server/.local/optimization9h-20261004"
SO = "/home/revn/halogen-re/mtp-hidden-rms-tap-20261004.so"
DESTINATION = "/candidate/libhalogen0162-mtp-hidden-rms-tap.so"
TRACE_PREFIX = "/tmp/alloy-mtp-hidden-rms-tap-"
IMAGE = "ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a"
ENGINE_SHA = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
FUNCTION_SHA = "132f2da76d86694ffe5f120d61e304e57c685f3db72935c6d5e61bf7b0d5cc20"
SERVICE_SHA = "3e3789619338061ca11614c939191e6e0b2ccb472baad4c33e9badd5c3b2e103"
SOURCES_SHA = "059706616417cfc215a58f5dc528dbc5422a32e23ec505b1206715ae8ed7d6a3"
ORIGINAL_PRELOAD = "/candidate/libhalogen0162-v2-preflight.so:/candidate/hip-register-private-rw.so"
FIXED_OPTIONS = ["--checkpoint", "v2", "--context-size", "262144", "--prompt-cache", "Off",
                 "--draft-tokens", "2", "--serve-seconds", "0", "--startup-timeout", "900"]
PROMPT = WORK / "mtp-tap-resume-d20a7077972049538940fe6b95bf62c7/prompt-8192-prose.txt"
PINS = {
    BACKEND / "scripts/service.py": SERVICE_SHA,
    BACKEND / ".local/machine.json": "4afd3a90d13222c3f3460425c48f315c5959a29c2b7ade78a82791c8552fe527",
    WORK / "run_mtp_route_capture.py": "b971ba320872f4ff8ac20023bad83a70ebe554a1aeda922ef2a05565d3434cb4",
    ROOT / "server/.local/upgrade0162/run_matrix.py": "12ca2f6a890a83415df398e1b867daf0cf0211e3a6275e67f628e92bf0841d58",
    ROOT / "server/host_frames.py": "417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8",
    PROMPT: "0fb44189491024eb0c3f1715828303dd6ba6073641d08ce7a8261f9a3a22c3a1",
}
ARM = b"rms1-v1-ready\n"
HARVEST = b"rms1-v1-harvest\n"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def plain(path):
    if not path.is_absolute() or not path.is_relative_to(ROOT):
        raise ValueError("path escaped the fixed workspace")
    for item in [path, *path.parents]:
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("linked/reparse path refused")
        if item == ROOT:
            break


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def check_sources(args, service=None):
    for path, expected in {**PINS, SOURCE: args.source_sha256, SELF: args.launcher_sha256}.items():
        plain(path)
        if not path.is_file() or digest(path) != expected:
            raise RuntimeError("reviewed RMS source/input changed: " + str(path))
    if service is not None and canonical(service.source_hashes()) != SOURCES_SHA:
        raise RuntimeError("reviewed backend source set changed")


def import_service(args):
    check_sources(args)
    sys.path.insert(0, str(BACKEND / "scripts"))
    import service
    if Path(service.__file__).resolve() != BACKEND / "scripts/service.py" or service.r.IMAGE != IMAGE or service.r.ENGINE_SHA != ENGINE_SHA:
        raise RuntimeError("unexpected service/image/engine identity")
    check_sources(args, service)
    return service


SO_REVIEW = """import hashlib,json,os,pathlib,stat,sys
p=pathlib.Path(sys.argv[1])
for parent in [p.parent,*p.parent.parents]:
 if not stat.S_ISDIR(parent.lstat().st_mode): raise ValueError('SO parent type')
fd=os.open(p,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
with os.fdopen(fd,'rb') as f:
 before=os.fstat(f.fileno())
 if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or not 0<before.st_size<=1048576: raise ValueError('SO identity')
 sha=hashlib.file_digest(f,'sha256').hexdigest(); after=os.fstat(f.fileno())
 if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns): raise ValueError('SO changed')
print(json.dumps({'sha256':sha,'bytes':before.st_size}))
"""


def verify_so(args, service):
    value = subprocess.run(service.portable.wsl_command("Ubuntu-24.04", "revn", ["python3", "-c", SO_REVIEW, SO]),
                           check=True, capture_output=True, text=True, timeout=30, creationflags=service.NO_WINDOW)
    if len(value.stdout) > 4096:
        raise RuntimeError("SO identity response exceeded budget")
    identity = json.loads(value.stdout)
    if identity.get("sha256") != args.so_sha256:
        raise RuntimeError("root-reviewed RMS SO changed")
    return identity


def patch_manifest(args, service):
    original = service.build_manifest
    def reviewed(options, attempt, run_id):
        if (options.checkpoint, options.context_size, options.prompt_cache, options.draft_tokens,
            options.serve_seconds, options.startup_timeout) != ("v2", 262144, "Off", 2, 0, 900):
            raise RuntimeError("fixed RMS launch options changed")
        if not re.fullmatch("[0-9a-f]{32}", run_id):
            raise RuntimeError("invalid owned run ID")
        check_sources(args, service)
        verify_so(args, service)
        if (service.r.MACHINE["distro"], service.r.MACHINE["user"]) != ("Ubuntu-24.04", "revn"):
            raise RuntimeError("reviewed WSL identity changed")
        manifest = original(options, attempt, run_id)
        if manifest["image"] != IMAGE or canonical(manifest["sources"]) != SOURCES_SHA or manifest["environment"].get("LD_PRELOAD") != ORIGINAL_PRELOAD or manifest["environment"].get("HALOGEN_HOST_RESERVE_GIB") != "18" or DESTINATION in manifest["mounts"]:
            raise RuntimeError("original service manifest changed")
        trace = TRACE_PREFIX + run_id
        manifest["mounts"][DESTINATION] = SO
        manifest["environment"]["LD_PRELOAD"] += ":" + DESTINATION
        manifest["environment"].update(HALOGEN_MTP_WIRE="D", HALOGEN_MTP_HIDDEN_RMS_TAP="rms1-v1", HALOGEN_MTP_HIDDEN_RMS_TAP_DIR=trace)
        manifest["mtp_hidden_rms_tap"] = dict(source=str(SOURCE), source_sha256=args.source_sha256,
            shared_object=SO, shared_object_sha256=args.so_sha256, launcher_sha256=args.launcher_sha256,
            trace_directory=trace, wire_mode="D", count=1, capture_limit=1,
            byte_limit=128 << 10, file_limit=8, intrusive=True, timing_claims=False)
        command = service.command(manifest)
        if "--read-only" in command or command.count("type=bind,src=" + SO + ",dst=" + DESTINATION + ",readonly") != 1:
            raise RuntimeError("RMS observer must have one exact readonly SO mount and existing writable /tmp")
        return manifest
    service.build_manifest = reviewed


def load_helper(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exact(args, helper, service, process, previous, run_id):
    state, attempt = helper.owned_state(service, process, previous, run_id)
    manifest = service.read(attempt / "manifest.json")
    tap = manifest.get("mtp_hidden_rms_tap", {})
    if (manifest["run_id"] != run_id or manifest["image"] != IMAGE or canonical(manifest["sources"]) != SOURCES_SHA or
        tap.get("source_sha256") != args.source_sha256 or tap.get("shared_object_sha256") != args.so_sha256 or
        tap.get("launcher_sha256") != args.launcher_sha256 or tap.get("trace_directory") != TRACE_PREFIX + run_id or
        manifest["environment"].get("HALOGEN_MTP_WIRE") != "D" or manifest["environment"].get("HALOGEN_MTP_DEPTH") != "2" or
        manifest["environment"].get("HALOGEN_HOST_RESERVE_GIB") != "18"):
        raise RuntimeError("exact RMS manifest changed")
    cid = service.read(attempt / "container.json")["id"]
    service.owned(service.r.inspect(cid), cid, manifest, running=True)
    return state, attempt, manifest, cid


def trigger(service, cid, trace, name, content):
    program = "import os,sys; fd=os.open(sys.argv[1]+'/'+sys.argv[2],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); data=sys.argv[3].encode(); n=os.write(fd,data); assert n==len(data); os.fsync(fd); os.close(fd)"
    service.r.docker("exec", "--user", "0", cid, "python3", "-c", program, trace, name, content.decode(), timeout=15)


async def request(args, helper, service, process, previous, run_id, watcher, out):
    import aiohttp
    check_sources(args, service)
    _, _, manifest, cid = exact(args, helper, service, process, previous, run_id)
    trace = manifest["mtp_hidden_rms_tap"]["trace_directory"]
    prompt = PROMPT.read_text(encoding="utf-8")
    token = service.TOKEN_PATH.read_text(encoding="ascii").strip()
    if not re.fullmatch("[A-Za-z0-9_-]{43}", token):
        raise RuntimeError("configured API token format differs")
    body = dict(model=service.MODEL, messages=[dict(role="user", content=prompt)], temperature=0, seed=1,
                stream=False, cache_prompt=False, enable_thinking=False, reasoning_effort="none",
                chat_template_kwargs=dict(enable_thinking=False), max_tokens=16, drafter="mtp")
    write(out / "request.json", body)
    trigger(service, cid, trace, "armed", ARM)
    write(out / "armed.json", dict(after_ready=True, run_id=run_id, trace=trace, wire_mode="D"))
    async with aiohttp.ClientSession(trust_env=False, timeout=aiohttp.ClientTimeout(total=180)) as client:
        async def fetch():
            async with client.post(service.API + "/v1/chat/completions", headers={"Authorization": "Bearer " + token}, json=body) as response:
                if response.status != 200:
                    raise RuntimeError("RMS capture HTTP " + str(response.status))
                data = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    data.extend(chunk)
                    if len(data) > 1 << 20:
                        raise RuntimeError("response exceeded1MiB budget")
                return json.loads(data)
        task = asyncio.create_task(fetch())
        try:
            while not task.done():
                watcher.check()
                if process.poll() is not None:
                    raise RuntimeError("owned service exited during request")
                await asyncio.sleep(.2)
            value = await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    write(out / "response.json", value)
    watcher.check()
    check_sources(args, service)
    exact(args, helper, service, process, previous, run_id)
    usage = value["usage"]
    message = value["choices"][0]["message"]
    if usage.get("prompt_tokens") != 8192 or usage.get("completion_tokens") != 16 or usage.get("cached_tokens", 0) != 0 or usage.get("prompt_tokens_details", {}).get("cached_tokens", 0) != 0 or message.get("reasoning_content"):
        raise RuntimeError("request differs from cold8192/16 thinking-off diagnostic")
    return dict(request_sha256=digest(out / "request.json"), response_sha256=digest(out / "response.json"), usage=usage)


INVENTORY = r'''import hashlib,json,os,pathlib,re,stat,sys
p=pathlib.Path(sys.argv[1])
if not re.fullmatch('/tmp/alloy-mtp-hidden-rms-tap-[0-9a-f]{32}',str(p)) or not stat.S_ISDIR(p.lstat().st_mode): raise ValueError('trace path/type')
limits={'activation.json':4096,'records.json':8192,'complete.json':1024,'armed':len(b'rms1-v1-ready\n'),'harvest':len(b'rms1-v1-harvest\n'),
 '000-input-residual-u16.bin':20480,'000-raw-gamma-u16.bin':20480,'000-output-hidden-rms-u16.bin':20480}
rows={}; total=0
for item in p.iterdir():
 st=item.lstat(); name=item.name
 if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or st.st_uid!=os.geteuid() or st.st_mode&0o777!=0o600 or name not in limits: raise ValueError('trace entry')
 if name.endswith('.bin') or name in ('armed','harvest'): good=st.st_size==limits[name]
 else: good=0<st.st_size<=limits[name]
 if not good: raise ValueError('trace extent')
 total+=st.st_size
 if total>131072 or len(rows)>=8: raise ValueError('trace bounds')
 fd=os.open(item,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:
  before=os.fstat(f.fileno()); sha=hashlib.file_digest(f,'sha256').hexdigest(); after=os.fstat(f.fileno())
 if len({(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns) for x in (st,before,after)})!=1: raise ValueError('trace changed')
 rows[name]={'bytes':st.st_size,'sha256':sha}
if set(rows)!=set(limits): raise ValueError('trace file set')
if (p/'armed').read_bytes()!=b'rms1-v1-ready\n' or (p/'harvest').read_bytes()!=b'rms1-v1-harvest\n': raise ValueError('trigger content')
print(json.dumps({'files':rows,'bytes':total,'file_count':len(rows)}))
'''


def harvest_export(args, helper, service, process, previous, run_id, watcher, out):
    _, _, manifest, cid = exact(args, helper, service, process, previous, run_id)
    trace = manifest["mtp_hidden_rms_tap"]["trace_directory"]
    trigger(service, cid, trace, "harvest", HARVEST)
    write(out / "harvest-request.json", dict(after_response=True, response_sha256=digest(out / "response.json")))
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        watcher.check()
        exact(args, helper, service, process, previous, run_id)
        text = service.r.docker("exec", "--user", "0", cid, "python3", "-c",
            "import pathlib,sys; p=pathlib.Path(sys.argv[1])/'complete.json'; assert not p.exists() or p.stat().st_size<=4096; print(p.read_text() if p.exists() else 'PENDING')", trace, timeout=15).strip()
        if text != "PENDING":
            try:
                complete = json.loads(text)
            except json.JSONDecodeError:
                time.sleep(.1)
                continue
            if (complete.get("passed") is not True or complete.get("error") is not None or complete.get("calls") != 1 or
                complete.get("captured") is not True or complete.get("mode") != "rms1-v1" or
                complete.get("observer_hip_syncs") != 2 or complete.get("observer_hip_copies") != 3):
                raise RuntimeError("native RMS capture/harvest failed: " + str(complete))
            write(out / "harvest-result.json", complete)
            break
        time.sleep(.1)
    else:
        raise TimeoutError("post-response RMS harvest did not complete within45s")
    inventory = json.loads(service.r.docker("exec", "--user", "0", cid, "python3", "-c", INVENTORY, trace, timeout=30))
    write(out / "trace-inventory.json", inventory)
    destination = out / "trace"
    destination.mkdir()
    exact(args, helper, service, process, previous, run_id)
    service.r.docker("cp", cid + ":" + trace + "/.", service.r.linux_path(destination), timeout=30)
    if {path.name for path in destination.iterdir()} != set(inventory["files"]):
        raise RuntimeError("exported trace file set changed")
    for name, row in inventory["files"].items():
        path = destination / name
        plain(path)
        if not path.is_file() or path.stat().st_size != row["bytes"] or digest(path) != row["sha256"]:
            raise RuntimeError("exported trace identity differs")
    activation = json.loads((destination / "activation.json").read_text())
    records = json.loads((destination / "records.json").read_text())
    if len(records.get("samples", [])) != 1:
        raise RuntimeError("native RMS trace does not contain exactly one sample")
    sample = records["samples"][0]
    if (activation.get("engine_sha256") != ENGINE_SHA or activation.get("function_sha256") != FUNCTION_SHA or
        activation.get("wire_env_required") != "D" or activation.get("limit") != 1 or activation.get("file_limit") != 8 or activation.get("byte_limit") != 131072 or
        records.get("engine_sha256") != ENGINE_SHA or records.get("function_sha256") != FUNCTION_SHA or
        records.get("mode") != "rms1-v1" or records.get("tensor_bytes") != 20480 or records.get("word_format") != "little-endian-bf16-u16" or
        sample.get("count") != 1 or sample.get("wire_mode") != "D" or sample.get("captured") is not True or sample.get("completed") is not True or
        sample.get("entry_valid") is not True or sample.get("exact_launches") != 1 or sample.get("nested_forwards") != 0 or sample.get("error") is not None or
        sample.get("width") != 10240 or sample.get("groups") != 1 or sample.get("grid") != [1, 1, 1] or sample.get("block") != [256, 1, 1] or
        sample.get("kernel_identity_rva") != "0x18d5160" or sample.get("launch_return_rva") != "0x17db632" or sample.get("shared_bytes") != 0 or sample.get("stream") != "0x0" or
        sample.get("launch_result_valid") is not True or sample.get("launch_result") != 0 or sample.get("observer_hip_syncs") != 2 or sample.get("observer_hip_copies") != 3):
        raise RuntimeError("native RMS trace does not establish exact engine/count1/D")
    for field, name in (("input_residual", "000-input-residual-u16.bin"), ("raw_gamma", "000-raw-gamma-u16.bin"), ("output_hidden_rms", "000-output-hidden-rms-u16.bin")):
        if sample.get(field + "_file") != name or sample.get(field + "_sha256") != inventory["files"][name]["sha256"]:
            raise RuntimeError("native payload identity differs from observer record")
    if json.loads((destination / "complete.json").read_text()) != complete:
        raise RuntimeError("harvest completion changed during export")
    write(out / "capture.json", dict(activation=activation, records=records, sample=sample, complete=complete, inventory=inventory, timing_claims=False))
    return dict(calls=1, exported_bytes=inventory["bytes"], files=inventory["file_count"], sample=sample)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--so-sha256", required=True)
    parser.add_argument("--launcher-sha256", required=True)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if os.name != "nt" or Path(__file__).absolute() != SELF:
        raise RuntimeError("use fixed Windows RMS launcher path")
    if any(not re.fullmatch("[0-9a-f]{64}", value) for value in (args.source_sha256, args.so_sha256, args.launcher_sha256)):
        parser.error("reviewed source/SO/launcher seals must be lowercase SHA256")
    service = import_service(args)
    if args.serve:
        if args.prepare_only:
            parser.error("--serve and --prepare-only conflict")
        patch_manifest(args, service)
        os.environ["ALLOY_MANAGED"] = "1"
        return service.main(FIXED_OPTIONS)
    helper = load_helper("reviewed_rms_lifecycle", WORK / "run_mtp_route_capture.py")
    sys.path.insert(0, str(ROOT / "server/.local/upgrade0162"))
    import run_matrix as runner
    from host_frames import frame
    service.r.configure()
    runtime = runner.controller_runtime()
    check_sources(args, service)
    so = verify_so(args, service)
    out = WORK / ("mtp-hidden-rms-capture-" + uuid.uuid4().hex)
    out.mkdir(exist_ok=False)
    command = [runtime["executable"], "-B", "-u", str(SELF), "--serve", "--source-sha256", args.source_sha256,
               "--so-sha256", args.so_sha256, "--launcher-sha256", args.launcher_sha256]
    write(out / "plan.json", dict(schema=1, source_pins={str(path): sha for path, sha in PINS.items()},
        observer_source_sha256=args.source_sha256, observer_so_sha256=args.so_sha256, launcher_sha256=args.launcher_sha256,
        runtime=runtime, command=command, shared_object=so, wire_mode="D", checkpoint="v2", context=262144,
        cache="Off", depth=2, reserve_gib=18, request_count=1, prompt_tokens=8192, max_tokens=16,
        ready_timeout_seconds=900, request_timeout_seconds=180, harvest_timeout_seconds=45,
        cleanup_timeout_seconds=600, trace_byte_limit=128 << 10, trace_file_limit=8, timing_claims=False))
    print("PREPARED " + str(out), flush=True)
    if args.prepare_only:
        return 0
    previous = service.read(service.STATE_PATH)
    gateway = runner.read(ROOT / "server/.local/current.json")
    if gateway.get("phase") not in ("stopped", "failed") or gateway.get("active_requests") != 0 or previous.get("phase") not in ("stopped", "failed") or not runner.recovered(previous) or (service.LOCAL / "runner.lock").exists():
        raise RuntimeError("require terminal idle gateway, recovered backend and no unresolved service lock")
    before = frame()
    service.check_runtime_frame(before, 0)
    write(out / "before.json", dict(backend=previous, gateway=gateway, memory=before))
    env = runner.controller_environment(os.environ, runtime)
    env["ALLOY_MANAGED"] = "1"
    runner.verify_controller_runtime(runtime, env, out)
    watcher = helper.MemoryWatch(service, frame, out)
    process = run_id = captured = exported = terminal = error = None
    watcher.thread.start()
    with (out / "service.log").open("x", encoding="utf-8") as log:
        try:
            check_sources(args, service)
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, creationflags=service.NO_WINDOW)
            write(out / "retained-process.json", dict(pid=process.pid, command=command, runtime=runtime))
            print("START owned RMS service pid=" + str(process.pid), flush=True)
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                watcher.check()
                if process.poll() is not None:
                    raise RuntimeError("owned RMS service exited before READY")
                state = service.read(service.STATE_PATH)
                if state.get("controller_pid") == process.pid:
                    state, attempt = helper.owned_state(service, process, previous["run_id"], run_id)
                    run_id = state["run_id"]
                    if state["phase"] == "ready":
                        exact(args, helper, service, process, previous["run_id"], run_id)
                        write(out / "ready.json", state)
                        break
                    if state["phase"] in ("stopped", "failed"):
                        raise RuntimeError("owned service terminated before READY")
                time.sleep(.2)
            else:
                raise TimeoutError("owned RMS service did not reach READY")
            print("READY; one cold8192/16 request with firstcount1 RMS capture", flush=True)
            captured = asyncio.run(request(args, helper, service, process, previous["run_id"], run_id, watcher, out))
            watcher.check()
            exported = harvest_export(args, helper, service, process, previous["run_id"], run_id, watcher, out)
            watcher.check()
            check_sources(args, service)
        except BaseException as exc:
            error = type(exc).__name__ + ": " + str(exc)
        finally:
            if process is not None:
                try:
                    terminal = helper.normal_stop(service, process, previous["run_id"], run_id, out, frame)
                except BaseException as exc:
                    error = (error + "; " if error else "") + "STOP_UNRESOLVED: " + str(exc)
            try:
                watcher.close()
            except BaseException as exc:
                error = (error + "; " if error else "") + str(exc)
    error = error or watcher.error
    unchanged = True
    try:
        check_sources(args, service)
    except Exception as exc:
        unchanged = False
        error = error or str(exc)
    passed = error is None and captured is not None and exported is not None and terminal is not None and terminal["cleanup_proven"] and terminal["recovery_proven"]
    write(out / "result.json", dict(passed=passed, error=error, capture=captured, trace=exported,
        cleanup_proven=bool(terminal and terminal["cleanup_proven"]), recovery_proven=bool(terminal and terminal["recovery_proven"]),
        source_pins_unchanged=unchanged, memory_minimum=watcher.minimum, finished_at=time.time(), timing_claims=False))
    print("FINISHED " + str(out) + " passed=" + str(passed), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
