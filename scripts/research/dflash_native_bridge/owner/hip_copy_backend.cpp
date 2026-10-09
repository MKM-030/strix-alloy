#include "hip_copy_backend.h"
namespace halogen0173::dflash::prefill {
bool HipCopyBackend::configure(HipFunctions f,int success,int not_ready) noexcept {
    if(configured_ || !f.memcpy_2d_async || !f.event_record || !f.event_query || success==not_ready)return false;
    functions_=f;success_=success;not_ready_=not_ready;configured_=true;return true;
}
CopyOps HipCopyBackend::operations() noexcept {
    if(!configured_)return {};
    return {this,copy,record,query};
}
bool HipCopyBackend::copy(void* ctx,void* dst,std::size_t dst_pitch,const void* src,
                          std::size_t src_pitch,std::size_t width,std::size_t rows,void* stream) noexcept {
    auto& b=*static_cast<HipCopyBackend*>(ctx);
    // hipMemcpyDeviceToDevice is 3. Identical native stream0 protects the source
    // after HC production and before attention/FFN or the next layer reuses it.
    return b.functions_.memcpy_2d_async(dst,dst_pitch,src,src_pitch,width,rows,3,stream)==b.success_;
}
bool HipCopyBackend::record(void* ctx,void* event,void* stream) noexcept {
    auto& b=*static_cast<HipCopyBackend*>(ctx);return b.functions_.event_record(event,stream)==b.success_;
}
Poll HipCopyBackend::query(void* ctx,void* event) noexcept {
    auto& b=*static_cast<HipCopyBackend*>(ctx);const int code=b.functions_.event_query(event);
    return code==b.success_?Poll::Complete:code==b.not_ready_?Poll::Pending:Poll::Failed;
}
}
