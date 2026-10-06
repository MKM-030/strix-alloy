// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// Fixed-shape compact-Q8 MTP H candidate. No host/runtime/serving integration.
// Required launch: grid80, block256, wave32, LDS0, original stream0.
#include <hip/hip_runtime.h>
#include <hip/hip_fp16.h>
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
constexpr unsigned kWidth=2560;
constexpr unsigned kRowBytes=2720;
constexpr unsigned kRowLanes=16;
static_assert(sizeof(uint4)==16 && alignof(uint4)==16, "Aligned vector loads");
static_assert(sizeof(float)==4 && sizeof(uint16_t)==2, "FP32/BF16 word contract");

__device__ __forceinline__ uint4 load128(const void* source) {
    uint4 result;
    __builtin_memcpy(&result,__builtin_assume_aligned(source,16),sizeof(result));
    return result;
}
__device__ __forceinline__ uint32_t load32(const void* source) {
    uint32_t result;
    __builtin_memcpy(&result,__builtin_assume_aligned(source,4),sizeof(result));
    return result;
}
__device__ __forceinline__ float add(float a,float b) {
    float out;
    asm volatile("v_add_f32 %0, %1, %2" : "=v"(out) : "v"(a),"v"(b));
    return out;
}
__device__ __forceinline__ float dot(uint32_t x,uint32_t w,float sum) {
    asm volatile("v_dot2_f32_bf16 %0, %1, %2, %0" : "+v"(sum) : "v"(x),"v"(w));
    return sum;
}
__device__ __forceinline__ uint16_t bf16(float value) {
    const uint32_t bits=__float_as_uint(value);
    return static_cast<uint16_t>((bits+0x7fffu+((bits>>16)&1u))>>16);
}
__device__ __forceinline__ uint16_t decode(unsigned code,float scale,float bias) {
    float value;
    // u8 and FP16->FP32 conversion are exact. Keep one native affine rounding.
    // Equivalence to the original FMA_MIX is scoped to finite native Q8 rows.
    const float code32=static_cast<float>(code);
    asm volatile("v_fma_f32 %0, %1, %2, %3" : "=v"(value)
                 : "v"(code32),"v"(scale),"v"(bias));
    return bf16(value);
}
struct Four {
    float a,b,c,d;
};
struct Inputs {
    uint4 a0,a1,b0,b1,c0,c1,d0,d1;
};
__device__ __forceinline__ void step(Four& sums,uint32_t weight,
                                    uint32_t a,uint32_t b,uint32_t c,uint32_t d) {
    sums.a=dot(a,weight,sums.a);sums.b=dot(b,weight,sums.b);
    sums.c=dot(c,weight,sums.c);sums.d=dot(d,weight,sums.d);
}
__device__ __forceinline__ void code4(Four& sums,uint32_t codes,
                                      float scale,float bias,
                                      uint32_t a0,uint32_t b0,uint32_t c0,uint32_t d0,
                                      uint32_t a1,uint32_t b1,uint32_t c1,uint32_t d1) {
    const uint32_t w0=static_cast<uint32_t>(decode(codes&255u,scale,bias)) |
                     (static_cast<uint32_t>(decode((codes>>8)&255u,scale,bias))<<16);
    step(sums,w0,a0,b0,c0,d0);
    const uint32_t w1=static_cast<uint32_t>(decode((codes>>16)&255u,scale,bias)) |
                     (static_cast<uint32_t>(decode(codes>>24,scale,bias))<<16);
    step(sums,w1,a1,b1,c1,d1);
}
__device__ __forceinline__ void accumulate(Four& total,const uint8_t* row,
                                          unsigned k,const Inputs& x) {
    const uint4 codes=load128(row+k);
    const uint32_t affine=load32(row+kWidth+4*(k>>6));
    const float scale=__half2float(__ushort_as_half(static_cast<uint16_t>(affine)));
    const float bias=__half2float(__ushort_as_half(static_cast<uint16_t>(affine>>16)));
    Four partial{0.0f,0.0f,0.0f,0.0f};
    code4(partial,codes.x,scale,bias,x.a0.x,x.b0.x,x.c0.x,x.d0.x,x.a0.y,x.b0.y,x.c0.y,x.d0.y);
    code4(partial,codes.y,scale,bias,x.a0.z,x.b0.z,x.c0.z,x.d0.z,x.a0.w,x.b0.w,x.c0.w,x.d0.w);
    code4(partial,codes.z,scale,bias,x.a1.x,x.b1.x,x.c1.x,x.d1.x,x.a1.y,x.b1.y,x.c1.y,x.d1.y);
    code4(partial,codes.w,scale,bias,x.a1.z,x.b1.z,x.c1.z,x.d1.z,x.a1.w,x.b1.w,x.c1.w,x.d1.w);
    total.a=add(total.a,partial.a);total.b=add(total.b,partial.b);
    total.c=add(total.c,partial.c);total.d=add(total.d,partial.d);
}
__device__ __forceinline__ void reduce(Four& value,int distance) {
    const float a=__shfl_xor(value.a,distance,kRowLanes);
    const float b=__shfl_xor(value.b,distance,kRowLanes);
    const float c=__shfl_xor(value.c,distance,kRowLanes);
    const float d=__shfl_xor(value.d,distance,kRowLanes);
    value.a=add(value.a,a);value.b=add(value.b,b);
    value.c=add(value.c,c);value.d=add(value.d,d);
}
__device__ __forceinline__ void store(uint16_t* Y,unsigned o,const Four& s) {
    Y[o]=bf16(s.a);Y[kWidth+o]=bf16(s.b);
    Y[2*kWidth+o]=bf16(s.c);Y[3*kWidth+o]=bf16(s.d);
}
}

extern "C" __global__ __launch_bounds__(256)
void halogen_gpu_hidden_q8_rows2(const uint8_t* __restrict__ W,
                                const uint16_t* __restrict__ X,
                                uint16_t* __restrict__ Y,int64_t K,int64_t N) {
    if(K!=kWidth || N!=kWidth)return;
    const unsigned p=threadIdx.x&15u;
    const unsigned o0=32*blockIdx.x+2*(threadIdx.x>>4);
    const unsigned o1=o0+1;
    const uint8_t* row0=W+o0*kRowBytes;
    const uint8_t* row1=W+o1*kRowBytes;
    Four s0{0.0f,0.0f,0.0f,0.0f},s1{0.0f,0.0f,0.0f,0.0f};
#pragma clang loop unroll(disable)
    for(unsigned q=0;q<10;++q) {
        const unsigned k=16*p+256*q;
        const Inputs x{load128(X+k),load128(X+k+8),
                       load128(X+kWidth+k),load128(X+kWidth+k+8),
                       load128(X+2*kWidth+k),load128(X+2*kWidth+k+8),
                       load128(X+3*kWidth+k),load128(X+3*kWidth+k+8)};
        accumulate(s0,row0,k,x);
        accumulate(s1,row1,k,x);
    }
    reduce(s0,8);reduce(s1,8);
    reduce(s0,4);reduce(s1,4);
    reduce(s0,2);reduce(s1,2);
    reduce(s0,1);reduce(s1,1);
    if(p==0) {store(Y,o0,s0);store(Y,o1,s1);}
}
