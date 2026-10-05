"""Sealed ready-row candidate launch through the unchanged Halogen service.

The default is a prepare-only manifest review. --run starts the normal service;
the root coordinator owns admission, sequential measurements and stock restore.
Only service.build_manifest is patched. install_controller_adapter() can route
one exact original Halogen child command through this launcher while retaining
the gateway's original Engine ownership, stop and recovery implementations.
"""
import argparse
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import uuid


IMAGE = ("ghcr.io/peonist-ai/halogen-flash-server@sha256:"
         "0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a")
ENGINE_SHA256 = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
# The pinned image and unchanged service launch flash_serve as UID 0.
ENGINE_UID = 0
ORIGINAL_PRELOAD = "/candidate/libhalogen0162-v2-preflight.so:/candidate/hip-register-private-rw.so"
SO_DESTINATION = "/candidate/libhalogen0162-ready-embedding.so"
ROWS_DESTINATION = "/candidate/ready-embedding-rows.bin"
CACHE_PREFIX = "HALOGEN_MTP_EMBEDDING_CACHE"
BACKEND_RELATIVE = "backends/halogen-wsl2-0.16.2"
FIXED_OPTIONS = ["--checkpoint", "v2", "--context-size", "262144",
                 "--prompt-cache", "Off", "--draft-tokens", "2",
                 "--prefill-chunk", "8192", "--max-prefill-tokens", "8192",
                 "--speculation-policy-json", '{"HALOGEN_PLD":"3,3"}',
                 "--serve-seconds", "0", "--startup-timeout", "900"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def hex_value(value, length=64):
    require(isinstance(value, str) and re.fullmatch("[0-9a-f]{%d}" % length, value)
            and any(c != "0" for c in value), "Expected a nonzero lowercase digest/generation")
    return value


def plain_file(path):
    path = Path(path)
    require(path.is_absolute(), "Expected an absolute local file path")
    for item in (path, *path.parents):
        info = item.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not
                getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024),
                "Linked/reparse local path refused: " + str(item))
    require(path.is_file(), "Expected a regular local file: " + str(path))
    return path


def file_bytes(path, limit):
    path = plain_file(path)
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, "Local file exceeds its budget")
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    require(len(raw) <= limit and tuple(getattr(before, k) for k in fields) ==
            tuple(getattr(after, k) for k in fields), "Local file changed during sealed read")
    return raw


def digest(path):
    return hashlib.sha256(file_bytes(path, 64 << 20)).hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode("utf-8")).hexdigest()


def linux_artifact(record, limit):
    require(isinstance(record, dict), "Expected a sealed Linux artifact")
    path = record.get("path")
    require(isinstance(path, str) and PurePosixPath(path).is_absolute() and
            str(PurePosixPath(path)) == path and ".." not in PurePosixPath(path).parts and
            not any(c in path for c in ("\x00", "\n", "\r", ",", ":")), "Invalid Linux artifact path")
    hex_value(record.get("sha256"))
    require(type(record.get("bytes")) is int and 0 < record["bytes"] <= limit,
            "Linux artifact size exceeds its bounded contract")


def validate_plan(plan):
    require(isinstance(plan, dict) and plan.get("schema") == 1, "Expected launcher plan schema 1")
    require(Path(plan["workspace"]).is_absolute(), "Expected an absolute active workspace")
    require(plan["image"] == IMAGE and plan["engine_sha256"] == ENGINE_SHA256,
            "Ready-row candidate requires the pinned original image and engine")
    for name in ("service_sha256", "machine_sha256", "backend_sources_sha256", "launcher_sha256",
                 "controller_sha256", "start_sha256", "profile_sha256"):
        hex_value(plan[name])
    pins = plan["source_pins"]
    require(isinstance(pins, dict) and 2 <= len(pins) <= 16, "Expected bounded candidate source pins")
    for path, expected in pins.items():
        require(Path(path).is_absolute(), "Candidate source pins must use absolute paths")
        hex_value(expected)
    require({"halogen0162_mtp_embedding_cache.c", "halogen0162_mtp_embedding_cache.h"}
            <= {Path(path).name for path in pins}, "Missing candidate C/header source pins")
    runtime = plan["runtime"]
    require(isinstance(runtime, dict) and Path(runtime["executable"]).is_absolute(), "Invalid native runtime pin")
    hex_value(runtime["executable_sha256"])
    linux_artifact(plan["shared_object"], 1 << 20)
    ready = plan["ready"]
    require(ready["policy"] in ("fixed-v1", "capture-v1"), "Unsupported ready-row policy")
    hex_value(ready["generation"], 32)
    hex_value(ready["model_binding"])
    hex_value(ready["provenance"])
    if ready["policy"] == "fixed-v1":
        linux_artifact(ready["rows"], 128 + 64 * 5128)
        require(ready["rows"]["bytes"] >= 128 + 5128 and (ready["rows"]["bytes"] - 128) % 5128 == 0,
                "Invalid ready-row artifact record extent")
    else:
        require("rows" not in ready, "Capture policy refuses a fixed row artifact")
    return plan


def load_plan(path, expected_sha256):
    hex_value(expected_sha256)
    raw = file_bytes(path, 65536)
    require(hashlib.sha256(raw).hexdigest() == expected_sha256, "Launcher plan seal changed")
    plan = validate_plan(json.loads(raw.decode("utf-8-sig")))
    require(digest(Path(__file__).absolute()) == plan["launcher_sha256"], "Launcher source seal changed")
    return plan


def verify_local_sources(plan):
    backend = Path(plan["workspace"]) / BACKEND_RELATIVE
    pins = dict(plan["source_pins"])
    pins.update({str(backend / "scripts/service.py"): plan["service_sha256"],
                 str(backend / ".local/machine.json"): plan["machine_sha256"],
                 str(backend / "Start.ps1"): plan["start_sha256"],
                 str(Path(plan["workspace"]) / "server/controller.py"): plan["controller_sha256"],
                 str(Path(__file__).absolute()): plan["launcher_sha256"]})
    for path, expected in pins.items():
        require(digest(path) == expected, "Pinned local source changed: " + str(path))


def import_reviewed_service(plan):
    require(os.name == "nt", "Run the sealed launcher on Windows")
    verify_local_sources(plan)
    control = Path(plan["workspace"]) / BACKEND_RELATIVE / "scripts"
    sys.path.insert(0, str(control))
    service = importlib.import_module("service")
    require(Path(service.__file__).resolve() == (control / "service.py").resolve(), "Unexpected service module")
    require(service.ROOT.resolve() == control.parent.resolve() and service.r.ROOT.resolve() == control.parent.resolve() and
            service.r.IMAGE == IMAGE and service.r.ENGINE_SHA == ENGINE_SHA256 and
            canonical_hash(service.source_hashes()) == plan["backend_sources_sha256"],
            "Pinned original backend source set changed")
    return service


def verify_artifacts(service, plan):
    """Bounded WSL file reads only; no engine, driver, provider or checkpoint access."""
    records = {"shared_object": plan["shared_object"]}
    if plan["ready"]["policy"] == "fixed-v1":
        records["rows"] = plan["ready"]["rows"]
    program = r'''
import hashlib,json,os,pathlib,stat,struct
spec=json.loads(SPEC)
output={}
for role,record in spec['records'].items():
    p=pathlib.Path(record['path'])
    for parent in (p.parent,*p.parent.parents):
        if not stat.S_ISDIR(parent.lstat().st_mode): raise ValueError('Linked/non-directory artifact parent')
    fd=os.open(p,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size!=record['bytes']:
            raise ValueError('Artifact identity/size changed')
        if role=='rows' and (before.st_uid!=spec['engine_uid'] or before.st_mode&0o222):
            raise ValueError('Fixed rows must be owned by the engine UID with no writable mode bits')
        raw=stream.read(record['bytes']+1)
        after=os.fstat(stream.fileno())
    fields=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
    if role=='rows': fields+=('st_mode','st_uid','st_nlink')
    if tuple(getattr(before,k) for k in fields)!=tuple(getattr(after,k) for k in fields):
        raise ValueError('Artifact changed during sealed read')
    if len(raw)!=record['bytes'] or hashlib.sha256(raw).hexdigest()!=record['sha256']:
        raise ValueError('Artifact seal changed')
    if role=='shared_object':
        if raw[:6]!=b'\x7fELF\x02\x01' or struct.unpack_from('<HH',raw,16)!=(3,62):
            raise ValueError('Expected Linux x86-64 ELF shared object')
    else:
        h=struct.unpack_from('<8s6I16s32s32s16s',raw)
        if h[:4]!=(b'HGNERC01',1,128,5120) or not 1<=h[4]<=64 or h[5] not in (1,2) or h[6]!=0 or h[10]!=bytes(16):
            raise ValueError('Ready-row header changed')
        ready=spec['ready']
        if (h[7].hex(),h[8].hex(),h[9].hex())!=(ready['generation'],ready['model_binding'],ready['provenance']):
            raise ValueError('Ready-row generation/model/provenance changed')
        if len(raw)!=128+h[4]*5128: raise ValueError('Ready-row record count changed')
        seen=set()
        for index in range(h[4]):
            token,reserved,*words=struct.unpack_from('<iI2560H',raw,128+index*5128)
            if not 0<=token<248320 or token in seen or reserved or any(w&0x7f80==0x7f80 for w in words):
                raise ValueError('Unsupported duplicate/nonfinite ready row')
            seen.add(token)
    output[role]=dict(sha256=record['sha256'],bytes=before.st_size,device=before.st_dev,inode=before.st_ino)
print(json.dumps(output,separators=(',',':')))
'''.replace("SPEC", repr(json.dumps(dict(records=records, ready=plan["ready"], engine_uid=ENGINE_UID), separators=(",", ":"))))
    require(service.r.MACHINE["distro"] == "Ubuntu-24.04" and service.r.MACHINE["user"] == "revn",
            "Reviewed ready-row distro/user changed")
    command = service.portable.wsl_command("Ubuntu-24.04", "revn", ["python3", "-c", program])
    command[0] = r"C:\Windows\System32\wsl.exe"
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30,
                            creationflags=service.NO_WINDOW)
    require(len(result.stdout) <= 4096, "Artifact review output exceeded budget")
    return json.loads(result.stdout)


def ready_environment(plan):
    ready = plan["ready"]
    result = {CACHE_PREFIX: "ready64-v1", "HALOGEN_MTP_WIRE": "D", "HALOGEN_LQ8_WAVE": "1",
              CACHE_PREFIX + "_GENERATION": ready["generation"],
              CACHE_PREFIX + "_IMMUTABLE": "engine-single-generation-v1",
              CACHE_PREFIX + "_DIR": "/tmp/alloy-mtp-embedding-cache-" + ready["generation"],
              CACHE_PREFIX + "_CAPACITY": "64", CACHE_PREFIX + "_READY_POLICY": ready["policy"],
              CACHE_PREFIX + "_MODEL_BINDING": ready["model_binding"],
              CACHE_PREFIX + "_PROVENANCE": ready["provenance"]}
    if ready["policy"] == "fixed-v1":
        result[CACHE_PREFIX + "_READY_ROWS"] = ROWS_DESTINATION
        result[CACHE_PREFIX + "_READY_ROWS_SHA256"] = ready["rows"]["sha256"]
    return result


def fixed_options(options):
    expected = dict(checkpoint="v2", context_size=262144, prompt_cache="Off", draft_tokens=2,
                    prefill_chunk=8192, max_prefill_tokens=8192, prefill_keep_trunk=False,
                    admit_ticks=None, kernel_controls_json=None, matmul_tuning_json=None,
                    speculation_policy_json={"HALOGEN_PLD": "3,3"}, lookup_receipt=None,
                    lookup_receipt_sha256=None, private_hsa_receipt=None, private_hsa_receipt_sha256=None,
                    qualified_lookup=None, qualified_hsa=None, serve_seconds=0, startup_timeout=900)
    require(all(getattr(options, key, None) == value for key, value in expected.items()),
            "Ready-row service options differ from fixed arena8192 MTP2/PLD3,3")


def patch_manifest(service, plan, verify=None):
    original = service.build_manifest
    verify = verify or (lambda: (verify_local_sources(plan), verify_artifacts(service, plan))[1])

    def reviewed_manifest(options, attempt, run_id):
        fixed_options(options)
        hex_value(run_id, 32)
        identity = verify()
        manifest = original(options, attempt, run_id)
        env = manifest["environment"]
        expected = dict(LD_PRELOAD=ORIGINAL_PRELOAD, HALOGEN_HOST_RESERVE_GIB="18", HALOGEN_CTX="262144",
                        HALOGEN_KV_POOL_POSITIONS="262144", HALOGEN_KV_SLOTS="1", HALOGEN_MTP_DEPTH="2",
                        HALOGEN_PROMPT_CACHE="0", HALOGEN_PREFILL_CHUNK="8192", HALOGEN_MAX_TOK="8192", HALOGEN_PLD="3,3")
        require(manifest["image"] == IMAGE and manifest["version"] == "0.16.2" and
                manifest["checkpoint"] == "v2" and manifest["context"] == 262144 and manifest["slots"] == 1 and
                canonical_hash(manifest["sources"]) == plan["backend_sources_sha256"] and
                all(env.get(key) == value for key, value in expected.items()), "Original service manifest identity changed")
        forbidden = (CACHE_PREFIX, "HALOGEN_MTP_FC_QUALITY", "HALOGEN_MTP_TAP", "HALOGEN_MTP_STATE_TAP",
                     "HALOGEN_MTP_ROUTE_TAP", "HALOGEN_MTP_EVENT_TAP", "HALOGEN_MTP_FULL_EVENT_TAP",
                     "HALOGEN_MTP_HIDDEN_RMS_TAP")
        require(not any(key.startswith(forbidden) for key in env) and env.get("HALOGEN_MTP_WIRE", "D") == "D" and
                env.get("HALOGEN_LQ8_WAVE", "1") == "1", "Incompatible candidate/tap environment")
        mounts = {SO_DESTINATION: plan["shared_object"]["path"]}
        if plan["ready"]["policy"] == "fixed-v1":
            mounts[ROWS_DESTINATION] = plan["ready"]["rows"]["path"]
        require(not any(path in manifest["mounts"] for path in (SO_DESTINATION, ROWS_DESTINATION)),
                "Candidate destination already exists in original manifest")
        manifest["mounts"].update(mounts)
        env["LD_PRELOAD"] += ":" + SO_DESTINATION
        env.update(ready_environment(plan))
        manifest["ready_embedding_cache"] = dict(schema=1, service_run_id=run_id,
            ready=copy.deepcopy(plan["ready"]), artifact_identity=identity,
            shared_object=copy.deepcopy(plan["shared_object"]), source_pins=dict(plan["source_pins"]),
            launcher_sha256=plan["launcher_sha256"], backend_sources_sha256=plan["backend_sources_sha256"],
            original_miss_route=True, original_memory_and_lifecycle=True,
            export_before_service_stop=plan["ready"]["policy"] == "capture-v1")
        if plan["ready"]["policy"] == "capture-v1":
            manifest["ready_embedding_cache"].update(
                export_trigger=ready_environment(plan)[CACHE_PREFIX + "_DIR"] + "/ready-export",
                export_trigger_content=plan["ready"]["generation"] + "\n",
                export_trigger_mode="0600", export_on_original_engine_thread=True)
        command = service.command(manifest)
        for destination, source in mounts.items():
            require(command.count("type=bind,src=" + source + ",dst=" + destination + ",readonly") == 1,
                    "Candidate artifact is not its exact read-only bind")
        for flag in ("--memory", "--memory-swap"):
            require(command.count(flag) == 1 and command[command.index(flag) + 1] == str(44 * 1024**3),
                    "Original container memory limit changed")
        return manifest

    service.build_manifest = reviewed_manifest
    return original


def install_controller_adapter(controller, plan_path, plan_sha256, profile_path):
    """Replace only the exact profile-derived child vector in an owned gateway.

    Call in the isolated controller child before controller.run/main. The root
    owns that child and normal cleanup. The returned original JobChild class
    permits restoring the single patched seam; no service globals are changed.
    """
    plan = load_plan(plan_path, plan_sha256)
    verify_local_sources(plan)
    workspace = Path(plan["workspace"])
    backend = workspace / BACKEND_RELATIVE
    require(Path(controller.__file__).resolve() == (workspace / "server/controller.py").resolve(),
            "Adapter received an unexpected original controller module")
    raw = file_bytes(profile_path, 65536)
    require(hashlib.sha256(raw).hexdigest() == plan["profile_sha256"], "Candidate gateway profile seal changed")
    profile = json.loads(raw.decode("utf-8-sig"))
    require(profile.get("minimum_reserve_gib") == 18 and profile.get("concurrency") == 1 and
            profile["backend"].get("identifier") == "halogen-v2" and profile["backend"].get("context") == 262144,
            "Candidate requires original singleton gateway and 18-GiB reserve")
    engine = profile["engine"]
    fixed = dict(kind="halogen", directory=BACKEND_RELATIVE, checkpoint="v2", context=262144,
                 prompt_cache="Off", draft_tokens=2, prefill_chunk=8192, max_prefill_tokens=8192,
                 speculation_policy={"HALOGEN_PLD": "3,3"})
    require(all(engine.get(key) == value for key, value in fixed.items()) and
            not any(key in engine for key in ("kernel_controls", "matmul_tuning", "lookup_tuning", "private_hsa",
                                             "prefill_keep_trunk", "admit_ticks", "environment")),
            "Candidate gateway controls differ from fixed original arena8192 profile")
    require(controller.validate_engine(engine, workspace).resolve() == backend.resolve(), "Unexpected validated backend")
    runtime = plan["runtime"]
    require(Path(sys.executable).resolve() == Path(runtime["executable"]).resolve() and
            digest(runtime["executable"]) == runtime["executable_sha256"], "Adapter native interpreter identity changed")
    expected = [engine["powershell"], "-NoProfile", "-File", str(backend / "Start.ps1"),
                "-Checkpoint", "v2", "-ContextSize", "262144", "-PromptCache", "Off"]
    expected += controller.halogen_draft_arguments(engine)
    expected += controller.halogen_kernel_arguments(engine, backend)
    expected += controller.halogen_speculation_arguments(engine, backend)
    expected += controller.halogen_matmul_arguments(engine, backend)
    expected += controller.halogen_lookup_arguments(engine, backend)
    expected += controller.halogen_private_hsa_arguments(engine, backend)
    original = controller.JobChild
    launcher = str(Path(__file__).absolute())
    replacement = [runtime["executable"], "-B", "-u", launcher, "--plan", str(Path(plan_path).absolute()),
                   "--plan-sha256", plan_sha256, "--run"]

    class ReadyEmbeddingChild(original):
        def __init__(self, command, *, cwd, env, stdout_path, stderr_path):
            require(list(command) == expected and Path(cwd).resolve() == backend.resolve(),
                    "Adapter refused a child command outside its exact original Start.ps1 vector")
            require(env.get("ALLOY_MANAGED") == "1" and env.get("PYTHONUTF8") == "1",
                    "Original managed controller child environment changed")
            require(digest(profile_path) == plan["profile_sha256"], "Candidate profile changed before child launch")
            load_plan(plan_path, plan_sha256)
            verify_local_sources(plan)
            require(digest(runtime["executable"]) == runtime["executable_sha256"], "Native child interpreter seal changed")
            super().__init__(replacement, cwd=cwd, env=env, stdout_path=stdout_path, stderr_path=stderr_path)

    controller.JobChild = ReadyEmbeddingChild
    return original


def prepare(service, plan):
    # Original adapter/source configuration starts no engine or provider.
    service.r.configure()
    with tempfile.TemporaryDirectory(prefix="alloy-ready-embedding-review-") as temporary:
        attempt = Path(temporary)
        source = (service.LOCAL / "entrypoint-wsl.sh").read_bytes()
        (attempt / "entrypoint-service.sh").write_bytes(service.service_entrypoint(source))
        manifest = service.build_manifest(service.options(FIXED_OPTIONS), attempt, uuid.uuid4().hex)
    return dict(prepare_only=True, launched=False, image=manifest["image"], checkpoint="v2", context=262144,
                prompt_cache="Off", draft_depth=2, prefill_chunk=8192, max_prefill_tokens=8192,
                host_reserve_gib=18, container_limit_gib=44, patched_functions=["service.build_manifest"],
                ready_embedding_cache=manifest["ready_embedding_cache"],
                environment={key: value for key, value in manifest["environment"].items()
                             if key.startswith(CACHE_PREFIX) or key in ("LD_PRELOAD", "HALOGEN_MTP_WIRE", "HALOGEN_LQ8_WAVE")})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--run", action="store_true")
    options = parser.parse_args(argv)
    plan = load_plan(options.plan, options.plan_sha256)
    service = import_reviewed_service(plan)
    patch_manifest(service, plan)
    if not options.run:
        print(json.dumps(prepare(service, plan), indent=2))
        return 0
    os.environ["ALLOY_MANAGED"] = "1"
    return service.main(FIXED_OPTIONS)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
