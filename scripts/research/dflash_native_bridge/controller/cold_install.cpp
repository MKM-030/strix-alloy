// Explicit default-off Linux cold installer. Compiled offline; never called here.
#include "cold_install.h"
#if !defined(__linux__) || !defined(__x86_64__)
#error "cold installer requires Linux x86-64"
#endif
using namespace hgn_dflash;
extern "C" {
struct NativePhdr {u32 type,flags;u64 offset,vaddr,paddr,filesz,memsz,align;};
struct NativeImage {u64 base;const char* name;const NativePhdr* phdr;unsigned short count;};
int dl_iterate_phdr(int(*)(NativeImage*,__SIZE_TYPE__,void*),void*);
void __register_frame(void*);
struct DwarfBases {void* text;void* data;void* function;};
const void* _Unwind_Find_FDE(const void*,DwarfBases*);
extern const u8 hgn_dflash_island_begin[],hgn_dflash_island_end[],hgn_dflash_island_frames[],hgn_dflash_island_frames_end[];
__thread relay::StackBounds hgn_dflash_stack_bounds __attribute__((tls_model("initial-exec")))={};
}
namespace {
static u8 optional_enabled;
static u64 in_flight;
static u32 installed,xsave_bytes;
static u64 xcr0,required_stack;
static u64 image_base;
constexpr u64 page=4096;
struct Pin {u64 rva;u32 bytes;u8 original[7];const u8* begin;const relay::Configuration* config;const u8* end;const u8* stock;u64 resume;};
#define RELAY(n) reinterpret_cast<const u8*>(&hgn_dflash_relay_##n##_begin),&hgn_dflash_relay_##n##_config,hgn_dflash_relay_##n##_code_end,hgn_dflash_relay_##n##_stock_delta
static const Pin pins[]={
    {0x173fcd5,7,{0x83,0xbe,0x1c,1,0,0,0},RELAY(0),0x173fcdc},
    {0x1782bdc,7,{0x48,0x8b,0xbb,8,1,0,0},RELAY(1),0x1782be3},
    {0x173ce9a,5,{0x48,0x8b,0x44,0x24,8},RELAY(2),0x173ce9f},
    {0x173cc71,7,{0x48,0x8b,0xb0,0x80,1,0,0},RELAY(3),0x173cc78},
    {0x1746c96,7,{0x49,0x8d,0x86,0x28,3,0,0},RELAY(4),0x1746c9d}
};
#undef RELAY
static long syscall6(long n,long a=0,long b=0,long c=0,long d=0,long e=0,long f=0)noexcept{
    register long r10 asm("r10")=d,r8 asm("r8")=e,r9 asm("r9")=f;long result;
    asm volatile("syscall":"=a"(result):"a"(n),"D"(a),"S"(b),"d"(c),"r"(r10),"r"(r8),"r"(r9):"rcx","r11","memory");return result;
}
static void copy(void* destination,const void* source,u64 bytes)noexcept{
    auto* d=static_cast<volatile u8*>(destination);auto* s=static_cast<const u8*>(source);for(u64 i=0;i<bytes;++i)d[i]=s[i];
}
static bool equal(const void* a,const void* b,u64 bytes)noexcept{
    auto* left=static_cast<const u8*>(a);auto* right=static_cast<const u8*>(b);for(u64 i=0;i<bytes;++i)if(left[i]!=right[i])return false;return true;
}
template<class T> static T value(u64 at)noexcept{T out{};copy(&out,reinterpret_cast<const void*>(at),sizeof(out));return out;}
[[noreturn]] static void fatal()noexcept{syscall6(231,127);__builtin_unreachable();}
struct Sha {u32 state[8];u64 bytes;u32 used;u8 block[64];};
static u32 rotate(u32 x,u32 n)noexcept{return(x>>n)|(x<<(32-n));}
static void hash_block(Sha& s,const u8* b)noexcept{
    static const u32 k[64]={
      0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
      0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
      0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
      0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
      0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
      0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
      0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
      0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
    u32 w[64];for(u32 i=0;i<16;++i)w[i]=(u32(b[4*i])<<24)|(u32(b[4*i+1])<<16)|(u32(b[4*i+2])<<8)|b[4*i+3];
    for(u32 i=16;i<64;++i)w[i]=w[i-16]+(rotate(w[i-15],7)^rotate(w[i-15],18)^(w[i-15]>>3))+w[i-7]+(rotate(w[i-2],17)^rotate(w[i-2],19)^(w[i-2]>>10));
    auto a=s.state[0],v=s.state[1],c=s.state[2],d=s.state[3],e=s.state[4],f=s.state[5],g=s.state[6],h=s.state[7];
    for(u32 i=0;i<64;++i){auto t1=h+(rotate(e,6)^rotate(e,11)^rotate(e,25))+((e&f)^((~e)&g))+k[i]+w[i];
        auto t2=(rotate(a,2)^rotate(a,13)^rotate(a,22))+((a&v)^(a&c)^(v&c));h=g;g=f;f=e;e=d+t1;d=c;c=v;v=a;a=t1+t2;}
    s.state[0]+=a;s.state[1]+=v;s.state[2]+=c;s.state[3]+=d;s.state[4]+=e;s.state[5]+=f;s.state[6]+=g;s.state[7]+=h;
}
static void hash_init(Sha& s)noexcept{
    const u32 initial[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    for(u32 i=0;i<8;++i)s.state[i]=initial[i];s.bytes=0;s.used=0;
}
static void hash_update(Sha& s,const u8* b,u64 bytes)noexcept{
    s.bytes+=bytes;for(u64 i=0;i<bytes;++i){s.block[s.used++]=b[i];if(s.used==64){hash_block(s,s.block);s.used=0;}}
}
static void hash_finish(Sha& s,u8* digest)noexcept{
    auto bits=s.bytes*8;s.block[s.used++]=0x80;
    if(s.used>56){while(s.used<64)s.block[s.used++]=0;hash_block(s,s.block);s.used=0;}
    while(s.used<56)s.block[s.used++]=0;
    for(u32 i=0;i<8;++i)s.block[63-i]=u8(bits>>(8*i));hash_block(s,s.block);
    for(u32 i=0;i<32;++i)digest[i]=u8(s.state[i/4]>>(24-8*(i%4)));
}
struct NativeStat {u64 dev,ino,nlink;u32 mode,uid,gid,pad;u64 rdev;i64 size,blksize,blocks,atime,atime_ns,mtime,mtime_ns,ctime,ctime_ns,reserved[3];};
static_assert(sizeof(NativeStat)==144);
static bool verify_file()noexcept{
    const u8 expected[32]={0xaf,0x4f,0x07,0xbb,0xe3,0x75,0x92,0x06,0x01,0x3e,0xb6,0xf1,0x32,0x80,0x95,0xca,
        0x21,0x05,0xcf,0xda,0x51,0x27,0xc5,0xb9,0xa2,0xab,0x93,0xe1,0xae,0xa9,0x87,0xb7};
    auto fd=syscall6(257,-100,reinterpret_cast<long>("/proc/self/exe"),0x80000);if(fd<0)return false;
    NativeStat before{},after{};bool ok=syscall6(5,fd,reinterpret_cast<long>(&before))==0&&before.size==26188824&&(before.mode&0xf000)==0x8000;
    Sha sha{};hash_init(sha);u8 buffer[8192],digest[32];u64 bytes=0;
    while(ok){auto n=syscall6(0,fd,reinterpret_cast<long>(buffer),sizeof(buffer));if(n==-4)continue;
        if(n<0){ok=false;break;}if(!n)break;bytes+=u64(n);if(bytes>26188824){ok=false;break;}hash_update(sha,buffer,u64(n));}
    hash_finish(sha,digest);
    ok=ok&&bytes==26188824&&equal(digest,expected,32)&&syscall6(5,fd,reinterpret_cast<long>(&after))==0
        &&before.dev==after.dev&&before.ino==after.ino&&before.size==after.size&&before.mtime==after.mtime&&before.mtime_ns==after.mtime_ns
        &&before.ctime==after.ctime&&before.ctime_ns==after.ctime_ns;
    if(syscall6(3,fd)!=0)ok=false;return ok;
}
static bool single_thread()noexcept{
    auto fd=syscall6(257,-100,reinterpret_cast<long>("/proc/self/task"),0x90000);if(fd<0)return false;
    u8 buffer[4096];u32 count=0;bool ok=true;
    for(;;){auto n=syscall6(217,fd,reinterpret_cast<long>(buffer),sizeof(buffer));if(n==-4)continue;if(n<0){ok=false;break;}if(!n)break;
        for(u64 at=0;at<u64(n);){if(u64(n)-at<20){ok=false;break;}auto length=u32(buffer[at+16])|(u32(buffer[at+17])<<8);
            if(length<20||length>u64(n)-at){ok=false;break;}if(buffer[at+19]!='.')++count;at+=length;}
        if(!ok||count>1)break;
    }
    if(syscall6(3,fd)!=0)ok=false;return ok&&count==1;
}
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
struct Cpu {u32 a,b,c,d;};
static Cpu cpuid(u32 leaf,u32 sub=0)noexcept{Cpu out{};asm volatile("cpuid":"=a"(out.a),"=b"(out.b),"=c"(out.c),"=d"(out.d):"a"(leaf),"c"(sub));return out;}
static bool cpu_state(u32& extent,u64& mask)noexcept{
    auto top=cpuid(0),features=cpuid(1);if(top.a<13||(features.c&((1u<<26)|(1u<<27)))!=((1u<<26)|(1u<<27)))return false;
    u32 lo,hi;asm volatile("xgetbv":"=a"(lo),"=d"(hi):"c"(0));mask=(u64(hi)<<32)|lo;auto d=cpuid(13);extent=d.b;
    if((mask&3)!=3||(mask&~((u64(d.d)<<32)|d.a))||(mask&~u64(0x2e7))||extent<576||extent>65536)return false;
    const bool amd=top.b==0x68747541&&top.d==0x69746e65&&top.c==0x444d4163;
    const bool intel=top.b==0x756e6547&&top.d==0x49656e69&&top.c==0x6c65746e;
    if(!amd&&!intel)return false;
    if(amd&&(cpuid(0x80000000).a<0x80000008||!(cpuid(0x80000008).b&(1u<<2))))return false;
    for(u32 bit=2;bit<64;++bit)if(mask&(u64(1)<<bit)){auto c=cpuid(13,bit);if(!c.a||c.b<576||(c.c&1)||u64(c.b)+c.a>extent)return false;}
    return true;
}
static bool relative(u64 field,u64 target,bool write)noexcept{
    auto delta=i64(target)-i64(field+4);if(delta<(-2147483647LL-1)||delta>2147483647LL)return false;
    if(write){auto d=i32(delta);copy(reinterpret_cast<void*>(field),&d,4);}return true;
}
static bool verify_frames(u64 original,u64 copied,u64 frames,u64 end)noexcept{
    const u8 prefix[9]={1,'z','R',0,1,0x78,16,1,0x1b};bool found[5]{};u32 count=0;
    for(auto at=frames;at+4<=end;){auto length=value<u32>(at);
        if(!length)return at+4==end&&count==5;
        if(length==0xffffffff||length<13||length>end-at-4)return false;
        auto id=value<u32>(at+4);
        if(!id){if(length<13||!equal(reinterpret_cast<const void*>(at+8),prefix,9))return false;}
        else {auto cie=at+4-id;if(cie<frames||cie>=at||value<u32>(cie+4))return false;
            auto begin=u64(i64(at+8)+value<i32>(at+8));auto extent=value<u32>(at+12);bool matched=false;
            for(u32 i=0;i<5;++i)if(begin==copied+u64(pins[i].begin)-original&&begin+extent==copied+u64(pins[i].end)-original&&!found[i]){
                found[i]=true;++count;matched=true;}
            if(!matched)return false;
        }at+=4+length;
    }return false;
}
static void* near_map(u64 bytes)noexcept{
    auto anchor=(image_base+0x1740000)&~(page-1);
    for(i64 i=1;i<=256;++i)for(i64 sign=1;sign>=-1;sign-=2){auto address=i64(anchor)+sign*i*0x200000;
        if(address<65536)continue;auto result=syscall6(9,address,long(bytes),3,0x100022,-1);
        if(result>=0){if(result!=address)fatal();return reinterpret_cast<void*>(result);}
    }
    return nullptr;
}
}
extern "C" __attribute__((visibility("default")))
cold::Result hgn_dflash_install_cold(const cold::Arguments* args)noexcept{
    if(!args||!args->enable)return cold::Result::Off;
    if(installed)return cold::Result::AlreadyInstalled;
    if(args->enable!=1||args->abi_version!=1||args->isolated_slot_cache_off!=1||!args->lane||(u64(args->lane)&7)
       ||args->optional_provider>1||args->callback_and_signal_budget>1048576
       ||(args->optional_provider&&(!args->provider||args->callback_and_signal_budget<81920)))return cold::Result::BadArguments;
    if(!single_thread())return cold::Result::NotSingleThread;
    if(!verify_file()||!admit_main())return cold::Result::ImageRejected;
    if(args->optional_provider&&!cpu_state(xsave_bytes,xcr0))return cold::Result::CpuRejected;
    required_stack=u64(xsave_bytes)+HGN_DFLASH_CAPTURE_RESERVE+HGN_DFLASH_XSAVE_PAD+63+args->callback_and_signal_budget;
    if(required_stack<u64(xsave_bytes)||required_stack>1048576)return cold::Result::BadArguments;
    const u8 endbr[4]={0xf3,0x0f,0x1e,0xfa};if(!equal(reinterpret_cast<const void*>(&hgn_dflash_ready_callback),endbr,4))return cold::Result::IslandRejected;
    auto original=u64(hgn_dflash_island_begin),end=u64(hgn_dflash_island_end);if(end<=original||end-original>131072)return cold::Result::IslandRejected;
    auto mapped=(end-original+page-1)&~(page-1);auto* allocation=near_map(mapped);if(!allocation)return cold::Result::MapFailed;
    auto copied=u64(allocation);copy(allocation,hgn_dflash_island_begin,end-original);
    auto relocate=[=](const void* pointer)noexcept{auto p=u64(pointer);if(p<original||p>=end)fatal();return copied+p-original;};
    auto tls=i64(u64(&hgn_dflash_stack_bounds)-u64(__builtin_thread_pointer()));
    for(const auto& pin:pins){relay::Configuration config{};config.enabled=args->optional_provider;config.xsave_bytes=xsave_bytes;
        config.xcr0_mask=xcr0;config.required_stack_below_original_rsp=required_stack;config.stack_tls_offset=tls;
        config.callback=&hgn_dflash_ready_callback;config.loss_counter=&args->lane->loss;config.runtime_enabled=&optional_enabled;
        config.in_flight_counter=&in_flight;config.lane=args->lane;config.provider=args->provider;
        copy(reinterpret_cast<void*>(relocate(pin.config)),&config,sizeof(config));
        if(!relative(relocate(pin.stock),image_base+pin.resume,true)||!relative(image_base+pin.rva+1,relocate(pin.begin),false))fatal();
    }
    if(!relative(relocate(hgn_dflash_relay_0_ready_delta),image_base+0x173fd86,true)
       ||!relative(relocate(hgn_dflash_relay_0_scalar_delta),image_base+0x1740408,true))fatal();
    auto frames=relocate(hgn_dflash_island_frames),frames_end=copied+u64(hgn_dflash_island_frames_end)-original;
    if(!verify_frames(original,copied,frames,frames_end)||syscall6(10,long(copied),long(mapped),5)!=0)fatal();
    __register_frame(reinterpret_cast<void*>(frames));
    for(const auto& pin:pins){DwarfBases bases{};auto pc=relocate(pin.begin);auto fde=u64(_Unwind_Find_FDE(reinterpret_cast<const void*>(pc),&bases));
        if(fde<frames||fde+17>frames_end||u64(bases.function)!=pc)fatal();}
    // Cold single-thread publication: every range/pin/FDE is checked first.
    // Any failure after publication begins exits rather than running partial gates.
    for(const auto& pin:pins){auto address=image_base+pin.rva,base=address&~(page-1);
        if(address+pin.bytes>base+page||!equal(reinterpret_cast<const void*>(address),pin.original,pin.bytes)
           ||syscall6(10,long(base),page,3)!=0)fatal();
        u8 patch[7]={0xe9,0,0,0,0,0x90,0x90};auto delta=i32(i64(relocate(pin.begin))-i64(address+5));copy(patch+1,&delta,4);
        copy(reinterpret_cast<void*>(address),patch,pin.bytes);if(syscall6(10,long(base),page,5)!=0)fatal();
    }
    installed=1;atomic_store(optional_enabled,u8(args->optional_provider));return cold::Result::Installed;
}
extern "C" __attribute__((visibility("default")))
bool hgn_dflash_register_current_stack(u64 low,u64 high)noexcept{
    hgn_dflash_stack_bounds={};if(!installed||!xsave_bytes)return false;
    u64 rsp;asm volatile("movq %%rsp,%0":"=r"(rsp));u32 bytes{};u64 mask{};
    if(!low||high<=low||rsp<low||rsp>=high||rsp-low<required_stack||!cpu_state(bytes,mask)||bytes!=xsave_bytes||mask!=xcr0)return false;
    hgn_dflash_stack_bounds={low,high};return true;
}
extern "C" __attribute__((visibility("default"))) void hgn_dflash_disable_optional()noexcept{atomic_store(optional_enabled,u8(0));}
extern "C" __attribute__((visibility("default"))) bool hgn_dflash_optional_drained()noexcept{return atomic_load(in_flight)==0;}
