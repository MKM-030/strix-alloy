#include "native_detour_0172.cpp"
#include <cassert>
#include <thread>
#include <sys/wait.h>
#include <fcntl.h>
#include <vector>

template<class T> static void put(void* p,std::size_t at,T v) {std::memcpy(static_cast<char*>(p)+at,&v,sizeof v);}
struct Fixture {
    static constexpr std::size_t rows=8192, data=8192, bytes=data+rows*160+4;
    std::byte* map;std::vector<std::byte> model,context,raw;
    std::vector<std::int32_t> tokens;std::vector<std::int64_t> ids;
    Fixture(std::size_t n,std::size_t workers):model(0x8f8),context(0x140),raw(n*2720,std::byte{0x7e}),tokens(n),ids(n*16) {
        char name[]="/tmp/ple-native-binding-XXXXXX";const int fd=mkstemp(name);assert(fd>=0);unlink(name);
        assert(!ftruncate(fd,bytes));map=static_cast<std::byte*>(mmap(nullptr,bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0));assert(map!=MAP_FAILED);close(fd);
        put(map,0,std::uint32_t(0x314e4748));put(map,4,std::uint32_t(2));put(map,8,std::uint64_t(1));put(map,16,std::uint64_t(104));put(map,24,std::uint64_t(data));put(map,32,std::uint64_t(bytes));
        auto* entry=map+104;constexpr char tensor[]="layers.1.ple.ngram_embedding.weight";std::memcpy(entry,tensor,sizeof tensor);
        put(entry,96,std::uint32_t(10));put(entry,100,std::uint32_t(3));put(entry,104,std::int64_t(128));put(entry,112,std::int64_t(64));put(entry,120,std::int64_t(160));put(entry,136,std::uint64_t(data));put(entry,144,std::uint64_t(rows*160+4));
        for(std::size_t r=0;r<rows;++r)for(std::size_t b=0;b<160;++b)map[data+r*160+b]=std::byte((r*37+b*11)%251);
        // Existing host registration splits protections inside one file mmap.
        assert(!mprotect(map,data,PROT_READ));
        put(model.data(),0x758,map+data);put(model.data(),0x768,std::uint64_t(rows));put(model.data(),0x770,std::int32_t(160));put(model.data(),0x774,std::int32_t(0));put(model.data(),0x798,raw.data());put(model.data(),0x2d8,std::int32_t(n));
        put(context.data(),0,raw.data());put(context.data(),8,tokens.data());put(context.data(),0x10,tokens.data()+n);put(context.data(),0x30,ids.data());put(context.data(),0x38,ids.data()+ids.size());put(context.data(),0x40,ids.data()+ids.size());put(context.data(),0x48,std::uint64_t(n*16));put(context.data(),0xc0,std::int32_t(workers));
    }
    ~Fixture(){assert(!munmap(map,bytes));}
    void launch(std::size_t workers) {std::uint64_t r[15]{};r[6]=reinterpret_cast<std::uintptr_t>(model.data());r[14]=reinterpret_cast<std::uintptr_t>(context.data());r[13]=workers;assert(ple0172_native_launch_dispatch(nullptr,r)==patch.stock_replay[0]);}
};
static void success() {
    Fixture f(8192,64);f.launch(64);assert(registry.size()==1&&active_windows.load()==1);
    std::atomic<std::size_t> cursor{};std::vector<std::thread> workers;
    for(int i=0;i<64;++i)workers.emplace_back([&]{
        std::byte state[0x28]{};put(state,8,f.model.data());put(state,0x10,f.context.data());put(state,0x18,std::int64_t(160));
        std::byte frame[0x28]{};put(frame,0x18,state);
        for(;;){const auto t=cursor.fetch_add(1);if(t>=8192)break;
            for(std::size_t j=0;j<16;++j)f.ids[t*16+j]=(t*131+j*977)%Fixture::rows;
            std::uint64_t r[15]{};r[11]=reinterpret_cast<std::uintptr_t>(f.model.data());r[12]=reinterpret_cast<std::uintptr_t>(f.ids.data()+t*16);r[14]=t;
            errno=EDOM;assert(ple0172_native_copy_dispatch(frame,r)==patch.engine_base+0x1865791);assert(errno==EDOM&&r[6]==reinterpret_cast<std::uintptr_t>(state)&&r[2]==t);
        }
        std::uint64_t r[15]{};r[6]=reinterpret_cast<std::uintptr_t>(state);r[11]=reinterpret_cast<std::uintptr_t>(f.model.data());r[1]=reinterpret_cast<std::uintptr_t>(f.context.data());
        assert(ple0172_native_complete_dispatch(nullptr,r)==patch.stock_replay[2]);assert(!local.window);
    });
    for(auto& t:workers)t.join();
    std::uint64_t r[15]{};r[1]=reinterpret_cast<std::uintptr_t>(f.model.data());r[13]=reinterpret_cast<std::uintptr_t>(f.context.data());assert(ple0172_native_consumer_dispatch(nullptr,r)==patch.stock_replay[3]);
    assert(registry.empty()&&active_windows.load()==0);
    for(std::size_t row=0;row<f.ids.size();++row)assert(!std::memcmp(f.raw.data()+row*160,f.map+Fixture::data+f.ids[row]*160,160));
    for(std::size_t b=f.ids.size()*160;b<f.raw.size();++b)assert(f.raw[b]==std::byte{0x7e});
}
static void fatal_test(bool exception) {
    const auto child=fork();assert(child>=0);
    if(!child){Fixture f(256,1);f.launch(1);if(registry.size()!=1){ple_page::TableView table;dprintf(2,"fixture diagnostic table=%d model=%d context=%d raw=%d ids=%d tokens=%d\n",actual_table(f.model.data(),table),readable(f.model.data(),0x8f8),readable(f.context.data(),0x140,true),readable(f.raw.data(),f.raw.size(),true),readable(f.ids.data(),f.ids.size()*8,true),readable(f.tokens.data(),f.tokens.size()*4));}assert(registry.size()==1);if(exception)throw 5;
        f.context[0x60]=std::byte{1};std::byte state[0x28]{};put(state,8,f.model.data());put(state,0x10,f.context.data());put(state,0x18,std::int64_t(160));
        std::uint64_t r[15]{};r[6]=reinterpret_cast<std::uintptr_t>(state);r[11]=reinterpret_cast<std::uintptr_t>(f.model.data());r[1]=reinterpret_cast<std::uintptr_t>(f.context.data());ple0172_native_complete_dispatch(nullptr,r);_exit(99);
    }
    int status{};assert(waitpid(child,&status,0)==child&&WIFEXITED(status)&&WEXITSTATUS(status)==79);
}
int main(){patch.engine_base=0x100000;for(int i=0;i<4;++i)patch.stock_replay[i]=0x200000+i*16;attached.store(true);
    {Fixture f(256,1);ple_page::TableView t;assert(actual_table(f.model.data(),t));assert(!mprotect(f.map+4096,4096,PROT_NONE));assert(!actual_table(f.model.data(),t));assert(!mprotect(f.map+4096,4096,PROT_READ));assert(actual_table(f.model.data(),t));}
    Fixture fallback(128,1);fallback.launch(1);assert(registry.empty());
    success();fatal_test(false);fatal_test(true);std::puts("PASS native dispatcher: 8192 tokens/131072 rows,64 workers, non-page-aligned split HGN, unreadable gap rejection, fallback, cancellation, exception");}
