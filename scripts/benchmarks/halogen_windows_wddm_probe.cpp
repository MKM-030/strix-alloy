// One read-only acquisition of the exact retained native Windows adapter.
// ROOT owns execution, a hard outer deadline, the 22/18-GiB admission/reserve
// guard, output capture and preservation of the idle colleague server.
// No device/queue creation, escape, HSA load, tuning, retry or frequency setter.
// SDK engine/memory clock fields cannot establish DCLK/FCLK or fabric hold.
#include <windows.h>
#include <winternl.h>
#include <d3dkmthk.h>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>

static_assert(sizeof(void*) == 8, "Build the reviewed x64 target");
static_assert(sizeof(NTSTATUS) == 4, "Exact signed 32-bit NTSTATUS required");

namespace {
constexpr LONG kLuidHigh = 0;
constexpr DWORD kLuidLow = 0x00011884;
constexpr UINT kPhysicalAdapter = 0;
constexpr UINT kNodeOrdinal = 2; // Retained PDH eng_2 is a lead, not a proved join.
constexpr UINT kVendor = 0x1002;
constexpr UINT kDevice = 0x1586;
constexpr std::size_t kOutputCeiling = 128 * 1024;
constexpr LONGLONG kDeadlineSeconds = 10;

struct Stamp {
    LONGLONG qpc = 0;
    std::uint64_t filetime100ns = 0;
    bool qpcValid = false;
};

Stamp Now() {
    Stamp result;
    LARGE_INTEGER qpc{};
    FILETIME utc{};
    result.qpcValid = QueryPerformanceCounter(&qpc) != FALSE;
    result.qpc = qpc.QuadPart;
    GetSystemTimePreciseAsFileTime(&utc);
    result.filetime100ns = (static_cast<std::uint64_t>(utc.dwHighDateTime) << 32) | utc.dwLowDateTime;
    return result;
}

struct Call {
    bool attempted = false;
    NTSTATUS status = 0;
    Stamp before{}, after{};
    const char* skipped = "not_reached";
    bool Ok() const { return attempted && status == 0; }
};

struct Context {
    LONGLONG deadline = 0;
    bool ClockReady() const {
        LARGE_INTEGER now{};
        return QueryPerformanceCounter(&now) != FALSE && now.QuadPart <= deadline;
    }
};

template<class Function>
Call Invoke(const Context& context, Function function, bool eligible = true,
            const char* skipReason = "prerequisite_unavailable", bool cleanup = false) {
    Call result;
    if (!eligible) {
        result.skipped = skipReason;
        return result;
    }
    if (!cleanup && !context.ClockReady()) {
        result.skipped = "internal_deadline_or_clock_unavailable";
        return result;
    }
    result.attempted = true;
    result.skipped = nullptr;
    result.before = Now();
    result.status = function();
    result.after = Now();
    return result;
}

template<class Buffer>
Call Query(const Context& context, D3DKMT_HANDLE adapter, KMTQUERYADAPTERINFOTYPE type,
           Buffer& buffer, bool eligible = true, const char* skipReason = "prerequisite_unavailable") {
    D3DKMT_QUERYADAPTERINFO request{};
    request.hAdapter = adapter;
    request.Type = type;
    request.pPrivateDriverData = &buffer;
    request.PrivateDriverDataSize = static_cast<UINT>(sizeof buffer);
    return Invoke(context, [&request] { return D3DKMTQueryAdapterInfo(&request); }, eligible, skipReason);
}

// Only these three graphics API entry points are referenced by this collector.
class Adapter {
public:
    D3DKMT_OPENADAPTERFROMLUID request{};
    Call open{}, close{};
    Adapter() { request.AdapterLuid.HighPart = kLuidHigh; request.AdapterLuid.LowPart = kLuidLow; }
    void Open(const Context& context) {
        open = Invoke(context, [this] { return D3DKMTOpenAdapterFromLuid(&request); });
    }
    void Close(const Context& context) {
        if (!request.hAdapter || close.attempted) return;
        D3DKMT_CLOSEADAPTER value{};
        value.hAdapter = request.hAdapter;
        close = Invoke(context, [&value] { return D3DKMTCloseAdapter(&value); }, true, nullptr, true);
        request.hAdapter = 0; // One close attempt; a failed close remains unqualified.
    }
    ~Adapter() {
        // Handles a C++ failure before the explicit close; no second close call.
        if (request.hAdapter && !close.attempted) {
            D3DKMT_CLOSEADAPTER value{};
            value.hAdapter = request.hAdapter;
            const NTSTATUS status = D3DKMTCloseAdapter(&value);
            (void)status;
        }
    }
};

void Json(std::ostream& out, const char* value) {
    out << '"';
    for (const unsigned char* p = reinterpret_cast<const unsigned char*>(value); *p; ++p) {
        if (*p == '"' || *p == '\\') out << '\\' << static_cast<char>(*p);
        else if (*p < 0x20) out << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                              << static_cast<unsigned>(*p) << std::dec;
        else out << static_cast<char>(*p);
    }
    out << '"';
}

template<std::size_t Size>
void WideJson(std::ostream& out, const WCHAR (&value)[Size]) {
    // Fixed SDK array bound, including nonterminated driver strings. UTF-16
    // code units are escaped directly; valid surrogate pairs remain pairs.
    out << '"';
    for (std::size_t i = 0; i < Size && value[i]; ++i) {
        const unsigned code = static_cast<unsigned>(value[i]);
        if (code == '"' || code == '\\') out << '\\' << static_cast<char>(code);
        else if (code >= 0x20 && code < 0x7f) out << static_cast<char>(code);
        else out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << code << std::dec;
    }
    out << '"';
}

void StampJson(std::ostream& out, const Stamp& stamp) {
    out << "{\"qpc_ticks\":" << stamp.qpc << ",\"qpc_valid\":" << (stamp.qpcValid ? "true" : "false")
        << ",\"utc_filetime_100ns\":" << stamp.filetime100ns << '}';
}

void CallJson(std::ostream& out, const Call& call) {
    out << "{\"attempted\":" << (call.attempted ? "true" : "false") << ",\"ntstatus_signed_i32\":";
    if (call.attempted) out << static_cast<std::int32_t>(call.status); else out << "null";
    out << ",\"ntstatus_hex_u32\":";
    if (call.attempted) out << "\"0x" << std::hex << std::setw(8) << std::setfill('0')
                           << static_cast<std::uint32_t>(call.status) << std::dec << '"';
    else out << "null";
    out << ",\"status_success\":" << (call.Ok() ? "true" : "false") << ",\"supported\":";
    if (call.Ok()) out << "true";
    else if (call.attempted && static_cast<std::uint32_t>(call.status) == 0xc00000bbu) out << "false";
    else out << "null";
    out << ",\"skipped_reason\":";
    if (call.skipped) Json(out, call.skipped); else out << "null";
    out << ",\"host_before\":"; StampJson(out, call.before);
    out << ",\"host_after\":"; StampJson(out, call.after);
    out << '}';
}

void Record(std::ostream& out, const char* name, const Call& call, std::size_t bytes,
            bool inputQualified = true) {
    Json(out, name);
    out << ":{\"sdk_buffer_bytes\":" << bytes << ",\"call\":";
    CallJson(out, call);
    out << ",\"fields_qualified\":" << (call.Ok() && inputQualified ? "true" : "false")
        << ",\"fields\":";
}

int Acquire() {
    LARGE_INTEGER frequency{};
    const Stamp start = Now();
    const bool clockReady = QueryPerformanceFrequency(&frequency) != FALSE && frequency.QuadPart > 0
        && frequency.QuadPart <= (std::numeric_limits<LONGLONG>::max)() / kDeadlineSeconds
        && start.qpcValid && start.qpc <= (std::numeric_limits<LONGLONG>::max)() - frequency.QuadPart * kDeadlineSeconds;
    Context context{clockReady ? start.qpc + frequency.QuadPart * kDeadlineSeconds : 0};
    Adapter adapter;
    if (clockReady) adapter.Open(context);
    const bool opened = adapter.open.Ok() && adapter.request.hAdapter != 0;
    const D3DKMT_HANDLE handle = adapter.request.hAdapter;
    D3DKMT_PHYSICAL_ADAPTER_COUNT count{};
    D3DKMT_ADAPTERTYPE type{};
    D3DKMT_QUERY_DEVICE_IDS ids{};
    ids.PhysicalAdapterIndex = kPhysicalAdapter;
    D3DKMT_DRIVERVERSION version{};
    D3DKMT_DRIVER_DESCRIPTION description{};
    const Call countCall = Query(context, handle, KMTQAITYPE_PHYSICALADAPTERCOUNT, count, opened);
    const Call typeCall = Query(context, handle, KMTQAITYPE_ADAPTERTYPE, type, opened);
    const Call idsCall = Query(context, handle, KMTQAITYPE_PHYSICALADAPTERDEVICEIDS, ids,
        opened && countCall.Ok() && count.Count > kPhysicalAdapter && count.Count <= 64,
        "physical_adapter_count_unqualified");
    const Call versionCall = Query(context, handle, KMTQAITYPE_DRIVERVERSION, version, opened);
    const bool identity = opened && countCall.Ok() && count.Count > kPhysicalAdapter && count.Count <= 64
        && typeCall.Ok() && !type.SoftwareDevice && idsCall.Ok() && ids.PhysicalAdapterIndex == kPhysicalAdapter
        && ids.DeviceIds.VendorID == kVendor && ids.DeviceIds.DeviceID == kDevice;
    const Call descriptionCall = Query(context, handle, KMTQAITYPE_DRIVER_DESCRIPTION, description,
        identity && versionCall.Ok() && version >= KMT_DRIVERVERSION_WDDM_2_6,
        "identity_or_WDDM_2_6_unqualified");
    D3DKMT_NODEMETADATA node{};
    node.NodeOrdinalAndAdapterIndex = (kPhysicalAdapter << 16) | kNodeOrdinal;
    const Call nodeCall = Query(context, handle, KMTQAITYPE_NODEMETADATA, node,
        identity && versionCall.Ok() && version >= KMT_DRIVERVERSION_WDDM_2_0,
        "identity_or_WDDM_2_0_unqualified");
    const bool nodeQualified = nodeCall.Ok()
        && node.NodeOrdinalAndAdapterIndex == ((kPhysicalAdapter << 16) | kNodeOrdinal);
    D3DKMT_SEGMENTSIZEINFO segments{};
    const Call segmentsCall = Query(context, handle, KMTQAITYPE_GETSEGMENTSIZE, segments, identity,
        "adapter_identity_unqualified");
    D3DKMT_SEGMENTGROUPSIZEINFO groups{};
    groups.PhysicalAdapterIndex = kPhysicalAdapter;
    const Call groupsCall = Query(context, handle, KMTQAITYPE_GETSEGMENTGROUPSIZE, groups,
        identity && versionCall.Ok() && version >= KMT_DRIVERVERSION_WDDM_2_2,
        "identity_or_WDDM_2_2_unqualified");
    const bool perfEligible = identity && versionCall.Ok() && version >= KMT_DRIVERVERSION_WDDM_2_4;
    D3DKMT_ADAPTER_PERFDATACAPS caps{};
    caps.PhysicalAdapterIndex = kPhysicalAdapter;
    const Call capsCall = Query(context, handle, KMTQAITYPE_ADAPTERPERFDATA_CAPS, caps, perfEligible,
        "identity_or_WDDM_2_4_unqualified");
    const Stamp sampleStart = Now();
    D3DKMT_NODE_PERFDATA engine{};
    engine.NodeOrdinal = kNodeOrdinal;
    engine.PhysicalAdapterIndex = kPhysicalAdapter;
    const Call engineCall = Query(context, handle, KMTQAITYPE_NODEPERFDATA, engine, perfEligible && nodeQualified,
        "identity_WDDM_2_4_or_node_metadata_unqualified");
    D3DKMT_ADAPTER_PERFDATA perf{};
    perf.PhysicalAdapterIndex = kPhysicalAdapter;
    const Call perfCall = Query(context, handle, KMTQAITYPE_ADAPTERPERFDATA, perf, perfEligible,
        "identity_or_WDDM_2_4_unqualified");
    const bool engineQualified = engineCall.Ok() && engine.NodeOrdinal == kNodeOrdinal
        && engine.PhysicalAdapterIndex == kPhysicalAdapter;
    const bool perfQualified = perfCall.Ok() && perf.PhysicalAdapterIndex == kPhysicalAdapter;
    const Stamp sampleEnd = Now();
    adapter.Close(context);
    const Stamp end = Now();
    const bool closed = opened && adapter.close.Ok();
    const bool dynamicInputMismatch = (engineCall.Ok() && !engineQualified) || (perfCall.Ok() && !perfQualified);
    const bool acquisitionQualified = clockReady && identity && nodeQualified && closed && !dynamicInputMismatch;
    std::ostringstream out;
    out << "{\"schema\":\"halogen.windows-wddm-readonly.v1\",\"samples_requested\":1,\"samples_acquired\":"
        << (engineCall.attempted || perfCall.attempted ? 1 : 0)
        << ",\"acquisition_qualified\":" << (acquisitionQualified ? "true" : "false")
        << ",\"adapter_identity_verified\":" << (identity ? "true" : "false")
        << ",\"node_metadata_qualified\":" << (nodeQualified ? "true" : "false")
        << ",\"adapter_close_qualified\":" << (closed ? "true" : "false")
        << ",\"engine_frequency_available\":" << (engineQualified ? "true" : "false")
        << ",\"adapter_performance_available\":" << (perfQualified ? "true" : "false")
        << ",\"dynamic_returned_input_mismatch\":" << (dynamicInputMismatch ? "true" : "false")
        << ",\"expected_luid\":{\"high_i32\":0,\"low_u32\":71812,\"hex\":\"0x00000000_0x00011884\"}"
        << ",\"expected_vendor_u32\":4098,\"expected_device_u32\":5510,\"physical_adapter_index\":0,\"node_ordinal\":2"
        << ",\"PDH_engine_to_node_mapping_qualified\":false,\"driver_version_units\":\"WDDM_enum_not_package_version\""
        << ",\"support_rule\":\"STATUS_SUCCESS_plus_unchanged_requested_indices_qualifies_fields;_STATUS_NOT_SUPPORTED_is_false;_other_failure_is_unknown\""
        << ",\"host_qpc_frequency_hz\":" << frequency.QuadPart << ",\"clock_ready\":" << (clockReady ? "true" : "false")
        << ",\"host_start\":"; StampJson(out, start);
    out << ",\"host_end\":"; StampJson(out, end);
    out << ",\"sample_host_start\":"; StampJson(out, sampleStart);
    out << ",\"sample_host_end\":"; StampJson(out, sampleEnd);
    out << ",\"calls\":{\"open\":"; CallJson(out, adapter.open);
    out << ",\"close\":"; CallJson(out, adapter.close);
    out << "},\"queries\":{";
    Record(out, "physical_adapter_count", countCall, sizeof count);
    if (countCall.Ok()) out << "{\"count\":" << count.Count << '}'; else out << "null";
    out << "},";
    Record(out, "adapter_type", typeCall, sizeof type);
    if (typeCall.Ok()) out << "{\"flags_raw_u32\":" << type.Value << ",\"software_device\":"
        << (type.SoftwareDevice ? "true" : "false") << '}'; else out << "null";
    out << "},";
    Record(out, "physical_adapter_device_ids", idsCall, sizeof ids, ids.PhysicalAdapterIndex == kPhysicalAdapter);
    if (idsCall.Ok()) out << "{\"physical_adapter_index\":" << ids.PhysicalAdapterIndex
        << ",\"vendor_id_u32\":" << ids.DeviceIds.VendorID << ",\"device_id_u32\":" << ids.DeviceIds.DeviceID
        << ",\"subvendor_id_u32\":" << ids.DeviceIds.SubVendorID << ",\"subsystem_id_u32\":" << ids.DeviceIds.SubSystemID
        << ",\"revision_id_u32\":" << ids.DeviceIds.RevisionID << ",\"bus_type_raw_u32\":" << ids.DeviceIds.BusType << '}';
    else out << "null";
    out << "},";
    Record(out, "driver_model_version", versionCall, sizeof version);
    if (versionCall.Ok()) out << "{\"WDDM_enum\":" << static_cast<unsigned>(version) << '}'; else out << "null";
    out << "},";
    Record(out, "driver_description", descriptionCall, sizeof description);
    if (descriptionCall.Ok()) { out << "{\"description\":"; WideJson(out, description.DriverDescription); out << '}'; }
    else out << "null";
    out << "},";
    Record(out, "node_metadata", nodeCall, sizeof node, nodeQualified);
    if (nodeCall.Ok()) {
        out << "{\"packed_node_and_physical_index_u32\":" << node.NodeOrdinalAndAdapterIndex
            << ",\"engine_type_raw_u32\":" << static_cast<unsigned>(node.NodeData.EngineType)
            << ",\"friendly_name\":"; WideJson(out, node.NodeData.FriendlyName);
        out << ",\"flags_raw_u32\":" << node.NodeData.Flags.Value << ",\"gpu_mmu_supported\":"
            << (node.NodeData.GpuMmuSupported ? "true" : "false") << ",\"io_mmu_supported\":"
            << (node.NodeData.IoMmuSupported ? "true" : "false") << '}';
    } else out << "null";
    out << "},";
    Record(out, "segment_sizes", segmentsCall, sizeof segments);
    if (segmentsCall.Ok()) out << "{\"dedicated_video_bytes\":" << segments.DedicatedVideoMemorySize
        << ",\"dedicated_system_bytes\":" << segments.DedicatedSystemMemorySize
        << ",\"shared_system_bytes\":" << segments.SharedSystemMemorySize << '}'; else out << "null";
    out << "},";
    Record(out, "segment_group_sizes", groupsCall, sizeof groups, groups.PhysicalAdapterIndex == kPhysicalAdapter);
    if (groupsCall.Ok()) out << "{\"physical_adapter_index\":" << groups.PhysicalAdapterIndex
        << ",\"local_bytes\":" << groups.LocalMemory << ",\"nonlocal_bytes\":" << groups.NonLocalMemory
        << ",\"nonbudget_bytes\":" << groups.NonBudgetMemory
        << ",\"legacy_dedicated_video_bytes\":" << groups.LegacyInfo.DedicatedVideoMemorySize
        << ",\"legacy_dedicated_system_bytes\":" << groups.LegacyInfo.DedicatedSystemMemorySize
        << ",\"legacy_shared_system_bytes\":" << groups.LegacyInfo.SharedSystemMemorySize << '}'; else out << "null";
    out << "},";
    Record(out, "adapter_performance_caps", capsCall, sizeof caps, caps.PhysicalAdapterIndex == kPhysicalAdapter);
    if (capsCall.Ok()) out << "{\"physical_adapter_index\":" << caps.PhysicalAdapterIndex
        << ",\"max_memory_bandwidth_bytes_per_second\":" << caps.MaxMemoryBandwidth
        << ",\"max_pcie_bandwidth_bytes_per_second\":" << caps.MaxPCIEBandwidth << ",\"max_fan_rpm\":" << caps.MaxFanRPM
        << ",\"temperature_damage_deci_celsius\":" << caps.TemperatureMax
        << ",\"temperature_warning_deci_celsius\":" << caps.TemperatureWarning << '}'; else out << "null";
    out << "},";
    Record(out, "node_performance", engineCall, sizeof engine, engineQualified);
    if (engineCall.Ok()) out << "{\"node_ordinal\":" << engine.NodeOrdinal << ",\"physical_adapter_index\":" << engine.PhysicalAdapterIndex
        << ",\"frequency_hz\":" << engine.Frequency << ",\"max_normal_frequency_hz\":" << engine.MaxFrequency
        << ",\"max_overclocked_frequency_hz\":" << engine.MaxFrequencyOC << ",\"voltage_mv\":" << engine.Voltage
        << ",\"max_normal_voltage_mv\":" << engine.VoltageMax << ",\"max_overclocked_voltage_mv\":" << engine.VoltageMaxOC
        << ",\"max_transition_latency_100ns\":" << engine.MaxTransitionLatency << '}'; else out << "null";
    out << "},";
    Record(out, "adapter_performance", perfCall, sizeof perf, perfQualified);
    if (perfCall.Ok()) out << "{\"physical_adapter_index\":" << perf.PhysicalAdapterIndex
        << ",\"memory_frequency_hz\":" << perf.MemoryFrequency << ",\"max_normal_memory_frequency_hz\":" << perf.MaxMemoryFrequency
        << ",\"max_overclocked_memory_frequency_hz\":" << perf.MaxMemoryFrequencyOC
        << ",\"memory_transferred_bytes_provider_interval\":" << perf.MemoryBandwidth
        << ",\"pcie_transferred_bytes_provider_interval\":" << perf.PCIEBandwidth << ",\"fan_rpm\":" << perf.FanRPM
        << ",\"power_tenths_of_percentage\":" << perf.Power << ",\"temperature_deci_celsius\":" << perf.Temperature
        << ",\"power_state_override_raw_u8\":" << static_cast<unsigned>(perf.PowerStateOverride) << '}'; else out << "null";
    out << "}},\"limits\":{\"synchronous_driver_calls_have_no_internal_interrupt\":true,\"caller_outer_deadline_required\":true,"
        << "\"internal_deadline_seconds\":10,\"sample_count_fixed\":1,\"output_ceiling_bytes\":131072,"
        << "\"host_bounds_are_not_provider_interval_bounds\":true,\"maximum_frequency_is_not_a_power_limit\":true,"
        << "\"power_field_is_not_watts\":true,\"segment_sizes_are_not_BIOS_UMA_reservation_proof\":true,"
        << "\"fabric_clock_observed\":false,\"fabric_clock_hold_proved\":false,\"memory_frequency_is_fabric_clock\":false,"
        << "\"frequency_hold_setter_called\":false,\"GPU_NPU_overlap_qualified\":false,\"private_power_policy_observed\":false,"
        << "\"settings_changed\":false,\"tuning_claim\":false,\"throughput_cause_established\":false}}\n";
    const std::string output = out.str();
    if (output.size() > kOutputCeiling) { std::cerr << "WDDM JSON output ceiling exceeded\n"; return 3; }
    std::cout.write(output.data(), static_cast<std::streamsize>(output.size()));
    std::cout.flush();
    if (!std::cout) return 3;
    // Unsupported optional telemetry remains a valid discovery result, not zero.
    return acquisitionQualified ? 0 : 1;
}
} // namespace

int main(int argc, char** argv) {
    if (argc != 1) {
        std::cerr << "halogen_windows_wddm_probe: one exact-LUID read-only sample; no arguments\n";
        return argc == 2 && std::string(argv[1]) == "--help" ? 0 : 2;
    }
    try { return Acquire(); }
    catch (const std::exception& error) { std::cerr << "WDDM collector failed: " << error.what() << '\n'; return 3; }
    catch (...) { std::cerr << "WDDM collector failed\n"; return 3; }
}
