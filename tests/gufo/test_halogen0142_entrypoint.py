"""Offline checks for the pinned 0.14.2 entrypoint transformation."""

import pathlib
import subprocess
import unittest

from experimental.halogen0142 import entrypoint_adapter as adapter


REPO = pathlib.Path(__file__).resolve().parents[2]
ROOT = REPO.parent / 'strix-alloy-research'
UPSTREAM = ROOT / "artifacts" / "halogen0142" / "entrypoint.sh"


class EntrypointAdapterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not UPSTREAM.is_file():
            raise unittest.SkipTest('Historical 0.14.2 sibling research entrypoint required')
        cls.original = UPSTREAM.read_bytes()

    def test_exact_upstream_identity_and_only_function_replaced(self):
        changed = adapter.transform(self.original)
        self.assertNotEqual(changed, self.original)
        old_start = self.original.index(b"host_preflight() {\n")
        old_end = self.original.index(b"\n}\n", old_start) + 3
        new_start = changed.index(b"native_host_preflight() {\n")
        new_end = changed.index(b"\n}\n", new_start) + 3
        self.assertEqual(changed[:new_start], self.original[:old_start])
        self.assertIn(self.original[old_start:old_end].replace(b"host_preflight()", b"native_host_preflight()"), changed)
        self.assertEqual(changed[changed.index(b"# THE DOWNLOAD'S SIZE"):], self.original[old_end + 1:])
        self.assertEqual(changed.count(b"host_preflight() {"), 2)

    def test_changed_input_rejected(self):
        changed = self.original.replace(b"WSL2 is not a supported host", b"WSL2 is now supported", 1)
        with self.assertRaisesRegex(ValueError, "SHA256"):
            adapter.transform(changed)

    def test_wsl_profile_requires_real_device_library_gpu_and_no_download(self):
        output = adapter.transform(self.original).decode()
        start = output.index("native_host_preflight() {")
        end = output.index("# THE DOWNLOAD'S SIZE", start)
        functions = output[start:end]
        # Fixture substitutions exist only here. The generated entrypoint uses
        # fixed production paths and a real HIP probe executable.
        functions = functions.replace("/dev/kfd", "$KFD_FIXTURE")
        functions = functions.replace("/dev/dxg", "$DXG_FIXTURE")
        functions = functions.replace("/usr/lib/librocdxg.so", "$LIB_FIXTURE")
        functions = functions.replace("/candidate/halogen0142_hip_probe", "$PROBE_FIXTURE")
        shell = r'''
set -eu
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
KFD_FIXTURE="$tmp/kfd"
DXG_FIXTURE=/dev/null
LIB_FIXTURE=/home/revn/ciru-runtime/venv/lib/python3.14/site-packages/_rocm_sdk_devel/lib/librocdxg.so
PROBE_FIXTURE="$tmp/probe"
printf '#!/bin/sh\nprintf "%%s\\n" "${HIP_ARCH:-gfx1151}"\n' > "$PROBE_FIXTURE"
chmod +x "$PROBE_FIXTURE"
''' + functions + r'''
check() {
  expected=$1; shift
  if "$@" >/dev/null 2>&1; then rc=0; else rc=$?; fi
  [ "$rc" -eq "$expected" ] || { echo "expected $expected got $rc" >&2; exit 1; }
}
check 1 host_preflight
export HALOGEN_WSL_PROFILE=halogen0142-dxg
check 0 host_preflight
export HALOGEN_DOWNLOAD=some-repository
check 1 host_preflight
unset HALOGEN_DOWNLOAD
export HIP_ARCH=gfx1100
check 1 host_preflight
export HIP_ARCH=gfx1151
check 0 host_preflight
DXG_FIXTURE="$tmp/missing"
check 1 host_preflight
DXG_FIXTURE="$tmp/regular"
touch "$DXG_FIXTURE"
check 1 host_preflight
DXG_FIXTURE=/dev/null
LIB_FIXTURE="$tmp/wrong.so"
printf wrong > "$LIB_FIXTURE"
check 1 host_preflight
_hg_dev="$tmp"
_hg_sys="$tmp/sys"
touch "$KFD_FIXTURE"
check 0 host_preflight
mkdir -p "$tmp/sys/class/kfd/kfd/topology/nodes/1"
printf 'gfx_target_version 110500\n' > "$tmp/sys/class/kfd/kfd/topology/nodes/1/properties"
check 1 host_preflight
printf 'gfx_target_version 110501\n' > "$tmp/sys/class/kfd/kfd/topology/nodes/1/properties"
check 0 host_preflight
'''
        result = subprocess.run(
            ["wsl.exe", "-d", "Ubuntu-24.04", "-u", "revn", "-e", "bash", "-s"],
            input=shell.encode(), capture_output=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_native_fallback_has_upstream_behavior(self):
        output = adapter.transform(self.original).decode()
        self.assertIn("native_host_preflight()", output)
        self.assertIn("[ \"$v\" = \"110501\" ] && found=1", output)
        self.assertIn("native_host_preflight", output[output.index("host_preflight() {", output.index("native_host_preflight() {")) :])

    def test_probe_loads_versioned_hip_runtime_in_exact_image(self):
        source = (REPO / "experimental" / "halogen0142" /
                  "halogen0142_hip_probe.c").read_text()
        self.assertIn('dlopen("libamdhip64.so.7", RTLD_NOW | RTLD_LOCAL)', source)


if __name__ == "__main__":
    unittest.main()
