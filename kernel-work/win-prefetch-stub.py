#!/usr/bin/env python3
"""Windows build fix from pwilkin/llama.cpp issue #24:
add a no-op prefetch() to the _WIN32 lazy-reader stub (prefetch is a page-cache hint;
on the mmap fallback a no-op is behaviour-correct). Idempotent."""
import sys

F = "src/llama-lazy-reader.h"
src = open(F).read()
if "void prefetch(const int32_t *, int64_t) const {}" in src:
    print("already patched"); sys.exit(0)

old = """    void gather(const int32_t *, int64_t, float *) const {
        GGML_ABORT("lazy direct reads are not supported on this platform");
    }
#else"""
new = """    void gather(const int32_t *, int64_t, float *) const {
        GGML_ABORT("lazy direct reads are not supported on this platform");
    }

    // --lazy-mode on-direct falls back to lazy mmap reads on Windows; prefetch() is a
    // page-cache hint there, so a no-op is behaviour-correct (see issue #24).
    void prefetch(const int32_t *, int64_t) const {}
#else"""
assert old in src, "anchor not found"
src = src.replace(old, new, 1)
open(F, "w").write(src)
print("patched OK")
