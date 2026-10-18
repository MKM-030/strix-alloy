"""Export the isolated source patch and byte manifest without invoking Git."""
from __future__ import annotations

import difflib
import hashlib
import json
import os
from pathlib import Path

BASE = Path(r"E:\strix-alloy\hipfire-mq2-ddee82\src")
CANDIDATE = Path(r"E:\strix-alloy\hipfire-native-windows-20261018\src")
OUTPUT = Path(__file__).resolve().parent
EXCLUDED = {".git", "target", "dist", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".cache"}
ALLOWED = {
    "crates/hip-bridge/src/ffi.rs",
    "crates/hipfire-config/Cargo.toml",
    "crates/hipfire-config/src/host_memory.rs",
    "crates/rdna-compute/src/dispatch.rs",
    "crates/rdna-compute/src/uma_memory.rs",
    "crates/rdna-compute/src/emu.rs",
    "crates/rdna-compute/src/loaded_code_check.rs",
    "crates/hipfire-runtime/src/ple_hot_store.rs",
    "crates/hipfire-runtime/src/ple_table_portable_tests.rs",
    "crates/hipfire-loader/src/carriers.rs",
    "docs/GETTING_STARTED.md",
}


def inventory(root: Path) -> dict[str, tuple[int, str]]:
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not Path(directory, d).is_symlink())
        for name in sorted(files):
            path = Path(directory, name)
            if path.is_symlink() or name.endswith(".pyc"):
                continue
            data = path.read_bytes()
            result[path.relative_to(root).as_posix()] = (len(data), hashlib.sha256(data).hexdigest())
    return result


def fingerprint(items: dict[str, tuple[int, str]]) -> str:
    body = "".join(f"{path}\0{size}\0{sha}\n" for path, (size, sha) in sorted(items.items()))
    return hashlib.sha256(body.encode()).hexdigest()


def main() -> None:
    before, after = inventory(BASE), inventory(CANDIDATE)
    changed = sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
    unexpected = set(changed) - ALLOWED
    if unexpected:
        raise RuntimeError(f"Unexpected source mutations: {sorted(unexpected)}")
    patch = []
    for path in changed:
        old = (BASE / path).read_text(encoding="utf-8").splitlines(keepends=True) if path in before else []
        new = (CANDIDATE / path).read_text(encoding="utf-8").splitlines(keepends=True) if path in after else []
        patch.append(f"diff --git a/{path} b/{path}\n")
        patch.extend(difflib.unified_diff(old, new, fromfile=f"a/{path}" if old else "/dev/null", tofile=f"b/{path}" if new else "/dev/null"))
    patch_bytes = "".join(patch).encode("utf-8")
    (OUTPUT / "native-windows-ddee82.patch").write_bytes(patch_bytes)
    manifest = {
        "schema": "hipfire.native-windows-source.v1",
        "upstream": "https://github.com/warpfront/hipfire",
        "baseline_commit": "ddee82c7464946c86f946d89af1b5634f212d466",
        "baseline_description": "upstream ddee82 plus retained native MTP drafted-counter instrumentation; not pristine upstream",
        "baseline_instrumentation": {"path": "native-mtp-drafted-counter.patch", "sha256": "a5e36c349ccdbc8d1d5eefe219d74f80a1361d7e4a04c0762f807de4d73faa30", "already_in_retained_snapshot": True},
        "baseline_canonical_tree_receipt": "957af478ab970adea8deb17514d729211600e05e",
        "baseline_source": str(BASE), "candidate_source": str(CANDIDATE),
        "consolidated_strix_main": "1fb4b1541b474b238e47001b2cbd6372eb0eb197",
        "copy": {"files": 7551, "robocopy_exit": 1, "excluded_directories": sorted(EXCLUDED), "excluded_files": ["*.pyc"], "git_metadata_copied": False},
        "baseline_files": len(before), "candidate_files": len(after),
        "lockfile": {"path": "Cargo.lock", "before": before["Cargo.lock"], "after": after["Cargo.lock"], "changed": before["Cargo.lock"] != after["Cargo.lock"], "dependency_change": "Existing windows 0.62.2 enables Win32_System_Performance only; no crate/version change."},
        "baseline_source_fingerprint": fingerprint(before), "candidate_source_fingerprint": fingerprint(after),
        "fingerprint_contract": "SHA256 of sorted UTF-8 records: relative POSIX path + NUL + decimal byte length + NUL + SHA256 hex + newline",
        "changed_files": [{"path": path, "before": before.get(path), "after": after.get(path)} for path in changed],
        "patch": {"path": "native-windows-ddee82.patch", "bytes": len(patch_bytes), "sha256": hashlib.sha256(patch_bytes).hexdigest()},
        "verification": {"source_bytes_inventoried": True, "tests_executed_by_implementer": False, "builds_executed_by_implementer": False, "dll_loaded_by_implementer": False, "hardware_queried_by_implementer": False, "git_mutated_by_implementer": False, "runtime_qualification_owner": "root"},
        "licenses": ["licenses/LICENSE", "licenses/LICENSE-APACHE", "licenses/LICENSE-MIT", "licenses/NOTICE"],
        "source_files": [{"path": path, "before": before.get(path), "after": after.get(path)} for path in sorted(before.keys() | after.keys())],
    }
    (OUTPUT / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    license_dir = OUTPUT / "licenses"
    license_dir.mkdir(exist_ok=True)
    for name in ["LICENSE", "LICENSE-APACHE", "LICENSE-MIT", "NOTICE"]:
        (license_dir / name).write_bytes((BASE / name).read_bytes())
    print(json.dumps({"changed_files": changed, "patch": manifest["patch"], "baseline_files": len(before), "candidate_files": len(after), "candidate_source_fingerprint": manifest["candidate_source_fingerprint"]}))


if __name__ == "__main__":
    main()
