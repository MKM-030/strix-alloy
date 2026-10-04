"""Owned exact-source MTP trace launch; the original service owns memory/cleanup.

No engine is started by --print-only. Normal mode fixes v2, capacity 262144,
cache Off and depth 2, then delegates to the unchanged service controller.
Only service.build_manifest is patched. The container's fresh /tmp trace is
armed by the root coordinator after READY and exported before normal stop.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import uuid


WORKSPACE = Path(r"C:\Projects\strix-alloy-clean")
BACKEND = WORKSPACE / "backends/halogen-wsl2-0.16.2"
CONTROL = BACKEND / "scripts"
TAP_SOURCE = WORKSPACE / "scripts/benchmarks/halogen0162_mtp_tap.c"
TAP_SO = "/home/revn/halogen-re/mtp-tap-20261004-armed.so"
TAP_DESTINATION = "/candidate/libhalogen0162-mtp-tap.so"
IMAGE = ("ghcr.io/peonist-ai/halogen-flash-server@sha256:"
         "0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a")
ENGINE_SHA256 = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
SERVICE_SHA256 = "2df703adc7a255a527b94a0c4c225a140023727da5e453fdd3474169566ab34a"
SOURCES_SHA256 = "d7d3249f519b78388aa3a7e4ca7c10d936926eadae42fa46ee36935d3a54af84"
MACHINE_SHA256 = "4afd3a90d13222c3f3460425c48f315c5959a29c2b7ade78a82791c8552fe527"
TAP_SOURCE_SHA256 = "15b8ad03de83bb436eb6344138e406652d70bb45fffd4650612ac68aa6af4fd0"
TAP_SO_SHA256 = "9df241ac54717f60477ce732faa54f3b1509a963e23eb3bd7eda824cfb254fb8"
ORIGINAL_PRELOAD = "/candidate/libhalogen0162-v2-preflight.so:/candidate/hip-register-private-rw.so"
FIXED_OPTIONS = ["--checkpoint", "v2", "--context-size", "262144",
                 "--prompt-cache", "Off", "--draft-tokens", "2",
                 "--serve-seconds", "0", "--startup-timeout", "900"]
ARM_CONTENT = "trace32-v1-ready\n"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def plain_workspace_file(path):
    if not path.is_absolute() or not path.is_relative_to(WORKSPACE):
        raise ValueError("Trace source escaped the fixed workspace")
    for item in [path, *path.parents]:
        mode = item.lstat()
        if (stat.S_ISLNK(mode.st_mode) or
                getattr(mode, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError("Linked/reparse trace path refused: " + str(item))
        if item == WORKSPACE:
            break
    if not path.is_file():
        raise ValueError("Expected a regular trace source: " + str(path))


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def verify_tap_so(service):
    # Read only the fixed reviewed SO. No engine, driver or checkpoint access.
    program = """import hashlib, json, os, pathlib, stat
p=pathlib.Path(%r)
for parent in [p.parent, *p.parent.parents]:
    st=parent.lstat()
    if not stat.S_ISDIR(st.st_mode): raise ValueError('Linked/non-directory SO parent')
fd=os.open(p,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
with os.fdopen(fd,'rb') as f:
    before=os.fstat(f.fileno())
    if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or not 0<before.st_size<=1048576:
        raise ValueError('Unexpected tap SO identity/size')
    sha=hashlib.file_digest(f,'sha256').hexdigest()
    after=os.fstat(f.fileno())
    if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
        raise ValueError('SO changed during review')
print(json.dumps({'sha256':sha,'bytes':before.st_size}))
""" % TAP_SO
    result = subprocess.run(service.portable.wsl_command("Ubuntu-24.04", "revn",
                            ["python3", "-c", program]), check=True, capture_output=True,
                            text=True, timeout=30, creationflags=service.NO_WINDOW)
    if len(result.stdout) > 4096:
        raise ValueError("SO review output exceeded budget")
    record = json.loads(result.stdout)
    if record.get("sha256") != TAP_SO_SHA256:
        raise ValueError("Pinned MTP tap SO changed")
    return record


def import_reviewed_service():
    if os.name != "nt":
        raise ValueError("Run this fixed launcher on Windows")
    path = Path(__file__).absolute()
    if path != WORKSPACE / "scripts/benchmarks/halogen0162_mtp_tap_launcher.py":
        raise ValueError("Use the fixed reviewed launcher path")
    for source, expected in ((CONTROL / "service.py", SERVICE_SHA256),
                             (TAP_SOURCE, TAP_SOURCE_SHA256),
                             (BACKEND / ".local/machine.json", MACHINE_SHA256)):
        plain_workspace_file(source)
        if digest(source) != expected:
            raise ValueError("Pinned trace source changed: " + str(source))
    sys.path.insert(0, str(CONTROL))
    import service
    if Path(service.__file__).resolve() != (CONTROL / "service.py").resolve():
        raise ValueError("Unexpected service module")
    if (service.r.IMAGE != IMAGE or service.r.ENGINE_SHA != ENGINE_SHA256 or
            canonical_hash(service.source_hashes()) != SOURCES_SHA256):
        raise ValueError("Pinned 0.16.2 image/source set changed")
    return service


def patch_manifest(service):
    original = service.build_manifest

    def reviewed_manifest(options, attempt, run_id):
        if (options.checkpoint, options.context_size, options.prompt_cache,
                options.draft_tokens, options.serve_seconds, options.startup_timeout) != (
                "v2", 262144, "Off", 2, 0, 900):
            raise ValueError("MTP trace launch options changed")
        if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
            raise ValueError("Unexpected owned service run ID")
        if service.r.MACHINE["distro"] != "Ubuntu-24.04" or service.r.MACHINE["user"] != "revn":
            raise ValueError("Reviewed tap distro/user changed")
        if digest(TAP_SOURCE) != TAP_SOURCE_SHA256:
            raise ValueError("MTP source changed before manifest")
        verify_tap_so(service)
        manifest = original(options, attempt, run_id)
        if (manifest["image"] != IMAGE or manifest["version"] != "0.16.2" or
                canonical_hash(manifest["sources"]) != SOURCES_SHA256 or
                manifest["environment"].get("LD_PRELOAD") != ORIGINAL_PRELOAD or
                manifest["environment"].get("HALOGEN_HOST_RESERVE_GIB") != "18" or
                TAP_DESTINATION in manifest["mounts"]):
            raise ValueError("Original service launch identity changed")
        trace_directory = "/tmp/alloy-mtp-tap-" + run_id
        manifest["mounts"][TAP_DESTINATION] = TAP_SO
        manifest["environment"]["LD_PRELOAD"] += ":" + TAP_DESTINATION
        manifest["environment"].update(HALOGEN_MTP_TAP="trace32-v1",
                                       HALOGEN_MTP_TAP_DIR=trace_directory)
        manifest["mtp_tap"] = dict(schema=1, source=str(TAP_SOURCE),
            source_sha256=TAP_SOURCE_SHA256, shared_object=TAP_SO,
            shared_object_sha256=TAP_SO_SHA256, engine_sha256=ENGINE_SHA256,
            launcher_sha256=digest(Path(__file__)), backend_sources_sha256=SOURCES_SHA256,
            trace_directory=trace_directory, trace_limit=32, token_count_limit=32768,
            arm_file=trace_directory + "/armed", arm_content=ARM_CONTENT,
            export_before_service_stop=True, intrusive_trace=True)
        command = service.command(manifest)
        if "--read-only" in command:
            raise ValueError("Reviewed trace requires the existing writable container /tmp")
        if command.count("type=bind,src=" + TAP_SO + ",dst=" + TAP_DESTINATION + ",readonly") != 1:
            raise ValueError("Tap SO mount is not the exact reviewed read-only bind")
        return manifest

    service.build_manifest = reviewed_manifest


def print_review(service):
    # configure() checks installed adapters/source identity; it starts no process
    # and performs no checkpoint/model read. The temporary entrypoint is outside
    # the backend so none of its files or pins are changed by this preview.
    service.r.configure()
    if service.r.MACHINE["distro"] != "Ubuntu-24.04" or service.r.MACHINE["user"] != "revn":
        raise ValueError("Reviewed tap distro/user changed")
    with tempfile.TemporaryDirectory(prefix="alloy-mtp-tap-review-") as temporary:
        attempt = Path(temporary)
        source = (service.LOCAL / "entrypoint-wsl.sh").read_bytes()
        (attempt / "entrypoint-service.sh").write_bytes(service.service_entrypoint(source))
        manifest = service.build_manifest(service.options(FIXED_OPTIONS), attempt, uuid.uuid4().hex)
        print(json.dumps(dict(print_only=True, launched=False, image=manifest["image"],
            checkpoint=manifest["checkpoint"], context=manifest["context"], slots=manifest["slots"],
            api=service.API, prompt_cache="Off", draft_depth=2, host_reserve_gib=18,
            patched_functions=["service.build_manifest"], tap=manifest["mtp_tap"],
            tap_mount=dict(destination=TAP_DESTINATION, source=TAP_SO, readonly=True),
            tap_environment={key: manifest["environment"][key] for key in (
                "LD_PRELOAD", "HALOGEN_MTP_TAP", "HALOGEN_MTP_TAP_DIR")}), indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-only", action="store_true")
    options = parser.parse_args()
    service = import_reviewed_service()
    verify_tap_so(service)
    patch_manifest(service)
    if options.print_only:
        print_review(service)
        return 0
    # Suppress the secret's console rendering under the coordinating root.
    os.environ["ALLOY_MANAGED"] = "1"
    return service.main(FIXED_OPTIONS)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
