"""Create a separate, version-locked selected-H DPP code object, offline only.

The replacement instruction fixture is assembled and reviewed separately by
the hardware-owning coordinator. This module never invokes an assembler, loads
a GPU module, changes the original binary, or installs a serving hook.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
from typing import Sequence


ORIGINAL_SHA256 = "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
ORIGINAL_BYTES = 17_704_408
H_FILE_OFFSET = 0x2D6800
H_VA = 0x2D7800
H_BYTES = 2360
H_SHA256 = "e1c4867af30e56b1809ddfc407f679e45f034ab135ec1fa3801eecc58f765269"
KD_FILE_OFFSET = 0x1FA640
KD_BYTES = 64
KD_SHA256 = "74caae65394734af5d319d6aab6b33b905644d7c1815f152b06c22868e2f498b"
FIXTURE_SHA256 = "602cde275166ac1097e6b5cc27ea7e2e3efb6ebeb83d109f4c44288fe0845540"
SYMBOL = "_ZN7halogen12_GLOBAL__N_16k_lq8wILi4ELi16ELi1EEEvPKhPKtPtll"


@dataclass(frozen=True)
class Exchange:
    va: int
    destination: int
    source: int
    address: int
    xor_mask: int

    @property
    def file_offset(self) -> int:
        return H_FILE_OFFSET + self.va - H_VA

    @property
    def original(self) -> bytes:
        # Exact gfx1151 DS_BPERMUTE_B32 encoding recovered from the sealed H.
        return struct.pack("<II", 0xDACC0000,
                           (self.destination << 24) | (self.source << 8)
                           | self.address)


# Original instruction order, including its interleaved butterfly stages.
EXCHANGES = (
    Exchange(0x2D7F28, 2, 21, 1, 8),
    Exchange(0x2D7F40, 4, 19, 1, 8),
    Exchange(0x2D7F4C, 3, 20, 1, 8),
    Exchange(0x2D7F54, 1, 16, 1, 8),
    Exchange(0x2D7F64, 6, 2, 5, 4),
    Exchange(0x2D7F74, 8, 4, 5, 4),
    Exchange(0x2D7F88, 7, 3, 5, 4),
    Exchange(0x2D7F9C, 8, 6, 11, 2),
    Exchange(0x2D7FC8, 5, 1, 5, 4),
    Exchange(0x2D7FE4, 1, 2, 11, 2),
    Exchange(0x2D7FF4, 5, 3, 11, 2),
    Exchange(0x2D7FFC, 11, 7, 11, 2),
    Exchange(0x2D8008, 6, 4, 12, 1),
    Exchange(0x2D8020, 2, 1, 12, 1),
    Exchange(0x2D8028, 7, 5, 12, 1),
    Exchange(0x2D8030, 3, 0, 12, 1),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_original(data: bytes) -> None:
    if len(data) != ORIGINAL_BYTES or sha256(data) != ORIGINAL_SHA256:
        raise ValueError("Input is not the sealed original gfx1151 code object")
    if sha256(data[H_FILE_OFFSET:H_FILE_OFFSET + H_BYTES]) != H_SHA256:
        raise ValueError("Selected H function seal differs")
    if sha256(data[KD_FILE_OFFSET:KD_FILE_OFFSET + KD_BYTES]) != KD_SHA256:
        raise ValueError("Selected H kernel descriptor seal differs")


def validate_fixture(fixture: bytes, expected_sha256: str) -> tuple[bytes, ...]:
    """Validate the root-pinned, sixteen-instruction, raw assembly fixture.

    Exact encoding validation is deliberately required in addition to its hash.
    No arbitrary eight-byte replacement is accepted. The gfx1151 DPP encoding
    constants are pinned after coordinator assembly and disassembly review.
    """
    if (len(expected_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_sha256)):
        raise ValueError("Fixture SHA256 must be sixty-four lowercase hex digits")
    if expected_sha256 != FIXTURE_SHA256:
        raise ValueError("Fixture SHA256 differs from the reviewed gfx1151 assembly")
    if len(fixture) != 8 * len(EXCHANGES):
        raise ValueError("Fixture must contain exactly sixteen eight-byte instructions")
    if sha256(fixture) != expected_sha256:
        raise ValueError("Fixture does not match the coordinator-pinned SHA256")
    instructions = tuple(fixture[i:i + 8] for i in range(0, len(fixture), 8))
    for exchange, instruction in zip(EXCHANGES, instructions):
        validate_dpp_instruction(exchange, instruction)
    return instructions


def validate_dpp_instruction(exchange: Exchange, instruction: bytes) -> None:
    if len(instruction) != 8:
        raise ValueError("DPP instruction must be eight bytes")
    first, second = struct.unpack("<II", instruction)
    # Coordinator clang7.2 assembly and gfx1151 objdump agree on these words:
    # V_MOV_B32_DPP, source escape0xfa; full row/bank masks, bound_ctrl1,
    # row_xmask controls0x161/162/164/168. No arithmetic modifier or src_neg.
    expected_first = 0x7E0002FA | (exchange.destination << 17)
    expected_second = 0xFF090000 | (exchange.xor_mask << 8) | 0x6000 | exchange.source
    if first != expected_first or second != expected_second:
        raise ValueError(f"Fixture DPP operand/control mismatch for VA {exchange.va:#x}")


def replace_exchanges(data: bytes, replacements: Sequence[bytes]) -> bytes:
    """Pure bounded byte replacement; caller must first verify source/fixture."""
    if len(replacements) != len(EXCHANGES):
        raise ValueError("Exactly sixteen replacement instructions are required")
    candidate = bytearray(data)
    for exchange, instruction in zip(EXCHANGES, replacements):
        offset = exchange.file_offset
        if len(instruction) != 8:
            raise ValueError("Replacement instruction is not eight bytes")
        if data[offset:offset + 8] != exchange.original:
            raise ValueError(f"Original instruction differs at VA {exchange.va:#x}")
        if instruction == exchange.original:
            raise ValueError("Replacement must differ from the original instruction")
        candidate[offset:offset + 8] = instruction
    result = bytes(candidate)
    prove_changed_ranges(data, result)
    return result


def prove_changed_ranges(original: bytes, candidate: bytes) -> None:
    """Prove layout and every byte outside the sixteen slots stayed unchanged."""
    if len(candidate) != len(original):
        raise ValueError("Code object length changed")
    cursor = 0
    for exchange in EXCHANGES:
        offset = exchange.file_offset
        if original[cursor:offset] != candidate[cursor:offset]:
            raise ValueError("Candidate changed bytes outside exchange slots")
        cursor = offset + 8
    if original[cursor:] != candidate[cursor:]:
        raise ValueError("Candidate changed bytes outside exchange slots")


def make_candidate(original: bytes, fixture: bytes, fixture_sha256: str) -> bytes:
    verify_original(original)
    replacements = validate_fixture(fixture, fixture_sha256)
    return replace_exchanges(original, replacements)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-codeobject", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--fixture-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    paths = [args.input_codeobject.resolve(), args.fixture.resolve(),
             args.output.resolve(), args.receipt.resolve()]
    if len(set(paths)) != 4:
        raise ValueError("Input, fixture, candidate and receipt must be distinct files")
    if args.output.exists() or args.receipt.exists():
        raise FileExistsError("Candidate and receipt outputs must not already exist")
    original = args.input_codeobject.read_bytes()
    fixture = args.fixture.read_bytes()
    candidate = make_candidate(original, fixture, args.fixture_sha256)
    # Exclusive creation prevents a concurrently created file from being replaced.
    with args.output.open("xb") as output:
        output.write(candidate)
    receipt = {
        "schema": "halogen-selected-h-dpp-patch-v1",
        "status": "offline-candidate-only",
        "hardware_qualified": False,
        "serving_installed": False,
        "symbol": SYMBOL,
        "input": str(paths[0]),
        "original_sha256": sha256(original),
        "fixture": str(paths[1]),
        "fixture_sha256": sha256(fixture),
        "candidate": str(paths[2]),
        "candidate_sha256": sha256(candidate),
        "bytes": len(candidate),
        "h_original_sha256": H_SHA256,
        "h_candidate_sha256": sha256(candidate[H_FILE_OFFSET:H_FILE_OFFSET + H_BYTES]),
        "descriptor_sha256": KD_SHA256,
        "changed_ranges": [
            {"va": hex(e.va), "file_offset": hex(e.file_offset), "bytes": 8,
             "original_hex": e.original.hex(),
             "replacement_hex": fixture[8 * i:8 * (i + 1)].hex(),
             "destination": e.destination, "source": e.source,
             "row_xmask": e.xor_mask}
            for i, e in enumerate(EXCHANGES)
        ],
        "all_other_bytes_unchanged": True,
        "waitcnt_and_delay_unchanged": True,
        "actual_prefill_tps": None,
        "actual_decode_tps": None,
        "native_acceptance": None,
    }
    with args.receipt.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(receipt, output, indent=2)
        output.write("\n")
    # Verify the input file remained immutable during candidate creation.
    if args.input_codeobject.read_bytes() != original:
        raise RuntimeError("Original code object changed concurrently")
    print(json.dumps({"candidate_sha256": receipt["candidate_sha256"],
                      "receipt": str(paths[3]), "hardware_qualified": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
