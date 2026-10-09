"""Read-only stdlib hash/JSON/Python syntax verification of this source archive."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "source-provenance.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    manifest = json.loads(MANIFEST.read_bytes())
    assert manifest["schema"] == "halogen0173.dflash.native-bridge-source-publication.v1"
    assert manifest["publication_state"] == "ready_for_root_review", "Transport freeze/review is still pending"
    assert manifest["source_only"] and manifest["default_off"]
    assert not manifest["native_installed"] and not manifest["serving_gain_claimed"]
    expected = {entry["path"] for entry in manifest["files"]}
    assert len(expected) == len(manifest["files"]), "Duplicate manifest path"
    actual = {path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*") if path.is_file()}
    assert actual == expected | {MANIFEST.name}, "Missing or unexpected package files"
    python_count = json_count = copied_count = 0
    imports: dict[str, list[str]] = {}
    for entry in manifest["files"]:
        path = (ROOT / entry["path"]).resolve()
        assert path.is_relative_to(ROOT) and not path.is_symlink(), "Package path escaped"
        data = path.read_bytes()
        assert len(data) == entry["bytes"] and sha256(data) == entry["sha256"], entry["path"]
        if entry["path"] != "transport/cpu-wire-fixture.bin":
            assert b"\0" not in data, "Unexpected binary data"
        else:
            assert entry["artifact_kind"] == "synthetic_cpu_wire_fixture"
        if entry["origin_kind"] == "copied_exact":
            copied_count += 1
            assert entry["original_path"] and entry["original_repo_path"]
            assert entry["original_sha256"] == entry["sha256"]
        else:
            assert entry["origin_kind"] == "package_created" and entry["original_path"] is None
        if path.suffix == ".json":
            json.loads(data)
            json_count += 1
        if path.suffix == ".py":
            tree = ast.parse(data, filename=entry["path"])
            # Compile verifies Python/import grammar; no module is imported or executed.
            compile(tree, entry["path"], "exec")
            imports[entry["path"]] = sorted({
                node.module if isinstance(node, ast.ImportFrom) else alias.name
                for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names
            })
            python_count += 1
    owner_seal = json.loads((ROOT / "owner/delivery-seal.json").read_bytes())
    owner_receipt = json.loads((ROOT / "owner/cpu-source-receipt.json").read_bytes())
    controller_seal = json.loads((ROOT / "controller/delivery_seal.json").read_bytes())
    controller_receipt = json.loads((ROOT / "controller/qualification_receipt.json").read_bytes())
    transport_seal = json.loads((ROOT / "transport/delivery_seal.json").read_bytes())
    transport_receipt = json.loads((ROOT / "transport/qualification_receipt.json").read_bytes())
    pins = manifest["frozen_pins"]
    for relative, pin in pins["package_file_sha256"].items():
        assert sha256((ROOT / relative).read_bytes()) == pin, relative
    for name, pin in owner_seal["files"].items():
        path = ROOT / "owner" / name
        if path.is_file():
            assert sha256(path.read_bytes()) == pin, name
    for name, artifact in controller_receipt["artifacts"].items():
        path = ROOT / "controller" / name
        if path.is_file():
            assert sha256(path.read_bytes()) == artifact["sha256"], name
    for name, pin in transport_seal["files"].items():
        path = ROOT / "transport" / name
        if path.is_file():
            assert sha256(path.read_bytes()) == pin, name
    for name, pin in transport_seal["owner_dependencies"].items():
        assert sha256((ROOT / "owner" / name).read_bytes()) == pin, name
    assert transport_seal["qualification_receipt_sha256"] == sha256((ROOT / "transport/qualification_receipt.json").read_bytes())
    assert transport_receipt["owner_dependencies"] == transport_seal["owner_dependencies"]
    assert all(command["exit"] == 0 for command in transport_receipt["commands"])
    assert not transport_seal["native_installed"] and not transport_seal["hardware_initialized"]
    header_pin = pins["package_file_sha256"]["controller/retained_controller.h"]
    assert owner_receipt["retained_controller_header_sha256"] == header_pin
    assert controller_seal["retained_header_sha256"] == header_pin
    assert controller_seal["shared_library_sha256"] == pins["excluded_controller_library_sha256"]
    assert controller_receipt["artifacts"]["retained_controller_source.so"]["sha256"] == pins["excluded_controller_library_sha256"]
    assert controller_seal["qualification_receipt_sha256"] == sha256((ROOT / "controller/qualification_receipt.json").read_bytes())
    assert owner_receipt["harness"]["exit_code"] == 0 and not owner_receipt["installed_native_relays"]
    assert not owner_receipt["live_capture_exporter_complete"] and not controller_receipt["native_installed"]
    print(json.dumps({
        "copied_files": copied_count,
        "package_created_files": len(manifest["files"]) - copied_count,
        "hashed_files": len(manifest["files"]),
        "python_syntax_files": python_count,
        "json_syntax_files": json_count + 1,
        "python_import_syntax": imports,
        "source_provenance_sha256": sha256(MANIFEST.read_bytes()),
        "hash_mismatches": 0,
        "source_only": True,
        "executed_qualification_helpers": False,
        "compiled_or_loaded_native_code": False,
        "hardware_initialized": False,
        "serving_gain_claimed": False,
    }, indent=2))


if __name__ == "__main__":
    main()
