"""Pinned-image binding before one exclusive original-Q8 FC host replay.

Root alone invokes this script after proving exclusive GPU ownership and a
stopped user server under its owned 22/18-GiB reserve/deadline guard. The
required acknowledgment records that external guard; it does not invent a
host-server observation from inside the image. Root mounts /candidate and
/fixtures read-only, a new writable /result, and no model/checkpoint.

The wrapper validates one installed regular HIP library, original bridge,
engine/codeobject, compiled replay, C source, its independently supplied own
source hash, frozen fixture manifest and exact six input/weight files. It
records the exact HIP path/argv before exec. No provider acquisition, kernel
replacement, tolerances, complete-head or speed claim is implemented.

Root command: python <this-file> --source-sha256 <independent-wrapper-SHA>
    --outer-exclusive-gpu-guard
Required C source mount: /candidate/halogen0162_fc_replay.c
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat


CANDIDATE = Path("/candidate")
FIXTURES = Path("/fixtures")
RESULT = Path("/result")
HIP_BASE = Path("/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib")
REPLAY_SHA256 = "fc631bcc9f8aecbf38ec457704481dea74603cead686c7da2405572d892beaae"
FC_SOURCE_SHA256 = "8535dbe608b49f8bbad8a962359de59e78df1bd0b9cae922045277b6a1d77826"
BRIDGE_SHA256 = "0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6"
ENGINE_SHA256 = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
CODE_SHA256 = "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
FIXTURES_SHA256 = "ae61a7924d985b1fd35e5d87eabd47736dbf20b91958bd5d7003dcf1cdb84f11"
PREPARER_SHA256 = "1fadd3b89872e6a1f9c1d5fecfd459e20c556b2d9039581ca2469ae1a435500c"
BUILDER_SHA256 = "6334b32fc8a9a5cb792590d0422c0ee1fb532a7c475785f75979962ec80c2544"
EXPORTER_SHA256 = "582e292581cc85b06be9af86e82af5bdc694a6a277cfbc416ae7a11e3343a870"
CHECKPOINT_SHA256 = "71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687"
ENGINE_BYTES, CODE_BYTES, WEIGHT_BYTES = 26052768, 17704408, 6963200
INPUT_SHAPES = {"e": [1, 2560], "h": [1, 10240]}
INPUT_BYTES = {"e": 5120, "h": 20480}
IDENTITY_FIELDS = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")


def sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("independently supplied lowercase SHA256 required")
    return value


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def identity(value):
    return {name: getattr(value, name) for name in IDENTITY_FIELDS}


def file_binding(path, expected=None, exact_bytes=None, maximum=128 << 20, capture=False):
    """Bounded regular-file hash from an unchanged, no-follow descriptor."""
    path = Path(path)
    require(path.is_absolute(), "binding path must be absolute")
    if expected is not None:
        sha(expected)
    before_path = path.lstat()
    require(stat.S_ISREG(before_path.st_mode), "binding must be a regular file: " + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(identity(before) == identity(before_path), "binding path/descriptor identity differs")
        require(0 < before.st_size <= maximum and (exact_bytes is None or before.st_size == exact_bytes),
                "binding file extent differs: " + str(path))
        digest, total, chunks = hashlib.sha256(), 0, []
        while total <= maximum:
            chunk = os.read(fd, min(1 << 20, maximum + 1 - total))
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
            if capture:
                chunks.append(chunk)
        after, after_path = os.fstat(fd), path.lstat()
        actual = digest.hexdigest()
        require(total == before.st_size and identity(before) == identity(after) == identity(after_path),
                "binding file changed during read: " + str(path))
        require(expected is None or actual == expected, "binding SHA256 differs: " + str(path))
        return dict(path=str(path), sha256=actual, bytes=total, identity=identity(before)), b"".join(chunks) if capture else None
    finally:
        os.close(fd)


def installed_hip():
    paths = {entry.resolve(strict=True) for entry in HIP_BASE.glob("libamdhip64.so*")}
    paths = {path for path in paths if stat.S_ISREG(path.lstat().st_mode)}
    require(len(paths) == 1, "expected one actual regular installed HIP library")
    library = next(iter(paths))
    require(library.is_relative_to(HIP_BASE.resolve(strict=True)), "installed HIP library escaped pinned package directory")
    return library


def fixture_contract(manifest):
    require(manifest.get("schema") == 1 and manifest.get("preparer_sha256") == PREPARER_SHA256,
            "frozen fixture schema/preparer differs")
    require(manifest.get("arithmetic_fitting") is False and manifest.get("tolerance_adjustment") is False and
            manifest.get("native_hidden_rms_inputs") is True and manifest.get("native_embedding_rms_inputs") is False,
            "fixture arithmetic/input qualification scope differs")
    require(manifest["source"]["checkpoint_sha256"] == CHECKPOINT_SHA256 and
            manifest["source_identity_before"] == manifest["source_identity_after"] == manifest["source"]["native_identity"],
            "frozen fixture checkpoint identity differs")
    require({BUILDER_SHA256, EXPORTER_SHA256} <= set(manifest["pins"].values()),
            "fixture source pins differ")
    require(set(manifest["raw_weights"]) == {"e", "h"} and set(manifest["inputs"]) == {"A", "B"},
            "exact two raw weights and A/B inputs required")
    for branch, name in (("e", "mtp.fc_embedding.weight"), ("h", "mtp.fc_hidden.weight")):
        row = manifest["raw_weights"][branch]
        expected = dict(name=name, store=7, variant=0, rank=2, dims=[2560, 2560], size=WEIGHT_BYTES)
        require(row["file"] == branch + "-weight.q8g64" and row["bytes"] == WEIGHT_BYTES and
                row.get("decoded_matches_frozen_external_data") is True and
                all(row["entry"].get(key) == value for key, value in expected.items()) and
                row["xor32"] == row["entry"]["xor32"], "exact original raw Q8 weight contract differs")
        sha(row["sha256"])
    for label in ("A", "B"):
        require(set(manifest["inputs"][label]) == {"e", "h"}, "exact e/h input branches required")
        for branch in ("e", "h"):
            row = manifest["inputs"][label][branch]
            provenance = "CPU-prepared embedding RMS; native embedding RMS unqualified" if branch == "e" else "original native hidden RMS"
            require(row["file"] == label + "-" + branch + "-norm.u16" and
                    row["bytes"] == INPUT_BYTES[branch] and row["shape"] == INPUT_SHAPES[branch] and
                    row["source"] == provenance, "frozen normalized BF16 input boundary differs")
            sha(row["sha256"])


def write_exclusive(name, value):
    fd = os.open(RESULT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def run(args):
    require(os.name == "posix", "pinned Linux image required")
    require(args.outer_exclusive_gpu_guard, "root-owned exclusive GPU/server/reserve guard acknowledgment required")
    require(stat.S_ISDIR(RESULT.lstat().st_mode), "existing regular result directory required")
    require(not os.path.lexists(RESULT / "native") and not os.path.lexists(RESULT / "runtime.json"),
            "new native output directory/runtime binding required")
    wave = os.environ.get("HALOGEN_LQ8_WAVE")
    require(wave in (None, "1"), "native Q8 WAVE path must be unset/default1 or exactly1")
    bindings = {}
    bindings["wrapper"], _ = file_binding(Path(__file__).absolute(), sha(args.source_sha256), maximum=1 << 20)
    bindings["fc_source"], _ = file_binding(CANDIDATE / "halogen0162_fc_replay.c", FC_SOURCE_SHA256, maximum=1 << 20)
    bindings["replay"], _ = file_binding(CANDIDATE / "replay", REPLAY_SHA256, maximum=8 << 20)
    require(os.access(CANDIDATE / "replay", os.X_OK), "pinned compiled replay must be executable")
    bindings["bridge"], _ = file_binding(Path("/usr/lib/librocdxg.so"), BRIDGE_SHA256, maximum=32 << 20)
    bindings["engine"], _ = file_binding(CANDIDATE / "flash_serve", ENGINE_SHA256, exact_bytes=ENGINE_BYTES, maximum=ENGINE_BYTES)
    bindings["codeobject"], _ = file_binding(CANDIDATE / "engine-gfx1151.hsaco", CODE_SHA256, exact_bytes=CODE_BYTES, maximum=CODE_BYTES)
    bindings["fixtures"], raw = file_binding(FIXTURES / "fixtures.json", FIXTURES_SHA256, maximum=2 << 20, capture=True)
    manifest = json.loads(raw)
    fixture_contract(manifest)
    for branch in ("e", "h"):
        row = manifest["raw_weights"][branch]
        bindings[branch + "_weight"], _ = file_binding(FIXTURES / row["file"], row["sha256"], exact_bytes=WEIGHT_BYTES, maximum=WEIGHT_BYTES)
    for label in ("A", "B"):
        for branch in ("e", "h"):
            row = manifest["inputs"][label][branch]
            bindings[label + "_" + branch], _ = file_binding(FIXTURES / row["file"], row["sha256"], exact_bytes=INPUT_BYTES[branch], maximum=INPUT_BYTES[branch])
    library = installed_hip()
    bindings["hip"], _ = file_binding(library)
    command = [str(CANDIDATE / "replay"), str(CANDIDATE / "flash_serve"), str(CANDIDATE / "engine-gfx1151.hsaco"),
               str(library), bindings["hip"]["sha256"]]
    for key in ("e_weight", "h_weight", "A_e", "A_h", "B_e", "B_h"):
        command.extend([bindings[key]["path"], bindings[key]["sha256"]])
    command.append(str(RESULT / "native"))
    require(len(command) == 18, "exact seventeen original FC host arguments required")
    record = dict(schema="halogen0162.fc-image-runtime-binding.v1", phase="validated-before-exec",
                  scope="four original FC calls on fixed normalized BF16 inputs; no native embedding-RMS/full-D/head/acceptance/speed qualification",
                  file_bindings=bindings, library=str(library), sha256=bindings["hip"]["sha256"], command=command,
                  fixture_manifest_sha256=FIXTURES_SHA256, fixture_preparer_sha256=PREPARER_SHA256,
                  input_provenance={label: {branch: manifest["inputs"][label][branch]["source"] for branch in ("e", "h")} for label in ("A", "B")},
                  outer_exclusive_gpu_guard_acknowledged=True, outer_owned_job_guard_required=True,
                  host_server_observation_performed=False, admission_gib=22, reserve_gib=18,
                  read_only_image_required=True, candidate_fixture_mounts_read_only_required=True,
                  models_required=False, model_reads_performed=False, halogen_lq8_wave=wave,
                  embedding_rms_qualified=False, full_d_qualified=False, full_head_qualified=False,
                  acceptance_claim=False, speed_claim=False, arithmetic_fitting=False, tolerance_adjustment=False)
    write_exclusive("runtime.json", record)
    # Preserve the selected installed HIP path and every original FC argument.
    os.execv(command[0], command)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--outer-exclusive-gpu-guard", action="store_true")
    args = parser.parse_args(argv)
    sha(args.source_sha256)
    try:
        run(args)
    except Exception as exc:
        # No overwrite and no retry. The root guard retains stderr/exit as well.
        if os.name == "posix" and RESULT.is_dir() and not os.path.lexists(RESULT / "wrapper-failure.json"):
            write_exclusive("wrapper-failure.json", dict(schema="halogen0162.fc-image-wrapper-failure.v1",
                            error=type(exc).__name__ + ": " + str(exc), source_sha256=args.source_sha256,
                            replay_started=False, no_retry=True))
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
