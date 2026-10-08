#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "page_phase_0172.h"
#include "native_patch_0172.h"
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <map>
#include <memory>
#include <typeinfo>
#include <unistd.h>

namespace {
using namespace ple_native_page_0172;
Ple0172NativePatch patch;
std::atomic<bool> attached{};
std::atomic<unsigned> active_windows{};
using Throw = void(*)(void*,void*,void(*)(void*));
std::atomic<Throw> native_throw{};

template<class T> T load(const void* p,std::size_t offset=0) noexcept {
    T result;std::memcpy(&result,static_cast<const unsigned char*>(p)+offset,sizeof result);return result;
}
[[noreturn]] void fail(const char* reason) noexcept {
    dprintf(2,"[ple0172-native-page] abort %s errno=%d; no incomplete H2D\n",reason,errno);
    _exit(79);
}
bool readable(const void* pointer,std::uint64_t bytes,bool write=false) noexcept {
    const auto address=reinterpret_cast<std::uintptr_t>(pointer);
    if(!address || !bytes || bytes>UINTPTR_MAX-address)return false;
    FILE* f=std::fopen("/proc/self/maps","re");if(!f)return false;
    char line[4096],permissions[5];unsigned long low,high;bool found=false;
    auto cursor=address;const auto end=address+bytes;
    while(std::fgets(line,sizeof line,f)) {
        if(std::sscanf(line,"%lx-%lx %4s",&low,&high,permissions)!=3 || high<=cursor)continue;
        if(low>cursor || permissions[0]!='r' || (write&&permissions[1]!='w'))break;
        cursor=high;
        if(cursor>=end) {found=true;break;}
    }
    const bool error=std::ferror(f);const int closed=std::fclose(f);return found&&!error&&!closed;
}
bool overlap(const void* a,std::uint64_t an,const void* b,std::uint64_t bn) noexcept {
    const auto aa=reinterpret_cast<std::uintptr_t>(a),bb=reinterpret_cast<std::uintptr_t>(b);
    return an>UINTPTR_MAX-aa || bn>UINTPTR_MAX-bb || (aa<bb+bn&&bb<aa+an);
}
bool actual_table(void* model,ple_page::TableView& table) noexcept {
    const auto* native=load<const std::byte*>(model,0x758);
    const auto rows=load<std::uint64_t>(model,0x768);
    if(!native || !rows || rows>(UINT64_MAX-67)/160)return false;
    const auto address=reinterpret_cast<std::uintptr_t>(native);
    FILE* f=std::fopen("/proc/self/maps","re");if(!f)return false;
    char line[4096],permissions[5];unsigned long low,high,offset;bool found=false;
    unsigned major{},minor{},selected_major{},selected_minor{};
    unsigned long long inode{},selected_inode{};std::uintptr_t mapping_address{};
    while(std::fgets(line,sizeof line,f)) {
        if(std::sscanf(line,"%lx-%lx %4s %lx %x:%x %llu",&low,&high,permissions,&offset,&major,&minor,&inode)!=7 ||
            address<low || address>=high || permissions[0]!='r' || !inode || offset>low)continue;
        mapping_address=low-offset;selected_major=major;selected_minor=minor;selected_inode=inode;break;
    }
    if(mapping_address && readable(reinterpret_cast<const void*>(mapping_address),104)) {
        const auto* mapping=reinterpret_cast<const std::byte*>(mapping_address);
        const auto bytes=load<std::uint64_t>(mapping,32);
        bool contiguous=false;
        if(bytes>=104 && bytes<=UINT64_MAX-4095) {
            const auto rounded=(bytes+4095)&~std::uint64_t(4095);
            if(rounded<=UINTPTR_MAX-mapping_address) {
                auto cursor=mapping_address;const auto end=mapping_address+rounded;
                std::rewind(f);
                while(std::fgets(line,sizeof line,f)) {
                    if(std::sscanf(line,"%lx-%lx %4s %lx %x:%x %llu",&low,&high,permissions,&offset,&major,&minor,&inode)!=7 || high<=cursor)continue;
                    if(low!=cursor || high>end || permissions[0]!='r' || major!=selected_major ||
                        minor!=selected_minor || inode!=selected_inode || offset!=low-mapping_address)break;
                    cursor=high;if(cursor==end){contiguous=true;break;}
                }
            }
        }
        if(!contiguous || load<std::uint32_t>(mapping)!=0x314e4748 || load<std::uint32_t>(mapping,4)!=2) {
            std::fclose(f);return false;
        }
        const auto count=load<std::uint64_t>(mapping,8),directory=load<std::uint64_t>(mapping,16),data=load<std::uint64_t>(mapping,24);
        if(!count||count>10000||directory!=104||directory+count*160>data||data>bytes||data%64) {
            std::fclose(f);return false;
        }
        constexpr char name[]="layers.1.ple.ngram_embedding.weight";
        const auto extent=((rows*160+63)&~std::uint64_t(63))+4;
        for(std::uint64_t i=0;i<count;++i) {
            const auto* e=mapping+directory+i*160;
            if(std::memcmp(e,name,sizeof name))continue;
            const auto d0=load<std::int64_t>(e,104),d1=load<std::int64_t>(e,112),d2=load<std::int64_t>(e,120);
            const auto at=load<std::uint64_t>(e,136),length=load<std::uint64_t>(e,144);
            if(found || load<std::uint32_t>(e,96)!=10 || load<std::uint32_t>(e,100)!=3 ||
                d0<=0||d1<=0||d2!=160||std::uint64_t(d0)>UINT64_MAX/std::uint64_t(d1)||
                std::uint64_t(d0)*std::uint64_t(d1)!=rows || at<data || at%64 || at>bytes ||
                length!=extent || length>bytes-at || mapping+at!=native || load<std::uint32_t>(e,156)) {found=false;break;}
            table={native,rows,mapping,std::size_t(bytes)};found=true;
        }
    }
    const bool error=std::ferror(f);const int closed=std::fclose(f);return found&&!error&&!closed;
}

struct Window {
    void* model{};void* context{};
    Arguments args;
    Phase phase;
    std::uint64_t generation{};
    std::size_t workers{};
    const void* token_begin{};const void* token_end{};
    std::chrono::steady_clock::time_point deadline;
    std::atomic<std::size_t> skipped_tokens{};
};
std::mutex registry_mutex;
std::map<void*,std::shared_ptr<Window>> registry;
std::uint64_t next_generation{};
struct Local {std::shared_ptr<Window> window;const void* state{};std::size_t skipped{};};
thread_local Local local;

bool stopping(void* context,void* cookie) noexcept {
    const auto& w=*static_cast<Window*>(cookie);
    return context!=w.context || __atomic_load_n(static_cast<unsigned char*>(context)+0x60,__ATOMIC_ACQUIRE) ||
        __atomic_load_n(static_cast<unsigned char*>(w.model)+0x318,__ATOMIC_ACQUIRE) ||
        std::chrono::steady_clock::now()>=w.deadline ||
        load<const void*>(context)!=w.args.raw.base || load<const void*>(context,8)!=w.token_begin ||
        load<const void*>(context,0x10)!=w.token_end || load<const void*>(context,0x30)!=w.args.ids.data() ||
        load<const void*>(context,0x38)!=w.args.ids.data()+w.args.ids.size() ||
        load<const void*>(w.model,0x758)!=w.args.table.base || load<std::uint64_t>(w.model,0x768)!=w.args.table.row_count ||
        load<std::int32_t>(w.model,0x770)!=160 || load<std::int32_t>(w.model,0x774)!=0;
}
std::shared_ptr<Window> lookup(void* context) {
    std::lock_guard lock(registry_mutex);
    auto it=registry.find(context);return it==registry.end()?nullptr:it->second;
}
void bind_local(const void* state,void* model,void* context) {
    if(local.state==state) {
        if(local.window && (local.window->model!=model || local.window->context!=context))fail("worker-state-drift");
        return;
    }
    if(local.window)fail("worker-reentry");
    local.window=lookup(context);local.state=state;local.skipped=0;
    if(local.window && (local.window->model!=model || load<const void*>(state,8)!=model ||
        load<const void*>(state,0x10)!=context || load<std::int64_t>(state,0x18)!=160))fail("worker-binding");
}
bool select(void* model,void* context,std::size_t workers) {
    // The exact native launcher already owns a valid context. Keep short native
    // decode windows on a cheap fallback before any /proc or allocation work.
    if(!context)return false;
    const auto first=load<std::uintptr_t>(context,8),end=load<std::uintptr_t>(context,0x10);
    if(end<first||(end-first)%4)return false;
    const auto tokens=(end-first)/4;
    if(tokens<256||tokens>8192)return false;
    if(!readable(context,0x140,true)||!load<const void*>(context)||!readable(model,0x8f8)||!workers||workers>256||load<std::int32_t>(context,0xc0)!=std::int32_t(workers)||
        load<std::uint64_t>(context,0x58)||load<std::int32_t>(model,0x770)!=160||load<std::int32_t>(model,0x774)!=0)return false;
    const auto ids=load<const std::int64_t*>(context,0x30);
    const auto ids_end=load<std::uintptr_t>(context,0x38),ids_capacity=load<std::uintptr_t>(context,0x40);
    const auto raw=load<std::byte*>(context);
    const auto allocation=load<std::int32_t>(model,0x2d8);
    if(!ids || reinterpret_cast<std::uintptr_t>(ids)%8 || ids_end<reinterpret_cast<std::uintptr_t>(ids) ||
        ids_end-reinterpret_cast<std::uintptr_t>(ids)!=tokens*128 || ids_capacity<ids_end ||
        load<std::uint64_t>(context,0x48)!=tokens*16 || allocation<std::int64_t(tokens) ||
        (raw!=load<std::byte*>(model,0x798)&&raw!=load<std::byte*>(model,0x7b8)) ||
        !readable(reinterpret_cast<const void*>(first),tokens*4) || !readable(ids,tokens*128,true) ||
        !readable(raw,std::uint64_t(allocation)*2720,true))return false;
    const auto raw_bytes=std::uint64_t(allocation)*2720;
    if(overlap(raw,raw_bytes,model,0x8f8)||overlap(raw,raw_bytes,context,0x140)||
        overlap(raw,raw_bytes,reinterpret_cast<const void*>(first),tokens*4)||
        overlap(ids,tokens*128,reinterpret_cast<const void*>(first),tokens*4))return false;
    auto w=std::make_shared<Window>();w->model=model;w->context=context;w->workers=workers;
    if(!actual_table(model,w->args.table))return false;
    w->args.native_context=context;w->args.token_count=tokens;w->args.context_rows=tokens*16;
    w->args.ids={ids,std::size_t(tokens*16)};w->args.raw={raw,std::size_t(raw_bytes)};
    w->args.native_stride=160;w->args.native_table_encoding=0;
    w->token_begin=reinterpret_cast<const void*>(first);w->token_end=reinterpret_cast<const void*>(end);
    w->deadline=std::chrono::steady_clock::now()+std::chrono::seconds(120);
    std::lock_guard lock(registry_mutex);
    if(registry.contains(context))fail("context-reused-before-consumer");
    w->generation=++next_generation;if(!w->generation)fail("generation-overflow");
    Qualification qualification{true,true,true,true,true,true,true};
    ple_page::Policy policy;policy.allow_page_order=true;
    if(!w->phase.begin(w->args,qualification,policy,workers,{context,w.get(),stopping},w->generation))return false;
    registry.emplace(context,w);
    active_windows.fetch_add(1,std::memory_order_release);
    dprintf(2,"[ple0172-native-page] selected generation=%llu tokens=%zu workers=%zu; actual HGN table\n",
        static_cast<unsigned long long>(w->generation),w->args.token_count,workers);
    return true;
}
}

extern "C" __attribute__((visibility("hidden"))) std::uintptr_t ple0172_native_launch_dispatch(void*,std::uint64_t* r) noexcept {
    const auto incoming=errno;
    try { select(reinterpret_cast<void*>(r[6]),reinterpret_cast<void*>(r[14]),std::uint32_t(r[13])); }
    catch(...) { if(active_windows.load(std::memory_order_acquire))fail("selection-exception"); }
    errno=incoming;return patch.stock_replay[PLE0172_NATIVE_LAUNCH];
}
extern "C" __attribute__((visibility("hidden"))) std::uintptr_t ple0172_native_copy_dispatch(void* frame,std::uint64_t* r) noexcept {
    const auto incoming=errno;const auto* state=load<const void*>(frame,0x18);
    auto* model=reinterpret_cast<void*>(r[11]);auto* context=load<void*>(state,0x10);
    try { bind_local(state,model,context); }catch(...) { fail("copy-binding-exception"); }
    if(!local.window) {errno=incoming;return patch.stock_replay[PLE0172_NATIVE_COPY];}
    auto& w=*local.window;
    if(stopping(context,&w)||r[14]>=w.args.token_count||r[12]!=reinterpret_cast<std::uintptr_t>(w.args.ids.data()+r[14]*16))fail("selected-copy-state");
    ++local.skipped;r[6]=reinterpret_cast<std::uintptr_t>(state);r[2]=r[14];
    errno=incoming;return patch.engine_base+0x1865791;
}
extern "C" __attribute__((visibility("hidden"))) std::uintptr_t ple0172_native_complete_dispatch(void*,std::uint64_t* r) noexcept {
    const auto incoming=errno;const auto* state=reinterpret_cast<const void*>(r[6]);
    auto* model=reinterpret_cast<void*>(r[11]);auto* context=reinterpret_cast<void*>(r[1]);
    try { bind_local(state,model,context); }catch(...) { fail("completion-binding-exception"); }
    if(local.window) {
        auto w=local.window;
        w->skipped_tokens.fetch_add(local.skipped,std::memory_order_release);
        if(w->phase.run_phase(w->generation)!=Result::success)fail("post-ID-phase");
    }
    local.window.reset();local.state=nullptr;local.skipped=0;
    errno=incoming;return patch.stock_replay[PLE0172_NATIVE_COMPLETE];
}
extern "C" __attribute__((visibility("hidden"))) std::uintptr_t ple0172_native_consumer_dispatch(void*,std::uint64_t* r) noexcept {
    const auto incoming=errno;auto* model=reinterpret_cast<void*>(r[1]);auto* context=reinterpret_cast<void*>(r[13]);
    try {
        auto w=lookup(context);
        if(w) {
            if(w->model!=model||!w->phase.permit_h2d(w->generation,true)||
                w->skipped_tokens.load(std::memory_order_acquire)!=w->args.token_count)fail("consumer-terminal");
            dprintf(2,"[ple0172-native-page] complete generation=%llu tokens=%zu rows=%zu workers=%zu; original scalar IDs/GPU unpack/RMS/FC\n",
                static_cast<unsigned long long>(w->generation),w->args.token_count,w->args.ids.size(),w->workers);
            std::lock_guard lock(registry_mutex);
            if(registry.erase(context)!=1)fail("consumer-registry");
            active_windows.fetch_sub(1,std::memory_order_release);
        }
    }catch(...) { fail("consumer-exception"); }
    errno=incoming;return patch.stock_replay[PLE0172_NATIVE_CONSUMER];
}
extern "C" [[noreturn]] void __cxa_throw(void* exception,void* type,void(*destroy)(void*)) {
    if(attached.load(std::memory_order_acquire)&&active_windows.load(std::memory_order_acquire))fail("selected-C++-unwind");
    auto target=native_throw.load(std::memory_order_acquire);
    if(!target) {
        target=reinterpret_cast<Throw>(dlsym(RTLD_NEXT,"__cxa_throw"));if(!target)fail("throw-symbol");
        native_throw.store(target,std::memory_order_release);
    }
    target(exception,type,destroy);__builtin_unreachable();
}
__attribute__((constructor)) static void install_native_page() {
    const auto* enabled=std::getenv("PLE0172_NATIVE_WORKER_PAGE_ORDER");if(!enabled)return;
    char path[4096];const auto size=readlink("/proc/self/exe",path,sizeof path-1);
    if(size<0||std::size_t(size)>=sizeof path-1)fail("exe-name");
    path[size]=0;const auto* name=std::strrchr(path,'/');name=name?name+1:path;
    if(std::strcmp(name,"flash_serve"))return;
    if(std::strcmp(enabled,"1"))fail("enable-value");
    const auto target=reinterpret_cast<Throw>(dlsym(RTLD_NEXT,"__cxa_throw"));if(!target)fail("throw-symbol");
    native_throw.store(target,std::memory_order_release);
    patch=ple0172_install_native_patch();attached.store(true,std::memory_order_release);
    dprintf(2,"[ple0172-native-page] attached four native seams on exact Halogen0.17.2\n");
}
