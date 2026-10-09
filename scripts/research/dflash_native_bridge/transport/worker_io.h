#pragma once
#include "owned_transport.h"
#include <cstdio>
namespace halogen0173::dflash::transport {
// Cold-opened binary pipe/file; the worker owns its lifetime. Native callbacks
// do not call fwrite, sleep, wait, create resources, or enter this loop.
SinkOps file_sink(std::FILE*) noexcept;
struct LoopOps {
    void* context{};
    bool (*stop)(void*) noexcept{};
    void (*wait)(void*,Step) noexcept{};
};
// Poll/wait only on the explicit worker. Poisoned returns false with resources
// retained; caller may attempt recover_failed_copy and run again.
bool run_worker(Exporter&,LoopOps) noexcept;
}
