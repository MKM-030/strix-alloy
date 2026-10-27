// ROOT ONLY: explicit HIP qualification fixture; never invoked by CPU tests.
// This executable intentionally allocates/copies/synchronizes its own fixture,
// outside the production enqueue helper. No engine/native pointer is accepted.
#include "hcmean.h"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>
using namespace hgn01816_hcmean_gpu;
bool read(const std::string& path,std::vector<std::uint16_t>& out) {
    std::ifstream f(path,std::ios::binary|std::ios::ate);
    if (!f)return false;
    const auto n=f.tellg();
    if (n<=0 || n>std::streamoff(512ull*1024*1024) || n%2)return false;
    out.resize(static_cast<std::size_t>(n)/2);f.seekg(0);
    return bool(f.read(reinterpret_cast<char*>(out.data()),n));
}
int main(int argc,char** argv) {
    if (argc!=9) {
        std::fprintf(stderr,"fixture DIR full_rows source_first rows tap destination_rows destination_first actual.u16\n");return 2;
    }
    std::uint32_t nums[6];
    for (int i=0;i<6;++i) {
        char* end=nullptr;const auto v=std::strtoull(argv[i+2],&end,10);
        if (!*argv[i+2] || *end || v>8192)return 2;
        nums[i]=static_cast<std::uint32_t>(v);
    }
    std::vector<std::uint16_t> raw,expected,actual;
    if (!read(std::string(argv[1])+"/raw.u16",raw) || !read(std::string(argv[1])+"/expected.u16",expected))return 2;
    Job j{};j.full_rows=nums[0];j.source_first=nums[1];j.rows=nums[2];j.tap=nums[3];
    if (j.tap>=5)return 2;
    j.completed_layer=completed_layers[j.tap];j.destination_rows=nums[4];j.destination_first=nums[5];
    j.mode=j.full_rows<=4?Mode::Decode:Mode::Prefill;j.raw_elements=raw.size();j.output_elements=expected.size();
    actual.resize(expected.size());
    hipStream_t stream=nullptr;std::uint16_t *gpu_raw=nullptr,*gpu_out=nullptr;
    int result=0;
    auto checked=[&](hipError_t e,const char* op){if(e!=hipSuccess){std::fprintf(stderr,"%s: %s\n",op,hipGetErrorString(e));result=3;return false;}return true;};
    do {
        if (!checked(hipStreamCreateWithFlags(&stream,hipStreamNonBlocking),"stream"))break;
        if (!checked(hipMalloc(reinterpret_cast<void**>(&gpu_raw),raw.size()*2),"raw alloc"))break;
        if (!checked(hipMalloc(reinterpret_cast<void**>(&gpu_out),actual.size()*2),"out alloc"))break;
        j.raw=gpu_raw;j.owned_output=gpu_out;
        if (validate(j)!=Status::Ok){result=2;break;}
        if (!checked(hipMemcpyAsync(gpu_raw,raw.data(),raw.size()*2,hipMemcpyHostToDevice,stream),"fixture input"))break;
        std::fill(actual.begin(),actual.end(),0x55aa);
        if (!checked(hipMemcpyAsync(gpu_out,actual.data(),actual.size()*2,hipMemcpyHostToDevice,stream),"guards"))break;
        const auto e=enqueue(j,stream);
        if (e.validation!=Status::Ok || !checked(e.launch,"launch")){result=3;break;}
        if (!checked(hipMemcpyAsync(actual.data(),gpu_out,actual.size()*2,hipMemcpyDeviceToHost,stream),"fixture result"))break;
        if (!checked(hipStreamSynchronize(stream),"fixture completion"))break;
        std::ofstream out(argv[8],std::ios::binary);
        if (!out.write(reinterpret_cast<const char*>(actual.data()),static_cast<std::streamsize>(actual.size()*2))){result=2;break;}
        std::size_t mismatches=0;
        for (std::size_t i=0;i<actual.size();++i) {
            if (actual[i]!=expected[i]) {
                if (mismatches<8)std::fprintf(stderr,"word%zu actual%04x expected%04x\n",i,unsigned(actual[i]),unsigned(expected[i]));
                ++mismatches;
            }
        }
        std::printf("explicit-contract words=%zu mismatches=%zu (includes guards)\n",actual.size(),mismatches);
        if(mismatches)result=1;
    } while(false);
    // Fixture-only cleanup after any queued work, never lifetime proof for native.
    if (stream)checked(hipStreamSynchronize(stream),"fixture cleanup completion");
    if (gpu_out)checked(hipFree(gpu_out),"out free");
    if (gpu_raw)checked(hipFree(gpu_raw),"raw free");
    if (stream)checked(hipStreamDestroy(stream),"stream destroy");
    return result;
}
