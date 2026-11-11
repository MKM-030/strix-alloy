// CPU fake-memory transactions only. No DLL, accelerator, socket or model.
#include <array>
#include <cstdint>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#if __has_include("append_head_scope.hpp")
#include "append_head_scope.hpp"
#else
// RED fixture: the missing implementation leaves both head calls untouched.
namespace append_head {
using Bytes=std::array<std::uint8_t,6>;
inline constexpr std::array<Bytes,2> original={Bytes{0xff,0x15,0x42,0x42,0x0b,0},Bytes{0xff,0x15,0xff,0x41,0x0b,0}};
inline constexpr Bytes suppressed={0x90,0x90,0x90,0x90,0x90,0x90};
template<class Memory>class Guard {
public:Guard(Memory&,std::uint64_t){}template<class F>void run(bool,F f){f();}
bool restored()const{return true;}bool terminal()const{return false;}std::uint64_t skipped()const{return 0;}
void require_restored()const{}
};
class SingleEngineLease{public:explicit SingleEngineLease(void*){}};
}
#endif

static void check(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
struct Memory {
    std::array<append_head::Bytes,2> bytes=append_head::original;
    std::uint32_t protection=32;
    unsigned writes=0,protects=0,flushes=0,restores=0;
    unsigned fail_write=0,fail_restore=0,fail_flush=0;
    std::uint64_t current_thread()const noexcept{return std::hash<std::thread::id>{}(std::this_thread::get_id());}
    bool read(unsigned index,append_head::Bytes& out)const noexcept{out=bytes[index];return true;}
    bool writable(std::uint32_t& previous)noexcept{++protects;previous=protection;protection=64;return true;}
    bool write(unsigned index,const append_head::Bytes& value)noexcept{
        ++writes;if(writes==fail_write)return false;bytes[index]=value;return true;
    }
    bool flush()noexcept{++flushes;return flushes!=fail_flush;}
    bool restore_protection(std::uint32_t value)noexcept{
        ++restores;if(restores==fail_restore)return false;protection=value;return true;
    }
    bool protection_restored()const noexcept{return protection==32;}
};
template<class F>static void rejects(F action){bool failed=false;try{action();}catch(const std::exception&){failed=true;}check(failed,"Expected refusal");}
static void normal_scope() {
    Memory memory;append_head::Guard<Memory> guard(memory,memory.current_thread());
    guard.run(true,[&]{check(memory.bytes[0]==append_head::suppressed&&memory.bytes[1]==append_head::suppressed,"Head calls were not suppressed inside scope");check(memory.protection==32,"Original execute protection must hold during action");});
    check(memory.bytes==append_head::original&&guard.restored(),"Original bytes/protection not restored");
    check(guard.skipped()==1&&!guard.terminal(),"Successful skipped count differs");
}
static void default_off() {
    Memory memory;append_head::Guard<Memory> guard(memory,memory.current_thread());
    guard.run(false,[&]{check(memory.bytes==append_head::original,"Default-off path changed bytes");});
    check(memory.writes==0&&memory.protects==0&&memory.flushes==0&&guard.skipped()==0&&guard.restored(),"Default-off performed patch operations");
}
static void unexpected_bytes() {
    Memory memory;append_head::Guard<Memory> guard(memory,memory.current_thread());memory.bytes[1][0]^=1;
    rejects([&]{guard.run(true,[]{throw std::runtime_error("Must not enter action");});});
    check(memory.writes==0&&memory.protects==0,"Unknown code was modified");
}
static void wrong_thread() {
    Memory memory;append_head::Guard<Memory> guard(memory,memory.current_thread());bool rejected=false;
    std::thread other([&]{try{guard.run(true,[]{});}catch(const std::exception&){rejected=true;}});other.join();
    check(rejected&&memory.writes==0&&guard.restored(),"Foreign thread changed code");
}
static void nested_use() {
    Memory memory;append_head::Guard<Memory> guard(memory,memory.current_thread());
    guard.run(true,[&]{rejects([&]{guard.run(true,[]{});});rejects([&]{guard.run(false,[]{});});});
    check(guard.skipped()==1&&guard.restored(),"Nested use invalidated outer restoration");
}
static void exception_restores() {
    Memory memory;append_head::Guard<Memory> guard(memory,memory.current_thread());bool original=false;
    try{guard.run(true,[]{throw std::runtime_error("injected native exception");});}
    catch(const std::exception& error){original=std::string(error.what())=="injected native exception";}
    check(original&&guard.restored()&&!guard.terminal()&&guard.skipped()==0,"Exception failed to restore/rethrow original");
}
static void partial_install_restores() {
    Memory memory;memory.fail_write=2;append_head::Guard<Memory> guard(memory,memory.current_thread());
    rejects([&]{guard.run(true,[]{throw std::runtime_error("Must not enter action");});});
    check(guard.restored()&&!guard.terminal()&&guard.skipped()==0,"Partial installation was not restored");
}
static void flush_failure_restores() {
    Memory memory;memory.fail_flush=1;append_head::Guard<Memory> guard(memory,memory.current_thread());
    rejects([&]{guard.run(true,[]{});});
    check(guard.restored()&&!guard.terminal(),"Installation flush failure was not restored");
}
static void irreversible_restore_is_sticky() {
    Memory memory;memory.fail_write=3;append_head::Guard<Memory> guard(memory,memory.current_thread());
    rejects([&]{guard.run(true,[]{});});
    check(guard.terminal()&&!guard.restored()&&guard.skipped()==0,"Irrecoverable restoration was labelled clean");
    memory.bytes=append_head::original;memory.protection=32;
    rejects([&]{guard.require_restored();});rejects([&]{guard.run(false,[]{});});
    check(guard.terminal()&&!guard.restored(),"Terminal restoration failure was cleared");
}
static void protection_restore_failure_is_terminal() {
    Memory memory;memory.fail_restore=2;append_head::Guard<Memory> guard(memory,memory.current_thread());
    rejects([&]{guard.run(true,[]{});});check(guard.terminal()&&!guard.restored(),"Page protection failure was labelled clean");
}
static void one_engine_only() {
    int first=0,second=0;
    {append_head::SingleEngineLease lease(&first);rejects([&]{append_head::SingleEngineLease denied(&second);});}
    append_head::SingleEngineLease next(&second);
}
int main() {
    struct Case{const char* name;void(*run)();};
    const Case cases[]={{"normal_scope",normal_scope},{"default_off",default_off},{"unexpected_bytes",unexpected_bytes},
        {"wrong_thread",wrong_thread},{"nested_use",nested_use},{"exception_restores",exception_restores},
        {"partial_install_restores",partial_install_restores},{"flush_failure_restores",flush_failure_restores},
        {"irreversible_restore_is_sticky",irreversible_restore_is_sticky},{"protection_restore_failure_is_terminal",protection_restore_failure_is_terminal},
        {"one_engine_only",one_engine_only}};
    for(const auto& item:cases){try{item.run();std::cout<<"PASS "<<item.name<<'\n';}
        catch(const std::exception& error){std::cerr<<"FAIL "<<item.name<<": "<<error.what()<<'\n';return 1;}}
    std::cout<<"11 CPU scoped-code tests PASS; no native engine calls\n";return 0;
}
