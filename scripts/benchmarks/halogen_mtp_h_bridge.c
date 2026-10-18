/* Finite root-owned Linux launcher and resident socket bridge. Default off.
 * gcc -O2 -Wall -Wextra -Werror this.c -o bridge
 * bridge --run HOST_IPV4 PORT LIFETIME_MS -- /absolute/engine [args...]
 * No Python/file polling or process creation in a projection exchange.
 * This is source infrastructure, not qualified transport/performance.
 */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include "halogen_mtp_h_wire.h"

#if !defined(__linux__) || !defined(__x86_64__)
#error Linux x86-64 only
#endif

#define FRAME_BYTES HGNH_FRAME_BYTES
#define HELLO_BYTES HGNH_HELLO_BYTES
#define REQUEST_BYTES HGNH_REQUEST_BYTES
#define RESPONSE_BYTES HGNH_RESPONSE_BYTES
#define MAX_CALLS HGNH_MAX_CALLS
static volatile sig_atomic_t cancelled;
static const char *bridge_error;
static void on_signal(int value) { (void)value; cancelled=1; }
static int fail(const char *reason) {if(!bridge_error) bridge_error=reason;return 0;}
static uint64_t now_ns(void) {
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t)) return 0;
    return (uint64_t)t.tv_sec*1000000000ULL+(uint64_t)t.tv_nsec;
}
static uint32_t le32(const unsigned char *p) {
    return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
static uint64_t le64(const unsigned char *p) {
    return (uint64_t)le32(p)|(uint64_t)le32(p+4)<<32;
}
static int number(const char *s,unsigned lower,unsigned upper,unsigned *out) {
    if(!s || !*s) return 0;
    for(const char *p=s;*p;p++) if(*p<'0'||*p>'9') return 0;
    errno=0; char *end=NULL; unsigned long n=strtoul(s,&end,10);
    if(errno||*end||n<lower||n>upper) return 0;
    *out=(unsigned)n; return 1;
}
static int wait_io(int fd,short wanted,int pidfd,uint64_t deadline) {
    for(;;) {
        uint64_t now=now_ns();
        if(cancelled||!now||now>=deadline) return 0;
        uint64_t left=deadline-now;
        struct timespec timeout={(time_t)(left/1000000000ULL),(long)(left%1000000000ULL)};
        struct pollfd p[2]={{fd,wanted,0},{pidfd,POLLIN,0}};
        int n=ppoll(p,pidfd<0?1U:2U,&timeout,NULL);
        if(n<0&&errno==EINTR) continue;
        if(n<=0) return 0;
        if(pidfd>=0 && p[1].revents) return 0;
        /* Read queued final data before interpreting peer HUP. */
        if(p[0].revents&wanted) return 1;
        if(p[0].revents&(POLLERR|POLLHUP|POLLNVAL)) return 0;
    }
}
static int exact_io(int fd,unsigned char *data,size_t bytes,int writing,int pidfd,uint64_t deadline) {
    size_t done=0;
    while(done<bytes) {
        if(!wait_io(fd,writing?POLLOUT:POLLIN,pidfd,deadline)) return 0;
        ssize_t n=writing?send(fd,data+done,bytes-done,MSG_NOSIGNAL):recv(fd,data+done,bytes-done,0);
        if(n<0&&(errno==EAGAIN||errno==EWOULDBLOCK||errno==EINTR)) continue;
        if(n<=0) return 0;
        done+=(size_t)n;
    }
    uint64_t now=now_ns();return !cancelled && now && now<deadline;
}
static int copy_frame(int from,int to,uint32_t kind,uint32_t bytes,uint64_t sequence,
                      int pidfd,uint64_t deadline) {
    unsigned char packet[FRAME_BYTES+RESPONSE_BYTES];
    if(bytes>RESPONSE_BYTES || !exact_io(from,packet,FRAME_BYTES,0,pidfd,deadline)) return 0;
    if(memcmp(packet,"HGNHFRM1",8)||le32(packet+8)!=kind||le32(packet+12)!=bytes||
       le64(packet+16)!=sequence) return 0;
    if(!exact_io(from,packet+FRAME_BYTES,bytes,0,pidfd,deadline)) return 0;
    /* Endpoints authenticate payload and session identity. The relay constrains
     * direction, sequence and extent; it never interprets model pointers. */
    return exact_io(to,packet,FRAME_BYTES+bytes,1,pidfd,deadline);
}
/* An idle responder owes no bytes. FIN, reset, and unsolicited data all poison
 * the session. This check is also used while the engine consumes a final reply.
 * It proves socket state, not remote Windows job identity or authentication. */
static int remote_quiet(int remote) {
    for(;;) {
        unsigned char byte;
        ssize_t count=recv(remote,&byte,1,MSG_PEEK|MSG_DONTWAIT);
        if(count>0) return fail("remote-unsolicited-data");
        if(count==0) return fail("remote-eof");
        if(errno==EAGAIN||errno==EWOULDBLOCK) return 1;
        if(errno!=EINTR) return fail("remote-peek-error");
        if(cancelled) return fail("cancelled");
    }
}
/* 1 complete header, 2 EOF at an empty header boundary, 0 failure. Drain local
 * queued bytes before interpreting child exit; partial headers never become a
 * clean exit merely because the owned child exits with code0. */
static int boundary_header(int local,int remote,int pidfd,unsigned char *header,uint64_t lifetime,
                           uint64_t *exchange_deadline) {
    size_t done=0;
    *exchange_deadline=lifetime;
    while(done<FRAME_BYTES) {
        uint64_t deadline=*exchange_deadline;
        uint64_t now=now_ns();
        if(cancelled||!now||now>=deadline) return fail("request-boundary-deadline");
        if(!remote_quiet(remote)) return 0;
        ssize_t count=recv(local,header+done,FRAME_BYTES-done,MSG_DONTWAIT);
        if(count>0) {
            if(done==0) {
                uint64_t first=now_ns();
                if(!first||UINT64_MAX-first<200000000ULL) return fail("request-first-byte-clock");
                uint64_t phase=first+200000000ULL;
                *exchange_deadline=phase<lifetime?phase:lifetime;
            }
            done+=(size_t)count;continue;
        }
        if(count==0) return done?fail("local-truncated-header"):2;
        if(errno==EINTR) continue;
        if(errno!=EAGAIN&&errno!=EWOULDBLOCK) return fail("local-header-read");
        uint64_t left=deadline-now;
        struct timespec timeout={(time_t)(left/1000000000ULL),(long)(left%1000000000ULL)};
        struct pollfd p[3]={{local,POLLIN,0},{pidfd,POLLIN,0},{remote,POLLIN,0}};
        int ready=ppoll(p,3,&timeout,NULL);
        if(ready<0&&errno==EINTR) continue;
        if(ready<=0) return fail("request-boundary-wait");
        if(p[2].revents && !remote_quiet(remote)) return 0;
        if(p[0].revents&(POLLERR|POLLNVAL)) return fail("local-boundary-poll");
        if(p[1].revents) {
            unsigned char byte;
            ssize_t queued=recv(local,&byte,1,MSG_PEEK|MSG_DONTWAIT);
            if(queued==0) return done?fail("local-truncated-header"):2;
            if(queued>0) continue;
            /* An inherited extra writer or ambiguous socket state cannot prove
             * an empty terminal boundary. Do not spin on a readable pidfd. */
            return fail("child-exit-without-local-eof");
        }
    }
    return 1;
}
/* 1 forwarded request, 2 clean empty next-frame EOF, 0 protocol/transport fault. */
static int next_request(int local,int remote,uint64_t sequence,int pidfd,uint64_t deadline) {
    unsigned char packet[FRAME_BYTES+REQUEST_BYTES];
    uint64_t exchange_deadline=deadline;
    int state=boundary_header(local,remote,pidfd,packet,deadline,&exchange_deadline);
    if(state!=1) return state;
    if(memcmp(packet,HGNH_FRAME_MAGIC,8)||le32(packet+8)!=HGNH_REQUEST||
       le32(packet+12)!=REQUEST_BYTES||le64(packet+16)!=sequence) return fail("request-frame-header");
    /* Header remainder, body and forwarding share one200ms first-byte budget.
     * While body input is incomplete, remote loss is observed within this
     * bounded budget even though exact_io watches local/pidfd only. */
    if(!exact_io(local,packet+FRAME_BYTES,REQUEST_BYTES,0,pidfd,exchange_deadline)) return fail("local-request-body");
    if(!remote_quiet(remote)) return 0;
    if(!exact_io(remote,packet,FRAME_BYTES+REQUEST_BYTES,1,pidfd,exchange_deadline)) return fail("request-forward");
    return 1;
}
static uint64_t earlier(uint64_t a,uint64_t b) {return a<b?a:b;}
static int private_ipv4(uint32_t network) {
    uint32_t a=ntohl(network);
    return (a>>24)==127U || (a>>24)==10U || (a>>20)==0xac1U || (a>>16)==0xc0a8U;
}
/* 1 terminal (reaped exactly once), 0 live, -1 wait error. No reusable-PID lookup. */
static int reap_child(pid_t child,int *status) {
    for(;;) {
        pid_t result=waitpid(child,status,WNOHANG);
        if(result==child) return 1;
        if(result==0) return 0;
        if(errno!=EINTR) return -1;
    }
}
static int wait_terminal(pid_t child,int pidfd,uint64_t deadline,int *status,int heed_cancel) {
    for(;;) {
        int state=reap_child(child,status);
        if(state) return state;
        uint64_t now=now_ns();
        if(!now||now>=deadline||(heed_cancel&&cancelled)) return 0;
        uint64_t left=deadline-now;
        struct timespec timeout={(time_t)(left/1000000000ULL),(long)(left%1000000000ULL)};
        struct pollfd p={pidfd,POLLIN,0};
        int result=ppoll(&p,pidfd<0?0U:1U,&timeout,NULL);
        if(result<0&&errno!=EINTR) return -1;
    }
}
/* Budget exhaustion / local EOF is not head completion. Retain both channels
 * and observe remote death until the exact owned child becomes terminal. No
 * post-budget local data is legal, even if queued by an already exited child.
 * A local EOF alone merely stops polling that permanently readable socket. */
static int wait_owned_end(pid_t child,int pidfd,int local,int remote,uint64_t deadline,
                          int *status,int local_eof) {
    for(;;) {
        if(!local_eof) {
            unsigned char byte;ssize_t queued=recv(local,&byte,1,MSG_PEEK|MSG_DONTWAIT);
            if(queued>0) {fail("local-post-budget-data");return 0;}
            if(queued==0) local_eof=1;
            else if(errno==EINTR) continue;
            else if(errno!=EAGAIN&&errno!=EWOULDBLOCK) {fail("local-end-peek");return 0;}
        }
        int state=reap_child(child,status);
        if(state) return state;
        uint64_t now=now_ns();
        if(cancelled||!now||now>=deadline) {fail("owned-end-deadline");return 0;}
        if(!remote_quiet(remote)) return 0;
        uint64_t left=deadline-now;
        struct timespec timeout={(time_t)(left/1000000000ULL),(long)(left%1000000000ULL)};
        struct pollfd p[3]={{pidfd,POLLIN,0},{remote,POLLIN,0},{local_eof?-1:local,POLLIN,0}};
        int ready=ppoll(p,3,&timeout,NULL);
        if(ready<0&&errno!=EINTR) {fail("owned-end-poll");return -1;}
        /* Re-enter with all sockets/child status checked; no millisecond poll. */
    }
}
static int signal_owned(pid_t child,int pidfd,int sig) {
    int result;
#ifdef SYS_pidfd_send_signal
    result=pidfd>=0?(int)syscall(SYS_pidfd_send_signal,pidfd,sig,NULL,0):kill(child,sig);
#else
    result=kill(child,sig);
#endif
    return result==0||errno==ESRCH;
}
int main(int argc,char **argv) {
    unsigned port=0,lifetime=0;
    if(argc<7||strcmp(argv[1],"--run")||strcmp(argv[5],"--")||argv[6][0]!='/'||
       !number(argv[3],1024,65535,&port)||!number(argv[4],1000,120000,&lifetime)) {
        fprintf(stderr,"Explicit --run private-HOST_IPV4 PORT LIFETIME_MS -- /absolute/engine required\n");
        return 2;
    }
    struct sockaddr_in address={0}; address.sin_family=AF_INET;address.sin_port=htons((uint16_t)port);
    if(inet_pton(AF_INET,argv[2],&address.sin_addr)!=1||!private_ipv4(address.sin_addr.s_addr)) return 2;
    const char *enable=getenv("HALOGEN_MTP_H_NATIVE");
    if(!enable||strcmp(enable,"replace64-v1")) return 2;
    struct sigaction action={0};action.sa_handler=on_signal;sigemptyset(&action.sa_mask);
    if(sigaction(SIGINT,&action,NULL)||sigaction(SIGTERM,&action,NULL)) return 2;
    signal(SIGPIPE,SIG_IGN);
    uint64_t start=now_ns();
    if(!start||UINT64_MAX-start<(uint64_t)lifetime*1000000ULL) return 2;
    uint64_t deadline=start+(uint64_t)lifetime*1000000ULL;
    int pair[2]={-1,-1},remote=-1,pidfd=-1,good=0,status=0,terminal=0,cleanup_ok=1;pid_t child=-1;
    unsigned exchanges=0;int boundary_eof=0;
    remote=socket(AF_INET,SOCK_STREAM|SOCK_CLOEXEC|SOCK_NONBLOCK,0);
    if(remote<0) goto cleanup;
    int one=1;
    if(setsockopt(remote,IPPROTO_TCP,TCP_NODELAY,&one,sizeof one)) goto cleanup;
    if(connect(remote,(struct sockaddr *)&address,sizeof address)) {
        if(errno!=EINPROGRESS||!wait_io(remote,POLLOUT,-1,earlier(deadline,start+2000000000ULL))) goto cleanup;
        int error=0;socklen_t length=sizeof error;
        if(getsockopt(remote,SOL_SOCKET,SO_ERROR,&error,&length)||error) goto cleanup;
    }
    if(socketpair(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC|SOCK_NONBLOCK,0,pair)) goto cleanup;
    pid_t guardian=getpid(); child=fork();
    if(child<0) goto cleanup;
    if(child==0) {
        close(pair[0]);close(remote);
        if(prctl(PR_SET_PDEATHSIG,SIGKILL)||getppid()!=guardian) _exit(125);
        signal(SIGPIPE,SIG_DFL);
        char fd_text[32],peer_text[32];
        snprintf(fd_text,sizeof fd_text,"%d",pair[1]);
        snprintf(peer_text,sizeof peer_text,"%ld",(long)guardian);
        int flags=fcntl(pair[1],F_GETFD);
        if(flags<0||fcntl(pair[1],F_SETFD,flags&~FD_CLOEXEC)||
           setenv("HALOGEN_MTP_H_FD",fd_text,1)||setenv("HALOGEN_MTP_H_PEER_PID",peer_text,1)) _exit(125);
        execv(argv[6],&argv[6]);_exit(127);
    }
    close(pair[1]);pair[1]=-1;
#ifdef SYS_pidfd_open
    pidfd=(int)syscall(SYS_pidfd_open,child,0);
#endif
    if(pidfd<0) goto cleanup; /* Do not rely on a reusable numeric PID. */
    uint64_t arm_deadline=earlier(deadline,now_ns()+2000000000ULL);
    if(!copy_frame(pair[0],remote,HGNH_HELLO,HELLO_BYTES,0,pidfd,arm_deadline)||
       !copy_frame(remote,pair[0],HGNH_READY,HELLO_BYTES,0,pidfd,arm_deadline)) {
        fail("handshake-frame");goto cleanup;
    }
    for(unsigned sequence=0;sequence<MAX_CALLS;sequence++) {
        int next=next_request(pair[0],remote,sequence,pidfd,deadline);
        if(next==0) goto cleanup;
        if(next==2) {boundary_eof=1;break;}
        uint64_t reply_deadline=earlier(deadline,now_ns()+200000000ULL);
        if(!copy_frame(remote,pair[0],HGNH_RESPONSE,RESPONSE_BYTES,sequence,pidfd,reply_deadline)) {
            fail("response-frame");goto cleanup;
        }
        exchanges++;
    }
    /* Budget exhaustion is not full-head completion. Keep both endpoints and
     * guardian alive until the original child exits normally. Owner controls
     * the finite workload/lifetime; no65th exchange or optimistic success. */
    terminal=wait_owned_end(child,pidfd,pair[0],remote,deadline,&status,boundary_eof);
    good=terminal==1&&WIFEXITED(status)&&WEXITSTATUS(status)==0;
cleanup:
    if(pair[0]>=0 && close(pair[0])) cleanup_ok=0;
    if(pair[1]>=0 && close(pair[1])) cleanup_ok=0;
    if(remote>=0 && close(remote)) cleanup_ok=0;
    /* Only the child just forked by this launcher is owned. pidfd pins its
     * identity even if it exits while cleanup runs. No foreign process lookup. */
    if(child>0) {
        if(terminal==0) terminal=reap_child(child,&status);
        if(terminal==0) {
            if(!signal_owned(child,pidfd,SIGTERM)) cleanup_ok=0;
            terminal=wait_terminal(child,pidfd,now_ns()+2000000000ULL,&status,0);
        }
        if(terminal==0) {
            if(!signal_owned(child,pidfd,SIGKILL)) cleanup_ok=0;
            terminal=wait_terminal(child,pidfd,now_ns()+2000000000ULL,&status,0);
        }
        if(terminal!=1) cleanup_ok=0;
    }
    if(pidfd>=0 && close(pidfd)) cleanup_ok=0;
    fprintf(stderr,"H bridge terminal: finite transport %s child_terminal=%d child_exit=%d cleanup_ok=%d "
        "exchanges=%u error=%s; not a speed qualification\n",
        good?"completed":"failed",terminal==1,terminal==1&&WIFEXITED(status)?WEXITSTATUS(status):-1,cleanup_ok,
        exchanges,bridge_error?bridge_error:"none");
    return good&&cleanup_ok?0:cleanup_ok?1:126;
}
