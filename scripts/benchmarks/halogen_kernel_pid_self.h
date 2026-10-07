/* Private, ephemeral AF_UNIX socket filter; no global attachment or pinning.
 * The datagram is filtered synchronously in this main thread's send context.
 * Close every probe reference before reporting an observed kernel identity. */
#ifndef HALOGEN_KERNEL_PID_SELF_H
#define HALOGEN_KERNEL_PID_SELF_H
#include <errno.h>
#include <linux/bpf.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

struct halogen_kernel_identity {
    uint32_t kernel_pid, kernel_tgid;
    long namespace_pid, namespace_tid;
    unsigned long long proc_pid_namespace_inode;
    unsigned probe_fds_closed;
};

static int halogen_bpf_call(enum bpf_cmd command, union bpf_attr *attribute) {
    return (int)syscall(__NR_bpf,command,attribute,sizeof(*attribute));
}
#define KPID_I(c,d,s,o,m) ((struct bpf_insn){.code=(c),.dst_reg=(d),.src_reg=(s),.off=(o),.imm=(m)})
static int halogen_observe_kernel_identity(struct halogen_kernel_identity *out) {
    int map=-1,program=-1,sockets[2]={-1,-1},observed=0,saved_error=0,closed=1;
    char log[16384]={0};
    union bpf_attr attribute={0};
    uint32_t key=0;
    uint64_t value=0;
    struct stat pid_namespace;
    memset(out,0,sizeof(*out));
    out->namespace_pid=(long)getpid();
    out->namespace_tid=syscall(__NR_gettid);
    if (out->namespace_pid<=0 || out->namespace_tid!=out->namespace_pid) {
        errno=EPROTO;goto cleanup;
    }
    attribute.map_type=BPF_MAP_TYPE_ARRAY;
    attribute.key_size=sizeof key;attribute.value_size=sizeof value;attribute.max_entries=1;
    map=halogen_bpf_call(BPF_MAP_CREATE,&attribute);
    if (map<0) goto cleanup;
    struct bpf_insn instructions[]={
        KPID_I(BPF_JMP|BPF_CALL,0,0,0,BPF_FUNC_get_current_pid_tgid),
        KPID_I(BPF_ALU64|BPF_MOV|BPF_X,6,0,0,0),
        KPID_I(BPF_ST|BPF_W|BPF_MEM,10,0,-4,0),
        KPID_I(BPF_LD|BPF_DW|BPF_IMM,1,BPF_PSEUDO_MAP_FD,0,map),KPID_I(0,0,0,0,0),
        KPID_I(BPF_ALU64|BPF_MOV|BPF_X,2,10,0,0),KPID_I(BPF_ALU64|BPF_ADD|BPF_K,2,0,0,-4),
        KPID_I(BPF_JMP|BPF_CALL,0,0,0,BPF_FUNC_map_lookup_elem),
        KPID_I(BPF_JMP|BPF_JEQ|BPF_K,0,0,1,0),KPID_I(BPF_STX|BPF_DW|BPF_MEM,0,6,0,0),
        KPID_I(BPF_ALU64|BPF_MOV|BPF_K,0,0,0,1),KPID_I(BPF_JMP|BPF_EXIT,0,0,0,0)
    };
    memset(&attribute,0,sizeof attribute);
    attribute.prog_type=BPF_PROG_TYPE_SOCKET_FILTER;
    attribute.insn_cnt=sizeof instructions/sizeof instructions[0];
    attribute.insns=(uint64_t)(uintptr_t)instructions;
    attribute.license=(uint64_t)(uintptr_t)"GPL";
    attribute.log_buf=(uint64_t)(uintptr_t)log;attribute.log_size=sizeof log;attribute.log_level=1;
    program=halogen_bpf_call(BPF_PROG_LOAD,&attribute);
    if (program<0) goto cleanup;
    if (socketpair(AF_UNIX,SOCK_DGRAM|SOCK_CLOEXEC,0,sockets) ||
        setsockopt(sockets[1],SOL_SOCKET,SO_ATTACH_BPF,&program,sizeof program)) goto cleanup;
    if (send(sockets[0],"X",1,0)!=1) goto cleanup;
    char byte=0;
    if (recv(sockets[1],&byte,1,MSG_DONTWAIT)!=1) goto cleanup;
    if (byte!='X') {errno=EPROTO;goto cleanup;}
    memset(&attribute,0,sizeof attribute);
    attribute.map_fd=map;attribute.key=(uint64_t)(uintptr_t)&key;attribute.value=(uint64_t)(uintptr_t)&value;
    if (halogen_bpf_call(BPF_MAP_LOOKUP_ELEM,&attribute)) goto cleanup;
    out->kernel_pid=(uint32_t)value;out->kernel_tgid=(uint32_t)(value>>32);
    if (!out->kernel_pid || out->kernel_pid>INT32_MAX || out->kernel_pid!=out->kernel_tgid) {
        errno=EPROTO;goto cleanup;
    }
    if (stat("/proc/self/ns/pid",&pid_namespace)) goto cleanup;
    out->proc_pid_namespace_inode=(unsigned long long)pid_namespace.st_ino;
    if (!out->proc_pid_namespace_inode) {errno=EPROTO;goto cleanup;}
    observed=1;
cleanup:
    if (!observed) saved_error=errno?errno:EPROTO;
    for (unsigned i=0;i<2;i++) if (sockets[i]>=0 && close(sockets[i])) {
        if (!saved_error) saved_error=errno;
        closed=0;
    }
    if (program>=0 && close(program)) {if (!saved_error) saved_error=errno;closed=0;}
    if (map>=0 && close(map)) {if (!saved_error) saved_error=errno;closed=0;}
    if (observed && closed) {out->probe_fds_closed=1;return 1;}
    errno=saved_error?saved_error:EPROTO;
    fprintf(stderr,"own-socket BPF PID probe failed errno=%d: %s\n%s",errno,strerror(errno),log);
    return 0;
}
#undef KPID_I
#endif
