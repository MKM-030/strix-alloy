// Experimental standalone component. No serving hook or native ABI substitution.
// Two same-expert routed rows share each packed weight load and int4 decode.
// All original group dot2, scale-FMA and lane reduction operations are retained.
#include <hip/hip_runtime.h>
#include <stdint.h>

namespace {
__device__ __forceinline__ uint32_t read32(const void* p) {
    uint32_t x; __builtin_memcpy(&x, p, 4); return x;
}
__device__ __forceinline__ uint16_t read16(const void* p) {
    uint16_t x; __builtin_memcpy(&x, p, 2); return x;
}
template<unsigned Byte>
__device__ __forceinline__ uint32_t unpack_pair(uint32_t lo, uint32_t hi) {
    uint32_t p;
    asm volatile("v_perm_b32 %0, %1, %2, %3" : "=v"(p)
                 : "v"(hi), "v"(lo), "n"(0x0c040c00u + Byte*0x10001u));
    p |= 0x64006400u;
    uint32_t r;
    asm volatile("v_pk_add_f16 %0, %1, %2" : "=v"(r) : "v"(p), "v"(0xe408e408u));
    return r;
}
__device__ __forceinline__ float dot2(uint32_t w, uint32_t q, float a) {
    asm volatile("v_dot2acc_f32_f16 %0, %1, %2" : "+v"(a) : "v"(w), "v"(q));
    return a;
}
__device__ __forceinline__ float scale_fma(uint16_t scale, float x, float a) {
    asm volatile("v_fma_mix_f32 %0, %1, %2, %0 op_sel_hi:[1,0,0]"
                 : "+v"(a) : "v"((uint32_t)scale), "v"(x));
    return a;
}
__device__ __forceinline__ float add(float a,float b) {
    float r; asm volatile("v_add_f32 %0, %1, %2" : "=v"(r) : "v"(a),"v"(b)); return r;
}
}

// Pairs are preconstructed task IDs. Second=-1 marks an unpaired task.
// Native reference takes these same weights, scales, queries and expert IDs;
// only its ordinary output/task order differs from this explicit pairing map.
extern "C" __global__ __launch_bounds__(256)
void alloy0172_moe_gu_pair_vector_v3(const unsigned char* weights, int64_t code_bytes,
                              const uint16_t* input, const int* experts,
                              const int2* pairs, float* output,
                              int rows, int task_count) {
    __shared__ __align__(16) uint32_t query[2][1280];
    const unsigned tid = threadIdx.x;
    const int blocks_per_task = rows / 64;
    const int pair_id = blockIdx.x / blocks_per_task;
    const int tile = blockIdx.x % blocks_per_task;
    const int2 ids = pairs[pair_id];
    if (ids.x < 0 || ids.x >= task_count || ids.y < -1 || ids.y >= task_count) return;
    const bool paired = ids.y >= 0;
    const int expert = experts[ids.x];
    if (paired && experts[ids.y] != expert) return;
    for (unsigned i=tid;i<1280;i+=256) {
        query[0][i] = read32(input + (int64_t)ids.x*2560 + 2*i);
        if (paired) query[1][i] = read32(input + (int64_t)ids.y*2560 + 2*i);
    }
    __syncthreads();
    const unsigned lane = tid & 3;
    const unsigned row = tile*64 + (tid>>2);
    const int64_t weight_row = (int64_t)expert*rows + row;
    const unsigned char* codes = weights + weight_row*1280;
    const unsigned char* scales = weights + code_bytes + weight_row*40;
    float a=0, b=0;
    // Keeping the twenty groups sequential limits register lifetime. Each group
    // is 128 int4 values, split into four original 32-value lane segments.
    #pragma unroll 1
    for (unsigned group=0;group<20;++group) {
        uint4 c; __builtin_memcpy(&c,codes+group*64+lane*16,16);
        const uint32_t words[4]={c.x,c.y,c.z,c.w};
        uint4 qa[4],qb[4];
        const unsigned base=group*64+lane*16;
        #pragma unroll
        for(unsigned p=0;p<4;++p) {
            __builtin_memcpy(&qa[p],__builtin_assume_aligned(query[0]+base+4*p,16),16);
            qb[p]=make_uint4(0,0,0,0);
            if(paired) __builtin_memcpy(&qb[p],__builtin_assume_aligned(query[1]+base+4*p,16),16);
        }
        // Force the eight independent b128 reads ahead of the dependent dots.
        asm volatile("" : : "v"(qa[0].x),"v"(qa[0].y),"v"(qa[0].z),"v"(qa[0].w),
            "v"(qa[1].x),"v"(qa[1].y),"v"(qa[1].z),"v"(qa[1].w),
            "v"(qa[2].x),"v"(qa[2].y),"v"(qa[2].z),"v"(qa[2].w),
            "v"(qa[3].x),"v"(qa[3].y),"v"(qa[3].z),"v"(qa[3].w),
            "v"(qb[0].x),"v"(qb[0].y),"v"(qb[0].z),"v"(qb[0].w),
            "v"(qb[1].x),"v"(qb[1].y),"v"(qb[1].z),"v"(qb[1].w),
            "v"(qb[2].x),"v"(qb[2].y),"v"(qb[2].z),"v"(qb[2].w),
            "v"(qb[3].x),"v"(qb[3].y),"v"(qb[3].z),"v"(qb[3].w) : "memory");
        float x=0,y=0;
        #pragma unroll
        for (unsigned j=0;j<4;++j) {
            const uint32_t lo=words[j]&0x0f0f0f0fu,hi=(words[j]>>4)&0x0f0f0f0fu;
            const uint32_t w0=unpack_pair<0>(lo,hi),w1=unpack_pair<1>(lo,hi);
            const uint32_t w2=unpack_pair<2>(lo,hi),w3=unpack_pair<3>(lo,hi);
            x=dot2(w0,qa[j].x,x); if(paired)y=dot2(w0,qb[j].x,y);
            x=dot2(w1,qa[j].y,x); if(paired)y=dot2(w1,qb[j].y,y);
            x=dot2(w2,qa[j].z,x); if(paired)y=dot2(w2,qb[j].z,y);
            x=dot2(w3,qa[j].w,x); if(paired)y=dot2(w3,qb[j].w,y);
        }
        const uint16_t s=read16(scales+2*group);
        a=scale_fma(s,x,a);
        if (paired) b=scale_fma(s,y,b);
    }
    a=add(a,__shfl_xor(a,1,4)); a=add(a,__shfl_xor(a,2,4));
    if (paired) { b=add(b,__shfl_xor(b,1,4)); b=add(b,__shfl_xor(b,2,4)); }
    if (lane==0) {
        output[(int64_t)ids.x*rows+row]=a;
        if (paired) output[(int64_t)ids.y*rows+row]=b;
    }
}
