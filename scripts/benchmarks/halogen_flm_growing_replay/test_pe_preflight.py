"""Synthetic CPU-only PE32+ fixtures. No compiled or loaded test binaries."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('growing_static_PE_tests', HERE / 'pe_preflight.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def make_pe(*, imports=(), exports=(), delay=()):
    data = bytearray(0x5200)
    def put(offset, fmt, *values):
        struct.pack_into(fmt, data, offset, *values)
    def off(rva):
        return rva - 0x1000 + 0x200
    data[:2] = b'MZ'; put(0x3c, '<I', 0x80)
    data[0x80:0x84] = b'PE\0\0'
    put(0x84, '<HH', 0x8664, 1); put(0x94, '<H', 240)
    optional = 0x98
    put(optional, '<H', 0x20b); put(optional + 24, '<Q', 0x140000000)
    put(optional + 60, '<I', 0x200); put(optional + 108, '<I', 16)
    section = optional + 240
    data[section:section + 8] = b'.rdata\0\0'
    put(section + 8, '<IIII', 0x5000, 0x1000, 0x5000, 0x200)
    cursor = 0x2000
    def allocate(raw, alignment=1):
        nonlocal cursor
        cursor = (cursor + alignment - 1) // alignment * alignment
        rva = cursor; data[off(rva):off(rva) + len(raw)] = raw; cursor += len(raw)
        return rva
    def text(value):
        return allocate(value.encode('ascii') + b'\0')
    if exports:
        put(optional + 112, '<II', 0x1000, 0x400)
        highest = max(item[0] for item in exports)
        named = [item for item in exports if item[1] is not None]
        put(off(0x1000) + 16, '<IIIIII', 1, highest, len(named), 0x1040, 0x1080, 0x10c0)
        export_cursor = 0x1100
        for ordinal, name, forward in exports:
            if forward:
                raw = forward.encode() + b'\0'; address = export_cursor
                data[off(address):off(address) + len(raw)] = raw; export_cursor += len(raw)
            else:
                address = 0x4000
            put(off(0x1040) + (ordinal - 1) * 4, '<I', address)
        for i, (ordinal, name, forward) in enumerate(named):
            raw = name.encode() + b'\0'; address = export_cursor
            data[off(address):off(address) + len(raw)] = raw; export_cursor += len(raw)
            put(off(0x1080) + i * 4, '<I', address)
            put(off(0x10c0) + i * 2, '<H', ordinal - 1)
    for delayed, rows, start, index, width in ((False, imports, 0x1400, 1, 20), (True, delay, 0x1800, 13, 32)):
        if not rows:
            continue
        put(optional + 112 + index * 8, '<II', start, (len(rows) + 1) * width)
        for i, (module, symbols) in enumerate(rows):
            values = []
            for symbol in symbols:
                values.append((1 << 63) | symbol if type(symbol) is int else allocate(b'\0\0' + symbol.encode() + b'\0'))
            thunk = allocate(struct.pack('<' + 'Q' * (len(values) + 1), *values, 0), 8)
            module_rva = text(module)
            if delayed:
                put(off(start) + i * width, '<IIIIIIII', 1, module_rva, 0, thunk, thunk, 0, 0, 0)
            else:
                put(off(start) + i * width, '<IIIII', thunk, 0, 0, module_rva, thunk)
    return bytes(data)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HERE)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.portable = self.root / 'portable'; self.portable.mkdir()
        self.system = self.root / 'system32'; self.system.mkdir()
        self.entry = self.portable / 'entry.exe'

    def write(self, name, data, system=False):
        path = (self.system if system else self.portable) / name
        path.write_bytes(data)
        return path

    def inspect(self, **kwargs):
        return p.inspect_closure(self.entry, self.portable, self.system, expected_pins={}, **kwargs)

    def test_named_ordinal_and_delay_imports_resolve(self):
        self.entry.write_bytes(make_pe(imports=[('a.dll', ['hello', 2])], delay=[('B.dll', ['later'])]))
        self.write('a.dll', make_pe(exports=[(1, 'hello', None), (2, None, None)]))
        self.write('b.DLL', make_pe(exports=[(1, 'later', None)]), system=True)
        result = self.inspect()
        self.assertTrue(result['passed'] and result['full_static_closure_complete'])
        self.assertEqual(result['total_import_symbols'], 3)
        self.assertFalse(result['DLL_loaded'])
        self.assertEqual(result['subprocesses_started'], 0)

    def test_named_and_ordinal_forwarder_chain_resolves(self):
        self.entry.write_bytes(make_pe(imports=[('a.dll', ['hello'])]))
        self.write('a.dll', make_pe(exports=[(1, 'hello', 'b.#2')]))
        self.write('b.dll', make_pe(exports=[(2, None, 'c.final')]), system=True)
        self.write('c.dll', make_pe(exports=[(1, 'final', None)]), system=True)
        result = self.inspect()
        self.assertTrue(result['passed'])
        self.assertEqual(len([edge for edge in result['edges'] if 'forwarder' in edge]), 2)

    def test_forwarder_cycle_fails_without_unbounded_walk(self):
        self.entry.write_bytes(make_pe(imports=[('a.dll', ['x'])]))
        self.write('a.dll', make_pe(exports=[(1, 'x', 'b.y')]))
        self.write('b.dll', make_pe(exports=[(1, 'y', 'a.x')]))
        result = self.inspect()
        self.assertFalse(result['passed'])
        self.assertIn('cycle', result['errors'][0]['message'])

    def test_API_set_is_honest_OS_classification_not_payload_failure(self):
        self.entry.write_bytes(make_pe(imports=[('api-ms-win-core-test-l1-1-0.dll', ['x'])]))
        result = self.inspect()
        self.assertTrue(result['passed'] and result['payload_closure_passed'])
        self.assertFalse(result['full_static_closure_complete'])
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['unresolved_API_set_contracts'], ['api-ms-win-core-test-l1-1-0.dll'])

    def test_missing_real_symbol_and_missing_real_module_fail(self):
        self.entry.write_bytes(make_pe(imports=[('a.dll', [2]), ('missing.dll', ['x'])]))
        self.write('a.dll', make_pe(exports=[(1, 'different', None)]))
        result = self.inspect()
        self.assertFalse(result['payload_closure_passed'])
        self.assertEqual(len(result['errors']), 2)

    def test_malformed_optional_header_and_unmapped_export_fail(self):
        data = bytearray(make_pe())
        struct.pack_into('<I', data, 0x98 + 108, 17)
        self.entry.write_bytes(data)
        result = self.inspect()
        self.assertFalse(result['passed'])
        self.assertIn('directory', result['errors'][0]['message'])
        data = bytearray(make_pe(exports=[(1, 'x', None)]))
        struct.pack_into('<I', data, 0x240, 0x90000000)
        self.entry.write_bytes(data)
        self.assertFalse(self.inspect()['passed'])

    def test_descriptor_and_file_and_module_limits_are_finite(self):
        self.entry.write_bytes(make_pe(imports=[('a.dll', ['x'])]))
        self.write('a.dll', make_pe(exports=[(1, 'x', None)]))
        self.assertFalse(self.inspect(limits=dict(max_modules=1))['passed'])
        self.assertFalse(self.inspect(limits=dict(max_file_bytes=20))['passed'])
        self.assertFalse(self.inspect(limits=dict(max_descriptors=1))['passed'])

    def test_dependency_hash_drift_is_rejected(self):
        self.entry.write_bytes(make_pe(imports=[('a.dll', ['x'])]))
        self.write('a.dll', make_pe(exports=[(1, 'x', None)]))
        result = p.inspect_closure(self.entry, self.portable, self.system, expected_pins={'a.dll': '0' * 64})
        self.assertFalse(result['passed'])
        self.assertIn('hash differs', result['errors'][0]['message'])

    def test_loader_zeroed_data_export_is_valid_without_reading_virtual_bytes(self):
        self.entry.write_bytes(make_pe(imports=[('a.dll', ['data'])]))
        data = bytearray(make_pe(exports=[(1, 'data', None)]))
        # Keep export metadata file-backed; exported storage is in zero-filled tail.
        struct.pack_into('<I', data, 0x98 + 240 + 8, 0x6000)
        struct.pack_into('<I', data, 0x240, 0x6500)
        self.write('a.dll', data)
        self.assertTrue(self.inspect()['passed'])

    def test_OS_internal_optional_imports_are_classified_without_payload_failure(self):
        self.entry.write_bytes(make_pe(imports=[('os.dll', ['x'])]))
        self.write('os.dll', make_pe(exports=[(1, 'x', None)], imports=[('optional.dll', ['y'])]), system=True)
        result = self.inspect()
        self.assertTrue(result['payload_closure_passed'])
        self.assertFalse(result['full_static_closure_complete'])
        self.assertEqual(len(result['OS_internal_import_modules_not_expanded']), 1)

    def test_XRT_imports_are_audited_even_when_XRT_is_in_System32(self):
        self.entry.write_bytes(make_pe(imports=[('xrt_coreutil.dll', ['x'])]))
        path = self.write('xrt_coreutil.dll', make_pe(exports=[(1, 'x', None)],
            imports=[('missing.dll', ['y'])]), system=True)
        result = p.inspect_closure(self.entry, self.portable, self.system,
                                  expected_pins={'xrt_coreutil.dll': p.hashlib.sha256(path.read_bytes()).hexdigest()})
        self.assertFalse(result['payload_closure_passed'])
        self.assertIn('missing.dll', result['errors'][0]['message'])


if __name__ == '__main__':
    unittest.main()
