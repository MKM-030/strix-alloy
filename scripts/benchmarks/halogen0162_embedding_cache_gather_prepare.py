"""Root-only source binding for the separate native-gather cache replay.

After independent source/metadata review and owned compilation, supply the
actual binary path/hash and reviewed harness hash. This preparer reads ordinary
source files only and writes new exclusive wrapper/runner files plus a plan.
It imports no provider, invokes no process/compiler, and changes no released
source. Review the generated plan/files before root runs the one small replay.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import uuid

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "scripts/benchmarks"
WORK = ROOT / "server/.local/optimization9h-20261004"
HARNESS = BENCH / "halogen0162_embedding_cache_gather_replay.c"
WRAPPER_TEMPLATE = BENCH / "halogen0162_embedding_cache_gather_image_wrapper.py"
RUNNER_TEMPLATE = BENCH / "halogen0162_embedding_cache_gather_owned_run.py"
HARNESS_SHA = "4eefc01e53e102d52d7828f930098224b3befa6151a0485684c64a91a94992f4"
WRAPPER_TEMPLATE_SHA = "7b4b753a2778c80ab6aabf0865211654042b498a6c30adce1b93f0a9b2304c64"
RUNNER_TEMPLATE_SHA = "3b2d931aa75847666772408db747220af5821dc54bfb6b8e8b074113cd3396a5"
PINS = {
    "halogen0162_embedding_cache_replay.c": "30abfb53cad7cfeed27409b70e3ac37c27b46db2d649acad73f3b4f4220ab9b3",
    "halogen0162_embedding_cache_image_wrapper.py": "d2364d1bb32af5d832336bce69b89e45063f72c1dbcd35ed548c49562d736210",
    "halogen0162_embedding_cache_owned_run.py": "8222a921019e3b626534996b74bf85232009478d117db9750ea6025e1e110fd7",
    "halogen0162_fc_replay.c": "8535dbe608b49f8bbad8a962359de59e78df1bd0b9cae922045277b6a1d77826",
    "halogen0162_fc_image_wrapper.py": "c1120b8ca7d50c508e94affafe7bf59ed329d3d72c751b9407cf1cb4383b7542",
    "halogen0162_fc_owned_run.py": "4377babdf8befd0481bd27e68a0c963e580a4285e0d0874c2700c03ac1a92152",
    "halogen0162_mtp_embedding_cache.c": "4de8014f186ce7bc9e4507f127543b69564ee88d01ab97779aedc73fac4436d4",
    "halogen0162_mtp_embedding_cache.h": "2b167c486a744cd0d78b2124da93f383778951bf6f11a9318c717a0c9263d309",
    HARNESS.name: HARNESS_SHA, WRAPPER_TEMPLATE.name: WRAPPER_TEMPLATE_SHA,
    RUNNER_TEMPLATE.name: RUNNER_TEMPLATE_SHA}


def valid_sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def source_bytes(path, expected):
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size < 1 << 20:
        raise ValueError("Bounded regular source file required: " + str(path))
    with path.open("rb") as stream:
        raw = stream.read((1 << 20) + 1)
    after = path.lstat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if (any(getattr(before, key) != getattr(after, key) for key in fields) or
            len(raw) != before.st_size or hashlib.sha256(raw).hexdigest() != expected):
        raise ValueError("Frozen source bytes/identity differ: " + str(path))
    return raw


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Expected exactly one reviewed template anchor: " + old)
    return text.replace(old, new, 1)


def write_exclusive(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--binary-sha256", required=True)
    parser.add_argument("--reviewed-harness-sha256", required=True)
    parser.add_argument("--source-sha256", required=True)
    args = parser.parse_args()
    if (not valid_sha(args.source_sha256) or not valid_sha(args.binary_sha256) or
            args.reviewed_harness_sha256 != HARNESS_SHA):
        raise ValueError("Independent preparer/binary pins and explicit reviewed harness pin required")
    binary = PurePosixPath(args.binary)
    if str(binary.parent) != "/home/revn/halogen-re" or not re.fullmatch(r"[A-Za-z0-9_-]+", binary.name):
        raise ValueError("New owned compiled binary required under /home/revn/halogen-re")
    source_bytes(Path(__file__).resolve(), args.source_sha256)
    sources = {name: source_bytes(BENCH / name, digest) for name, digest in PINS.items()}
    tag = uuid.uuid4().hex
    wrapper = BENCH / ("halogen0162_embedding_cache_gather_image_bound_" + tag + ".py")
    runner = BENCH / ("halogen0162_embedding_cache_gather_owned_bound_" + tag + ".py")
    wrapper_raw = sources[WRAPPER_TEMPLATE.name]
    text = sources[RUNNER_TEMPLATE.name].decode("utf-8")
    text = replace_once(text, "ROOT_SUPPLIES_REVIEWED_GATHER_HARNESS_SHA256", HARNESS_SHA)
    text = replace_once(text, "ROOT_SUPPLIES_NEW_COMPILED_GATHER_BINARY_PATH", args.binary)
    text = replace_once(text, "ROOT_SUPPLIES_NEW_COMPILED_GATHER_BINARY_SHA256", args.binary_sha256)
    text = replace_once(text, 'WRAPPER = ROOT / "scripts/benchmarks/' + WRAPPER_TEMPLATE.name + '"',
                        'WRAPPER = ROOT / "scripts/benchmarks/' + wrapper.name + '"')
    wrapper_sha = write_exclusive(wrapper, wrapper_raw)
    runner_sha = write_exclusive(runner, text.encode("utf-8"))
    plan = dict(schema="halogen0162.embedding-cache-gather-source-binding.v1",
        root_source_review_required=True, root_metadata_review_required=True,
        binary_path_and_hash_independently_supplied=True, binary_read_performed=False,
        wrapper=str(wrapper), wrapper_sha256=wrapper_sha, runner=str(runner), runner_sha256=runner_sha,
        preparer_source_sha256=args.source_sha256, source_pins=PINS, harness=str(HARNESS), harness_sha256=HARNESS_SHA,
        binary=args.binary, binary_sha256=args.binary_sha256, shared_core_only=True,
        copy_kernel="_ZN7halogen12_GLOBAL__N_114k_embed_gatherEPKtPKiPt", copy_grid=[1, 1, 1], copy_block=[256, 1, 1],
        original_m1_launches_expected=38, gather_copy_launches_expected=24,
        validation_copies_expected=128, owned_allocations_expected=4, owned_frees_expected=4,
        models_mounted=False, NPU_executed=False, acceptance_claim=False, end_to_end_throughput_qualified=False,
        colleague_server_preserved=True, admission_gib=22, reserve_gib=18, own_container_limit_gib=2,
        root_command=["python", str(runner), "--wrapper-sha256", wrapper_sha, "--source-sha256", runner_sha])
    plan_path = WORK / ("native-embedding-cache-gather-run-plan-" + tag + ".json")
    plan_sha = write_exclusive(plan_path, json.dumps(plan, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(plan=str(plan_path), plan_sha256=plan_sha, **plan), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
