/* Host-only live mapping validation. No HIP library, engine or activation. */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

static unsigned maps_opens;
static FILE *counted_fopen(const char *path,const char *mode) {
    if (!strcmp(path,"/proc/self/maps")) maps_opens++;
    return fopen(path,mode);
}
static char *inactive_getenv(const char *name) {(void)name;return NULL;}
#define fopen counted_fopen
#define getenv inactive_getenv
#ifndef HALOGEN_MAP_TEST_SOURCE
#define HALOGEN_MAP_TEST_SOURCE "../halogen0162_mtp_embedding_cache.c"
#endif
#include HALOGEN_MAP_TEST_SOURCE
#undef getenv
#undef fopen

/* Run the same assertions against the retained unbatched source baseline. */
#ifndef MAPPED_SPANS_MAX
#define MAPPED_SPANS_MAX 8u
struct mapped_query {uintptr_t address;size_t bytes;const char *wanted;};
static int mapped_spans(const struct mapped_query *queries,unsigned count) {
    if (!queries || !count || count>MAPPED_SPANS_MAX) return 0;
    for (unsigned i=0;i<count;i++)
        if (!mapped_span(queries[i].address,queries[i].bytes,queries[i].wanted)) return 0;
    return 1;
}
#endif

static void range_checks(void) {
    long page=sysconf(_SC_PAGESIZE);assert(page>0);
    unsigned char *memory=mmap(NULL,(size_t)page*3,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    assert(memory!=MAP_FAILED && !mprotect(memory+page,(size_t)page,PROT_READ));
    struct mapped_query readable[3]={
        {(uintptr_t)memory,8,NULL},
        {(uintptr_t)(memory+page),(size_t)page,"r--p"},
        {(uintptr_t)(memory+2*page),8,NULL}
    };
    maps_opens=0;assert(mapped_spans(readable,3));assert(maps_opens==1);
    struct mapped_query crossing={(uintptr_t)(memory+page-4),8,NULL};
    assert(!mapped_spans(&crossing,1));
    struct mapped_query wrong_permissions={(uintptr_t)(memory+page),4,"rw-p"};
    assert(!mapped_spans(&wrong_permissions,1));
    assert(!munmap(memory+page,(size_t)page));
    assert(!mapped_spans(readable,3));
    struct mapped_query malformed[3]={{0,4,NULL},{(uintptr_t)memory,0,NULL},{UINTPTR_MAX-3,8,NULL}};
    for (unsigned i=0;i<3;i++) {
        maps_opens=0;assert(!mapped_spans(&malformed[i],1));assert(!maps_opens);
    }
    maps_opens=0;assert(!mapped_spans(NULL,1) && !mapped_spans(readable,0) &&
        !mapped_spans(readable,MAPPED_SPANS_MAX+1));assert(!maps_opens);
    assert(!munmap(memory,(size_t)page) && !munmap(memory+2*page,(size_t)page));
}

static void argument_checks(void) {
    uint64_t cells[5]={11,12,13,14,15};void *args[5];uintptr_t values[5]={0};
    for (unsigned i=0;i<5;i++) args[i]=&cells[i];
    maps_opens=0;assert(launch_arguments(args,values,5,0));assert(maps_opens==2);
    for (unsigned i=0;i<5;i++) assert(values[i]==(uintptr_t)&cells[i]);
    maps_opens=0;assert(!launch_arguments(NULL,values,5,0));assert(!maps_opens);
    args[3]=NULL;maps_opens=0;assert(!launch_arguments(args,values,5,0));assert(maps_opens==1);
}

static void current_context_checks(void) {
    unsigned char model[MODEL_BYTES]={0},wire[16]={0};int32_t token=17;
    struct head_context context={.model=(uintptr_t)model,.tokens=(uintptr_t)&token,.token=17};
    model[0x900]=1;wire[0]='D';wire[8]=1;engine_base=(uintptr_t)wire-WIRE_RVA;
    bound.model=(uintptr_t)model;bound.thread=pthread_self();bound.wire_guard=1;bound_ready=1;
    maps_opens=0;assert(context_live(&context));assert(maps_opens==1);
    token++;assert(!context_live(&context));token--;
    model[0x908+0x18]=1;assert(!context_live(&context));model[0x908+0x18]=0;
    uintptr_t changed=16;memcpy(model+0x4f0,&changed,sizeof changed);assert(!context_live(&context));
    memset(model+0x4f0,0,sizeof changed);
    atomic_store(&retired,1);maps_opens=0;assert(!context_live(&context));assert(!maps_opens);
    atomic_store(&retired,0);assert(context_live(&context));bound_ready=0;
}

int main(void) {
    assert(!atomic_load(&enabled));range_checks();argument_checks();current_context_checks();
    puts("live mapping batch checks passed");return 0;
}
