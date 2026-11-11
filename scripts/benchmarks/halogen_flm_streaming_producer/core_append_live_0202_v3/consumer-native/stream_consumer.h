#ifndef HGN0202_STREAM_CONSUMER_H
#define HGN0202_STREAM_CONSUMER_H
#include <stddef.h>
#include <stdint.h>

#define HGN0202_STREAM_HEADER 112u
#define HGN0202_STREAM_MAX_IDS 3u
#define HGN0202_STREAM_MAX_BYTES 124u
#define HGN0202_STREAM_SLOTS 4u
#define HGN0202_STREAM_HEAD_ROWS 248320u
#define HGN0202_STREAM_SHARED_IDS 248070u
#define HGN0202_STREAM_MAX_CONTEXT 262144u
#define HGN0202_STREAM_DRAIN_LIMIT 8u

enum hgn0202_stream_kind { HDO2_BEGIN=1, HDO2_AUTHORITY=2, HDO2_READY=3,
                          HDO2_CANCEL=4, HDO2_END=5 };

/* LE header, decoded by offsets rather than packed struct casts:
 * 0 HDO2, 4 u16 version2, 6 u16 header112, 8 u32 total,12 u32 kind,
 * 16 u64 request_id,24 u32 P,28 u32 flags0,32 epoch[16],48 nonce64,
 * 56 u64 global published T count G,64 prefix SHA256[32],96 sequence64,
 * 104 i32 last published T/current(-1 at G0),108 u32 ID count; IDs at112.
 * Authority and READY sequences are independent monotonic streams per epoch.
 */
struct hgn0202_stream_packet {
    uint32_t kind, n_prompt, count;
    uint64_t request_id, nonce, generated, sequence;
    uint8_t epoch[16], prefix_sha256[32];
    int32_t current_token, ids[HGN0202_STREAM_MAX_IDS];
};

struct hgn0202_stream_snapshot {
    uint64_t rax, rbx, rcx, rdx, rsi, rdi, rbp;
    uint64_t r8, r9, r10, r11, r12, r13, r14, r15, rflags;
};

struct hgn0202_stream_native_view {
    uintptr_t request, speculative;
    uint64_t request_id;
    int32_t n_prompt, generated, current_token, budget;
};

struct hgn0202_stream_stats {
    uint64_t queries, lock_busy, datagrams, rejected_datagrams, recv_errors;
    uint64_t begins, authorities, readies, retirements, sequence_failures;
    uint64_t stale_readies, prefix_misses, current_misses, already_consumed;
    uint64_t hits, proposed_ids, native_fallbacks;
};

/* Cold owner only; socket must be a dedicated same-host SOCK_DGRAM endpoint.
 * Caller owns descriptor, identity/byte checks, executable hook and cleanup.
 * Native request IDs must increase within this one native process (as the
 * pinned API Engine.generate does). Reusing an ID fails closed until restart.
 */
int hgn0202_stream_configure(int fd,unsigned enabled,uintptr_t fallback,uintptr_t consume);
void hgn0202_stream_bind_stats(struct hgn0202_stream_stats *shared);
int hgn0202_stream_get_stats(struct hgn0202_stream_stats *out);
void hgn0202_stream_relay(void);
__attribute__((visibility("hidden")))
int hgn0202_stream_decode(const uint8_t *wire,size_t bytes,struct hgn0202_stream_packet *out);
__attribute__((visibility("hidden")))
int hgn0202_stream_select(const struct hgn0202_stream_packet *authority,
                         const struct hgn0202_stream_packet *ready,
                         const struct hgn0202_stream_native_view *native,
                         int32_t out[HGN0202_STREAM_MAX_IDS]);
__attribute__((visibility("hidden")))
int hgn0202_stream_consume_snapshot(const struct hgn0202_stream_snapshot *saved);
#endif
