"""Bind the small shared-core embedding-cache replay inside the pinned image.

Root supplies independently reviewed source/binary pins and enforces the idle
colleague, 22/18 GiB reserve, retained process and deadline guard outside this
image. This script does not observe a host server. Only frozen component
fixtures are used; no model/checkpoint, NPU or complete head is loaded.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ORIGINAL_WRAPPER_SHA = "c1120b8ca7d50c508e94affafe7bf59ed329d3d72c751b9407cf1cb4383b7542"
helper_path = Path(__file__).absolute().with_name("halogen0162_fc_image_wrapper.py")
if not stat.S_ISREG(helper_path.lstat().st_mode) or helper_path.stat().st_size > 1 << 20:
    raise RuntimeError("bounded original wrapper helper required")
with helper_path.open("rb") as helper_stream:
    if hashlib.file_digest(helper_stream, "sha256").hexdigest() != ORIGINAL_WRAPPER_SHA:
        raise RuntimeError("pinned original wrapper helper changed")
sys.path.insert(0, str(helper_path.parent))
import halogen0162_fc_image_wrapper as frozen

INPUT_SHA = {"A": "97079c27ab56da44c2ab29780c856be79803d402caf754acfbf7d187fbe34892",
             "B": "8104e72375af48ab130c04b01fe68399e1d6c84951f9aa45c67a54b7d00db6ce"}
WEIGHT_SHA = "ec6ac9d2e6111b3cf9df7cc408afd555cd33ac291e5613d4000d58cd8a51107d"


def run(args):
    frozen.require(os.name == "posix", "pinned Linux image required")
    frozen.require(args.outer_idle_server_gpu_guard, "root-owned idle colleague/small GPU guard required")
    for value in (args.source_sha256, args.replay_sha256, args.harness_sha256,
                  args.cache_source_sha256, args.cache_header_sha256):
        frozen.sha(value)
    frozen.require(stat.S_ISDIR(frozen.RESULT.lstat().st_mode), "new regular result directory required")
    frozen.require(not os.path.lexists(frozen.RESULT / "native") and
                   not os.path.lexists(frozen.RESULT / "runtime.json"), "exclusive new output required")
    wave = os.environ.get("HALOGEN_LQ8_WAVE")
    frozen.require(wave == "1", "pinned native Q8 WAVE1 required")
    bindings = {}
    sources = {
        "wrapper": (Path(__file__).absolute(), args.source_sha256),
        "wrapper_helper": (helper_path, ORIGINAL_WRAPPER_SHA),
        "fc_source": (frozen.CANDIDATE / "halogen0162_fc_replay.c", frozen.FC_SOURCE_SHA256),
        "harness": (frozen.CANDIDATE / "halogen0162_embedding_cache_replay.c", args.harness_sha256),
        "cache_source": (frozen.CANDIDATE / "halogen0162_mtp_embedding_cache.c", args.cache_source_sha256),
        "cache_header": (frozen.CANDIDATE / "halogen0162_mtp_embedding_cache.h", args.cache_header_sha256)}
    for key, (path, digest) in sources.items():
        bindings[key], _ = frozen.file_binding(path, digest, maximum=1 << 20)
    bindings["replay"], _ = frozen.file_binding(frozen.CANDIDATE / "replay", args.replay_sha256, maximum=8 << 20)
    frozen.require(os.access(frozen.CANDIDATE / "replay", os.X_OK), "reviewed replay must be executable")
    bindings["bridge"], _ = frozen.file_binding(Path("/usr/lib/librocdxg.so"), frozen.BRIDGE_SHA256, maximum=32 << 20)
    bindings["engine"], _ = frozen.file_binding(frozen.CANDIDATE / "flash_serve", frozen.ENGINE_SHA256,
        exact_bytes=frozen.ENGINE_BYTES, maximum=frozen.ENGINE_BYTES)
    bindings["codeobject"], _ = frozen.file_binding(frozen.CANDIDATE / "engine-gfx1151.hsaco", frozen.CODE_SHA256,
        exact_bytes=frozen.CODE_BYTES, maximum=frozen.CODE_BYTES)
    bindings["fixtures"], raw = frozen.file_binding(frozen.FIXTURES / "fixtures.json",
        frozen.FIXTURES_SHA256, maximum=2 << 20, capture=True)
    manifest = json.loads(raw)
    frozen.fixture_contract(manifest)
    frozen.require(manifest["raw_weights"]["e"]["sha256"] == WEIGHT_SHA,
                   "fixed original embedding Q8 matrix required")
    weight = manifest["raw_weights"]["e"]
    bindings["e_weight"], _ = frozen.file_binding(frozen.FIXTURES / weight["file"], WEIGHT_SHA,
        exact_bytes=frozen.WEIGHT_BYTES, maximum=frozen.WEIGHT_BYTES)
    for label in ("A", "B"):
        row = manifest["inputs"][label]["e"]
        frozen.require(row["sha256"] == INPUT_SHA[label], "fixed normalized A/B embedding rows required")
        bindings[label + "_e"], _ = frozen.file_binding(frozen.FIXTURES / row["file"], INPUT_SHA[label],
            exact_bytes=5120, maximum=5120)
    library = frozen.installed_hip()
    bindings["hip"], _ = frozen.file_binding(library)
    command = [str(frozen.CANDIDATE / "replay"), str(frozen.CANDIDATE / "flash_serve"),
               str(frozen.CANDIDATE / "engine-gfx1151.hsaco"), str(library), bindings["hip"]["sha256"]]
    for key in ("e_weight", "A_e", "B_e"):
        command.extend([bindings[key]["path"], bindings[key]["sha256"]])
    command.append(str(frozen.RESULT / "native"))
    frozen.require(len(command) == 12, "exact11 embedding-cache replay arguments required")
    frozen.write_exclusive("runtime.json", dict(
        schema="halogen0162.embedding-cache-image-binding.v1", phase="validated-before-exec",
        file_bindings=bindings, command=command, library=str(library), sha256=bindings["hip"]["sha256"],
        fixture_manifest_sha256=frozen.FIXTURES_SHA256, fixture_preparer_sha256=frozen.PREPARER_SHA256,
        outer_idle_server_gpu_guard_acknowledged=True, outer_owned_job_guard_required=True,
        host_server_observation_performed=False, admission_gib=22, reserve_gib=18,
        read_only_image_required=True, candidate_fixture_mounts_read_only_required=True,
        models_required=False, model_reads_performed=False, halogen_lq8_wave=wave,
        shared_core_only=True, embedding_gather_RMS_qualified=False, head_integration_qualified=False,
        acceptance_claim=False, end_to_end_throughput_qualified=False, NPU_executed=False,
        selected_hit_rate_is_synthetic=True, arithmetic_fitting=False, tolerance_adjustment=False))
    os.execv(command[0], command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source-sha256", "replay-sha256", "harness-sha256", "cache-source-sha256", "cache-header-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--outer-idle-server-gpu-guard", action="store_true")
    args = parser.parse_args()
    try:
        run(args)
    except Exception as exc:
        if os.name == "posix" and frozen.RESULT.is_dir() and not os.path.lexists(frozen.RESULT / "wrapper-failure.json"):
            frozen.write_exclusive("wrapper-failure.json", dict(
                schema="halogen0162.embedding-cache-wrapper-failure.v1", error=type(exc).__name__ + ": " + str(exc),
                replay_started=False, no_retry=True))
        raise


if __name__ == "__main__":
    main()
