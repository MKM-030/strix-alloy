// Read-only ADLX probe. Built against AMD's pinned v1.5 SDK, using the
// PerfGPUMetrics sample's Initialize/GetSupportedGPUMetrics/GetCurrent pattern.
// No tuning setters, tracking start/stop, or sampling-configuration changes.
#include "SDK/ADLXHelper/Windows/Cpp/ADLXHelper.h"
#include "SDK/Include/IPerformanceMonitoring3.h"
#include "SDK/Include/IGPUTuning.h"
#include <Windows.h>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

using namespace adlx;

static std::string Json(const char* value) {
    if (!value) return "null";
    std::ostringstream out;
    out << '"';
    for (const unsigned char c : std::string(value)) {
        if (c == '"' || c == '\\') out << '\\' << c;
        else if (c < 32) out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<int>(c) << std::dec;
        else out << c;
    }
    out << '"';
    return out.str();
}

static long long EpochMs() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

static void Result(const char* operation, ADLX_RESULT result, int gpuIndex = -1) {
    std::cout << "{\"record\":\"api_result\",\"operation\":" << Json(operation)
              << ",\"gpu_index\":" << gpuIndex << ",\"result\":" << result << "}\n";
}

template<class T, class S>
static IADLXInterfacePtr_T<T> Extension(S* source, const char* name, int gpuIndex) {
    T* raw = nullptr;
    const ADLX_RESULT result = source ? source->QueryInterface(T::IID(), reinterpret_cast<void**>(&raw)) : ADLX_INVALID_OBJECT;
    Result(name, result, gpuIndex);
    IADLXInterfacePtr_T<T> pointer;
    pointer.Attach(raw);
    return pointer;
}

// A metric's official support, range, getter, and unit stay together.
#define BASE_METRICS(X) \
    X("gpu_usage", "%", GPUUsage, adlx_double) \
    X("gpu_clock", "MHz", GPUClockSpeed, adlx_int) \
    X("vram_clock", "MHz", GPUVRAMClockSpeed, adlx_int) \
    X("gpu_temperature", "C", GPUTemperature, adlx_double) \
    X("gpu_hotspot_temperature", "C", GPUHotspotTemperature, adlx_double) \
    X("gpu_power", "W", GPUPower, adlx_double) \
    X("total_board_power", "W", GPUTotalBoardPower, adlx_double) \
    X("fan_speed", "RPM", GPUFanSpeed, adlx_int) \
    X("dedicated_vram", "MB", GPUVRAM, adlx_int) \
    X("gpu_voltage", "mV", GPUVoltage, adlx_int) \
    X("intake_temperature", "C", GPUIntakeTemperature, adlx_double)
#define EXT1_METRICS(X) \
    X("memory_temperature", "C", GPUMemoryTemperature, adlx_double) \
    X("npu_frequency", "MHz", NPUFrequency, adlx_int) \
    X("npu_activity", "%", NPUActivityLevel, adlx_int)
#define EXT2_METRICS(X) X("shared_gpu_memory", "MB", GPUSharedMemory, adlx_int)
#define EXT3_METRICS(X) X("fan_duty", "%", GPUFanDuty, adlx_int)

template<class S, class SupportMethod, class RangeMethod>
static bool MetricSupport(int gpuIndex, const char* name, const char* unit, S* source,
                          SupportMethod supportMethod, RangeMethod rangeMethod) {
    adlx_bool supported = false;
    const ADLX_RESULT result = source ? (source->*supportMethod)(&supported) : ADLX_UNKNOWN_INTERFACE;
    std::cout << "{\"record\":\"metric_support\",\"gpu_index\":" << gpuIndex
              << ",\"metric\":" << Json(name) << ",\"unit\":" << Json(unit)
              << ",\"result\":" << result << ",\"supported\":";
    if (ADLX_SUCCEEDED(result)) std::cout << (supported ? "true" : "false");
    else std::cout << "null";
    if (ADLX_SUCCEEDED(result) && supported) {
        adlx_int min = 0, max = 0;
        const ADLX_RESULT rangeResult = (source->*rangeMethod)(&min, &max);
        std::cout << ",\"range_result\":" << rangeResult;
        if (ADLX_SUCCEEDED(rangeResult)) std::cout << ",\"min\":" << min << ",\"max\":" << max;
    }
    std::cout << "}\n";
    return ADLX_SUCCEEDED(result) && supported;
}

template<class T, class M, class Method>
static void MetricValue(const char* name, M* metrics, Method method, bool& first) {
    if (!first) std::cout << ',';
    first = false;
    T value = 0;
    const ADLX_RESULT result = metrics ? (metrics->*method)(&value) : ADLX_UNKNOWN_INTERFACE;
    std::cout << Json(name) << ":{\"result\":" << result << ",\"value\":";
    if (ADLX_SUCCEEDED(result) && std::isfinite(static_cast<double>(value))) std::cout << value;
    else std::cout << "null";
    std::cout << '}';
}

struct GPUState {
    int index;
    IADLXGPUPtr gpu;
    std::map<std::string, bool> supported;
};

static int Probe(ADLXHelper& helper, int samples, int intervalMs) {
    IADLXGPUListPtr gpus;
    auto* system = helper.GetSystemServices();
    ADLX_RESULT result = system->GetGPUs(&gpus);
    Result("GetGPUs", result);
    if (ADLX_FAILED(result) || !gpus) return 3;
    IADLXPerformanceMonitoringServicesPtr perf;
    result = system->GetPerformanceMonitoringServices(&perf);
    Result("GetPerformanceMonitoringServices", result);
    IADLXGPUTuningServicesPtr tuning;
    result = system->GetGPUTuningServices(&tuning);
    Result("GetGPUTuningServices", result);
    std::vector<GPUState> states;
    for (adlx_uint i = gpus->Begin(); i != gpus->End(); ++i) {
        GPUState state;
        state.index = static_cast<int>(i);
        result = gpus->At(i, &state.gpu);
        Result("GPUList.At", result, state.index);
        if (ADLX_FAILED(result) || !state.gpu) continue;
        const char* name = nullptr;
        const char* deviceId = nullptr;
        adlx_uint totalVRAM = 0;
        const ADLX_RESULT nameResult = state.gpu->Name(&name);
        const ADLX_RESULT idResult = state.gpu->DeviceId(&deviceId);
        const ADLX_RESULT vramResult = state.gpu->TotalVRAM(&totalVRAM);
        std::cout << "{\"record\":\"gpu\",\"gpu_index\":" << i
                  << ",\"name\":" << Json(ADLX_SUCCEEDED(nameResult) ? name : nullptr)
                  << ",\"device_id\":" << Json(ADLX_SUCCEEDED(idResult) ? deviceId : nullptr)
                  << ",\"total_vram_result\":" << vramResult << ",\"total_vram_mb\":";
        if (ADLX_SUCCEEDED(vramResult)) std::cout << totalVRAM; else std::cout << "null";
        std::cout << "}\n";
        IADLXGPUMetricsSupportPtr support;
        result = perf ? perf->GetSupportedGPUMetrics(state.gpu, &support) : ADLX_NOT_SUPPORTED;
        Result("GetSupportedGPUMetrics", result, state.index);
        auto support1 = Extension<IADLXGPUMetricsSupport1>(support.GetPtr(), "QueryInterface.GPUMetricsSupport1", state.index);
        auto support2 = Extension<IADLXGPUMetricsSupport2>(support.GetPtr(), "QueryInterface.GPUMetricsSupport2", state.index);
        auto support3 = Extension<IADLXGPUMetricsSupport3>(support.GetPtr(), "QueryInterface.GPUMetricsSupport3", state.index);
#define BASE_SUPPORT(n, u, m, t) state.supported[n] = MetricSupport(state.index, n, u, support.GetPtr(), &IADLXGPUMetricsSupport::IsSupported##m, &IADLXGPUMetricsSupport::Get##m##Range);
        BASE_METRICS(BASE_SUPPORT)
#undef BASE_SUPPORT
#define EXT1_SUPPORT(n, u, m, t) state.supported[n] = MetricSupport(state.index, n, u, support1.GetPtr(), &IADLXGPUMetricsSupport1::IsSupported##m, &IADLXGPUMetricsSupport1::Get##m##Range);
        EXT1_METRICS(EXT1_SUPPORT)
#undef EXT1_SUPPORT
#define EXT2_SUPPORT(n, u, m, t) state.supported[n] = MetricSupport(state.index, n, u, support2.GetPtr(), &IADLXGPUMetricsSupport2::IsSupported##m, &IADLXGPUMetricsSupport2::Get##m##Range);
        EXT2_METRICS(EXT2_SUPPORT)
#undef EXT2_SUPPORT
#define EXT3_SUPPORT(n, u, m, t) state.supported[n] = MetricSupport(state.index, n, u, support3.GetPtr(), &IADLXGPUMetricsSupport3::IsSupported##m, &IADLXGPUMetricsSupport3::Get##m##Range);
        EXT3_METRICS(EXT3_SUPPORT)
#undef EXT3_SUPPORT
#define TUNING_SUPPORT(m) { adlx_bool flag = false; const ADLX_RESULT r = tuning ? tuning->m(state.gpu, &flag) : ADLX_NOT_SUPPORTED; std::cout << "{\"record\":\"tuning_support\",\"gpu_index\":" << i << ",\"query\":" << Json(#m) << ",\"result\":" << r << ",\"value\":"; if (ADLX_SUCCEEDED(r)) std::cout << (flag ? "true" : "false"); else std::cout << "null"; std::cout << "}\n"; }
        TUNING_SUPPORT(IsAtFactory)
        TUNING_SUPPORT(IsSupportedAutoTuning)
        TUNING_SUPPORT(IsSupportedPresetTuning)
        TUNING_SUPPORT(IsSupportedManualGFXTuning)
        TUNING_SUPPORT(IsSupportedManualVRAMTuning)
        TUNING_SUPPORT(IsSupportedManualFanTuning)
        TUNING_SUPPORT(IsSupportedManualPowerTuning)
#undef TUNING_SUPPORT
        states.push_back(state);
    }
    if (states.empty() || !perf) return 4;
    int successfulSamples = 0;
    for (int sample = 0; sample < samples; ++sample) {
        for (auto& state : states) {
            const auto requestedAt = EpochMs();
            IADLXGPUMetricsPtr metrics;
            const ADLX_RESULT currentResult = perf->GetCurrentGPUMetrics(state.gpu, &metrics);
            IADLXGPUMetrics1Ptr metrics1(metrics);
            IADLXGPUMetrics2Ptr metrics2(metrics);
            IADLXGPUMetrics3Ptr metrics3(metrics);
            adlx_int64 timestamp = 0;
            const ADLX_RESULT timestampResult = metrics ? metrics->TimeStamp(&timestamp) : ADLX_INVALID_OBJECT;
            std::cout << "{\"record\":\"sample\",\"gpu_index\":" << state.index
                      << ",\"sample_index\":" << sample << ",\"requested_epoch_ms\":" << requestedAt
                      << ",\"completed_epoch_ms\":" << EpochMs() << ",\"result\":" << currentResult
                      << ",\"timestamp_result\":" << timestampResult << ",\"adlx_timestamp_ms\":";
            if (ADLX_SUCCEEDED(timestampResult)) std::cout << timestamp; else std::cout << "null";
            std::cout << ",\"metrics\":{";
            bool first = true;
#define BASE_VALUE(n, u, m, t) if (state.supported[n]) MetricValue<t>(n, metrics.GetPtr(), &IADLXGPUMetrics::m, first);
            BASE_METRICS(BASE_VALUE)
#undef BASE_VALUE
#define EXT1_VALUE(n, u, m, t) if (state.supported[n]) MetricValue<t>(n, metrics1.GetPtr(), &IADLXGPUMetrics1::m, first);
            EXT1_METRICS(EXT1_VALUE)
#undef EXT1_VALUE
#define EXT2_VALUE(n, u, m, t) if (state.supported[n]) MetricValue<t>(n, metrics2.GetPtr(), &IADLXGPUMetrics2::m, first);
            EXT2_METRICS(EXT2_VALUE)
#undef EXT2_VALUE
#define EXT3_VALUE(n, u, m, t) if (state.supported[n]) MetricValue<t>(n, metrics3.GetPtr(), &IADLXGPUMetrics3::m, first);
            EXT3_METRICS(EXT3_VALUE)
#undef EXT3_VALUE
            std::cout << "}}" << std::endl;
            if (ADLX_SUCCEEDED(currentResult) && metrics) ++successfulSamples;
        }
        if (sample + 1 < samples) std::this_thread::sleep_for(std::chrono::milliseconds(intervalMs));
    }
    return successfulSamples ? 0 : 5;
}

int main(int argc, char** argv) {
    int samples = 5, intervalMs = 1000;
    try {
        for (int i = 1; i < argc; ++i) {
            const std::string argument = argv[i];
            if (argument == "--help") {
                std::cerr << "halogen_adlx_probe [--samples 1..86400] [--interval-ms 100..60000]\nRead-only support/range and current metric queries; NDJSON on stdout.\n";
                return 0;
            }
            if (i + 1 >= argc) throw std::invalid_argument("Missing option value");
            const std::string value = argv[++i];
            size_t consumed = 0;
            const int number = std::stoi(value, &consumed);
            if (consumed != value.size()) throw std::invalid_argument("Invalid option value");
            if (argument == "--samples" && number >= 1 && number <= 86400) samples = number;
            else if (argument == "--interval-ms" && number >= 100 && number <= 60000) intervalMs = number;
            else throw std::invalid_argument("Unknown or out-of-range option");
        }
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
    std::cout << std::setprecision(12);
    ADLXHelper helper;
    const ADLX_RESULT initializeResult = helper.Initialize();
    std::cout << "{\"record\":\"initialize\",\"read_only\":true,\"result\":" << initializeResult
              << ",\"adlx_version\":" << Json(helper.QueryVersion())
              << ",\"adlx_full_version\":" << helper.QueryFullVersion()
              << ",\"sdk_full_version\":" << ADLX_FULL_VERSION
              << ",\"samples\":" << samples << ",\"interval_ms\":" << intervalMs << "}\n";
    int exitCode = 3;
    if (ADLX_SUCCEEDED(initializeResult) && helper.GetSystemServices()) exitCode = Probe(helper, samples, intervalMs);
    // Probe's ADLX smart pointers have all been released before termination.
    const ADLX_RESULT terminateResult = helper.Terminate();
    Result("Terminate", terminateResult);
    if (ADLX_FAILED(terminateResult) && exitCode == 0) exitCode = 6;
    return exitCode;
}
