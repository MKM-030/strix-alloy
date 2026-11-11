// Two-site append-only scope. Pure coordinator: Windows memory operations are
// injected by the private bridge; CPU tests use arrays and make no native call.
#pragma once
#include <array>
#include <atomic>
#include <cstdint>
#include <exception>
#include <stdexcept>

namespace append_head {
using Bytes=std::array<std::uint8_t,6>;
inline constexpr std::array<Bytes,2> original={Bytes{0xff,0x15,0x42,0x42,0x0b,0},Bytes{0xff,0x15,0xff,0x41,0x0b,0}};
inline constexpr Bytes suppressed={0x90,0x90,0x90,0x90,0x90,0x90};
class Error:public std::runtime_error {public:using std::runtime_error::runtime_error;};
class RestorationFailure:public Error {public:using Error::Error;};

class SingleEngineLease {
    inline static std::atomic<void*> owner_{nullptr};
    void* identity_;
public:
    explicit SingleEngineLease(void* identity):identity_(identity) {
        if(!identity)throw Error("One non-null native engine owner required");
        void* empty=nullptr;
        if(!owner_.compare_exchange_strong(empty,identity))throw Error("Only one native engine may exist in this private bridge");
    }
    ~SingleEngineLease()noexcept {
        void* expected=identity_;
        if(!owner_.compare_exchange_strong(expected,nullptr))std::terminate();
    }
    SingleEngineLease(const SingleEngineLease&)=delete;
    SingleEngineLease& operator=(const SingleEngineLease&)=delete;
};

template<class Memory>class Guard {
    Memory& memory_;
    const std::uint64_t owner_;
    bool busy_=false,dirty_=false,terminal_=false;
    std::uint32_t original_protection_=0;
    std::uint64_t skipped_=0;
    bool bytes_equal(const std::array<Bytes,2>& expected)const noexcept {
        for(unsigned i=0;i<2;++i){Bytes actual{};if(!memory_.read(i,actual)||actual!=expected[i])return false;}
        return true;
    }
    bool restore()noexcept {
        std::uint32_t ignored=0;
        bool writable=memory_.writable(ignored),first=false,second=false,flushed=false;
        if(writable){first=memory_.write(0,original[0]);second=memory_.write(1,original[1]);flushed=memory_.flush();}
        // Always attempt the captured original permissions, even after a byte
        // or cache-flush failure. An unsuccessful restore is permanently fatal.
        bool protection=memory_.restore_protection(original_protection_);
        bool ok=writable&&first&&second&&flushed&&protection&&bytes_equal(original)&&memory_.protection_restored();
        if(!ok){terminal_=true;return false;}
        dirty_=false;return true;
    }
    void owner()const {
        if(memory_.current_thread()!=owner_)throw Error("Append-head scope belongs to its native actor thread");
    }
public:
    Guard(Memory& memory,std::uint64_t thread):memory_(memory),owner_(thread){}
    Guard(const Guard&)=delete;
    Guard& operator=(const Guard&)=delete;
    bool terminal()const noexcept{return terminal_;}
    std::uint64_t skipped()const noexcept{return skipped_;}
    bool restored()const noexcept{return !terminal_&&!dirty_&&bytes_equal(original)&&memory_.protection_restored();}
    void require_restored()const {
        owner();
        if(terminal_)throw RestorationFailure("TERMINAL append-head restoration failed; native cleanup is not qualified");
        if(busy_)throw Error("Nested append-head/native operation is forbidden");
        if(!restored())throw Error("Original append-head instruction bytes or page protection differ");
    }
    template<class F>void run(bool enabled,F action) {
        require_restored();busy_=true;
        struct Reset{bool& value;~Reset(){value=false;}} reset{busy_};
        if(!enabled){action();return;}
        if(!memory_.writable(original_protection_))throw Error("Cannot make the two owned head call sites writable");
        dirty_=true;
        try {
            bool first=memory_.write(0,suppressed),second=memory_.write(1,suppressed);
            bool flushed=memory_.flush(),protection=memory_.restore_protection(original_protection_);
            const std::array<Bytes,2> patched={suppressed,suppressed};
            if(!first||!second||!flushed||!protection||!bytes_equal(patched)||!memory_.protection_restored())
                throw Error("Scoped append-head patch installation failed");
            action();
        }catch(...) {
            auto original_error=std::current_exception();
            if(!restore())throw RestorationFailure("TERMINAL append-head restoration failed; native cleanup is not qualified");
            std::rethrow_exception(original_error);
        }
        if(!restore())throw RestorationFailure("TERMINAL append-head restoration failed; native cleanup is not qualified");
        ++skipped_;
    }
};
}
