#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace halogen0173::shadow {
inline constexpr char kRuntimeSha256[] = "af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7";
inline constexpr std::size_t kContextCapacity = 64, kOfferCapacity = 16;
enum class Kind : std::uint32_t { Birth=1, SlotAttach=2, SlotInvalidate=3, Retire=4, Begin=5, Outcome=6, Gap=7 };
enum class Source : std::uint32_t { None=0, Neural=1, Pld=2 };
enum Flag : std::uint32_t {
    ContextAvailable=1u<<0, ContextTruncated=1u<<1, OfferAvailable=1u<<2,
    OfferTruncated=1u<<3, TransportAvailable=1u<<4, CountersAvailable=1u<<5,
    Continuing=1u<<6, Terminal=1u<<7, PartialOutput=1u<<8, Censored=1u<<9
};
// This is a frozen LITTLE-ENDIAN byte wire, not a native C++ object protocol.
// Only little-endian hosts may memcpy these packed objects to the wire.
#pragma pack(push, 1)
struct Header {
    std::array<char,8> magic{'H','0','1','7','3','S','L','1'};
    std::uint32_t version=1, record_bytes=512;
    std::array<char,64> runtime_sha256{};
    std::array<std::uint8_t,16> session_nonce{};
    std::uint32_t context_cap=64, offer_cap=16, counter_count=8, flags=0;
    std::array<std::uint8_t,16> reserved{};
};
struct Event {
    Kind kind{};
    std::uint32_t flags{};
    std::uint64_t sequence{}, owner_birth{}, slot_cookie{}, slot_epoch{}, round{}, wire_request_id{};
    Source source{};
    std::int32_t native_status{};
    std::uint64_t dropped_cumulative{};
    std::uint32_t context_total{}, context_count{}, offer_total{}, offer_count{};
    std::int32_t current_id{}, opening_id{}, depth_low{}, depth_high{}, stock_width{}, native_allowance{};
    std::uint32_t transported_count{};
    std::int32_t model_position{};
    std::uint32_t adaptive{}, reserved{};
    // Raw cumulative Request counters, not deltas or independent horizon labels:
    // +0,+0x28,+0x40,+0x48,+0x60,+0x68,+0x70,+0x78.
    std::array<std::uint64_t,8> counters{};
    std::array<std::int32_t,64> context_suffix{};
    std::array<std::int32_t,16> pld_offer{};
};
#pragma pack(pop)
static_assert(sizeof(Header)==128 && sizeof(Event)==512);
static_assert(offsetof(Event,sequence)==8 && offsetof(Event,source)==56);
static_assert(offsetof(Event,dropped_cumulative)==64 && offsetof(Event,counters)==128);
static_assert(offsetof(Event,context_suffix)==192 && offsetof(Event,pld_offer)==448);
} // namespace halogen0173::shadow
