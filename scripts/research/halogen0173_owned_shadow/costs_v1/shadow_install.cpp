// Linux x86-64, exact 0.17.3 cold-start preload. No running-process installer.
#include "shadow_collector.h"
#include <algorithm>
#include <alloca.h>
#include <atomic>
#include <cerrno>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <dlfcn.h>
#include <elf.h>
#include <fcntl.h>
#include <link.h>
#include <openssl/evp.h>
#include <pthread.h>
#include <sys/mman.h>
#include <sys/random.h>
#include <sys/stat.h>
#include <unistd.h>
#if !defined(__linux__) || !defined(__x86_64__)
#error "owned shadow preload requires Linux x86-64"
#endif

using halogen0173::shadow::Collector;
using halogen0173::shadow::Event;
using halogen0173::shadow::CostEvent;
using halogen0173::shadow::Frame;
using halogen0173::shadow::Site;
struct ShadowStackBounds { std::uint64_t low,high; };
extern "C" {
__thread ShadowStackBounds hgn_shadow_stack_bounds __attribute__((tls_model("initial-exec")))={};
void __register_frame(void*);
extern unsigned char hgn_shadow_island_begin[],hgn_shadow_island_end[],hgn_shadow_island_frames[],hgn_shadow_island_frames_end[];
#define DECLARE_RELAY(i) extern unsigned char hgn_shadow_relay_##i##_begin[],hgn_shadow_relay_##i##_code_end[],hgn_shadow_relay_##i##_config[],hgn_shadow_relay_##i##_resume_delta[];
DECLARE_RELAY(0) DECLARE_RELAY(1) DECLARE_RELAY(2) DECLARE_RELAY(3) DECLARE_RELAY(4)
DECLARE_RELAY(5) DECLARE_RELAY(6) DECLARE_RELAY(7) DECLARE_RELAY(8)
extern unsigned char hgn_shadow_relay_4_branch_delta[],hgn_shadow_relay_8_branch_delta[];
struct ShadowDwarfBases { void* text; void* data; void* function; };
const void* _Unwind_Find_FDE(const void*,ShadowDwarfBases*);
}
namespace {
static Collector collector;
using PthreadCreate=int(*)(pthread_t*,const pthread_attr_t*,void*(*)(void*),void*);
static PthreadCreate original_create;
static bool active,full_elf_verified,native_pins_verified;
static unsigned installed_sites;
static std::atomic<int> journal{-1};
static int cost_journal=-1;
static bool costs_enabled;
static char journal_path[PATH_MAX],status_path[PATH_MAX],nonce_hex[33];
static char cost_journal_path[PATH_MAX];
static std::atomic<bool> writer_stop{false};
static std::atomic<std::uint64_t> relay_inflight{0};
static pthread_t writer_thread;
static std::uint64_t written_events;
static std::uint64_t written_cost_events,cost_timing_failures;
static std::uint32_t xsave_bytes;
static std::uint64_t xcr0;
constexpr std::size_t kPage=4096;
struct RelayConfig { std::uint32_t enabled,xsave_bytes; std::uint64_t xcr0,required_stack,tls_offset,callback,loss_counter,runtime_enabled,inflight_counter; };
static_assert(sizeof(RelayConfig)==64);
static_assert(std::atomic<std::uint64_t>::is_always_lock_free && std::atomic<bool>::is_always_lock_free && sizeof(std::atomic<std::uint64_t>)==8 && sizeof(std::atomic<bool>)==1);
struct Pin { std::uintptr_t rva; std::size_t bytes; std::array<std::uint8_t,10> original; unsigned char* relay; unsigned char* config; unsigned char* resume; unsigned char* branch; std::uintptr_t branch_target; };
#define RELAY(i) hgn_shadow_relay_##i##_begin,hgn_shadow_relay_##i##_config,hgn_shadow_relay_##i##_resume_delta
static const Pin pins[] = {
 {0x1732c7e,8,{0x48,0x8d,0xbc,0x24,0xd0,0x01,0,0},RELAY(0),nullptr,0},
 {0x173d711,8,{0x48,0x8d,0xbc,0x24,0xd0,0x01,0,0},RELAY(1),nullptr,0},
 {0x1740844,8,{0x41,0x0f,0xb6,0xb1,0xb0,0x01,0,0},RELAY(2),nullptr,0},
 {0x17413ff,5,{0x48,0x8b,0x44,0x24,0x10},RELAY(3),nullptr,0},
 {0x17411fb,5,{0x83,0xf8,0xfe,0x75,0x70},RELAY(4),hgn_shadow_relay_4_branch_delta,0x1741270},
 {0x1770630,5,{0x41,0x57,0x41,0x56,0x53},RELAY(5),nullptr,0},
 {0x1800fc0,5,{0x55,0x41,0x57,0x41,0x56},RELAY(6),nullptr,0},
 {0x1805290,8,{0x50,0x48,0x63,0x87,0xc8,0,0,0},RELAY(7),nullptr,0},
 {0x1746470,10,{0x83,0x7f,0x48,0,0x0f,0x84,0x44,0x02,0,0},RELAY(8),hgn_shadow_relay_8_branch_delta,0x17466be}
};
static const unsigned char* code_ends[]={hgn_shadow_relay_0_code_end,hgn_shadow_relay_1_code_end,hgn_shadow_relay_2_code_end,hgn_shadow_relay_3_code_end,hgn_shadow_relay_4_code_end,hgn_shadow_relay_5_code_end,hgn_shadow_relay_6_code_end,hgn_shadow_relay_7_code_end,hgn_shadow_relay_8_code_end};
bool write_all(int fd,const void* p,std::size_t bytes) noexcept {
    const auto* at=static_cast<const std::uint8_t*>(p);
    while(bytes) { auto n=write(fd,at,bytes); if(n<0 && errno==EINTR) continue; if(n<=0) return false; at+=n; bytes-=static_cast<std::size_t>(n); }
    return true;
}
void status(const char* error,bool enabled) noexcept {
    if(!status_path[0]) return;
    const int fd=open(status_path,O_WRONLY|O_CREAT|O_TRUNC|O_CLOEXEC|O_NOFOLLOW,0600);
    if(fd<0) return;
    char json[1024]; const int n=std::snprintf(json,sizeof(json),
      "{\"schema\":\"halogen0173.owned-shadow.install.v1\",\"runtime_sha256\":\"%s\",\"session_nonce\":\"%s\",\"full_elf_verified\":%s,\"native_pins_verified\":%s,\"installed_sites\":%u,\"capture_enabled\":%s,\"cost_capture_enabled\":%s,\"cost_schema\":\"halogen0173.shadow-cost.v1\",\"cost_clock\":\"CLOCK_MONOTONIC_RAW\",\"error\":\"%s\"}\n",
      halogen0173::shadow::kRuntimeSha256,nonce_hex,full_elf_verified?"true":"false",native_pins_verified?"true":"false",installed_sites,enabled?"true":"false",costs_enabled?"true":"false",error);
    if(n>0 && static_cast<std::size_t>(n)<sizeof(json)) { write_all(fd,json,n); fsync(fd); } close(fd);
}
[[noreturn]] void fail(const char* reason) noexcept { status(reason,false); dprintf(2,"halogen0173 owned-shadow startup failed: %s\n",reason); _exit(127); }
struct Cpu { unsigned a,b,c,d; };
Cpu cpuid(unsigned leaf,unsigned sub=0) noexcept { Cpu v{}; asm volatile("cpuid":"=a"(v.a),"=b"(v.b),"=c"(v.c),"=d"(v.d):"a"(leaf),"c"(sub)); return v; }
bool cpu_state(std::uint32_t& bytes,std::uint64_t& mask) noexcept {
    const auto top=cpuid(0),features=cpuid(1);
    if(top.a<13 || (features.c&((1u<<26)|(1u<<27)))!=((1u<<26)|(1u<<27))) return false;
    unsigned lo,hi; asm volatile("xgetbv":"=a"(lo),"=d"(hi):"c"(0)); mask=(std::uint64_t{hi}<<32)|lo;
    const auto d=cpuid(13); bytes=d.b;
    const auto supported=(std::uint64_t{d.d}<<32)|d.a;
    if((mask&3)!=3 || (mask&~supported) || (mask&~std::uint64_t{0x2e7}) || bytes<576 || bytes>65536) return false;
    const bool amd=top.b==0x68747541 && top.d==0x69746e65 && top.c==0x444d4163;
    const bool intel=top.b==0x756e6547 && top.d==0x49656e69 && top.c==0x6c65746e;
    if(!amd && !intel) return false;
    if(amd && (cpuid(0x80000000).a<0x80000008 || !(cpuid(0x80000008).b&(1u<<2)))) return false;
    for(unsigned bit=2;bit<64;++bit) if(mask&(std::uint64_t{1}<<bit)) {
        const auto component=cpuid(13,bit);
        if(!component.a || component.b<576 || (component.c&1) || std::uint64_t{component.b}+component.a>bytes) return false;
    }
    return true;
}
void register_stack() {
    hgn_shadow_stack_bounds={};
    std::uint32_t bytes{}; std::uint64_t mask{};
    if(!cpu_state(bytes,mask) || bytes!=xsave_bytes || mask!=xcr0) return;
    pthread_attr_t attr; void* begin=nullptr; std::size_t size=0;
    if(pthread_getattr_np(pthread_self(),&attr)) return;
    const int result=pthread_attr_getstack(&attr,&begin,&size); pthread_attr_destroy(&attr);
    if(result || !begin || size>UINTPTR_MAX-reinterpret_cast<std::uintptr_t>(begin)) return;
    const auto rsp=reinterpret_cast<std::uintptr_t>(&attr),low=reinterpret_cast<std::uintptr_t>(begin),high=low+size;
    // Grow a demand-mapped main stack while cold, within the stack extent
    // reported by pthread attributes. Touch each page; do not weaken admission.
    // The extra 64KiB covers the later native handler and registration call tree.
    const std::size_t commit=std::size_t{xsave_bytes}+65536+1048576+512+65536;
    if(rsp<low || rsp-low<commit+8192) return;
    auto* committed=static_cast<volatile unsigned char*>(alloca(commit));
    for(std::size_t i=0;i<commit;i+=kPage) committed[i]=0;
    committed[commit-1]=0;
    FILE* maps=std::fopen("/proc/self/maps","r"); if(!maps) return;
    char line[1024],perms[8]; unsigned long a,b;
    while(std::fgets(line,sizeof(line),maps)) if(std::sscanf(line,"%lx-%lx %7s",&a,&b,perms)==3 && a<=rsp && rsp<b && !std::strcmp(perms,"rw-p")) {
        hgn_shadow_stack_bounds={std::max<std::uint64_t>(low,a),std::min<std::uint64_t>(high,b)}; break;
    }
    std::fclose(maps);
}
struct Start { void*(*function)(void*); void* argument; };
void* thread_start(void* opaque) {
    auto item=*static_cast<Start*>(opaque); free(opaque); const int saved=errno; register_stack(); errno=saved; return item.function(item.argument);
}
std::uintptr_t main_base;
int main_image(dl_phdr_info* info,std::size_t,void*) noexcept {
    if(info->dlpi_name && info->dlpi_name[0]) return 0;
    main_base=info->dlpi_addr;
    for(const auto& pin:pins) {
        bool matched=false;
        for(unsigned j=0;j<info->dlpi_phnum;++j) { const auto& p=info->dlpi_phdr[j];
            if(p.p_type==PT_LOAD && (p.p_flags&(PF_R|PF_X|PF_W))==(PF_R|PF_X) && pin.rva>=p.p_vaddr && pin.rva+pin.bytes<=p.p_vaddr+p.p_filesz && p.p_offset+pin.rva-p.p_vaddr==pin.rva-0x1000) matched=true;
        }
        if(!matched) fail("native-site-segment");
    }
    return 1;
}
void verify_elf() noexcept {
    const int fd=open("/proc/self/exe",O_RDONLY|O_CLOEXEC); struct stat before{},after{}; Elf64_Ehdr eh{};
    if(fd<0 || fstat(fd,&before) || !S_ISREG(before.st_mode) || before.st_size!=26188824 || pread(fd,&eh,sizeof(eh),0)!=sizeof(eh)) fail("native-elf-stat");
    if(std::memcmp(eh.e_ident,ELFMAG,4) || eh.e_ident[EI_CLASS]!=ELFCLASS64 || eh.e_ident[EI_DATA]!=ELFDATA2LSB || eh.e_machine!=EM_X86_64 || eh.e_type!=ET_DYN) fail("native-elf-header");
    auto* md=EVP_MD_CTX_new(); if(!md || EVP_DigestInit_ex(md,EVP_sha256(),nullptr)!=1) fail("sha-init");
    unsigned char buffer[65536],digest[32]; off_t offset=0;
    while(offset<before.st_size) { const auto wanted=std::min<std::size_t>(sizeof(buffer),before.st_size-offset); auto got=pread(fd,buffer,wanted,offset); if(got<0 && errno==EINTR) continue; if(got<=0 || EVP_DigestUpdate(md,buffer,got)!=1) fail("sha-read"); offset+=got; }
    unsigned n=0; if(EVP_DigestFinal_ex(md,digest,&n)!=1 || n!=32) fail("sha-final"); EVP_MD_CTX_free(md);
    char hex[65]; for(unsigned i=0;i<32;++i) std::snprintf(hex+2*i,3,"%02x",digest[i]);
    if(std::strcmp(hex,halogen0173::shadow::kRuntimeSha256)) { fail("native-elf-sha256"); }
    full_elf_verified=true;
    if(dl_iterate_phdr(main_image,nullptr)!=1 || !main_base) fail("native-main-image");
    for(const auto& pin:pins) {
        unsigned char raw[10]; if(pread(fd,raw,pin.bytes,pin.rva-0x1000)!=static_cast<ssize_t>(pin.bytes) || std::memcmp(raw,pin.original.data(),pin.bytes) || std::memcmp(reinterpret_cast<const void*>(main_base+pin.rva),raw,pin.bytes)) fail("native-instruction-pin");
    }
    if(fstat(fd,&after) || before.st_dev!=after.st_dev || before.st_ino!=after.st_ino || before.st_size!=after.st_size || before.st_mtim.tv_sec!=after.st_mtim.tv_sec || before.st_mtim.tv_nsec!=after.st_mtim.tv_nsec || before.st_ctim.tv_sec!=after.st_ctim.tv_sec || before.st_ctim.tv_nsec!=after.st_ctim.tv_nsec || close(fd)) fail("native-file-changed");
    native_pins_verified=true;
}
void relative32(std::uintptr_t field,std::uintptr_t target) noexcept {
    const auto delta=static_cast<std::int64_t>(target)-static_cast<std::int64_t>(field+4);
    if(delta<INT32_MIN || delta>INT32_MAX) { fail("relay-rel32-range"); }
    const auto d=static_cast<std::int32_t>(delta); std::memcpy(reinterpret_cast<void*>(field),&d,4);
}
template<class T> T island_value(std::uintptr_t at) noexcept { T value{}; std::memcpy(&value,reinterpret_cast<const void*>(at),sizeof(value)); return value; }
void verify_frames(std::uintptr_t original,std::uintptr_t copied,std::uintptr_t frames,std::uintptr_t frames_end) noexcept {
    constexpr unsigned char cie_prefix[]{1,'z','R',0,1,0x78,16,1,0x1b};
    std::array<bool,9> found{}; unsigned count=0; auto at=frames;
    while(at+4<=frames_end) {
        const auto length=island_value<std::uint32_t>(at);
        if(!length) { if(at+4!=frames_end || count!=9) fail("relay-fde-terminator"); return; }
        if(length==UINT32_MAX || length<13 || length>frames_end-at-4) fail("relay-fde-length");
        const auto id=island_value<std::uint32_t>(at+4);
        if(!id) {
            if(length<17 || std::memcmp(reinterpret_cast<const void*>(at+8),cie_prefix,sizeof(cie_prefix))) fail("relay-cie-encoding");
        } else {
            const auto cie=at+4-id;
            if(cie<frames || cie>=at || island_value<std::uint32_t>(cie+4)!=0) fail("relay-fde-cie");
            const auto begin=static_cast<std::uintptr_t>(static_cast<std::int64_t>(at+8)+island_value<std::int32_t>(at+8));
            const auto extent=island_value<std::uint32_t>(at+12); bool matched=false;
            for(unsigned i=0;i<9;++i) if(begin==copied+reinterpret_cast<std::uintptr_t>(pins[i].relay)-original && begin+extent==copied+reinterpret_cast<std::uintptr_t>(code_ends[i])-original && !found[i]) { found[i]=true; ++count; matched=true; }
            if(!matched) fail("relay-fde-code-range");
        }
        at+=4+length;
    }
    fail("relay-fde-no-terminator");
}
void* near_island(std::size_t bytes) noexcept {
    const auto anchor=(main_base+0x1740000)&~std::uintptr_t{kPage-1};
    for(unsigned i=1;i<=256;++i) for(int sign:{1,-1}) {
        const auto candidate=static_cast<std::int64_t>(anchor)+std::int64_t{sign}*i*0x200000;
        if(candidate<65536 || candidate>INT64_MAX-static_cast<std::int64_t>(bytes)) continue;
        auto* p=mmap(reinterpret_cast<void*>(candidate),bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
        if(p!=MAP_FAILED) { if(reinterpret_cast<std::uintptr_t>(p)!=static_cast<std::uintptr_t>(candidate)) fail("relay-map-address"); return p; }
    }
    fail("relay-near-map");
}
bool close_requested() noexcept {
    char path[PATH_MAX]; if(std::snprintf(path,sizeof(path),"%s.close-request",journal_path)>=PATH_MAX) return false;
    const int fd=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW); if(fd<0) return false;
    char content[34]; const auto n=read(fd,content,sizeof(content)); close(fd);
    return (n==32 || (n==33 && content[32]=='\n')) && !std::memcmp(content,nonce_hex,32);
}
void close_receipt(bool io_ok,bool cost_io_ok,std::uint64_t dropped,std::uint64_t live,std::uint64_t pending) noexcept {
    char path[PATH_MAX],json[1536];
    const int path_size=std::snprintf(path,sizeof(path),"%s.close.json",journal_path);
    if(path_size<0 || path_size>=PATH_MAX) return;
    const int fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600); if(fd<0) return;
    const bool qualified=io_ok && dropped==0 && live==0 && pending==0 && relay_inflight.load()==0;
    const int n=std::snprintf(json,sizeof(json),"{\"schema\":\"halogen0173.owned-shadow.close.v1\",\"session_nonce\":\"%s\",\"closed\":%s,\"qualified_close\":%s,\"written_events\":%llu,\"dropped_cumulative\":%llu,\"live_owners\":%llu,\"pending_rounds\":%llu,\"relay_inflight\":%llu,\"cost_capture_enabled\":%s,\"cost_closed\":%s,\"cost_qualified_close\":%s,\"written_cost_events\":%llu,\"cost_timing_failures\":%llu}\n",nonce_hex,io_ok?"true":"false",qualified?"true":"false",static_cast<unsigned long long>(written_events),static_cast<unsigned long long>(dropped),static_cast<unsigned long long>(live),static_cast<unsigned long long>(pending),static_cast<unsigned long long>(relay_inflight.load()),costs_enabled?"true":"false",costs_enabled && cost_io_ok?"true":"false",costs_enabled && qualified && cost_io_ok && cost_timing_failures==0?"true":"false",static_cast<unsigned long long>(written_cost_events),static_cast<unsigned long long>(cost_timing_failures));
    if(n>0 && static_cast<std::size_t>(n)<sizeof(json)) { write_all(fd,json,n); fsync(fd); } close(fd);
}
void* writer(void*) {
    bool io_ok=true,cost_io_ok=true,closing=false;
    for(;;) {
        if(!closing && (writer_stop.load() || close_requested())) { collector.disable(); closing=true; }
        Event event{}; CostEvent cost{};
        while(collector.drain(event,cost)) {
            io_ok&=write_all(journal,&event,sizeof(event)); ++written_events;
            if(costs_enabled && (cost.kind==halogen0173::shadow::Kind::Begin || cost.kind==halogen0173::shadow::Kind::Outcome)) {
                cost_io_ok&=write_all(cost_journal,&cost,sizeof(cost)); ++written_cost_events;
                if(cost.flags!=halogen0173::shadow::CostClockValid) ++cost_timing_failures;
            }
        }
        if(closing) {
            std::uint64_t dropped{},live{},pending{};
            if(relay_inflight.load(std::memory_order_acquire)==0 && collector.close_counts(dropped,live,pending)) {
                io_ok&=(fsync(journal)==0); io_ok&=(close(journal)==0); journal=-1;
                if(costs_enabled) { cost_io_ok&=(fsync(cost_journal)==0); cost_io_ok&=(close(cost_journal)==0); cost_journal=-1; }
                close_receipt(io_ok,cost_io_ok,dropped,live,pending); return nullptr;
            }
        }
        if(!io_ok || !cost_io_ok) { collector.disable(); closing=true; }
        usleep(20000);
    }
}
} // namespace

// Compile with -fcf-protection=branch; startup verifies the real target ENDBR64.
extern "C" __attribute__((visibility("hidden"),noinline))
void hgn_owned_shadow_callback(std::uint32_t site,const void* capture) noexcept {
    const int saved=errno; Frame frame{}; std::memcpy(frame.gpr.data(),capture,sizeof(frame.gpr));
    collector.on_site(static_cast<Site>(site),frame); errno=saved;
}
extern "C" int pthread_create(pthread_t* thread,const pthread_attr_t* attr,void*(*function)(void*),void* argument) {
    // Another DSO constructor may call this before our constructor runs.
    // Resolve and forward stock behavior even while this adapter is disabled.
    if(!original_create) {
        const int saved=errno;
        const auto resolved=reinterpret_cast<PthreadCreate>(dlsym(RTLD_NEXT,"pthread_create"));
        errno=saved;
        if(!resolved) return ENOSYS;
        if(!active) return resolved(thread,attr,function,argument);
        original_create=resolved;
    }
    if(!active) return original_create(thread,attr,function,argument);
    const int saved=errno; auto* item=static_cast<Start*>(malloc(sizeof(Start))); if(!item) { errno=saved; return ENOMEM; }
    *item={function,argument}; errno=saved; const int result=original_create(thread,attr,thread_start,item);
    const int after=errno; if(result) free(item); errno=after; return result;
}
__attribute__((constructor)) static void start_shadow() {
    original_create=reinterpret_cast<PthreadCreate>(dlsym(RTLD_NEXT,"pthread_create"));
    const char* enable=getenv("HALOGEN0173_SHADOW"); if(!enable || std::strcmp(enable,"owned-ledger-v1")) return;
    char executable[PATH_MAX]; const auto len=readlink("/proc/self/exe",executable,sizeof(executable)-1);
    if(len<=0) { return; }
    executable[len]=0; const auto* base=std::strrchr(executable,'/'); if(std::strcmp(base?base+1:executable,"flash_serve")) return;
    // Normal entrypoint invokes this exact native binary for the resident probe
    // before the serving process. It must not claim journal or status paths.
    char command[4096]; const int command_fd=open("/proc/self/cmdline",O_RDONLY|O_CLOEXEC);
    const auto command_n=command_fd<0?-1:read(command_fd,command,sizeof(command)); if(command_fd>=0) close(command_fd);
    if(command_n>0) {
        const auto first=strnlen(command,static_cast<std::size_t>(command_n));
        if(first<static_cast<std::size_t>(command_n)) {
            const auto* argument=command+first+1;
            const auto remaining=static_cast<std::size_t>(command_n)-first-1;
            constexpr char resident[]="--resident-gib";
            if(remaining>=sizeof(resident) && !std::memcmp(argument,resident,sizeof(resident))) return;
        }
    }
    const auto* path=getenv("HALOGEN0173_SHADOW_JOURNAL"),*status_env=getenv("HALOGEN0173_SHADOW_STATUS");
    if(!path || path[0]!='/' || std::strlen(path)>PATH_MAX-32) { fail("journal-path"); }
    std::strcpy(journal_path,path);
    if(status_env) { if(status_env[0]!='/' || std::strlen(status_env)>=PATH_MAX) fail("status-path"); std::strcpy(status_path,status_env); }
    else std::snprintf(status_path,sizeof(status_path),"%s.status.json",journal_path);
    const auto* cost_mode=getenv("HALOGEN0173_SHADOW_COSTS");
    if(cost_mode) {
        if(std::strcmp(cost_mode,"monotonic-raw-v1")) fail("cost-mode");
        const auto* cost_path=getenv("HALOGEN0173_SHADOW_COST_JOURNAL");
        if(!cost_path || cost_path[0]!='/' || std::strlen(cost_path)>=PATH_MAX ||
           !std::strcmp(cost_path,journal_path) || !std::strcmp(cost_path,status_path)) fail("cost-journal-path");
        std::strcpy(cost_journal_path,cost_path); costs_enabled=true;
    }
    if(!original_create) fail("pthread-create-resolution");
    DIR* tasks=opendir("/proc/self/task"); if(!tasks) fail("startup-task-inventory"); unsigned task_count=0; while(auto* entry=readdir(tasks)) if(entry->d_name[0]!='.') ++task_count; closedir(tasks); if(task_count!=1) fail("startup-not-single-thread");
    verify_elf(); if(!cpu_state(xsave_bytes,xcr0)) fail("xsave-state"); register_stack(); if(!hgn_shadow_stack_bounds.low || hgn_shadow_stack_bounds.high<=hgn_shadow_stack_bounds.low) fail("main-stack-bounds");
    const std::array<unsigned char,4> endbr{0xf3,0x0f,0x1e,0xfa}; if(std::memcmp(reinterpret_cast<const void*>(&hgn_owned_shadow_callback),endbr.data(),4)) fail("callback-ibt-entry");
    std::array<std::uint8_t,16> nonce{}; if(getrandom(nonce.data(),nonce.size(),0)!=static_cast<ssize_t>(nonce.size())) fail("session-nonce");
    for(unsigned i=0;i<16;++i) std::snprintf(nonce_hex+2*i,3,"%02x",nonce[i]);
    journal=open(journal_path,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600); if(journal<0) fail("journal-open");
    if(!collector.configure(true,nonce,costs_enabled)) { fail("collector-configure"); }
    const auto header=collector.header(); if(!write_all(journal,&header,sizeof(header))) fail("journal-header");
    if(costs_enabled) {
        cost_journal=open(cost_journal_path,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
        if(cost_journal<0) fail("cost-journal-open");
        const auto cost_header=collector.cost_header();
        if(!write_all(cost_journal,&cost_header,sizeof(cost_header))) fail("cost-journal-header");
    }
    const auto original=reinterpret_cast<std::uintptr_t>(hgn_shadow_island_begin),end=reinterpret_cast<std::uintptr_t>(hgn_shadow_island_end);
    if(end<=original || end-original>131072) { fail("relay-island-size"); }
    const auto mapped_bytes=(end-original+kPage-1)&~std::uintptr_t{kPage-1};
    auto* allocation=near_island(mapped_bytes); const auto copy=reinterpret_cast<std::uintptr_t>(allocation); std::memcpy(allocation,hgn_shadow_island_begin,end-original);
    const auto relocate=[=](const unsigned char* p) { const auto value=reinterpret_cast<std::uintptr_t>(p); if(value<original || value>=end) fail("relay-symbol-range"); return copy+value-original; };
    const auto tls_offset=reinterpret_cast<std::uintptr_t>(&hgn_shadow_stack_bounds)-reinterpret_cast<std::uintptr_t>(__builtin_thread_pointer());
    for(const auto& pin:pins) {
        const RelayConfig cfg{1,xsave_bytes,xcr0,std::uint64_t{xsave_bytes}+65536+1048576+512,tls_offset,reinterpret_cast<std::uintptr_t>(&hgn_owned_shadow_callback),reinterpret_cast<std::uintptr_t>(collector.loss_counter_address()),reinterpret_cast<std::uintptr_t>(collector.enabled_address()),reinterpret_cast<std::uintptr_t>(&relay_inflight)};
        std::memcpy(reinterpret_cast<void*>(relocate(pin.config)),&cfg,sizeof(cfg)); relative32(relocate(pin.resume),main_base+pin.rva+pin.bytes);
        if(pin.branch) relative32(relocate(pin.branch),main_base+pin.branch_target);
        const auto distance=static_cast<std::int64_t>(relocate(pin.relay))-static_cast<std::int64_t>(main_base+pin.rva+5); if(distance<INT32_MIN || distance>INT32_MAX) fail("native-to-relay-range");
    }
    const auto frames=relocate(hgn_shadow_island_frames);
    const auto frames_end=copy+reinterpret_cast<std::uintptr_t>(hgn_shadow_island_frames_end)-original;
    verify_frames(original,copy,frames,frames_end);
    if(mprotect(allocation,mapped_bytes,PROT_READ|PROT_EXEC)) { fail("relay-rx"); }
    __register_frame(reinterpret_cast<void*>(frames));
    for(const auto& pin:pins) {
        ShadowDwarfBases bases{}; const auto pc=relocate(pin.relay);
        const auto fde=reinterpret_cast<std::uintptr_t>(_Unwind_Find_FDE(reinterpret_cast<const void*>(pc),&bases));
        if(fde<frames || fde+17>frames_end || reinterpret_cast<std::uintptr_t>(bases.function)!=pc) fail("relay-fde-registration");
    }
    for(const auto& pin:pins) {
        const auto address=main_base+pin.rva,page=address&~std::uintptr_t{kPage-1};
        if(address+pin.bytes>page+kPage || std::memcmp(reinterpret_cast<const void*>(address),pin.original.data(),pin.bytes)) fail("native-pin-before-publication");
        if(mprotect(reinterpret_cast<void*>(page),kPage,PROT_READ|PROT_WRITE)) fail("native-site-rw");
        std::array<std::uint8_t,10> patch{}; patch.fill(0x90); patch[0]=0xe9; const auto d=static_cast<std::int32_t>(static_cast<std::int64_t>(relocate(pin.relay))-static_cast<std::int64_t>(address+5)); std::memcpy(patch.data()+1,&d,4); std::memcpy(reinterpret_cast<void*>(address),patch.data(),pin.bytes);
        if(mprotect(reinterpret_cast<void*>(page),kPage,PROT_READ|PROT_EXEC)) { fail("native-site-rx"); }
        ++installed_sites;
    }
    active=true;
    if(original_create(&writer_thread,nullptr,writer,nullptr)) fail("journal-writer-start");
    status("",true);
}
__attribute__((destructor)) static void finish_shadow() {
    if(!active || journal<0) { return; }
    writer_stop.store(true); pthread_join(writer_thread,nullptr);
}
