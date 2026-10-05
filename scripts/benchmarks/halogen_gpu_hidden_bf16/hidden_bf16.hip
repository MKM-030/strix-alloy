// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// Source-only, fixed-shape replay of the retained gfx1151 M4 hidden FC.
// W contains original native-rounded BF16 words in [output][K] order.
// The caller must launch grid(160,1,1), block(256,1,1), shared=0, stream=0.
#include <hip/hip_runtime.h>
#include <stdint.h>

#if !defined(__HIP_PLATFORM_AMD__)
#error "This kernel requires the AMD HIP device toolchain."
#endif

#if defined(__HIP_DEVICE_COMPILE__) && __HIP_DEVICE_COMPILE__
#if !defined(__gfx1151__)
#error "This kernel is qualified only for a gfx1151 device compilation."
#endif
#endif

namespace {
constexpr unsigned kWidth = 2560;
constexpr unsigned kBlock = 256;
constexpr unsigned kGrid = 160;
constexpr unsigned kRowLanes = 16;

static_assert(sizeof(uint16_t) == 2, "BF16 words must be 16 bits.");
static_assert(sizeof(uint32_t) == 4, "Packed BF16 pairs must be 32 bits.");
static_assert(sizeof(float) == 4, "Accumulators must be FP32.");
static_assert(sizeof(uint4) == 16 && alignof(uint4) == 16,
              "The weight/input vector load contract is 128 bits, aligned16.");

__device__ __forceinline__ uint4 load128(const uint16_t* words) {
    // Every source is aligned16 by the base-pointer contract and fixed strides.
    // memcpy avoids accessing a uint16_t allocation through an aliased uint4*.
    // The owner must still check that compilation emits a global128-bit load.
    uint4 result;
    __builtin_memcpy(&result, __builtin_assume_aligned(words, 16), sizeof(result));
    return result;
}

__device__ __forceinline__ float native_dot2(uint32_t x_pair,
                                            uint32_t w_pair, float acc) {
    // Low/high halfwords are consecutive BF16 elements, with no conversion.
    // Keep the same hardware dot2 and its accumulator boundary; no FMA path.
    asm volatile("v_dot2_f32_bf16 %0, %1, %2, %0"
                 : "+v"(acc) : "v"(x_pair), "v"(w_pair));
    return acc;
}

__device__ __forceinline__ float native_add(float left, float right) {
    float result;
    // A separate native FP32 ADD prevents contraction/reassociation through
    // either a chunk boundary or one stage of the XOR butterfly.
    asm volatile("v_add_f32 %0, %1, %2"
                 : "=v"(result) : "v"(left), "v"(right));
    return result;
}

__device__ __forceinline__ void dot_four(float& d0, float& d1,
                                         float& d2, float& d3,
                                         uint32_t x0, uint32_t x1,
                                         uint32_t x2, uint32_t x3,
                                         uint32_t w) {
    // Four independent streams interleaved at each increasing pair index.
    d0 = native_dot2(x0, w, d0);
    d1 = native_dot2(x1, w, d1);
    d2 = native_dot2(x2, w, d2);
    d3 = native_dot2(x3, w, d3);
}

__device__ __forceinline__ void butterfly(float& s0, float& s1,
                                          float& s2, float& s3, int distance) {
    // On physical wave32, width16 keeps both output-row halves independent.
    // All lanes execute every stage before the p0-only store branch.
    const float v0 = __shfl_xor(s0, distance, kRowLanes);
    const float v1 = __shfl_xor(s1, distance, kRowLanes);
    const float v2 = __shfl_xor(s2, distance, kRowLanes);
    const float v3 = __shfl_xor(s3, distance, kRowLanes);
    s0 = native_add(s0, v0);
    s1 = native_add(s1, v1);
    s2 = native_add(s2, v2);
    s3 = native_add(s3, v3);
}

__device__ __forceinline__ uint16_t native_bf16_rne(float value) {
    // The original finite-value integer RNE sequence; no NaN canonicalization.
    const uint32_t bits = __float_as_uint(value);
    return static_cast<uint16_t>((bits + 0x7fffu + ((bits >> 16) & 1u)) >> 16);
}
}  // namespace

extern "C" __global__ __launch_bounds__(256)
void halogen_gpu_hidden_bf16(const uint16_t* __restrict__ W,
                             const uint16_t* __restrict__ X,
                             uint16_t* __restrict__ Y,
                             int64_t K, int64_t N) {
    // The caller validates exact geometry and emitted gfx1151/wave32 metadata
    // before launch. Only fixed K/N are checked here; invalid dimensions return
    // without writing output or supplying an error/status object.
    if (K != kWidth || N != kWidth) {
        return;
    }

    const unsigned t = threadIdx.x;
    const unsigned o = kRowLanes * blockIdx.x + (t >> 4);
    const unsigned p = t & (kRowLanes - 1);
    const uint16_t* const w_row = W + o * kWidth;

    float s0 = 0.0f;
    float s1 = 0.0f;
    float s2 = 0.0f;
    float s3 = 0.0f;

    // Preserve ten separately accumulated chunks; do not make a long dot2
    // chain across q. Keeping this loop rolled also avoids a huge source body.
#pragma clang loop unroll(disable)
    for (unsigned q = 0; q < 10; ++q) {
        const unsigned k = kRowLanes * p + 256 * q;
        const uint4 w0 = load128(w_row + k);
        const uint4 w1 = load128(w_row + k + 8);
        const uint4 x00 = load128(X + k);
        const uint4 x01 = load128(X + k + 8);
        const uint4 x10 = load128(X + kWidth + k);
        const uint4 x11 = load128(X + kWidth + k + 8);
        const uint4 x20 = load128(X + 2 * kWidth + k);
        const uint4 x21 = load128(X + 2 * kWidth + k + 8);
        const uint4 x30 = load128(X + 3 * kWidth + k);
        const uint4 x31 = load128(X + 3 * kWidth + k + 8);

        float d0 = 0.0f;
        float d1 = 0.0f;
        float d2 = 0.0f;
        float d3 = 0.0f;
        dot_four(d0, d1, d2, d3, x00.x, x10.x, x20.x, x30.x, w0.x);
        dot_four(d0, d1, d2, d3, x00.y, x10.y, x20.y, x30.y, w0.y);
        dot_four(d0, d1, d2, d3, x00.z, x10.z, x20.z, x30.z, w0.z);
        dot_four(d0, d1, d2, d3, x00.w, x10.w, x20.w, x30.w, w0.w);
        dot_four(d0, d1, d2, d3, x01.x, x11.x, x21.x, x31.x, w1.x);
        dot_four(d0, d1, d2, d3, x01.y, x11.y, x21.y, x31.y, w1.y);
        dot_four(d0, d1, d2, d3, x01.z, x11.z, x21.z, x31.z, w1.z);
        dot_four(d0, d1, d2, d3, x01.w, x11.w, x21.w, x31.w, w1.w);

        s0 = native_add(s0, d0);
        s1 = native_add(s1, d1);
        s2 = native_add(s2, d2);
        s3 = native_add(s3, d3);
    }

    butterfly(s0, s1, s2, s3, 8);
    butterfly(s0, s1, s2, s3, 4);
    butterfly(s0, s1, s2, s3, 2);
    butterfly(s0, s1, s2, s3, 1);

    if (p == 0) {
        Y[o] = native_bf16_rne(s0);
        Y[kWidth + o] = native_bf16_rne(s1);
        Y[2 * kWidth + o] = native_bf16_rne(s2);
        Y[3 * kWidth + o] = native_bf16_rne(s3);
    }
}
