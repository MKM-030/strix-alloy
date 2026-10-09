#include "retained_relay.h"
#if (!defined(__linux__) || !defined(__x86_64__)) && !defined(HGN_DFLASH_SYSV_MOCK)
#error "retained callback is a Linux x86-64 SysV source"
#endif
extern "C" int* __errno_location()noexcept;
extern "C" __attribute__((noinline,visibility("default")))
void HGN_DFLASH_CALLBACK_ABI hgn_dflash_ready_callback(hgn_dflash::u32 site,hgn_dflash::Frame* frame,
    hgn_dflash::Invocation* invocation,hgn_dflash::Lane* lane,
    const hgn_dflash::Configuration* provider)noexcept {
    int* const error=__errno_location();
    const int saved=*error;
    if(site==0&&frame&&invocation&&lane&&provider)
        hgn_dflash::ready_dispatch(*lane,*provider,*frame,*invocation);
    *error=saved;
}
