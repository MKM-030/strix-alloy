// CPU-only ABI-shaped forwarding tests; no HIP runtime or GPU is loaded.
#include "launch_redirect_linux.cpp"
#include <cassert>
#include <cstdio>
#include <cstring>
namespace {
void* ptr(unsigned n){return reinterpret_cast<void*>(static_cast<std::uintptr_t>(n));}
void* expected_stream{};
int calls{},result_code{};
void hit(void* stream){assert(stream==expected_stream);++calls;}
int kernel(const void* f,DzDim3 g,DzDim3 b,void** a,std::size_t s,void* stream){
    assert(f==ptr(2)&&g.x==3&&g.y==4&&g.z==5&&b.x==6&&b.y==7&&b.z==8&&a==reinterpret_cast<void**>(ptr(9))&&s==10);hit(stream);return result_code;}
int module(void* f,unsigned gx,unsigned gy,unsigned gz,unsigned bx,unsigned by,unsigned bz,unsigned s,void* stream,void** a,void** e){
    assert(f==ptr(2)&&gx==3&&gy==4&&gz==5&&bx==6&&by==7&&bz==8&&s==10&&a==reinterpret_cast<void**>(ptr(9))&&e==reinterpret_cast<void**>(ptr(11)));hit(stream);return result_code;}
int ext(void* f,unsigned gx,unsigned gy,unsigned gz,unsigned bx,unsigned by,unsigned bz,std::size_t s,void* stream,void** a,void** e,void* start,void* stop,unsigned flags){
    assert(start==ptr(12)&&stop==ptr(13)&&flags==14);return module(f,gx,gy,gz,bx,by,bz,static_cast<unsigned>(s),stream,a,e);}
int matmul(void* h,void* d,const void* alpha,const void* a,void* ad,const void* b,void* bd,const void* beta,const void* c,void* cd,void* out,void* dd,const void* algo,void* ws,std::size_t n,void* stream){
    assert(h==ptr(1)&&d==ptr(2)&&alpha==ptr(3)&&a==ptr(4)&&ad==ptr(5)&&b==ptr(6)&&bd==ptr(7)&&beta==ptr(8)&&c==ptr(9)&&cd==ptr(10)&&out==ptr(11)&&dd==ptr(12)&&algo==ptr(13)&&ws==ptr(14)&&n==15);hit(stream);return result_code;}
int copy(void* d,const void* s,std::size_t n,int k,void* stream){assert(d==ptr(2)&&s==ptr(3)&&n==4&&k==5);hit(stream);return result_code;}
int fill(void* d,int v,std::size_t n,void* stream){assert(d==ptr(2)&&v==3&&n==4);hit(stream);return result_code;}
int sync(void* stream){hit(stream);return result_code;}
int alloc(void**,std::size_t){++calls;return result_code;}
int alloc_async(void**,std::size_t,void*){++calls;return result_code;}
int alloc_pool(void**,std::size_t,void*,void*){++calls;return result_code;}
int release(void*){++calls;return result_code;}
int release_async(void*,void*){++calls;return result_code;}
int host_alloc(void**,std::size_t,unsigned){++calls;return result_code;}
int sync_copy(void*,const void*,std::size_t,int){++calls;return result_code;}
int sync_fill(void*,int,std::size_t){++calls;return result_code;}
int host_func(void*,void (*)(void*),void*){++calls;return result_code;}
int callback(void*,void (*)(void*,int,void*),void*,unsigned){++calls;return result_code;}
int device_sync(){++calls;return result_code;}
int event_record(void* event,void* stream){assert(event==ptr(2));hit(stream);return result_code;}
int event_single(void* event){assert(event==ptr(2));++calls;return result_code;}
int event_create(void** event){assert(event);++calls;return result_code;}
int event_flags(void** event,unsigned flags){assert(event&&flags==17);++calls;return result_code;}
int elapsed(float* ms,void* start,void* stop){assert(ms&&start==ptr(2)&&stop==ptr(3));++calls;return result_code;}
int observed{};bool accept=true;
bool observe(void*,const deferred_z::Submit& s){
    assert(s.caller);
    if(s.kind==deferred_z::SubmitKind::matmul){
        assert(s.matmul_handle==ptr(1)&&s.matmul_alpha==ptr(3)&&s.matmul_beta==ptr(8)&&s.matmul_algorithm==ptr(13));
        assert(s.matmul_operands[0]==ptr(4)&&s.matmul_operands[1]==ptr(6)&&s.matmul_operands[2]==ptr(9)&&s.matmul_operands[3]==ptr(11));
        assert(s.matmul_layouts[0]==ptr(5)&&s.matmul_layouts[1]==ptr(7)&&s.matmul_layouts[2]==ptr(10)&&s.matmul_layouts[3]==ptr(12));
    }
    ++observed;return accept;
}
void submissions(void* stream){
    void** args=reinterpret_cast<void**>(ptr(9));void** extra=reinterpret_cast<void**>(ptr(11));
    assert(hipLaunchKernel(ptr(2),{3,4,5},{6,7,8},args,10,stream)==result_code);
    assert(hipModuleLaunchKernel(ptr(2),3,4,5,6,7,8,10,stream,args,extra)==result_code);
    assert(hipExtModuleLaunchKernel(ptr(2),3,4,5,6,7,8,10,stream,args,extra,ptr(12),ptr(13),14)==result_code);
    assert(hipblasLtMatmul(ptr(1),ptr(2),ptr(3),ptr(4),ptr(5),ptr(6),ptr(7),ptr(8),ptr(9),ptr(10),ptr(11),ptr(12),ptr(13),ptr(14),15,stream)==result_code);
    assert(hipMemcpyAsync(ptr(2),ptr(3),4,5,stream)==result_code);
    assert(hipMemsetAsync(ptr(2),3,4,stream)==result_code);
    assert(hipStreamSynchronize(stream)==result_code);
}
}
extern "C" void* dlsym(void* handle,const char* name){
    assert(handle==RTLD_NEXT);
#define MAP(n,f) if(!std::strcmp(name,n))return reinterpret_cast<void*>(&f)
    MAP("hipLaunchKernel",kernel);MAP("hipModuleLaunchKernel",module);MAP("hipExtModuleLaunchKernel",ext);
    MAP("hipblasLtMatmul",matmul);MAP("hipMemcpyAsync",copy);MAP("hipMemsetAsync",fill);MAP("hipStreamSynchronize",sync);
    MAP("hipMalloc",alloc);MAP("hipFree",release);MAP("hipFreeAsync",release_async);MAP("hipHostMalloc",host_alloc);
    MAP("hipMallocAsync",alloc_async);MAP("hipMallocFromPoolAsync",alloc_pool);
    MAP("hipHostFree",release);MAP("hipFreeHost",release);MAP("hipMemcpy",sync_copy);MAP("hipMemset",sync_fill);
    MAP("hipLaunchHostFunc",host_func);MAP("hipStreamAddCallback",callback);
    MAP("hipDeviceSynchronize",device_sync);MAP("hipEventRecord",event_record);MAP("hipEventSynchronize",event_single);
    MAP("hipEventCreate",event_create);MAP("hipEventCreateWithFlags",event_flags);MAP("hipEventDestroy",event_single);MAP("hipEventElapsedTime",elapsed);
#undef MAP
    return nullptr;
}
int main(){
    expected_stream=ptr(44);submissions(expected_stream);assert(calls==7&&observed==0);
    deferred_z::Observation o{observe,nullptr,false};
    {deferred_z::ObserverScope obs(o);deferred_z::Redirect r{nullptr,ptr(55),false,0};
     deferred_z::RedirectScope scope(r);expected_stream=r.side;submissions(nullptr);submissions(r.side);
     assert(calls==21&&observed==14&&r.redirected==14&&!r.failed);
     const int before=calls;assert(hipMemcpyAsync(ptr(2),ptr(3),4,5,ptr(99))!=0);assert(r.failed&&calls==before);}
    {deferred_z::ObserverScope obs(o);accept=false;const int before=calls;
     assert(hipMemcpyAsync(ptr(2),ptr(3),4,5,nullptr)!=0);assert(calls==before);accept=true;}
    {deferred_z::Redirect r{nullptr,ptr(55),false,0};deferred_z::RedirectScope scope(r);
     result_code=91;expected_stream=r.side;assert(hipMemsetAsync(ptr(2),3,4,nullptr)==91);assert(r.failed);result_code=0;}
    {deferred_z::Redirect r{nullptr,ptr(55),false,0};deferred_z::RedirectScope scope(r);int before=calls;void* p{};
     assert(hipMalloc(&p,1)==801);assert(hipFree(ptr(1))==801);assert(hipFreeAsync(ptr(1),nullptr)==801);
     assert(hipMallocAsync(&p,1,nullptr)==801);assert(hipMallocFromPoolAsync(&p,1,ptr(1),nullptr)==801);
     assert(hipHostMalloc(&p,1,0)==801);assert(hipHostFree(ptr(1))==801);assert(hipFreeHost(ptr(1))==801);
     assert(hipMemcpy(ptr(1),ptr(2),3,4)==801);assert(hipMemset(ptr(1),2,3)==801);
     assert(hipLaunchHostFunc(nullptr,nullptr,nullptr)==801);assert(hipStreamAddCallback(nullptr,nullptr,nullptr,0)==801);
     assert(calls==before&&r.failed);}
    assert(!deferred_z::active_redirect&&!deferred_z::active_observation);
    void* event{};float milliseconds{};int before=calls;expected_stream=ptr(44);
    assert(hipDeviceSynchronize()==0);assert(hipEventRecord(ptr(2),expected_stream)==0);
    assert(hipEventSynchronize(ptr(2))==0);assert(hipEventCreate(&event)==0);
    assert(hipEventCreateWithFlags(&event,17)==0);assert(hipEventDestroy(ptr(2))==0);
    assert(hipEventElapsedTime(&milliseconds,ptr(2),ptr(3))==0);assert(calls==before+7);
    {deferred_z::ObserverScope obs(o);int seen=observed;
     assert(hipEventRecord(ptr(2),expected_stream)==0);assert(observed==seen+1);
     accept=false;before=calls;assert(hipDeviceSynchronize()==801);assert(calls==before);accept=true;}
    {deferred_z::Redirect r{nullptr,ptr(55),false,0};deferred_z::RedirectScope scope(r);before=calls;
     assert(hipDeviceSynchronize()==801);assert(hipEventRecord(ptr(2),nullptr)==801);
     assert(hipEventSynchronize(ptr(2))==801);assert(hipEventCreate(&event)==801);
     assert(hipEventCreateWithFlags(&event,17)==801);assert(hipEventDestroy(ptr(2))==801);
     assert(hipEventElapsedTime(&milliseconds,ptr(2),ptr(3))==801);assert(calls==before&&r.failed);}
    std::puts("PASS: seven wrappers preserve arguments, scoped main/side redirect and observation, foreign/rejected/error paths, twelve temporary/callback paths and seven event/device paths blocked before native call");
}
