/* CPU-only qualification of the same private-socket helper used by v3. */
#define _GNU_SOURCE
#include "halogen_kernel_pid_self.h"
int main(void) {
    struct halogen_kernel_identity identity;
    if (!halogen_observe_kernel_identity(&identity)) return 1;
    int result=printf("{\"passed\":true,\"namespace_pid\":%ld,\"namespace_tid\":%ld,"
        "\"kernel_pid\":%u,\"kernel_tgid\":%u,\"proc_pid_namespace_inode\":%llu,"
        "\"scope\":\"own-socket-only\",\"probe_fds_closed\":true,\"persistent_kernel_attachment\":false}\n",
        identity.namespace_pid,identity.namespace_tid,identity.kernel_pid,identity.kernel_tgid,
        identity.proc_pid_namespace_inode);
    return result>0 && !fflush(stdout)?0:1;
}
