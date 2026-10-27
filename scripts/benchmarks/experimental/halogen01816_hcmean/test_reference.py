"""CPU bit oracle and adversarial source-expression checks; never touches HIP."""
import importlib.util
import struct
import random
import sys
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location('hcmean_reference', HERE/'reference.py')
ops=None
if SPEC and SPEC.loader and (HERE/'reference.py').exists():
    ops=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(ops)

class BitReference(unittest.TestCase):
    def test_component_exists(self):self.assertIsNotNone(ops,'explicit mean bit contract missing')

    @unittest.skipIf(ops is None,'component missing')
    def test_rne_ties_subnormal_signedzero_and_specials(self):
        self.assertEqual(ops.to_bf16(1.00390625),0x3f80)
        self.assertEqual(ops.to_bf16(1.01171875),0x3f82)
        self.assertEqual(ops.to_bf16(2.0**-133),1)
        self.assertEqual(ops.to_bf16(-0.0),0x8000)
        self.assertEqual(ops.mean_bits([0x8000]*4),0)
        self.assertEqual(ops.mean_bits([0x7f80]*4),0x7f80)
        self.assertEqual(ops.mean_bits([0x7f80,0xff80,0,0]),0x7fc0)

    @unittest.skipIf(ops is None,'component missing')
    def test_cancellation_and_overflow_are_explicit(self):
        b=ops.to_bf16
        self.assertEqual(ops.mean_bits(list(map(b,[2**24,1,-2**24,1]))),b(.25))
        self.assertEqual(ops.mean_bits(list(map(b,[2**24,-2**24,1,1]))),b(.5))
        self.assertEqual(ops.mean_bits([0x7f7f]*4),0x7f80)
        self.assertNotEqual(ops.mean_bits(list(map(b,[2**24,1,-2**24,1]))),b(.5))

    @unittest.skipIf(ops is None,'component missing')
    def test_fixture_layout_taps_tail_and_guards(self):
        for rows,offset in ((1,0),(4,3),(8192,8191)):
            raw,expected=ops.make_fixture(rows,offset,1,4,2)
            self.assertEqual(len(raw),(rows*10240))
            self.assertEqual(len(expected),4*12800)
            self.assertTrue(all(v==0x55aa for v in expected[:2*12800]))
            start=2*12800+4*2560
            for col in (0,7,8,2559):
                xs=[raw[offset*10240+s*2560+col] for s in range(4)]
                self.assertEqual(expected[start+col],ops.mean_bits(xs))
            self.assertEqual(expected[start-1],0x55aa)
        with self.assertRaises(ValueError):ops.make_fixture(4,4,1,0,0)

@unittest.skipUnless('--run-cpu' in sys.argv,'explicit torch CPU check only')
class SourceExpression(unittest.TestCase):
    def test_actual_torch_cpu_mean_bits_adversarial(self):
        import torch
        torch.set_num_threads(1);torch.set_num_interop_threads(1)
        rng=random.Random(1816)
        patterns=ops.patterns()+[[rng.randrange(65536) for _ in range(4)] for _ in range(4096)]
        raw=torch.tensor([[p[s] for p in patterns] for s in range(4)],dtype=torch.uint16,device='cpu').view(torch.bfloat16)
        result=raw.mean(0).view(torch.uint16).tolist()
        expected=[ops.mean_bits(p) for p in patterns]
        # NaN payload is intentionally canonical in kernel contract, not payload parity.
        for p,a,b in zip(patterns,result,expected):
            if (b&0x7fff)>0x7f80:self.assertGreater(a&0x7fff,0x7f80)
            else:self.assertEqual(a,b,(p,a,b))

if __name__=='__main__':
    if '--run-cpu' in sys.argv:sys.argv.remove('--run-cpu');SourceExpression.__unittest_skip__=False
    unittest.main()
