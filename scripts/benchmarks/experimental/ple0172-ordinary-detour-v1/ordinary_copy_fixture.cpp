// Focused CPU fixture for the newly connected dispatcher; no engine/devices.
#include "ordinary_detour_0172.cpp"
#include <array>
#include <chrono>
#include <vector>
#include <sys/wait.h>
static void check(bool value,const char* reason) {
    if(!value){std::fprintf(stderr,"FAIL %s\n",reason);std::exit(1);}
}
template<class T> static void put(void* pointer,std::size_t offset,T value) {
    std::memcpy(static_cast<unsigned char*>(pointer)+offset,&value,sizeof value);
}
int main() {
    check(setenv("PLE0172_ORDINARY_PAGE_ORDER","1",1)==0,"set explicit fixture enable");
    constexpr std::uint64_t source_rows=600,rows=4096;
    constexpr std::int32_t tokens=256;
    constexpr std::size_t raw_capacity=std::size_t(tokens)*2720;
    std::vector<unsigned char> mapping(320+source_rows*160+4),raw(raw_capacity+32,0xa5);
    put(mapping.data(),0,std::uint32_t(0x314e4748));put(mapping.data(),4,std::uint32_t(2));
    put(mapping.data(),8,std::uint64_t(1));put(mapping.data(),16,std::uint64_t(104));
    put(mapping.data(),24,std::uint64_t(320));put(mapping.data(),32,std::uint64_t(mapping.size()));
    constexpr char name[]="layers.1.ple.ngram_embedding.weight";
    std::memcpy(mapping.data()+104,name,sizeof name);
    auto* entry=mapping.data()+104;
    put(entry,96,std::uint32_t(10));put(entry,100,std::uint32_t(3));
    put(entry,104,std::int64_t(1));put(entry,112,std::int64_t(source_rows));put(entry,120,std::int64_t(160));
    put(entry,136,std::uint64_t(320));put(entry,144,std::uint64_t(source_rows*160+4));
    for(std::size_t i=0;i<source_rows*160;++i)mapping[320+i]=static_cast<unsigned char>((i+i/160)%251);
    std::array<unsigned char,16> mapper{};
    put(mapper.data(),0,mapping.data());put(mapper.data(),8,std::uint64_t(mapping.size()));
    std::array<unsigned char,0x8f0> model{};
    put(model.data(),0x2d0,mapper.data());put(model.data(),0x2d8,tokens);
    put(model.data(),0x308,std::uintptr_t(0x174b0d0));put(model.data(),0x310,std::uintptr_t(0x174ab30));
    put(model.data(),0x758,mapping.data()+320);put(model.data(),0x768,source_rows);
    put(model.data(),0x770,std::int32_t(160));put(model.data(),0x798,raw.data()+16);
    std::vector<std::int64_t> ids(rows);
    for(std::size_t i=0;i<rows;++i)ids[i]=std::int64_t((i*173+i/7)%source_rows);
    alignas(16) std::array<unsigned char,0x218> frame{};
    put(frame.data(),0,rows);put(frame.data(),0xa8,std::uint64_t(tokens));
    put(frame.data(),0x130,ids.data());put(frame.data(),0x138,ids.data()+ids.size());
    put(frame.data(),0x140,ids.data()+ids.size());
    const double now=double(std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count())/1000000.0;
    put(frame.data(),0x1f0,now);put(frame.data(),0x1f8,0.1);
    std::array<std::uint64_t,15> saved{};saved[11]=reinterpret_cast<std::uintptr_t>(model.data());
    stock_replay=0x1111;
    put(model.data(),0x2d0,static_cast<void*>(nullptr));
    check(ple0172_ordinary_dispatch(frame.data(),saved.data())==stock_replay,"unknown mapper delegates stock");
    for(auto byte:raw)check(byte==0xa5,"stock path untouched output");
    put(model.data(),0x2d0,mapper.data());
    check(ple0172_ordinary_dispatch(frame.data(),saved.data())==complete_rva,"complete follows original H2D continuation");
    check(load<std::uint64_t>(frame.data(),8)==160&&saved[6]==tokens,"native stride and token register restored");
    for(std::size_t i=0;i<rows;++i)
        check(std::memcmp(raw.data()+16+i*160,mapping.data()+320+std::size_t(ids[i])*160,160)==0,"complete original-order bytes");
    for(std::size_t i=0;i<16;++i)check(raw[i]==0xa5&&raw[raw.size()-1-i]==0xa5,"raw guards preserved");
    const pid_t child=fork();check(child>=0,"abort child created");
    if(!child){model[0x318]=1;ple0172_ordinary_dispatch(frame.data(),saved.data());_exit(90);}
    int status=0;check(waitpid(child,&status,0)==child&&WIFEXITED(status)&&WEXITSTATUS(status)==79,"cancel aborts before H2D/fallback");
    std::puts("PASS: actual metadata binding, before-write stock fallback, exact original-order page copies, native continuation setup, cancel abort");
}
