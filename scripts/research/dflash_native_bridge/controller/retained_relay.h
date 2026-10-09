#pragma once
// Inert Linux x86-64 SysV templates. No entry is published by this source.
#define HGN_DFLASH_RED_ZONE 128
#define HGN_DFLASH_FRAME_BYTES 136
#define HGN_DFLASH_CAPTURE_RESERVE 264
#define HGN_DFLASH_INVOCATION_RESERVE 16
#define HGN_DFLASH_XSAVE_PAD 128
#define HGN_DFLASH_CFG_ENABLED 0
#define HGN_DFLASH_CFG_XSAVE_BYTES 4
#define HGN_DFLASH_CFG_XCR0 8
#define HGN_DFLASH_CFG_REQUIRED_STACK 16
#define HGN_DFLASH_CFG_STACK_TLS_OFFSET 24
#define HGN_DFLASH_CFG_CALLBACK 32
#define HGN_DFLASH_CFG_LOSS_COUNTER 40
#define HGN_DFLASH_CFG_RUNTIME_ENABLED 48
#define HGN_DFLASH_CFG_IN_FLIGHT 56
#define HGN_DFLASH_CFG_LANE 64
#define HGN_DFLASH_CFG_PROVIDER 72
#define HGN_DFLASH_CFG_BYTES 80
#define HGN_DFLASH_TLS_STACK_LOW 0
#define HGN_DFLASH_TLS_STACK_HIGH 8
#define HGN_DFLASH_REL32_SENTINEL 0x5a17c0de
#define HGN_DFLASH_HANDLER_CFA 0x1a40
#define HGN_DFLASH_PREPARE_CFA 0x30
#define HGN_DFLASH_CHUNK_CFA 0x120
#define HGN_DFLASH_LANE_MODEL 0
#define HGN_DFLASH_LANE_SLOT 8
#define HGN_DFLASH_LANE_CONFIGURED 12
#define HGN_DFLASH_LANE_GENERATION 16
#define HGN_DFLASH_LANE_PHASE 24
#define HGN_DFLASH_LANE_LOCK 28
#define HGN_DFLASH_LANE_REQUEST 32
#define HGN_DFLASH_LANE_BIRTH 56
#define HGN_DFLASH_LANE_ROUND 80
#define HGN_DFLASH_LANE_LOSS 88
#define HGN_DFLASH_LANE_FRESH_RESET 96
#define HGN_DFLASH_LANE_READY_ENABLED 108

#ifndef __ASSEMBLER__
#include "retained_controller.h"
#if defined(HGN_DFLASH_SYSV_MOCK) && defined(_WIN32)
#define HGN_DFLASH_CALLBACK_ABI __attribute__((sysv_abi))
#else
#define HGN_DFLASH_CALLBACK_ABI
#endif
namespace hgn_dflash::relay {
struct StackBounds {u64 low{},high{};};
using Callback=void(HGN_DFLASH_CALLBACK_ABI *)(u32,Frame*,Invocation*,Lane*,const hgn_dflash::Configuration*)noexcept;
struct Configuration {
    u32 enabled{},xsave_bytes{};
    u64 xcr0_mask{},required_stack_below_original_rsp{};
    i64 stack_tls_offset{};
    Callback callback{};
    u64* loss_counter{};
    const u8* runtime_enabled{};
    u64* in_flight_counter{};
    Lane* lane{};
    const hgn_dflash::Configuration* provider{};
};
static_assert(sizeof(Configuration)==HGN_DFLASH_CFG_BYTES);
static_assert(__builtin_offsetof(Configuration,lane)==HGN_DFLASH_CFG_LANE);
static_assert(__builtin_offsetof(Configuration,provider)==HGN_DFLASH_CFG_PROVIDER);
static_assert(__builtin_offsetof(Configuration,callback)==HGN_DFLASH_CFG_CALLBACK);
static_assert(sizeof(Frame)==HGN_DFLASH_FRAME_BYTES);
static_assert(__builtin_offsetof(Lane,model)==HGN_DFLASH_LANE_MODEL);
static_assert(__builtin_offsetof(Lane,slot)==HGN_DFLASH_LANE_SLOT);
static_assert(__builtin_offsetof(Lane,configured)==HGN_DFLASH_LANE_CONFIGURED);
static_assert(__builtin_offsetof(Lane,generation)==HGN_DFLASH_LANE_GENERATION);
static_assert(__builtin_offsetof(Lane,request)==HGN_DFLASH_LANE_REQUEST);
static_assert(__builtin_offsetof(Lane,birth)==HGN_DFLASH_LANE_BIRTH);
static_assert(__builtin_offsetof(Lane,round)==HGN_DFLASH_LANE_ROUND);
static_assert(__builtin_offsetof(Lane,ready_enabled)==HGN_DFLASH_LANE_READY_ENABLED);
// Mandatory gate memory and code remain retained through full slot reset or
// process exit. enabled/runtime_enabled close only the optional callback.
// Config/Lane model-slot pins become immutable before entry publication.
// Cold setup must establish >=280 bytes of unconditional stack headroom;
// optional admission additionally covers XSAVE alignment, callback and signal
// budget. xsave_bytes/mask require prevalidated complete enabled standard state.
// loss_counter must be &lane->loss. All pointed storage is retained/aligned.
// The callback is a retained ENDBR64 target using a real balanced CALL/RET.
// Provider returns copied ready values immediately; no dispatch/wait is here.
}
extern "C" {
void HGN_DFLASH_CALLBACK_ABI hgn_dflash_ready_callback(hgn_dflash::u32 site,hgn_dflash::Frame* frame,
    hgn_dflash::Invocation* invocation,hgn_dflash::Lane* lane,
    const hgn_dflash::Configuration* provider)noexcept;
extern const unsigned char hgn_dflash_templates_begin[],hgn_dflash_templates_end[];
#define HGN_DFLASH_DECLARE(n) \
    void hgn_dflash_relay_##n##_begin(); \
    extern const unsigned char hgn_dflash_relay_##n##_code_end[]; \
    extern const unsigned char hgn_dflash_relay_##n##_end[]; \
    extern const hgn_dflash::relay::Configuration hgn_dflash_relay_##n##_config; \
    extern const unsigned char hgn_dflash_relay_##n##_mandatory_gate[]; \
    extern const unsigned char hgn_dflash_relay_##n##_stock_delta[];
HGN_DFLASH_DECLARE(0)
HGN_DFLASH_DECLARE(1)
HGN_DFLASH_DECLARE(2)
HGN_DFLASH_DECLARE(3)
HGN_DFLASH_DECLARE(4)
#undef HGN_DFLASH_DECLARE
extern const unsigned char hgn_dflash_relay_0_ready_delta[];
extern const unsigned char hgn_dflash_relay_0_scalar_delta[];
}
#endif
