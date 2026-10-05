#!/usr/bin/env python3
"""Build only private stock/backport ROCr libraries inside ROOT's CPU container.

This helper neither creates a container nor installs packages, loads HSA, mounts
devices, launches a model, installs ROCr, or alters the supplied SDK/source tree.
ROOT must provide the pinned image, resource guard, verified paths, and a fresh
output directory. Do not run this helper in the host or colleague container.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys


BASE_COMMIT = "2b22ab0195cc1461cd9abf3b969e9dd7c10af350"
BASE_CMAKE_SHA = "2f682b448c14a4616a274ff6098c3b9776ad204aa7aa44d51e67a1e2cbfef924"
BASE_RUNTIME_SHA = "9e4450bec2c7cea5c6c93a72b5fedff8d15d1122d2a7fe52dc3cd017008c537a"
PATCH_SHA = "ead910aaf82bb7ace5bf59ad288f4ae5d620feefa32d594221832878de93f745"
HEADER_SHA = "2dcf4c597ca89721583185f75f0d4746e6a124edcb54d721df5d3e5ab90725b8"
RUNTIME_REL = "runtime/hsa-runtime/core/runtime/runtime.cpp"
HEADER_REL = "runtime/hsa-runtime/core/util/poll_backoff.h"
IMAGE_TARGET_DEVICES = (
    "gfx700;gfx701;gfx702;gfx801;gfx802;gfx803;gfx805;gfx810;"
    "gfx900;gfx902;gfx904;gfx906;gfx908;gfx909;gfx90a;gfx90c;gfx942;gfx950;"
    "gfx1010;gfx1011;gfx1012;gfx1013;gfx1030;gfx1031;gfx1032;gfx1033;gfx1034;gfx1035;gfx1036;"
    "gfx1100;gfx1101;gfx1102;gfx1103;gfx1150;gfx1151;gfx1152;gfx1153;gfx1200;gfx1201"
)
GENERATORS = (
    "runtime/hsa-runtime/image/blit_src/create_hsaco_ascii_file.sh",
    "runtime/hsa-runtime/core/runtime/trap_handler/create_trap_handler_header.sh",
    "runtime/hsa-runtime/core/runtime/blit_shaders/create_blit_shader_header.sh",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def checked_file(value, parent=None):
    path = Path(value).absolute()
    resolved = path.resolve(strict=True)
    require(path.is_file(), f"not a file: {path}")
    require(re.fullmatch(r"/[A-Za-z0-9_./+\-]+", str(path)), f"simple absolute POSIX path required: {path}")
    if parent is not None:
        require(resolved.is_relative_to(parent), f"SDK path escapes SDK root: {path}")
    # Preserve the clang++ symlink name: argv[0] selects the C++ linker driver.
    return path


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, help="verified top-level projects/rocr-runtime")
    parser.add_argument("--patch", required=True)
    parser.add_argument("--sdk-root", required=True)
    parser.add_argument("--clang", required=True)
    parser.add_argument("--clangxx", required=True)
    parser.add_argument("--objcopy", required=True)
    parser.add_argument("--drm-library", required=True, help="exact renamed SDK DRM library")
    parser.add_argument("--drm-amdgpu-library", required=True, help="exact renamed SDK AMDGPU library")
    parser.add_argument("--runtime-rpath", required=True, help="original RPATH/RUNPATH string, or empty")
    parser.add_argument("--output", required=True, help="fresh absolute private output directory")
    args = parser.parse_args()

    require(sys.platform.startswith("linux"), "Linux disposable build container required")
    require(os.environ.get("HALOGEN_PRIVATE_CPU_CONTAINER") == "1", "ROOT container marker required")
    require(not Path("/dev/kfd").exists() and not Path("/dev/dxg").exists()
            and not list(Path("/dev/dri").glob("renderD*")), "GPU devices must not be mounted")
    source = Path(args.source_root).resolve(strict=True)
    sdk = Path(args.sdk_root).resolve(strict=True)
    patch = checked_file(args.patch)
    output_arg = Path(args.output)
    require(output_arg.is_absolute(), "output must be an absolute container path")
    output = output_arg.resolve()
    require(not output.exists(), "output must not already exist")
    require(not output.is_relative_to(source) and not source.is_relative_to(output)
            and not output.is_relative_to(sdk) and not sdk.is_relative_to(output),
            "output must be separate from supplied source and SDK")
    for path in (source, sdk, output, patch):
        require(re.fullmatch(r"/[A-Za-z0-9_./+\-]+", str(path)),
                f"simple absolute POSIX path required for CMake/pkg-config: {path}")
    require(sha(source / "CMakeLists.txt") == BASE_CMAKE_SHA, "base CMake hash mismatch")
    require(sha(source / RUNTIME_REL) == BASE_RUNTIME_SHA, "base runtime hash mismatch")
    require(not (source / HEADER_REL).exists(), "base source already contains patch header")
    require(sha(patch) == PATCH_SHA, "backport patch hash mismatch")
    clang = checked_file(args.clang, sdk)
    clangxx = checked_file(args.clangxx, sdk)
    objcopy = checked_file(args.objcopy, sdk)
    bitcode = checked_file(sdk / "lib/llvm/amdgcn/bitcode/ocml.bc", sdk).parent
    elf = checked_file(sdk / "lib/rocm_sysdeps/lib/librocm_sysdeps_elf.so.1", sdk)
    numa = checked_file(sdk / "lib/rocm_sysdeps/lib/librocm_sysdeps_numa.so.1", sdk)
    drm = checked_file(args.drm_library, sdk)
    amdgpu = checked_file(args.drm_amdgpu_library, sdk)
    profiler = checked_file(sdk / "lib/librocprofiler-register.so.0", sdk)
    profiler_header = checked_file(sdk / "include/rocprofiler-register/rocprofiler-register.h", sdk)
    for path in (drm, amdgpu):
        require(path.parent == elf.parent and re.fullmatch(r"librocm_sysdeps_[A-Za-z0-9_]+\.so(?:\.[0-9]+)*", path.name),
                f"exact renamed SDK sysdep required: {path}")
    require(drm != amdgpu, "DRM and AMDGPU libraries must be distinct")
    for header in ("/usr/include/libelf.h", "/usr/include/numa.h", "/usr/include/xf86drm.h", "/usr/include/libdrm/amdgpu.h"):
        require(Path(header).is_file(), f"missing Debian development header: {header}")
    for name in ("cmake", "ninja", "pkg-config", "patch", "bash", "xxd", "readelf", "nm"):
        require(shutil.which(name), f"missing disposable-container tool: {name}")

    output.mkdir(parents=True)
    commands = []
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = ":".join([str(sdk / "lib"), str(elf.parent), env.get("LD_LIBRARY_PATH", "")]).rstrip(":")

    def run(argv, log, cwd=None):
        commands.append({"argv": [str(item) for item in argv], "cwd": str(cwd) if cwd else None, "log": log})
        with (output / log).open("x", encoding="utf-8") as handle:
            result = subprocess.run([str(item) for item in argv], cwd=cwd, env=env,
                                    stdout=handle, stderr=subprocess.STDOUT, check=False)
        require(result.returncode == 0, f"command exited {result.returncode}; see {output / log}")
        return (output / log).read_text(encoding="utf-8", errors="replace")

    compiler_version = run([clang, "--version"], "clang-version.txt")
    require(re.search(r"clang version 23\.", compiler_version), "exact SDK Clang 23 required")
    compilerxx_version = run([clangxx, "--version"], "clangxx-version.txt")
    require(re.search(r"clang version 23\.", compilerxx_version), "exact SDK Clang++ 23 required")
    run([objcopy, "--version"], "objcopy-version.txt")
    compiler_help = run([clang, "--help"], "clang-help.txt")
    require("--rocm-device-lib-path" in compiler_help, "SDK compiler lacks explicit device-library path flag")

    shim = output / "shim"
    wrapper = shim / "bin/clang-device"
    # Only OpenCL image blits consume device libraries; assembly invocations stay unchanged.
    write(wrapper, "#!/bin/bash\nfor arg in \"$@\"; do\n  if [ \"$arg\" = cl ]; then\n    exec "
          + shlex.quote(str(clang)) + " " + shlex.quote("--rocm-device-lib-path=" + str(bitcode))
          + " \"$@\"\n  fi\ndone\nexec " + shlex.quote(str(clang)) + " \"$@\"\n")
    wrapper.chmod(0o755)
    for package, target, executable in (("Clang", "clang", wrapper), ("LLVM", "llvm-objcopy", objcopy)):
        write(shim / f"cmake/{package}/{package}Config.cmake",
              f"if(NOT TARGET {target})\n  add_executable({target} IMPORTED GLOBAL)\n"
              f"  set_target_properties({target} PROPERTIES IMPORTED_LOCATION \"{executable}\")\nendif()\n"
              f"set({package}_FOUND TRUE)\n")
    write(shim / "cmake/rocprofiler-register/rocprofiler-register-config.cmake",
          "if(NOT TARGET rocprofiler-register::rocprofiler-register)\n"
          "  add_library(rocprofiler-register::rocprofiler-register SHARED IMPORTED GLOBAL)\n"
          "  set_target_properties(rocprofiler-register::rocprofiler-register PROPERTIES\n"
          f"    IMPORTED_LOCATION \"{profiler}\"\n    INTERFACE_INCLUDE_DIRECTORIES \"{sdk / 'include'}\")\n"
          "endif()\nset(rocprofiler-register_FOUND TRUE)\n")
    (shim / "lib").mkdir()
    for name, library in (("libdrm", drm), ("libdrm_amdgpu", amdgpu)):
        stem = library.name.split(".so", 1)[0]
        (shim / "lib" / (stem + ".so")).symlink_to(library)
        requires = "Requires: libdrm\n" if name == "libdrm_amdgpu" else ""
        write(shim / f"pkgconfig/{name}.pc",
              f"Name: {name}\nDescription: Exact SDK renamed dependency with Debian headers\nVersion: 0\n"
              f"{requires}Libs: -L{shim / 'lib'} -l{stem[3:]}\nCflags: -I/usr/include/libdrm\n")
    env["PKG_CONFIG_PATH"] = str(shim / "pkgconfig")
    env["PKG_CONFIG_LIBDIR"] = str(shim / "pkgconfig")
    env["HIP_DEVICE_LIB_PATH"] = str(bitcode)
    run(["pkg-config", "--libs", "--cflags", "libdrm", "libdrm_amdgpu"], "pkgconfig.txt")

    manifest = {"base_commit": BASE_COMMIT, "patch_sha256": PATCH_SHA, "sdk_root": str(sdk),
                "source_root": str(source), "compiler_version": compiler_version,
                "target_devices": IMAGE_TARGET_DEVICES, "jobs": 2, "runtime_rpath": args.runtime_rpath,
                "inputs": {str(path): sha(path) for path in (clang, clangxx, objcopy, elf, numa, drm, amdgpu, profiler, profiler_header, bitcode / "ocml.bc")},
                "commands": commands, "artifacts": {}}
    try:
        for variant in ("stock", "patched"):
            private_source = output / variant / "source"
            shutil.copytree(source, private_source)
            for rel in GENERATORS:
                (private_source / rel).chmod(0o755)
            if variant == "patched":
                run(["patch", "--batch", "--forward", "--dry-run", "-p3", "-i", patch], "patch-check.txt", private_source)
                run(["patch", "--batch", "--forward", "-p3", "-i", patch], "patch-apply.txt", private_source)
                require(sha(private_source / HEADER_REL) == HEADER_SHA, "patched header hash mismatch")
            build = output / variant / "build"
            configure = ["cmake", "-S", private_source, "-B", build, "-G", "Ninja",
                         "-DCMAKE_BUILD_TYPE=Release", f"-DCMAKE_C_COMPILER={clang}", f"-DCMAKE_CXX_COMPILER={clangxx}",
                         "-DCMAKE_EXE_LINKER_FLAGS=-rtlib=libgcc", "-DCMAKE_SHARED_LINKER_FLAGS=-rtlib=libgcc",
                         "-DBUILD_SHARED_LIBS=ON", "-DBUILD_ROCR=ON", "-DBUILD_THUNK_VIRTIO=OFF",
                         "-DIMAGE_SUPPORT=ON", "-DPC_SAMPLING_SUPPORT=ON", f"-DTARGET_DEVICES={IMAGE_TARGET_DEVICES}",
                         "-DENABLE_LDCONFIG=OFF", "-DEXPORT_TO_USER_PACKAGE_REGISTRY=OFF",
                         "-DCMAKE_BUILD_WITH_INSTALL_RPATH=ON", f"-DCMAKE_INSTALL_RPATH={args.runtime_rpath.replace(':', ';')}",
                         f"-DCMAKE_INSTALL_PREFIX={output / variant / 'unused-install'}",
                         f"-DClang_DIR={shim / 'cmake/Clang'}", f"-DLLVM_DIR={shim / 'cmake/LLVM'}",
                         f"-Drocprofiler-register_DIR={shim / 'cmake/rocprofiler-register'}",
                         f"-DLIBELF_LIBRARIES={elf}", "-DLIBELF_INCLUDE_DIRS=/usr/include",
                         f"-DNUMA={numa}", f"-DNUMA_LIBRARIES={numa}"]
            run(configure, f"{variant}-configure.txt")
            run(["cmake", "--build", build, "--target", "hsa-runtime64", "--parallel", "2"], f"{variant}-build.txt")
            library_dir = build / "rocr/lib"
            artifacts = output / variant / "lib"
            artifacts.mkdir()
            libraries = sorted(library_dir.glob("libhsa-runtime64.so*"))
            require(libraries, f"no HSA library produced under {library_dir}")
            for library in libraries:
                require(library.resolve().is_relative_to(library_dir.resolve()), "build library symlink escapes output")
                if library.is_symlink():
                    (artifacts / library.name).symlink_to(Path(os.readlink(library)).name)
                else:
                    shutil.copy2(library, artifacts / library.name)
            real = (artifacts / "libhsa-runtime64.so.1").resolve(strict=True)
            run(["readelf", "-d", real], f"{variant}-dynamic.txt")
            run(["readelf", "--version-info", real], f"{variant}-versions.txt")
            run(["nm", "-D", "--defined-only", "--format=posix", real], f"{variant}-exports.txt")
            manifest["artifacts"][variant] = {"library": str(real), "sha256": sha(real), "bytes": real.stat().st_size}
        manifest["status"] = "built_private_only_unqualified"
    except Exception as error:
        manifest["status"] = "failed"
        manifest["error"] = str(error)
        raise
    finally:
        write(output / "build-manifest.json", json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"status": manifest["status"], "output": str(output), "artifacts": manifest["artifacts"]}, indent=2))


if __name__ == "__main__":
    main()
