/* CPU fixtures only; Root compiles/runs. No engine or hardware is involved. */
#include "stream_consumer.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static unsigned char packets[64][124];static size_t lengths[64];static unsigned qin,qout;
static uint64_t storage[256],request_bytes[32],spec_bytes[96];
static struct hgn0203_stream_snapshot *saved;
static unsigned char *frame;
static void put32(unsigned char *p,uint32_t x){for(unsigned i=0;i<4;++i)p[i]=(unsigned char)(x>>(8*i));}
static void put64(unsigned char *p,uint64_t x){for(unsigned i=0;i<8;++i)p[i]=(unsigned char)(x>>(8*i));}
long hgn0203_stream_test_recv(int fd,uint8_t *out,size_t capacity) {
    (void)fd;if(qout==qin)return -11;size_t n=lengths[qout];
    memcpy(out,packets[qout],n<capacity?n:capacity);++qout;return (long)n;
}
static void queue_packet(unsigned kind,uint64_t g,uint64_t sequence,int32_t current,
                         unsigned sha_tag,const int32_t *ids,unsigned count) {
    assert(qin<64);unsigned char *p=packets[qin];memset(p,0,124);memcpy(p,"HDO2",4);
    p[4]=2;p[6]=112;put32(p+8,112+4*count);put32(p+12,kind);put64(p+16,41);
    put32(p+24,8192);memset(p+32,17,16);put64(p+48,9);put64(p+56,g);
    memset(p+64,(int)sha_tag,32);put64(p+96,sequence);put32(p+104,(uint32_t)current);
    put32(p+108,count);for(unsigned i=0;i<count;++i)put32(p+112+4*i,(uint32_t)ids[i]);
    lengths[qin++]=112+4*count;
}
static void native_prefix(int32_t g,int32_t current) {
    put32((unsigned char *)request_bytes+0x60,(uint32_t)g);
    put32((unsigned char *)spec_bytes+0x244,(uint32_t)current);
}
static void setup(void) {
    memset(storage,0,sizeof(storage));memset(request_bytes,0,sizeof(request_bytes));
    memset(spec_bytes,0,sizeof(spec_bytes));qin=qout=0;
    saved=(struct hgn0203_stream_snapshot *)storage;frame=(unsigned char *)storage+256;
    saved->r13=(uintptr_t)spec_bytes;saved->rsi=3;
    uintptr_t request=(uintptr_t)request_bytes,spec=(uintptr_t)spec_bytes;
    memcpy(frame+0x178,&request,sizeof(request));
    memcpy((unsigned char *)request_bytes+0x10,&spec,sizeof(spec));
    put64((unsigned char *)request_bytes,41);put32((unsigned char *)request_bytes+0x5c,8192);
    native_prefix(1,100);assert(hgn0203_stream_configure(7,1,1,2));
}
static void begin_and_authority(void) {
    int32_t current=100;queue_packet(HDO2_BEGIN,0,1,-1,0,NULL,0);
    queue_packet(HDO2_AUTHORITY,1,2,100,1,&current,1);
}
static void test_exact_and_once(void) {
    setup();begin_and_authority();int32_t ids[3]={101,102,103};
    queue_packet(HDO2_READY,1,1,100,1,ids,3);
    assert(hgn0203_stream_consume_snapshot(saved)==3);
    assert(memcmp(frame+0x2a0,ids,sizeof(ids))==0);
    assert(*(int64_t *)(frame+0x480)==-1&&frame[0x220]==0&&frame[0xa0]==0);
    queue_packet(HDO2_READY,1,2,100,1,ids,3);
    assert(hgn0203_stream_consume_snapshot(saved)==-1);
    struct hgn0203_stream_stats stats;assert(hgn0203_stream_get_stats(&stats));
    assert(stats.hits==1&&stats.proposed_ids==3&&stats.already_consumed==1);
}
static void test_precomputed_future_survives_until_authority(void) {
    setup();begin_and_authority();int32_t next[2]={102,103};
    queue_packet(HDO2_READY,2,1,101,2,next,2);
    assert(hgn0203_stream_consume_snapshot(saved)==-1);
    native_prefix(2,101);int32_t current=101;
    queue_packet(HDO2_AUTHORITY,2,3,101,2,&current,1);
    assert(hgn0203_stream_consume_snapshot(saved)==2);
    assert(memcmp(frame+0x2a0,next,sizeof(next))==0);
}
static void test_future_hash_mismatch_never_arms(void) {
    setup();begin_and_authority();int32_t next=102;
    queue_packet(HDO2_READY,2,1,101,99,&next,1);
    assert(hgn0203_stream_consume_snapshot(saved)==-1);
    native_prefix(2,101);int32_t current=101;
    queue_packet(HDO2_AUTHORITY,2,3,101,2,&current,1);
    assert(hgn0203_stream_consume_snapshot(saved)==-1);
}
static void test_no_self_arm_no_g0_no_current_mismatch(void) {
    setup();int32_t next=101;queue_packet(HDO2_READY,1,1,100,1,&next,1);
    assert(hgn0203_stream_consume_snapshot(saved)==-1);
    setup();native_prefix(0,-1);queue_packet(HDO2_BEGIN,0,1,-1,0,NULL,0);
    queue_packet(HDO2_READY,0,1,-1,0,&next,1);
    assert(hgn0203_stream_consume_snapshot(saved)==-1);
    setup();begin_and_authority();native_prefix(1,777);
    queue_packet(HDO2_READY,1,1,100,1,&next,1);
    assert(hgn0203_stream_consume_snapshot(saved)==-1);
}
static void test_gap_cancel_and_reuse_retire(void) {
    setup();begin_and_authority();int32_t next=101;
    queue_packet(HDO2_AUTHORITY,2,4,101,2,&next,1);native_prefix(2,101);
    queue_packet(HDO2_READY,2,1,101,2,&next,1);
    assert(hgn0203_stream_consume_snapshot(saved)==-1);
    setup();begin_and_authority();queue_packet(HDO2_CANCEL,1,3,100,1,NULL,0);
    queue_packet(HDO2_READY,1,1,100,1,&next,1);
    assert(hgn0203_stream_consume_snapshot(saved)==-1);
    queue_packet(HDO2_BEGIN,0,1,-1,0,NULL,0); /* retired request cannot rearm */
    int32_t actual=100;queue_packet(HDO2_AUTHORITY,1,2,100,1,&actual,1);
    assert(hgn0203_stream_consume_snapshot(saved)==-1);
}
int main(void) {
    test_exact_and_once();test_precomputed_future_survives_until_authority();
    test_future_hash_mismatch_never_arms();test_no_self_arm_no_g0_no_current_mismatch();
    test_gap_cancel_and_reuse_retire();puts("HDO2 stream consumer CPU fixtures passed");return 0;
}
