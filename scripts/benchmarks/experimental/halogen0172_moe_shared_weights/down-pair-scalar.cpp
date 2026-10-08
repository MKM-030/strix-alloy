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
__device__ __forceinline__ uint32_t unpack_pair(uint32_t code) {
    uint32_t p = 0x64006400u | (code & 15u) | ((code & 240u) << 12);
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
void alloy0172_moe_down_pair_v1(const unsigned char* weights, int64_t code_bytes,
                              const uint16_t* input, const int* experts,
                              const int2* pairs, float* output,
                              int rows, int task_count) {
    __shared__ uint32_t query[2][320];
    const unsigned tid = threadIdx.x;
    const int blocks_per_task = rows / 64;
    const int pair_id = blockIdx.x / blocks_per_task;
    const int tile = blockIdx.x % blocks_per_task;
    const int2 ids = pairs[pair_id];
    if (ids.x < 0 || ids.x >= task_count || ids.y < -1 || ids.y >= task_count) return;
    const bool paired = ids.y >= 0;
    const int expert = experts[ids.x];
    if (paired && experts[ids.y] != expert) return;
    for (unsigned i=tid;i<320;i+=256) {
        query[0][i] = read32(input + (int64_t)ids.x*640 + 2*i);
        if (paired) query[1][i] = read32(input + (int64_t)ids.y*640 + 2*i);
    }
    __syncthreads();
    const unsigned lane = tid & 3;
    const unsigned row = tile*64 + (tid>>2);
    const int64_t weight_row = (int64_t)expert*rows + row;
    const unsigned char* codes = weights + weight_row*320;
    const unsigned char* scales = weights + code_bytes + weight_row*10;
    float a=0, b=0;
    // Keeping the five groups sequential limits register lifetime. Each group
    // is 128 int4 values, split into four original 32-value lane segments.
    #pragma unroll 1
    for (unsigned group=0;group<5;++group) {
        uint4 c; __builtin_memcpy(&c,codes+group*64+lane*16,16);
        const uint32_t words[4]={c.x,c.y,c.z,c.w};
        float x=0,y=0;
        #pragma unroll
        for (unsigned j=0;j<16;++j) {
            const unsigned byte=(words[j/4] >> (8*(j%4))) & 255;
            const uint32_t w=unpack_pair(byte);
            const unsigned at=group*64+lane*16+j;
            x=dot2(w,query[0][at],x);
            if (paired) y=dot2(w,query[1][at],y);
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
