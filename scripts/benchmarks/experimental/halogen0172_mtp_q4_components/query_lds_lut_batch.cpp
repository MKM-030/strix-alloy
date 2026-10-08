// Default-off, source-only Halogen 0.17.2 Q4 cooperative-query/LUT-batch probe.
// No host entry point, launch, allocation, runtime hook, or engine integration.
// UNQUALIFIED: the owner must inspect emitted instructions and compare EVERY
// real captured output row bitwise before considering this kernel usable.
// One fixed variant: sixteen pair-LUT loads per group precede an operand-use
// fence and the original dependent dot2 chain. More live VGPRs can reduce speed.
#if !defined(HG0172_Q4_QUERY_LDS_ENABLE) || HG0172_Q4_QUERY_LDS_ENABLE != 1
#error "Explicit source-only opt-in requires HG0172_Q4_QUERY_LDS_ENABLE=1."
#endif

#include <hip/hip_runtime.h>
#include <stddef.h>
#include <stdint.h>

#if !defined(__HIP_PLATFORM_AMD__)
#error "AMD HIP device compilation is required."
#endif
#if defined(__HIP_DEVICE_COMPILE__) && __HIP_DEVICE_COMPILE__
#if !defined(__gfx1151__)
#error "Only the retained gfx1151/wave32 kernel is in scope."
#endif
#endif

namespace {
constexpr unsigned kWidth = 2560;
constexpr unsigned kThreads = 256;
constexpr unsigned kRowLanes = 16;
constexpr unsigned kGroups = 80;
constexpr unsigned kGroupsPerLane = 5;
constexpr unsigned kCodeRowBytes = 1280;
constexpr unsigned kScaleRowBytes = 160;
constexpr unsigned kQueryPacks = 320;

struct alignas(16) SharedBlock {
    uint32_t pair_lut[256];
    uint4 query[4][kGroups];
};

static_assert(sizeof(uint16_t) == 2 && sizeof(uint32_t) == 4,
              "Packed words require little-endian 16/32-bit storage.");
static_assert(sizeof(float) == 4 && sizeof(int64_t) == 8,
              "The public arguments and accumulators require fixed widths.");
static_assert(sizeof(uint4) == 16 && alignof(uint4) == 16,
              "Global and LDS query/code packs require aligned 128-bit vectors.");
static_assert(offsetof(SharedBlock, query) == 1024,
              "The native packed BF16 pair table occupies 1024 bytes.");
static_assert(sizeof(SharedBlock) == 6144,
              "Exactly 1024 table bytes plus 5120 query bytes are in scope.");
#if defined(__BYTE_ORDER__) && defined(__ORDER_LITTLE_ENDIAN__)
static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__, "Little endian only.");
#endif

__device__ __forceinline__ uint4 load128_global(const void* address) {
    // memcpy avoids type-punning raw code/query storage through a uint4*.
    // The caller must validate alignment, and the owner must verify b128 codegen.
    uint4 value;
    __builtin_memcpy(&value, __builtin_assume_aligned(address, 16), sizeof(value));
    return value;
}

__device__ __forceinline__ uint32_t load32_bits(const unsigned char* address) {
    uint32_t value;
    __builtin_memcpy(&value, address, sizeof(value));
    return value;
}

__device__ __forceinline__ uint16_t load16_bits(const unsigned char* address) {
    uint16_t value;
    __builtin_memcpy(&value, address, sizeof(value));
    return value;
}

__device__ __forceinline__ uint16_t native_bf16_rne_bits(uint32_t fp32_bits) {
    // Exact integer sequence at native 0x73b6c0..0x73b718. No float conversion,
    // NaN canonicalization, clipping, or new codebook/weight representation.
    return static_cast<uint16_t>(
        (fp32_bits + 0x7fffu + ((fp32_bits >> 16) & 1u)) >> 16);
}

__device__ __forceinline__ float native_dot2_zero(uint32_t query_pair,
                                                 uint32_t weight_pair) {
    float result;
    asm volatile("v_dot2_f32_bf16 %0, %1, %2, 0"
                 : "=v"(result) : "v"(query_pair), "v"(weight_pair));
    return result;
}

__device__ __forceinline__ float native_dot2(uint32_t query_pair,
                                            uint32_t weight_pair, float sum) {
    asm volatile("v_dot2_f32_bf16 %0, %1, %2, %0"
                 : "+v"(sum) : "v"(query_pair), "v"(weight_pair));
    return sum;
}

__device__ __forceinline__ float native_scale(uint16_t fp16_bits) {
    float result;
    const uint32_t low_half = fp16_bits;
    asm volatile("v_cvt_f32_f16 %0, %1"
                 : "=v"(result) : "v"(low_half));
    return result;
}

__device__ __forceinline__ float native_scale_fma(float sum, float scale,
                                                 float group_dot) {
    // Same FP32 fused scale*group_dot+sum as native v_dual_fmac_f32 at 0x73bad4.
    asm volatile("v_fmac_f32 %0, %1, %2"
                 : "+v"(sum) : "v"(scale), "v"(group_dot));
    return sum;
}

__device__ __forceinline__ float native_add(float left, float right) {
    float result;
    asm volatile("v_add_f32 %0, %1, %2"
                 : "=v"(result) : "v"(left), "v"(right));
    return result;
}

__device__ __forceinline__ float group_dot_lut_batch(const uint4& q0,
                                                     const uint4& q1,
                                                     const uint4& q2,
                                                     const uint4& q3,
                                                     const uint4& codes,
                                                     const uint32_t* lut) {
    // Each byte indexes one packed BF16 pair: low nibble first, high second.
    // All sixteen independent reads are source-visible before the first dot2.
    const uint32_t w00 = lut[codes.x & 0xffu];
    const uint32_t w01 = lut[(codes.x >> 8) & 0xffu];
    const uint32_t w02 = lut[(codes.x >> 16) & 0xffu];
    const uint32_t w03 = lut[codes.x >> 24];
    const uint32_t w04 = lut[codes.y & 0xffu];
    const uint32_t w05 = lut[(codes.y >> 8) & 0xffu];
    const uint32_t w06 = lut[(codes.y >> 16) & 0xffu];
    const uint32_t w07 = lut[codes.y >> 24];
    const uint32_t w08 = lut[codes.z & 0xffu];
    const uint32_t w09 = lut[(codes.z >> 8) & 0xffu];
    const uint32_t w10 = lut[(codes.z >> 16) & 0xffu];
    const uint32_t w11 = lut[codes.z >> 24];
    const uint32_t w12 = lut[codes.w & 0xffu];
    const uint32_t w13 = lut[(codes.w >> 8) & 0xffu];
    const uint32_t w14 = lut[(codes.w >> 16) & 0xffu];
    const uint32_t w15 = lut[codes.w >> 24];

    // A single empty volatile asm consumes every pair in a VGPR and clobbers
    // memory at compiler level. This prevents ordinary load sinking across
    // the fence; it emits no hardware barrier, LDS instruction or wait itself.
    // Root must verify batched ds_load lowering and waits in actual codegen.
    // Keeping all sixteen pairs live here is an intentional register risk.
    asm volatile(""
                 :
                 : "v"(w00), "v"(w01), "v"(w02), "v"(w03),
                   "v"(w04), "v"(w05), "v"(w06), "v"(w07),
                   "v"(w08), "v"(w09), "v"(w10), "v"(w11),
                   "v"(w12), "v"(w13), "v"(w14), "v"(w15)
                 : "memory");

    // Preserve all sixteen dot2 operands and the dependent order exactly.
    float dot = native_dot2_zero(q0.x, w00);
    dot = native_dot2(q0.y, w01, dot);
    dot = native_dot2(q0.z, w02, dot);
    dot = native_dot2(q0.w, w03, dot);
    dot = native_dot2(q1.x, w04, dot);
    dot = native_dot2(q1.y, w05, dot);
    dot = native_dot2(q1.z, w06, dot);
    dot = native_dot2(q1.w, w07, dot);
    dot = native_dot2(q2.x, w08, dot);
    dot = native_dot2(q2.y, w09, dot);
    dot = native_dot2(q2.z, w10, dot);
    dot = native_dot2(q2.w, w11, dot);
    dot = native_dot2(q3.x, w12, dot);
    dot = native_dot2(q3.y, w13, dot);
    dot = native_dot2(q3.z, w14, dot);
    return native_dot2(q3.w, w15, dot);
}

__device__ __forceinline__ void stage_query_pack(unsigned pack,
                                                 const unsigned char* query,
                                                 SharedBlock& shared) {
    const uint4 value = load128_global(query + 16u * pack);
    shared.query[pack & 3u][pack >> 2] = value;
}

__device__ __forceinline__ float xor_add(float value, int distance) {
    // Installed HIP __shfl_xor exchanges integer bits through wave shuffle /
    // ds_bpermute. On required wave32, width16 isolates the two logical rows.
    return native_add(value, __shfl_xor(value, distance, kRowLanes));
}
}  // namespace

// Ten fixed-width arguments match the retained argument VALUES/order. This is
// a new symbol/module, not the stock descriptor or an asserted binary ABI clone.
extern "C" __global__ __launch_bounds__(kThreads)
void halogen0172_q4_query_lut_batch_v1(const unsigned char* __restrict__ base,
                                const uint16_t* __restrict__ query_bf16,
                                float* __restrict__ output,
                                int64_t width, int64_t rows,
                                int64_t code_offset, int64_t scale_offset,
                                int64_t scale_stride,
                                const void* optional_zero, float beta_zero) {
    // Uniform precondition guard. The host must validate geometry, alignment,
    // extents, aliasing and wave32 before launch; returning supplies no status.
    if (!base || !query_bf16 || !output || width != kWidth || rows <= 0 ||
        code_offset < 64 || scale_offset < 64 || scale_stride != kScaleRowBytes ||
        optional_zero || __float_as_uint(beta_zero) != 0u) {
        return;
    }

    __shared__ SharedBlock shared;
    const unsigned tid = threadIdx.x;
    const unsigned lane = tid & (kRowLanes - 1u);
    const int64_t logical_row = static_cast<int64_t>(blockIdx.x) * kRowLanes +
                                (tid >> 4);
    const bool valid_row = logical_row < rows;
    // Native 0x73b664/668 maps invalid tail rows to row zero before its loads.
    // Keep all lanes active through the block barrier and butterfly.
    const int64_t load_row = valid_row ? logical_row : 0;

    const uint16_t low = native_bf16_rne_bits(load32_bits(base + 4u * lane));
    const uint16_t high = native_bf16_rne_bits(load32_bits(base + 4u * (tid >> 4)));
    shared.pair_lut[tid] = static_cast<uint32_t>(low) |
                           (static_cast<uint32_t>(high) << 16);

    const auto* query_bytes = reinterpret_cast<const unsigned char*>(query_bf16);
    stage_query_pack(tid, query_bytes, shared);
    if (tid < kQueryPacks - kThreads) {
        stage_query_pack(tid + kThreads, query_bytes, shared);
    }
    __syncthreads();

    const unsigned char* const codes_row = base + code_offset +
                                           load_row * kCodeRowBytes;
    const unsigned char* const scales_row = base + scale_offset +
                                            load_row * scale_stride;
    float sum = 0.0f;
#pragma clang loop unroll(disable)
    for (unsigned j = 0; j < kGroupsPerLane; ++j) {
        const unsigned group = lane + kRowLanes * j;
        const uint4 codes = load128_global(codes_row + 16u * group);
        const uint4 q0 = shared.query[0][group];
        const uint4 q1 = shared.query[1][group];
        const uint4 q2 = shared.query[2][group];
        const uint4 q3 = shared.query[3][group];
        const float dot = group_dot_lut_batch(q0, q1, q2, q3, codes,
                                              shared.pair_lut);
        const float scale = native_scale(load16_bits(scales_row + 2u * group));
        sum = native_scale_fma(sum, scale, dot);
    }

    // Separate, dependent native FP32 adds in exactly XOR 8,4,2,1 order.
    sum = xor_add(sum, 8);
    sum = xor_add(sum, 4);
    sum = xor_add(sum, 2);
    sum = xor_add(sum, 1);
    if (valid_row && lane == 0) {
        output[logical_row] = sum;
    }
}
