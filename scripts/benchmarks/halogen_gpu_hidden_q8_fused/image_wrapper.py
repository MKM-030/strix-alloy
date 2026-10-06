"""Pinned-image binding before one finite original/candidate GPU H comparison.

Root alone invokes this with its stopped-server/exclusive GPU/22-to-18 GiB
owned-job guard. This wrapper observes no host server and does not retry.
Candidate and frozen fixtures are read-only; /result is fresh and writable.
No model, NPU, engine hook, complete head or token/acceptance claim.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

CANDIDATE, FIXTURES, RESULT = Path("/candidate"), Path("/fixtures"), Path("/result")
HIP_BASE = Path("/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib")
BINARY = "/home/revn/halogen-re/gpu-hidden-q8-fused-replay-20261006-v1"
BINARY_SHA = "2ee18d0f7996f9ea5d7476fa73eef74bd80540b4ffe7b50d4e135fb1e03761cc"
SOURCE_SHA = "184247a546507b41832af8dbefda1d3da43fe8f495c6c075a61a1a4243803bcc"
ENGINE_SHA = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
CODE_SHA = "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
CANDIDATE_SHA = "4fed1059167eed6faf2aad4ed4b6636fa6c561003c3d58ab5464b827efb79d4f"
HIP_SHA = "6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5"
BRIDGE_SHA = "0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6"
FIXTURES_SHA = "ae61a7924d985b1fd35e5d87eabd47736dbf20b91958bd5d7003dcf1cdb84f11"
RAW_WEIGHT_SHA = "018511894df3996e3a2fcb1dff60860c45a808b65036fd38db472b6e985bdd3f"
CANDIDATE_WEIGHT_SHA = "018511894df3996e3a2fcb1dff60860c45a808b65036fd38db472b6e985bdd3f"
INPUT_SHA = {
    "A": "bf43576e6a9d47efb9a15bcba42d74618ade2ea64b025e747d1c6960e2ddff34",
    "B": "0a46c80b3de775d94eee31b1ca4b3927fe8368353f12f5a40314d88591a31711"}
IDENTITY_FIELDS = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(value):
    require(isinstance(value, str) and len(value) == 64 and
            all(c in "0123456789abcdef" for c in value), "independent lowercase SHA256 required")
    return value


def identity(value):
    return {name: getattr(value, name) for name in IDENTITY_FIELDS}


def file_binding(path, expected, exact_bytes=None, maximum=128 << 20, capture=False):
    path = Path(path)
    require(path.is_absolute(), "absolute binding path required")
    sha(expected)
    before_path = path.lstat()
    require(stat.S_ISREG(before_path.st_mode), "regular binding required: " + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(identity(before) == identity(before_path), "path/descriptor identity differs")
        require(0 < before.st_size <= maximum and
                (exact_bytes is None or before.st_size == exact_bytes), "bounded extent differs")
        digest, total, chunks = hashlib.sha256(), 0, []
        while total <= maximum:
            chunk = os.read(fd, min(1 << 20, maximum + 1 - total))
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
            if capture:
                chunks.append(chunk)
        require(total == before.st_size and
                identity(before) == identity(os.fstat(fd)) == identity(path.lstat()),
                "binding changed while read: " + str(path))
        require(digest.hexdigest() == expected, "binding SHA256 differs: " + str(path))
        return dict(path=str(path), sha256=expected, bytes=total, identity=identity(before)), \
            b"".join(chunks) if capture else None
    finally:
        os.close(fd)


def installed_hip():
    paths = {entry.resolve(strict=True) for entry in HIP_BASE.glob("libamdhip64.so*")}
    paths = {path for path in paths if stat.S_ISREG(path.lstat().st_mode)}
    require(len(paths) == 1, "one actual regular installed HIP library required")
    library = next(iter(paths))
    require(library.is_relative_to(HIP_BASE.resolve(strict=True)), "HIP escaped pinned package")
    return library


def write_exclusive(name, value):
    fd = os.open(RESULT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def run(args):
    sha(BINARY_SHA)
    sha(SOURCE_SHA)
    require(os.name == "posix", "pinned Linux image required")
    require(args.outer_exclusive_gpu_guard, "root-owned GPU/server/reserve guard acknowledgment required")
    require(stat.S_ISDIR(RESULT.lstat().st_mode), "regular result directory required")
    require(not os.path.lexists(RESULT / "native") and not os.path.lexists(RESULT / "runtime.json"),
            "fresh native output/runtime binding required")
    require(os.environ.get("HALOGEN_LQ8_WAVE") in (None, "1"), "stock WAVE default/one required")
    bindings = {}
    bindings["wrapper"], _ = file_binding(Path(__file__).absolute(), sha(args.source_sha256), maximum=1 << 20)
    bindings["source"], _ = file_binding(CANDIDATE / "replay.c", SOURCE_SHA, maximum=1 << 20)
    bindings["replay"], _ = file_binding(CANDIDATE / "replay", BINARY_SHA, maximum=8 << 20)
    require(os.access(CANDIDATE / "replay", os.X_OK), "compiled replay must be executable")
    bindings["bridge"], _ = file_binding(Path("/usr/lib/librocdxg.so"), BRIDGE_SHA, maximum=32 << 20)
    bindings["engine"], _ = file_binding(CANDIDATE / "flash_serve", ENGINE_SHA,
                                        exact_bytes=26052768, maximum=26052768)
    bindings["codeobject"], _ = file_binding(CANDIDATE / "engine-gfx1151.hsaco", CODE_SHA,
                                            exact_bytes=17704408, maximum=17704408)
    bindings["candidate"], _ = file_binding(CANDIDATE / "hidden-q8-fused.hsaco", CANDIDATE_SHA,
                                           exact_bytes=6352, maximum=6352)
    bindings["candidate_weight"], _ = file_binding(CANDIDATE / "hidden-candidate-q8.bin", CANDIDATE_WEIGHT_SHA,
                                         exact_bytes=6963200, maximum=6963200)
    bindings["fixtures"], raw = file_binding(FIXTURES / "fixtures.json", FIXTURES_SHA,
                                             maximum=2 << 20, capture=True)
    manifest = json.loads(raw)
    require(manifest.get("schema") == 1 and
            manifest["raw_weights"]["h"]["sha256"] == RAW_WEIGHT_SHA and
            manifest["raw_weights"]["h"]["file"] == "h-weight.q8g64" and
            manifest["raw_weights"]["h"]["bytes"] == 6963200 and
            manifest["raw_weights"]["h"]["entry"]["dims"] == [2560, 2560],
            "frozen H geometry/provenance differs")
    bindings["raw_weight"], _ = file_binding(FIXTURES / "h-weight.q8g64", RAW_WEIGHT_SHA,
                                            exact_bytes=6963200, maximum=6963200)
    for label in ("A", "B"):
        item = manifest["inputs"][label]["h"]
        require(item == dict(file=label + "-h-norm.u16", bytes=20480, sha256=INPUT_SHA[label],
                             shape=[1, 10240], source="original native hidden RMS"),
                "frozen whole-row-normalized H input differs")
        bindings[label + "_input"], _ = file_binding(FIXTURES / item["file"], INPUT_SHA[label],
                                                     exact_bytes=20480, maximum=20480)
    library = installed_hip()
    bindings["hip"], _ = file_binding(library, HIP_SHA)
    command = [str(CANDIDATE / "replay"), bindings["engine"]["path"], bindings["codeobject"]["path"],
               bindings["candidate"]["path"], CANDIDATE_SHA, str(library), HIP_SHA,
               bindings["raw_weight"]["path"], bindings["candidate_weight"]["path"],
               bindings["A_input"]["path"], bindings["B_input"]["path"], str(RESULT / "native")]
    require(len(command) == 12, "exact eleven replay arguments required")
    record = dict(schema="halogen.gpu-hidden-q8-fused.image-runtime-binding.v1", phase="validated-before-exec",
                  file_bindings=bindings, command=command, library=str(library), sha256=HIP_SHA,
                  binary_source_path=BINARY, replay_sha256=BINARY_SHA,
                  fixture_manifest_sha256=FIXTURES_SHA, candidate_raw_weight_sha256=CANDIDATE_WEIGHT_SHA,
                  original_codeobject_sha256=CODE_SHA, candidate_codeobject_sha256=CANDIDATE_SHA,
                  outer_exclusive_gpu_guard_acknowledged=True, outer_owned_job_guard_required=True,
                  host_server_observation_performed=False, admission_gib=22, reserve_gib=18,
                  read_only_image_required=True, candidate_fixture_mounts_read_only_required=True,
                  models_required=False, model_reads_performed=False, npu_initialized=False,
                  warmup_pairs=4, measured_pairs=16, alternating_arm_order=True,
                  original_grid=[160, 1, 1], candidate_grid=[160, 1, 1],
                  untimed_same_arm_primer_per_timed_launch=True, separate_priming_output=True,
                  separately_timed_single_launches=True, exact_hash_after_every_timed_launch=True,
                  full_head_qualified=False, acceptance_claim=False, end_to_end_speed_claim=False,
                  prefill_gain_claim=False, arithmetic_fitting=False, tolerance_adjustment=False)
    write_exclusive("runtime.json", record)
    os.execv(command[0], command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--outer-exclusive-gpu-guard", action="store_true")
    args = parser.parse_args()
    sha(args.source_sha256)
    try:
        run(args)
    except Exception as exc:
        if os.name == "posix" and RESULT.is_dir() and not os.path.lexists(RESULT / "wrapper-failure.json"):
            write_exclusive("wrapper-failure.json", dict(schema="halogen.gpu-hidden-q8-fused.wrapper-failure.v1",
                            error=type(exc).__name__ + ": " + str(exc), source_sha256=args.source_sha256,
                            replay_started=False, no_retry=True))
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
