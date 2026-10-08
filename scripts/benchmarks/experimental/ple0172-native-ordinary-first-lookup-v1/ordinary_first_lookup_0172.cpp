#include "ordinary_first_lookup_0172.h"
#include "../ple0172-native-page-scheduler-v1/page_segment_scheduler.h"
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <limits>

namespace {
constexpr std::size_t model_bytes=0x7c8, frame_bytes=0x218;
template<class T> T load(const void* object,std::size_t offset) noexcept {
    T value; std::memcpy(&value,static_cast<const std::byte*>(object)+offset,sizeof(T)); return value;
}
bool overlap(const void* a,std::size_t an,const void* b,std::size_t bn) noexcept {
    const auto x=reinterpret_cast<std::uintptr_t>(a),y=reinterpret_cast<std::uintptr_t>(b);
    if (an>std::numeric_limits<std::uintptr_t>::max()-x ||
        bn>std::numeric_limits<std::uintptr_t>::max()-y) return true;
    return x<y+bn && y<x+an;
}
double clock_seconds() noexcept {
    // Native steady_clock nanoseconds are truncated to microseconds before
    // conversion to seconds at0x17ec153..0x17ec183 and0x17ec2d8..0x17ec300.
    return double(std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count())/1000000.0;
}
struct Poll {
    const Ple0172OrdinaryContract& owner;
    void* model;
    bool callback_enabled;
    double last_callback,period;
    bool aborted{},copying{};
    static bool requested(void* cookie) noexcept {
        auto& poll=*static_cast<Poll*>(cookie);
        if (poll.aborted) return true;
        if (poll.owner.stop_requested && poll.owner.stop_requested(poll.owner.stop_cookie))
            return poll.aborted=true;
        if (poll.copying && poll.callback_enabled && clock_seconds()-poll.last_callback>=poll.period) {
            // Exact native machine ABI: one Any_data-address argument. Owner
            // proves the callback ABI and maintains the std::function lifetime.
            const auto manager=load<std::uintptr_t>(poll.model,0x308);
            const auto invoke=load<void (*)(const void*)>(poll.model,0x310);
            if (!manager || !invoke) return poll.aborted=true;
            try { invoke(static_cast<const std::byte*>(poll.model)+0x2f8); }
            catch (...) { return poll.aborted=true; }
            poll.last_callback=clock_seconds();
            if (poll.owner.stop_requested && poll.owner.stop_requested(poll.owner.stop_cookie))
                return poll.aborted=true;
        }
        return false;
    }
};
}

extern "C" int ple0172_ordinary_first_lookup(void* model,const void* frame,
    const Ple0172OrdinaryContract* owner,std::uint32_t callback_enabled) noexcept {
    if (!owner || owner->abi_version!=1 || owner->struct_bytes!=sizeof(*owner) ||
        owner->enable_page_order!=1 || owner->qualification_mask!=PLE0172_ALL_QUALIFIED)
        return PLE0172_ORDINARY_STOCK;
    const auto* enabled=std::getenv("PLE0172_ORDINARY_PAGE_ORDER");
    if (!enabled || enabled[0]!='1' || enabled[1]!='\0') return PLE0172_ORDINARY_STOCK;
    if (!model || !frame || owner->native_model!=model || !owner->selected_mapper ||
        !owner->metadata_table || !owner->mapping_base || owner->metadata_dtype!=10 ||
        callback_enabled>1) return PLE0172_ORDINARY_STOCK;

    const auto rows=load<std::uint64_t>(frame,0);
    const auto begin=load<std::uintptr_t>(frame,0x130);
    const auto end=load<std::uintptr_t>(frame,0x138);
    const auto capacity=load<std::uintptr_t>(frame,0x140);
    const auto tokens=load<std::int32_t>(frame,0xa8); // Native saved token count/ebp.
    const auto allocation=load<std::int32_t>(model,0x2d8);
    const auto stride=load<std::int32_t>(model,0x770);
    const auto encoding=load<std::int32_t>(model,0x774);
    const auto raw=load<std::byte*>(model,0x798);
    const auto table=load<const std::byte*>(model,0x758);
    const auto table_rows=load<std::uint64_t>(model,0x768);
    const auto direct=load<const void*>(model,0x2d0);
    if (load<std::uint8_t>(model,0x7c0)!=0 || rows<4096 || rows>131072 ||
        !begin || begin%alignof(std::int64_t) || begin>end || end>capacity ||
        end-begin!=rows*sizeof(std::int64_t) || tokens<=0 || tokens>8192 || rows!=std::uint64_t(tokens)*16 ||
        allocation<tokens || allocation<=0 || stride!=160 || encoding!=0 || !raw ||
        table!=owner->metadata_table || table_rows!=owner->metadata_rows || !table_rows ||
        table_rows>(std::numeric_limits<std::uint64_t>::max()-67)/160)
        return PLE0172_ORDINARY_STOCK;
    if (owner->mapper_selection!=PLE0172_MAPPER_DIRECT || !direct || direct!=owner->selected_mapper)
        return PLE0172_ORDINARY_STOCK;
    if (load<const void*>(owner->selected_mapper,0)!=owner->mapping_base ||
        load<std::uint64_t>(owner->selected_mapper,8)!=owner->mapping_bytes ||
        owner->metadata_extent!=((table_rows*160+63)&~std::uint64_t(63))+4 ||
        owner->mapping_bytes>std::numeric_limits<std::size_t>::max()) return PLE0172_ORDINARY_STOCK;
    const auto map=reinterpret_cast<std::uintptr_t>(owner->mapping_base);
    const auto source=reinterpret_cast<std::uintptr_t>(table);
    if (owner->mapping_bytes>std::numeric_limits<std::uintptr_t>::max()-map || source<map ||
        source>map+owner->mapping_bytes || owner->metadata_extent>map+owner->mapping_bytes-source)
        return PLE0172_ORDINARY_STOCK;
    const auto raw_capacity=std::size_t(std::uint64_t(allocation)*2720);
    if (overlap(raw,raw_capacity,model,model_bytes) || overlap(raw,raw_capacity,frame,frame_bytes) ||
        overlap(raw,raw_capacity,owner,sizeof(*owner)) ||
        overlap(raw,raw_capacity,owner->selected_mapper,16)) return PLE0172_ORDINARY_STOCK;
    const auto start=load<double>(frame,0x1f0),period=load<double>(frame,0x1f8);
    if (callback_enabled && (!std::isfinite(start) || !std::isfinite(period) || period<=0))
        return PLE0172_ORDINARY_STOCK;
    Poll poll{*owner,model,callback_enabled!=0,start,period};
    const ple_page::Stop stop{&poll,&Poll::requested};
    ple_page::Schedule schedule;
    ple_page::Policy policy;
    policy.allow_page_order=true;
    const auto prepared=schedule.prepare({table,table_rows,
        static_cast<const std::byte*>(owner->mapping_base),std::size_t(owner->mapping_bytes)},
        {raw,raw_capacity},{reinterpret_cast<const std::int64_t*>(begin),std::size_t(rows)},policy,stop);
    if (prepared==ple_page::Status::fallback) return PLE0172_ORDINARY_STOCK;
    if (prepared!=ple_page::Status::ready) return PLE0172_ORDINARY_ABORT;
    // Selection is irrevocable at this point; any stop/partial copy aborts the
    // native request. Only a complete result permits its unchanged raw H2D.
    poll.copying=true; // Native timed callback is never invoked on stock fallback.
    const auto copied=schedule.copy_pages(0,schedule.page_count(),stop);
    if (copied!=ple_page::Status::complete || Poll::requested(&poll)) return PLE0172_ORDINARY_ABORT;
    if (load<std::byte*>(model,0x798)!=raw || load<const std::byte*>(model,0x758)!=table ||
        load<std::uint64_t>(model,0x768)!=table_rows || load<std::int32_t>(model,0x770)!=stride ||
        load<std::int32_t>(model,0x774)!=encoding || load<std::int32_t>(model,0x2d8)!=allocation ||
        load<std::uintptr_t>(frame,0x130)!=begin || load<std::uintptr_t>(frame,0x138)!=end ||
        load<std::uint64_t>(frame,0)!=rows) return PLE0172_ORDINARY_ABORT;
    return PLE0172_ORDINARY_COMPLETE;
}
