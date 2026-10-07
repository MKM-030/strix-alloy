/* Read-only native binding of one exact PDH GPU Copy instance to node metadata.
 * This opens an adapter handle, queries metadata, and closes only that handle.
 * It creates no device/context/queue and submits no GPU work. --plan calls none
 * of the D3DKMT APIs. Root owns execution; compile/plan are hardware-free.
 * Exact SDK structs from d3dkmthk.h/d3dkmdt.h; link Gdi32.lib and Bcrypt.lib.
 * https://learn.microsoft.com/windows-hardware/drivers/ddi/d3dkmthk/nf-d3dkmthk-d3dkmtopenadapterfromluid
 * https://learn.microsoft.com/windows-hardware/drivers/ddi/d3dkmdt/ns-d3dkmdt-d3dkmt_nodemetadata
 * https://learn.microsoft.com/windows-hardware/drivers/ddi/d3dkmthk/ns-d3dkmthk-_d3dkmt_physical_adapter_count
 * The query proves the adapter/index/node class only, not PID ownership or
 * PDH instance lifetime continuity. The instance PID is retained as input.
 */
#define WIN32_LEAN_AND_MEAN
#define _WIN32_WINNT 0x0a00
#include <windows.h>
#include <winternl.h>
#include <d3dkmthk.h>
#include <bcrypt.h>
#include <stdint.h>
#include <stdio.h>
#include <wchar.h>
#include <string.h>

#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "bcrypt.lib")

#define MAX_INSTANCE 256
#define MAX_OUTPUT 8192
#define NOT_CALLED ((NTSTATUS)0xc0000002L)
#define MAX_EXECUTABLE_BYTES (UINT64_C(32) * 1024 * 1024)

C_ASSERT(DXGK_ENGINE_TYPE_COPY == 6);
C_ASSERT(KMTQAITYPE_NODEMETADATA == 25);
C_ASSERT(KMTQAITYPE_PHYSICALADAPTERCOUNT == 30);

typedef struct {
    ULONG pid, physical, node, high, low;
    char instance[MAX_INSTANCE];
} TARGET;

static BOOL token(const WCHAR **cursor, const WCHAR *expected)
{
    size_t length = wcslen(expected);
    if (wcsncmp(*cursor, expected, length)) return FALSE;
    *cursor += length;
    return TRUE;
}

static BOOL number(const WCHAR **cursor, unsigned base, ULONG maximum, ULONG *out)
{
    uint64_t value = 0;
    unsigned count = 0;
    for (;;) {
        WCHAR c = **cursor;
        unsigned digit;
        if (c >= L'0' && c <= L'9') digit = (unsigned)(c - L'0');
        else if (base == 16 && c >= L'a' && c <= L'f') digit = (unsigned)(c - L'a') + 10;
        else if (base == 16 && c >= L'A' && c <= L'F') digit = (unsigned)(c - L'A') + 10;
        else break;
        if (digit >= base || count >= 10) return FALSE;
        value = value * base + digit;
        if (value > maximum) return FALSE;
        ++*cursor;
        ++count;
    }
    if (!count || (base == 16 && count > 8)) return FALSE;
    *out = (ULONG)value;
    return TRUE;
}

static BOOL parse_instance(const WCHAR *instance, TARGET *target)
{
    const WCHAR *cursor = instance;
    ULONG duplicate = 0;
    size_t i, length = wcslen(instance);
    if (!length || length >= MAX_INSTANCE) return FALSE;
    if (!token(&cursor, L"pid_") || !number(&cursor, 10, UINT32_MAX, &target->pid) || !target->pid ||
        !token(&cursor, L"_luid_0x") || !number(&cursor, 16, UINT32_MAX, &target->high) ||
        !token(&cursor, L"_0x") || !number(&cursor, 16, UINT32_MAX, &target->low) ||
        !token(&cursor, L"_phys_") || !number(&cursor, 10, 65535, &target->physical) ||
        !token(&cursor, L"_eng_") || !number(&cursor, 10, 65535, &target->node) ||
        _wcsnicmp(cursor, L"_engtype_copy", 13)) return FALSE;
    cursor += 13;
    if (*cursor == L'#') {
        ++cursor;
        if (!number(&cursor, 10, UINT32_MAX, &duplicate)) return FALSE;
    }
    if (*cursor) return FALSE;
    for (i = 0; i < length; ++i) {
        if (instance[i] > 127) return FALSE;
        target->instance[i] = (char)instance[i];
    }
    target->instance[length] = 0;
    return TRUE;
}

static BOOL executable_hash(char out[65])
{
    WCHAR path[32768];
    HANDLE file = INVALID_HANDLE_VALUE;
    BCRYPT_ALG_HANDLE algorithm = NULL;
    BCRYPT_HASH_HANDLE hash = NULL;
    BYTE buffer[65536], digest[32];
    DWORD length, got;
    LARGE_INTEGER size;
    BOOL ok = FALSE;
    unsigned i;
    static const char hex[] = "0123456789abcdef";
    length = GetModuleFileNameW(NULL, path, ARRAYSIZE(path));
    if (!length || length >= ARRAYSIZE(path)) goto done;
    file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_DELETE,
                       NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE || !GetFileSizeEx(file, &size) || size.QuadPart <= 0 ||
        (ULONGLONG)size.QuadPart > MAX_EXECUTABLE_BYTES) goto done;
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, NULL, 0) < 0 ||
        BCryptCreateHash(algorithm, &hash, NULL, 0, NULL, 0, 0) < 0) goto done;
    for (;;) {
        if (!ReadFile(file, buffer, sizeof(buffer), &got, NULL)) goto done;
        if (!got) break;
        if (BCryptHashData(hash, buffer, got, 0) < 0) goto done;
    }
    if (BCryptFinishHash(hash, digest, sizeof(digest), 0) < 0) goto done;
    for (i = 0; i < sizeof(digest); ++i) {
        out[i * 2] = hex[digest[i] >> 4];
        out[i * 2 + 1] = hex[digest[i] & 15];
    }
    out[64] = 0;
    ok = TRUE;
done:
    if (hash) BCryptDestroyHash(hash);
    if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0);
    if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
    return ok;
}

static BOOL unicode_json(const WCHAR *input, size_t count, char *output, size_t capacity)
{
    size_t i, used = 0;
    for (i = 0; i < count && input[i]; ++i) {
        int written;
        /* ASCII escaping preserves exact UTF-16 code units, including surrogates. */
        if (capacity - used < 7) return FALSE;
        written = sprintf_s(output + used, capacity - used, "\\u%04x", (unsigned)input[i]);
        if (written != 6) return FALSE;
        used += 6;
    }
    if (i == count) return FALSE;
    output[used] = 0;
    return TRUE;
}

int wmain(int argc, WCHAR **argv)
{
    TARGET target = {0};
    const WCHAR *instance = NULL, *output = NULL;
    BOOL plan = FALSE, success = FALSE;
    HANDLE file = INVALID_HANDLE_VALUE;
    D3DKMT_OPENADAPTERFROMLUID opened = {0};
    D3DKMT_CLOSEADAPTER closed = {0};
    D3DKMT_QUERYADAPTERINFO query = {0};
    D3DKMT_PHYSICAL_ADAPTER_COUNT physical = {0};
    D3DKMT_NODEMETADATA metadata = {0};
    NTSTATUS open_status = NOT_CALLED, physical_status = NOT_CALLED;
    NTSTATUS node_status = NOT_CALLED, close_status = NOT_CALLED;
    LARGE_INTEGER frequency = {0}, before = {0}, after = {0};
    ULARGE_INTEGER utc;
    FILETIME ft;
    char hash[65], friendly[DXGK_MAX_METADATA_NAME_LENGTH * 6 + 1] = {0};
    char receipt[MAX_OUTPUT];
    int i, length;
    DWORD written;
    for (i = 1; i < argc; ++i) {
        if (!wcscmp(argv[i], L"--instance") && !instance && i + 1 < argc) instance = argv[++i];
        else if (!wcscmp(argv[i], L"--output") && !output && i + 1 < argc) output = argv[++i];
        else if (!wcscmp(argv[i], L"--plan") && !plan) plan = TRUE;
        else { fputs("invalid_cli\n", stderr); return 2; }
    }
    if (!instance || !output || !*output || !parse_instance(instance, &target)) {
        fputs("requires --instance <exact Copy instance> --output <fresh receipt.jsonl> [--plan]\n", stderr);
        return 2;
    }
    if (!executable_hash(hash) || !QueryPerformanceFrequency(&frequency) || frequency.QuadPart <= 0) {
        fputs("executable_hash_or_clock_failed\n", stderr); return 3;
    }
    if (plan) {
        printf("{\"schema\":\"halogen.gpu-node-metadata.plan.v1\",\"instance\":\"%s\","
               "\"adapter_luid\":\"0x%08lx%08lx\",\"physical_index\":%lu,\"node_ordinal\":%lu,"
               "\"NodeOrdinalAndAdapterIndex\":%lu,\"native_executable_sha256\":\"%s\","
               "\"query_executed\":false}\n", target.instance, target.high, target.low,
               target.physical, target.node, (target.physical << 16) | target.node, hash);
        return 0;
    }
    file = CreateFileW(output, GENERIC_WRITE, 0, NULL, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) { fputs("output_refused\n", stderr); return 4; }
    GetSystemTimePreciseAsFileTime(&ft);
    utc.LowPart = ft.dwLowDateTime;
    utc.HighPart = ft.dwHighDateTime;
    metadata.NodeOrdinalAndAdapterIndex = (target.physical << 16) | target.node;
    if (!QueryPerformanceCounter(&before)) goto finish;
    memcpy(&opened.AdapterLuid.HighPart, &target.high, sizeof(target.high));
    opened.AdapterLuid.LowPart = target.low;
    open_status = D3DKMTOpenAdapterFromLuid(&opened);
    if (open_status == 0 && opened.hAdapter) {
        query.hAdapter = opened.hAdapter;
        query.Type = KMTQAITYPE_PHYSICALADAPTERCOUNT;
        query.pPrivateDriverData = &physical;
        query.PrivateDriverDataSize = sizeof(physical);
        physical_status = D3DKMTQueryAdapterInfo(&query);
        if (physical_status == 0 && target.physical < physical.Count) {
            query.Type = KMTQAITYPE_NODEMETADATA;
            query.pPrivateDriverData = &metadata;
            query.PrivateDriverDataSize = sizeof(metadata);
            node_status = D3DKMTQueryAdapterInfo(&query);
        }
        closed.hAdapter = opened.hAdapter;
        close_status = D3DKMTCloseAdapter(&closed);
    }
    if (!QueryPerformanceCounter(&after)) goto finish;
    if (!unicode_json(metadata.NodeData.FriendlyName, ARRAYSIZE(metadata.NodeData.FriendlyName),
                      friendly, sizeof(friendly))) goto finish;
    success = open_status == 0 && physical_status == 0 && node_status == 0 && close_status == 0 &&
              before.QuadPart > 0 && after.QuadPart >= before.QuadPart &&
              metadata.NodeData.EngineType == DXGK_ENGINE_TYPE_COPY;
    length = sprintf_s(receipt, sizeof(receipt),
        "{\"schema\":\"halogen.gpu-node-metadata.v1\",\"api\":\"D3DKMTQueryAdapterInfo\","
        "\"type\":\"KMTQAITYPE_NODEMETADATA\",\"status\":%lu,\"success\":%s,"
        "\"instance\":\"%s\",\"input_pdh_pid\":%lu,\"adapter_luid\":\"0x%08lx%08lx\","
        "\"physical_index\":%lu,\"node_ordinal\":%lu,\"NodeOrdinalAndAdapterIndex\":%lu,"
        "\"EngineType\":%u,\"expected_copy_engine_type\":%u,\"FriendlyName\":\"%s\","
        "\"open_adapter_status\":%lu,\"physical_count_status\":%lu,\"physical_adapter_count\":%u,"
        "\"close_adapter_status\":%lu,\"native_executable_sha256\":\"%s\","
        "\"qpc_frequency\":%lld,\"qpc_before\":%lld,\"qpc_after\":%lld,\"utc_filetime\":%llu,"
        "\"sizeof_D3DKMT_NODEMETADATA\":%zu,\"DXGKDDI_INTERFACE_VERSION\":%u,"
        "\"pid_ownership_attested\":false,\"instance_generation_verified\":false}\n",
        (ULONG)node_status, success ? "true" : "false", target.instance, target.pid,
        target.high, target.low, target.physical, target.node, metadata.NodeOrdinalAndAdapterIndex,
        (unsigned)metadata.NodeData.EngineType, (unsigned)DXGK_ENGINE_TYPE_COPY, friendly,
        (ULONG)open_status, (ULONG)physical_status, physical.Count, (ULONG)close_status, hash,
        frequency.QuadPart, before.QuadPart, after.QuadPart, utc.QuadPart,
        sizeof(metadata), (unsigned)DXGKDDI_INTERFACE_VERSION);
    if (length <= 0 || !WriteFile(file, receipt, (DWORD)length, &written, NULL) ||
        written != (DWORD)length || !FlushFileBuffers(file)) success = FALSE;
finish:
    if (!CloseHandle(file)) success = FALSE;
    if (!success) fputs("metadata_query_not_qualified; inspect receipt status fields\n", stderr);
    return success ? 0 : 5;
}
