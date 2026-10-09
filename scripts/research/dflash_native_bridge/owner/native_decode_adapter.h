#pragma once
#include "decode_capture.h"
#include "native_adapter.h"
namespace halogen0173::dflash::prefill {
enum class DecodeSite : std::uint32_t {VerifyBegin,VerifyReturned,CommitBegin,CommitReturned,ScalarBegin,ScalarReturned,CommonOutcome,RequestDestructor};
struct RoundSource {
    void* context{};
    // Shared native-controller round, assigned once by mandatory Entry dispatch.
    std::uint64_t (*current)(void*,const Binding&) noexcept{};
};
class NativeDecodeAdapter final {
public:
    bool configure(bool enable,Owner*,DecodeCapture*,RoundSource,bool default_stream_verified) noexcept;
    void on_site(DecodeSite,const Frame&) noexcept;
    void on_hc(const Frame&) noexcept;
    void source_loss() noexcept {if(capture_)capture_->source_loss();}
private:
    Owner* owner_{};DecodeCapture* capture_{};
    RoundSource rounds_{};
    Binding active_binding_{};
    std::uint32_t commit_count_{};
    bool enabled_{},active_{};
};
}
