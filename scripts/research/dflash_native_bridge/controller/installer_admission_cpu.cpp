#include "retained_controller.h"
using namespace hgn_dflash;
struct NativePhdr {u32 type,flags;u64 offset,vaddr,paddr,filesz,memsz,align;};
struct NativeImage {u64 base;const char* name;const NativePhdr* phdr;unsigned short count;};
struct Pin {u64 rva;u32 bytes;u8 original[7];};
static const Pin pins[]={{0x173fcd5,7,{0x83,0xbe,0x1c,0x01,0x00,0x00,0x00}},
{0x1782bdc,7,{0x48,0x8b,0xbb,0x08,0x01,0x00,0x00}},
{0x173ce9a,5,{0x48,0x8b,0x44,0x24,0x08}},
{0x173cc71,7,{0x48,0x8b,0xb0,0x80,0x01,0x00,0x00}},
{0x1746c96,7,{0x49,0x8d,0x86,0x28,0x03,0x00,0x00}},};
static u64 image_base;static u8 image_bytes[0x1800000];static NativePhdr phdr{1,5,0,0x1000,0,0x1800000,0x1800000,4096};
static NativeImage image{u64(image_bytes),"",&phdr,1};
static bool equal(const void* a,const void* b,u64 n)noexcept{auto* x=static_cast<const u8*>(a);auto* y=static_cast<const u8*>(b);for(u64 i=0;i<n;++i)if(x[i]!=y[i])return false;return true;}
static int dl_iterate_phdr(int(*fn)(NativeImage*,__SIZE_TYPE__,void*),void* ctx){return fn(&image,sizeof(image),ctx);}
static int find_main(NativeImage* image,__SIZE_TYPE__ size,void*)noexcept{
    if(size<sizeof(NativeImage)||!image->name||image->name[0])return 0;
    if(!image->phdr||image->count>64)return 1;
    for(const auto& pin:pins){bool executable=false;
        for(u32 i=0;i<image->count;++i){const auto& p=image->phdr[i];if(p.type==1&&p.flags==5&&pin.rva>=p.vaddr
            &&pin.rva+pin.bytes<=p.vaddr+p.filesz&&p.offset+pin.rva-p.vaddr==pin.rva-0x1000)executable=true;}
        if(!executable||!equal(reinterpret_cast<const void*>(image->base+pin.rva),pin.original,pin.bytes))return 1;}
    const u8 reset[5]={0xe8,0x66,0x68,5,0},ready[3]={0x44,0x89,0xed},scalar[5]={0x48,0x8b,0x5c,0x24,0x10};
    if(!equal(reinterpret_cast<const void*>(image->base+0x173ce95),reset,5)||!equal(reinterpret_cast<const void*>(image->base+0x173fd86),ready,3)
       ||!equal(reinterpret_cast<const void*>(image->base+0x1740408),scalar,5))return 1;
    image_base=image->base;return 1;
}
static bool admit_main()noexcept{
    image_base=0;
    return dl_iterate_phdr(find_main,nullptr)==1&&image_base;
}

int main(){for(const auto& p:pins)for(u32 i=0;i<p.bytes;++i)image_bytes[p.rva+i]=p.original[i];
const u8 reset[5]={0xe8,0x66,0x68,5,0},ready[3]={0x44,0x89,0xed},scalar[5]={0x48,0x8b,0x5c,0x24,0x10};
for(u32 i=0;i<5;++i){image_bytes[0x173ce95+i]=reset[i];image_bytes[0x1740408+i]=scalar[i];}for(u32 i=0;i<3;++i)image_bytes[0x173fd86+i]=ready[i];
const u64 changed[3]={0x173ce95,0x173fd86,0x1740408};for(auto rva:changed){if(!admit_main())return 10;
// Emulate CpuRejected/IslandRejected/MapFailed after image admission.
image_bytes[rva]^=1;if(admit_main()||image_base)return 1;image_bytes[rva]^=1;}return 0;}
