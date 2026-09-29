/* Separate test-only interposer. Never linked into the production bridge. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

static unsigned thunk_attempts, protection_calls, stat_calls;
static int fault(const char *wanted) {
    const char *value = getenv("FIXTURE_BRIDGE_FAULT");
    return value && !strcmp(value, wanted);
}
void *mmap(void *address, size_t length, int prot, int flags, int fd, off_t offset) {
    void *(*real_mmap)(void *,size_t,int,int,int,off_t) = dlsym(RTLD_NEXT, "mmap");
    if (flags & MAP_FIXED_NOREPLACE) {
        ++thunk_attempts;
        if ((flags & MAP_FIXED) || (prot & PROT_EXEC)) _exit(88);
        if (fault("mmap_exhaust")) {
            if (thunk_attempts == 256) dprintf(2, "fixture bounded attempts=256\n");
            if (thunk_attempts > 256) _exit(88);
            errno = EEXIST; return MAP_FAILED;
        }
        if (fault("mmap_error")) { errno = ENOMEM; return MAP_FAILED; }
        if (fault("mmap_wrong_address") || fault("munmap_error"))
            return real_mmap(NULL, length, prot, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    }
    return real_mmap(address, length, prot, flags, fd, offset);
}
int munmap(void *address, size_t length) {
    int (*real_munmap)(void *,size_t) = dlsym(RTLD_NEXT, "munmap");
    if (fault("munmap_error")) { errno = EIO; return -1; }
    return real_munmap(address, length);
}
int mprotect(void *address, size_t length, int prot) {
    int (*real_mprotect)(void *,size_t,int) = dlsym(RTLD_NEXT, "mprotect");
    if (thunk_attempts) {
        ++protection_calls;
        if ((prot & (PROT_WRITE | PROT_EXEC)) == (PROT_WRITE | PROT_EXEC)) _exit(88);
        if ((fault("thunk_rx") && protection_calls == 1) ||
            (fault("text_rw") && protection_calls == 2) ||
            (fault("text_rx") && protection_calls == 3)) { errno = EACCES; return -1; }
    }
    return real_mprotect(address, length, prot);
}
int fstat(int fd, struct stat *out) {
    int (*real_fstat)(int,struct stat *) = dlsym(RTLD_NEXT, "fstat");
    int result = real_fstat(fd, out);
    if (fault("stat_error")) { errno = EIO; return -1; }
    if (!result && fault("stat_drift") && ++stat_calls == 2) ++out->st_ctim.tv_sec;
    return result;
}
ssize_t pread(int fd, void *buffer, size_t count, off_t offset) {
    ssize_t (*real_pread)(int,void *,size_t,off_t) = dlsym(RTLD_NEXT, "pread");
    if (fault("read_error")) { errno = EIO; return -1; }
    return real_pread(fd, buffer, count, offset);
}
