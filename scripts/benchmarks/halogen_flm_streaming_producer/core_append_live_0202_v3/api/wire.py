"""HDO2 exact-prefix packets. Pure codec; no engine, file or socket access."""
import re
import struct

HEADER = struct.Struct('<4sHHIIQII16sQQ32sQiI')
HEADER_BYTES = 112
MAX_PROPOSALS = 3
MAX_BYTES = HEADER_BYTES + 4 * MAX_PROPOSALS
BEGIN, AUTHORITY, READY, CANCEL, END = range(1, 6)
HEAD_ROWS = 248320
SHARED_IDS = 248070
MAX_CONTEXT = 262144
KEY_FIELDS = ('request_id', 'n_prompt', 'request_epoch', 'nonce', 'generated_count',
              'prefix_sha256', 'current_token')


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def hexadecimal(value, digits):
    return type(value) is str and re.fullmatch('[0-9a-f]{' + str(digits) + '}', value) is not None


def key(value):
    if type(value) is not dict or any(name not in value for name in KEY_FIELDS):
        raise ValueError('Complete HDO2 prefix key required')
    result = {name: value[name] for name in KEY_FIELDS}
    p, g = result['n_prompt'], result['generated_count']
    if (not integer(result['request_id'], 0, (1 << 63) - 1)
            or not integer(p, 1, MAX_CONTEXT) or not integer(g, 0, MAX_CONTEXT - p)
            or not hexadecimal(result['request_epoch'], 32)
            or result['request_epoch'] == '0' * 32
            or not integer(result['nonce'], 1, (1 << 64) - 1)
            or not hexadecimal(result['prefix_sha256'], 64)
            or not integer(result['current_token'], -1 if g == 0 else 0,
                           -1 if g == 0 else HEAD_ROWS - 1)):
        raise ValueError('Invalid HDO2 exact-prefix key')
    return result


def encode(kind, binding, sequence, token_ids=()):
    binding = key(binding)
    if not integer(kind, BEGIN, END) or not integer(sequence, 1, (1 << 64) - 1):
        raise ValueError('Invalid HDO2 kind or sequence')
    ids = tuple(token_ids)
    if kind == READY:
        if (binding['generated_count'] < 1 or not 1 <= len(ids) <= MAX_PROPOSALS
                or any(not integer(i, 0, SHARED_IDS - 1) for i in ids)):
            raise ValueError('READY contains one through three shared IDs')
    elif kind == AUTHORITY:
        if (binding['generated_count'] < 1 or len(ids) != 1
                or not integer(ids[0], 0, HEAD_ROWS - 1) or ids[0] != binding['current_token']):
            raise ValueError('AUTHORITY contains exactly the published current T')
    elif ids:
        raise ValueError('Control packet cannot contain proposal IDs')
    if kind == BEGIN and (binding['generated_count'] != 0 or sequence != 1):
        raise ValueError('BEGIN is sequence one at generated count zero')
    payload = struct.pack('<' + str(len(ids)) + 'i', *ids)
    return HEADER.pack(b'HDO2', 2, HEADER_BYTES, HEADER_BYTES + len(payload), kind,
                       binding['request_id'], binding['n_prompt'], 0,
                       bytes.fromhex(binding['request_epoch']), binding['nonce'],
                       binding['generated_count'], bytes.fromhex(binding['prefix_sha256']),
                       sequence, binding['current_token'], len(ids)) + payload


def decode(packet):
    if type(packet) is not bytes or not HEADER_BYTES <= len(packet) <= MAX_BYTES:
        raise ValueError('Bounded complete HDO2 datagram required')
    row = HEADER.unpack_from(packet)
    magic, version, header, total, kind, request, p, flags, epoch, nonce, g, sha, sequence, current, count = row
    if (magic != b'HDO2' or version != 2 or header != HEADER_BYTES or total != len(packet)
            or flags != 0 or count > MAX_PROPOSALS or total != HEADER_BYTES + 4 * count):
        raise ValueError('HDO2 framing differs')
    binding = dict(request_id=request, n_prompt=p, request_epoch=epoch.hex(), nonce=nonce,
                   generated_count=g, prefix_sha256=sha.hex(), current_token=current)
    ids = struct.unpack_from('<' + str(count) + 'i', packet, HEADER_BYTES)
    # Reuse all semantic validation, including current and shared-ID bounds.
    if encode(kind, binding, sequence, ids) != packet:
        raise ValueError('HDO2 packet is not canonical')
    return dict(kind=kind, binding=binding, sequence=sequence, token_ids=ids)
