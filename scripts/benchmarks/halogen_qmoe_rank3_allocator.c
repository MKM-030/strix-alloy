/* Coherent rank3 activation/output variant of the retained diagnostic host.
 * The pinned AMDQMoEKernel reads activation shape[2]; x/y are [1,1,WIDTH].
 * Router remains [1,EXPERTS]. Only the new exported helper is changed.
 * Root owns compilation, artifact admission, native calls and measurements.
 */
/* Separate diagnostic retained allocator-session candidate; not a repair claim.
 * Source alignment with OGA v0.14.0 model.cpp:343-417:
 * https://github.com/microsoft/onnxruntime-genai/blob/v0.14.0/src/models/model.cpp#L343-L417
 * Keep the exact 96-byte graph and fresh default options with empty EP options.
 * A function-local holder matches one bounded invocation, not OGA global
 * cross-model persistence, environment CPU arena or optional provider shutdown.
 * Root owns pinned build, WinML bootstrap, exclusive guard and admission.
 * A direct native refresh callback runs on the ordinary invoking host thread
 * after all session/tensor/binding setup and before each RunWithBinding.
 * No callback, collector refresh or native invocation is qualified by source.
 */
#define WIN32_LEAN_AND_MEAN
#define _CRT_SECURE_NO_WARNINGS
#include <windows.h>
#include <stdio.h>
#include <stddef.h>
#include <string.h>
#include <wchar.h>
#include "onnxruntime_c_api.h"

#if !defined(_WIN32) || !defined(_M_X64)
#error This diagnostic helper requires native Windows x64.
#endif
#if ORT_API_VERSION != 29
#error This diagnostic helper requires the pinned ORT CAPI29 headers.
#endif

#define LIGHT "RyzenAILightExecutionProvider"
#define WIDTH 2560
#define EXPERTS 512
#define CALLS 2
#define OUT_BYTES (WIDTH * sizeof(uint16_t))

/* Direct function pointer into the separately retained collector DLL. The
 * caller must keep that DLL loaded and pass its __cdecl refresh_capture export;
 * no Python callback/trampoline, concurrent Run, handler or payload inspection.
 */
typedef DWORD (__cdecl *QmoeCaptureRefreshCallback)(void);
C_ASSERT(sizeof(QmoeCaptureRefreshCallback) == 8);

/* Exact upstream g_trivial_model; creates the allocator holder, never Run. */
static const unsigned char oga_trivial_model[96] = {
  0x08, 0x0a, 0x12, 0x01, 0x61, 0x3a, 0x53, 0x0a, 0x38, 0x12, 0x06, 0x76, 0x61, 0x6c, 0x75, 0x65,
  0x73, 0x22, 0x08, 0x43, 0x6f, 0x6e, 0x73, 0x74, 0x61, 0x6e, 0x74, 0x2a, 0x24, 0x0a, 0x05, 0x76,
  0x61, 0x6c, 0x75, 0x65, 0x2a, 0x18, 0x08, 0x01, 0x10, 0x01, 0x42, 0x0c, 0x63, 0x6f, 0x6e, 0x73,
  0x74, 0x5f, 0x74, 0x65, 0x6e, 0x73, 0x6f, 0x72, 0x4a, 0x04, 0x00, 0x00, 0x00, 0x00, 0xa0, 0x01,
  0x04, 0x12, 0x01, 0x62, 0x62, 0x14, 0x0a, 0x06, 0x76, 0x61, 0x6c, 0x75, 0x65, 0x73, 0x12, 0x0a,
  0x0a, 0x08, 0x08, 0x01, 0x12, 0x04, 0x0a, 0x02, 0x08, 0x01, 0x42, 0x04, 0x0a, 0x00, 0x10, 0x15
};


typedef struct QmoeRetainedAllocatorReceipt {
  uint32_t schema;
  uint32_t api_version;
  uint32_t session_creations;
  uint32_t allocator_acquired;
  uint32_t allocator_type;
  int32_t allocator_mem_type;
  uint32_t allocator_device_type;
  uint32_t calls_attempted;
  uint32_t calls_completed;
  uint32_t zero_outputs;
  uint32_t cleanup_completed;
  uint32_t provider_unregistered;
  uint32_t session_creation_attempts;
  uint32_t allocator_session_created;
  uint32_t allocator_session_released;
  uint64_t qpc_frequency;
  uint64_t call_ticks[CALLS];
} QmoeRetainedAllocatorReceipt;
C_ASSERT(sizeof(QmoeRetainedAllocatorReceipt) == 88);
C_ASSERT(offsetof(QmoeRetainedAllocatorReceipt, qpc_frequency) == 64);
C_ASSERT(offsetof(QmoeRetainedAllocatorReceipt, call_ticks) == 72);

static void stage(const char* name) {
  printf("QMOE_CAPI_STAGE %s\n", name);
  fflush(stdout);
}

static void set_error(char* error, size_t capacity, const char* where, const char* message) {
  if (capacity == 0 || error == NULL) return;
  snprintf(error, capacity, "%s: %s", where, message);
  error[capacity - 1] = '\0';
}

/* Use the actual allocator's memory description to establish CPU addressing.
 * Session allocator acquisition must match OGA's exact Cpu/default/device key.
 * Unsupported geometry or memory type fails before any payload dereference.
 */
static OrtStatus* validate_model_io(const OrtApi* api, OrtSession* session, int output,
                                  size_t index, ONNXTensorElementDataType expected_type,
                                  size_t expected_dimensions, const int64_t* expected_shape,
                                  int* valid) {
  OrtTypeInfo* type_info = NULL;
  const OrtTensorTypeAndShapeInfo* tensor_info = NULL;
  OrtStatus* status;
  ONNXTensorElementDataType type = ONNX_TENSOR_ELEMENT_DATA_TYPE_UNDEFINED;
  size_t dimensions = 0, dimension;
  int64_t shape[3] = {0, 0, 0};
  *valid = 0;
  if (expected_dimensions == 0 || expected_dimensions > 3 || expected_shape == NULL)
    return NULL;
  status = output ? api->SessionGetOutputTypeInfo(session, index, &type_info)
                  : api->SessionGetInputTypeInfo(session, index, &type_info);
  if (status) return status;
  status = api->CastTypeInfoToTensorInfo(type_info, &tensor_info);
  if (!status && tensor_info == NULL) {
    api->ReleaseTypeInfo(type_info);
    return NULL;
  }
  if (!status) status = api->GetTensorElementType(tensor_info, &type);
  if (!status) status = api->GetDimensionsCount(tensor_info, &dimensions);
  if (!status && dimensions == expected_dimensions)
    status = api->GetDimensions(tensor_info, shape, expected_dimensions);
  if (!status && dimensions == expected_dimensions && type == expected_type) {
    *valid = 1;
    for (dimension = 0; dimension < expected_dimensions; ++dimension) {
      if (shape[dimension] != expected_shape[dimension]) {
        *valid = 0;
        break;
      }
    }
  }
  api->ReleaseTypeInfo(type_info);
  return status;
}

/* Inputs are verified absolute paths supplied by the existing root-owned guard.
 * Root must verify the frozen graph/header/bank, DLL and complete ORT stage
 * before calling; bootstrap WinML, set DLL search directories, and arm its
 * native fault collector. output_receipts is exactly CALLS*OUT_BYTES bytes.
 * All output data is synthetic zero-bank output, not real model payload.
 */
__declspec(dllexport) int __cdecl qmoe_rank3_allocator_run(
    const wchar_t* ort_path, const wchar_t* ep_path, const wchar_t* model_path,
    const char* model_root_utf8, const char* header_path_utf8,
    const wchar_t* profile_prefix, QmoeRetainedAllocatorReceipt* receipt,
    void* output_receipts, size_t output_capacity, char* error, size_t error_capacity,
    QmoeCaptureRefreshCallback refresh_callback) {
  HMODULE ort_module = NULL;
  const OrtApiBase* (ORT_API_CALL * get_api_base)(void) = NULL;
  const OrtApiBase* base = NULL;
  const OrtApi* api = NULL;
  OrtEnv* env = NULL;
  OrtSessionOptions* options = NULL;
  OrtSession* session = NULL;
  OrtSession* allocator_session = NULL;
  OrtSessionOptions* allocator_options = NULL;
  OrtMemoryInfo* memory_info = NULL;
  OrtAllocator* allocator = NULL;
  OrtAllocator* default_allocator = NULL;
  OrtValue* x = NULL;
  OrtValue* router = NULL;
  OrtValue* output = NULL;
  OrtIoBinding* binding = NULL;
  OrtStatus* status = NULL;
  const OrtEpDevice* const* devices = NULL;
  const OrtEpDevice* chosen = NULL;
  const OrtMemoryInfo* actual_info = NULL;
  const char* actual_name = NULL;
  char* profile_path = NULL;
  size_t count = 0, i, input_count = 0, output_count = 0;
  int registered = 0, code = 1, valid = 0;
  OrtAllocatorType allocator_type = OrtInvalidAllocator;
  OrtMemType mem_type = OrtMemTypeDefault;
  OrtMemoryInfoDeviceType device_type = OrtMemoryInfoDeviceType_NPU;
  uint16_t* xp = NULL;
  uint16_t* yp = NULL;
  float* rp = NULL;
  const int64_t x_shape[3] = {1, 1, WIDTH};
  const int64_t router_shape[2] = {1, EXPERTS};
  const char* keys[4] = {"external_data_file", "hybrid_opt_token_backend",
                        "hybrid_opt_qmoe_dynamic_experts", "hybrid_opt_qmoe_num_dynamic_layers"};
  const char* values[4];
  LARGE_INTEGER frequency, started, finished;
  wchar_t loaded_path[32768];
  DWORD refresh_status;

#define CHECK(call) do { status = (call); if (status) { \
  set_error(error, error_capacity, #call, api->GetErrorMessage(status)); \
  api->ReleaseStatus(status); status = NULL; goto cleanup; } } while (0)
#define REQUIRE(test, message) do { if (!(test)) { \
  set_error(error, error_capacity, "contract", (message)); goto cleanup; } } while (0)

  if (!receipt || !output_receipts || output_capacity != CALLS * OUT_BYTES ||
      !error || error_capacity < 256 || !ort_path || !ep_path || !model_path ||
      !model_root_utf8 || !header_path_utf8 || !profile_prefix || !refresh_callback) return 2;
  memset(receipt, 0, sizeof(*receipt));
  memset(output_receipts, 0x7F, output_capacity);
  error[0] = '\0';
  receipt->schema = 2;
  receipt->api_version = ORT_API_VERSION;
  stage("load_pinned_ort");
  ort_module = LoadLibraryExW(ort_path, NULL,
      LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
  REQUIRE(ort_module, "LoadLibraryExW of pinned ORT failed");
  REQUIRE(GetModuleFileNameW(ort_module, loaded_path, 32768) != 0 &&
          _wcsicmp(loaded_path, ort_path) == 0, "Loaded ORT path differs from pinned absolute path");
  *(FARPROC*)&get_api_base = GetProcAddress(ort_module, "OrtGetApiBase");
  REQUIRE(get_api_base, "Pinned ORT has no OrtGetApiBase export");
  base = get_api_base();
  REQUIRE(base && strcmp(base->GetVersionString(), "1.29.0") == 0, "ORT version is not 1.29.0");
  api = base->GetApi(ORT_API_VERSION);
  REQUIRE(api, "ORT CAPI29 unavailable");
  REQUIRE(QueryPerformanceFrequency(&frequency), "QPC unavailable");
  receipt->qpc_frequency = (uint64_t)frequency.QuadPart;
  CHECK(api->CreateEnv(ORT_LOGGING_LEVEL_WARNING, "halogen-qmoe-rank3-allocator", &env));
  stage("register_pinned_light");
  CHECK(api->RegisterExecutionProviderLibrary(env, LIGHT, ep_path));
  registered = 1;
  CHECK(api->GetEpDevices(env, &devices, &count));
  for (i = 0; i < count; ++i) {
    if (strcmp(api->EpDevice_EpName(devices[i]), LIGHT) == 0 &&
        api->HardwareDevice_Type(api->EpDevice_Device(devices[i])) == OrtHardwareDeviceType_NPU) {
      REQUIRE(chosen == NULL, "Multiple Light NPU devices found");
      chosen = devices[i];
    }
  }
  REQUIRE(chosen, "Pinned Light NPU device not found");
  values[0] = header_path_utf8;
  values[1] = "npu";
  values[2] = values[3] = "0";
  CHECK(api->CreateSessionOptions(&options));
  CHECK(api->SetIntraOpNumThreads(options, 1));
  CHECK(api->SetInterOpNumThreads(options, 1));
  CHECK(api->AddSessionConfigEntry(options, "model_root", model_root_utf8));
  CHECK(api->EnableProfiling(options, profile_prefix));
  CHECK(api->SessionOptionsAppendExecutionProvider_V2(options, env, &chosen, 1, keys, values, 4));
  CHECK(api->AddSessionConfigEntry(options, "session.disable_cpu_ep_fallback", "1"));
  CHECK(api->RegisterCustomOpsLibrary_V2(options, ep_path));
  /* Fresh defaults: do not clone strict QMoEBf/profile/thread/bank options. */
  CHECK(api->CreateSessionOptions(&allocator_options));
  CHECK(api->AddSessionConfigEntry(allocator_options, "model_root", model_root_utf8));
  CHECK(api->SessionOptionsAppendExecutionProvider_V2(allocator_options, env, &chosen, 1, NULL, NULL, 0));
  CHECK(api->RegisterCustomOpsLibrary_V2(allocator_options, ep_path));
  CHECK(api->SetSessionLogSeverityLevel(allocator_options, ORT_LOGGING_LEVEL_ERROR));
  stage("retained_allocator_session_admission");
  ++receipt->session_creation_attempts;
  CHECK(api->CreateSessionFromArray(env, oga_trivial_model, sizeof(oga_trivial_model),
                                   allocator_options, &allocator_session));
  ++receipt->session_creations;
  receipt->allocator_session_created = 1;
  stage("oga_retained_cpu_session_allocator");
  CHECK(api->CreateMemoryInfo("Cpu", OrtDeviceAllocator, 0, OrtMemTypeDefault, &memory_info));
  CHECK(api->CreateAllocator(allocator_session, memory_info, &allocator));
  receipt->allocator_acquired = 1;
  actual_info = allocator->Info(allocator);
  REQUIRE(actual_info, "Session allocator returned no memory description");
  CHECK(api->MemoryInfoGetName(actual_info, &actual_name));
  CHECK(api->MemoryInfoGetType(actual_info, &allocator_type));
  CHECK(api->MemoryInfoGetMemType(actual_info, &mem_type));
  api->MemoryInfoGetDeviceType(actual_info, &device_type);
  receipt->allocator_type = (uint32_t)allocator_type;
  receipt->allocator_mem_type = (int32_t)mem_type;
  receipt->allocator_device_type = (uint32_t)device_type;
  /* ORT SessionState resolves allocators by OrtDevice, not the requested name.
   * OGA also does not require the returned name to equal the requested "Cpu".
   * Preserve CPU addressing and memory-type checks before dereferencing data.
   */
  printf("QMOE_CAPI_ALLOCATOR name=%.*s type=%d mem=%d device=%d\n", 64,
         actual_name ? actual_name : "<null>", (int)allocator_type, (int)mem_type, (int)device_type);
  fflush(stdout);
  REQUIRE(allocator_type == OrtDeviceAllocator && mem_type == OrtMemTypeDefault &&
          device_type == OrtMemoryInfoDeviceType_CPU, "Session allocator differs from exact OGA Cpu/device/default key");
  stage("strict_session_admission");
  ++receipt->session_creation_attempts;
  CHECK(api->CreateSession(env, model_path, options, &session));
  ++receipt->session_creations;
  CHECK(api->SessionGetInputCount(session, &input_count));
  CHECK(api->SessionGetOutputCount(session, &output_count));
  REQUIRE(input_count == 2 && output_count == 1, "Frozen graph I/O count differs");
  CHECK(validate_model_io(api, session, 0, 0, ONNX_TENSOR_ELEMENT_DATA_TYPE_BFLOAT16, 3, x_shape, &valid));
  REQUIRE(valid, "Frozen activation metadata differs");
  CHECK(validate_model_io(api, session, 0, 1, ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, 2, router_shape, &valid));
  REQUIRE(valid, "Frozen router metadata differs");
  CHECK(validate_model_io(api, session, 1, 0, ONNX_TENSOR_ELEMENT_DATA_TYPE_BFLOAT16, 3, x_shape, &valid));
  REQUIRE(valid, "Frozen output metadata differs");
  CHECK(api->CreateTensorAsOrtValue(allocator, x_shape, 3, ONNX_TENSOR_ELEMENT_DATA_TYPE_BFLOAT16, &x));
  CHECK(api->CreateTensorAsOrtValue(allocator, router_shape, 2, ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &router));
  CHECK(api->CreateTensorAsOrtValue(allocator, x_shape, 3, ONNX_TENSOR_ELEMENT_DATA_TYPE_BFLOAT16, &output));
  CHECK(api->GetTensorMutableData(x, (void**)&xp));
  CHECK(api->GetTensorMutableData(router, (void**)&rp));
  CHECK(api->GetTensorMutableData(output, (void**)&yp));
  REQUIRE(xp && rp && yp, "Bounded session tensors returned null data");
  CHECK(api->CreateIoBinding(session, &binding));
  CHECK(api->BindOutput(binding, "y", output));
  for (i = 0; i < CALLS; ++i) {
    size_t element;
    size_t first_expert = i == 0 ? 0 : 502;
    for (element = 0; element < WIDTH; ++element) xp[element] = i == 0 ? 0x3F80 : 0x4000;
    memset(rp, 0, EXPERTS * sizeof(float));
    for (element = 0; element < 10; ++element) rp[first_expert + element] = (float)(10 - element) / 10.0f;
    memset(yp, 0x7F, OUT_BYTES);
    /* BindInput may copy across memory domains immediately. Bind only after
     * populating the current fixture so the two calls cannot reuse stale data.
     */
    CHECK(api->BindInput(binding, "x", x));
    CHECK(api->BindInput(binding, "router", router));
    CHECK(api->SynchronizeBoundInputs(binding));
    /* The callback executes in ordinary host code, outside ORT and outside
     * VEH. Its success publishes a complete immutable map for the coming call.
     * Refresh time is excluded from the existing Run/output-sync QPC receipt.
     * A refresh error prevents this Run and follows the normal cleanup path.
     */
    stage(i == 0 ? "synthetic_call_0_capture_refresh" : "synthetic_call_1_capture_refresh");
    refresh_status = refresh_callback();
    printf("QMOE_CAPI_CAPTURE_REFRESH call=%u status=%lu\n",
           (unsigned int)i, (unsigned long)refresh_status);
    fflush(stdout);
    if (refresh_status != ERROR_SUCCESS) {
      if (error_capacity != 0) {
        snprintf(error, error_capacity, "refresh_capture call %u failed with Win32 error %lu",
                 (unsigned int)i, (unsigned long)refresh_status);
        error[error_capacity - 1] = '\0';
      }
      goto cleanup;
    }
    stage(i == 0 ? "synthetic_call_0_capture_refreshed" : "synthetic_call_1_capture_refreshed");
    stage(i == 0 ? "synthetic_call_0_invoke" : "synthetic_call_1_invoke");
    ++receipt->calls_attempted;
    REQUIRE(QueryPerformanceCounter(&started), "QPC start failed");
    CHECK(api->RunWithBinding(session, NULL, binding));
    CHECK(api->SynchronizeBoundOutputs(binding));
    REQUIRE(QueryPerformanceCounter(&finished), "QPC finish failed");
    receipt->call_ticks[i] = (uint64_t)(finished.QuadPart - started.QuadPart);
    ++receipt->calls_completed;
    stage(i == 0 ? "synthetic_call_0_returned" : "synthetic_call_1_returned");
    for (element = 0; element < WIDTH; ++element)
      REQUIRE((yp[element] & 0x7FFF) == 0, "Zero-bank output contains a nonzero or nonfinite BF16 value");
    ++receipt->zero_outputs;
    memcpy((unsigned char*)output_receipts + i * OUT_BYTES, yp, OUT_BYTES);
  }
  stage("profile_attribution_receipt");
  CHECK(api->GetAllocatorWithDefaultOptions(&default_allocator));
  CHECK(api->SessionEndProfiling(session, default_allocator, &profile_path));
  REQUIRE(profile_path, "ORT profiling produced no receipt path");
  printf("QMOE_CAPI_PROFILE %s\n", profile_path);
  fflush(stdout);
  code = 0;

cleanup:
  stage("cleanup");
  if (api) {
    if (profile_path) {
      status = api->AllocatorFree(default_allocator, profile_path);
      if (status) {
        if (error[0] == '\0') set_error(error, error_capacity, "profile path free", api->GetErrorMessage(status));
        api->ReleaseStatus(status);
        code = 1;
      }
    }
    if (binding) api->ReleaseIoBinding(binding);
    if (output) api->ReleaseValue(output);
    if (router) api->ReleaseValue(router);
    if (x) api->ReleaseValue(x);
    /* Holder outlives execution session and every allocator-backed value. */
    if (session) api->ReleaseSession(session);
    if (allocator) api->ReleaseAllocator(allocator);
    if (memory_info) api->ReleaseMemoryInfo(memory_info);
    if (allocator_session) {
      api->ReleaseSession(allocator_session);
      receipt->allocator_session_released = 1;
    }
    if (options) api->ReleaseSessionOptions(options);
    if (allocator_options) api->ReleaseSessionOptions(allocator_options);
    if (registered) {
      status = api->UnregisterExecutionProviderLibrary(env, LIGHT);
      if (status) {
        if (error[0] == '\0') set_error(error, error_capacity, "unregister", api->GetErrorMessage(status));
        api->ReleaseStatus(status);
        code = 1;
      } else receipt->provider_unregistered = 1;
    }
    if (env) api->ReleaseEnv(env);
  }
  if (ort_module) FreeLibrary(ort_module);
  receipt->cleanup_completed = 1;
  return code;
#undef REQUIRE
#undef CHECK
}
