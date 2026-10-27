#include <cstdio>
#if !__has_include("adapter_core.h")
int main() { std::puts("FAIL: Deferred-Z adapter core is not implemented"); return 1; }
#else
#include "adapter_core.h"
#include <cassert>
#include <array>
int main() {
 using namespace dz_adapter;
 assert(!enabled(nullptr) && !enabled("0") && !enabled("true") && enabled("1"));
 assert(!overlap({0x1000,0x1000},{0x2000,0x1000}));
 assert(overlap({0x1000,0x1001},{0x2000,0x1000}));
 assert(!valid({~std::uintptr_t(0)-2,8}));
 assert(contains({0x1000,0x1000},{0x1200,0x200}));
 assert(!contains({0x1000,0x1000},{0x1800,0x1000}));
 Warmup warm; Tuple t{0x100,0x200,0x300,6144,8192,2560};
 assert(!warm.ready(t)); warm.remember(t); assert(warm.ready(t));
 Tuple changed=t; changed.input++; assert(!warm.ready(changed));
 changed=t; changed.m=4096; assert(!warm.ready(changed));
 std::array<unsigned char,17> bytes{}; absolute_jump(bytes.data(),0x1122334455667788ULL);
 assert(bytes[0]==0xff && bytes[1]==0x25 && bytes[6]==0x88 && bytes[13]==0x11);
 std::array<unsigned char,5> call{}; assert(relative_call(call.data(),0x1000,0x2000));
 assert(call[0]==0xe8 && call[1]==0xfb && call[2]==0x0f);
 assert(!relative_call(call.data(),0x1000,0x100000000ULL));
 Range z{0x10000000,96*1024*1024};
 std::array<Range,3> good{{{0x20000000,40*1024*1024},{0x30000000,160*1024*1024},{0x40000000,256*1024*1024}}};
 assert(disjoint(z,good.data(),good.size())); good[1]=z; assert(!disjoint(z,good.data(),good.size()));
 std::puts("PASS: opt-in, overflow-safe ranges, tuple warmup and instruction encodings");
}
#endif
