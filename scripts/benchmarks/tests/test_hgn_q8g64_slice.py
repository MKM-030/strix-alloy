"""Tiny CPU fixture for the reusable q8 row reader; no model file is opened."""
import io
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from halogen_npu_v2_dense_mlp import decode_q8g64
from halogen_npu_v2_head_assets import geometry, tensor_plan, decode_tile, MAX_TILE_BYTES
from halogen_npu_v2_sparse import WindowStream
from hgn_q8g64_slice import decode_rows


class Q8SliceTests(unittest.TestCase):
    def test_nonzero_rows_match_existing_dense_decoder_and_read_only_slice(self):
        width, count, offset = 128, 4, 32
        row_bytes = width + width // 16
        codes = np.arange(count * width, dtype=np.uint16).reshape(count, width).astype(np.uint8)
        affine = np.array([[[0.5, -2], [2, 3]], [[1, 7], [0.25, -1]],
                           [[2, -5], [0.5, 9]], [[0.125, 1], [4, -3]]], dtype="<f2")
        payload = b"".join(codes[row].tobytes() + affine[row].tobytes() for row in range(count))
        entry = dict(name="fixture", dims=[count, width], store=7, variant=0,
                     offset=offset, size=len(payload))
        source = b"\0" * offset + payload
        reference, _ = decode_q8g64(io.BytesIO(source), entry)

        class TrackedStream(io.BytesIO):
            def __init__(self, data):
                super().__init__(data)
                self.reads = []

            def read(self, length=-1):
                self.reads.append((self.tell(), length))
                return super().read(length)

        stream = TrackedStream(source)
        result = decode_rows(stream, entry, 1, 2)
        np.testing.assert_array_equal(result, reference[1:3])
        self.assertEqual(result.dtype, np.dtype("float32"))
        self.assertEqual(stream.reads, [(offset + row_bytes, 2 * row_bytes)])
        with self.assertRaisesRegex(ValueError, "truncated"):
            decode_rows(io.BytesIO(source[:offset + 3 * row_bytes - 1]), entry, 1, 2)
        # Unknown output encoding must fail at metadata validation, before reads.
        with self.assertRaisesRegex(ValueError, "store16.*refused"):
            geometry(dict(name="lm_head.weight", store=16, variant=0,
                          dims=[248320, 2560], offset=64845765504, size=317849600))

    def test_ht_second_group_plan_and_decode_use_only_bound_sideplanes(self):
        # Reuse the independently qualified synthetic fixture; no model files.
        from test_hgn_ht_slice import fixture
        import hashlib
        source, entry, suh, svh = fixture(256, 256)
        entry["name"], suh["name"], svh["name"] = "lm_head.weight", "lm_head.suh", "lm_head.svh"
        planes = dict(suh=suh, svh=svh)
        plan = tensor_plan(entry, 128, 128, MAX_TILE_BYTES, 0, planes)
        self.assertEqual(len(plan["tiles"]), 1)
        tile = plan["tiles"][0]
        self.assertLessEqual(tile["workspace_bytes"], 64 * 1024**2)
        self.assertEqual(tile["decoded_bytes"], 128 * 256 * 4)
        ranges = []
        for item in tile["source_ranges"]:
            source.seek(item["offset"])
            ranges.append((item["offset"], source.read(item["bytes"])))
        value, receipt = decode_tile(WindowStream(ranges), plan, tile)
        self.assertEqual(hashlib.sha256(value.tobytes()).hexdigest(),
                         "b62700464503e25b8ca8bc18dfe6a12bfd8308672e550a620dcdfd0030561301")
        self.assertEqual(receipt["decoded_shape"], [128, 256])
        self.assertEqual(sorted(source.reads), sorted([
            (entry["offset"] + 16384, 16384), (suh["offset"], 512), (svh["offset"] + 256, 256)]))
        with self.assertRaisesRegex(ValueError, "aligned complete"):
            tensor_plan(entry, 1, 128, MAX_TILE_BYTES, 0, planes)


if __name__ == "__main__":
    unittest.main()
