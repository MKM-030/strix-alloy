#include "shadow_cost_wire.h"
#include <cerrno>
#include <limits>
#include <time.h>

extern "C" halogen0173::shadow::CostStamp hgn_shadow_cost_stamp() noexcept {
    using namespace halogen0173::shadow;
    const int saved=errno;
    timespec value{};
    if(clock_gettime(CLOCK_MONOTONIC_RAW,&value)) {
        const int error=errno; errno=saved;
        return {0,CostClockReadFailed,error?error:EIO};
    }
    errno=saved;
    constexpr std::uint64_t billion=1000000000;
    constexpr auto maximum=std::numeric_limits<std::uint64_t>::max();
    if(value.tv_sec<0 || value.tv_nsec<0 || value.tv_nsec>=1000000000 ||
       static_cast<std::uint64_t>(value.tv_sec)>(maximum-static_cast<std::uint64_t>(value.tv_nsec))/billion)
        return {0,CostClockInvalidSample,EOVERFLOW};
    return {static_cast<std::uint64_t>(value.tv_sec)*billion+static_cast<std::uint64_t>(value.tv_nsec),CostClockValid,0};
}
