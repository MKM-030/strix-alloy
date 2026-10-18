/* Default-OFF diagnostics for one independently mapped0.18.1 ELF.
 * Every real chrono call occurs exactly once and returns its ORIGINAL RAX.
 * Only readonly native fields and new observer-owned state are accessed.
 * No native time/duration/divisor/counter store, accelerator API or patch. */
#include "observer_core.h"
#include "phase_clock_pins.h"
typedef unsigned long h_uptr;
typedef h_i64 (*h_clock_fn)(void);
struct h_timespec { long seconds,nanos; };
struct h_stat { h_u64 dev,ino,nlink;h_u32 mode,uid,gid,pad;h_u64 rdev;h_i64 size,blksize,blocks,atime,atime_ns,mtime,mtime_ns,ctime,ctime_ns,reserved[3]; };
struct h_phdr { h_u32 type,flags;h_u64 offset,vaddr,paddr,filesz,memsz,align; };
struct h_dl_phdr_info { h_uptr base;const char *name;const struct h_phdr *phdr;unsigned short phnum; };
struct h_dl_info { const char *filename;void *base;const char *symbol;void *address; };
extern void *dlvsym(void *,const char *,const char *);
extern int dladdr(const void *,struct h_dl_info *);
extern int dl_iterate_phdr(int (*)(struct h_dl_phdr_info *,unsigned long,void *),void *);
extern char *getenv(const char *);
_Static_assert(sizeof(long)==8&&sizeof(void*)==8,"Linux x86-64 LP64 only");
_Static_assert(sizeof(struct h_stat)==144,"Linux x86-64 fstat ABI");
enum { PH_PREFILL=1,PH_DECODE=2,MAX_PAIRS=256,MAX_OWNERS=256 };
static h_clock_fn real_clock;
static h_uptr engine_base,provider_base;
static unsigned active,prepared,lock_word;
static const char *journal_path,*arm_path,*nonce;
static h_u64 sequence,epoch_counter,arm_device,arm_inode,dropped;
static long journal_fd=-1;
static struct h_pair pairs[MAX_PAIRS];
static struct h_owner owners[MAX_OWNERS];
static inline long h_syscall(long n,long a,long b,long c,long d,long e,long f) {
#ifdef HGN_OBSERVER_CPU_TEST
 extern long hgn_cpu_syscall(long,long,long,long,long,long,long);
 return hgn_cpu_syscall(n,a,b,c,d,e,f);
#else
 register long r10 __asm__("r10")=d,r8 __asm__("r8")=e,r9 __asm__("r9")=f;long result;
 __asm__ volatile("syscall":"=a"(result):"a"(n),"D"(a),"S"(b),"d"(c),"r"(r10),"r"(r8),"r"(r9):"rcx","r11","memory");return result;
#endif
}
static inline unsigned h_strlen(const char *p) { unsigned n=0;while(p[n]&&n<4096)++n;return n; }
static inline int h_equal(const h_u8 *a,const h_u8 *b,unsigned n) { unsigned i;for(i=0;i<n;++i)if(a[i]!=b[i])return 0;return 1; }
static void h_lock(void) { while(__atomic_exchange_n(&lock_word,1,__ATOMIC_ACQUIRE))__asm__ volatile("pause"); }
static void h_unlock(void) { __atomic_store_n(&lock_word,0,__ATOMIC_RELEASE); }
static inline void h_fatal(const char *message) {
 (void)h_syscall(1,2,(long)message,h_strlen(message),0,0,0);(void)h_syscall(231,125,0,0,0,0,0);__builtin_unreachable();
}
static inline int h_hash_file(const char *path,const h_u8 *expected,h_u64 expected_size) {
 h_u8 buffer[8192],digest[32];struct hgn_sha256 s;long fd,n;h_u64 size=0;
 fd=h_syscall(257,-100,(long)path,0x80000,0,0,0);if(fd<0)return 0;hgn_sha_init(&s);
 for(;;){n=h_syscall(0,fd,(long)buffer,sizeof(buffer),0,0,0);if(n==-4)continue;
  if(n<0){(void)h_syscall(3,fd,0,0,0,0,0);return 0;}if(!n)break;size+=(h_u64)n;
  if(size>expected_size){(void)h_syscall(3,fd,0,0,0,0,0);return 0;}hgn_sha_update(&s,buffer,(h_u64)n);}
 (void)h_syscall(3,fd,0,0,0,0,0);hgn_sha_final(&s,digest);return size==expected_size&&h_equal(digest,expected,32);
}
static inline int h_find_main(struct h_dl_phdr_info *info,unsigned long size,void *unused) {
 unsigned i,j;(void)unused;if(size<sizeof(*info)||!info->name||info->name[0])return 0;
 if(!info->phdr||info->phnum>64)return 1;
 for(i=0;i<HGN_PIN_COUNT;++i){int mapped=0;for(j=0;j<info->phnum;++j){const struct h_phdr *p=&info->phdr[j];
  if(p->type==1&&p->flags==5&&hgn_pins[i].rva>=p->vaddr&&hgn_pins[i].rva+hgn_pins[i].size<=p->vaddr+p->memsz)mapped=1;}
  if(!mapped||!h_equal((const h_u8 *)(info->base+hgn_pins[i].rva),hgn_pins[i].bytes,hgn_pins[i].size))return 1;}
 engine_base=info->base;return 1;
}
static int h_raw(h_u64 *v) {
 struct h_timespec ts;
 if(h_syscall(228,4,(long)&ts,0,0,0,0)<0||ts.seconds<0||ts.nanos<0||ts.nanos>=1000000000L)return 0;
 if((h_u64)ts.seconds>(0x7fffffffffffffffULL-(h_u64)ts.nanos)/1000000000ULL)return 0;
 *v=(h_u64)ts.seconds*1000000000ULL+(h_u64)ts.nanos;return 1;
}
struct h_text { char data[2048];unsigned size,overflow; };
static void h_put(struct h_text *s,const char *p) { unsigned i;for(i=0;p[i];++i){if(s->size>=sizeof(s->data)){s->overflow=1;return;}s->data[s->size++]=p[i];} }
static void h_number(struct h_text *s,h_u64 v) { char b[21];unsigned n=0;do{b[n++]=(char)('0'+v%10);v/=10;}while(v);
 while(n){if(s->size>=sizeof(s->data)){s->overflow=1;return;}s->data[s->size++]=b[--n];} }
static void h_field(struct h_text *s,const char *n,h_u64 v) { h_put(s,",\"");h_put(s,n);h_put(s,"\":");h_number(s,v); }
static void h_signed(struct h_text *s,const char *n,h_i64 v) { h_put(s,",\"");h_put(s,n);h_put(s,"\":");
 if(v<0){h_put(s,"-");h_number(s,(h_u64)(-(v+1))+1);}else h_number(s,(h_u64)v); }
/* Runtime diagnostic failure disables capture and preserves native serving.
 * The incomplete/nonzero-status journal is fail-closed in the offline reader. */
static int h_emit(struct h_text *s) { long n;h_put(s,"}\n");
 if(s->overflow){++dropped;__atomic_store_n(&active,0,__ATOMIC_RELEASE);__atomic_store_n(&prepared,0,__ATOMIC_RELEASE);return 0;}
 do{n=h_syscall(1,journal_fd,(long)s->data,s->size,0,0,0);}while(n==-4);
 if(n!=(long)s->size){++dropped;__atomic_store_n(&active,0,__ATOMIC_RELEASE);__atomic_store_n(&prepared,0,__ATOMIC_RELEASE);return 0;}return 1; }
static void h_event(unsigned phase,unsigned begin,const struct h_pair *p,h_i64 value,unsigned status,
 h_u64 before,h_u64 after,h_u64 book,h_uptr rva,h_uptr stack,h_i64 tid,h_uptr object,h_i64 rid,
 h_i64 observed,h_i64 object_start,h_u64 prefill,unsigned prompt,unsigned predicted) {
 struct h_text s={{0},0,0};h_put(&s,"{\"kind\":\"phase\"");h_field(&s,"sequence",++sequence);
 h_field(&s,"phase",phase);h_field(&s,"begin",begin);h_field(&s,"pair_id",p->pair_id);h_field(&s,"request_epoch",p->epoch);
 h_field(&s,"status",status);h_signed(&s,"request_id",rid);h_field(&s,"caller_rva",rva);h_field(&s,"caller_stack",stack);
 h_signed(&s,"tid",tid);h_field(&s,"object",object);h_field(&s,"begin_object",p->object);
 h_signed(&s,"native_return_ns",value);h_signed(&s,"returned_ns",value);h_signed(&s,"native_start_ns",p->native_start);
 h_field(&s,"raw_before_ns",before);h_field(&s,"raw_after_ns",after);h_field(&s,"start_raw_before_ns",p->raw_before);
 h_field(&s,"start_raw_after_ns",p->raw_after);h_signed(&s,"observed_native_start_ns",observed);
 h_signed(&s,"object_native_start_ns",object_start);h_field(&s,"bookkeeping_done_raw_ns",book);h_field(&s,"dropped",dropped);
 if(phase==PH_DECODE){h_field(&s,"prompt_count",prompt);h_field(&s,"predicted_count",predicted);
  if(!begin)h_field(&s,"native_prefill_ms_bits",prefill);}
 (void)h_emit(&s);
}
static void h_overhead(h_u64 phase_sequence,h_u64 epoch,h_u64 before,h_u64 after,h_u64 book,h_u64 emit_done,unsigned status) {
 struct h_text s={{0},0,0};h_put(&s,"{\"kind\":\"overhead\"");h_field(&s,"sequence",++sequence);h_field(&s,"phase_sequence",phase_sequence);
 h_field(&s,"request_epoch",epoch);h_field(&s,"raw_before_ns",before);h_field(&s,"raw_after_ns",after);
 h_field(&s,"bookkeeping_done_raw_ns",book);h_field(&s,"phase_emit_done_raw_ns",emit_done);h_field(&s,"status",status);
 h_field(&s,"dropped",dropped);(void)h_emit(&s);
}
static inline void h_require_absent(const char *path,const char *message) {
 long fd=h_syscall(257,-100,(long)path,0xa0800,0,0,0);if(fd>=0){(void)h_syscall(3,fd,0,0,0,0,0);h_fatal(message);}if(fd!=-2)h_fatal(message);
}
static void h_activate(void) {
 struct h_text s={{0},0,0};journal_fd=h_syscall(257,-100,(long)journal_path,0xa04c1,0600,0,0);if(journal_fd<0)h_fatal("observer: fresh journal required\n");
 h_put(&s,"{\"kind\":\"activation\",\"schema\":\"halogen0181.passive-phase.v1\",\"engine_sha256\":\"" HGN_ENGINE_SHA_HEX "\",\"provider_sha256\":\"" HGN_PROVIDER_SHA_HEX "\",\"nonce\":\"");h_put(&s,nonce);h_put(&s,"\"");
 h_field(&s,"engine_base",engine_base);h_field(&s,"real_clock_address",(h_uptr)real_clock);h_field(&s,"provider_base",provider_base);
 h_field(&s,"raw_clock_id",4);h_field(&s,"default_off",1);h_field(&s,"native_returns_unchanged",1);
 h_field(&s,"deferred_arm",arm_path?1:0);h_field(&s,"arm_file_device",arm_device);h_field(&s,"arm_file_inode",arm_inode);
 if(!h_emit(&s))h_fatal("observer: activation journal failed\n");__atomic_store_n(&active,1,__ATOMIC_RELEASE);
}
static int h_arm_if_ready(void) {
 struct h_stat stat;long fd;if(__atomic_load_n(&active,__ATOMIC_ACQUIRE))return 1;
 fd=h_syscall(257,-100,(long)arm_path,0xa0800,0,0,0);if(fd==-2)return 0;if(fd<0)h_fatal("observer: arming open rejected\n");
 if(h_syscall(5,fd,(long)&stat,0,0,0,0)<0||(stat.mode&0xf000)!=0x8000||(stat.mode&0777)!=0600||stat.size!=0||stat.nlink!=1||stat.uid!=(h_u32)h_syscall(107,0,0,0,0,0,0))h_fatal("observer: owned empty0600 arm required\n");
 (void)h_syscall(3,fd,0,0,0,0,0);h_lock();if(!__atomic_load_n(&active,__ATOMIC_ACQUIRE)){arm_device=stat.dev;arm_inode=stat.ino;h_activate();}h_unlock();return 1;
}
#ifndef HGN_OBSERVER_CPU_TEST
__attribute__((constructor)) static void h_initialize(void) {
 struct h_dl_info binding;const char *on,*arm;h_u64 raw;unsigned i;
 real_clock=(h_clock_fn)dlvsym((void *)-1L,"_ZNSt6chrono3_V212steady_clock3nowEv","GLIBCXX_3.4.19");
 if(!real_clock)h_fatal("observer: versioned real provider unavailable\n");on=getenv("HGN0181_OBSERVER_ENABLE");if(!on||on[0]!='1'||on[1])return;
 if(!h_hash_file("/proc/self/exe",hgn_engine_sha,HGN_ENGINE_BYTES))h_fatal("observer: exact engine rejected\n");
 (void)dl_iterate_phdr(h_find_main,(void *)0);if(!engine_base)h_fatal("observer: mapped source pins rejected\n");
 if(!dladdr((const void *)real_clock,&binding)||!binding.filename||!binding.base||(h_uptr)real_clock-(h_uptr)binding.base!=0xd5490UL||!h_equal((const h_u8 *)real_clock,hgn_provider_code,sizeof(hgn_provider_code))||!h_hash_file(binding.filename,hgn_provider_sha,2497768ULL))h_fatal("observer: exact provider binding rejected\n");
 if(!h_raw(&raw))h_fatal("observer: RAW unavailable\n");provider_base=(h_uptr)binding.base;
 nonce=getenv("HGN0181_OBSERVER_NONCE");if(!nonce||h_strlen(nonce)!=32)h_fatal("observer:32hex nonce required\n");
 for(i=0;i<32;++i)if(!((nonce[i]>='0'&&nonce[i]<='9')||(nonce[i]>='a'&&nonce[i]<='f')))h_fatal("observer: nonce rejected\n");
 journal_path=getenv("HGN0181_OBSERVER_JOURNAL");if(!journal_path||journal_path[0]!='/'||h_strlen(journal_path)>=4096)h_fatal("observer: fresh absolute journal required\n");
 arm=getenv("HGN0181_OBSERVER_ARM_FILE");if(arm){if(arm[0]!='/'||h_strlen(arm)>=4096||(h_strlen(arm)==h_strlen(journal_path)&&h_equal((const h_u8 *)arm,(const h_u8 *)journal_path,h_strlen(arm))))h_fatal("observer: distinct fresh arm required\n");
  h_require_absent(journal_path,"observer: journal not fresh\n");h_require_absent(arm,"observer: arm not fresh\n");arm_path=arm;__atomic_store_n(&prepared,1,__ATOMIC_RELEASE);return;}
 h_activate();
}
#endif
__attribute__((visibility("hidden"))) h_i64 hgn_phase_now(h_uptr caller,h_uptr stack,h_uptr saved_r14,h_uptr saved_rbx,h_i64 saved_r15) {
 h_uptr rva,key=saved_r14;h_i64 native,rid,observed=0,object_start=0,tid;h_u64 before=0,after=0,book=0,emit_done=0,prefill=0,phase_sequence;
 unsigned phase,begin,status=0,matches,free_slot,slot,i,prompt=0,predicted=0;struct h_owner *owner=(void*)0;
 struct h_pair *pair=(void*)0,missing={0};(void)saved_r15;
 if(!real_clock){
#ifdef HGN_OBSERVER_CPU_TEST
  return 0;
#else
  h_clock_fn early=(h_clock_fn)dlvsym((void *)-1L,"_ZNSt6chrono3_V212steady_clock3nowEv","GLIBCXX_3.4.19");if(!early)h_fatal("observer: early provider unavailable\n");return early();
#endif
 }
 if(!__atomic_load_n(&active,__ATOMIC_ACQUIRE)){if(!__atomic_load_n(&prepared,__ATOMIC_ACQUIRE))return real_clock();
  rva=caller-engine_base;if((rva!=0x181870fUL&&rva!=0x181a8dcUL)||!h_arm_if_ready())return real_clock();}
 rva=caller-engine_base;
 if(rva==0x181870fUL){phase=PH_PREFILL;begin=1;}else if(rva==0x1818d60UL){phase=PH_PREFILL;begin=0;}
 else if(rva==0x181a8dcUL){phase=PH_DECODE;begin=1;}else if(rva==0x181e7c2UL){phase=PH_DECODE;begin=0;}else return real_clock();
 /* The single native call is bracketed before ANY identity/count sampling. */
 if(!h_raw(&before))status=1;native=real_clock();if(!h_raw(&after))status=1;
 if(!hgn_bracket_valid(before,after))status=1;
 rid=*(const h_i64 *)key;tid=h_syscall(186,0,0,0,0,0,0);h_lock();
 slot=hgn_owner_find(owners,MAX_OWNERS,rid,&matches,&free_slot);
 if(matches==1)owner=&owners[slot];
 if(matches>1)status=9;
 if(begin&&!owner&&free_slot<MAX_OWNERS){owner=&owners[free_slot];owner->used=1;owner->request_id=rid;owner->epoch=++epoch_counter;owner->stage=phase;owner->prefill_object=phase==PH_PREFILL?key:0;}
 else if(begin&&owner){if(owner->bad||owner->stage==3||(phase==PH_PREFILL&&(owner->stage!=PH_PREFILL||owner->prefill_object!=key))||(phase==PH_DECODE&&owner->stage==PH_DECODE))status=9;
  if(!status&&phase==PH_DECODE)owner->stage=PH_DECODE;}
 if(!owner){if(!status)status=2;missing.request_id=rid;missing.object=key;}
 if(owner&&owner->bad&&!status)status=9;
 if(phase==PH_DECODE){prompt=*(const unsigned *)(key+0x54);predicted=*(const unsigned *)(key+0x58);}
 if(!begin){observed=phase==PH_PREFILL?*(const h_i64 *)(stack+0x18):(h_i64)saved_rbx;
  if(phase==PH_DECODE){object_start=*(const h_i64 *)(key+0x1c8);prefill=*(const h_u64 *)(key+0x1c0);}}
 slot=hgn_pair_find(pairs,MAX_PAIRS,phase,rid,owner?owner->epoch:0,key,stack,tid,begin?native:observed,&matches,&free_slot);
 if(matches==1)pair=&pairs[slot];if(matches>1)status=7;
 if(begin){
  /* Reject any other open Decode for the same owner, including a differing
   * native timestamp; an existing begin must never be silently replaced. */
  for(i=0;i<MAX_PAIRS;++i)if(pairs[i].valid&&pairs[i].epoch==(owner?owner->epoch:0)&&pairs[i].request_id==rid){
   if(pairs[i].phase==phase)status=5;else if(phase==PH_DECODE)status=10;}
  if(!pair&&free_slot<MAX_PAIRS)pair=&pairs[free_slot];if(!pair){if(!status)status=2;pair=&missing;}
  pair->object=key;pair->stack=stack;pair->tid=tid;pair->request_id=rid;pair->epoch=owner?owner->epoch:0;
  pair->native_start=native;pair->raw_before=before;pair->raw_after=after;pair->pair_id=sequence+1;pair->phase=phase;pair->valid=status?0:1;observed=native;
 }else{
  if(!pair){if(!status)status=3;pair=&missing;pair->epoch=owner?owner->epoch:0;}
  if(!status&&!hgn_pair_valid(pair,native,observed,before,after))status=4;
  if(!status&&phase==PH_DECODE&&object_start!=pair->native_start)status=8;
  if(pair!=&missing)pair->valid=0;if(owner&&phase==PH_DECODE)owner->stage=3;
 }
 if(owner&&status)owner->bad=1;if(!h_raw(&book)||book<after)status=1;
 phase_sequence=sequence+1;h_event(phase,begin,pair,native,status,before,after,book,rva,stack,tid,key,rid,observed,object_start,prefill,prompt,predicted);
 if(!h_raw(&emit_done)||emit_done<book)status=1;
 if(__atomic_load_n(&active,__ATOMIC_ACQUIRE))h_overhead(phase_sequence,pair->epoch,before,after,book,emit_done,status);
 h_unlock();return hgn_unchanged(native);
}
