/* Default-off, in-process identity bridge for a separately owned launch.
 * This ABI contains no credentials. Calling it never adds a capability.
 * A sealed launcher must establish that CAP_BPF is its sole capability delta.
 */
#ifndef HALOGEN_SERVING_KERNEL_IDENTITY_H
#define HALOGEN_SERVING_KERNEL_IDENTITY_H
#include <stdint.h>

#define HALOGEN_SERVING_KERNEL_IDENTITY_ABI 1u
#define HALOGEN_SERVING_KERNEL_IDENTITY_BYTES 144u

enum halogen_serving_kernel_identity_failure_stage {
    HALOGEN_SERVING_STAGE_NONE = 0,
    HALOGEN_SERVING_STAGE_INITIAL_TASK = 1,
    HALOGEN_SERVING_STAGE_INITIAL_CAPABILITIES = 2,
    HALOGEN_SERVING_STAGE_CAPABILITY_PRECONDITION = 3,
    HALOGEN_SERVING_STAGE_PROBE = 4,
    HALOGEN_SERVING_STAGE_AMBIENT_DROP = 5,
    HALOGEN_SERVING_STAGE_BOUNDING_DROP = 6,
    HALOGEN_SERVING_STAGE_CAPSET_DROP = 7,
    HALOGEN_SERVING_STAGE_FINAL_CAPABILITIES = 8,
    HALOGEN_SERVING_STAGE_FINAL_TASK = 9
};

struct halogen_serving_kernel_identity {
    uint32_t abi_version;
    uint32_t struct_bytes;
    uint32_t kernel_pid;
    uint32_t kernel_tgid;
    int64_t namespace_pid;
    int64_t namespace_tid;
    uint64_t proc_pid_namespace_inode;
    uint32_t probe_fds_closed;
    uint32_t capability_drop_checked;
    uint32_t failure_stage;
    uint32_t probe_errno;
    uint32_t drop_errno;
    uint32_t capability_count;
    uint64_t before_effective;
    uint64_t before_permitted;
    uint64_t before_inheritable;
    uint64_t before_bounding;
    uint64_t before_ambient;
    uint64_t after_effective;
    uint64_t after_permitted;
    uint64_t after_inheritable;
    uint64_t after_bounding;
    uint64_t after_ambient;
};

#ifdef __cplusplus
extern "C" {
#endif
uint32_t halogen_serving_kernel_identity_abi(void);
uint32_t halogen_serving_kernel_identity_size(void);
const char *halogen_serving_kernel_identity_header_sha256(void);
/* activate must equal 1 and bytes must equal 144. Invalid arguments return 0
 * before touching the output or performing any observation or mutation.
 * Success is 1 only after the private probe closes all references and only
 * CAP_BPF is removed from E/P/I/bounding/ambient. Every failure forbids exec.
 * A failure after probing still attempts all CAP_BPF removal steps. Removal
 * is irreversible; the caller must exit rather than retry or execute a child.
 */
int halogen_serving_observe_and_drop_bpf(
    struct halogen_serving_kernel_identity *out, uint32_t bytes, uint32_t activate);
#ifdef __cplusplus
}
#endif
#endif
