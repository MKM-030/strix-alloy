// Read-only system power discovery, using the existing pinned probe helpers.
// This translation unit reuses its JSON, QueryInterface, and ADLX lifecycle.
// The renamed GPU main/Probe functions are never called here.
#define main HalogenAdlxGpuProbeMain
#include "halogen_adlx_probe.cpp"
#undef main
#include "SDK/Include/ISystem1.h"
#include "SDK/Include/IPowerTuning.h"
#include "SDK/Include/IPerformanceMonitoring1.h"

static bool Capability(const char* name, ADLX_RESULT result, adlx_bool value) {
    std::cout << "{\"record\":\"system_support\",\"query\":" << Json(name)
              << ",\"result\":" << result << ",\"supported\":";
    if (ADLX_SUCCEEDED(result)) std::cout << (value ? "true" : "false");
    else std::cout << "null";
    std::cout << "}\n";
    return ADLX_SUCCEEDED(result) && value;
}

static int ProbePower(ADLXHelper& helper) {
    auto* system = helper.GetSystemServices();
    IADLXPerformanceMonitoringServicesPtr perf;
    ADLX_RESULT result = system->GetPerformanceMonitoringServices(&perf);
    Result("GetPerformanceMonitoringServices", result);
    IADLXSystemMetricsSupportPtr support;
    result = perf ? perf->GetSupportedSystemMetrics(&support) : ADLX_NOT_SUPPORTED;
    Result("GetSupportedSystemMetrics", result);
    auto support1 = Extension<IADLXSystemMetricsSupport1>(support.GetPtr(),
        "QueryInterface.SystemMetricsSupport1", -1);
    adlx_bool flag = false;
    result = support ? support->IsSupportedCPUUsage(&flag) : ADLX_UNKNOWN_INTERFACE;
    const bool cpuSupported = Capability("IsSupportedCPUUsage", result, flag);
    flag = false;
    result = support ? support->IsSupportedSmartShift(&flag) : ADLX_UNKNOWN_INTERFACE;
    const bool shiftSupported = Capability("IsSupportedSmartShift", result, flag);
    flag = false;
    result = support1 ? support1->IsSupportedPowerDistribution(&flag) : ADLX_UNKNOWN_INTERFACE;
    const bool distributionSupported = Capability("IsSupportedPowerDistribution", result, flag);

    // Power-tuning-domain discovery is separate from GPU manual-tuning support.
    auto system1 = Extension<IADLXSystem1>(system, "QueryInterface.System1", -1);
    IADLXPowerTuningServicesPtr power;
    result = system1 ? system1->GetPowerTuningServices(&power) : ADLX_UNKNOWN_INTERFACE;
    Result("GetPowerTuningServices", result);
    IADLXSmartShiftMaxPtr maximum;
    result = power ? power->GetSmartShiftMax(&maximum) : ADLX_NOT_SUPPORTED;
    Result("GetSmartShiftMax", result);
    flag = false;
    result = maximum ? maximum->IsSupported(&flag) : ADLX_UNKNOWN_INTERFACE;
    if (Capability("SmartShiftMax.IsSupported", result, flag)) {
        ADLX_SSM_BIAS_MODE mode = SSM_BIAS_AUTO;
        const ADLX_RESULT modeResult = maximum->GetBiasMode(&mode);
        adlx_int bias = 0;
        const ADLX_RESULT biasResult = maximum->GetBias(&bias);
        std::cout << "{\"record\":\"smart_shift_max_readback\",\"mode_result\":" << modeResult
                  << ",\"mode\":";
        if (ADLX_SUCCEEDED(modeResult)) std::cout << static_cast<int>(mode); else std::cout << "null";
        std::cout << ",\"mode_name\":";
        if (ADLX_SUCCEEDED(modeResult)) std::cout << Json(mode == SSM_BIAS_AUTO ? "auto" : (mode == SSM_BIAS_MANUAL ? "manual" : "unknown")); else std::cout << "null";
        std::cout << ",\"bias_result\":" << biasResult << ",\"bias\":";
        if (ADLX_SUCCEEDED(biasResult)) std::cout << bias; else std::cout << "null";
        std::cout << "}\n";
    }

    if (perf && (cpuSupported || shiftSupported || distributionSupported)) {
        const auto requestedAt = EpochMs();
        IADLXSystemMetricsPtr metrics;
        const ADLX_RESULT currentResult = perf->GetCurrentSystemMetrics(&metrics);
        Result("GetCurrentSystemMetrics", currentResult);
        auto metrics1 = Extension<IADLXSystemMetrics1>(metrics.GetPtr(),
            "QueryInterface.SystemMetrics1", -1);
        std::cout << "{\"record\":\"system_sample\",\"requested_epoch_ms\":" << requestedAt
                  << ",\"result\":" << currentResult << ",\"metrics\":{";
        bool first = true;
        if (cpuSupported) MetricValue<adlx_double>("cpu_usage_percent", metrics.GetPtr(), &IADLXSystemMetrics::CPUUsage, first);
        if (shiftSupported) MetricValue<adlx_int>("smart_shift", metrics.GetPtr(), &IADLXSystemMetrics::SmartShift, first);
        if (distributionSupported) {
            if (!first) std::cout << ',';
            adlx_int apuValue = 0, gpuValue = 0, apuLimit = 0, gpuLimit = 0, totalLimit = 0;
            const ADLX_RESULT distributionResult = metrics1 ? metrics1->PowerDistribution(
                &apuValue, &gpuValue, &apuLimit, &gpuLimit, &totalLimit) : ADLX_UNKNOWN_INTERFACE;
            std::cout << "\"power_distribution\":{\"result\":" << distributionResult
                      << ",\"units\":\"driver_units_unverified\",\"values\":";
            if (ADLX_SUCCEEDED(distributionResult)) {
                std::cout << "{\"apu_shift_value\":" << apuValue << ",\"gpu_shift_value\":" << gpuValue
                          << ",\"apu_shift_limit\":" << apuLimit << ",\"gpu_shift_limit\":" << gpuLimit
                          << ",\"total_shift_limit\":" << totalLimit << '}';
            } else std::cout << "null";
            std::cout << '}';
        }
        std::cout << "},\"completed_epoch_ms\":" << EpochMs() << "}\n";
    }
    // Unsupported capabilities are valid discovery results; every API result is retained.
    return 0;
}

int main(int argc, char** argv) {
    if (argc > 1) {
        std::cerr << "halogen_adlx_power_probe\nOne read-only support/readback acquisition; no setters or tracking.\n";
        return argc == 2 && std::string(argv[1]) == "--help" ? 0 : 2;
    }
    std::cout << std::setprecision(12);
    ADLXHelper helper;
    const ADLX_RESULT initializeResult = helper.Initialize();
    std::cout << "{\"record\":\"initialize\",\"read_only\":true,\"result\":" << initializeResult
              << ",\"adlx_version\":" << Json(helper.QueryVersion())
              << ",\"adlx_full_version\":" << helper.QueryFullVersion()
              << ",\"sdk_full_version\":" << ADLX_FULL_VERSION << "}\n";
    int exitCode = 3;
    if (ADLX_SUCCEEDED(initializeResult) && helper.GetSystemServices()) exitCode = ProbePower(helper);
    // All ProbePower smart pointers leave scope before Terminate, as in the GPU probe.
    const ADLX_RESULT terminateResult = helper.Terminate();
    Result("Terminate", terminateResult);
    if (ADLX_FAILED(terminateResult) && exitCode == 0) exitCode = 6;
    return exitCode;
}
