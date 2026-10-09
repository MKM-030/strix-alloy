#pragma once
#include "pending_owner.h"

namespace halogen0173::dflash::prefill {
// Resolution, pinned-storage allocation and event creation belong to cold startup.
// This component never loads HIP, initializes a device, allocates or waits.
struct HipFunctions {
    int (*memcpy_2d_async)(void*,std::size_t,const void*,std::size_t,
                           std::size_t,std::size_t,int,void*){};
    int (*event_record)(void*,void*){};
    int (*event_query)(void*){};
};
class HipCopyBackend final {
public:
    bool configure(HipFunctions functions,int success_code,int not_ready_code) noexcept;
    CopyOps operations() noexcept;
private:
    static bool copy(void*,void*,std::size_t,const void*,std::size_t,std::size_t,std::size_t,void*) noexcept;
    static bool record(void*,void*,void*) noexcept;
    static Poll query(void*,void*) noexcept;
    HipFunctions functions_{};
    int success_{},not_ready_{};
    bool configured_{};
};
}
