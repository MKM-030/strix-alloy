// Private standalone real-operation replay candidate. No serving registration.
// A 512-thread workgroup owns all ten experts and one normalized H128 strip.
#include <hip/hip_runtime.h>
#include <stdint.h>

namespace {
__device__ __forceinline__ uint32_t read32(const void* p) {
    uint32_t x; __builtin_memcpy(&x,p,4); return x;
}
__device__ __forceinline__ uint16_t read16(const void* p) {
    uint16_t x; __builtin_memcpy(&x,p,2); return x;
}
template<unsigned Byte>
__device__ __forceinline__ uint32_t unpack_pair(uint32_t lo,uint32_t hi) {
    uint32_t p,r;
    asm volatile("v_perm_b32 %0, %1, %2, %3" : "=v"(p)
                 : "v"(hi),"v"(lo),"n"(0x0c040c00u+Byte*0x10001u));
    p|=0x64006400u;
    asm volatile("v_pk_add_f16 %0, %1, %2" : "=v"(r)
                 : "v"(p),"v"(0xe408e408u));
    return r;
}
__device__ __forceinline__ float dot2(uint32_t w,uint32_t q,float a) {
    asm volatile("v_dot2acc_f32_f16 %0, %1, %2" : "+v"(a) : "v"(w),"v"(q));
    return a;
}
__device__ __forceinline__ float scale_fma(uint16_t s,float x,float a) {
    asm volatile("v_fma_mix_f32 %0, %1, %2, %0 op_sel_hi:[1,0,0]"
                 : "+v"(a) : "v"((uint32_t)s),"v"(x));
    return a;
}
__device__ __forceinline__ float add(float a,float b) {
    float r; asm volatile("v_add_f32 %0, %1, %2" : "=v"(r) : "v"(a),"v"(b)); return r;
}
__device__ __forceinline__ float sub(float a,float b) {
    float r; asm volatile("v_sub_f32 %0, %1, %2" : "=v"(r) : "v"(a),"v"(b)); return r;
}
__device__ __forceinline__ float mul(float a,float b) {
    float r; asm volatile("v_mul_f32 %0, %1, %2" : "=v"(r) : "v"(a),"v"(b)); return r;
}
__device__ __forceinline__ float channel_mix(uint16_t s,float x) {
    float r;
    asm volatile("v_fma_mix_f32 %0, %1, %2, neg(0) op_sel_hi:[1,0,0]"
                 : "=v"(r) : "v"((uint32_t)s),"v"(x));
    return r;
}
__device__ __forceinline__ float residual_fma(float s,float r,float a) {
    asm volatile("v_fmac_f32 %0, %1, %2" : "+v"(a) : "v"(s),"v"(r)); return a;
}
__device__ __forceinline__ uint32_t bits(float x) {
    uint32_t r; __builtin_memcpy(&r,&x,4); return r;
}
__device__ __forceinline__ float value(uint32_t x) {
    float r; __builtin_memcpy(&r,&x,4); return r;
}
__device__ __forceinline__ uint16_t bf16_rne(float x) {
    const uint32_t u=bits(x); return (uint16_t)((u+0x7fffu+((u>>16)&1u))>>16);
}
// Exactly the native signed-own + XOR-peer expression, including source order.
template<unsigned Mask>
__device__ __forceinline__ float butterfly(float x,unsigned lane) {
    const float peer=__shfl_xor(x,Mask,32);
    return add((lane&Mask)?value(bits(x)^0x80000000u):x,peer);
}
__device__ __forceinline__ float project(const unsigned char* w,int64_t scale_bytes,
                                        const uint32_t* query,int expert,unsigned row,unsigned lane) {
    const int64_t flat=(int64_t)expert*2560+row;
    const unsigned char* codes=w+flat*320;
    const unsigned char* scales=w+scale_bytes+flat*10;
    float a=0.0f;
    #pragma unroll 1
    for(unsigned g=0;g<5;++g) {
        uint4 c; __builtin_memcpy(&c,codes+g*64+lane*16,16);
        const uint32_t words[4]={c.x,c.y,c.z,c.w};
        uint4 q[4];
        #pragma unroll
        for(unsigned j=0;j<4;++j)
            __builtin_memcpy(&q[j],__builtin_assume_aligned(query+g*64+lane*16+4*j,16),16);
        asm volatile("" : : "v"(q[0].x),"v"(q[0].y),"v"(q[0].z),"v"(q[0].w),
            "v"(q[1].x),"v"(q[1].y),"v"(q[1].z),"v"(q[1].w),
            "v"(q[2].x),"v"(q[2].y),"v"(q[2].z),"v"(q[2].w),
            "v"(q[3].x),"v"(q[3].y),"v"(q[3].z),"v"(q[3].w) : "memory");
        float x=0.0f;
        #pragma unroll
        for(unsigned j=0;j<4;++j) {
            const uint32_t lo=words[j]&0x0f0f0f0fu,hi=(words[j]>>4)&0x0f0f0f0fu;
            x=dot2(unpack_pair<0>(lo,hi),q[j].x,x);
            x=dot2(unpack_pair<1>(lo,hi),q[j].y,x);
            x=dot2(unpack_pair<2>(lo,hi),q[j].z,x);
            x=dot2(unpack_pair<3>(lo,hi),q[j].w,x);
        }
        a=scale_fma(read16(scales+2*g),x,a);
    }
    a=add(a,__shfl_xor(a,1,4));
    return add(a,__shfl_xor(a,2,4));
}
}

// Original FL ABI is retained to make an exact replay binding straightforward.
// scratch/counters/task_map are deliberately unaccessed. Native GL remains stock.
// Launch grid=20*N, block=512. Host proves positive N and the original extents.
extern "C" __global__ __launch_bounds__(512)
void alloy0173_moe_fl_owner512_v1(const unsigned char* weights,int64_t scale_bytes,
    const uint16_t* input,const int* experts,float* scratch,const float* route_weights,
    const uint16_t* metadata,const uint16_t* residual,const float* scalar,
    uint16_t* output,unsigned* counters,const int* task_map) {
    (void)scratch;(void)counters;(void)task_map;
    __shared__ __align__(16) uint32_t query[10][320];
    __shared__ float folded[128];
    const unsigned t=threadIdx.x,lane=t&3u;
    const unsigned token=blockIdx.x/20u,strip=blockIdx.x%20u;
    // The entire ten-input operation is staged once, avoiding a barrier per expert.
    for(unsigned k=t;k<3200;k+=512)
        query[k/320][k%320]=read32(input+(int64_t)token*6400+2*k);
    __syncthreads();
    const unsigned row=strip*128+(t>>2);
    float f=0.0f;
    #pragma unroll 1
    for(unsigned e=0;e<10;++e) {
        const unsigned task=10*token+e;
        const float p=project(weights,scale_bytes,query[e],experts[task],row,lane);
        // Native projection is fully reduced before separate route multiply/add.
        // All lanes retain the same expression; only quartet lane zero publishes.
        f=add(f,mul(route_weights[task],p));
    }
    if(lane==0) folded[t>>2]=f;
    __syncthreads();
    if(t<32) {
        const unsigned offset=strip*128+4*t;
        const float x0=folded[4*t],x1=folded[4*t+1];
        const float x2=folded[4*t+2],x3=folded[4*t+3];
        const float p=add(x0,x1),m=sub(x0,x1),q=add(x2,x3),n=sub(x2,x3);
        float a=add(p,q),b=add(m,n),c=sub(p,q),d=sub(m,n);
        a=butterfly<1>(a,t);b=butterfly<1>(b,t);c=butterfly<1>(c,t);d=butterfly<1>(d,t);
        a=butterfly<2>(a,t);b=butterfly<2>(b,t);c=butterfly<2>(c,t);d=butterfly<2>(d,t);
        a=butterfly<4>(a,t);b=butterfly<4>(b,t);c=butterfly<4>(c,t);d=butterfly<4>(d,t);
        a=butterfly<8>(a,t);b=butterfly<8>(b,t);c=butterfly<8>(c,t);d=butterfly<8>(d,t);
        a=butterfly<16>(a,t);b=butterfly<16>(b,t);c=butterfly<16>(c,t);d=butterfly<16>(d,t);
        const float norm=value(0x3db504f3u);
        float h[4]={a,b,c,d};
        const float s=scalar[token];
        #pragma unroll
        for(unsigned j=0;j<4;++j) {
            const float mixed=channel_mix(metadata[offset+j],mul(norm,h[j]));
            const float rounded=value((uint32_t)bf16_rne(mixed)<<16);
            const float r=value((uint32_t)residual[(int64_t)token*2560+offset+j]<<16);
            output[(int64_t)token*2560+offset+j]=bf16_rne(residual_fma(s,r,rounded));
        }
    }
}
