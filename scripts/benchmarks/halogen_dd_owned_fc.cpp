/* Normal, typed Dynamic Dispatch 1.8 C++ client. No code patching or hooks.
 * Root-owned child guards select and pin the DLLs, interpreter and input bytes.
 * Only a single already-packed expert FC is staged; resident BOs are reused.
 */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define HALOGEN_DD_OWNED_FC_BUILD
#include <windows.h>
#include <ops/llm_ops/mladfmatmulbias/mladfmatmulbias.hpp>
#include "halogen_dd_owned_fc.h"
#include <algorithm>
#include <any>
#include <cstdio>
#include <cstring>
#include <exception>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using FcOp = ryzenai::mladfmatmulbias<uint16_t, int8_t, uint16_t, uint16_t>;
static_assert(sizeof(xrt::bo) == 16, "Reviewed XRT/MSVC x64 BO ABI changed");
static_assert(sizeof(HalogenDdOwnedFcReceipt) == 88, "Receipt ABI changed");

namespace {
struct State {
    std::unique_ptr<FcOp> op;
    std::vector<xrt::bo> inputs, outputs;
    HalogenDdOwnedFcReceipt receipt{};
};
void describe(char *error, uint32_t capacity, const char *message) noexcept {
    if (error && capacity) {
        const auto bytes = std::min<size_t>(std::strlen(message), capacity - 1);
        std::memcpy(error, message, bytes);
        error[bytes] = '\0';
    }
}
void publish(State &state, HalogenDdOwnedFcReceipt *receipt) noexcept {
    if (receipt) *receipt = state.receipt;
}
void checkpoint(uint32_t fc_index, const char *stage) noexcept {
    std::fprintf(stdout, "DD_OWNED_NATIVE_STAGE fc%u_%s\n", fc_index, stage);
    std::fflush(stdout);
}
}

extern "C" __declspec(dllexport)
int halogen_dd_owned_fc_create(uint32_t fc_index, const uint8_t *packed,
    uint64_t packed_bytes, void **handle, HalogenDdOwnedFcReceipt *receipt,
    char *error, uint32_t error_capacity) {
    if (handle) *handle = nullptr;
    if (receipt) *receipt = {};
    describe(error, error_capacity, "");
    State candidate;
    auto &r = candidate.receipt;
    r.schema = 1; r.size = sizeof(r); r.stage = 1; r.fc_index = fc_index;
    try {
        if (!handle || !receipt || !packed || fc_index > 1)
            throw std::invalid_argument("Missing output/packed data or invalid FC index");
        r.logical_k = fc_index == 0 ? 2560u : 640u;
        r.logical_n = fc_index == 0 ? 1280u : 2560u;
        r.kernel_k = fc_index == 0 ? 2560u : 768u;
        r.kernel_n = fc_index == 0 ? 2560u : 3072u;
        const uint64_t expected_bytes = fc_index == 0 ? 4198400ull : 1597440ull;
        if (packed_bytes != expected_bytes)
            throw std::invalid_argument("Pass raw packed FC bytes without expert-stride tail padding");
        r.packed_bytes = packed_bytes;
        LARGE_INTEGER frequency{};
        if (!QueryPerformanceFrequency(&frequency) || frequency.QuadPart <= 0)
            throw std::runtime_error("QPC frequency unavailable");
        r.qpc_frequency = frequency.QuadPart;
        std::map<std::string, std::any> attrs{
            {"op_version", std::string("v2")}, {"group_size", 32},
            {"max_m", 1}, {"num_preformat_tensors", 1}, {"use_host_buffer", 0},
            {"without_bias", false}, {"wts_interleaved", false}
        };
        r.stage = 2;
        checkpoint(fc_index, "constructor_begin");
        candidate.op = std::make_unique<FcOp>("bfloat16", "int4", "bfloat16", true, attrs);
        checkpoint(fc_index, "constructor_done");
        /* The preformatted-constant path does not initialize DD's group-size
         * member before scratch allocation. Set it through the public API. */
        checkpoint(fc_index, "set_shape_begin");
        const auto shape = candidate.op->set_shape({1, r.logical_k},
            {r.logical_k, r.logical_n}, 32);
        if (shape.size() != 4 || shape[0] != 1 || shape[1] != r.kernel_k ||
            shape[2] != r.kernel_n || shape[3] != 32)
            throw std::runtime_error("Public DD selected different kernel geometry");
        checkpoint(fc_index, "set_shape_done");
        std::vector<Tensor> constants{
            {nullptr, {r.logical_k, r.logical_n}, "int4"},
            {const_cast<uint8_t *>(packed), {static_cast<size_t>(packed_bytes)}, "uint8"}
        };
        checkpoint(fc_index, "initialize_const_params_begin");
        candidate.op->initialize_const_params(constants, attrs);
        checkpoint(fc_index, "initialize_const_params_done");
        checkpoint(fc_index, "get_owned_bos_begin");
        candidate.inputs = candidate.op->get_inputs(1);
        candidate.outputs = candidate.op->get_outputs(1);
        auto weights = candidate.op->get_const();
        if (candidate.inputs.size() != 1 || candidate.outputs.size() != 1 ||
            weights.size() != 1 || weights[0].size() != packed_bytes)
            throw std::runtime_error("Owned DD BO count or packed byte extent differs");
        candidate.inputs.push_back(weights[0]);
        r.input_bo_bytes = candidate.inputs[0].size();
        r.output_bo_bytes = candidate.outputs[0].size();
        if (r.input_bo_bytes < 2ull * r.kernel_k || r.output_bo_bytes < 2ull * r.kernel_n)
            throw std::runtime_error("Owned token BO does not cover padded geometry");
        checkpoint(fc_index, "get_owned_bos_done");
        auto resident = std::make_unique<State>(std::move(candidate));
        publish(*resident, receipt);
        *handle = resident.release();
        return 0;
    } catch (const std::exception &failure) {
        r.stage = 255; r.output_valid = 0; publish(candidate, receipt);
        describe(error, error_capacity, failure.what());
    } catch (...) {
        r.stage = 255; r.output_valid = 0; publish(candidate, receipt);
        describe(error, error_capacity, "Unknown public DD setup exception");
    }
    return 1;
}

extern "C" __declspec(dllexport)
int halogen_dd_owned_fc_run(void *handle, const uint16_t *input,
    uint32_t input_elements, uint16_t *output, uint32_t output_elements,
    HalogenDdOwnedFcReceipt *receipt, char *error, uint32_t error_capacity) {
    describe(error, error_capacity, "");
    if (receipt) *receipt = {};
    if (!handle) {
        describe(error, error_capacity, "Missing resident FC handle");
        return 1;
    }
    auto &state = *static_cast<State *>(handle);
    auto &r = state.receipt;
    r.output_valid = 0; r.qpc_start = 0; r.qpc_end = 0; r.stage = 3;
    if (output) std::fill_n(output, std::min(output_elements, r.logical_n), uint16_t{0});
    try {
        if (!receipt || !input || !output || input_elements != r.logical_k ||
            output_elements != r.logical_n || r.calls_completed >= 2)
            throw std::invalid_argument("Exact logical input/output extents and at most two calls required");
        /* set_input zeros kernel-K padding and copies only original logical K. */
        state.op->set_input(const_cast<uint16_t *>(input), state.inputs[0]);
        state.inputs[0].sync(XCL_BO_SYNC_BO_TO_DEVICE, 2ull * r.kernel_k, 0);
        /* Nonzero sentinel makes an unwritten zero-bank output detectable. */
        auto device_output = state.outputs[0].map<uint16_t *>();
        std::fill_n(device_output, r.kernel_n, uint16_t{0x7fc1});
        state.outputs[0].sync(XCL_BO_SYNC_BO_TO_DEVICE, 2ull * r.kernel_n, 0);
        LARGE_INTEGER tick{};
        if (!QueryPerformanceCounter(&tick)) throw std::runtime_error("QPC start unavailable");
        r.qpc_start = tick.QuadPart;
        /* Owned output BO is present during DD's synchronous N-depadding. */
        state.op->execute(state.inputs, state.outputs, true);
        state.outputs[0].sync(XCL_BO_SYNC_BO_FROM_DEVICE, 2ull * r.kernel_n, 0);
        if (!QueryPerformanceCounter(&tick)) throw std::runtime_error("QPC end unavailable");
        r.qpc_end = tick.QuadPart;
        device_output = state.outputs[0].map<uint16_t *>();
        std::copy_n(device_output, r.logical_n, output);
        ++r.calls_completed; r.output_valid = 1; r.stage = 4;
        publish(state, receipt);
        return 0;
    } catch (const std::exception &failure) {
        describe(error, error_capacity, failure.what());
    } catch (...) {
        describe(error, error_capacity, "Unknown public DD execution exception");
    }
    r.stage = 255; r.output_valid = 0;
    if (output) std::fill_n(output, std::min(output_elements, r.logical_n), uint16_t{0});
    publish(state, receipt);
    return 1;
}

extern "C" __declspec(dllexport)
void halogen_dd_owned_fc_destroy(void *handle) {
    delete static_cast<State *>(handle);
}
