#pragma once
#include "../dflash-prefill-owner-20261009/decode_capture.h"

namespace halogen0173::dflash::transport {
namespace source = halogen0173::dflash::prefill;
inline constexpr std::size_t kHeaderBytes=256;
inline constexpr std::uint32_t kMaxChunkRows=128, kMaskId=248077;
enum class Input : std::uint32_t {Prefill,Verify,Scalar};
enum class Step : std::uint8_t {Off,Idle,Queued,Waiting,Sent,Acknowledged,Stopped,Poisoned};
struct Identity {
    source::Binding binding{};
    std::uint64_t capture_sequence{};
};
struct HostChunk {
    void* features{};
    std::size_t bytes{};
    std::uint32_t rows{};
    bool pinned{};
};
// Functions and HostChunk are supplied by the worker's cold HIP resource owner.
// A failed enqueue may have queued work, so the borrow is never released on a
// failed enqueue/record/query unless worker-only drain proves completion.
struct D2HOps {
    void* context{};
    bool (*enqueue)(void*,void*,const void*,std::uint32_t) noexcept{};
    bool (*record)(void*) noexcept{};
    source::Poll (*query)(void*) noexcept{};
    bool (*drain)(void*) noexcept{};
};
struct SinkOps {
    void* context{};
    // Synchronous consumption of all three owned byte ranges on worker only.
    // false permanently closes this stream; partially written frames cannot retry.
    bool (*write)(void*,const std::uint8_t*,std::size_t,const std::uint8_t*,std::size_t,
                  const void*,std::size_t) noexcept{};
};
class Exporter final {
public:
    Exporter() noexcept=default;
    Exporter(const Exporter&)=delete;
    Exporter& operator=(const Exporter&)=delete;
    bool configure(bool,source::Owner*,source::DecodeCapture*,source::LeaseOps,HostChunk,D2HOps,SinkOps) noexcept;
    // Single external worker thread only. Never invoke these from a native
    // callback, mandatory gate or ready lookup. step performs one fence query.
    Step step() noexcept;
    bool acknowledge(const Identity&) noexcept;
    bool cancel(const Identity&) noexcept;
    bool retire(const source::Binding&) noexcept; // Explicit worker terminal control, also while idle.
    bool recover_failed_copy() noexcept; // May wait through worker D2HOps::drain.
    void disable_new() noexcept {enabled_=false;}
    bool drained() const noexcept {return !borrowed_&&!in_flight_&&!terminal_pending_;}
    bool stopped() const noexcept {return !enabled_;}
    bool failed() const noexcept {return aborted_;}
    Identity active_identity() const noexcept {return {binding_,sequence_};}
private:
    bool live() noexcept;
    bool acquire() noexcept;
    bool enqueue() noexcept;
    bool emit(bool abort) noexcept;
    void fail() noexcept;
    bool equal(const Identity&) const noexcept;
    source::Owner* owner_{};source::DecodeCapture* decode_{};
    source::LeaseOps lease_{};HostChunk host_{};D2HOps d2h_{};SinkOps sink_{};
    source::Binding binding_{},last_prefill_{};
    const void* staging_{};
    const std::int32_t* prefill_ids_{};
    std::array<std::int32_t,4> decode_ids_{};
    std::array<std::uint8_t,kMaxChunkRows*4> id_bytes_{};
    std::uint64_t sequence_{},round_{},packet_sequence_{};
    std::uint32_t rows_{},verified_{},offset_{},chunk_rows_{};
    std::int32_t anchor_{},next_current_{-1};
    Input input_{Input::Prefill};
    bool configured_{},enabled_{},borrowed_{},in_flight_{},ready_ack_{},poisoned_{};
    bool aborted_{},loss_notified_{},abort_emitted_{},sink_failed_{};
    bool terminal_pending_{};
};
// These signatures mirror the installed HIP C ABI; no runtime is loaded here.
struct HipFunctions {
    int (*host_malloc)(void**,std::size_t,unsigned){};
    int (*host_free)(void*){};
    int (*stream_create)(void**,unsigned){};
    int (*stream_destroy)(void*){};
    int (*stream_synchronize)(void*){};
    int (*event_create)(void**,unsigned){};
    int (*event_destroy)(void*){};
    int (*memcpy_2d_async)(void*,std::size_t,const void*,std::size_t,std::size_t,std::size_t,int,void*){};
    int (*event_record)(void*,void*){};
    int (*event_query)(void*){};
};
class HipD2H final {
public:
    HipD2H() noexcept=default;
    HipD2H(const HipD2H&)=delete;
    HipD2H& operator=(const HipD2H&)=delete;
    // Explicit worker/cold resource setup only. Default off performs no calls.
    bool configure(bool,HipFunctions,int success,int not_ready,std::uint32_t chunk_rows,Exporter* owner=nullptr) noexcept;
    HostChunk host_chunk() const noexcept;
    D2HOps operations() noexcept;
    // Refuses disposal while a copy is outstanding or exporter owns a borrow.
    bool close(const Exporter&) noexcept;
private:
    static bool enqueue(void*,void*,const void*,std::uint32_t) noexcept;
    static bool record(void*) noexcept;
    static source::Poll query(void*) noexcept;
    static bool drain(void*) noexcept;
    bool dispose() noexcept;
    HipFunctions f_{};void* host_{};void* event_{};void* stream_{};
    Exporter* owner_{};
    std::uint32_t rows_{};int success_{},not_ready_{};
    bool configured_{},queued_{},recorded_{};
};
}
