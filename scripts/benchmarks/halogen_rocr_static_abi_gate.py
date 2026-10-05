"""Read-only ELF gate via installed Windows LLVM readers; never loads an ELF."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

LLVM = Path("C:/AI/runtimes/ironenv/Lib/site-packages/llvm-aie/bin")
ORIGINAL_SHA = "1961df7d395b62d9b7c0086e0a247a02d0e97129eb9d8b28acb0e0a597e819f5"
IMAGE = "ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a"
REQUIRED_SYSDEPS = {"librocm_sysdeps_elf.so.1", "librocm_sysdeps_drm.so.2",
                    "librocm_sysdeps_drm_amdgpu.so.1", "librocm_sysdeps_numa.so.1"}
LOOP_NAME = "rocr::core::Runtime::AsyncEventsLoop(void*)"


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        if isinstance(value, str):
            stream.write(value)
        else:
            json.dump(value, stream, indent=2)
            stream.write("\n")


def reader(tool, arguments):
    executable = LLVM / (tool + ".exe")
    require(executable.is_file(), "installed LLVM reader absent")
    result = subprocess.run([str(executable), *map(str, arguments)], check=True,
        capture_output=True, text=True, encoding="utf-8", errors="strict",
        timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return result.stdout


def inspect(path, label, out, loop=True):
    path = Path(path).resolve(strict=True)
    before = path.stat()
    dynamic = reader("llvm-readelf", ["-d", path])
    versions = reader("llvm-readelf", ["--version-info", path])
    symbols = reader("llvm-readelf", ["--dyn-syms", "--wide", path])
    for suffix, value in (("dynamic", dynamic), ("versions", versions), ("dynsyms", symbols)):
        save(out / (label + "-" + suffix + ".txt"), value)
    needed = re.findall(r"\(NEEDED\).*?\[([^]]+)\]", dynamic)
    soname = re.findall(r"\(SONAME\).*?\[([^]]+)\]", dynamic)
    exports, imports = [], []
    for line in symbols.splitlines():
        fields = re.match(r"\s*\d+:\s+[0-9a-f]+\s+\d+\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", line)
        if fields is None:
            continue
        kind, binding, visibility, index, name = fields.groups()
        if index == "UND":
            imports.append(dict(name=name, binding=binding, type=kind))
        elif binding in ("GLOBAL", "WEAK") and visibility in ("DEFAULT", "PROTECTED"):
            exports.append(dict(name=name, binding=binding, visibility=visibility, type=kind))
    definitions, needs, section, dependency = set(), {}, None, None
    for line in versions.splitlines():
        if line.startswith("Version definition section"):
            section = "definitions"
        elif line.startswith("Version needs section"):
            section = "needs"
        file_match = re.search(r"File: (\S+)", line)
        if section == "needs" and file_match:
            dependency = file_match.group(1)
            needs[dependency] = []
        name = re.search(r"Name: (\S+)", line)
        if name and section == "definitions":
            definitions.add(name.group(1))
        elif name and section == "needs" and dependency:
            needs[dependency].append(name.group(1))
    record = dict(path=str(path), sha256=sha(path), bytes=before.st_size, soname=soname,
        needed=needed, exports=exports, imports=imports, version_definitions=sorted(definitions), version_needs=needs)
    if loop:
        nm = reader("llvm-nm", ["-C", "-S", "--defined-only", path])
        save(out / (label + "-nm.txt"), nm)
        found = []
        for line in nm.splitlines():
            item = re.match(r"([0-9a-f]+)\s+([0-9a-f]+)\s+\S\s+(.+)$", line)
            if item and item.group(3) == LOOP_NAME:
                found.append((int(item.group(1), 16), int(item.group(2), 16)))
        require(len(found) == 1, "exact AsyncEventsLoop symbol boundary unavailable: " + label)
        address, length = found[0]
        disassembly = reader("llvm-objdump", ["--disassemble", "--demangle", "--x86-asm-syntax=intel",
            "--start-address=" + hex(address), "--stop-address=" + hex(address + length), path])
        save(out / (label + "-async-loop.txt"), disassembly)
        calls = [line.strip() for line in disassembly.splitlines() if re.search(r"\bcall\b", line)]
        sleeps = [line for line in calls if "uSleep" in line or "usleep" in line]
        record["async_loop"] = dict(address=hex(address), bytes=length, sleep_calls=sleeps,
                                    sleep_call_present=bool(sleeps))
        record["undefined_direct_hsakmt"] = [row["name"] for row in imports if row["name"].startswith("hsaKmt")]
        record["static_thunk_loader_present"] = "ThunkLoader::LoadThunkApiTable()" in nm
        record["static_hsakmt_present"] = bool(re.search(r"\bt\s+hsaKmt", nm))
    after = path.stat()
    require((before.st_size, before.st_mtime_ns, before.st_ino) ==
            (after.st_size, after.st_mtime_ns, after.st_ino), "ELF changed during static read")
    save(out / (label + ".json"), record)
    return record


def export_set(record):
    return {tuple(row[key] for key in ("name", "binding", "visibility", "type")) for row in record["exports"]}


def default_export_names(record):
    # An unversioned relocation can use an unversioned or default-version
    # definition. A non-default NAME@VERSION alone is not a supplier.
    return {row["name"].split("@@", 1)[0] for row in record["exports"]
            if "@" not in row["name"] or "@@" in row["name"]}


def unversioned_import_closure(candidate, dependencies):
    suppliers = {"self": default_export_names(candidate)}
    suppliers.update({name: default_export_names(dependencies[name])
                      for name in candidate["needed"] if name in dependencies})
    required, optional = [], []
    for row in candidate["imports"]:
        if "@" in row["name"]:
            continue
        if row["binding"] == "WEAK":
            optional.append(row["name"])
            continue
        supplied_by = sorted(name for name, names in suppliers.items() if row["name"] in names)
        required.append(dict(name=row["name"], binding=row["binding"], type=row["type"],
                             supplied_by=supplied_by))
    unresolved = sorted(row["name"] for row in required if not row["supplied_by"])
    return dict(required=required, optional_weak=sorted(optional), unresolved=unresolved,
                unresolved_internal_rocr=[name for name in unresolved if name.startswith("_ZN4rocr")])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True)
    parser.add_argument("--stock")
    parser.add_argument("--patched")
    parser.add_argument("--dependencies", help="root-exported unchanged-image dependency manifest")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    require(bool(args.stock) == bool(args.patched), "stock and patched must be supplied together")
    out = Path(args.out).absolute()
    out.mkdir(exist_ok=False)
    result = dict(schema="halogen.rocr-private-static-abi-gate.v1", passed=False,
                  static_only=True, elf_execution_performed=False, runtime_qualified=False,
                  checks={}, errors=[], unresolved_dependency_availability=[])
    try:
        original = inspect(args.original, "original", out)
        require(original["sha256"] == ORIGINAL_SHA, "original HSA identity differs")
        result["original"] = original
        if not args.stock:
            result["phase"] = "original-baseline-prepared-no-candidate-read"
            result["passed"] = True
        else:
            stock, patched = inspect(args.stock, "source-stock", out), inspect(args.patched, "patched", out)
            result.update(source_stock=stock, patched=patched, phase="private-build-static-comparison")
            required_exports = export_set(original)
            for label, candidate in (("source_stock", stock), ("patched", patched)):
                missing = sorted(required_exports - export_set(candidate))
                additions = sorted(export_set(candidate) - required_exports)
                checks = dict(missing_original_exports=missing, added_exports=additions,
                    soname_one=candidate["soname"] == ["libhsa-runtime64.so.1"],
                    rocr_version_preserved="ROCR_1" in candidate["version_definitions"],
                    renamed_sysdeps_present=REQUIRED_SYSDEPS <= set(candidate["needed"]),
                    added_needed=sorted(set(candidate["needed"]) - set(original["needed"])),
                    forbidden_generic_needed=[name for name in candidate["needed"] if re.match(r"lib(?:elf|drm|drm_amdgpu|numa)\.so", name)],
                    direct_hsakmt_imports=candidate["undefined_direct_hsakmt"],
                    static_thunk_graph=candidate["static_thunk_loader_present"] and candidate["static_hsakmt_present"],
                    added_version_needs={name: sorted(set(values) - set(original["version_needs"].get(name, [])))
                                         for name, values in candidate["version_needs"].items()})
                result["checks"][label] = checks
                if (missing or not checks["soname_one"] or not checks["rocr_version_preserved"] or
                    not checks["renamed_sysdeps_present"] or checks["added_needed"] or
                    checks["forbidden_generic_needed"] or checks["direct_hsakmt_imports"] or not checks["static_thunk_graph"]):
                    result["errors"].append(label + " export/SONAME/dependency/static-thunk gate failed")
            same_interface = (export_set(stock) == export_set(patched) and stock["needed"] == patched["needed"] and
                              stock["version_needs"] == patched["version_needs"])
            loop_gate = (not original["async_loop"]["sleep_call_present"] and
                         not stock["async_loop"]["sleep_call_present"] and patched["async_loop"]["sleep_call_present"])
            result["checks"].update(stock_patched_interface_equal=same_interface,
                async_loop_sleep_only_in_patched=loop_gate)
            if not same_interface or not loop_gate:
                result["errors"].append("matched-build interface or targeted async-loop sleep gate failed")
            dependencies = {}
            if args.dependencies:
                manifest = json.loads(Path(args.dependencies).read_text(encoding="utf-8-sig"))
                require(manifest.get("image", manifest.get("source_image")) == IMAGE, "dependency manifest image identity differs")
                bindings = manifest.get("bindings")
                if bindings is None:
                    bindings = [dict(soname=Path(row["source_path"]).name,
                        snapshot_path=str(Path(row["export_path"]).absolute()),
                        image_path=row["source_path"], sha256=row["sha256"]) for row in manifest["files"]]
                for index, row in enumerate(bindings):
                    require(row["image_path"].startswith("/"), "unchanged-image path provenance required")
                    dependency = inspect(row["snapshot_path"], "dependency-" + str(index), out, loop=False)
                    require(dependency["sha256"] == row["sha256"], "dependency export hash differs")
                    require(row["soname"] not in dependencies, "duplicate dependency SONAME")
                    dependencies[row["soname"]] = dependency
            for label, candidate in (("source_stock", stock), ("patched", patched)):
                availability = {}
                for name, versions in candidate["version_needs"].items():
                    snapshot = dependencies.get(name)
                    if snapshot is None:
                        result["unresolved_dependency_availability"].append(dict(variant=label, soname=name, versions=versions))
                        continue
                    missing = sorted(set(versions) - set(snapshot["version_definitions"]))
                    availability[name] = dict(required_versions=versions, missing_versions=missing,
                                               snapshot_sha256=snapshot["sha256"])
                    if missing:
                        result["errors"].append(label + " needs unavailable " + name + " versions: " + repr(missing))
                for name in candidate["needed"]:
                    if name not in dependencies and name not in candidate["version_needs"]:
                        result["unresolved_dependency_availability"].append(dict(variant=label, soname=name, versions=[]))
                result["checks"][label]["provided_dependency_availability"] = availability
                closure = unversioned_import_closure(candidate, dependencies)
                result["checks"][label]["strong_unversioned_import_closure"] = closure
                if closure["unresolved"]:
                    result["errors"].append(label + " has unresolved strong unversioned imports: " + repr(closure["unresolved"]))
            result["dependency_manifest"] = str(Path(args.dependencies).absolute()) if args.dependencies else None
            result["passed"] = not result["errors"] and not result["unresolved_dependency_availability"]
    except Exception as error:
        result["errors"].append(type(error).__name__ + ": " + str(error))
    save(out / "gate.json", result)
    print(json.dumps(dict(passed=result["passed"], phase=result.get("phase"), errors=result["errors"],
        unresolved_dependency_count=len(result["unresolved_dependency_availability"]), out=str(out))))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
