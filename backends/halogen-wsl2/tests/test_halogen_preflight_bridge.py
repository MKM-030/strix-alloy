"""CPU ELF fixture: production detour/helper/assembly; no HIP or model launch."""
import hashlib
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'posix', 'Linux GCC CPU fixtures; run inside WSL explicitly')
class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='preflight-bridge-')
        cls.build = pathlib.Path(cls.tmp.name)
        cls.exe = cls.build / 'flash_serve'
        cls.compile(['-fPIE', '-pie', '-rdynamic', '-fno-omit-frame-pointer',
                     str(ROOT / 'tests/preflight-bridge-fixture.c'),
                     str(ROOT / 'tests/preflight-bridge-fixture.S'), '-ldl', '-o', str(cls.exe)])
        cls.original = cls.exe.read_bytes()
        cls.digest = hashlib.sha256(cls.original).hexdigest()
        symbols = subprocess.check_output(['nm', '-n', str(cls.exe)], text=True)
        cls.symbols = {line.split()[2]: int(line.split()[0], 16)
                       for line in symbols.splitlines() if len(line.split()) == 3}
        cls.lib = cls.build / 'bridge.so'
        cls.build_bridge(cls.lib)
        cls.faults = cls.build / 'faults.so'
        cls.compile(['-shared', '-fPIC', str(ROOT / 'tests/preflight-bridge-faults.c'),
                     '-ldl', '-o', str(cls.faults)])

    @classmethod
    def compile(cls, flags):
        result = subprocess.run(['gcc', '-O2', '-Wall', '-Wextra', '-Werror'] + flags,
                                text=True, capture_output=True)
        if result.returncode:
            raise AssertionError(result.stderr)

    @classmethod
    def build_bridge(cls, output, digest=None, symbol='fixture_site'):
        source = ROOT / 'patches/halogen-preflight-bridge.c'
        if not source.exists():
            cls.compile(['-shared', '-fPIC', '-x', 'c', '/dev/null', '-o', str(output)])
            return
        cls.compile(['-shared', '-fPIC', '-DHALOGEN_BRIDGE_FIXTURE=1',
                     '-DHALOGEN_BRIDGE_FIXTURE_SHA256="' + (digest or cls.digest) + '"',
                     '-DHALOGEN_BRIDGE_FIXTURE_RVA=' + str(cls.symbols[symbol]),
                     str(source), str(ROOT / 'patches/halogen-preflight-trampoline.S'),
                     '-ldl', '-o', str(output)])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, case='abi', changes=None, library=None, exe=None, code=0):
        env = dict(os.environ, LD_PRELOAD=str(library or self.lib),
                   HALOGEN_PREFLIGHT_PROFILE='flash0138-copy48-v1',
                   HALOGEN_HYBRID_PROFILE='vgm64-copy48-v1',
                   HALOGEN_HYBRID_COPY_BYTES='51539607552',
                   HALOGEN_HYBRID_RECLAIM_COPY='1', HALOGEN_FLASH_PIN_TRUNK='1')
        for key, value in (changes or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        result = subprocess.run([str(exe or self.exe), case], env=env,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertEqual(self.exe.read_bytes(), self.original)
        return result

    def test_actual_trampoline_preserves_abi(self):
        self.assertIn('ABI GP/flags/x87/MXCSR/XMM/stack/frame verified', self.run_case().stdout)

    def test_installed_detour_and_original_low_memory_comparison(self):
        self.run_case('admission')
        self.run_case('low')

    def test_full_digest_and_loaded_signature_and_permissions(self):
        for name, digest, symbol in [('hash', '0' * 64, 'fixture_site'),
                                     ('signature', None, 'fixture_bad_signature'),
                                     ('permissions', None, 'fixture_writable')]:
            with self.subTest(name=name):
                library = self.build / (name + '.so')
                self.build_bridge(library, digest, symbol)
                self.run_case(library=library, code=78)

    def test_other_process_is_inert_even_without_profile(self):
        exe = self.build / 'other-process'
        shutil.copyfile(self.exe, exe); exe.chmod(0o755)
        self.assertEqual(self.run_case('inert', exe=exe,
                          changes={'HALOGEN_PREFLIGHT_PROFILE': None}).stdout, 'inert\n')

    def test_exact_configuration_required(self):
        for key, values in {
            'HALOGEN_PREFLIGHT_PROFILE': [None, '', 'wrong'],
            'HALOGEN_HYBRID_PROFILE': [None, 'wrong'],
            'HALOGEN_HYBRID_COPY_BYTES': [None, '51539607553', '051539607552'],
            'HALOGEN_HYBRID_RECLAIM_COPY': [None, '0'],
            'HALOGEN_FLASH_PIN_TRUNK': [None, '0'],
            'HALOGEN_PREFLIGHT_TRACE_ONLY': ['yes', '2'],
        }.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.run_case(changes={key: value}, code=78)

    def test_inert_fake_capacity_variable_cannot_change_admission(self):
        self.run_case('low', changes={'HALOGEN_FAKE_MEMAVAILABLE_BYTES': str(1 << 60)})

    def test_helper_failures_are_terminal(self):
        for case in ('planner_error', 'too_large', 'overflow', 'reversed', 'misaligned',
                     'oversized', 'null_object', 'floor'):
            with self.subTest(case=case):
                self.run_case(case, code=79)

    def test_trace_exits_before_return_to_engine(self):
        result = self.run_case(changes={'HALOGEN_PREFLIGHT_TRACE_ONLY': '1'}, code=77)
        for text in ('aggregate=8192', 'host=4096', 'mapping=16384', 'count=2',
                     'range[0]=0:4096', 'range[1]=8192:12288'):
            self.assertIn(text, result.stderr)
        self.assertNotIn('ABI GP', result.stdout)
        self.run_case(changes={'HALOGEN_PREFLIGHT_TRACE_ONLY': '0'})

    def test_installation_failures_are_bounded_and_terminal(self):
        for fault, reason in {
            'mmap_exhaust': 'thunk-candidates-exhausted',
            'mmap_error': 'thunk-map',
            'mmap_wrong_address': 'fixed-noreplace-unsupported',
            'munmap_error': 'thunk-unmap',
            'thunk_rx': 'thunk-rx', 'text_rw': 'text-rw', 'text_rx': 'text-rx',
            'stat_error': 'executable-open-stat', 'stat_drift': 'digest-consistency',
            'read_error': 'elf-format',
        }.items():
            with self.subTest(fault=fault):
                result = self.run_case(changes={'FIXTURE_BRIDGE_FAULT': fault},
                    library=str(self.faults) + ':' + str(self.lib), code=78)
                self.assertIn('reason=' + reason, result.stderr)
                if fault == 'mmap_exhaust':
                    self.assertIn('bounded attempts=256', result.stderr)
                self.assertNotIn('active sha256=', result.stderr)

    def test_no_writable_executable_transition(self):
        self.run_case('admission', library=str(self.faults) + ':' + str(self.lib))

    def test_occupied_candidate_is_never_overwritten(self):
        result = self.run_case('admission', changes={'FIXTURE_OCCUPY_CANDIDATE': '1'})
        self.assertIn('occupied candidate unchanged', result.stdout)

    def test_production_build_has_no_fixture_hash_or_runtime_bypass(self):
        library = self.build / 'production.so'
        self.compile(['-shared', '-fPIC', '-DHALOGEN_RESEARCH_VGM64=1',
                      '-DHALOGEN_PREFLIGHT_V1=1', '-mno-avx', '-mno-avx2', '-mno-avx512f',
                      str(ROOT / 'patches/hip-register-hybrid.c'),
                      str(ROOT / 'patches/halogen-preflight-bridge.c'),
                      str(ROOT / 'patches/halogen-preflight-trampoline.S'), '-ldl', '-pthread',
                      '-Wl,-z,relro,-z,now,-z,noexecstack,-z,defs', '-o', str(library)])
        self.assertIn(b'39382df17e7bd922a302d7dbfaaaa80d5dbb4a813e50268265a74c70c8679625',
                      library.read_bytes())
        self.assertNotIn(self.digest.encode(), library.read_bytes())
        result = self.run_case(library=library, code=78)
        self.assertIn('reason=elf-sha256', result.stderr)


if __name__ == '__main__':
    unittest.main()
