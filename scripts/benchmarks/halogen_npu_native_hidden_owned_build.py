"""Root-owned, bounded offline build of the reviewed native hidden package.

Default preparation only. Build includes device-free host --inspect; no NPU is opened with
--build. Compiler children are retained in a Windows job and closed in finally.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from host_frames import frame
from owned_child import JobChild


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reserve(floor: int) -> dict:
    value = frame()
    if min(value["available_bytes"], value["commit_headroom_bytes"]) < floor * 1024**3:
        raise RuntimeError(f"Physical/commit reserve below {floor} GiB")
    return value


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--manifest-sha256", required=True)
    p.add_argument("--build", action="store_true")
    a = p.parse_args()
    manifest = a.manifest.resolve(strict=True)
    if digest(manifest) != a.manifest_sha256:
        raise ValueError("Build manifest differs from independently reviewed hash")
    plan = json.loads(manifest.read_bytes())
    if plan["schema"] != "halogen.native-hidden-offline-build.v1":
        raise ValueError("Wrong build manifest schema")
    source = Path(plan["source_directory"]).resolve(strict=True)
    pins = {Path(k).resolve(strict=True): v for k, v in plan["source_pins"].items()}
    if source / "build.ps1" not in pins or Path(__file__).resolve() not in pins:
        raise ValueError("Build script and supervisor must have independent source pins")

    def verify():
        for path, wanted in pins.items():
            if digest(path) != wanted:
                raise ValueError("Reviewed build source changed: " + str(path))

    verify()
    minimum = reserve(22)
    print("Prepared reviewed offline native hidden build; device execution disabled", flush=True)
    if not a.build:
        return 0
    vc = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat")
    if not vc.is_file():
        raise FileNotFoundError(vc)
    work = ROOT / "server/.local/optimization9h-20261004" / ("native-hidden-build-" + uuid.uuid4().hex)
    work.mkdir()
    artifacts = work / "artifacts"
    batch = work / "offline-build.cmd"
    # Fixed executable/source paths only; no shell interpolation of user bodies.
    paths = (str(vc), str(source / "build.ps1"), str(artifacts))
    if any('"' in s or "\n" in s or "\r" in s or "%" in s for s in paths):
        raise ValueError("Unexpected batch metacharacter in canonical build path")
    batch.write_text(
        '@echo off\ncall "' + str(vc) + '" -no_logo -arch=x64 -host_arch=x64\n'
        'if errorlevel 1 exit /b %errorlevel%\n'
        '"C:\\Program Files\\PowerShell\\7\\pwsh.exe" -NoProfile -ExecutionPolicy Bypass -File "'
        + str(source / "build.ps1") + '" -OutDir "' + str(artifacts) + '"\n'
        'exit /b %errorlevel%\n', encoding="ascii",
    )
    command = [r"C:\Windows\System32\cmd.exe", "/d", "/c", str(batch)]
    child = None
    errors = []
    identity = None
    started = time.monotonic()
    result = dict(offline_build_only=True, NPU_executed=False, server_changed=False,
                  command=command, source_pins={str(k): v for k, v in pins.items()})
    try:
        child = JobChild(command, cwd=ROOT, env=os.environ.copy(),
                         stdout_path=work / "stdout.log", stderr_path=work / "stderr.log")
        identity = child.owner.verify_live_identity()
        print(json.dumps(dict(work=str(work), identity=identity, offline_only=True)), flush=True)
        while child.poll() is None:
            observed = reserve(18)
            for key in minimum:
                minimum[key] = min(minimum[key], observed[key])
            if time.monotonic() - started >= 660:
                raise TimeoutError("Bounded offline compiler deadline")
            child.owner.wait(100)
        result["exit_code"] = child.poll()
        if child.poll() != 0:
            raise RuntimeError("Compiler failed; see retained stdout/stderr logs")
        verify()
        receipt = json.loads((artifacts / "build-receipt.json").read_text(encoding="utf-8-sig"))
        if not receipt["build_succeeded"] or receipt["runtime_executed"]:
            raise ValueError("Build receipt does not prove offline completion")
        result["build_receipt_sha256"] = digest(artifacts / "build-receipt.json")
    except BaseException as e:
        errors.append(type(e).__name__ + ": " + str(e))
    finally:
        if child is not None:
            try:
                child.close()
                result["owned_job_closed"] = True
            except BaseException as e:
                errors.append("Owned cleanup: " + type(e).__name__ + ": " + str(e))
                result["owned_job_closed"] = False
        result.update(passed=not errors, errors=errors, identity=identity,
                      elapsed_seconds=time.monotonic() - started, minimum_memory=minimum)
        (work / "owned-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(work=str(work), passed=not errors, errors=errors)), flush=True)
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
