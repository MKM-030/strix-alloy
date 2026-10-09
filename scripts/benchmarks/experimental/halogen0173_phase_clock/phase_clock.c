/* Default-off, measurement-only clock instrument for one exact upstream ELF.
 * The native start return remains the real libstdc++ MONOTONIC value. At one
 * proved measurement end, native_start + RAW_delta is returned, so existing
 * subtraction produces RAW duration. Scheduling/progress calls still forward.
 * No patch, accelerator API, kernel substitution, allocation, or sleep occurs.
 */
#include "phase_clock_core.h"
#include "phase_clock_pins.h"
typedef unsigned long h_uptr;
typedef h_i64 (*h_clock_fn)(void);
struct h_timespec { long seconds, nanos; };
struct h_stat { h_u64 dev,ino,nlink;h_u32 mode,uid,gid,pad;h_u64 rdev;
    h_i64 size,blksize,blocks,atime,atime_ns,mtime,mtime_ns,ctime,ctime_ns,reserved[3]; };
struct h_phdr { h_u32 type, flags; h_u64 offset, vaddr, paddr, filesz, memsz, align; };
struct h_dl_phdr_info { h_uptr base; const char *name; const struct h_phdr *phdr; unsigned short phnum; };
struct h_dl_info { const char *filename; void *base; const char *symbol; void *address; };
extern void *dlvsym(void *, const char *, const char *);
extern int dladdr(const void *,struct h_dl_info *);
extern int dl_iterate_phdr(int (*)(struct h_dl_phdr_info *,unsigned long,void *),void *);
extern char *getenv(const char *);
_Static_assert(sizeof(long)==8 && sizeof(void*)==8 && sizeof(h_i64)==8,"Linux x86-64 LP64 only");
_Static_assert(sizeof(struct h_stat)==144,"Linux x86-64 fstat ABI");

static h_clock_fn real_clock;
static h_uptr engine_base;
static int active;
static int prepared;
static const char *journal_path,*arm_path;
static h_uptr provider_base;
static h_u64 arm_device,arm_inode;
static long journal_fd=-1;
static unsigned lock_word;
static h_u64 sequence;
enum { PH_PREFILL=1, PH_DECODE=2, MAX_PAIRS=256 };
static struct h_pair pairs[MAX_PAIRS];
static long h_syscall(long n,long a,long b,long c,long d,long e,long f) {
    register long r10 __asm__("r10")=d, r8 __asm__("r8")=e, r9 __asm__("r9")=f;
    long result;
    __asm__ volatile("syscall":"=a"(result):"a"(n),"D"(a),"S"(b),"d"(c),"r"(r10),"r"(r8),"r"(r9):"rcx","r11","memory");
    return result;
}
static unsigned h_strlen(const char *p) { unsigned n=0;while(p[n] && n<4096)++n;return n; }
static int h_equal(const h_u8 *a,const h_u8 *b,unsigned n) { unsigned i;for(i=0;i<n;++i)if(a[i]!=b[i])return 0;return 1; }
static void h_lock(void) { while(__atomic_exchange_n(&lock_word,1,__ATOMIC_ACQUIRE))__asm__ volatile("pause"); }
static void h_unlock(void) { __atomic_store_n(&lock_word,0,__ATOMIC_RELEASE); }
static void h_fatal(const char *message) {
    (void)h_syscall(1,2,(long)message,h_strlen(message),0,0,0);
    (void)h_syscall(231,125,0,0,0,0,0);__builtin_unreachable();
}
static int h_hash_file(const char *path,const h_u8 *expected,h_u64 expected_size) {
    h_u8 buffer[8192],digest[32];struct hgn_sha256 sha;long fd,n;h_u64 size=0;
    fd=h_syscall(257,-100,(long)path,0x80000,0,0,0);if(fd<0)return 0;
    hgn_sha_init(&sha);
    for(;;) { n=h_syscall(0,fd,(long)buffer,sizeof(buffer),0,0,0);
        if(n==-4)continue;if(n<0){(void)h_syscall(3,fd,0,0,0,0,0);return 0;}if(!n)break;
        size+=(h_u64)n;if(size>expected_size){(void)h_syscall(3,fd,0,0,0,0,0);return 0;}
        hgn_sha_update(&sha,buffer,(h_u64)n);
    }
    (void)h_syscall(3,fd,0,0,0,0,0);hgn_sha_final(&sha,digest);
    return size==expected_size && h_equal(digest,expected,32);
}
static int h_find_main(struct h_dl_phdr_info *info,unsigned long size,void *unused) {
    unsigned i,j;(void)unused;if(size<sizeof(*info)||!info->name||info->name[0])return 0;
    if(!info->phdr||info->phnum>64)return 1;
    for(i=0;i<HGN_PIN_COUNT;++i) {
        int mapped=0;
        for(j=0;j<info->phnum;++j) {
            const struct h_phdr *p=&info->phdr[j];
            if(p->type==1 && p->flags==5 && hgn_pins[i].rva>=p->vaddr &&
               hgn_pins[i].rva+hgn_pins[i].size<=p->vaddr+p->memsz) mapped=1;
        }
        if(!mapped||!h_equal((const h_u8 *)(info->base+hgn_pins[i].rva),hgn_pins[i].bytes,hgn_pins[i].size))return 1;
    }
    engine_base=info->base;return 1;
}
static int h_raw(h_u64 *value) {
    struct h_timespec ts;
    /* Direct syscall: no broad clock_gettime interposition and no errno change. */
    if(h_syscall(228,4,(long)&ts,0,0,0,0)<0||ts.seconds<0||ts.nanos<0||ts.nanos>=1000000000L)return 0;
    if((h_u64)ts.seconds>(0x7fffffffffffffffULL-(h_u64)ts.nanos)/1000000000ULL)return 0;
    *value=(h_u64)ts.seconds*1000000000ULL+(h_u64)ts.nanos;return 1;
}
struct h_text { char data[1024]; unsigned size; };
static void h_put(struct h_text *s,const char *p) { unsigned i;for(i=0;p[i]&&s->size<sizeof(s->data);++i)s->data[s->size++]=p[i]; }
static void h_number(struct h_text *s,h_u64 v) { char b[21];unsigned n=0;do{b[n++]=(char)('0'+v%10);v/=10;}while(v);while(n&&s->size<sizeof(s->data))s->data[s->size++]=b[--n]; }
static void h_field(struct h_text *s,const char *name,h_u64 value) { h_put(s,",\"");h_put(s,name);h_put(s,"\":");h_number(s,value); }
static void h_signed_field(struct h_text *s,const char *name,h_i64 value) {
    h_put(s,",\"");h_put(s,name);h_put(s,"\":");
    if(value<0){h_put(s,"-");h_number(s,(h_u64)(-(value+1))+1);}else h_number(s,(h_u64)value);
}
static void h_emit(struct h_text *s) {
    long n;h_put(s,"}\n");
    do{n=h_syscall(1,journal_fd,(long)s->data,s->size,0,0,0);}while(n==-4);
    if(n!=(long)s->size)h_fatal("phase clock: journal write failed; no RAW qualification\n");
}
static void h_event(unsigned phase,unsigned begin,const struct h_pair *p,h_u64 raw_end,h_i64 actual_return,
                    unsigned status,h_uptr caller,h_uptr caller_stack,long caller_tid,
                    h_uptr object,h_i64 request_id,h_i64 observed_start,h_i64 object_start,
                    h_u64 prompt_bits,unsigned prompt,unsigned predicted) {
    struct h_text s={{0},0};h_put(&s,"{\"kind\":\"phase\"");h_field(&s,"sequence",++sequence);
    h_field(&s,"begin",begin);h_field(&s,"pair_id",p->pair_id);h_field(&s,"caller_stack",caller_stack);
    h_field(&s,"phase",phase);h_field(&s,"status",status);h_signed_field(&s,"request_id",request_id);
    h_field(&s,"object",object);h_field(&s,"begin_object",p->key);
    h_field(&s,"tid",(h_u64)caller_tid);h_field(&s,"caller_rva",caller);
    h_field(&s,"native_start_ns",(h_u64)p->native_start);h_field(&s,"raw_start_ns",p->raw_start);
    h_field(&s,"observed_native_start_ns",(h_u64)observed_start);h_field(&s,"object_native_start_ns",(h_u64)object_start);
    h_field(&s,"raw_end_ns",raw_end);h_field(&s,"returned_end_ns",(h_u64)actual_return);
    h_field(&s,"raw_delta_ns",raw_end>=p->raw_start?raw_end-p->raw_start:0);
    if(phase==PH_DECODE){h_field(&s,"native_prefill_ms_bits",prompt_bits);h_field(&s,"prompt_count",prompt);h_field(&s,"predicted_count",predicted);}
    h_emit(&s);
}
static void h_require_absent(const char *path,const char *message) {
    long fd=h_syscall(257,-100,(long)path,0xa0800,0,0,0);
    if(fd>=0){(void)h_syscall(3,fd,0,0,0,0,0);h_fatal(message);}
    if(fd!=-2)h_fatal(message);
}
static void h_activate(void) {
    struct h_text s={{0},0};
    /* O_WRONLY|O_CREAT|O_EXCL|O_APPEND|O_CLOEXEC|O_NOFOLLOW. */
    journal_fd=h_syscall(257,-100,(long)journal_path,0xa04c1,0600,0,0);
    if(journal_fd<0)h_fatal("phase clock: cannot create fresh audit journal\n");
    h_put(&s,"{\"kind\":\"activation\",\"engine_sha256\":\"" HGN_ENGINE_SHA_HEX "\",\"provider_sha256\":\"" HGN_PROVIDER_SHA_HEX "\"");
    h_field(&s,"engine_base",engine_base);h_field(&s,"real_clock_address",(h_uptr)real_clock);
    h_field(&s,"provider_base",provider_base);h_field(&s,"raw_clock_id",4);h_field(&s,"default_off",1);
    h_field(&s,"decode_pairing_version",2);
    h_field(&s,"deferred_arm",arm_path?1:0);h_field(&s,"arm_file_device",arm_device);h_field(&s,"arm_file_inode",arm_inode);
    h_emit(&s);__atomic_store_n(&active,1,__ATOMIC_RELEASE);
}
static int h_arm_if_ready(void) {
    struct h_stat stat;long fd;
    if(__atomic_load_n(&active,__ATOMIC_ACQUIRE))return 1;
    fd=h_syscall(257,-100,(long)arm_path,0xa0800,0,0,0);
    if(fd==-2)return 0;
    if(fd<0)h_fatal("phase clock: arming file open rejected\n");
    if(h_syscall(5,fd,(long)&stat,0,0,0,0)<0 || (stat.mode&0xf000)!=0x8000 ||
       (stat.mode&0777)!=0600 || stat.size!=0 || stat.nlink!=1 ||
       stat.uid!=(h_u32)h_syscall(107,0,0,0,0,0,0))
        h_fatal("phase clock: arming file must be an empty owned regular0600 file\n");
    (void)h_syscall(3,fd,0,0,0,0,0);
    h_lock();
    if(!__atomic_load_n(&active,__ATOMIC_ACQUIRE)){
        arm_device=stat.dev;arm_inode=stat.ino;h_activate();
    }
    h_unlock();return 1;
}
__attribute__((constructor)) static void h_initialize(void) {
    struct h_dl_info binding;const char *on,*journal,*arm;h_u64 raw;
    real_clock=(h_clock_fn)dlvsym((void *)-1L,"_ZNSt6chrono3_V212steady_clock3nowEv","GLIBCXX_3.4.19");
    if(!real_clock)h_fatal("phase clock: real GLIBCXX_3.4.19 steady clock unavailable\n");
    on=getenv("HGN0173_PHASE_RAW");if(!on||on[0]!='1'||on[1])return;
    if(!h_hash_file("/proc/self/exe",hgn_engine_sha,HGN_ENGINE_BYTES))h_fatal("phase clock: exact engine SHA/size rejected\n");
    (void)dl_iterate_phdr(h_find_main,(void *)0);
    if(!engine_base)h_fatal("phase clock: mapped measurement instruction bytes rejected\n");
    if(!dladdr((const void *)real_clock,&binding)||!binding.filename||!binding.base||
       (h_uptr)real_clock-(h_uptr)binding.base!=0xd5490UL||
       !h_equal((const h_u8 *)real_clock,hgn_provider_code,sizeof(hgn_provider_code))||
       !h_hash_file(binding.filename,hgn_provider_sha,2497768ULL))
        h_fatal("phase clock: real libstdc++ symbol/provider binding rejected\n");
    if(!h_raw(&raw))h_fatal("phase clock: initial CLOCK_MONOTONIC_RAW unavailable\n");
    journal=getenv("HGN0173_PHASE_JOURNAL");
    if(!journal||journal[0]!='/'||h_strlen(journal)>=4096)h_fatal("phase clock: fresh absolute journal path required\n");
    journal_path=journal;provider_base=(h_uptr)binding.base;
    arm=getenv("HGN0173_PHASE_ARM_FILE");
    if(arm){
        if(arm[0]!='/'||h_strlen(arm)>=4096)h_fatal("phase clock: fresh absolute arming path required\n");
        if(h_strlen(arm)==h_strlen(journal)&&h_equal((const h_u8 *)arm,(const h_u8 *)journal,h_strlen(arm)))
            h_fatal("phase clock: journal and arming path must differ\n");
        h_require_absent(journal,"phase clock: deferred journal path is not fresh\n");
        h_require_absent(arm,"phase clock: arming path must not exist at startup\n");
        arm_path=arm;__atomic_store_n(&prepared,1,__ATOMIC_RELEASE);return;
    }
    h_activate();
}

__attribute__((visibility("hidden"))) h_i64 hgn_phase_now(h_uptr caller,h_uptr stack,
    h_uptr saved_r14,h_uptr saved_rbx,h_i64 saved_r15) {
    h_i64 native_value,end_value,request_id,observed_start,object_start=0;
    h_u64 raw_value=0,prompt_bits=0;unsigned phase,start,i,slot,matches,free_slot=MAX_PAIRS,status=0;
    unsigned prompt=0,predicted=0;h_uptr key,rva;long tid;struct h_pair *pair=(void*)0,missing={0};
    /* Calls before our constructor also use the exact versioned real provider. */
    if(!real_clock) {
        h_clock_fn early=(h_clock_fn)dlvsym((void *)-1L,"_ZNSt6chrono3_V212steady_clock3nowEv","GLIBCXX_3.4.19");
        if(!early)h_fatal("phase clock: early real symbol unavailable\n");return early();
    }
    if(!__atomic_load_n(&active,__ATOMIC_ACQUIRE)){
        if(!__atomic_load_n(&prepared,__ATOMIC_ACQUIRE))return real_clock();
        rva=caller-engine_base;
        /* Only selected starts poll while waiting; ends and unrelated callers
         * remain pure forwarding. Activation/journal happens before this start. */
        if((rva!=0x1746b3fUL&&rva!=0x17490bbUL)||!h_arm_if_ready())return real_clock();
    }
    rva=caller-engine_base;
    if(rva==0x1746b3fUL){phase=PH_PREFILL;start=1;key=saved_r14;}
    else if(rva==0x1746f16UL){phase=PH_PREFILL;start=0;key=saved_r14;}
    else if(rva==0x17490bbUL){phase=PH_DECODE;start=1;key=saved_r14;}
    else if(rva==0x174ca12UL){phase=PH_DECODE;start=0;key=saved_rbx;}
    else return real_clock();
    /* RAW sample immediately follows native start; end RAW sample precedes
     * bookkeeping. Native endpoints are still called exactly once. */
    if(start){native_value=real_clock();status=h_raw(&raw_value)?0:1;}
    else{status=h_raw(&raw_value)?0:1;native_value=real_clock();}
    request_id=*(const h_i64 *)key;
    tid=h_syscall(186,0,0,0,0,0,0);h_lock();
    slot=hgn_pair_lookup(pairs,MAX_PAIRS,phase,key,stack,tid,request_id,&free_slot,&matches);
    if(matches==1)pair=&pairs[slot];
    if(matches>1){
        /* Never select an arbitrary duplicate signed-ID record. */
        for(i=0;i<MAX_PAIRS;++i)
            if(hgn_pair_identity(&pairs[i],phase,key,stack,tid,request_id))pairs[i].valid=0;
        status=7;
    }
    if(start){
        /* Duplicate begins are visible and invalidate the old pair. They must
         * never silently overwrite a begin that was not consumed. */
        if(pair){pair->valid=0;status=5;}
        if(!pair&&free_slot<MAX_PAIRS)pair=&pairs[free_slot];
        if(pair){pair->key=key;pair->stack=stack;pair->tid=tid;pair->native_start=native_value;
            pair->request_id=request_id;pair->raw_start=raw_value;pair->pair_id=sequence+1;pair->phase=phase;pair->valid=status?0:1;}
        else status=2;
        if(!pair){missing.key=key;missing.stack=stack;missing.tid=tid;missing.request_id=request_id;
            missing.native_start=native_value;missing.raw_start=raw_value;missing.pair_id=sequence+1;pair=&missing;}
        h_event(phase,1,pair,raw_value,native_value,status,rva,stack,tid,key,request_id,native_value,0,0,0,0);
        h_unlock();return native_value;
    }
    if(!pair){if(!status)status=3;missing.key=key;missing.tid=tid;missing.request_id=request_id;pair=&missing;}
    if(phase==PH_PREFILL){end_value=*(const h_i64 *)(stack+0x18);}
    else{end_value=saved_r15;object_start=*(const h_i64 *)(key+0x198);prompt_bits=*(const h_u64 *)(key+0x190);
        prompt=*(const unsigned *)(key+0x54);predicted=*(const unsigned *)(key+0x58);}
    observed_start=end_value;
    if(!status && pair->request_id!=request_id)status=6;
    if(!status && phase==PH_DECODE && object_start!=observed_start)status=8;
    if(!status&&!hgn_phase_delta(pair->native_start,pair->raw_start,raw_value,end_value,&end_value))status=4;
    /* A failed pair uses untouched native start/end; never fabricate a delta. */
    if(status)end_value=native_value;
    h_event(phase,0,pair,raw_value,end_value,status,rva,stack,tid,key,request_id,observed_start,object_start,prompt_bits,prompt,predicted);
    if(pair!=&missing)pair->valid=0;
    h_unlock();return end_value;
}
