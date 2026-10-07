"""Default-off isolated copy of the pinned authenticated service engine boundary.

No installed entrypoint or lifecycle default imports or calls this adapter.
Preparation is offline. Only an enabled pinned policy plus explicit activation
may enter the final-env engine boundary; root owns admission and actual launch.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

SERVICE_SHA256 = "e8b34cad609aef2dfe32c3f183baa9c9bb4e30114e6e65668664e133f5271ac6"
ENTRYPOINT_SHA256 = "e68722b13e6d5f5cb43fbda89f3ea3c92c13be5a8da96113c91b4cfee08a1033"
AUTHENTICATED_SHA256 = "f3ee2640146141aa87b0455e01384c93a1c41fcfa256a9d30ba04105b46564b0"
POLICY_SCHEMA = "halogen.serving-kernel-identity.adapter-policy.v1"
BASELINE_SCHEMA = "halogen.serving-kernel-identity.cpu-baseline.v1"
API_NEEDLE = b"/halogen/tools/serve_api.py"
AUTH_API = b"/candidate/auth_api.py"
ADAPTER_COMMAND = b"python3 -I /candidate/halogen_serving_kernel_adapter.py engine"
POLICY_PATH = "/candidate/serving-kernel-adapter-policy.json"
POLICY_SHA_PATH = "/candidate/serving-kernel-adapter-policy.sha256"
ENGINE_LAUNCH = (b'  "${_hg_flash_serve:-/usr/local/bin/flash_serve}" --ck "$HALOGEN_CHECKPOINT" \\\n'
                 b'      --port "$ENG_PORT" --bind 127.0.0.1 \\\n'
                 b'      --slots "$ENG_SLOTS" --ctx "$ENG_CTX" --max-tok "$ENG_MAX_TOK" --kv-pool "$ENG_POOL" &\n')
WRAPPED_LAUNCH = (b"  " + ADAPTER_COMMAND + b" --policy " + POLICY_PATH.encode() + b' \\\n'
                  b'      --policy-sha256 "$(cat ' + POLICY_SHA_PATH.encode() + b')" --activate -- ' + ENGINE_LAUNCH[2:])
NPU_GUARD = (b'  if [ -n "${HALOGEN_NPU_MODELS:-}" ] || [ "${_hg_npu_alone:-0}" != 0 ]; then\n'
             b'    echo "halogen identity adapter: NPU configuration refused" >&2; exit 1\n'
             b'  fi\n')


def bootstrap():
    path = Path(__file__).resolve().with_name("halogen_serving_kernel_bootstrap.py")
    spec = importlib.util.spec_from_file_location("service_identity_bridge", path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def render(source, service_source, *, activate=False):
    if hashlib.sha256(source).hexdigest() != ENTRYPOINT_SHA256 or hashlib.sha256(service_source).hexdigest() != SERVICE_SHA256:
        raise ValueError("Frozen service/entrypoint source differs")
    if source.count(API_NEEDLE) != 5: raise ValueError("Exactly five API substitutions required")
    authenticated = source.replace(API_NEEDLE, AUTH_API)
    if hashlib.sha256(authenticated).hexdigest() != AUTHENTICATED_SHA256: raise ValueError("Authenticated service pin differs")
    if activate is not True: return authenticated
    if (authenticated.count(ENGINE_LAUNCH) != 1 or authenticated.count(b"all)\n") != 1 or
            authenticated.count(ENGINE_LAUNCH + b"  ENGINE_PID=$!\n") != 1):
        raise ValueError("Exact all engine boundary differs")
    return authenticated.replace(b"all)\n", b"all)\n" + NPU_GUARD).replace(ENGINE_LAUNCH, WRAPPED_LAUNCH)


def isolate_command(command, *, activate=False):
    """Pure reviewed overlay of service.command(m); callers retain owned checks."""
    if activate is not True: return list(command)
    caps = [item for item in command if item.startswith("--cap-add")]
    if (not command or command[0] != "create" or caps != ["--cap-add=SYS_PTRACE"] or
            command.count("--security-opt=seccomp=unconfined") != 1 or
            any(item.startswith(("--cgroupns", "--privileged", "--cap-drop")) for item in command)):
        raise ValueError("Exact existing SYS_PTRACE/seccomp service command required")
    position = command.index("--cap-add=SYS_PTRACE") + 1
    return list(command[:position]) + ["--cap-add=BPF", "--cgroupns=host"] + list(command[position:])


def capability_policy(api, masks):
    masks = api._masks(masks)
    if (any(masks[key] & api.BPF_MASK for key in api.CAP_KEYS) or
            any(not masks[key] & (1 << 19) for key in ("effective", "permitted", "bounding")) or
            not masks["effective"] & (1 << 8)):
        raise ValueError("Independent SYS_PTRACE baseline and existing SETPCAP required")
    before = {key: masks[key] | (api.BPF_MASK if key in {"effective", "permitted", "bounding"} else 0) for key in api.CAP_KEYS}
    return dict(only_added="CAP_BPF", baseline_masks=masks, expected_before_masks=before)


def load_policy(api, path, digest):
    if str(path) != POLICY_PATH: raise ValueError("Fixed candidate policy path required")
    with api._verified_fd(path, digest, api.MAX_JSON_BYTES) as fd:
        value = json.loads(os.read(fd, api.MAX_JSON_BYTES + 1), object_pairs_hook=api._duplicates)
    keys = {"schema", "enabled", "scope", "nonce", "service_run_id", "container_id", "manifest_sha256",
            "service_sha256", "upstream_entrypoint_sha256", "authenticated_entrypoint_sha256", "candidate_entrypoint_sha256",
            "adapter_sha256", "bootstrap_sha256", "native_source_sha256", "frozen_header_sha256", "native_helper_path",
            "native_helper_sha256", "native_helper_bytes", "baseline_receipt_path", "baseline_receipt_sha256", "argv_sha256"}
    if (type(value) is not dict or set(value) != keys or value["schema"] != POLICY_SCHEMA or value["enabled"] is not True or
            value["scope"] != "all-engine-task-only"):
        raise ValueError("Exact enabled engine-only adapter policy required")
    for key in ("nonce", "service_run_id"): api._nonce(value[key])
    for key in keys:
        if key.endswith("sha256") or key == "container_id": api._sha(value[key])
    if (value["service_sha256"] != SERVICE_SHA256 or value["upstream_entrypoint_sha256"] != ENTRYPOINT_SHA256 or
            value["authenticated_entrypoint_sha256"] != AUTHENTICATED_SHA256 or
            value["frozen_header_sha256"] != api.FROZEN_HEADER_SHA256 or
            value["baseline_receipt_path"] != "/candidate/serving-kernel-baseline.json" or
            value["native_helper_path"] != "/candidate/halogen_serving_kernel_identity.so" or
            type(value["native_helper_bytes"]) is not int or not 0 < value["native_helper_bytes"] <= 1024**2):
        raise ValueError("Adapter source/baseline/native pins differ")
    return value


def read_baseline(api, policy):
    value, raw, owner = api._read_receipt(policy["baseline_receipt_path"])
    if (owner != os.getuid() or hashlib.sha256(raw).hexdigest() != policy["baseline_receipt_sha256"] or
            value.get("schema") != BASELINE_SCHEMA or value.get("native_probe_performed") is not False or
            value.get("native_helper_sha256") != policy["native_helper_sha256"] or value.get("native_helper_bytes") != policy["native_helper_bytes"]):
        raise ValueError("Independent baseline owner/hash/helper binding differs")
    api._nonce(value["nonce"]); api._sha(value["container_id"])
    pins = value["source_sha256"]
    if (value["container_id"] == policy["container_id"] or value["nonce"] == policy["nonce"] or
            value["snapshot"]["task_count"] != 1 or not api._in_container({"cgroup": value["snapshot"].get("cgroup", "")}, value["container_id"]) or
            pins.get("halogen_serving_kernel_bootstrap.py") != policy["bootstrap_sha256"] or
            pins.get("halogen_serving_kernel_identity.c") != policy["native_source_sha256"] or
            pins.get("halogen_kernel_pid_self.h") != api.FROZEN_HEADER_SHA256):
        raise ValueError("Separate observed baseline/source binding required")
    return capability_policy(api, value["snapshot"]["capabilities"])


def derive_launch_plan(api, policy, argv, environment, capability):
    api._argv_check(argv)
    if (api.digest_json(argv) != policy["argv_sha256"] or environment.get("HALOGEN_CHECKPOINT_VARIANT") != "v2" or
            environment.get("HALOGEN_NPU_MODELS", "") or environment.get("_hg_npu_alone", "0") != "0"):
        raise ValueError("Sealed v2 argv or NPU-free environment differs")
    keys = ("nonce", "service_run_id", "container_id", "manifest_sha256", "bootstrap_sha256", "native_source_sha256",
            "frozen_header_sha256", "native_helper_path", "native_helper_sha256", "native_helper_bytes", "argv_sha256")
    value = {key: policy[key] for key in keys}
    value.update(schema=api.PLAN_SCHEMA, enabled=True, engine_sha256=api.ENGINE_SHA256, engine_bytes=api.ENGINE_BYTES,
                 environment_sha256=api.digest_json(environment), capability_policy=capability)
    return api.validate_plan(value)


def engine(policy_path, policy_sha, argv, *, activate=False):
    if activate is not True: raise ValueError("Adapter requires explicit activation")
    api = bootstrap(); api._require_linux(); policy = load_policy(api, policy_path, policy_sha)
    capability = read_baseline(api, policy)
    with api._verified_fd(Path(__file__).resolve(), policy["adapter_sha256"], 262144):
        with api._verified_fd("/candidate/entrypoint-wsl-candidate.sh", policy["candidate_entrypoint_sha256"], 262144):
            api._argv_check(argv)
            if api.digest_json(argv) != policy["argv_sha256"]: raise ValueError("Sealed argv differs")
            # Bash sets this to the invoked executable; restore the direct-engine
            # value before hashing and forwarding the complete environment.
            os.environ["_"] = argv[0]
            plan = derive_launch_plan(api, policy, argv, dict(os.environ), capability)
            path = Path("/tmp/halogen-serving-adapter-plan-" + policy["nonce"] + ".json")
            binding_path = Path("/tmp/halogen-serving-adapter-binding-" + policy["nonce"] + ".json")
            for fresh in (path, binding_path, api.PREFIX + policy["nonce"] + ".json"): api._require_fresh_receipt(fresh)
            payload = json.dumps(plan, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
            plan_sha = hashlib.sha256(payload).hexdigest(); api._publish_fresh(path, plan)
            binding = dict(schema="halogen.serving-kernel-identity.adapter-binding.v1", policy_sha256=policy_sha,
                           launch_plan_sha256=plan_sha, nonce=policy["nonce"], service_run_id=policy["service_run_id"],
                           container_id=policy["container_id"], manifest_sha256=policy["manifest_sha256"],
                           adapter_sha256=policy["adapter_sha256"], service_sha256=policy["service_sha256"],
                           candidate_entrypoint_sha256=policy["candidate_entrypoint_sha256"], baseline_receipt_sha256=policy["baseline_receipt_sha256"],
                           argv_sha256=plan["argv_sha256"], environment_sha256=plan["environment_sha256"],
                           environment_scope="after-all-entrypoint-setup", capability_scope="engine-task-only",
                           ancestor_bpf_removal_claimed=False, post_exec_verified=False, qualifications=False)
            api._publish_fresh(binding_path, binding)
            api.launch(path, plan_sha, argv, activate=True)


def prepare(args):
    with args.entrypoint.open("rb") as source_file: source = source_file.read(262145)
    with args.service_script.open("rb") as service_file: service = service_file.read(262145)
    if len(source) > 262144 or len(service) > 262144: raise ValueError("Bounded source required")
    result = render(source, service, activate=args.activate)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as output: output.write(result); output.flush(); os.fsync(output.fileno())
    print(json.dumps(dict(schema="halogen.serving-kernel-identity.adapter-preparation.v1", enabled=args.activate,
                          service_sha256=SERVICE_SHA256, upstream_entrypoint_sha256=ENTRYPOINT_SHA256,
                          authenticated_entrypoint_sha256=AUTHENTICATED_SHA256,
                          candidate_entrypoint_sha256=hashlib.sha256(result).hexdigest(), candidate_entrypoint_bytes=len(result),
                          api_substitution_count=5, engine_boundary_count=int(args.activate), lifecycle_defaults_modified=False)))


def main():
    class QuietParser(argparse.ArgumentParser):
        def error(self, message): raise ValueError("Invalid adapter options")
    parser = QuietParser(description=__doc__); sub = parser.add_subparsers(dest="action", required=True)
    prep = sub.add_parser("prepare"); prep.add_argument("--entrypoint", type=Path, required=True)
    prep.add_argument("--service-script", type=Path, required=True); prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--activate", action="store_true", default=False)
    run = sub.add_parser("engine"); run.add_argument("--policy", type=Path, required=True)
    run.add_argument("--policy-sha256", required=True); run.add_argument("--activate", action="store_true", default=False)
    supplied = sys.argv[1:]; split = supplied.index("--") if "--" in supplied else len(supplied)
    args = parser.parse_args(supplied[:split]); argv = supplied[split + 1:]
    if args.action == "prepare":
        if argv: raise ValueError("Preparation takes no engine argv")
        prepare(args)
    else: engine(args.policy, args.policy_sha256, argv, activate=args.activate)


if __name__ == "__main__":
    try: main()
    except Exception as error:
        print(json.dumps(dict(passed=False, error_type=type(error).__name__, details_redacted=True)), file=sys.stderr)
        raise SystemExit(1)
