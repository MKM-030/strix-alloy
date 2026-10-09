"""Pinned original BF16 embedding binding, mapped once and copied per token.

This is an explicit cold preparation operation, never a native relay callback.
No network, tensor runtime or accelerator initialization occurs at import.
"""
import hashlib
import json
import mmap
from pathlib import Path

REVISION = 'f5d08274bafd880402bd16f5e3e6c514136ec06c'
SHA256 = '2d651616c258aaeae8ba1c4631bcbc6e72f3dca8f2a2f3add3b00c4bb45f95c2'
FILE_BYTES = 2974788136
HEADER_BYTES = 1568
HEADER_SHA256 = '3f68ed90e4b36cbbdfcbb6c598a5a72e1d5d95dab5013765f5bf5da17d7ef9e1'
TENSOR = 'model.language_model.embed_tokens.weight'
VOCAB, WIDTH, ROW_BYTES, DATA_OFFSET = 248320, 2560, 5120, 1576
MASK_ID, MAX_TARGET_ID = 248077, 248076

class OriginalEmbeddingRows:
    def __init__(self, receipt_path):
        receipt = json.loads(Path(receipt_path).read_text(encoding='utf-8-sig'))
        if not (receipt.get('qualified') is True and receipt.get('whole_shard_hash_verified') is True
                and receipt.get('revision') == REVISION and receipt.get('sha256') == SHA256
                and receipt.get('bytes') == FILE_BYTES and receipt.get('tensor_key') == TENSOR):
            raise ValueError('A verified pinned complete embedding shard receipt is required')
        self.path = Path(receipt['path'])
        self._file = self.path.open('rb')
        try:
            initial = self.path.stat()
            if initial.st_size != FILE_BYTES:
                raise ValueError('Original embedding shard size changed')
            self._file.seek(0)
            if hashlib.file_digest(self._file, 'sha256').hexdigest() != SHA256:
                raise ValueError('Original embedding shard hash changed')
            self._file.seek(0)
            if int.from_bytes(self._file.read(8), 'little') != HEADER_BYTES:
                raise ValueError('Original embedding header length changed')
            header = self._file.read(HEADER_BYTES)
            if hashlib.sha256(header).hexdigest() != HEADER_SHA256:
                raise ValueError('Original embedding tensor header changed')
            tensor = json.loads(header)[TENSOR]
            if tensor != dict(dtype='BF16', shape=[VOCAB, WIDTH], data_offsets=[0, VOCAB*ROW_BYTES]):
                raise ValueError('Original embedding tensor layout changed')
            final = self.path.stat()
            if (initial.st_size, initial.st_mtime_ns, initial.st_ino) != (final.st_size, final.st_mtime_ns, final.st_ino):
                raise ValueError('Original embedding shard changed during preparation')
            self._map = mmap.mmap(self._file.fileno(), length=0, access=mmap.ACCESS_READ)
            self.identity = dict(revision=REVISION, sha256=SHA256, bytes=FILE_BYTES,
                tensor_key=TENSOR, shape=[VOCAB,WIDTH], whole_shard_hash_verified=True)
        except BaseException:
            self._file.close()
            raise

    def raw_row(self, token_id, *, allow_reserved=False):
        ceiling = VOCAB - 1 if allow_reserved else MAX_TARGET_ID
        if type(token_id) is not int or not 0 <= token_id <= ceiling:
            raise ValueError('Embedding token ID outside admitted domain')
        if getattr(self, '_map', None) is None:
            raise RuntimeError('Embedding binding is closed')
        start = DATA_OFFSET + token_id * ROW_BYTES
        # bytes is an independent snapshot. mmap pointers never leave this class.
        return self._map[start:start+ROW_BYTES]

    def tensor_row(self, torch, token_id, *, device='cpu', allow_reserved=False):
        # bytearray is private temporary writable storage for torch.frombuffer;
        # clone detaches it before the explicit optional device copy.
        row = torch.frombuffer(bytearray(self.raw_row(token_id, allow_reserved=allow_reserved)),
            dtype=torch.bfloat16, count=WIDTH).clone()
        if not bool(torch.isfinite(row).all().item()):
            raise ValueError('Original embedding row is nonfinite')
        return row.to(device=device)

    def mask_row(self, torch, *, device='cpu'):
        return self.tensor_row(torch, MASK_ID, device=device, allow_reserved=True)

    def close(self):
        if getattr(self, '_map', None) is not None:
            self._map.close()
            self._map = None
        self._file.close()

    def __enter__(self): return self
    def __exit__(self, *exc): self.close()

def qualify(receipt_path, previous_ranges_path, output_path):
    previous = json.loads(Path(previous_ranges_path).read_text(encoding='utf-8-sig'))
    with OriginalEmbeddingRows(receipt_path) as binding:
        rows = []
        for previous_row in previous['embedding_rows']:
            token_id = previous_row['token_id']
            data = binding.raw_row(token_id, allow_reserved=token_id==MASK_ID)
            sha = hashlib.sha256(data).hexdigest()
            assert sha == previous_row['sha256'] and len(data) == ROW_BYTES
            rows.append(dict(token_id=token_id, bytes=len(data), sha256=sha, matches_previous_range=True))
        rejected = []
        for token_id in (-1, MASK_ID, VOCAB, True):
            try: binding.raw_row(token_id)
            except ValueError: rejected.append(token_id)
            else: raise AssertionError('Out-of-domain original embedding row admitted')
        identity = binding.identity
    try: binding.raw_row(0)
    except RuntimeError: closed_rejected = True
    else: raise AssertionError('Closed binding still usable')
    report = dict(schema='halogen0173.local-original-embedding-row-binding.v1', qualified=True,
        identity=identity, rows=rows, rejected_domain_inputs=rejected,
        closed_binding_rejected=closed_rejected, network_used=False,
        tensor_inference=False, device_initialized=False, complete_teacher_downloaded=False)
    Path(output_path).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(qualified=True, original_rows_checked=len(rows), source_sha256=SHA256)),flush=True)

if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--receipt',required=True);p.add_argument('--previous-ranges',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();qualify(args.receipt,args.previous_ranges,args.output)
