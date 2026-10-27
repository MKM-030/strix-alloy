"""Version binding and isolated reuse of audited CPU-only bridge fixtures."""
import importlib.util
import pathlib
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
RESEARCH = ROOT.parent / 'strix-alloy-research'
PUBLIC = ROOT.parent / 'strix-alloy-wsl2'
ENGINE = RESEARCH / 'artifacts/halogen0142/flash_serve'
GENERATOR = ROOT / 'experimental/halogen0142/bridge_adapter.py'


@unittest.skipUnless(ENGINE.is_file() and (PUBLIC/'patches').is_dir(),
                     'Historical 0.14.2 sibling research artifacts and public source required')
class BindingTests(unittest.TestCase):
    def adapter(self):
        self.assertTrue(GENERATOR.is_file(), 'candidate version-binding generator is required')
        spec = importlib.util.spec_from_file_location('candidate_bridge', GENERATOR)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_candidate_requires_exact_binding(self):
        m = self.adapter()
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td) / 'output'
            m.generate(PUBLIC / 'patches', ENGINE, out)
            bridge = (out / 'patches/halogen-preflight-bridge.c').read_text()
            self.assertIn(m.ENGINE_SHA, bridge)
            self.assertIn('0xdf7db0', bridge)
            self.assertIn('flash0142-copy48-v1', bridge)
            self.assertEqual((out / 'patches/halogen-preflight-trampoline.S').read_bytes(),
                             (PUBLIC / 'patches/halogen-preflight-trampoline.S').read_bytes())
            self.assertNotIn(m.ENGINE_SHA, (PUBLIC / 'patches/halogen-preflight-bridge.c').read_text())

    def test_rejects_source_drift(self):
        m = self.adapter()
        with tempfile.TemporaryDirectory() as td:
            source = pathlib.Path(td) / 'source'
            shutil.copytree(PUBLIC / 'patches', source)
            with (source / 'hip-register-hybrid.c').open('ab') as f:
                f.write(b'\n')
            with self.assertRaisesRegex(ValueError, 'source identity'):
                m.generate(source, ENGINE, pathlib.Path(td) / 'out')

    def test_rejects_engine_and_evidence_drift(self):
        m = self.adapter()
        data = ENGINE.read_bytes()
        m.verify_engine(data)
        for offset in (0, m.SITE_OFFSET, m.FUNCTION_OFFSET, len(data)-1):
            changed = bytearray(data)
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                m.verify_engine(bytes(changed))
        with self.assertRaisesRegex(ValueError, 'site signature'):
            m.verify_abi(data[:m.SITE_OFFSET] + b'\0' + data[m.SITE_OFFSET+1:])
        changed = bytearray(data)
        changed[m.FUNCTION_OFFSET] ^= 1
        with self.assertRaisesRegex(ValueError, 'ABI evidence'):
            m.verify_abi(bytes(changed))

    def test_existing_output_is_not_overwritten(self):
        m = self.adapter()
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileExistsError):
                m.generate(PUBLIC / 'patches', ENGINE, pathlib.Path(td))


@unittest.skipUnless(os.name == 'posix', 'CPU compiler fixtures require WSL/Linux')
@unittest.skipUnless(ENGINE.is_file() and (PUBLIC/'tests').is_dir(),
                     'Historical 0.14.2 sibling research artifacts and public fixtures required')
class CandidateCPUFixtures(unittest.TestCase):
    def test_candidate_uses_complete_original_cpu_suites(self):
        module = BindingTests().adapter()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td) / 'candidate'
            module.generate(PUBLIC / 'patches', ENGINE, root)
            shutil.copytree(PUBLIC / 'tests', root / 'tests', ignore=shutil.ignore_patterns('__pycache__'))
            # Candidate-only fixture copies bind the same cases to the new profile/hash.
            # Public files stay byte-for-byte unchanged.
            for name in ('test_halogen_preflight_bridge.py', 'test_halogen_preflight_plan.py'):
                path = root / 'tests' / name
                source = path.read_text().replace('flash0138-copy48-v1', 'flash0142-copy48-v1')
                source = source.replace(module.OLD_SHA, module.ENGINE_SHA)
                path.write_text(source)
                result = subprocess.run(['python3', str(path), '-v'], text=True,
                                        capture_output=True, timeout=120)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                print(result.stderr, flush=True)


if __name__ == '__main__':
    unittest.main()
