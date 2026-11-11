"""CPU actual-ELF and constructor-use regression; no compiler or ELF load."""
import hashlib
import json
from pathlib import Path
import re
import struct
import unittest

HERE = Path(__file__).resolve().parent
PRIMARY = HERE.parents[1]


class ColdAddressTests(unittest.TestCase):
    def test_actual_constructor_uses_only_generated_address_roles(self):
        source = (HERE / 'cold_install.c').read_text()
        initializer = source[source.index('__attribute__((constructor))'):]
        self.assertNotRegex(initializer, r'image_base\s*\+\s*0x')
        self.assertIn('hgn0202_cold_addresses(image_base, &seam, &fallback, &consume)', initializer)
        self.assertIn('near_relay(seam)', initializer)
        self.assertIn('hgn0202_stream_configure(descriptor, 1, fallback, consume)', initializer)
        self.assertIn('memcpy((void *)seam, patch, sizeof(patch))', initializer)
        for old in ('1e9f166', '1e9f16d', '1e9f6ed'):
            self.assertNotIn(old, source)

    def test_generated_rows_match_fresh_proof_and_actual_executable_segments(self):
        elf = (PRIMARY / 'extracted/flash_serve').read_bytes()
        contract = json.loads((PRIMARY / 'npu-consumer-seam-v1/native-contract.json').read_bytes())
        self.assertEqual(hashlib.sha256(elf).hexdigest(), 'bf84053705d1e89c214ff64c79ad1276c5fe353d80a9bb0f38ef3bac6645b97c')
        header = (HERE / 'native_pins.h').read_text()
        rows = re.findall(r'\{(0x[0-9a-f]+),(\d+),pin(\d+)\}', header)
        self.assertEqual([int(row[0], 16) for row in rows], [0x1f96dc6, 0x1f96dcd, 0x1f9734d])
        phoff = struct.unpack_from('<Q', elf, 32)[0]
        size, count = struct.unpack_from('<HH', elf, 54)
        for rva, length, index in rows:
            expected = bytes(int(v, 16) for v in re.search(r'pin' + index + r'\[\] = \{([^}]+)\}', header)[1].split(','))
            self.assertEqual(len(expected), int(length))
            matches = []
            for i in range(count):
                typ, flags, offset, begin, _, nbytes, _, _ = struct.unpack_from('<IIQQQQQQ', elf, phoff + i * size)
                if typ == 1 and flags & 1 and begin <= int(rva, 16) and int(rva, 16) + int(length) <= begin + nbytes:
                    matches.append(elf[offset + int(rva, 16) - begin:offset + int(rva, 16) - begin + int(length)])
            self.assertEqual(matches, [expected])
        self.assertIsInstance(contract, dict)


if __name__ == '__main__': unittest.main()
