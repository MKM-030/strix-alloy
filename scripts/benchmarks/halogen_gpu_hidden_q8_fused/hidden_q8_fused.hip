// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// Standalone fixed-shape component candidate, never installed in serving.
// Original compact Q8 rows; grid160/block256/wave32/LDS0/stream0.
#include <hip/hip_runtime.h>
#include <stdint.h>

#if !defined(__HIP_PLATFORM_AMD__)
#error "AMD HIP device compilation required"
#endif
#if defined(__HIP_DEVICE_COMPILE__) && __HIP_DEVICE_COMPILE__
#if !defined(__gfx1151__)
#error "Only gfx1151 is in scope"
#endif
#endif

namespace {
constexpr unsigned width=2560, row_bytes=2720;
static_assert(sizeof(uint4)==16 && alignof(uint4)==16,"Vector load contract");
static_assert(sizeof(float)==4 && sizeof(uint16_t)==2,"FP32/BF16 word contract");

__device__ __forceinline__ uint4 load128(const void* source) {
    uint4 value;
    __builtin_memcpy(&value,__builtin_assume_aligned(source,16),sizeof(value));
    return value;
}
__device__ __forceinline__ uint32_t load32(const void* source) {
    uint32_t value;
    __builtin_memcpy(&value,__builtin_assume_aligned(source,4),sizeof(value));
    return value;
}
__device__ __forceinline__ float add(float left,float right) {
    float value;
    asm volatile("v_add_f32 %0, %1, %2":"=v"(value):"v"(left),"v"(right));
    return value;
}
__device__ __forceinline__ uint32_t rounded_bits(float value) {
    const uint32_t bits=__float_as_uint(value);
    return bits+0x7fffu+((bits>>16)&1u);
}
__device__ __forceinline__ uint16_t bf16(float value) {
    return static_cast<uint16_t>(rounded_bits(value)>>16);
}
__device__ __forceinline__ uint32_t decode(unsigned code,uint32_t affine) {
    float value;
    const float code32=static_cast<float>(code);
    // FP32 code, FP16 scale in low half and FP16 bias in high half.
    // The original fused FP32 affine boundary remains before BF16 RNE.
    asm volatile("v_fma_mix_f32 %0, %1, %2, %2 op_sel:[0,0,1] op_sel_hi:[0,1,1]"
                 :"=v"(value):"v"(code32),"v"(affine));
    return rounded_bits(value);
}
__device__ __forceinline__ uint32_t pack(uint32_t first,uint32_t second) {
    uint32_t value;
    // PERM byte selectors0..3 address src1,4..7 src0. Select[6,7,2,3].
    // Integer RNE remains scalar and unchanged; only halfword extraction fuses.
    asm volatile("v_perm_b32 %0, %1, %2, %3"
                 :"=v"(value):"v"(first),"v"(second),"s"(0x03020706u));
    return value;
}
__device__ __forceinline__ float dot(uint32_t x,uint32_t w,float sum) {
    asm volatile("v_dot2_f32_bf16 %0, %1, %2, %0":"+v"(sum):"v"(x),"v"(w));
    return sum;
}
struct Four {float a,b,c,d;};
struct Inputs {uint4 a0,a1,b0,b1,c0,c1,d0,d1;};
__device__ __forceinline__ void step(Four& sums,uint32_t w,
                                    uint32_t a,uint32_t b,uint32_t c,uint32_t d) {
    sums.a=dot(a,w,sums.a);sums.b=dot(b,w,sums.b);
    sums.c=dot(c,w,sums.c);sums.d=dot(d,w,sums.d);
}
__device__ __forceinline__ void code4(Four& sums,uint32_t codes,uint32_t affine,
                                     uint32_t a0,uint32_t b0,uint32_t c0,uint32_t d0,
                                     uint32_t a1,uint32_t b1,uint32_t c1,uint32_t d1) {
    const uint32_t w0=pack(decode(codes&255u,affine),decode((codes>>8)&255u,affine));
    step(sums,w0,a0,b0,c0,d0);
    const uint32_t w1=pack(decode((codes>>16)&255u,affine),decode(codes>>24,affine));
    step(sums,w1,a1,b1,c1,d1);
}
template<unsigned distance>
__device__ __forceinline__ float butterfly(float value) {
    static_assert(distance==8 || distance==4 || distance==2 || distance==1,
                  "XOR stays within each fully active sixteen-lane row");
    float result;
    // DPP permutes src0 only: shuffled+own rather than own+shuffled.
    // Finite FP32 ADD under original RNE/denorm mode is commutative;
    // no NaN payload equivalence is claimed. Native replay is still required.
    asm volatile("v_add_f32 %0, %1, %1 row_xmask:%2 row_mask:0xf bank_mask:0xf bound_ctrl:1"
                 :"=v"(result):"v"(value),"n"(distance));
    return result;
}
template<unsigned distance>
__device__ __forceinline__ void reduce(Four& sums) {
    sums.a=butterfly<distance>(sums.a);sums.b=butterfly<distance>(sums.b);
    sums.c=butterfly<distance>(sums.c);sums.d=butterfly<distance>(sums.d);
}
}

extern "C" __global__ __launch_bounds__(256)
void halogen_gpu_hidden_q8_fused(const uint8_t* __restrict__ W,
                                const uint16_t* __restrict__ X,
                                uint16_t* __restrict__ Y,int64_t K,int64_t N) {
    if(K!=width || N!=width)return;
    const unsigned p=threadIdx.x&15u;
    const unsigned o=16*blockIdx.x+(threadIdx.x>>4);
    const uint8_t* row=W+o*row_bytes;
    Four total{0.0f,0.0f,0.0f,0.0f};
#pragma clang loop unroll(disable)
    for(unsigned q=0;q<10;++q) {
        const unsigned k=16*p+256*q;
        const uint4 codes=load128(row+k);
        const uint32_t affine=load32(row+width+4*(k>>6));
        const Inputs x{load128(X+k),load128(X+k+8),
                       load128(X+width+k),load128(X+width+k+8),
                       load128(X+2*width+k),load128(X+2*width+k+8),
                       load128(X+3*width+k),load128(X+3*width+k+8)};
        Four partial{0.0f,0.0f,0.0f,0.0f};
        code4(partial,codes.x,affine,x.a0.x,x.b0.x,x.c0.x,x.d0.x,x.a0.y,x.b0.y,x.c0.y,x.d0.y);
        code4(partial,codes.y,affine,x.a0.z,x.b0.z,x.c0.z,x.d0.z,x.a0.w,x.b0.w,x.c0.w,x.d0.w);
        code4(partial,codes.z,affine,x.a1.x,x.b1.x,x.c1.x,x.d1.x,x.a1.y,x.b1.y,x.c1.y,x.d1.y);
        code4(partial,codes.w,affine,x.a1.z,x.b1.z,x.c1.z,x.d1.z,x.a1.w,x.b1.w,x.c1.w,x.d1.w);
        total.a=add(total.a,partial.a);total.b=add(total.b,partial.b);
        total.c=add(total.c,partial.c);total.d=add(total.d,partial.d);
    }
    reduce<8>(total);reduce<4>(total);reduce<2>(total);reduce<1>(total);
    if(p==0) {
        Y[o]=bf16(total.a);Y[width+o]=bf16(total.b);
        Y[2*width+o]=bf16(total.c);Y[3*width+o]=bf16(total.d);
    }
}
