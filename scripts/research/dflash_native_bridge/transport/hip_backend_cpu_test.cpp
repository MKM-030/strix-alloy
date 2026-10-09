#define main lifetime_fixture_main
#include "transport_cpu_test.cpp"
#undef main
static std::array<std::uint8_t,4*kConcatRowBytes> pinned;
static unsigned calls,freed,destroyed,copies;
static bool done,fail_sync,fail_event_create;
static int stream_token,event_token;
static int alloc(void** p,std::size_t n,unsigned flags){++calls;if(n!=pinned.size()||flags)return 1;*p=pinned.data();return 0;}
static int free_host(void* p){++calls;if(p!=pinned.data())return 1;++freed;return 0;}
static int stream_create(void** p,unsigned flags){++calls;if(flags!=1)return 1;*p=&stream_token;return 0;}
static int event_create(void** p,unsigned flags){++calls;if(fail_event_create)return 1;if(flags!=2)return 1;*p=&event_token;return 0;}
static int destroy_stream(void* p){++calls;if(p!=&stream_token)return 1;++destroyed;return 0;}
static int destroy_event(void* p){++calls;if(p!=&event_token)return 1;++destroyed;return 0;}
static int sync(void* p){++calls;return p!=&stream_token||fail_sync?1:0;}
static int copy(void* d,std::size_t dp,const void* s,std::size_t sp,std::size_t bytes,std::size_t rows,int kind,void* stream){
    ++calls;if(d!=pinned.data()||!s||dp!=kConcatRowBytes||sp!=kConcatRowBytes||bytes!=kConcatRowBytes||rows>4||kind!=2||stream!=&stream_token)return 1;++copies;return 0;
}
static int record(void* e,void* s){++calls;return e==&event_token&&s==&stream_token?0:1;}
static int query(void* e){++calls;if(e!=&event_token)return 1;return done?0:600;}
static Exporter off,foreign;
static HipD2H hip,partial;
int main(){
    HipFunctions functions{alloc,free_host,stream_create,destroy_stream,sync,event_create,destroy_event,copy,record,query};
    if(!hip.configure(false,functions,0,600,4)||calls)return 1;
    if(hip.configure(true,functions,0,600,2,&off)||calls)return 2;
    if(hip.configure(true,functions,0,600,4)||calls)return 3;
    if(!hip.configure(true,functions,0,600,4,&off)||calls!=3)return 4;
    auto chunk=hip.host_chunk();if(!chunk.pinned||chunk.bytes!=pinned.size()||chunk.rows!=4)return 5;
    auto ops=hip.operations();
    if(hip.close(foreign)||!ops.enqueue(ops.context,pinned.data(),f[0].staging.data(),4)||!ops.record(ops.context)||copies!=1)return 6;
    if(hip.close(off)||ops.query(ops.context)!=Poll::Pending||freed)return 7;
    done=true;if(ops.query(ops.context)!=Poll::Complete||!hip.close(off)||freed!=1||destroyed!=2)return 8;
    fail_event_create=true;if(partial.configure(true,functions,0,600,4,&off)||freed!=2||destroyed!=3)return 9;
    fail_event_create=false;if(!partial.configure(true,functions,0,600,4,&off))return 10;
    ops=partial.operations();if(!ops.enqueue(ops.context,pinned.data(),f[0].staging.data(),1))return 11;
    fail_sync=true;if(ops.drain(ops.context)||partial.close(off))return 12;
    fail_sync=false;if(!ops.drain(ops.context)||!partial.close(off)||freed!=3)return 13;
    return 0;
}
