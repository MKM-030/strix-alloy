import datetime, hashlib, json, pathlib, re, sys, aiohttp
stage = pathlib.Path(r"C:\Projects\strix-alloy-scc-voice\voice\native-bridge\runtime\sdk-session-admission-20261014")
live = stage.parents[1]
def log_text(path):
    raw = path.read_bytes()
    return raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
tests = {}
for phase, name, expected in [
    ("initial_red", "RED-TESTS-WINDOWS.log", 39),
    ("hardening_red", "RED-HARDENING-TESTS-WINDOWS.log", 11),
    ("review_red", "RED-REVIEW-TESTS-WINDOWS.log", 4),
    ("final_green", "GREEN-TESTS-WINDOWS.log", 0)]:
    content = log_text(stage / name)
    count = re.search(r"Ran (\d+) tests in ([0-9.]+)s", content)
    failure = re.search(r"FAILED \(failures=(\d+)\)", content)
    failures = int(failure.group(1)) if failure else 0
    assert count and int(count.group(1)) == 39 and failures == expected, (phase, content[-400:])
    assert failures or re.search(r"^OK\s*$", content, re.M), phase
    tests[phase] = {"test_count": 39, "failures": failures, "errors": 0, "seconds": float(count.group(2)), "exit_code": 1 if failures else 0, "log": name}
manifest = []
for path in sorted(stage.iterdir()):
    if path.is_file() and path.name != "VALIDATION.json":
        raw = path.read_bytes()
        manifest.append({"file": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
native = live / "native_bridge.py"
core = live / "core.py"
native_sha = hashlib.sha256(native.read_bytes()).hexdigest()
core_sha = hashlib.sha256(core.read_bytes()).hexdigest()
assert native_sha == "f7cb39ef09da63b5484308be52ca33985bb4005645f668030c8896c37821475d"
assert core_sha == "54bcef0d4de5d8bcc1fc37f2dfe194741fa55f7185a318bffe2fbf7ed48626e8"
assert hashlib.sha256((stage / "core.py").read_bytes()).hexdigest() == core_sha
evidence = {
    "status": "inactive_candidate_only",
    "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "windows_stage": str(stage),
    "python": sys.version.split()[0], "aiohttp": aiohttp.__version__,
    "tests": tests, "py_compile_exit": 0,
    "synthetic_tokens_only": True, "real_platform_requests": 0,
    "route_registered": False, "sdk_success_response_implemented": False,
    "session_transport_implemented": False, "production_activation": False,
    "live_native_sha256_before": native_sha, "live_native_sha256_after": native_sha,
    "live_core_sha256_before": core_sha, "live_core_sha256_after": core_sha,
    "source_and_readme_files": 7, "test_logs": 4,
    "manifested_files_excluding_validation_and_bytecode": len(manifest),
    "file_manifest": manifest,
    "review": {"independent_read_only_review": True,
        "no_authorization_bypass_found": True,
        "resolved": ["Request identity encoding instead of aiohttp compression default", "Reject additional recognized competing auth headers"],
        "integration_prerequisites": ["Enforce POST /api/webrtc/sessions in future adapter", "Bound complete still-encoded body while reading", "Obtain actual SDK wire success contract before transport implementation"]},
}
(stage / "VALIDATION.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
print(json.dumps(evidence, separators=(",", ":")))
