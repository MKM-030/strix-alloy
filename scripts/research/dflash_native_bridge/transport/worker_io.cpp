#include "worker_io.h"
namespace halogen0173::dflash::transport {
namespace {
bool write(void* p,const std::uint8_t* h,std::size_t hn,const std::uint8_t* ids,std::size_t n,const void* f,std::size_t bytes) noexcept {
    auto* file=static_cast<std::FILE*>(p);
    return file&&std::fwrite(h,1,hn,file)==hn&&std::fwrite(ids,1,n,file)==n&&std::fwrite(f,1,bytes,file)==bytes&&std::fflush(file)==0;
}
}
SinkOps file_sink(std::FILE* f) noexcept {return {f,write};}
bool run_worker(Exporter& x,LoopOps ops) noexcept {
    if(!ops.stop||!ops.wait)return false;
    for(;;){if(ops.stop(ops.context))x.disable_new();const auto s=x.step();
        if(s==Step::Poisoned)return false;
        if((s==Step::Stopped||s==Step::Off)&&x.drained())return !x.failed();
        ops.wait(ops.context,s);
    }
}
}
