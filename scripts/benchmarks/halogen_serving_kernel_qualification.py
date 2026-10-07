"""Owned CPU-only bridge qualification; baseline and qualify use fresh containers.

No flash_serve or provider code is imported or executed. A pinned plan is required
for every stage. Root owns container creation, native build and runtime execution.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SOURCE_NAMES = ("halogen_serving_kernel_bootstrap.py", "halogen_serving_kernel_qualification.py",
                "halogen_serving_kernel_identity.c", "halogen_serving_kernel_identity.h", "halogen_kernel_pid_self.h")
PLAN_SCHEMA = "halogen.serving-kernel-identity.cpu-plan.v1"
BASELINE_SCHEMA = "halogen.serving-kernel-identity.cpu-baseline.v1"
PRE_SCHEMA = "halogen.serving-kernel-identity.cpu-pre-exec.v1"
POST_SCHEMA = "halogen.serving-kernel-identity.cpu-post-exec.v1"
ARTIFACTS = Path("/artifacts")


def bridge():
    spec = importlib.util.spec_from_file_location("qualification_bridge", HERE / SOURCE_NAMES[0])
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def load_plan(api, path, digest):
    with api._verified_fd(path, digest, api.MAX_JSON_BYTES) as fd:
        value = json.loads(os.read(fd, api.MAX_JSON_BYTES + 1), object_pairs_hook=api._duplicates)
    keys = {"schema", "enabled", "nonce", "container_id", "source_sha256", "native_helper_path",
            "native_helper_sha256", "native_helper_bytes", "baseline_receipt_path", "baseline_receipt_sha256"}
    if (type(value) is not dict or set(value) != keys or value["schema"] != PLAN_SCHEMA or value["enabled"] is not True or
            type(value["source_sha256"]) is not dict or set(value["source_sha256"]) != set(SOURCE_NAMES)):
        raise ValueError("Exact explicitly enabled CPU plan required")
    api._nonce(value["nonce"]); api._sha(value["container_id"]); api._sha(value["native_helper_sha256"])
    for digest in value["source_sha256"].values(): api._sha(digest)
    if (value["source_sha256"][SOURCE_NAMES[-1]] != api.FROZEN_HEADER_SHA256 or
            value["native_helper_path"] != "/candidate/halogen_serving_kernel_identity.so" or
            type(value["native_helper_bytes"]) is not int or not 0 < value["native_helper_bytes"] <= 1024**2):
        raise ValueError("Native/header pin differs")
    if value["baseline_receipt_path"] is None:
        if value["baseline_receipt_sha256"] is not None: raise ValueError("Baseline fields must both be absent")
    else:
        if value["baseline_receipt_path"] != "/candidate/baseline.json": raise ValueError("Fixed baseline path required")
        api._sha(value["baseline_receipt_sha256"])
    return value


def check_pins(api, plan):
    for name, digest in plan["source_sha256"].items():
        with api._verified_fd(HERE / name, digest, 262144): pass
    with api._verified_fd(plan["native_helper_path"], plan["native_helper_sha256"], 1024**2,
                          exact=plan["native_helper_bytes"]): pass


def owned_snapshot(api, plan):
    value = api._snapshot()
    if value["task_count"] != 1 or not api._in_container({"cgroup": value.get("cgroup", "")}, plan["container_id"]):
        raise ValueError("Sole main task and full self-view container ID required")
    gettid = api.ctypes.CDLL(None).gettid; gettid.argtypes = []; gettid.restype = api.ctypes.c_int
    if gettid() != os.getpid(): raise ValueError("Main OS thread required")
    return value


def interpreter_pin(api):
    path = Path(sys.executable).resolve()
    raw = api._read_proc(path, 128 * 1024**2)
    pin = dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    with api._verified_fd(path, pin["sha256"], 128 * 1024**2, exact=pin["bytes"]): pass
    return pin


def payload_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def publish(api, path, value):
    api._publish_fresh(path, value)
    return hashlib.sha256(payload_bytes(value)).hexdigest()


def read_private(api, path, digest):
    value, raw, owner = api._read_receipt(path)
    if owner != os.getuid() or hashlib.sha256(raw).hexdigest() != api._sha(digest):
        raise ValueError("Private receipt owner/hash differs")
    return value


def baseline(api, plan, plan_sha):
    if plan["baseline_receipt_path"] is not None: raise ValueError("Baseline must have no prior receipt")
    output = ARTIFACTS / ("baseline-" + plan["nonce"] + ".json"); api._require_fresh_receipt(output)
    check_pins(api, plan); before = owned_snapshot(api, plan)
    if any(before["capabilities"][key] & api.BPF_MASK for key in api.CAP_KEYS):
        raise ValueError("Independent baseline must contain no BPF")
    if not before["capabilities"]["effective"] & (1 << 8): raise ValueError("Existing SETPCAP required")
    interpreter = interpreter_pin(api); after = owned_snapshot(api, plan)
    if not api._same_task(before, after) or before["capabilities"] != after["capabilities"]:
        raise ValueError("Baseline changed")
    receipt = dict(schema=BASELINE_SCHEMA, nonce=plan["nonce"], container_id=plan["container_id"],
                   plan_sha256=plan_sha, source_sha256=plan["source_sha256"],
                   native_helper_sha256=plan["native_helper_sha256"], native_helper_bytes=plan["native_helper_bytes"],
                   snapshot=after, interpreter=interpreter, native_probe_performed=False)
    digest = publish(api, output, receipt)
    print(json.dumps(dict(schema=BASELINE_SCHEMA, receipt_sha256=digest, nonce=plan["nonce"], native_probe_performed=False)))


def expected_masks(api, plan):
    if plan["baseline_receipt_path"] is None: raise ValueError("Independent no-BPF baseline receipt required")
    receipt = read_private(api, plan["baseline_receipt_path"], plan["baseline_receipt_sha256"])
    if (receipt.get("schema") != BASELINE_SCHEMA or receipt.get("native_probe_performed") is not False or
            receipt.get("source_sha256") != plan["source_sha256"] or
            receipt.get("native_helper_sha256") != plan["native_helper_sha256"] or
            receipt.get("native_helper_bytes") != plan["native_helper_bytes"] or
            receipt.get("nonce") == plan["nonce"] or receipt.get("container_id") == plan["container_id"]):
        raise ValueError("Separate pinned baseline container required")
    api._nonce(receipt["nonce"]); api._sha(receipt["container_id"])
    masks = api._masks(receipt["snapshot"]["capabilities"])
    if (any(masks[key] & api.BPF_MASK for key in api.CAP_KEYS) or not masks["effective"] & (1 << 8) or
            receipt["snapshot"]["task_count"] != 1 or not api._in_container(
                {"cgroup": receipt["snapshot"].get("cgroup", "")}, receipt["container_id"])):
        raise ValueError("Independent no-BPF sole-task baseline required")
    before = {key: masks[key] | (api.BPF_MASK if key in {"effective", "permitted", "bounding"} else 0) for key in api.CAP_KEYS}
    return receipt, dict(only_added="CAP_BPF", baseline_masks=masks, expected_before_masks=before)


def qualify(api, plan, plan_path, plan_sha):
    prior, policy = expected_masks(api, plan)
    output = ARTIFACTS / ("pre-exec-" + plan["nonce"] + ".json")
    api._require_fresh_receipt(output)
    api._require_fresh_receipt(ARTIFACTS / ("post-exec-" + plan["nonce"] + ".json"))
    check_pins(api, plan); before = owned_snapshot(api, plan)
    if before["capabilities"] != policy["expected_before_masks"]: raise ValueError("BPF-only container delta differs")
    interpreter = prior["interpreter"]
    if interpreter != interpreter_pin(api): raise ValueError("Baseline interpreter pin differs")
    environment = dict(os.environ); environment_sha = api.digest_json(environment)
    with api._verified_fd(interpreter["path"], interpreter["sha256"], 128 * 1024**2, exact=interpreter["bytes"]) as fd:
        native_plan = dict(plan, capability_policy=policy)
        native = api.validate_native(api._observe_native(native_plan), native_plan, before)
        after = owned_snapshot(api, plan)
        if not api._same_task(before, after) or after["capabilities"] != policy["baseline_masks"]:
            raise ValueError("Probe/drop changed task or baseline")
        receipt = dict(schema=PRE_SCHEMA, nonce=plan["nonce"], container_id=plan["container_id"], plan_sha256=plan_sha,
                       source_sha256=plan["source_sha256"], native_helper_sha256=plan["native_helper_sha256"],
                       baseline_receipt_sha256=plan["baseline_receipt_sha256"], before=before, after=after,
                       capability_policy=policy, kernel_identity=native, interpreter=interpreter,
                       environment_sha256=environment_sha, post_exec_verified=False, qualifications=False)
        pre_sha = publish(api, output, receipt)
        check_pins(api, plan); api._check_fd(fd, interpreter["sha256"], 128 * 1024**2, exact=interpreter["bytes"])
        final = owned_snapshot(api, plan)
        if not api._same_task(after, final) or final["capabilities"] != policy["baseline_masks"] or api.digest_json(dict(os.environ)) != environment_sha:
            raise ValueError("Task/environment changed before exec")
        argv = [interpreter["path"], "-I", str(Path(__file__).resolve()), "report", "--plan", str(plan_path),
                "--plan-sha256", plan_sha, "--pre-exec-sha256", pre_sha]
        os.execve(fd, argv, environment)
        raise RuntimeError("Exec returned")


def report(api, plan, plan_sha, pre_sha):
    check_pins(api, plan); prior, policy = expected_masks(api, plan)
    pre = read_private(api, ARTIFACTS / ("pre-exec-" + plan["nonce"] + ".json"), pre_sha)
    if (pre.get("schema") != PRE_SCHEMA or pre.get("nonce") != plan["nonce"] or pre.get("container_id") != plan["container_id"] or
            pre.get("plan_sha256") != plan_sha or pre.get("source_sha256") != plan["source_sha256"] or
            pre.get("baseline_receipt_sha256") != plan["baseline_receipt_sha256"] or pre.get("capability_policy") != policy or
            pre.get("interpreter") != prior["interpreter"] or pre.get("post_exec_verified") is not False or pre.get("qualifications") is not False):
        raise ValueError("Pre-exec receipt binding differs")
    current = owned_snapshot(api, plan)
    if (not api._same_task(pre["before"], current) or not api._same_task(pre["after"], current) or
            current["capabilities"] != policy["baseline_masks"] or api.digest_json(dict(os.environ)) != pre["environment_sha256"]):
        raise ValueError("Exec did not preserve identity/baseline/environment")
    api.validate_native(pre["kernel_identity"], dict(capability_policy=policy), current)
    interpreter = prior["interpreter"]
    with api._verified_fd("/proc/self/exe", interpreter["sha256"], 128 * 1024**2, exact=interpreter["bytes"], follow_proc=True):
        final = owned_snapshot(api, plan)
        if not api._same_task(current, final) or final["capabilities"] != policy["baseline_masks"]:
            raise ValueError("Reporter changed")
    value = dict(pre, schema=POST_SCHEMA, reporter_snapshot=final, pre_exec_receipt_sha256=pre_sha,
                 post_exec_verified=True, cpu_identity_capability_exec_qualified=True, qualifications=False)
    digest = publish(api, ARTIFACTS / ("post-exec-" + plan["nonce"] + ".json"), value)
    print(json.dumps(dict(schema=POST_SCHEMA, nonce=plan["nonce"], pid=final["pid"], start_ticks=final["start_ticks"],
                         kernel_pid=pre["kernel_identity"]["kernel_pid"], kernel_tgid=pre["kernel_identity"]["kernel_tgid"],
                         receipt_sha256=digest, post_exec_verified=True, cpu_identity_capability_exec_qualified=True)))


def main():
    class QuietParser(argparse.ArgumentParser):
        def error(self, message): raise ValueError("Invalid CPU qualification options")
    parser = QuietParser(description=__doc__)
    parser.add_argument("action", choices=("baseline", "qualify", "report"))
    parser.add_argument("--plan", type=Path, required=True); parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--pre-exec-sha256")
    args = parser.parse_args(); api = bridge(); api._require_linux(); plan = load_plan(api, args.plan, args.plan_sha256)
    if args.action == "baseline":
        if args.pre_exec_sha256: raise ValueError("Unexpected reporter option")
        baseline(api, plan, args.plan_sha256)
    elif args.action == "qualify":
        if args.pre_exec_sha256: raise ValueError("Unexpected reporter option")
        qualify(api, plan, args.plan, args.plan_sha256)
    else:
        if not args.pre_exec_sha256: raise ValueError("Pinned pre-exec receipt required")
        report(api, plan, args.plan_sha256, args.pre_exec_sha256)


if __name__ == "__main__":
    try: main()
    except Exception as error:
        print(json.dumps(dict(passed=False, error_type=type(error).__name__, details_redacted=True)), file=sys.stderr)
        raise SystemExit(1)
