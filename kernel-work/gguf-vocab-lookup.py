"""gguf-vocab-lookup.py — resolve token ids to strings from a GGUF's tokenizer metadata.

Reads tokenizer.ggml.tokens (array of strings) from a GGUF header and prints the requested ids.
Used to identify whether a diverging token is a normal token or a special/template/EOS token,
which decides whether the serial-vs-verify divergence is an EOS/special-suppression difference.
"""
import struct
import sys


class R:
    def __init__(self, f):
        self.f = f

    def raw(self, n):
        b = self.f.read(n)
        if len(b) != n:
            raise EOFError("short read")
        return b

    def u32(self):
        return struct.unpack("<I", self.raw(4))[0]

    def u64(self):
        return struct.unpack("<Q", self.raw(8))[0]

    def st(self):
        n = self.u64()
        return self.raw(n).decode("utf-8", "replace")


def read_kv(f):
    r = R(f)
    assert r.raw(4) == b"GGUF"
    ver = r.u32()
    n_tensors = r.u64()
    n_kv = r.u64()
    meta = {}
    for _ in range(n_kv):
        k = r.st()
        t = r.u32()
        # only fully decode strings and string arrays; skip numbers cheaply
        if t == 8:
            meta[k] = r.st()
        elif t == 9:
            et = r.u32()
            n = r.u64()
            if et == 8:
                meta[k] = [r.st() for _ in range(n)]
            else:
                # skip scalar array by advancing (best effort): sizes
                sz = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
                f.seek(sz.get(et, 4) * n, 1)
        else:
            sz = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
            f.seek(sz.get(t, 4), 1)
    return ver, n_tensors, meta


def main():
    path = sys.argv[1]
    ids = [int(x) for x in sys.argv[2:]]
    with open(path, "rb") as f:
        ver, n_tensors, meta = read_kv(f)
    toks = meta.get("tokenizer.ggml.tokens")
    types = meta.get("tokenizer.ggml.token_type")
    print(f"file={path}")
    print(f"ver={ver} tensors={n_tensors} vocab={len(toks) if toks else None}")
    for k in ("tokenizer.ggml.bos_token_id", "tokenizer.ggml.eos_token_id",
              "tokenizer.ggml.eot_token_id", "tokenizer.ggml.padding_token_id",
              "tokenizer.ggml.add_bos_token", "tokenizer.ggml.add_eos_token"):
        if k in meta:
            print(f"  {k} = {meta[k]}")
    if not toks:
        return
    # ggml token_type: 1=NORMAL 2=UNKNOWN 3=CONTROL 4=USER_DEFINED 5=UNUSED 6=BYTE
    TY = {1: "NORMAL", 2: "UNKNOWN", 3: "CONTROL", 4: "USER_DEFINED", 5: "UNUSED", 6: "BYTE"}
    for i in ids:
        if i < 0 or i >= len(toks):
            print(f"  {i}: OUT OF RANGE")
            continue
        ty = types[i] if types and i < len(types) else None
        print(f"  {i}: ty={TY.get(ty, ty)} repr={toks[i]!r}")


if __name__ == "__main__":
    main()
