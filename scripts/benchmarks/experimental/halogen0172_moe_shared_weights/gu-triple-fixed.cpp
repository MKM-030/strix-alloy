// Standalone exact native GU projection component, three same-expert tasks.
// No GL counter/activation/fold substitution and no engine hook.
#include <hip/hip_runtime.h>
#include <hip/hip_fp16.h>
#include <stdint.h>
namespace {
template<unsigned Byte>
__device__ __forceinline__ uint32_t unpack(uint32_t lo,uint32_t hi) {
    uint32_t r;
    asm("v_perm_b32 %0, %1, %2, %3" : "=v"(r) : "v"(hi),"v"(lo),"n"(0x0c040c00u+Byte*0x10001u));
    r|=0x64006400u;
    asm("v_pk_add_f16 %0, %0, %1" : "+v"(r) : "v"(0xe408e408u));
    return r;
}
__device__ __forceinline__ float dot(uint32_t w,uint32_t q,float a) {
    __2f16 wh,qh;
    __builtin_memcpy(&wh,&w,4); __builtin_memcpy(&qh,&q,4);
    return __ockl_fdot2(wh,qh,a,false);
}
__device__ __forceinline__ float scaled(uint16_t s,float x,float a) {
    asm("v_fma_mix_f32 %0, %1, %2, %0 op_sel_hi:[1,0,0]" : "+v"(a) : "v"((uint32_t)s),"v"(x));
    return a;
}
__device__ __forceinline__ float add(float a,float b) {
    float r;asm("v_add_f32 %0, %1, %2" : "=v"(r) : "v"(a),"v"(b));return r;
}
}
extern "C" __global__ __launch_bounds__(256)
void alloy0172_moe_gu_triple_v4(const unsigned char* weights,int64_t code_bytes,
                              const uint16_t* input,const int* experts,
                              const int* triples,float* output,int rows,int task_count) {
    __shared__ __align__(16) uint32_t query[3][1280];
    const unsigned tid=threadIdx.x,lane=tid&3;
    const unsigned group_id=blockIdx.x/(rows/64),tile=blockIdx.x%(rows/64);
    const int a=triples[3*group_id],b=triples[3*group_id+1],c=triples[3*group_id+2];
    if(a<0||b<0||c<0||a>=task_count||b>=task_count||c>=task_count)return;
    const int expert=experts[a];
    if(experts[b]!=expert||experts[c]!=expert)return;
    for(unsigned i=tid;i<1280;i+=256) {
        __builtin_memcpy(query[0]+i,input+(int64_t)a*2560+2*i,4);
        __builtin_memcpy(query[1]+i,input+(int64_t)b*2560+2*i,4);
        __builtin_memcpy(query[2]+i,input+(int64_t)c*2560+2*i,4);
    }
    __syncthreads();
    const unsigned row=tile*64+(tid>>2);
    const int64_t wr=(int64_t)expert*rows+row;
    const unsigned char* codes=weights+wr*1280;
    const unsigned char* scales=weights+code_bytes+wr*40;
    float aa=0,bb=0,cc=0;
    #pragma unroll 1
    for(unsigned g=0;g<20;g++) {
        uint4 packed;__builtin_memcpy(&packed,codes+g*64+lane*16,16);
        uint4 qa[4],qb[4],qc[4];
        #pragma unroll
        for(unsigned j=0;j<4;j++) {
            const unsigned at=g*64+lane*16+j*4;
            __builtin_memcpy(qa+j,__builtin_assume_aligned(query[0]+at,16),16);
            __builtin_memcpy(qb+j,__builtin_assume_aligned(query[1]+at,16),16);
            __builtin_memcpy(qc+j,__builtin_assume_aligned(query[2]+at,16),16);
        }
        const uint32_t words[4]={packed.x,packed.y,packed.z,packed.w};
        float x=0,y=0,z=0;
        #pragma unroll
        for(unsigned j=0;j<4;j++) {
            const uint32_t lo=words[j]&0x0f0f0f0fu,hi=(words[j]>>4)&0x0f0f0f0fu;
            const uint32_t w0=unpack<0>(lo,hi),w1=unpack<1>(lo,hi);
            const uint32_t w2=unpack<2>(lo,hi),w3=unpack<3>(lo,hi);
            x=dot(w0,qa[j].x,x);y=dot(w0,qb[j].x,y);z=dot(w0,qc[j].x,z);
            x=dot(w1,qa[j].y,x);y=dot(w1,qb[j].y,y);z=dot(w1,qc[j].y,z);
            x=dot(w2,qa[j].z,x);y=dot(w2,qb[j].z,y);z=dot(w2,qc[j].z,z);
            x=dot(w3,qa[j].w,x);y=dot(w3,qb[j].w,y);z=dot(w3,qc[j].w,z);
        }
        uint16_t s;__builtin_memcpy(&s,scales+2*g,2);
        aa=scaled(s,x,aa);bb=scaled(s,y,bb);cc=scaled(s,z,cc);
    }
    aa=add(aa,__shfl_xor(aa,1,4));aa=add(aa,__shfl_xor(aa,2,4));
    bb=add(bb,__shfl_xor(bb,1,4));bb=add(bb,__shfl_xor(bb,2,4));
    cc=add(cc,__shfl_xor(cc,1,4));cc=add(cc,__shfl_xor(cc,2,4));
    if(lane==0) {
        output[(int64_t)a*rows+row]=aa;output[(int64_t)b*rows+row]=bb;
        output[(int64_t)c*rows+row]=cc;
    }
}
