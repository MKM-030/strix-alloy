/* CPU-only native bridge. No constructor, exec, global BPF attachment or pin.
 * Capability syscalls affect this task, so a sole main task is mandatory.
 * Build and actual qualification belong to the owned launch controller.
 */
#define _GNU_SOURCE
#include "halogen_serving_kernel_identity.h"
#include "halogen_kernel_pid_self.h"
#include <dirent.h>
#include <linux/capability.h>
#include <stddef.h>
#include <sys/prctl.h>

_Static_assert(sizeof(struct halogen_serving_kernel_identity) == 144,
               "serving identity ABI must remain exactly 144 bytes");
_Static_assert(offsetof(struct halogen_serving_kernel_identity, before_effective) == 64,
               "serving identity ABI mask offset changed");
_Static_assert(CAP_BPF == 39, "reviewed CAP_BPF number changed");
_Static_assert(_LINUX_CAPABILITY_U32S_3 == 2, "64-bit capability ABI required");

struct capability_snapshot {
    uint64_t effective, permitted, inheritable, bounding, ambient;
    uint32_t count;
};
struct task_snapshot {
    int64_t pid, tid;
    uint64_t inode;
};

uint32_t halogen_serving_kernel_identity_abi(void) {
    return HALOGEN_SERVING_KERNEL_IDENTITY_ABI;
}
uint32_t halogen_serving_kernel_identity_size(void) {
    return HALOGEN_SERVING_KERNEL_IDENTITY_BYTES;
}
const char *halogen_serving_kernel_identity_header_sha256(void) {
    return "21c311d0d5dd458bca7f84b611dc734a9db1a4182938841629c98ed8efd718eb";
}

static int error_number(void) {
    return errno > 0 ? errno : EPROTO;
}

static int get_task(struct task_snapshot *out) {
    struct stat before, after;
    char name[32];
    out->pid = (int64_t)getpid();
    out->tid = (int64_t)syscall(SYS_gettid);
    if (out->pid <= 0 || out->pid > INT32_MAX || out->tid != out->pid) {
        errno = EPROTO;
        return 0;
    }
    int length = snprintf(name, sizeof name, "%lld", (long long)out->pid);
    if (length <= 0 || (size_t)length >= sizeof name ||
        stat("/proc/self/ns/pid", &before)) return 0;
    if (!before.st_ino) {errno = EPROTO; return 0;}
    DIR *directory = opendir("/proc/self/task");
    if (!directory) return 0;
    unsigned count = 0;
    int saved = 0;
    for (;;) {
        errno = 0;
        struct dirent *entry = readdir(directory);
        if (!entry) {saved = errno; break;}
        if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, "..")) continue;
        if (++count != 1 || strcmp(entry->d_name, name)) {saved = EBUSY; break;}
    }
    if (closedir(directory) && !saved) saved = error_number();
    if (!saved && count != 1) saved = EPROTO;
    if (saved) {errno = saved; return 0;}
    if (stat("/proc/self/ns/pid", &after)) return 0;
    if (after.st_ino != before.st_ino ||
        (int64_t)getpid() != out->pid || (int64_t)syscall(SYS_gettid) != out->tid) {
        errno = EPROTO;
        return 0;
    }
    out->inode = (uint64_t)after.st_ino;
    return 1;
}

static int get_cap_data(struct __user_cap_data_struct data[2]) {
    struct __user_cap_header_struct header = {
        .version = _LINUX_CAPABILITY_VERSION_3, .pid = 0
    };
    memset(data, 0, 2 * sizeof(*data));
    return syscall(SYS_capget, &header, data) == 0;
}

static int get_capabilities(struct capability_snapshot *out) {
    struct __user_cap_data_struct data[2];
    memset(out, 0, sizeof(*out));
    if (!get_cap_data(data)) return 0;
    out->effective = (uint64_t)data[0].effective | ((uint64_t)data[1].effective << 32);
    out->permitted = (uint64_t)data[0].permitted | ((uint64_t)data[1].permitted << 32);
    out->inheritable = (uint64_t)data[0].inheritable | ((uint64_t)data[1].inheritable << 32);
    /* Read the runtime extent, not just CAP_LAST_CAP from build headers. */
    for (unsigned cap = 0; cap <= 64; cap++) {
        int bounding = prctl(PR_CAPBSET_READ, (unsigned long)cap, 0UL, 0UL, 0UL);
        if (bounding < 0) {
            if (errno != EINVAL) return 0;
            if (cap <= CAP_BPF) {errno = ENOTSUP; return 0;}
            out->count = cap;
            break;
        }
        if (cap == 64) {errno = EOVERFLOW; return 0;}
        if (bounding != 0 && bounding != 1) {errno = EPROTO; return 0;}
        int ambient = prctl(PR_CAP_AMBIENT, (unsigned long)PR_CAP_AMBIENT_IS_SET,
                            (unsigned long)cap, 0UL, 0UL);
        if (ambient < 0) return 0;
        if (ambient != 0 && ambient != 1) {errno = EPROTO; return 0;}
        if (bounding) out->bounding |= UINT64_C(1) << cap;
        if (ambient) out->ambient |= UINT64_C(1) << cap;
    }
    if (!out->count) {errno = EOVERFLOW; return 0;}
    uint64_t supported = out->count == 64 ? UINT64_MAX :
                         (UINT64_C(1) << out->count) - 1;
    if ((out->effective | out->permitted | out->inheritable) & ~supported) {
        errno = EPROTO;
        return 0;
    }
    return 1;
}

static void record_before(struct halogen_serving_kernel_identity *out,
                          const struct capability_snapshot *value) {
    out->capability_count = value->count;
    out->before_effective = value->effective;
    out->before_permitted = value->permitted;
    out->before_inheritable = value->inheritable;
    out->before_bounding = value->bounding;
    out->before_ambient = value->ambient;
}
static void record_after(struct halogen_serving_kernel_identity *out,
                         const struct capability_snapshot *value) {
    out->after_effective = value->effective;
    out->after_permitted = value->permitted;
    out->after_inheritable = value->inheritable;
    out->after_bounding = value->bounding;
    out->after_ambient = value->ambient;
}
static void drop_failure(struct halogen_serving_kernel_identity *out, uint32_t stage) {
    if (!out->drop_errno) {
        out->drop_errno = (uint32_t)error_number();
        /* Cleanup failure takes priority; probe_errno retains probe failure. */
        out->failure_stage = stage;
    }
}
static int fail_before_probe(struct halogen_serving_kernel_identity *out, uint32_t stage) {
    drop_failure(out, stage);
    errno = (int)out->drop_errno;
    return 0;
}

int halogen_serving_observe_and_drop_bpf(
    struct halogen_serving_kernel_identity *out, uint32_t bytes, uint32_t activate) {
    /* These checks must precede even an output dereference or native snapshot. */
    if (activate != 1) {errno = EPERM; return 0;}
    if (!out || bytes != HALOGEN_SERVING_KERNEL_IDENTITY_BYTES) {
        errno = EINVAL;
        return 0;
    }
    memset(out, 0, sizeof(*out));
    out->abi_version = HALOGEN_SERVING_KERNEL_IDENTITY_ABI;
    out->struct_bytes = HALOGEN_SERVING_KERNEL_IDENTITY_BYTES;
    struct task_snapshot first_task, final_task;
    struct capability_snapshot before, after;
    if (!get_task(&first_task))
        return fail_before_probe(out, HALOGEN_SERVING_STAGE_INITIAL_TASK);
    if (!get_capabilities(&before))
        return fail_before_probe(out, HALOGEN_SERVING_STAGE_INITIAL_CAPABILITIES);
    record_before(out, &before);
    const uint64_t bpf_bit = UINT64_C(1) << CAP_BPF;
    const uint64_t setpcap_bit = UINT64_C(1) << CAP_SETPCAP;
    if (!(before.effective & bpf_bit) || !(before.permitted & bpf_bit) ||
        !(before.bounding & bpf_bit) || !(before.effective & setpcap_bit)) {
        errno = EPERM;
        return fail_before_probe(out, HALOGEN_SERVING_STAGE_CAPABILITY_PRECONDITION);
    }

    struct halogen_kernel_identity identity;
    int observed = halogen_observe_kernel_identity(&identity);
    if (observed) {
        out->kernel_pid = identity.kernel_pid;
        out->kernel_tgid = identity.kernel_tgid;
        out->namespace_pid = (int64_t)identity.namespace_pid;
        out->namespace_tid = (int64_t)identity.namespace_tid;
        out->proc_pid_namespace_inode = (uint64_t)identity.proc_pid_namespace_inode;
        out->probe_fds_closed = identity.probe_fds_closed;
        if (out->namespace_pid != first_task.pid || out->namespace_tid != first_task.tid ||
            out->proc_pid_namespace_inode != first_task.inode || !out->probe_fds_closed) {
            errno = EPROTO;
            observed = 0;
        }
    }
    if (!observed) {
        out->probe_errno = (uint32_t)error_number();
        out->failure_stage = HALOGEN_SERVING_STAGE_PROBE;
    }

    /* Do not short-circuit: even a failed probe attempts every BPF-only drop.
     * Nothing here adds CAP_SETPCAP or changes other capability bits. */
    if (prctl(PR_CAP_AMBIENT, (unsigned long)PR_CAP_AMBIENT_LOWER,
              (unsigned long)CAP_BPF, 0UL, 0UL))
        drop_failure(out, HALOGEN_SERVING_STAGE_AMBIENT_DROP);
    if (prctl(PR_CAPBSET_DROP, (unsigned long)CAP_BPF, 0UL, 0UL, 0UL))
        drop_failure(out, HALOGEN_SERVING_STAGE_BOUNDING_DROP);
    struct __user_cap_data_struct data[2];
    if (!get_cap_data(data)) {
        drop_failure(out, HALOGEN_SERVING_STAGE_CAPSET_DROP);
    } else {
        const uint32_t word_bit = UINT32_C(1) << (CAP_BPF % 32);
        data[CAP_BPF / 32].effective &= ~word_bit;
        data[CAP_BPF / 32].permitted &= ~word_bit;
        data[CAP_BPF / 32].inheritable &= ~word_bit;
        struct __user_cap_header_struct header = {
            .version = _LINUX_CAPABILITY_VERSION_3, .pid = 0
        };
        if (syscall(SYS_capset, &header, data))
            drop_failure(out, HALOGEN_SERVING_STAGE_CAPSET_DROP);
    }
    if (!get_capabilities(&after)) {
        drop_failure(out, HALOGEN_SERVING_STAGE_FINAL_CAPABILITIES);
    } else {
        record_after(out, &after);
        const uint64_t keep = ~bpf_bit;
        if (after.count != before.count || after.effective != (before.effective & keep) ||
            after.permitted != (before.permitted & keep) ||
            after.inheritable != (before.inheritable & keep) ||
            after.bounding != (before.bounding & keep) || after.ambient != (before.ambient & keep)) {
            errno = EPROTO;
            drop_failure(out, HALOGEN_SERVING_STAGE_FINAL_CAPABILITIES);
        } else if (!out->drop_errno) {
            out->capability_drop_checked = 1;
        }
    }
    if (!get_task(&final_task)) {
        drop_failure(out, HALOGEN_SERVING_STAGE_FINAL_TASK);
    } else if (final_task.pid != first_task.pid || final_task.tid != first_task.tid ||
               final_task.inode != first_task.inode) {
        errno = EPROTO;
        drop_failure(out, HALOGEN_SERVING_STAGE_FINAL_TASK);
    }
    if (observed && out->probe_fds_closed && out->capability_drop_checked && !out->drop_errno) {
        out->failure_stage = HALOGEN_SERVING_STAGE_NONE;
        errno = 0;
        return 1;
    }
    errno = out->drop_errno ? (int)out->drop_errno :
            out->probe_errno ? (int)out->probe_errno : EPROTO;
    return 0;
}
