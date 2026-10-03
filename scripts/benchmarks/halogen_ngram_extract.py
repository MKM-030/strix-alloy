"""Extract the reviewed w4b lookup tensor into one standalone HGN v2 file.

No model executes. A bounded_hash.py receipt from the same host/filesystem is
required: its reviewed SHA256 and full file identity replace another 120 GB
source hash. Payload and complete output SHA256 are computed while copying.
XOR32 is also checked when NumPy is available; --verify-xor requires it for a
large table. The CLI accepts only the pinned production shape. Importing the
module permits a smaller explicit ExtractionSpec for CPU fixtures.

Layout/checksum reference: https://github.com/jtsylve/hgn-spec/blob/main/CONTAINER.md
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct

HEADER_BYTES, ENTRY_BYTES, DATA_OFFSET = 104, 160, 320
TENSOR_NAME = 'layers.1.ple.ngram_embedding.weight'
SOURCE_SHA256 = '9c116bbc01f77b7a15464c1a124eb3325b286089b8a2a6f2856c9b246a235bd6'
SOURCE_BYTES = 124068083904
TABLE_DIMS = (128, 2500012, 160)
TABLE_BYTES = 51200245764
MAX_CHUNK_BYTES = 8 * 1024**2


@dataclass(frozen=True)
class ExtractionSpec:
    source_sha256: str = SOURCE_SHA256
    source_bytes: int = SOURCE_BYTES
    tensor_dims: tuple = TABLE_DIMS
    payload_bytes: int = TABLE_BYTES
    tensor_count: int = 1198


def align64(value):
    return (value + 63) // 64 * 64


def file_identity(value):
    return dict(size=value.st_size, device=value.st_dev, inode=value.st_ino,
                mtime_ns=value.st_mtime_ns, ctime_ns=value.st_ctime_ns)


def _safe_path(value):
    if '..' in Path(value).parts:
        raise ValueError('Parent traversal paths are refused')
    path = Path(os.path.abspath(value))
    for node in reversed((path, *path.parents)):
        try:
            info = node.lstat()
        except FileNotFoundError:
            if node != path:
                raise ValueError('Parent directory does not exist: ' + str(node))
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Symlink/reparse paths are refused: ' + str(node))
    return path


def _read_exact(stream, length):
    data = stream.read(length)
    if len(data) != length:
        raise ValueError('Truncated HGN read')
    return data


def _path_stat(path):
    # Python 3.12 Windows stat/fstat differ in ctime interpretation. Receipts
    # from bounded_hash.py use fstat, so use fstat for every identity comparison.
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    with os.fdopen(os.open(path, flags), 'rb', buffering=0) as stream:
        return os.fstat(stream.fileno())


def _inspect(stream, expected):
    stream.seek(0)
    header = _read_exact(stream, HEADER_BYTES)
    magic, version, count, table, data, size = struct.unpack_from('<IIQQQQ', header)
    if (magic != 0x314e4748 or version != 2 or size != expected.source_bytes or
            not 1 <= count <= 10000 or count != expected.tensor_count or
            table != HEADER_BYTES or data % 64 or table + count * ENTRY_BYTES > data or
            data > size):
        raise ValueError('Invalid or unexpected HGN v2 header')
    found = None
    stream.seek(table)
    for _ in range(count):
        entry = _read_exact(stream, ENTRY_BYTES)
        name_bytes = entry[:96]
        if b'\0' not in name_bytes:
            raise ValueError('HGN tensor name is not terminated')
        try:
            name = name_bytes.split(b'\0', 1)[0].decode('ascii')
        except UnicodeDecodeError as exc:
            raise ValueError('Invalid HGN tensor name') from exc
        storage, rank = struct.unpack_from('<II', entry, 96)
        dimensions = struct.unpack_from('<4q', entry, 104)
        offset, length, checksum, variant = struct.unpack_from('<QQII', entry, 136)
        if (not name or not 1 <= rank <= 4 or any(v <= 0 for v in dimensions[:rank]) or
                offset % 64 or offset < data or not length or length > size - offset):
            raise ValueError('Invalid HGN tensor extent or dimensions: ' + name)
        if name != TENSOR_NAME:
            continue
        if found is not None:
            raise ValueError('Duplicate ngram tensor')
        if (storage != 10 or rank != 3 or dimensions[:rank] != expected.tensor_dims or
                variant != 0 or length != expected.payload_bytes or
                math.prod(dimensions[:rank]) + 4 != length):
            raise ValueError('Unexpected ngram storage, shape, variant or size')
        found = dict(entry=entry, offset=offset, size=length, xor32=checksum,
                     storage=storage, dimensions=list(dimensions[:rank]), variant=variant)
    if found is None:
        raise ValueError('Missing ngram tensor')
    return header, found


def _xor_backend(verify_xor, payload_bytes):
    if verify_xor is False:
        return None, False
    try:
        import numpy
    except ImportError:
        if payload_bytes <= 64 * 1024**2:
            return None, True
        if verify_xor:
            raise ValueError('Large XOR32 verification requires an existing NumPy runtime')
        return None, False
    return numpy, True


def _xor_block(data, numpy):
    padded = data + b'\0' * (-len(data) % 4)
    if numpy is not None:
        return int(numpy.bitwise_xor.reduce(numpy.frombuffer(padded, dtype='<u4'),
                                           initial=numpy.uint32(0)))
    result = 0
    for word, in struct.iter_unpack('<I', padded):
        result ^= word
    return result


def _remove_created(path, identity):
    try:
        current = path.lstat()
        if (current.st_dev, current.st_ino) == identity:
            path.unlink()
    except FileNotFoundError:
        pass


def extract_ngram(source, destination, *, source_receipt, expected=ExtractionSpec(),
                  chunk_bytes=MAX_CHUNK_BYTES, verify_xor=None, receipt_path=None):
    if not 4 <= chunk_bytes <= MAX_CHUNK_BYTES or chunk_bytes % 4:
        raise ValueError('Chunk size must be divisible by four and at most 8 MiB')
    source, destination = _safe_path(source), _safe_path(destination)
    receipt_path = _safe_path(receipt_path or destination.with_suffix(destination.suffix + '.receipt.json'))
    if source == destination or receipt_path in (source, destination):
        raise ValueError('Source, output and receipt paths must differ')
    if destination.exists() or receipt_path.exists():
        raise FileExistsError('Output or receipt already exists')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    created = []
    try:
        with os.fdopen(os.open(source, flags), 'rb', buffering=0) as input_stream:
            info = os.fstat(input_stream.fileno())
            before = file_identity(info)
            if not stat.S_ISREG(info.st_mode) or before['size'] != expected.source_bytes:
                raise ValueError('Unexpected source size or file type')
            if (not isinstance(source_receipt, dict) or
                    source_receipt.get('sha256') != expected.source_sha256 or
                    source_receipt.get('identity') != before):
                raise ValueError('Reviewed source receipt does not match current file identity')
            header, tensor = _inspect(input_stream, expected)
            numpy, do_xor = _xor_backend(verify_xor, tensor['size'])
            end = align64(DATA_OFFSET + tensor['size'])
            entry = bytearray(tensor['entry'])
            struct.pack_into('<Q', entry, 136, DATA_OFFSET)
            output_header = struct.pack('<IIQQQQ', 0x314e4748, 2, 1, HEADER_BYTES,
                                        DATA_OFFSET, end) + header[40:104]
            output_sha, payload_sha = hashlib.sha256(), hashlib.sha256()
            output_flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                            getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0))
            with os.fdopen(os.open(destination, output_flags, 0o600), 'wb', buffering=0) as output:
                owned = os.fstat(output.fileno())
                created.append((destination, (owned.st_dev, owned.st_ino)))
                def write(data):
                    output_sha.update(data)
                    view = memoryview(data)
                    while view:
                        written = output.write(view)
                        if not written:
                            raise OSError('Incomplete HGN write')
                        view = view[written:]
                write(output_header)
                write(entry)
                write(b'\0' * (DATA_OFFSET - HEADER_BYTES - ENTRY_BYTES))
                input_stream.seek(tensor['offset'])
                position, checksum = 0, 0
                while position < tensor['size']:
                    block = _read_exact(input_stream, min(chunk_bytes, tensor['size'] - position))
                    write(block)
                    payload_sha.update(block)
                    if do_xor:
                        checksum ^= _xor_block(block, numpy)
                    if hasattr(os, 'posix_fadvise'):
                        os.posix_fadvise(input_stream.fileno(), tensor['offset'] + position,
                                         len(block), os.POSIX_FADV_DONTNEED)
                    position += len(block)
                write(b'\0' * (end - DATA_OFFSET - tensor['size']))
                if do_xor and checksum != tensor['xor32']:
                    raise ValueError('Ngram payload XOR32 mismatch')
                _safe_path(source)
                if (file_identity(os.fstat(input_stream.fileno())) != before or
                        file_identity(_path_stat(source)) != before):
                    raise ValueError('Source changed during ngram extraction')
                if output.tell() != end or os.fstat(output.fileno()).st_size != end:
                    raise ValueError('Incomplete standalone HGN output')
                output.flush()
                os.fsync(output.fileno())
                written_identity = file_identity(os.fstat(output.fileno()))
            _safe_path(destination)
            output_info = _path_stat(destination)
            if file_identity(output_info) != written_identity:
                raise ValueError('Output changed before receipt publication')
            result = dict(schema=1,
                source=dict(path=str(source), sha256=expected.source_sha256, identity=before,
                            header_sha256=hashlib.sha256(header).hexdigest()),
                tensor=dict(name=TENSOR_NAME, storage=tensor['storage'], dimensions=tensor['dimensions'],
                            variant=tensor['variant'], source_offset=tensor['offset'], bytes=position,
                            sha256=payload_sha.hexdigest(), xor32=f'{tensor["xor32"]:08x}',
                            xor32_verified=do_xor),
                output=dict(path=str(destination), bytes=end, sha256=output_sha.hexdigest(),
                            identity=file_identity(output_info), data_offset=DATA_OFFSET),
                chunk_bytes=chunk_bytes)
            with os.fdopen(os.open(receipt_path, output_flags, 0o600), 'wb') as receipt_stream:
                owned = os.fstat(receipt_stream.fileno())
                created.append((receipt_path, (owned.st_dev, owned.st_ino)))
                receipt_stream.write((json.dumps(result, indent=2) + '\n').encode())
                receipt_stream.flush()
                os.fsync(receipt_stream.fileno())
            return result
    except BaseException:
        for path, identity in reversed(created):
            _remove_created(path, identity)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--source-receipt', required=True, type=Path)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--verify-xor', action='store_true', default=None)
    args = parser.parse_args()
    receipt = json.loads(_safe_path(args.source_receipt).read_text(encoding='utf-8'))
    result = extract_ngram(args.source, args.output, source_receipt=receipt,
                           receipt_path=args.receipt, verify_xor=args.verify_xor)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
