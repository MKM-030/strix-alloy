/* Narrow Linux x86-64 LP64 declarations for Windows-hosted freestanding LLVM.
 * No implementation or substitute libc. Imports resolve to deployed libc at
 * root-owned Linux loading. Ordinary Linux builds use system headers instead. */
#ifndef ALLOY0173_FL_LINUX_ABI_H
#define ALLOY0173_FL_LINUX_ABI_H
typedef __UINT8_TYPE__ uint8_t;
typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;
typedef __UINT64_TYPE__ uint64_t;
typedef __INT64_TYPE__ int64_t;
typedef __UINTPTR_TYPE__ uintptr_t;
typedef __SIZE_TYPE__ size_t;
typedef long ssize_t;
typedef int pid_t;
typedef struct _IO_FILE FILE;
typedef union {char bytes[40];long alignment;} pthread_mutex_t;
typedef int pthread_once_t;
#define NULL ((void*)0)
#define EOF (-1)
#define UINT32_MAX 0xffffffffU
#define UINT64_MAX 0xffffffffffffffffUL
#define INT64_C(x) x##L
#define PTHREAD_MUTEX_INITIALIZER {{0}}
#define PTHREAD_ONCE_INIT 0
#define RTLD_NEXT ((void*)-1L)
#define RTLD_NOW 2
#define RTLD_LOCAL 0
#define EINTR 4
#define O_WRONLY 1
#define O_CREAT 0x40
#define O_EXCL 0x80
#define O_NOFOLLOW 0x20000
#define O_CLOEXEC 0x80000
struct iovec {void* iov_base;size_t iov_len;};
struct dl_phdr_info {uintptr_t dlpi_addr;const char* dlpi_name;const void* dlpi_phdr;unsigned short dlpi_phnum;};
extern FILE *stderr,*stdout;
extern int* __errno_location(void);
#define errno (*__errno_location())
extern void* dlopen(const char*,int);
extern void* dlsym(void*,const char*);
extern int dlclose(void*);
extern char* dlerror(void);
extern int dl_iterate_phdr(int(*)(struct dl_phdr_info*,size_t,void*),void*);
extern char* getenv(const char*);
extern void* malloc(size_t);
extern void free(void*);
extern void* memcpy(void*,const void*,size_t);
extern int memcmp(const void*,const void*,size_t);
extern int strcmp(const char*,const char*);
extern size_t strnlen(const char*,size_t);
extern FILE* fopen(const char*,const char*);
extern int fclose(FILE*);
extern size_t fread(void*,size_t,size_t,FILE*);
extern int ferror(FILE*);
extern int fgetc(FILE*);
extern int fflush(FILE*);
extern int printf(const char*,...);
extern int fprintf(FILE*,const char*,...);
extern int snprintf(char*,size_t,const char*,...);
extern int open(const char*,int,...);
extern int close(int);
extern ssize_t write(int,const void*,size_t);
extern ssize_t pwrite(int,const void*,size_t,long);
extern int fsync(int);
extern pid_t getpid(void);
extern ssize_t process_vm_readv(pid_t,const struct iovec*,unsigned long,const struct iovec*,unsigned long,unsigned long);
extern void _exit(int) __attribute__((noreturn));
extern int pthread_mutex_lock(pthread_mutex_t*);
extern int pthread_mutex_unlock(pthread_mutex_t*);
extern int pthread_once(pthread_once_t*,void(*)(void));
_Static_assert(sizeof(long)==8 && sizeof(void*)==8 && sizeof(pthread_mutex_t)==40,"Linux x86-64 libc ABI");
#endif
