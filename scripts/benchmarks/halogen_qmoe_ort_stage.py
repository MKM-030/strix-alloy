"""Copy and seal an existing ORT package using only standard-library file reads.

No imports from either runtime environment, installs, provider calls or models.
Existing environments are read-only donors; the destination must be fresh.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import sys

ROOT = Path(r"C:\Projects\strix-alloy-clean")
WORK = ROOT / "server/.local/optimization9h-20261004"
DONOR = Path(r"C:\AI\runtimes\qwen3-tts\.venv\Lib\site-packages")
TREES = ("onnxruntime", "onnxruntime-1.29.0.dist-info")
KEY_PINS = {
    "onnxruntime/__init__.py": "c8dc5c6007d8a3a4691fc7dcc650c11bda155a033bcc029cd0dd46f630565c32",
    "onnxruntime/capi/onnxruntime.dll": "f9013e824c1dbc5b1874ffdabeedfd1cad4e2dabd9d93528f6ec6d21c2980d00",
    "onnxruntime/capi/onnxruntime_pybind11_state.pyd": "d9114a3f211f302fb6efb537a1972c2a5e01b408a7311abf14127d100dc76849",
    "onnxruntime/capi/onnxruntime_inference_collection.py": "2bc0c884f3e139e1b7800c7f0601f1bf34dfc84880fb4bb4407fefc156ecb4b6",
    "onnxruntime/capi/_pybind_state.py": "9db5299d49dcc01bf9a60240f32ba00d82510384d37c2d206983840f98c3f920",
    "onnxruntime-1.29.0.dist-info/METADATA": "eb1f9c5003bd1146122da378763d3f0a853e48d5156f2d54685481820794ac80",
    "onnxruntime-1.29.0.dist-info/WHEEL": "f767fbbf21c4fc6662c119c3d88d39bc24ff4b7f54be4472ba0b980c028e19bf",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def plain_path(path):
    path = Path(path).absolute()
    for entry in (path, *path.parents):
        info = entry.lstat()
        require(not entry.is_symlink() and not getattr(info, "st_file_attributes", 0) & 0x400,
                "Reparse path is not admitted: " + str(entry))
    return path.resolve(strict=True)


def tree_files():
    files = []
    for name in TREES:
        tree = plain_path(DONOR / name)
        require(tree.is_dir(), "Missing complete donor tree")
        for entry in tree.rglob("*"):
            plain_path(entry)
            if entry.is_file():
                files.append(entry)
    return sorted(files, key=lambda path: path.relative_to(DONOR).as_posix())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    args = parser.parse_args()
    work = plain_path(WORK)
    stage = args.stage.absolute()
    require(stage.parent == work and stage.name.startswith("qmoe-ort129-stage-")
            and not stage.exists(), "Fresh direct task-local ORT stage required")
    require(sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 12),
            "Use CPython 3.12 for static staging")
    before = tree_files()
    donor_inventory = {
        path.relative_to(DONOR).as_posix(): (path.stat().st_size, digest(path)) for path in before
    }
    require(all(donor_inventory[name][1] == pin for name, pin in KEY_PINS.items()),
            "Reviewed donor key pin changed")
    require("Tag: cp312-cp312-win_amd64" in (DONOR / TREES[1] / "WHEEL").read_text(),
            "Donor wheel ABI changed")
    stage.mkdir()
    site = stage / "site-packages"
    site.mkdir()
    files = []
    for path in before:
        relative = path.relative_to(DONOR).as_posix()
        size, expected = donor_inventory[relative]
        target = site / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        require(target.stat().st_size == size and digest(target) == expected,
                "Copied donor bytes differ: " + relative)
        target.chmod(stat.S_IREAD)
        files.append(dict(relative_path=relative, donor_path=str(path), staged_path=str(target),
                          bytes=size, donor_sha256=expected, staged_sha256=expected))
    after = tree_files()
    require([path.relative_to(DONOR).as_posix() for path in after] == list(donor_inventory),
            "Donor file set changed while staging")
    require(all((path.stat().st_size, digest(path)) == donor_inventory[path.relative_to(DONOR).as_posix()]
                for path in after), "Donor bytes changed while staging")
    manifest = dict(schema="halogen_qmoe_ort_stage_v1", completed=True,
                    scope="static complete-package copy; API27 candidate only; no native import or hardware",
                    donor_site_packages=str(DONOR), stage_root=str(stage), site_packages=str(site),
                    trees=list(TREES), package_name="onnxruntime", package_version="1.29.0",
                    wheel_tag="cp312-cp312-win_amd64", c_api_max_version=29,
                    donor_preserved=True, old_winml_environment_modified=False,
                    includes_donor_bytecode=True, staged_files_read_only=True,
                    file_count=len(files), total_bytes=sum(row["bytes"] for row in files),
                    key_pins=KEY_PINS, files=files, stager_source_sha256=digest(Path(__file__)))
    manifest_path = stage / "stage-manifest.json"
    with manifest_path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(manifest, output, indent=2, allow_nan=False)
        output.write("\n")
    manifest_path.chmod(stat.S_IREAD)
    print(json.dumps(dict(manifest=str(manifest_path), manifest_sha256=digest(manifest_path),
                          file_count=len(files), total_bytes=manifest["total_bytes"],
                          native_imports=False, donor_preserved=True), indent=2))


if __name__ == "__main__":
    main()
