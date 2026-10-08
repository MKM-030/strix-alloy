#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "../ple0172-native-ordinary-first-lookup-v1/ordinary_first_lookup_0172.h"
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cerrno>
#include <climits>
#include <elf.h>
#include <fcntl.h>
#include <link.h>
#include <openssl/evp.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#if !defined(__linux__) || !defined(__x86_64__)
#error Exact Linux x86-64 engine required
#endif
namespace {
constexpr std::uint64_t engine_bytes=26178504;
constexpr char engine_sha[]="ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913";
constexpr std::uintptr_t seam_rva=0x17ec18c, fallback_rva=0x17ec196, complete_rva=0x17ec959;
constexpr unsigned char overwritten[10]={0x48,0x8b,0x04,0x24,0x48,0x3d,0xff,0x0f,0x00,0x00};
constexpr unsigned char complete_bytes[7]={0x48,0x8b,0x3d,0x58,0xd6,0x10,0x00};
std::uintptr_t engine_base{}, stock_replay{};
template<class T> T load(const void* pointer,std::size_t offset) noexcept {
    T value; std::memcpy(&value,static_cast<const unsigned char*>(pointer)+offset,sizeof(value));return value;
}
[[noreturn]] void fail(const char* reason) noexcept {
    dprintf(2,"[ple0172-page-order] abort %s errno=%d; no incomplete H2D\n",reason,errno);_exit(79);
}
bool readable(const void* pointer,std::uint64_t bytes,bool write=false) noexcept {
    const auto address=reinterpret_cast<std::uintptr_t>(pointer);
    if (!address || !bytes || bytes>UINTPTR_MAX-address) return false;
    FILE* file=std::fopen("/proc/self/maps","re");if (!file)return false;
    char line[4096],permissions[5];unsigned long low,high;bool found=false;
    while (std::fgets(line,sizeof line,file)) {
        if (std::sscanf(line,"%lx-%lx %4s",&low,&high,permissions)==3 &&
            address>=low && address+bytes<=high && permissions[0]=='r' && (!write || permissions[1]=='w')) {found=true;break;}
    }
    const bool error=std::ferror(file)!=0;const int closed=std::fclose(file);return found&&!error&&!closed;
}
bool selected_metadata(void* model,Ple0172OrdinaryContract& contract) noexcept {
    const auto* mapper=load<const void*>(model,0x2d0);
    if (!readable(mapper,16))return false;
    const auto* mapping=load<const unsigned char*>(mapper,0);
    const auto bytes=load<std::uint64_t>(mapper,8);
    if (!readable(mapping,bytes) || bytes<104 || load<std::uint32_t>(mapping,0)!=0x314e4748 ||
        load<std::uint32_t>(mapping,4)!=2 || load<std::uint64_t>(mapping,32)!=bytes)return false;
    const auto count=load<std::uint64_t>(mapping,8), directory=load<std::uint64_t>(mapping,16), data=load<std::uint64_t>(mapping,24);
    if (!count || count>10000 || directory!=104 || directory+count*160>data || data>bytes || data%64)return false;
    constexpr char name[]="layers.1.ple.ngram_embedding.weight";
    const auto* table=load<const void*>(model,0x758);
    const auto rows=load<std::uint64_t>(model,0x768);
    if (!rows || rows>(UINT64_MAX-67)/160)return false;
    const auto extent=((rows*160+63)&~std::uint64_t(63))+4;
    bool found=false;
    for (std::uint64_t i=0;i<count;++i) {
        const auto* entry=mapping+directory+i*160;
        if (std::memcmp(entry,name,sizeof name))continue;
        const auto d0=load<std::int64_t>(entry,104),d1=load<std::int64_t>(entry,112),d2=load<std::int64_t>(entry,120);
        const auto offset=load<std::uint64_t>(entry,136),length=load<std::uint64_t>(entry,144);
        if (found || load<std::uint32_t>(entry,96)!=10 || load<std::uint32_t>(entry,100)!=3 ||
            d0<=0 || d1<=0 || d2!=160 || std::uint64_t(d0)>UINT64_MAX/std::uint64_t(d1) ||
            std::uint64_t(d0)*std::uint64_t(d1)!=rows || offset<data || offset%64 || offset>bytes ||
            length!=extent || length>bytes-offset || mapping+offset!=table || load<std::uint32_t>(entry,156)!=0)return false;
        found=true;
    }
    if (!found)return false;
    contract.selected_mapper=mapper;contract.metadata_table=table;contract.metadata_rows=rows;
    contract.metadata_extent=extent;contract.mapping_base=mapping;contract.mapping_bytes=bytes;
    contract.metadata_dtype=10;contract.mapper_selection=PLE0172_MAPPER_DIRECT;return true;
}
struct Owner {void* model;const void* mapper;const void* mapping;std::uint64_t bytes;};
int stopping(void* opaque) noexcept {
    const auto& owner=*static_cast<Owner*>(opaque);
    if (__atomic_load_n(static_cast<unsigned char*>(owner.model)+0x318,__ATOMIC_ACQUIRE))return 1;
    return load<const void*>(owner.model,0x2d0)!=owner.mapper ||
        load<const void*>(owner.mapper,0)!=owner.mapping || load<std::uint64_t>(owner.mapper,8)!=owner.bytes ||
        load<std::uintptr_t>(owner.model,0x308)!=engine_base+0x174b0d0 ||
        load<std::uintptr_t>(owner.model,0x310)!=engine_base+0x174ab30;
}
void jump(unsigned char* buffer,std::uintptr_t target) noexcept {
    const unsigned char opcode[6]={0xff,0x25,0,0,0,0};std::memcpy(buffer,opcode,6);std::memcpy(buffer+6,&target,8);
}
int main_image(dl_phdr_info* info,std::size_t,void* opaque) noexcept {
    if (info->dlpi_name&&*info->dlpi_name)return 0;
    for (std::size_t i=0;i<info->dlpi_phnum;++i) {
        const auto& p=info->dlpi_phdr[i];
        if(p.p_type==PT_LOAD && p.p_flags==(PF_R|PF_X) && p.p_vaddr<=seam_rva &&
            complete_rva+sizeof complete_bytes<=p.p_vaddr+p.p_filesz &&
            p.p_offset+seam_rva-p.p_vaddr==seam_rva-0x1000) {
            *static_cast<std::uintptr_t*>(opaque)=info->dlpi_addr;return 1;
        }
    }
    return 0;
}
void verify_engine() {
    int fd=open("/proc/self/exe",O_RDONLY|O_CLOEXEC);struct stat before{},after{};
    if(fd<0 || fstat(fd,&before) || !S_ISREG(before.st_mode) || std::uint64_t(before.st_size)!=engine_bytes)fail("engine-stat");
    EVP_MD_CTX* context=EVP_MD_CTX_new();unsigned char buffer[65536],digest[32];unsigned length=0;
    if(!context || EVP_DigestInit_ex(context,EVP_sha256(),nullptr)!=1)fail("hash-init");
    std::uint64_t copied=0;
    while(copied<engine_bytes) {
        const auto amount=engine_bytes-copied<sizeof buffer?std::size_t(engine_bytes-copied):sizeof buffer;
        ssize_t got=pread(fd,buffer,amount,off_t(copied));
        if(got<0&&errno==EINTR)continue;
        if(got<=0||std::size_t(got)>amount||EVP_DigestUpdate(context,buffer,std::size_t(got))!=1)fail("hash-read");
        copied+=std::size_t(got);
    }
    if(EVP_DigestFinal_ex(context,digest,&length)!=1||length!=32)fail("hash-end");
    EVP_MD_CTX_free(context);
    char actual[65];for(unsigned i=0;i<32;++i)std::snprintf(actual+i*2,3,"%02x",digest[i]);
    if(std::strcmp(actual,engine_sha)||fstat(fd,&after)||before.st_dev!=after.st_dev||before.st_ino!=after.st_ino||
        before.st_size!=after.st_size||before.st_mtim.tv_sec!=after.st_mtim.tv_sec||before.st_mtim.tv_nsec!=after.st_mtim.tv_nsec||
        before.st_ctim.tv_sec!=after.st_ctim.tv_sec||before.st_ctim.tv_nsec!=after.st_ctim.tv_nsec||close(fd))fail("engine-changed");
    if(dl_iterate_phdr(main_image,&engine_base)!=1)fail("engine-load");
    if(!readable(reinterpret_cast<void*>(engine_base+seam_rva),sizeof overwritten)||
        std::memcmp(reinterpret_cast<void*>(engine_base+seam_rva),overwritten,sizeof overwritten)||
        std::memcmp(reinterpret_cast<void*>(engine_base+complete_rva),complete_bytes,sizeof complete_bytes))fail("seam-bytes");
}
}
extern "C" void ple0172_ordinary_seam();
extern "C" __attribute__((visibility("hidden"))) std::uintptr_t ple0172_ordinary_dispatch(void* frame,std::uint64_t* registers) noexcept {
    // GPR block is rax,rbx,rcx,rdx,rsi,rdi,rbp,r8,r9,r10,r11,r12,r13,r14,r15.
    const int incoming_errno=errno;auto* model=reinterpret_cast<void*>(registers[11]);
    // This private entry receives the original live native stack exclusively
    // from the pinned seam. Small decode lookups must not scan /proc mappings.
    const auto rows=load<std::uint64_t>(frame,0);
    if(rows<4096||rows>131072) {errno=incoming_errno;return stock_replay;}
    if(!readable(model,0x7c8)||!readable(frame,0x218,true)) {errno=incoming_errno;return stock_replay;}
    const auto ids=load<const void*>(frame,0x130);
    const auto end=load<std::uintptr_t>(frame,0x138);
    const auto first=reinterpret_cast<std::uintptr_t>(ids);
    const auto allocation=load<std::int32_t>(model,0x2d8);
    if(end<first||end-first!=rows*8||!readable(ids,rows*8)||allocation<=0||
        !readable(load<void*>(model,0x798),std::uint64_t(allocation)*2720,true)||
        load<std::uintptr_t>(model,0x308)!=engine_base+0x174b0d0||
        load<std::uintptr_t>(model,0x310)!=engine_base+0x174ab30) {errno=incoming_errno;return stock_replay;}
    Ple0172OrdinaryContract contract{};
    if(!selected_metadata(model,contract)) {errno=incoming_errno;return stock_replay;}
    Owner owner{model,contract.selected_mapper,contract.mapping_base,contract.mapping_bytes};
    contract.abi_version=1;contract.struct_bytes=sizeof contract;contract.enable_page_order=1;
    contract.qualification_mask=PLE0172_ALL_QUALIFIED;contract.native_model=model;
    contract.stop_cookie=&owner;contract.stop_requested=stopping;
    const int result=ple0172_ordinary_first_lookup(model,frame,&contract,std::uint32_t(registers[14]&255));
    if(result==PLE0172_ORDINARY_STOCK) {errno=incoming_errno;return stock_replay;}
    if(result!=PLE0172_ORDINARY_COMPLETE)fail("ordinary-copy-not-complete");
    const std::uint64_t stride=160;std::memcpy(static_cast<unsigned char*>(frame)+8,&stride,8);
    registers[6]=load<std::uint64_t>(frame,0xa8);
    dprintf(2,"[ple0172-page-order] complete rows=%llu; original GPU IDs/unpack/RMS/FC\n",static_cast<unsigned long long>(rows));
    errno=incoming_errno;return engine_base+complete_rva;
}
__attribute__((constructor)) static void install_ordinary() {
    const auto* enabled=std::getenv("PLE0172_ORDINARY_PAGE_ORDER");if(!enabled)return;
    char path[4096];ssize_t size=readlink("/proc/self/exe",path,sizeof path-1);if(size<0||std::size_t(size)>=sizeof path-1)fail("exe-name");
    path[size]=0;const auto* name=std::strrchr(path,'/');name=name?name+1:path;if(std::strcmp(name,"flash_serve"))return;
    if(std::strcmp(enabled,"1"))fail("enable-value");
    verify_engine();
    const long page_bytes=sysconf(_SC_PAGESIZE);if(page_bytes!=4096)fail("page-size");
    const auto entry=engine_base+seam_rva,page=entry&~std::uintptr_t(4095);unsigned char* relay=nullptr;
    for(unsigned i=0;i<256;++i) {
        const auto distance=std::uintptr_t(i/2+1)*0x200000;
        if((i&1)?page<distance:distance>UINTPTR_MAX-page)continue;
        const auto candidate=(i&1)?page-distance:page+distance;
        void* area=mmap(reinterpret_cast<void*>(candidate),4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
        if(area==MAP_FAILED){if(errno==EEXIST)continue;fail("relay-map");}
        if(area!=reinterpret_cast<void*>(candidate))fail("relay-address");
        relay=static_cast<unsigned char*>(area);break;
    }
    if(!relay)fail("relay-exhausted");
    jump(relay,reinterpret_cast<std::uintptr_t>(&ple0172_ordinary_seam));
    std::memcpy(relay+64,overwritten,sizeof overwritten);jump(relay+74,engine_base+fallback_rva);
    stock_replay=reinterpret_cast<std::uintptr_t>(relay+64);
    if(mprotect(relay,4096,PROT_READ|PROT_EXEC))fail("relay-rx");
    const auto displacement=std::intptr_t(reinterpret_cast<std::uintptr_t>(relay)-(entry+5));
    if(displacement<INT32_MIN||displacement>INT32_MAX)fail("relay-range");
    unsigned char patch[10]={0xe9,0,0,0,0,0x90,0x90,0x90,0x90,0x90};const auto relative=std::int32_t(displacement);std::memcpy(patch+1,&relative,4);
    if(mprotect(reinterpret_cast<void*>(page),4096,PROT_READ|PROT_WRITE))fail("seam-rw");
    std::memcpy(reinterpret_cast<void*>(entry),patch,sizeof patch);__builtin___clear_cache(reinterpret_cast<char*>(entry),reinterpret_cast<char*>(entry+10));
    if(mprotect(reinterpret_cast<void*>(page),4096,PROT_READ|PROT_EXEC))fail("seam-rx");
    dprintf(2,"[ple0172-page-order] attached ordinary seam 0x17ec18c on exact Halogen 0.17.2\n");
}
