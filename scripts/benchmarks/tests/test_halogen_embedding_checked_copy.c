/* Focused host-only checked-copy contract; no HIP/engine activation. */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/uio.h>
#include <unistd.h>

static unsigned copy_calls;
static ssize_t last_copy_bytes;
static ssize_t counted_readv(pid_t pid,const struct iovec *local,unsigned long locals,
        const struct iovec *remote,unsigned long remotes,unsigned long flags) {
    copy_calls++;last_copy_bytes=process_vm_readv(pid,local,locals,remote,remotes,flags);
    return last_copy_bytes;
}
static char *inactive_getenv(const char *name) {(void)name;return NULL;}
#define process_vm_readv counted_readv
#define getenv inactive_getenv
#include "../halogen0162_mtp_embedding_cache.c"
#undef getenv
#undef process_vm_readv

static void range_checks(void) {
    long page=sysconf(_SC_PAGESIZE);assert(page>0);
    unsigned char *memory=mmap(NULL,(size_t)page*3,PROT_READ|PROT_WRITE,
        MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    assert(memory!=MAP_FAILED);memset(memory,0x5a,(size_t)page*3);
    assert(!mprotect(memory+page,(size_t)page,PROT_READ));
    unsigned char copied[8]={0};
    struct checked_copy_query query={(uintptr_t)(memory+page-4),copied,sizeof copied};
    copy_calls=0;assert(checked_copy(&query,1) && copy_calls==1);
    for (unsigned i=0;i<sizeof copied;i++) assert(copied[i]==0x5a);
    /* Readability may span adjacent VMAs; a hole must reject the entire read. */
    assert(!munmap(memory+page,(size_t)page));
    assert(!checked_copy(&query,1));assert(last_copy_bytes==4);
    query.address=(uintptr_t)(memory+page);assert(!checked_copy(&query,1));
    struct checked_copy_query invalid[3]={{0,copied,4},{(uintptr_t)memory,copied,0},
        {UINTPTR_MAX-3,copied,8}};
    for (unsigned i=0;i<3;i++) {
        copy_calls=0;assert(!checked_copy(&invalid[i],1) && !copy_calls);
    }
    copy_calls=0;assert(!checked_copy(NULL,1) && !checked_copy(&query,0) &&
        !checked_copy(&query,CHECKED_COPY_MAX_QUERIES+1) && !copy_calls);
    assert(!munmap(memory,(size_t)page) && !munmap(memory+2*page,(size_t)page));
}

static void argument_checks(void) {
    long page=sysconf(_SC_PAGESIZE);assert(page>0);
    unsigned char *memory=mmap(NULL,(size_t)page*2,PROT_READ|PROT_WRITE,
        MAP_PRIVATE|MAP_ANONYMOUS,-1,0);assert(memory!=MAP_FAILED);
    uint64_t cells[3]={11,12,13};int32_t width=2560,groups=1;
    memcpy(memory+page-4,&width,4);assert(!munmap(memory+page,(size_t)page));
    void *args[5]={&cells[0],&cells[1],&cells[2],memory+page-4,&groups};
    uintptr_t values[5]={0};
    copy_calls=0;assert(checked_launch_arguments(args,values,5,24u) && copy_calls==2);
    assert(values[0]==11 && values[1]==12 && values[2]==13 && values[3]==2560 && values[4]==1);
    cells[1]=99;assert(values[1]==12); /* Consumers use the owned values. */
    assert(!checked_launch_arguments(args,values,5,0)); /* i64 would touch the hole. */
    args[2]=NULL;assert(!checked_launch_arguments(args,values,5,24u));
    assert(!checked_launch_arguments(NULL,values,5,24u));
    assert(!checked_launch_arguments(args,values,0,0) &&
        !checked_launch_arguments(args,values,5,1u<<5));
    assert(!munmap(memory,(size_t)page));
}

static void current_context_checks(void) {
    unsigned char model[MODEL_BYTES]={0},wire[9]={0};int32_t token=17,outer=4,slot=2;
    struct head_context context={.model=(uintptr_t)model,.tokens=(uintptr_t)&token,
        .token=17,.outer_position=4,.slot=2};
    model[0x900]=1;memcpy(model+0x220,&outer,4);memcpy(model+0xa0,&slot,4);
    wire[0]='D';wire[8]=1;engine_base=(uintptr_t)wire-WIRE_RVA;
    checked_copy_mode=1;ready_mode=1;fixed_rows=1;
    bound.model=(uintptr_t)model;bound.thread=pthread_self();bound.wire_guard=1;bound_ready=1;
    struct host_snapshot entry;copy_calls=0;
    assert(!checked_head_entry(model,NULL,1,0,0x17dcc08,&entry) && !copy_calls);
    assert(context_live(&context));
    uintptr_t live_tokens=context.tokens;context.tokens=0;
    assert(!context_live(&context) && head_completion_live(&context));context.tokens=live_tokens;
    token++;assert(!context_live(&context));token--;
    model[0x908+0x18]=1;assert(!context_live(&context));model[0x908+0x18]=0;
    uintptr_t changed=16;memcpy(model+0x730,&changed,8);assert(!context_live(&context));
    memset(model+0x730,0,8);wire[8]=2;assert(!context_live(&context));wire[8]=1;
    wire[0]='X';assert(!context_live(&context));wire[0]='D';
    outer++;memcpy(model+0x220,&outer,4);assert(!context_live(&context));
    /* Completion retains the native binding+slot contract, not outer/token equality. */
    token++;assert(head_completion_live(&context));
    slot++;memcpy(model+0xa0,&slot,4);assert(!head_completion_live(&context));
    slot--;memcpy(model+0xa0,&slot,4);outer--;memcpy(model+0x220,&outer,4);token--;
    atomic_store(&retired,1);copy_calls=0;assert(!context_live(&context) && !copy_calls);
    atomic_store(&retired,0);assert(context_live(&context));bound_ready=0;
}

static void fixed_readiness_checks(void) {
    memset(&cache,0,sizeof cache);atomic_flag_clear(&cache.busy);
    cache.initialized=1;cache.capacity=1;
    cache.entries[0]=(struct ecache_entry){.device=(void *)0x10000,.token=17,.valid=1};
    const uint16_t *row=NULL;fixed_import_synchronized=1;
    assert(lookup_fixed_ready(17,&row)==ECACHE_HIT && row==(const uint16_t *)0x10000);
    assert(!cache.stats.event_queries && !cache.stats.copy_enqueues);
    assert(lookup_fixed_ready(18,&row)==ECACHE_MISS && !row);
    fixed_import_synchronized=0;assert(lookup_fixed_ready(17,&row)==ECACHE_ERROR);
    cache.initialized=0;checked_copy_mode=0;ready_mode=0;fixed_rows=0;
}

int main(void) {
    assert(!atomic_load(&enabled));range_checks();argument_checks();
    current_context_checks();fixed_readiness_checks();
    puts("checked-copy host contract passed");return 0;
}
