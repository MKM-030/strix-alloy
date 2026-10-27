#pragma once
#include "hcmean_plan.h"
#include <hip/hip_runtime.h>
namespace hgn01816_hcmean_gpu {
struct Enqueued { Status validation; hipError_t launch; };
// No allocation, synchronization, memcpy, stream lookup, owner inference or capture.
// Validity of source/output memory, same-stream ordering and lifetime are external.
// Ok/hipSuccess records submission only; caller checks async completion separately.
Enqueued enqueue(const Job&,hipStream_t actual_stream) noexcept;
}
