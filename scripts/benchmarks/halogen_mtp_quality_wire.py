"""CPU-only packet validation/publication for the disabled native quality shim.

Consumes an explicitly supplied complete-MLP BF16 output. It runs no model,
imports no numerical/native library, and never generates a candidate itself.
"""
import argparse
import hashlib
import hmac
import math
import os
from pathlib import Path
import stat
import struct


HEADER = struct.Struct("<8sIIiiiI16s32s")
INPUT_BYTES = OUTPUT_BYTES = 5120
BODY_BYTES = 10320
REQUEST_BYTES = HEADER.size + BODY_BYTES
RESPONSE_BYTES = HEADER.size + OUTPUT_BYTES + 32
MAX_CALLS = 4


def _finite_bf16(payload):
    if len(payload) != OUTPUT_BYTES:
        raise ValueError("requires exactly 2560 BF16 words")
    if any((value & 0x7f80) == 0x7f80 for (value,) in struct.iter_unpack("<H", payload)):
        raise ValueError("nonfinite BF16 value")


def decode_request(packet):
    if len(packet) != REQUEST_BYTES:
        raise ValueError("request size differs from the fixed contract")
    magic, version, size, sequence, position, slot, reserved, nonce, digest = HEADER.unpack_from(packet)
    if (magic != b"HGNMLPQ1" or version != 1 or size != BODY_BYTES or reserved
            or not 0 <= sequence < MAX_CALLS or position < 0 or slot < 0):
        raise ValueError("invalid request header")
    body = packet[HEADER.size:]
    if not hmac.compare_digest(hashlib.sha256(packet[:48] + body).digest(), digest):
        raise ValueError("request binding digest differs")
    hidden, original = body[:INPUT_BYTES], body[-OUTPUT_BYTES:]
    _finite_bf16(hidden)
    _finite_bf16(original)
    ids = struct.unpack_from("<10i", body, INPUT_BYTES)
    coefficients = struct.unpack_from("<10f", body, INPUT_BYTES + 40)
    if len(set(ids)) != 10 or any(not 0 <= index < 512 for index in ids):
        raise ValueError("requires ten distinct native expert IDs")
    if any(not math.isfinite(value) or value < 0 for value in coefficients) or sum(coefficients) <= 0:
        raise ValueError("invalid native coefficients")
    return dict(sequence=sequence, position=position, slot=slot, nonce=nonce,
                digest=digest, hidden=hidden, expert_ids=ids,
                coefficients=coefficients, original_output=original)


def encode_response(request, candidate):
    fields = decode_request(request)
    _finite_bf16(candidate)
    header = HEADER.pack(b"HGNMLPR1", 1, OUTPUT_BYTES, fields["sequence"],
                         fields["position"], fields["slot"], 0,
                         fields["nonce"], fields["digest"])
    payload = header + candidate
    return payload + hashlib.sha256(payload).digest()


def decode_response(request, response):
    fields = decode_request(request)
    if len(response) != RESPONSE_BYTES:
        raise ValueError("response size differs from the fixed contract")
    expected = HEADER.pack(b"HGNMLPR1", 1, OUTPUT_BYTES, fields["sequence"],
                           fields["position"], fields["slot"], 0,
                           fields["nonce"], fields["digest"])
    if not hmac.compare_digest(response[:HEADER.size], expected):
        raise ValueError("response belongs to a different request")
    if not hmac.compare_digest(hashlib.sha256(response[:-32]).digest(), response[-32:]):
        raise ValueError("response digest differs")
    candidate = response[HEADER.size:-32]
    _finite_bf16(candidate)
    return candidate


def bounded_read(path, expected_bytes):
    path = Path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size != expected_bytes:
        raise ValueError("requires one regular exact-sized input file")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("input identity changed while opening")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read(expected_bytes + 1)
        after = os.fstat(descriptor)
        identity = lambda row: (row.st_dev, row.st_ino, row.st_size, row.st_mtime_ns, row.st_ctime_ns)
        if len(payload) != expected_bytes or identity(opened) != identity(after):
            raise ValueError("input changed during bounded read")
        return payload
    finally:
        os.close(descriptor)


def publish_response(request_path, candidate_path):
    request_path = Path(request_path)
    request = bounded_read(request_path, REQUEST_BYTES)
    fields = decode_request(request)
    expected_name = f"{fields['sequence']:03d}-request.bin"
    if request_path.name != expected_name:
        raise ValueError("request filename differs from its sequence")
    response = encode_response(request, bounded_read(candidate_path, OUTPUT_BYTES))
    output = request_path.with_name(f"{fields['sequence']:03d}-response.bin")
    temporary = output.with_name(output.name + ".partial-" + os.urandom(8).hex())
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(response)
            stream.flush()
            os.fsync(descriptor)
        # A hard-link publication is atomic and refuses an existing response.
        # If the shared filesystem lacks hard links, fail without a final file.
        os.link(temporary, output)
    finally:
        os.close(descriptor)
        temporary.unlink()
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--candidate-output-u16", type=Path, required=True)
    options = parser.parse_args()
    print(publish_response(options.request, options.candidate_output_u16))
