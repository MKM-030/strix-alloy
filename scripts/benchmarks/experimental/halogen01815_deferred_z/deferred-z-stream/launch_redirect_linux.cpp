// Unattached ELF interposers: no constructor, dlopen, device call or hook patch.
// Include in the SAME DSO as the context (TLS must not be duplicated across DSOs).
// Runtime call coverage and version-specific resolution remain unqualified.
#include "deferred_z_stream.h"
#include <dlfcn.h>
#include <cstdlib>
#ifdef _MSC_VER
#include <intrin.h>
#define DZ_CALLER_ADDRESS() _ReturnAddress()
#else
#define DZ_CALLER_ADDRESS() __builtin_return_address(0)
#endif

namespace {
template<class T> T next(const char* name) {
    auto p=reinterpret_cast<T>(dlsym(RTLD_NEXT,name));
    if (!p) std::abort(); // never forge successful submission
    return p;
}
bool prepare(deferred_z::Submit view,void*& stream) {
    if (!deferred_z::observe_submit(view)) return false;
    return deferred_z::redirect_stream(view.stream,stream);
}
bool reject_temporary_path() {
    if (!deferred_z::active_redirect) return false;
    deferred_z::launch_error(801);
    return true;
}
bool observe_plain(deferred_z::SubmitKind kind,void* destination=nullptr,
    const void* source=nullptr,std::size_t bytes=0,void* stream=nullptr) {
    deferred_z::Submit view{};view.kind=kind;view.destination=destination;
    view.source=source;view.bytes=bytes;view.stream=stream;
    return deferred_z::observe_submit(view);
}
}

struct DzDim3 { unsigned x,y,z; };
static_assert(sizeof(DzDim3)==12,"pinned HIP dim3 layout");
extern "C" int hipLaunchKernel(const void* function,DzDim3 grid,DzDim3 block,
    void** args,std::size_t shared,void* requested) {
    using Fn=int (*)(const void*,DzDim3,DzDim3,void**,std::size_t,void*);
    static Fn original=next<Fn>("hipLaunchKernel");
    void* stream=nullptr;
    deferred_z::Submit view{};view.kind=deferred_z::SubmitKind::kernel;view.function=function;
    view.stream=requested;view.args=args;view.shared=shared;view.caller=DZ_CALLER_ADDRESS();
    view.grid[0]=grid.x;view.grid[1]=grid.y;view.grid[2]=grid.z;
    view.block[0]=block.x;view.block[1]=block.y;view.block[2]=block.z;
    if (!prepare(view,stream)) return 1;
    const int result=original(function,grid,block,args,shared,stream);
    deferred_z::launch_error(result);
    return result;
}

extern "C" int hipModuleLaunchKernel(void* f,unsigned gx,unsigned gy,unsigned gz,
    unsigned bx,unsigned by,unsigned bz,unsigned shared,void* requested,void** args,void** extra) {
    using Fn=int (*)(void*,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,void*,void**,void**);
    static Fn original=next<Fn>("hipModuleLaunchKernel");
    void* stream=nullptr;
    deferred_z::Submit view{};view.kind=deferred_z::SubmitKind::module;view.function=f;
    view.stream=requested;view.args=args;view.extra=extra;view.shared=shared;view.caller=DZ_CALLER_ADDRESS();
    view.grid[0]=gx;view.grid[1]=gy;view.grid[2]=gz;view.block[0]=bx;view.block[1]=by;view.block[2]=bz;
    if (!prepare(view,stream)) return 1;
    const int result=original(f,gx,gy,gz,bx,by,bz,shared,stream,args,extra);
    deferred_z::launch_error(result);
    return result;
}

extern "C" int hipblasLtMatmul(void* handle,void* desc,const void* alpha,
    const void* a,void* ad,const void* b,void* bd,const void* beta,
    const void* c,void* cd,void* d,void* dd,const void* algo,
    void* workspace,std::size_t workspace_bytes,void* requested) {
    using Fn=int (*)(void*,void*,const void*,const void*,void*,const void*,void*,const void*,
        const void*,void*,void*,void*,const void*,void*,std::size_t,void*);
    static Fn original=next<Fn>("hipblasLtMatmul");
    void* stream=nullptr;
    deferred_z::Submit view{};view.kind=deferred_z::SubmitKind::matmul;view.function=desc;
    view.stream=requested;view.source=a;view.destination=d;view.bytes=workspace_bytes;
    view.workspace=workspace;view.workspace_bytes=workspace_bytes;view.caller=DZ_CALLER_ADDRESS();
    view.matmul_handle=handle;
    view.matmul_operands[0]=a;view.matmul_operands[1]=b;view.matmul_operands[2]=c;view.matmul_operands[3]=d;
    view.matmul_layouts[0]=ad;view.matmul_layouts[1]=bd;view.matmul_layouts[2]=cd;view.matmul_layouts[3]=dd;
    view.matmul_alpha=alpha;view.matmul_beta=beta;view.matmul_algorithm=algo;
    if (!prepare(view,stream)) return 1;
    const int result=original(handle,desc,alpha,a,ad,b,bd,beta,c,cd,d,dd,algo,
        workspace,workspace_bytes,stream);
    deferred_z::launch_error(result);
    return result;
}

extern "C" int hipExtModuleLaunchKernel(void* f,unsigned gx,unsigned gy,unsigned gz,
    unsigned bx,unsigned by,unsigned bz,std::size_t shared,void* requested,
    void** args,void** extra,void* start,void* stop,unsigned flags) {
    using Fn=int (*)(void*,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,std::size_t,
        void*,void**,void**,void*,void*,unsigned);
    static Fn original=next<Fn>("hipExtModuleLaunchKernel");void* stream=nullptr;
    deferred_z::Submit view{};view.kind=deferred_z::SubmitKind::ext_module;view.function=f;
    view.stream=requested;view.args=args;view.extra=extra;view.shared=shared;view.caller=DZ_CALLER_ADDRESS();
    view.flags=flags;view.start_event=start;view.stop_event=stop;
    view.grid[0]=gx;view.grid[1]=gy;view.grid[2]=gz;view.block[0]=bx;view.block[1]=by;view.block[2]=bz;
    if(!prepare(view,stream))return 1;
    int r=original(f,gx,gy,gz,bx,by,bz,shared,stream,args,extra,start,stop,flags);
    deferred_z::launch_error(r);
    return r;
}
extern "C" int hipMemcpyAsync(void* dst,const void* src,std::size_t bytes,int kind,void* requested) {
    using Fn=int (*)(void*,const void*,std::size_t,int,void*);
    static Fn original=next<Fn>("hipMemcpyAsync");void* stream=nullptr;
    deferred_z::Submit view{};view.kind=deferred_z::SubmitKind::copy;view.stream=requested;
    view.source=src;view.destination=dst;view.bytes=bytes;view.caller=DZ_CALLER_ADDRESS();
    view.operation_value=kind;
    if(!prepare(view,stream))return 1;
    int r=original(dst,src,bytes,kind,stream);deferred_z::launch_error(r);
    return r;
}
extern "C" int hipMemsetAsync(void* dst,int value,std::size_t bytes,void* requested) {
    using Fn=int (*)(void*,int,std::size_t,void*);
    static Fn original=next<Fn>("hipMemsetAsync");void* stream=nullptr;
    deferred_z::Submit view{};view.kind=deferred_z::SubmitKind::memset;view.stream=requested;
    view.destination=dst;view.bytes=bytes;view.caller=DZ_CALLER_ADDRESS();
    view.operation_value=value;
    if(!prepare(view,stream))return 1;
    int r=original(dst,value,bytes,stream);deferred_z::launch_error(r);
    return r;
}
extern "C" int hipStreamSynchronize(void* requested) {
    using Fn=int (*)(void*);static Fn original=next<Fn>("hipStreamSynchronize");void* stream=nullptr;
    deferred_z::Submit view{};view.kind=deferred_z::SubmitKind::synchronize;view.stream=requested;view.caller=DZ_CALLER_ADDRESS();
    if(!prepare(view,stream))return 1;
    int r=original(stream);deferred_z::launch_error(r);
    return r;
}

// Native timing/tuning operations are outside the qualified warmed closure.
// Adapter-owned events and drains use direct RTLD_NEXT Api pointers, bypassing
// these wrappers. Never let native Z record an event on the wrong stream.
extern "C" int hipDeviceSynchronize() {
    using Fn=int (*)();
    static Fn original=next<Fn>("hipDeviceSynchronize");
    deferred_z::Submit view{};
    view.kind=deferred_z::SubmitKind::synchronize;
    view.function=reinterpret_cast<const void*>(original);
    view.caller=DZ_CALLER_ADDRESS();
    if (reject_temporary_path() || !deferred_z::observe_submit(view)) {
        return 801;
    }
    return original();
}
extern "C" int hipEventRecord(void* event,void* stream) {
    using Fn=int (*)(void*,void*);
    static Fn original=next<Fn>("hipEventRecord");
    deferred_z::Submit view{};
    view.kind=deferred_z::SubmitKind::synchronize;
    view.function=reinterpret_cast<const void*>(original);
    view.stream=stream;
    view.start_event=event;
    view.caller=DZ_CALLER_ADDRESS();
    if (reject_temporary_path() || !deferred_z::observe_submit(view)) {
        return 801;
    }
    return original(event,stream);
}
extern "C" int hipEventSynchronize(void* event) {
    using Fn=int (*)(void*);
    static Fn original=next<Fn>("hipEventSynchronize");
    deferred_z::Submit view{};
    view.kind=deferred_z::SubmitKind::synchronize;
    view.function=reinterpret_cast<const void*>(original);
    view.start_event=event;
    view.caller=DZ_CALLER_ADDRESS();
    if (reject_temporary_path() || !deferred_z::observe_submit(view)) {
        return 801;
    }
    return original(event);
}
extern "C" int hipEventCreate(void** event) {
    using Fn=int (*)(void**);
    static Fn original=next<Fn>("hipEventCreate");
    deferred_z::Submit view{};
    view.kind=deferred_z::SubmitKind::synchronize;
    view.function=reinterpret_cast<const void*>(original);
    view.destination=event;
    view.caller=DZ_CALLER_ADDRESS();
    if (reject_temporary_path() || !deferred_z::observe_submit(view)) {
        return 801;
    }
    return original(event);
}
extern "C" int hipEventCreateWithFlags(void** event,unsigned flags) {
    using Fn=int (*)(void**,unsigned);
    static Fn original=next<Fn>("hipEventCreateWithFlags");
    deferred_z::Submit view{};
    view.kind=deferred_z::SubmitKind::synchronize;
    view.function=reinterpret_cast<const void*>(original);
    view.destination=event;
    view.flags=flags;
    view.caller=DZ_CALLER_ADDRESS();
    if (reject_temporary_path() || !deferred_z::observe_submit(view)) {
        return 801;
    }
    return original(event,flags);
}
extern "C" int hipEventDestroy(void* event) {
    using Fn=int (*)(void*);
    static Fn original=next<Fn>("hipEventDestroy");
    deferred_z::Submit view{};
    view.kind=deferred_z::SubmitKind::synchronize;
    view.function=reinterpret_cast<const void*>(original);
    view.start_event=event;
    view.caller=DZ_CALLER_ADDRESS();
    if (reject_temporary_path() || !deferred_z::observe_submit(view)) {
        return 801;
    }
    return original(event);
}
extern "C" int hipEventElapsedTime(float* milliseconds,void* start,void* stop) {
    using Fn=int (*)(float*,void*,void*);
    static Fn original=next<Fn>("hipEventElapsedTime");
    deferred_z::Submit view{};
    view.kind=deferred_z::SubmitKind::synchronize;
    view.function=reinterpret_cast<const void*>(original);
    view.destination=milliseconds;
    view.start_event=start;
    view.stop_event=stop;
    view.caller=DZ_CALLER_ADDRESS();
    if (reject_temporary_path() || !deferred_z::observe_submit(view)) {
        return 801;
    }
    return original(milliseconds,start,stop);
}

// Warmed HT closure must contain no temporary allocation/free or synchronous
// copy. Fail BEFORE such a native operation; never free a buffer still queued
// on side or silently return success. Native callback creation is likewise
// unsupported because a callback can outlive the caller's TLS redirect scope.
extern "C" int hipMalloc(void** p,std::size_t n) {
    using Fn=int (*)(void**,std::size_t);static Fn original=next<Fn>("hipMalloc");
    if (reject_temporary_path() || !observe_plain(deferred_z::SubmitKind::allocate,p,nullptr,n)) {
        return 801;
    }
    return original(p,n);
}
extern "C" int hipMallocAsync(void** p,std::size_t n,void* stream) {
    using Fn=int (*)(void**,std::size_t,void*);static Fn original=next<Fn>("hipMallocAsync");
    if (reject_temporary_path() || !observe_plain(deferred_z::SubmitKind::allocate,p,nullptr,n,stream)) {
        return 801;
    }
    return original(p,n,stream);
}
extern "C" int hipMallocFromPoolAsync(void** p,std::size_t n,void* pool,void* stream) {
    using Fn=int (*)(void**,std::size_t,void*,void*);static Fn original=next<Fn>("hipMallocFromPoolAsync");
    if (reject_temporary_path() || !observe_plain(deferred_z::SubmitKind::allocate,p,nullptr,n,stream)) {
        return 801;
    }
    return original(p,n,pool,stream);
}
extern "C" int hipFree(void* p) {
    using Fn=int (*)(void*);static Fn original=next<Fn>("hipFree");
    if (reject_temporary_path() || !observe_plain(deferred_z::SubmitKind::release,p)) {
        return 801;
    }
    return original(p);
}
extern "C" int hipFreeAsync(void* p,void* stream) {
    using Fn=int (*)(void*,void*);static Fn original=next<Fn>("hipFreeAsync");
    if (reject_temporary_path() || !observe_plain(deferred_z::SubmitKind::release,p,nullptr,0,stream)) {
        return 801;
    }
    return original(p,stream);
}
extern "C" int hipHostMalloc(void** p,std::size_t n,unsigned flags) {
    using Fn=int (*)(void**,std::size_t,unsigned);static Fn original=next<Fn>("hipHostMalloc");
    if (reject_temporary_path() || !observe_plain(deferred_z::SubmitKind::allocate,p,nullptr,n)) {
        return 801;
    }
    return original(p,n,flags);
}
extern "C" int hipHostFree(void* p) {
    using Fn=int (*)(void*);static Fn original=next<Fn>("hipHostFree");
    if (reject_temporary_path() || !observe_plain(deferred_z::SubmitKind::release,p)) {
        return 801;
    }
    return original(p);
}
extern "C" int hipFreeHost(void* p) {
    using Fn=int (*)(void*);static Fn original=next<Fn>("hipFreeHost");
    if (reject_temporary_path() || !observe_plain(deferred_z::SubmitKind::release,p)) {
        return 801;
    }
    return original(p);
}
extern "C" int hipMemcpy(void* dst,const void* src,std::size_t n,int kind) {
    using Fn=int (*)(void*,const void*,std::size_t,int);static Fn original=next<Fn>("hipMemcpy");
    if (reject_temporary_path() || !observe_plain(deferred_z::SubmitKind::synchronous_copy,dst,src,n)) {
        return 801;
    }
    return original(dst,src,n,kind);
}
extern "C" int hipMemset(void* dst,int value,std::size_t n) {
    using Fn=int (*)(void*,int,std::size_t);static Fn original=next<Fn>("hipMemset");
    if (reject_temporary_path() || !observe_plain(deferred_z::SubmitKind::synchronous_copy,dst,nullptr,n)) {
        return 801;
    }
    return original(dst,value,n);
}
extern "C" int hipLaunchHostFunc(void* stream,void (*fn)(void*),void* data) {
    using Fn=int (*)(void*,void (*)(void*),void*);static Fn original=next<Fn>("hipLaunchHostFunc");
    if (reject_temporary_path() || !observe_plain(deferred_z::SubmitKind::host_callback,data,nullptr,0,stream)) {
        return 801;
    }
    return original(stream,fn,data);
}
extern "C" int hipStreamAddCallback(void* stream,void (*fn)(void*,int,void*),void* data,unsigned flags) {
    using Fn=int (*)(void*,void (*)(void*,int,void*),void*,unsigned);static Fn original=next<Fn>("hipStreamAddCallback");
    if (reject_temporary_path() || !observe_plain(deferred_z::SubmitKind::host_callback,data,nullptr,0,stream)) {
        return 801;
    }
    return original(stream,fn,data,flags);
}

extern "C" bool deferred_z_bind_hip(deferred_z::Api* api) {
    if(!api)return false;
    api->stream_create=reinterpret_cast<decltype(api->stream_create)>(dlsym(RTLD_NEXT,"hipStreamCreateWithFlags"));
    api->stream_destroy=reinterpret_cast<decltype(api->stream_destroy)>(dlsym(RTLD_NEXT,"hipStreamDestroy"));
    api->stream_sync=reinterpret_cast<decltype(api->stream_sync)>(dlsym(RTLD_NEXT,"hipStreamSynchronize"));
    api->event_create=reinterpret_cast<decltype(api->event_create)>(dlsym(RTLD_NEXT,"hipEventCreateWithFlags"));
    api->event_destroy=reinterpret_cast<decltype(api->event_destroy)>(dlsym(RTLD_NEXT,"hipEventDestroy"));
    api->event_record=reinterpret_cast<decltype(api->event_record)>(dlsym(RTLD_NEXT,"hipEventRecord"));
    api->event_query=reinterpret_cast<decltype(api->event_query)>(dlsym(RTLD_NEXT,"hipEventQuery"));
    api->stream_wait=reinterpret_cast<decltype(api->stream_wait)>(dlsym(RTLD_NEXT,"hipStreamWaitEvent"));
    return api->stream_create&&api->stream_destroy&&api->stream_sync&&api->event_create&&
        api->event_destroy&&api->event_record&&api->event_query&&api->stream_wait;
}
