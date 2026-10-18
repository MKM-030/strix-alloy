/* Root-owned CPU executable test of the REAL C producer with fake syscalls.
 * No engine/library/device is loaded. Requires Linux x86-64 LP64; agent did
 * not compile or execute this harness. All time values are synthetic fixtures. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define HGN_OBSERVER_CPU_TEST 1
#include "phase_clock.c"
static h_i64 test_native;
static h_u64 test_raw;
static unsigned test_calls,test_reads,test_bad_raw,test_short_write;
static char test_log[65536];static unsigned test_log_size;
static h_i64 test_clock(void) { ++test_calls;return test_native; }
long hgn_cpu_syscall(long n,long a,long b,long c,long d,long e,long f) {
 (void)a;(void)d;(void)e;(void)f;
 if(n==228){struct h_timespec *ts=(struct h_timespec *)b;++test_reads;if(test_bad_raw)return -5;
  test_raw+=100;ts->seconds=(long)(test_raw/1000000000ULL);ts->nanos=(long)(test_raw%1000000000ULL);return 0;}
 if(n==186)return 91;
 if(n==1){if(test_short_write)return c-1;assert(c>=0&&test_log_size+(unsigned)c<sizeof(test_log));
  memcpy(test_log+test_log_size,(const void *)b,(unsigned)c);test_log_size+=(unsigned)c;test_log[test_log_size]=0;return c;}
 if(n==231){assert(!"Unexpected fatal test path");return -1;}return -1;
}
static void reset_test(void) {
 memset(pairs,0,sizeof(pairs));memset(owners,0,sizeof(owners));memset(test_log,0,sizeof(test_log));
 active=1;prepared=0;lock_word=0;sequence=0;epoch_counter=0;dropped=0;journal_fd=7;engine_base=0;
 test_calls=0;test_reads=0;test_bad_raw=0;test_short_write=0;test_log_size=0;test_raw=10000000;real_clock=test_clock;
}
static void endpoint(h_uptr rva,void *object,void *stack,h_i64 carried,h_i64 value) {
 unsigned before=test_calls;test_native=value;
 assert(hgn_phase_now(rva,(h_uptr)stack,(h_uptr)object,(h_uptr)carried,0)==value);assert(test_calls==before+1);
}
int main(void) {
 h_u64 pf[104]={0},req[104]={0},moved[104]={0},stack[16]={0};double pms=1.0;
 reset_test();pf[0]=(h_u64)-17;req[0]=(h_u64)-17;
 endpoint(0x181870f,pf,stack,0,1000000);*(h_i64 *)((h_u8 *)stack+0x18)=1000000;
 endpoint(0x1818d60,pf,stack,0,2000000);
 memcpy((h_u8 *)req+0x1c0,&pms,8);*(unsigned *)((h_u8 *)req+0x54)=37;*(unsigned *)((h_u8 *)req+0x58)=1;
 endpoint(0x181a8dc,req,stack,0,3000000);*(h_i64 *)((h_u8 *)req+0x1c8)=3000000;
 memcpy(moved,req,0x338);*(unsigned *)((h_u8 *)moved+0x58)=9;endpoint(0x181e7c2,moved,stack,3000000,5000000);
 assert(test_calls==4&&owners[0].stage==3&&!owners[0].bad);
 assert(strstr(test_log,"\"kind\":\"phase\"")&&strstr(test_log,"\"native_return_ns\":5000000,\"returned_ns\":5000000"));
 endpoint(0x181870f,pf,stack,0,6000000);assert(owners[0].bad&&strstr(test_log,"\"status\":9"));
 reset_test();active=0;endpoint(0x181870f,pf,stack,0,7000000);assert(!test_reads&&!test_log_size);
 reset_test();endpoint(0x12345,pf,stack,0,8000000);assert(!test_reads&&!test_log_size);
 reset_test();test_bad_raw=1;endpoint(0x181870f,pf,stack,0,9000000);assert(strstr(test_log,"\"status\":1"));
 reset_test();test_short_write=1;endpoint(0x181870f,pf,stack,0,10000000);assert(!active&&!prepared&&dropped);
 printf("C producer fixtures passed: originalRAX,oneRealCall,movedRequest,IDreuse,defaultOff,unrelated,RAWfailure,shortWrite\n");return 0;
}
