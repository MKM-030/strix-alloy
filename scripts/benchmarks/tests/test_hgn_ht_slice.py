"""Small synthetic fixtures; no checkpoint, native library or accelerator."""
import hashlib
import importlib.util
import io
from pathlib import Path
import unittest

import numpy as np


READER = Path(__file__).resolve().parents[1] / "hgn_ht_slice.py"
# Generated with decoder-only AST functions from pinned hgnht.py 6abedcfd...
# and hgnenc.py f9612777...; no ctypes/encoder imports or real weights.
REFERENCE_SHA256 = {
    128: "7f46c34ee6b6de61d3acfe4bcc90218ecc87303867efb12062183c18fc283d8c",
    256: "f6c11360db03f4acc645b6e417773d726c3365df1fdd690d346963e4b90435b8",
}


class RecordingStream(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.reads = []

    def read(self, length=-1):
        self.reads.append((self.tell(), length))
        return super().read(length)


def fixture(output_rows=256, width=128):
    # Direct disk words, independent of the production unpacker. Random nibbles
    # exercise the last-three cyclic history and every disk tile dimension.
    codes = np.random.default_rng(901 + output_rows).integers(
        0, 16, size=(output_rows // 128, width // 16, 8, 32, 8), dtype=np.uint8
    )
    words = np.bitwise_or.reduce(
        codes.astype(np.uint32) << np.arange(28, -1, -4, dtype=np.uint32), axis=-1
    )
    packed = words.astype("<u4").tobytes()
    signs = np.where(np.arange(width) % 3 == 0, -1, 1).astype("<f2")
    scales = (
        np.where(np.arange(output_rows) % 5 == 0, -1, 1)
        * (1 + np.arange(output_rows) % 7) / 8
    ).astype("<f2")
    scales[::31] = 0
    weight_offset = 512
    signs_offset = weight_offset + len(packed) + 64
    scales_offset = signs_offset + signs.nbytes + 64
    data = bytearray(b"\xff" * (scales_offset + scales.nbytes))
    data[weight_offset:weight_offset + len(packed)] = packed
    data[signs_offset:signs_offset + signs.nbytes] = signs.tobytes()
    data[scales_offset:scales_offset + scales.nbytes] = scales.tobytes()
    entry = dict(name="fixture.weight", store=16, variant=0x1208, rank=2,
                 dims=[output_rows, width], offset=weight_offset, size=len(packed))
    suh = dict(name="fixture.suh", store=2, variant=0, rank=1,
               dims=[width], offset=signs_offset, size=signs.nbytes)
    svh = dict(name="fixture.svh", store=2, variant=0, rank=1,
               dims=[output_rows], offset=scales_offset, size=scales.nbytes)
    return RecordingStream(data), entry, suh, svh


class HtSliceTests(unittest.TestCase):
    def reader(self):
        self.assertTrue(READER.is_file(), "bounded HT reader is not implemented")
        spec = importlib.util.spec_from_file_location("ht_slice_under_test", READER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_128_and_256_rows_match_pinned_decoder(self):
        reader = self.reader()
        for count in (128, 256):
            with self.subTest(rows=count):
                stream, entry, suh, svh = fixture(count)
                decoded, receipt = reader.decode_rows(stream, entry, 0, count, suh, svh)
                self.assertEqual(decoded.shape, (count, 128))
                self.assertEqual(decoded.dtype, np.dtype("<f4"))
                self.assertTrue(np.isfinite(decoded).all())
                expected_hash = REFERENCE_SHA256[count]
                self.assertEqual(hashlib.sha256(decoded.tobytes()).hexdigest(), expected_hash)
                self.assertEqual(receipt["decoded_sha256"], expected_hash)
                self.assertEqual(receipt["source_bytes_read"], count * 128 // 2 + 256 + count * 2)
                self.assertEqual(receipt["decoded_bytes"], count * 128 * 4)
                for record in receipt["source_ranges"]:
                    source = stream.getvalue()[record["offset"]:record["offset"] + record["bytes"]]
                    self.assertEqual(record["sha256"], hashlib.sha256(source).hexdigest())

    def test_second_group_reads_only_its_packed_rows_and_scales(self):
        reader = self.reader()
        stream, entry, suh, svh = fixture()
        full, _ = reader.decode_rows(stream, entry, 0, 256, suh, svh)
        self.assertEqual(hashlib.sha256(full.tobytes()).hexdigest(), REFERENCE_SHA256[256])
        stream.reads.clear()
        decoded, receipt = reader.decode_rows(stream, entry, 128, 128, suh, svh)
        np.testing.assert_array_equal(decoded, full[128:])
        permitted = [
            (entry["offset"] + 128 * 128 // 2, 128 * 128 // 2),
            (suh["offset"], 128 * 2),
            (svh["offset"] + 128 * 2, 128 * 2),
        ]
        self.assertEqual(sorted(stream.reads), sorted(permitted))
        self.assertEqual(receipt["source_bytes_read"], sum(length for _, length in permitted))

    def test_width_256_and_second_group_match_pinned_decoder(self):
        # These golden hashes were checked directly against the pinned decoder
        # AST with WinML NumPy, exercising two input-H128 blocks and K/16 tiles.
        reader = self.reader()
        stream, entry, suh, svh = fixture(256, 256)
        decoded, receipt = reader.decode_rows(stream, entry, 0, 256, suh, svh)
        self.assertEqual(decoded.shape, (256, 256))
        self.assertEqual(receipt["decoded_sha256"],
                         "10c7f0fc75dceac1bece11013ef09b766866d491364b74555664df613e805c0f")
        stream.reads.clear()
        second, receipt = reader.decode_rows(stream, entry, 128, 128, suh, svh)
        self.assertEqual(hashlib.sha256(second.tobytes()).hexdigest(),
                         "b62700464503e25b8ca8bc18dfe6a12bfd8308672e550a620dcdfd0030561301")
        np.testing.assert_array_equal(second, decoded[128:])
        self.assertEqual(sorted(stream.reads), sorted([
            (entry["offset"] + 16384, 16384), (suh["offset"], 512),
            (svh["offset"] + 256, 256),
        ]))
        self.assertEqual(receipt["source_bytes_read"], 17152)

    def test_invalid_matrix_metadata_is_rejected_before_reads(self):
        reader = self.reader()
        mutations = [dict(store=5), dict(variant=0), dict(rank=3),
                     dict(dims=[127, 128]), dict(dims=[256, 129]),
                     dict(size=1), dict(offset=-1), dict(dims=[True, 128])]
        for changes in mutations:
            with self.subTest(changes=changes):
                stream, entry, suh, svh = fixture()
                entry.update(changes)
                with self.assertRaises(ValueError):
                    reader.decode_rows(stream, entry, 0, 128, suh, svh)
                self.assertEqual(stream.reads, [])

    def test_unaligned_or_out_of_bounds_rows_are_rejected_before_reads(self):
        reader = self.reader()
        for start, count in ((1, 128), (0, 127), (128, 256), (-128, 128),
                             (0, 0), (False, 128), (0, True)):
            with self.subTest(start=start, count=count):
                stream, entry, suh, svh = fixture()
                with self.assertRaises(ValueError):
                    reader.decode_rows(stream, entry, start, count, suh, svh)
                self.assertEqual(stream.reads, [])

    def test_oversized_decoded_slice_is_rejected_before_reads(self):
        reader = self.reader()
        stream, entry, suh, svh = fixture()
        entry.update(dims=[262144, 128], size=262144 * 128 // 2)
        suh["offset"] = entry["offset"] + entry["size"]
        svh.update(dims=[262144], size=262144 * 2, offset=suh["offset"] + suh["size"])
        with self.assertRaises(ValueError):
            reader.decode_rows(stream, entry, 0, 262144, suh, svh)
        self.assertEqual(stream.reads, [])

    def test_invalid_side_plane_metadata_is_rejected_before_reads(self):
        reader = self.reader()
        mutations = [dict(store=0), dict(variant=1), dict(rank=2),
                     dict(dims=[256]), dict(size=1), dict(name="other.suh")]
        for changes in mutations:
            with self.subTest(changes=changes):
                stream, entry, suh, svh = fixture()
                suh.update(changes)
                with self.assertRaises(ValueError):
                    reader.decode_rows(stream, entry, 0, 128, suh, svh)
                self.assertEqual(stream.reads, [])

    def test_non_sign_or_nonfinite_side_planes_are_rejected(self):
        reader = self.reader()
        for plane, value in (("suh", 0), ("suh", np.nan), ("svh", np.inf)):
            with self.subTest(plane=plane, value=value):
                stream, entry, suh, svh = fixture()
                data = bytearray(stream.getvalue())
                offset = (suh if plane == "suh" else svh)["offset"]
                data[offset:offset + 2] = np.array([value], dtype="<f2").tobytes()
                with self.assertRaises(ValueError):
                    reader.decode_rows(RecordingStream(data), entry, 0, 128, suh, svh)

    def test_truncated_selected_range_is_rejected(self):
        reader = self.reader()
        stream, entry, suh, svh = fixture()
        with self.assertRaises(ValueError):
            reader.decode_rows(RecordingStream(stream.getvalue()[:-1]), entry, 128, 128, suh, svh)


if __name__ == "__main__":
    unittest.main()
