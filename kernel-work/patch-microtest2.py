#!/usr/bin/env python3
src = open('hipgraph-microtest2.cu').read()
old = "    auto read_out = [&]() { CK(hipMemcpy(h_got.data(), d_out, bytes, hipMemcpyDeviceToHost)); };"
new = """    auto read_out = [&]() {
        CK(hipStreamSynchronize(stream));
        CK(hipDeviceSynchronize());
        CK(hipStreamSynchronize(stream));
        CK(hipMemcpy(h_got.data(), d_out, bytes, hipMemcpyDeviceToHost));
    };"""
assert old in src
src = src.replace(old, new)
open('hipgraph-microtest2.cu', 'w').write(src)
print('patched')
