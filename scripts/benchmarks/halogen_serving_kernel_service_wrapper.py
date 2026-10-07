"""Explicitly activated, sealed, isolated overlay around the stock service main.

This file changes no installed source or lifecycle default. Windows execution
delegates admission/lease/guard/cleanup to the frozen original service module.
Root owns the real launch; importing this module performs no WSL/device action.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = ROOT / "backends/halogen-wsl2-0.16.2/scripts/service.py"
SCHEMA = "halogen.serving-kernel-identity.service-overlay.v1"
IMAGE = "ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a"
SOURCE_PATHS = ("backends/halogen-wsl2-0.16.2/scripts/service.py",
                "scripts/benchmarks/halogen_serving_kernel_service_wrapper.py",
                "scripts/benchmarks/halogen_serving_kernel_adapter.py",
                "scripts/benchmarks/halogen_serving_kernel_bootstrap.py",
                "scripts/benchmarks/halogen_serving_kernel_identity.c",
                "scripts/benchmarks/halogen_serving_kernel_identity.h",
                "scripts/benchmarks/halogen_kernel_pid_self.h")

# Structured argv to root-owned Python; no shell interpolation or credential data.
LINUX_IO = r'''
import hashlib,json,os,stat,sys
task=json.loads(sys.argv[1])
def check(path,digest,maximum,private=False,exact=None):
 f=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
 try:
  s=os.fstat(f)
  if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or not 0<s.st_size<=maximum or (exact is not None and s.st_size!=exact): raise ValueError('file extent')
  if private and (s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o600): raise ValueError('private ownership')
  raw=os.read(f,maximum+1)
  if len(raw)!=s.st_size or hashlib.sha256(raw).hexdigest()!=digest: raise ValueError('file pin')
 finally: os.close(f)
 return raw
check(task['helper']['linux_path'],task['helper']['sha256'],1048576,exact=task['helper']['bytes'])
baseline_raw=check(task['baseline']['linux_path'],task['baseline']['sha256'],16384,private=True)
canonical=json.dumps(json.loads(baseline_raw),sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
if hashlib.sha256(canonical).hexdigest()!=task['baseline_json_sha256']:raise ValueError('baseline semantic pin')
directory=task['directory']
if task['action']=='prepare':
 os.mkdir(directory,0o700)
 for name in ('policy.json','policy.sha256'):
  f=os.open(directory+'/'+name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600);os.close(f)
elif task['action']=='seal':
 s=os.stat(directory,follow_symlinks=False)
 if not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o700:raise ValueError('owned directory')
 raw=(json.dumps(task['policy'],sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
 if len(raw)>16384:raise ValueError('bounded policy')
 digest=hashlib.sha256(raw).hexdigest()
 for name,data in (('policy.json',raw),('policy.sha256',(digest+'\n').encode())):
  f=os.open(directory+'/'+name,os.O_WRONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
  try:
   s=os.fstat(f)
   if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o600 or s.st_size!=0:raise ValueError('fresh placeholder')
   pending=memoryview(data)
   while pending:
    n=os.write(f,pending)
    if n<=0:raise OSError('write progress')
    pending=pending[n:]
   os.fsync(f)
  finally:os.close(f)
elif task['action']=='verify-sealed':
 check(directory+'/policy.json',task['policy_sha256'],16384,private=True)
 check(directory+'/policy.sha256',hashlib.sha256((task['policy_sha256']+'\n').encode()).hexdigest(),65,private=True,exact=65)
elif task['action']!='check':raise ValueError('action')
print(json.dumps({'passed':True}))
'''


def load_local(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def modules():
    adapter = load_local("isolated_service_adapter", Path(__file__).with_name("halogen_serving_kernel_adapter.py"))
    return adapter, adapter.bootstrap()


@contextmanager
def local_pin(api, path, digest, maximum):
    # CRT text-mode reads translate CRLF; pins always cover the original bytes.
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        api._check_fd(fd, digest, maximum)
        yield fd
    finally: os.close(fd)


def validate_plan(api, adapter, plan, argv):
    keys = {"schema", "enabled", "nonce", "scope", "image", "source_sha256", "service_argv_sha256", "helper", "baseline", "policy_directory"}
    if (type(plan) is not dict or set(plan) != keys or plan["schema"] != SCHEMA or plan["enabled"] is not True or
            plan["scope"] != "v2-all-engine-task-only" or plan["image"] != IMAGE or
            type(plan["source_sha256"]) is not dict or set(plan["source_sha256"]) != set(SOURCE_PATHS)):
        raise ValueError("Exact enabled sealed service overlay required")
    api._nonce(plan["nonce"]); api._sha(plan["service_argv_sha256"])
    if api.digest_json(argv) != plan["service_argv_sha256"]: raise ValueError("Normal service argument hash differs")
    if plan["policy_directory"] != "/home/revn/halogen-re/serving-kernel-service-" + plan["nonce"]:
        raise ValueError("Fresh owned Linux policy directory required")
    for item, keys in ((plan["helper"], {"linux_path", "sha256", "bytes"}), (plan["baseline"], {"windows_path", "windows_sha256", "linux_path", "sha256"})):
        if type(item) is not dict or set(item) != keys or type(item["linux_path"]) is not str or not re.fullmatch(r"/home/revn/halogen-re/[A-Za-z0-9_./-]+", item["linux_path"]) or ".." in Path(item["linux_path"]).parts:
            raise ValueError("Exact bounded owned Linux input required")
        api._sha(item["sha256"])
    if type(plan["helper"]["bytes"]) is not int or not 0 < plan["helper"]["bytes"] <= 1024**2: raise ValueError("Bounded native helper required")
    for relative, digest in plan["source_sha256"].items():
        with local_pin(api, ROOT / relative, digest, 262144): pass
    if plan["source_sha256"][SOURCE_PATHS[0]] != adapter.SERVICE_SHA256: raise ValueError("Frozen service source differs")
    api._sha(plan["baseline"]["windows_sha256"])
    with local_pin(api, plan["baseline"]["windows_path"], plan["baseline"]["windows_sha256"], api.MAX_JSON_BYTES) as fd:
        baseline = json.loads(os.read(fd, api.MAX_JSON_BYTES + 1), object_pairs_hook=api._duplicates)
    if (baseline.get("schema") != adapter.BASELINE_SCHEMA or baseline.get("native_probe_performed") is not False or
            baseline.get("native_helper_sha256") != plan["helper"]["sha256"] or baseline.get("native_helper_bytes") != plan["helper"]["bytes"]):
        raise ValueError("Independent measured baseline/helper differs")
    api._nonce(baseline["nonce"]); api._sha(baseline["container_id"])
    if (baseline["nonce"] == plan["nonce"] or baseline["snapshot"]["task_count"] != 1 or
            not api._in_container({"cgroup": baseline["snapshot"].get("cgroup", "")}, baseline["container_id"])):
        raise ValueError("Separate actual baseline task/container binding required")
    adapter.capability_policy(api, baseline["snapshot"]["capabilities"])
    for relative in SOURCE_PATHS[3:]:
        if baseline["source_sha256"].get(Path(relative).name) != plan["source_sha256"][relative]: raise ValueError("Baseline source pin differs")
    return baseline


def expected_argv(api, manifest):
    env = manifest["environment"]
    argv = [api.ENGINE, "--ck", env["HALOGEN_CHECKPOINT"], "--port", env.get("HALOGEN_PORT", "8730"), "--bind", "127.0.0.1",
            "--slots", env["HALOGEN_KV_SLOTS"], "--ctx", env["HALOGEN_CTX"], "--max-tok", str(min(int(env.get("HALOGEN_MAX_TOK", "32768")), int(env["HALOGEN_CTX"]))),
            "--kv-pool", env["HALOGEN_KV_POOL_POSITIONS"]]
    api._argv_check(argv)
    if env.get("HALOGEN_CHECKPOINT_VARIANT") != "v2" or env.get("HALOGEN_NPU_MODELS", ""): raise ValueError("Exact NPU-free v2 serving scope required")
    return argv


class Overlay:
    def __init__(self, service, adapter, api, plan, root_plan_sha, argv):
        self.service, self.adapter, self.api, self.plan = service, adapter, api, plan
        self.root_plan_sha, self.argv = root_plan_sha, argv
        self.original_manifest, self.original_command, self.original_docker = service.build_manifest, service.command, service.r.docker
        self.manifest = None; self.attempt = None; self.cid = None; self.policy_sha = None; self.baseline_json_sha = None

    def inputs(self):
        baseline = validate_plan(self.api, self.adapter, self.plan, self.argv)
        self.baseline_json_sha = self.api.digest_json(baseline)

    def linux(self, action, **extra):
        machine = self.service.r.MACHINE
        task = dict(action=action, helper=self.plan["helper"], baseline=self.plan["baseline"], directory=self.plan["policy_directory"],
                    baseline_json_sha256=self.baseline_json_sha, **extra)
        command = self.service.portable.wsl_command(machine["distro"], "root", ["python3", "-I", "-c", LINUX_IO,
                                                                             json.dumps(task, sort_keys=True, separators=(",", ":"))])
        result = json.loads(self.service.r.invoke(command, 30))
        if result != {"passed": True}: raise ValueError("Owned Linux input operation failed")

    def build_manifest(self, options, attempt, run_id):
        self.inputs(); self.linux("prepare")
        manifest = self.original_manifest(options, attempt, run_id)
        expected_argv(self.api, manifest)
        directory = self.plan["policy_directory"]
        manifest["mounts"].update({"/candidate/halogen_serving_kernel_adapter.py": self.service.r.linux_path(Path(__file__).with_name("halogen_serving_kernel_adapter.py")),
                                  "/candidate/halogen_serving_kernel_bootstrap.py": self.service.r.linux_path(Path(__file__).with_name("halogen_serving_kernel_bootstrap.py")),
                                  "/candidate/halogen_serving_kernel_identity.so": self.plan["helper"]["linux_path"],
                                  "/candidate/serving-kernel-baseline.json": self.plan["baseline"]["linux_path"],
                                  self.adapter.POLICY_PATH: directory + "/policy.json", self.adapter.POLICY_SHA_PATH: directory + "/policy.sha256"})
        manifest["kernel_identity_overlay"] = dict(schema=SCHEMA, root_plan_sha256=self.root_plan_sha, nonce=self.plan["nonce"],
                                                  sources=self.plan["source_sha256"], baseline_receipt_sha256=self.plan["baseline"]["sha256"],
                                                  native_helper_sha256=self.plan["helper"]["sha256"], only_added_capability="CAP_BPF", cgroup_namespace="host",
                                                  scope="engine-task-only", ancestor_bpf_removal_claimed=False)
        self.manifest, self.attempt = manifest, Path(attempt)
        return manifest

    def command(self, manifest):
        if manifest is not self.manifest: raise ValueError("Wrong private manifest")
        return self.adapter.isolate_command(self.original_command(manifest), activate=True)

    def check_created(self, cid):
        self.api._sha(cid); info = self.service.r.inspect(cid); self.service.owned(info, cid, self.manifest)
        host, config = info.get("HostConfig", {}), info.get("Config", {})
        caps = host.get("CapAdd") or []
        if (info.get("Id") != cid or info.get("State", {}).get("Running") is not False or config.get("Image") != IMAGE or
                sorted(str(value).removeprefix("CAP_") for value in caps) != ["BPF", "SYS_PTRACE"] or host.get("CapDrop") or
                host.get("Privileged") is not False or host.get("CgroupnsMode") != "host" or
                "seccomp=unconfined" not in (host.get("SecurityOpt") or [])):
            raise ValueError("Created container identity/capability scope differs")
        mounts = info.get("Mounts", [])
        if len(mounts) != len(self.manifest["mounts"]): raise ValueError("Created mount count differs")
        for destination, source in self.manifest["mounts"].items():
            matches = [item for item in mounts if item.get("Destination") == destination]
            if len(matches) != 1 or matches[0].get("Source") != source or matches[0].get("RW") is not False or matches[0].get("Type") != "bind":
                raise ValueError("Created read-only mount differs")
        for key, value in self.manifest["environment"].items():
            if [item for item in config.get("Env", []) if item.startswith(key + "=")] != [key + "=" + value]:
                raise ValueError("Created environment binding differs")

    def policy(self, cid, manifest_sha):
        pins = self.plan["source_sha256"]
        return dict(schema=self.adapter.POLICY_SCHEMA, enabled=True, scope="all-engine-task-only", nonce=self.plan["nonce"],
                    service_run_id=self.manifest["run_id"], container_id=cid, manifest_sha256=manifest_sha,
                    service_sha256=self.adapter.SERVICE_SHA256, upstream_entrypoint_sha256=self.adapter.ENTRYPOINT_SHA256,
                    authenticated_entrypoint_sha256=self.adapter.AUTHENTICATED_SHA256, candidate_entrypoint_sha256=self.manifest["entrypoint_sha256"],
                    adapter_sha256=pins[SOURCE_PATHS[2]], bootstrap_sha256=pins[SOURCE_PATHS[3]], native_source_sha256=pins[SOURCE_PATHS[4]],
                    frozen_header_sha256=pins[SOURCE_PATHS[6]], native_helper_path="/candidate/halogen_serving_kernel_identity.so",
                    native_helper_sha256=self.plan["helper"]["sha256"], native_helper_bytes=self.plan["helper"]["bytes"],
                    baseline_receipt_path="/candidate/serving-kernel-baseline.json", baseline_receipt_sha256=self.plan["baseline"]["sha256"],
                    argv_sha256=self.api.digest_json(expected_argv(self.api, self.manifest)))

    def docker(self, *args, **kwargs):
        if args and args[0] == "create":
            if self.cid is not None or self.manifest is None: raise ValueError("One owned creation required")
            self.inputs(); self.linux("check")
            raw = self.api._read_proc(self.attempt / "manifest.json", 1048576)
            if json.loads(raw) != self.manifest: raise ValueError("Persisted private manifest differs")
            cid = self.original_docker(*args, **kwargs)
            self.check_created(cid)
            policy = self.policy(cid, hashlib.sha256(raw).hexdigest())
            self.policy_sha = hashlib.sha256((json.dumps(policy, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()).hexdigest()
            self.linux("seal", policy=policy); self.cid = cid
            self.service.atomic(self.attempt / "kernel-identity-overlay-seal.json", dict(schema=SCHEMA, container_id=cid,
                                root_plan_sha256=self.root_plan_sha, policy_sha256=self.policy_sha, nonce=self.plan["nonce"],
                                manifest_sha256=policy["manifest_sha256"], argv_sha256=policy["argv_sha256"], ancestor_bpf_removal_claimed=False))
            return cid
        if args and args[0] == "start":
            if args != ("start", self.cid) or self.policy_sha is None: raise ValueError("Unsealed start refused")
            self.inputs(); self.check_created(self.cid); self.linux("verify-sealed", policy_sha256=self.policy_sha)
        return self.original_docker(*args, **kwargs)


def run(plan_path, plan_sha, argv, *, activate=False):
    if activate is not True: raise ValueError("Service overlay requires explicit activation")
    if os.name != "nt": raise OSError("Windows stock service controller required")
    adapter, api = modules()
    with local_pin(api, plan_path, plan_sha, api.MAX_JSON_BYTES) as fd:
        plan = json.loads(os.read(fd, api.MAX_JSON_BYTES + 1), object_pairs_hook=api._duplicates)
    validate_plan(api, adapter, plan, argv)
    original_path = list(sys.path); original_managed = os.environ.get("ALLOY_MANAGED")
    service = None; overlay = None; original_entrypoint = None
    try:
        sys.path.insert(0, str(SERVICE_PATH.parent))
        service = load_local("isolated_stock_halogen_service", SERVICE_PATH)
        options = service.options(argv)
        if options.checkpoint != "v2" or options.stop or options.status or options.guard or options.print_only:
            raise ValueError("Explicit normal v2 startup arguments required")
        overlay = Overlay(service, adapter, api, plan, plan_sha, argv)
        service_source = SERVICE_PATH.read_bytes(); original_entrypoint = service.service_entrypoint
        service.service_entrypoint = lambda source: adapter.render(source, service_source, activate=True)
        service.build_manifest, service.command, service.r.docker = overlay.build_manifest, overlay.command, overlay.docker
        os.environ["ALLOY_MANAGED"] = "1"
        if Path(service.__file__).resolve() != SERVICE_PATH: raise ValueError("Original guard-spawn source must remain unchanged")
        return service.main(argv)
    finally:
        if overlay is not None:
            service.build_manifest, service.command, service.r.docker = overlay.original_manifest, overlay.original_command, overlay.original_docker
            if original_entrypoint is not None: service.service_entrypoint = original_entrypoint
        sys.path[:] = original_path
        if original_managed is None: os.environ.pop("ALLOY_MANAGED", None)
        else: os.environ["ALLOY_MANAGED"] = original_managed


def main():
    class QuietParser(argparse.ArgumentParser):
        def error(self, message): raise ValueError("Invalid isolated service overlay options")
    parser = QuietParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True); parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--activate", action="store_true", default=False)
    supplied = sys.argv[1:]; split = supplied.index("--") if "--" in supplied else len(supplied)
    args = parser.parse_args(supplied[:split])
    return run(args.plan, args.plan_sha256, supplied[split + 1:], activate=args.activate)


if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as error:
        print(json.dumps(dict(passed=False, error_type=type(error).__name__, details_redacted=True)), file=sys.stderr)
        raise SystemExit(1)
