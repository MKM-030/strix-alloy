#ifndef HALOGEN0162_MTP_EMBEDDING_CACHE_H
#define HALOGEN0162_MTP_EMBEDDING_CACHE_H
#include <stddef.h>
#include <stdint.h>
#include <stdatomic.h>

#define ECACHE_ABI_VERSION 1u
#define ECACHE_MAX_ENTRIES 64u
#define ECACHE_ROW_BYTES 5120u
#define ECACHE_TOKEN_COUNT 248320u
#define ECACHE_MISS 0
#define ECACHE_HIT 1
#define ECACHE_ERROR (-1)
#define ECACHE_HOST_VALIDATION_MAPS "maps-v1"
#define ECACHE_HOST_VALIDATION_CHECKED_COPY "checked-copy-v1"

/* All callbacks operate on the same default HIP stream (NULL). Return 0 for
 * success. event_query alone returns 1 for pending, -1 for any native error.
 * The owner pins the runtime/arithmetic and enforces process/deadline/reserves. */
struct ecache_ops {
    uint32_t abi_version;
    int (*allocate)(void **,size_t);
    int (*release)(void *);
    int (*copy_async)(void *,const void *,size_t,int,void *);
    int (*stream_synchronize)(void *);
    int (*event_create)(void **,unsigned);
    int (*event_record)(void *,void *);
    int (*event_query)(void *);
    int (*event_destroy)(void *);
};
struct ecache_entry {void *device,*event;int32_t token;unsigned valid;};
struct ecache_stats {
    uint64_t calls,hits,misses,original_calls,captures,pending_fallbacks,evictions;
    uint64_t failures,copy_enqueues,event_queries,allocations,frees;
    uint64_t events_created,events_destroyed,stream_drains,resets;
};
struct ecache_state {
    struct ecache_ops ops;
    struct ecache_entry entries[ECACHE_MAX_ENTRIES];
    struct ecache_stats stats;
    unsigned char generation[16];
    unsigned capacity,next_victim,initialized;
    _Atomic unsigned failed;
    atomic_flag busy;
};
/* Callback must launch exactly one unchanged original M1 on these input/output
 * pointers, return 0 on success, and preserve native errno desired by owner.
 * The owner supplies zeroed state for init and exclusive init/reset/close
 * lifetime ownership. Apply overlap/reentrancy permanently fails the state.
 * A failed apply must not be used as permission for a native retry: a failed
 * candidate write may already have been submitted. Device pointers remain
 * opaque; the owner guarantees all input/output allocations are live.
 * ECACHE_MISS means successful original callback; ECACHE_HIT means its skip.
 * A token outside [0, ECACHE_TOKEN_COUNT) is an unsupported native fallback. */
typedef int (*ecache_launch_fn)(void *,const uint16_t *,uint16_t *);
int ecache_init(struct ecache_state *,const struct ecache_ops *,const unsigned char[16],unsigned);
int ecache_apply(struct ecache_state *,int32_t,const uint16_t *,uint16_t *,ecache_launch_fn,void *);
/* Capture-policy misses always launch the original once, including a row that
 * completed after ready lookup. Existing M1-only apply semantics are unchanged. */
int ecache_capture_original(struct ecache_state *,int32_t,const uint16_t *,uint16_t *,ecache_launch_fn,void *);
/* Reset/close require the caller's exclusive lifetime ownership. They drain the
 * stream before invalidating/freeing. Reset rejects the current/zero generation;
 * the owner supplies globally fresh generation values, including past epochs. */
int ecache_reset(struct ecache_state *,const unsigned char[16]);
int ecache_close(struct ecache_state *);
/* Borrowed ready pointers require exclusive full-head ownership. No eviction,
 * reset, close or import may occur until the consuming launch is enqueued on
 * the same default stream. The caller owns every GPU allocation extent. */
int ecache_lookup_ready(struct ecache_state *,int32_t,const uint16_t **);
#define ECACHE_ARTIFACT_HEADER_BYTES 128u
#define ECACHE_ARTIFACT_RECORD_BYTES (8u+ECACHE_ROW_BYTES)
#define ECACHE_ARTIFACT_MAX_BYTES (ECACHE_ARTIFACT_HEADER_BYTES+ECACHE_MAX_ENTRIES*ECACHE_ARTIFACT_RECORD_BYTES)
struct ecache_artifact {
    unsigned count,origin;
    unsigned char generation[16],model_binding[32],provenance[32];
    int32_t tokens[ECACHE_MAX_ENTRIES];
    uint16_t rows[ECACHE_MAX_ENTRIES][ECACHE_ROW_BYTES/2];
};
/* Import requires empty state and drains before returning, so host rows may be
 * released afterwards. Export requires exclusive ownership and drains/copies.
 * Neither API proves arithmetic or live-model provenance; owner supplies it. */
int ecache_import_rows(struct ecache_state *,const struct ecache_artifact *);
int ecache_export_rows(struct ecache_state *,struct ecache_artifact *);
int ecache_artifact_encode(const struct ecache_artifact *,unsigned char *,size_t,size_t *);
int ecache_artifact_decode(const unsigned char *,size_t,const unsigned char[16],
    const unsigned char[32],const unsigned char[32],struct ecache_artifact *);
enum {ECACHE_BRANCH_GATHER,ECACHE_BRANCH_RMS,ECACHE_BRANCH_M1,ECACHE_BRANCH_SEED};
struct ecache_branch {unsigned stage,failed;};
int ecache_branch_step(struct ecache_branch *,unsigned);
#endif
