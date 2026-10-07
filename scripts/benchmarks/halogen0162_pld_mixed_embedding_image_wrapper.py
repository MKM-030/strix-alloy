"""Bind pinned inputs before one finite original-GPU PLD mixed-row component.

Root alone invokes this in its pinned image after establishing exclusive GPU
ownership, stopped server, owned process/container, deadline and memory reserve.
The acknowledgment records that external guard; this wrapper observes no host
server and acquires no provider. Mount /candidate, /fc-fixtures, /rms-fixtures
read-only and a fresh writable /result. No model/checkpoint mount is required.

The bounded no-follow file_binding and installed_hip implementations are reused
unchanged from the frozen FC/RMS image wrappers. This wrapper checks the sealed
mixed C and included FC C, the root-compiled binary, original engine/codeobject,
installed HIP/bridge, both manifests and seven exact input files, then records
the nineteen native arguments before exec. No retry or performance claim.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat


CANDIDATE, FC_FIXTURES, RMS_FIXTURES, RESULT = (
    Path("/candidate"), Path("/fc-fixtures"), Path("/rms-fixtures"), Path("/result")
)
HIP_BASE = Path("/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib")
REPLAY_SHA256 = "85d806d41f1366d6f20f0bac199c2a3d9814e4cb686f2b86d9261d484c8ee8e3"
MIXED_SOURCE_SHA256 = "a1c45e8c2594886b9f0e9dfe5fe7acfe3cf3f43e87c3b3e804123f212d6f1aee"
FC_SOURCE_SHA256 = "8535dbe608b49f8bbad8a962359de59e78df1bd0b9cae922045277b6a1d77826"
HIP_SHA256 = "6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5"
BRIDGE_SHA256 = "0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6"
ENGINE_SHA256 = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
CODE_SHA256 = "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
FC_FIXTURES_SHA256 = "ae61a7924d985b1fd35e5d87eabd47736dbf20b91958bd5d7003dcf1cdb84f11"
RMS_FIXTURES_SHA256 = "cf7ae0ed36d323ae32b6664ed080bc2b3cdd44863878d51719b53ddef9f72246"
ENGINE_BYTES, CODE_BYTES, WEIGHT_BYTES = 26052768, 17704408, 6963200
IDENTITY_FIELDS = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
INPUTS = (
    ("e_weight", "e-weight.q8g64", "ec6ac9d2e6111b3cf9df7cc408afd555cd33ac291e5613d4000d58cd8a51107d", WEIGHT_BYTES),
    ("h_weight", "h-weight.q8g64", "018511894df3996e3a2fcb1dff60860c45a808b65036fd38db472b6e985bdd3f", WEIGHT_BYTES),
    ("A_raw", "A-input.u16", "af284c0101ac76b7562b3d9e19cfc6721266f282358d8f313a09b961435ee374", 5120),
    ("B_raw", "B-input.u16", "e14b7e6b5bd1a53d1e0c26d0eb9d2356728668a89a2e591707c463cc1e2b01b4", 5120),
    ("gamma", "raw-gamma.u16", "04c4a570850e06f2d8913da8220d54d4c7f87db6eb6d45480b938e8ba41d6a86", 5120),
    ("A_h", "A-h-norm.u16", "bf43576e6a9d47efb9a15bcba42d74618ade2ea64b025e747d1c6960e2ddff34", 20480),
    ("B_h", "B-h-norm.u16", "0a46c80b3de775d94eee31b1ca4b3927fe8368353f12f5a40314d88591a31711", 20480),
)


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


def fixture_specs(fc, rms):
    """Select only the independently pinned native component input boundaries."""
    require(fc.get("schema") == rms.get("schema") == 1 and
            fc.get("preparer_sha256") == "1fadd3b89872e6a1f9c1d5fecfd459e20c556b2d9039581ca2469ae1a435500c" and
            rms.get("source_sha256") == "669c8dcbb18f2f06584d392130cfe52df24516e639315d855f0c74348536edc0",
            "frozen FC/RMS schema and preparer pins differ")
    require(fc.get("native_hidden_rms_inputs") is True and
            fc.get("native_embedding_rms_inputs") is False and
            all(manifest.get("arithmetic_fitting") is False and manifest.get("tolerance_adjustment") is False
                for manifest in (fc, rms)), "frozen fixture arithmetic qualification differs")
    require([row["label"] for row in rms["rows"]] == ["A", "B"] and
            fc["source"]["checkpoint_sha256"] == "71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687",
            "frozen A/B input or original checkpoint lineage differs")
    rows = {row["label"]: row for row in rms["rows"]}
    specs = []
    for key, name, digest, size in INPUTS:
        if key in ("e_weight", "h_weight"):
            item, base = fc["raw_weights"][key[0]], FC_FIXTURES
            require(item.get("decoded_matches_frozen_external_data") is True,
                    "original raw Q8 lineage differs")
        elif key in ("A_raw", "B_raw"):
            item, base = rows[key[0]]["files"][name], RMS_FIXTURES
            require(rows[key[0]]["fc_normalized_input_sha256"] == fc["inputs"][key[0]]["e"]["sha256"],
                    "original embedding normalization boundary differs")
        elif key == "gamma":
            item, base = rms["gamma"], RMS_FIXTURES
            require(rms["gamma_original_raw_checkpoint_sha256"] == digest,
                    "original raw gamma lineage differs")
        else:
            item, base = fc["inputs"][key[0]]["h"], FC_FIXTURES
            require(item["shape"] == [1, 10240] and item["source"] == "original native hidden RMS",
                    "original hidden normalization boundary differs")
        require(item["file"] == name and item["sha256"] == digest and item["bytes"] == size,
                "exact frozen input name/hash/extent differs: " + key)
        specs.append((key, (base / name).as_posix(), digest, size))
    return specs


def component_command(bindings):
    command = [(CANDIDATE / "replay").as_posix(), (CANDIDATE / "flash_serve").as_posix(),
               (CANDIDATE / "engine-gfx1151.hsaco").as_posix(), bindings["hip"]["path"], bindings["hip"]["sha256"]]
    for key in ("e_weight", "h_weight", "A_raw", "B_raw", "gamma", "A_h", "B_h"):
        command.extend([bindings[key]["path"], bindings[key]["sha256"]])
    command.append((RESULT / "native").as_posix())
    require(len(command) == 20, "exact nineteen mixed component arguments required")
    return command


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
    require(not any(os.path.lexists(RESULT / name) for name in ("native", "runtime.json", "wrapper-failure.json")),
            "fresh native output directory/runtime binding required")
    wave = os.environ.get("HALOGEN_LQ8_WAVE")
    require(wave in (None, "1"), "native Q8 WAVE path must be unset/default1 or exactly1")
    bindings = {}
    bindings["wrapper"], _ = file_binding(Path(__file__).absolute(), sha(args.source_sha256), maximum=1 << 20)
    for key, name, digest in (
        ("mixed_source", "halogen0162_pld_mixed_embedding_replay.c", MIXED_SOURCE_SHA256),
        ("fc_source", "halogen0162_fc_replay.c", FC_SOURCE_SHA256),
    ):
        bindings[key], _ = file_binding(CANDIDATE / name, digest, maximum=1 << 20)
    bindings["replay"], _ = file_binding(CANDIDATE / "replay", REPLAY_SHA256, maximum=8 << 20)
    require(os.access(CANDIDATE / "replay", os.X_OK), "pinned compiled replay must be executable")
    bindings["bridge"], _ = file_binding(Path("/usr/lib/librocdxg.so"), BRIDGE_SHA256, maximum=32 << 20)
    bindings["engine"], _ = file_binding(CANDIDATE / "flash_serve", ENGINE_SHA256, exact_bytes=ENGINE_BYTES, maximum=ENGINE_BYTES)
    bindings["codeobject"], _ = file_binding(CANDIDATE / "engine-gfx1151.hsaco", CODE_SHA256, exact_bytes=CODE_BYTES, maximum=CODE_BYTES)
    bindings["fc_manifest"], raw = file_binding(FC_FIXTURES / "fixtures.json", FC_FIXTURES_SHA256, maximum=2 << 20, capture=True)
    fc = json.loads(raw)
    bindings["rms_manifest"], raw = file_binding(RMS_FIXTURES / "fixtures.json", RMS_FIXTURES_SHA256, maximum=2 << 20, capture=True)
    rms = json.loads(raw)
    for key, path, digest, size in fixture_specs(fc, rms):
        bindings[key], _ = file_binding(Path(path), digest, exact_bytes=size, maximum=size)
    library = installed_hip()
    bindings["hip"], _ = file_binding(library, HIP_SHA256)
    command = component_command(bindings)
    write_exclusive("runtime.json", dict(
        schema="halogen0162.pld-mixed-embedding-image-runtime-binding.v1", phase="validated-before-exec",
        scope="finite original-GPU k2/k3/k4 embedding/seed component with synthetic private table IDs0/1",
        file_bindings=bindings, library=str(library), command=command, replay_sha256=REPLAY_SHA256,
        outer_exclusive_gpu_guard_acknowledged=True, outer_owned_job_deadline_reserve_guard_required=True,
        host_server_observation_performed=False, read_only_image_required=True,
        candidate_fixture_mounts_read_only_required=True, models_required=False, model_reads_performed=False,
        halogen_lq8_wave=wave, warmup_pairs_per_case=4, measured_pairs_per_case=16, cases=6,
        synthetic_table_ids=[0, 1], prepared_prefix_source="original GPU M1 on fixed A/B inputs",
        producer_transport_measured=False, npu_qualified=False, live_embedding_skip_qualified=False,
        full_head_qualified=False, acceptance_claim=False, speed_claim=False,
        arithmetic_fitting=False, tolerance_adjustment=False,
    ))
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
        if os.name == "posix" and RESULT.is_dir() and not os.path.lexists(RESULT / "wrapper-failure.json"):
            write_exclusive("wrapper-failure.json", dict(
                schema="halogen0162.pld-mixed-embedding-image-wrapper-failure.v1",
                error=type(exc).__name__ + ": " + str(exc), source_sha256=args.source_sha256,
                replay_started=False, no_retry=True,
            ))
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
