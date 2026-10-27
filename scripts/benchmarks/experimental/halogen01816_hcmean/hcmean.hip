#include "hcmean.h"
#if defined(__HIP_DEVICE_COMPILE__) && !defined(__gfx1151__)
#error "This source packet is scoped to gfx1151"
#endif

namespace hgn01816_hcmean_gpu {
__device__ __forceinline__ float decode(std::uint16_t b) {
    return __uint_as_float(std::uint32_t(b)<<16);
}
__device__ __forceinline__ std::uint16_t encode(float f) {
    auto u=__float_as_uint(f);
    if ((u&0x7fffffffU)>0x7f800000U)return 0x7fc0;
    return static_cast<std::uint16_t>((u+0x7fffU+((u>>16)&1U))>>16);
}
__device__ __forceinline__ std::uint16_t mean(std::uint16_t a,std::uint16_t b,std::uint16_t c,std::uint16_t d) {
    // Match Reduce.cuh's four zero-initialized accumulators and ordered combine.
    // Strict FP32 IEEE build required: no reassociation, contraction or FTZ.
    #pragma clang fp reassociate(off) contract(off)
    float x=0.0f+decode(a),y=0.0f+decode(b),z=0.0f+decode(c),w=0.0f+decode(d);
    float sum=x+y;
    sum=sum+z;
    sum=sum+w;
    return encode(sum*0.25f);
}
__global__ void mean_kernel(Job job) {
    const unsigned vector=blockIdx.x*blockDim.x+threadIdx.x;
    if (vector>=width/8)return;
    const std::uint64_t row=blockIdx.y;
    const std::uint64_t src=(job.source_first+row)*job.raw_row_stride+vector*8;
    const uint4 a=*reinterpret_cast<const uint4*>(job.raw+src);
    const uint4 b=*reinterpret_cast<const uint4*>(job.raw+src+job.raw_stream_stride);
    const uint4 c=*reinterpret_cast<const uint4*>(job.raw+src+2*job.raw_stream_stride);
    const uint4 d=*reinterpret_cast<const uint4*>(job.raw+src+3*job.raw_stream_stride);
    const unsigned av[4]={a.x,a.y,a.z,a.w},bv[4]={b.x,b.y,b.z,b.w};
    const unsigned cv[4]={c.x,c.y,c.z,c.w},dv[4]={d.x,d.y,d.z,d.w};
    unsigned packed[4];
    #pragma unroll
    for (unsigned i=0;i<4;++i) {
        const auto lo=mean(static_cast<std::uint16_t>(av[i]),static_cast<std::uint16_t>(bv[i]),static_cast<std::uint16_t>(cv[i]),static_cast<std::uint16_t>(dv[i]));
        const auto hi=mean(static_cast<std::uint16_t>(av[i]>>16),static_cast<std::uint16_t>(bv[i]>>16),static_cast<std::uint16_t>(cv[i]>>16),static_cast<std::uint16_t>(dv[i]>>16));
        packed[i]=unsigned(lo)|(unsigned(hi)<<16);
    }
    const auto tap_offset=job.output_row_stride==concat_width?job.tap*width:0;
    const auto dst=(job.destination_first+row)*job.output_row_stride+tap_offset+vector*8;
    *reinterpret_cast<uint4*>(job.owned_output+dst)=make_uint4(packed[0],packed[1],packed[2],packed[3]);
}
Enqueued enqueue(const Job& input,hipStream_t actual_stream) noexcept {
    const auto status=validate(input);
    if (status!=Status::Ok)return {status,hipErrorInvalidValue};
    // hipLaunchKernel returns immediate submission status without clearing prior
    // last-error state or synchronizing. No device pointer/stream ownership query.
    Job job=input;
    void* args[]={&job};
    const auto error=hipLaunchKernel(reinterpret_cast<const void*>(mean_kernel),
        dim3(3,job.rows,1),dim3(128,1,1),args,0,actual_stream);
    return {Status::Ok,error};
}
} // namespace hgn01816_hcmean_gpu
