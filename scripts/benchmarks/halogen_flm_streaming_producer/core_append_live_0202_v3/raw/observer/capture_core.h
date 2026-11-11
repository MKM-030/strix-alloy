#ifndef CAPTURE_CORE_H
#define CAPTURE_CORE_H
#include "sha256_core.h"
#include "endpoint_pins.h"
/* All fields fixed width. Little-endian x86-64 only. Native fields are read
 * only. */
static inline int hgn_bracket_valid(h_u64 a, h_u64 b) {
  return a > 0 && b >= a;
}
struct event {
  h_u64 caller_rva, caller_stack, saved_r14, saved_r15, saved_rbx, object;
  h_i64 request_id, native, native_start, tid;
  h_u64 raw_before, raw_after, prefill_accum_bits, published_prefill_bits;
  h_u32 site, status, prompt, generated;
  h_i64 native_slot;
};
struct capture {
  h_u64 magic, version, count, overflow, done, ordinal, cohort_count, epoch_nonce;
  struct event events[64];
};
typedef char event_size_must_be_136[(sizeof(struct event) == 136) ? 1 : -1];
typedef char
    capture_size_must_be_8768[(sizeof(struct capture) == 8768) ? 1 : -1];
/* Header overflow flags preserve both bounded-capacity and interference faults. */
#define HGN_FLAG_OVERFLOW 1ULL
#define HGN_FLAG_INTERFERENCE 2ULL
static inline unsigned site(h_u64 pc) {
  return pc == HGN_PF_BEGIN_PC   ? 1
         : pc == HGN_PF_END_PC ? 2
         : pc == HGN_DECODE_BEGIN_PC ? 3
         : pc == HGN_DECODE_END_PC ? 4
                           : 0;
}
static inline h_u64 select_object(unsigned s, h_u64 r14, h_u64 r15) {
  return s <= 2 ? r15 : r14;
}
static inline int append(struct capture *c, const struct event *e) {
  if (c->done)
    return 0;
  if (c->count < 64)
    c->events[c->count++] = *e;
  else
    c->overflow |= HGN_FLAG_OVERFLOW;
  if (e->site == 4) {
    c->done = 1;
    return 1;
  }
  return 0;
}
#endif
