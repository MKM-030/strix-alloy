"""Pinned-image binding for two original in-place embedding RMS calls.

Root alone invokes this after checking real process/controller/provider handles,
exclusive GPU ownership and a stopped user engine under its owned 22/18-GiB
reserve/deadline guard. The acknowledgment records the outer guard; this image
wrapper performs no host-server observation. Candidate/fixtures are mounted
read-only, /result is fresh/writable and no model is mounted. No retry,
provider acquisition, replacement arithmetic or performance claim is made.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat


CANDIDATE, FIXTURES, RESULT = Path("/candidate"), Path("/fixtures"), Path("/result")
HIP_BASE = Path("/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib")
HIP_SHA256 = "6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5"
RMS_SOURCE_SHA256 = "7ea99028014f590a0938d5a06790f51ce571948706d851c16bfcb72f694f4fa8"
BRIDGE_SHA256 = "0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6"
ENGINE_SHA256 = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
CODE_SHA256 = "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
FIXTURES_SHA256 = "cf7ae0ed36d323ae32b6664ed080bc2b3cdd44863878d51719b53ddef9f72246"
PREPARER_SHA256 = "669c8dcbb18f2f06584d392130cfe52df24516e639315d855f0c74348536edc0"
BUILDER_SHA256 = "6334b32fc8a9a5cb792590d0422c0ee1fb532a7c475785f75979962ec80c2544"
PROBE_SHA256 = "f5214bfc4c4a24ccfec7a708fcd90b919d05c1f0dfa8bf79eaa3bab6b5cf18a3"
GAMMA_SHA256 = "04c4a570850e06f2d8913da8220d54d4c7f87db6eb6d45480b938e8ba41d6a86"
ENGINE_BYTES, CODE_BYTES, TENSOR_BYTES = 26052768, 17704408, 5120
BINARY_PATTERN = r"/home/revn/halogen-re/embedding-rms-replay-[0-9a-f]{32}"
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
    require(manifest.get("schema") == 1 and manifest.get("source_sha256") == PREPARER_SHA256,
            "frozen embedding RMS fixture schema/preparer differs")
    required = dict(gamma_selected_external_data_bytes=10240,
                    gamma_original_raw_checkpoint_sha256=GAMMA_SHA256,
                    full_external_data_rehashed=False, selected_region_sha256_verified=True,
                    checkpoint_payload_read=False, cpu_session_creations=0, cpu_calls=0,
                    npu_initialized=False, native_embedding_gather_qualified=False,
                    native_embedding_rms_qualified=False, native_parity_claim=False,
                    full_D_claim=False, arithmetic_fitting=False, tolerance_adjustment=False)
    require(all(manifest.get(key) == value for key, value in required.items()),
            "embedding RMS fixture provenance/qualification differs")
    expected_entry = dict(name="mtp.pre_fc_norm_embedding.weight", store=0, variant=0,
                          rank=1, dims=[2560], offset=65185026944, size=5120, xor32=7733293)
    require(manifest.get("gamma_original_source_entry") == expected_entry and
            manifest.get("gamma") == dict(file="raw-gamma.u16", bytes=5120, sha256=GAMMA_SHA256),
            "unchanged original raw BF16 gamma lineage differs")
    require({BUILDER_SHA256, PROBE_SHA256} <= set(manifest["pins"].values()),
            "frozen original source helper pins differ")
    require([row["label"] for row in manifest["rows"]] == ["A", "B"] and
            manifest["bindings"]["A"]["e"]["shape"] == [1, 2560] and
            manifest["bindings"]["A"]["e"]["bytes"] == 5120 and
            manifest["bindings"]["B"] == dict(scope="controlled distinct synthetic BF16 feed", seed=20261004),
            "frozen explicit embedding A/B boundary differs")
    normalized = {"A": "97079c27ab56da44c2ab29780c856be79803d402caf754acfbf7d187fbe34892",
                  "B": "8104e72375af48ab130c04b01fe68399e1d6c84951f9aa45c67a54b7d00db6ce"}
    for row in manifest["rows"]:
        label = row["label"]
        require(set(row["files"]) == {label + suffix for suffix in ("-input.u16", "-numpy-rms.u16", "-ort-rms.u16")} and
                row.get("original_ORT_reference_derived_from_retained_frozen_words") is True and
                row["fc_normalized_input_sha256"] == normalized[label],
                "exact input and retained normalization references required")
        for name, item in row["files"].items():
            require(item["file"] == name and item["bytes"] == TENSOR_BYTES,
                    "bounded embedding RMS fixture name/extent differs")
            sha(item["sha256"])
        require(row["files"][label + "-numpy-rms.u16"]["sha256"] == normalized[label] ==
                row["files"][label + "-ort-rms.u16"]["sha256"],
                "frozen NumPy/ORT normalization reference hashes differ")


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
    require(re.fullmatch(BINARY_PATTERN, args.binary_source_path) is not None,
            "root-compiled embedding replay path must match exact owned location")
    replay_sha = sha(args.replay_sha256)
    require(stat.S_ISDIR(RESULT.lstat().st_mode), "existing regular result directory required")
    require(not os.path.lexists(RESULT / "native") and not os.path.lexists(RESULT / "runtime.json"),
            "fresh native output directory/runtime binding required")
    bindings = {}
    bindings["wrapper"], _ = file_binding(Path(__file__).absolute(), sha(args.source_sha256), maximum=1 << 20)
    bindings["rms_source"], _ = file_binding(CANDIDATE / "halogen0162_embedding_rms_replay.c", RMS_SOURCE_SHA256, maximum=1 << 20)
    bindings["replay"], _ = file_binding(CANDIDATE / "replay", replay_sha, maximum=8 << 20)
    require(os.access(CANDIDATE / "replay", os.X_OK), "pinned compiled replay must be executable")
    bindings["bridge"], _ = file_binding(Path("/usr/lib/librocdxg.so"), BRIDGE_SHA256, maximum=32 << 20)
    bindings["engine"], _ = file_binding(CANDIDATE / "flash_serve", ENGINE_SHA256, exact_bytes=ENGINE_BYTES, maximum=ENGINE_BYTES)
    bindings["codeobject"], _ = file_binding(CANDIDATE / "engine-gfx1151.hsaco", CODE_SHA256, exact_bytes=CODE_BYTES, maximum=CODE_BYTES)
    bindings["fixtures"], raw = file_binding(FIXTURES / "fixtures.json", FIXTURES_SHA256, maximum=2 << 20, capture=True)
    manifest = json.loads(raw)
    fixture_contract(manifest)
    bindings["gamma"], _ = file_binding(FIXTURES / "raw-gamma.u16", GAMMA_SHA256,
                                       exact_bytes=TENSOR_BYTES, maximum=TENSOR_BYTES)
    for row in manifest["rows"]:
        label = row["label"]
        item = row["files"][label + "-input.u16"]
        bindings[label + "_input"], _ = file_binding(FIXTURES / item["file"], item["sha256"],
                                                    exact_bytes=TENSOR_BYTES, maximum=TENSOR_BYTES)
    library = installed_hip()
    bindings["hip"], _ = file_binding(library, HIP_SHA256)
    command = [str(CANDIDATE / "replay"), str(CANDIDATE / "flash_serve"), str(CANDIDATE / "engine-gfx1151.hsaco"),
               str(library), bindings["hip"]["sha256"]]
    for key in ("A_input", "gamma", "B_input", "gamma"):
        command.extend([bindings[key]["path"], bindings[key]["sha256"]])
    command.append(str(RESULT / "native"))
    require(len(command) == 14, "exact thirteen original embedding RMS arguments required")
    record = dict(schema="halogen0162.embedding-rms-image-runtime-binding.v1", phase="validated-before-exec",
                  scope="two original in-place embedding RMS calls on explicit BF16 rows; no table-gather/full-D/head/acceptance/speed qualification",
                  file_bindings=bindings, library=str(library), sha256=bindings["hip"]["sha256"], command=command,
                  binary_source_path=args.binary_source_path, replay_sha256=replay_sha,
                  fixture_manifest_sha256=FIXTURES_SHA256, fixture_preparer_sha256=PREPARER_SHA256,
                  input_provenance=manifest["bindings"], raw_gamma_copied_unchanged=True, input_output_alias=True,
                  outer_exclusive_gpu_guard_acknowledged=True, outer_owned_job_guard_required=True,
                  host_server_observation_performed=False, admission_gib=22, reserve_gib=18,
                  read_only_image_required=True, candidate_fixture_mounts_read_only_required=True,
                  models_required=False, model_reads_performed=False, table_gather_replayed=False,
                  embedding_rms_qualified=False, full_d_qualified=False, full_head_qualified=False,
                  acceptance_claim=False, speed_claim=False, arithmetic_fitting=False, tolerance_adjustment=False)
    write_exclusive("runtime.json", record)
    os.execv(command[0], command)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--binary-source-path", required=True)
    parser.add_argument("--replay-sha256", required=True)
    parser.add_argument("--outer-exclusive-gpu-guard", action="store_true")
    args = parser.parse_args(argv)
    sha(args.source_sha256)
    sha(args.replay_sha256)
    try:
        run(args)
    except Exception as exc:
        if os.name == "posix" and RESULT.is_dir() and not os.path.lexists(RESULT / "wrapper-failure.json"):
            write_exclusive("wrapper-failure.json", dict(schema="halogen0162.embedding-rms-image-wrapper-failure.v1",
                            error=type(exc).__name__ + ": " + str(exc), source_sha256=args.source_sha256,
                            replay_sha256=args.replay_sha256, replay_started=False, no_retry=True))
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
