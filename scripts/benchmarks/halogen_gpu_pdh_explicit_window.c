/* Bounded, source-only Windows x64 GPU PDH epoch collector; link Pdh/Psapi.
 * Root starts this only AFTER excluded warmup and proved idle, then acknowledges
 * its flushed baseline before measured requests. The entire baseline-to-final
 * epoch, including idle margins, belongs to the caller's rejection policy.
 * No ownership whitelist, threshold, process launch, ETW or privilege changes.
 * https://learn.microsoft.com/windows/win32/api/pdh/nf-pdh-pdhaddenglishcounterw
 * https://learn.microsoft.com/windows/win32/api/pdh/nf-pdh-pdhcollectquerydatawithtime
 * https://learn.microsoft.com/windows/win32/api/pdh/nf-pdh-pdhexpandwildcardpathw
 * https://learn.microsoft.com/windows/win32/api/pdh/nf-pdh-pdhparsecounterpathw
 * https://learn.microsoft.com/windows/win32/api/pdh/nf-pdh-pdhgetrawcountervalue
 * https://learn.microsoft.com/windows/win32/api/pdh/nf-pdh-pdhcalculatecounterfromrawvalue
 * Documented localization -> expansion -> AddCounter sequence, retaining one
 * explicit handle for each exact provider path for the entire epoch. Expanded
 * paths and parsed duplicate-instance indices are provider counter identity,
 * never an inferred process birth/generation. No raw enumeration rank pairing.
 * PDH has no instance birth/generation token. Observed disappearance, duplicate,
 * reset and invalid status are unresolved; hidden same-name reuse cannot be
 * disproved by raw continuity. Instance identity proof remains external.
 * Raw FILETIME fields are preserved, not relabelled as host UTC. Separate precise
 * host UTC/QPC brackets provide calibration; query time is only its first value.
 * PDH calls/stdout can block: late sampling/monitor gaps invalidate the receipt.
 */
#define WIN32_LEAN_AND_MEAN
#define _WIN32_WINNT 0x0602
#include <windows.h>
#include <pdh.h>
#include <pdhmsg.h>
#include <psapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <wchar.h>
#include <stdarg.h>
#include <float.h>
#include <io.h>
#include <fcntl.h>

#pragma comment(lib, "pdh.lib")
#pragma comment(lib, "psapi.lib")

#define PATH_CHARS 1024u
#define NAME_CHARS 512u
#define MAX_ITEMS 4096u
#define RAW_BYTES (1024u * 1024u)
#define INFO_BYTES (64u * 1024u)
#define EXPAND_BYTES (512u * 1024u)
#define NAME_POOL_BYTES RAW_BYTES
#define OUTPUT_BYTES (UINT64_C(64) * 1024 * 1024)
#define LINE_BYTES (UINT64_C(8) * 1024 * 1024)
#define TERMINAL_RESERVE 16384u
#define PRIVATE_BYTES (UINT64_C(16) * 1024 * 1024)
#define GIB (UINT64_C(1024) * 1024 * 1024)
#define NOT_CALLED ((DWORD)0xffffffffu)
#define MEMORY_POLL_MS 100u
#define MEMORY_GAP_MS 250u
#define SAMPLE_MS 500u
#define SAMPLE_GAP_MS 1500u
#define SCHEMA "halogen.gpu-pdh.window.v1"

static const WCHAR COUNTER_PATH[] = L"\\GPU Engine(*)\\Utilization Percentage";

enum REASON { R_NONE, R_CLI, R_CLOCK, R_MARKER, R_ADMISSION, R_MEMORY_API,
    R_RESERVE, R_PRIVATE, R_MEMORY_GAP, R_THREAD, R_ALLOC, R_PDH, R_RAW,
    R_SAMPLE_GAP, R_OUTPUT_CAP, R_IO, R_CLOSE, R_TOPOLOGY };

typedef struct {
    LONGLONG before, after;
    ULONGLONG utc;
    SYSTEMTIME st;
} MARK;

typedef struct {
    HANDLE abort_event, done_event;
    SRWLOCK memory_lock;
    LARGE_INTEGER frequency;
    volatile LONG reason;
    DWORD memory_code;
    ULONGLONG min_physical, min_commit, max_private;
    LONGLONG last_qpc, max_gap_qpc;
    DWORD samples;
} GUARD;

typedef struct { GUARD *guard; ULONGLONG bytes; BOOL failed; } OUTPUT;
typedef struct {
    WCHAR *buffer, **index;
    DWORD count, chars, code;
    LONGLONG qpc_before, qpc_after;
    BOOL available;
} TOPOLOGY;
typedef struct {
    PDH_HCOUNTER handle;
    const WCHAR *path, *instance, *parsed_instance;
    DWORD registry_index, provider_index, type;
    LONGLONG timebase;
} EXPLICIT_COUNTER;
typedef struct {
    TOPOLOGY baseline;
    EXPLICIT_COUNTER *items;
    WCHAR *name_pool;
    DWORD count, name_chars, localized_code, remove_code;
    WCHAR localized[PATH_CHARS];
} COUNTERS;
typedef struct {
    const WCHAR *szName;
    PDH_RAW_COUNTER RawValue;
    EXPLICIT_COUNTER *source;
    DWORD raw_code, metadata_code, timebase_code, type;
    LONGLONG timebase;
} RAW_ITEM;
typedef struct { RAW_ITEM *item; DWORD original; } INDEX;
typedef struct {
    void *buffer;
    INDEX *index;
    DWORD count, query_code, raw_array_code, metadata_code, timebase_code, type;
    LONGLONG query_time, timebase, qpc_before, qpc_after;
    MARK utc_before, utc_after;
    BOOL raw_available;
    TOPOLOGY topology_before, topology_after;
    BOOL topology_unchanged;
} SNAPSHOT;

#if !defined(_WIN64)
#error This bounded collector requires a Windows x64 build.
#endif
typedef char raw_items_fit[(MAX_ITEMS * sizeof(RAW_ITEM) <= RAW_BYTES) ? 1 : -1];
#define OWNED_ALLOCATION_BYTES (2 * RAW_BYTES + NAME_POOL_BYTES + 5 * EXPAND_BYTES + \
    2 * MAX_ITEMS * sizeof(INDEX) + 5 * MAX_ITEMS * sizeof(WCHAR *) + \
    MAX_ITEMS * sizeof(EXPLICIT_COUNTER) + 2 * INFO_BYTES)
typedef char fixed_storage_under_7mib[(OWNED_ALLOCATION_BYTES < 7u * 1024u * 1024u) ? 1 : -1];

static const char *reason_name(LONG r)
{
    static const char *const names[] = { "none", "invalid_cli", "clock_failed",
        "stop_marker_refused", "start_reserve_below_22gib", "memory_query_failed",
        "runtime_reserve_below_18gib", "private_commit_above_16mib",
        "monitor_gap_above_250ms", "monitor_thread_failed", "allocation_bound_or_failure",
        "pdh_api_failed", "malformed_raw_array", "sample_gap_above_1500ms",
        "output_cap_reached", "receipt_io_failed", "owned_query_close_failed",
        "explicit_counter_topology_changed_or_invalid" };
    return r >= R_NONE && r <= R_TOPOLOGY ? names[r] : "unknown";
}

static void fail(GUARD *g, LONG reason)
{
    InterlockedCompareExchange(&g->reason, reason, R_NONE);
    if (g->abort_event) SetEvent(g->abort_event);
}

static void mark_now(MARK *m)
{
    FILETIME ft;
    LARGE_INTEGER q;
    QueryPerformanceCounter(&q); m->before = q.QuadPart;
    GetSystemTimePreciseAsFileTime(&ft);
    m->utc = ((ULONGLONG)ft.dwHighDateTime << 32) | ft.dwLowDateTime;
    FileTimeToSystemTime(&ft, &m->st);
    QueryPerformanceCounter(&q); m->after = q.QuadPart;
}

static BOOL memory_sample(GUARD *g, BOOL admission)
{
    MEMORYSTATUSEX ms;
    PERFORMANCE_INFORMATION pi;
    PROCESS_MEMORY_COUNTERS_EX pm;
    LARGE_INTEGER q;
    ULONGLONG commit;
    LONGLONG gap;
    BOOL valid;
    AcquireSRWLockExclusive(&g->memory_lock);
    ZeroMemory(&ms, sizeof(ms)); ms.dwLength = (DWORD)sizeof(ms);
    ZeroMemory(&pi, sizeof(pi)); pi.cb = (DWORD)sizeof(pi);
    ZeroMemory(&pm, sizeof(pm)); pm.cb = (DWORD)sizeof(pm);
    if (!GlobalMemoryStatusEx(&ms) || !GetPerformanceInfo(&pi, (DWORD)sizeof(pi)) ||
        !GetProcessMemoryInfo(GetCurrentProcess(), (PROCESS_MEMORY_COUNTERS *)&pm,
                             (DWORD)sizeof(pm))) {
        g->memory_code = GetLastError(); fail(g, R_MEMORY_API);
        ReleaseSRWLockExclusive(&g->memory_lock); return FALSE;
    }
    if (pi.CommitLimit < pi.CommitTotal || !pi.PageSize ||
        (ULONGLONG)(pi.CommitLimit - pi.CommitTotal) > UINT64_MAX / pi.PageSize) {
        g->memory_code = ERROR_INVALID_DATA; fail(g, R_MEMORY_API);
        ReleaseSRWLockExclusive(&g->memory_lock); return FALSE;
    }
    commit = (ULONGLONG)(pi.CommitLimit - pi.CommitTotal) * pi.PageSize;
    QueryPerformanceCounter(&q);
    gap = g->last_qpc ? q.QuadPart - g->last_qpc : 0;
    g->last_qpc = q.QuadPart;
    if (gap > g->max_gap_qpc) g->max_gap_qpc = gap;
    ++g->samples;
    if (ms.ullAvailPhys < g->min_physical) g->min_physical = ms.ullAvailPhys;
    if (commit < g->min_commit) g->min_commit = commit;
    if ((ULONGLONG)pm.PrivateUsage > g->max_private) g->max_private = pm.PrivateUsage;
    if (gap < 0 || gap > g->frequency.QuadPart * MEMORY_GAP_MS / 1000)
        fail(g, R_MEMORY_GAP);
    if (ms.ullAvailPhys < (admission ? 22 : 18) * GIB ||
        commit < (admission ? 22 : 18) * GIB) fail(g, admission ? R_ADMISSION : R_RESERVE);
    if ((ULONGLONG)pm.PrivateUsage > PRIVATE_BYTES) fail(g, R_PRIVATE);
    valid = g->reason == R_NONE;
    ReleaseSRWLockExclusive(&g->memory_lock);
    return valid;
}

static DWORD WINAPI monitor_thread(void *context)
{
    GUARD *g = (GUARD *)context;
    for (;;) {
        DWORD code;
        memory_sample(g, FALSE);
        code = WaitForSingleObject(g->done_event, MEMORY_POLL_MS);
        if (code == WAIT_OBJECT_0) break;
        if (code != WAIT_TIMEOUT) { fail(g, R_THREAD); break; }
    }
    memory_sample(g, FALSE);
    return 0;
}

static BOOL out_bytes(OUTPUT *o, const char *s, size_t n)
{
    size_t written;
    if (o->failed) return FALSE;
    if ((ULONGLONG)n > OUTPUT_BYTES - o->bytes) {
        fail(o->guard, R_OUTPUT_CAP); o->failed = TRUE; return FALSE;
    }
    written = fwrite(s, 1, n, stdout); o->bytes += written;
    if (written != n || ferror(stdout)) {
        fail(o->guard, R_IO); o->failed = TRUE; return FALSE;
    }
    return TRUE;
}

static void outf(OUTPUT *o, const char *format, ...)
{
    char buffer[1024];
    int n;
    va_list args;
    if (o->failed) return;
    va_start(args, format); n = vsnprintf(buffer, sizeof(buffer), format, args); va_end(args);
    if (n < 0 || (size_t)n >= sizeof(buffer)) {
        fail(o->guard, R_IO); o->failed = TRUE; return;
    }
    out_bytes(o, buffer, (size_t)n);
}

static void out_wide(OUTPUT *o, const WCHAR *s)
{
    char utf8[PATH_CHARS * 4];
    int i, n = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, s, -1,
                                 utf8, (int)sizeof(utf8), NULL, NULL);
    if (!n) { fail(o->guard, R_RAW); o->failed = TRUE; return; }
    outf(o, "\"");
    for (i = 0; i < n - 1 && !o->failed; ++i) {
        unsigned char c = (unsigned char)utf8[i];
        if (c == '"' || c == '\\') outf(o, "\\%c", c);
        else if (c < 0x20) outf(o, "\\u%04x", (unsigned)c);
        else out_bytes(o, utf8 + i, 1);
    }
    outf(o, "\"");
}

static BOOL flush_output(OUTPUT *o)
{
    int code = fflush(stdout);
    if (code != 0 || ferror(stdout)) { fail(o->guard, R_IO); o->failed = TRUE; }
    return !o->failed;
}

static void out_mark(OUTPUT *o, const MARK *m)
{
    outf(o, "{\"qpc_before\":\"%lld\",\"qpc_after\":\"%lld\","
         "\"utc_filetime_100ns\":\"%llu\",\"utc\":\"%04u-%02u-%02uT%02u:%02u:%02u.%03uZ\"}",
         (long long)m->before, (long long)m->after, (unsigned long long)m->utc,
         (unsigned)m->st.wYear, (unsigned)m->st.wMonth, (unsigned)m->st.wDay,
         (unsigned)m->st.wHour, (unsigned)m->st.wMinute, (unsigned)m->st.wSecond,
         (unsigned)m->st.wMilliseconds);
}

static ULONGLONG raw_time(const PDH_RAW_COUNTER *raw)
{
    return ((ULONGLONG)raw->TimeStamp.dwHighDateTime << 32) | raw->TimeStamp.dwLowDateTime;
}

static BOOL valid_status(DWORD code)
{
    return code == PDH_CSTATUS_VALID_DATA || code == PDH_CSTATUS_NEW_DATA;
}

static int compare_index(const void *a, const void *b)
{
    const INDEX *ia = (const INDEX *)a, *ib = (const INDEX *)b;
    int c = wcscmp(ia->item->szName, ib->item->szName);
    if (c) return c;
    return ia->original < ib->original ? -1 : ia->original != ib->original;
}

static BOOL bounded_string(const void *buffer, DWORD bytes, const WCHAR *text,
                           DWORD cap, BOOL allow_empty)
{
    uintptr_t begin = (uintptr_t)buffer, end = begin + bytes, p = (uintptr_t)text;
    const WCHAR *nul;
    if (!p || p < begin || p >= end || (p - begin) % sizeof(WCHAR)) return FALSE;
    nul = wmemchr(text, L'\0', (end - p) / sizeof(WCHAR));
    return nul && (allow_empty || nul != text) && (size_t)(nul - text) < cap;
}

static int compare_path(const void *a, const void *b)
{
    return wcscmp(*(const WCHAR *const *)a, *(const WCHAR *const *)b);
}

static BOOL expand_topology(GUARD *g, const WCHAR *localized, TOPOLOGY *t)
{
    DWORD needed = 0, used = EXPAND_BYTES / sizeof(WCHAR), i;
    WCHAR *p, *end;
    LARGE_INTEGER q;
    t->count = t->chars = 0; t->available = FALSE;
    t->qpc_before = t->qpc_after = 0;
    if (!QueryPerformanceCounter(&q) || q.QuadPart <= 0) {
        t->code = ERROR_INVALID_DATA; fail(g, R_CLOCK); return FALSE;
    }
    t->qpc_before = q.QuadPart;
    t->code = (DWORD)PdhExpandWildCardPathW(NULL, localized, NULL, &needed, PDH_REFRESHCOUNTERS);
    if (t->code != PDH_MORE_DATA || needed < 2 || needed > EXPAND_BYTES / sizeof(WCHAR)) {
        fail(g, needed > EXPAND_BYTES / sizeof(WCHAR) ? R_ALLOC : R_TOPOLOGY); goto done;
    }
    t->code = (DWORD)PdhExpandWildCardPathW(NULL, localized, t->buffer, &used, PDH_REFRESHCOUNTERS);
    if (t->code != ERROR_SUCCESS) { fail(g, R_TOPOLOGY); goto done; }
    if (used < 2 || used > EXPAND_BYTES / sizeof(WCHAR) ||
        t->buffer[used - 1] || t->buffer[used - 2]) goto malformed;
    t->chars = used; p = t->buffer; end = p + used;
    while (p < end && *p) {
        WCHAR *nul = wmemchr(p, L'\0', (size_t)(end - p));
        if (!nul || nul == p || (size_t)(nul - p) >= PATH_CHARS ||
            t->count == MAX_ITEMS) goto malformed;
        t->index[t->count++] = p;
        p = nul + 1;
    }
    if (!t->count || p >= end) goto malformed;
    /* Retain provider MULTI_SZ order; sort pointers only for exact set checks. */
    qsort(t->index, t->count, sizeof(WCHAR *), compare_path);
    for (i = 1; i < t->count; ++i)
        if (!wcscmp(t->index[i - 1], t->index[i])) goto malformed;
    t->available = TRUE;
    goto done;
malformed:
    t->code = ERROR_INVALID_DATA; fail(g, R_TOPOLOGY);
done:
    if (!QueryPerformanceCounter(&q) || q.QuadPart <= 0) {
        t->code = ERROR_INVALID_DATA; fail(g, R_CLOCK); return FALSE;
    }
    t->qpc_after = q.QuadPart;
    if (t->qpc_after < t->qpc_before) { t->code = ERROR_INVALID_DATA; fail(g, R_CLOCK); }
    return t->available && t->code == ERROR_SUCCESS;
}

static BOOL same_topology(const TOPOLOGY *a, const TOPOLOGY *b)
{
    DWORD i;
    if (!a->available || !b->available || a->count != b->count) return FALSE;
    for (i = 0; i < a->count; ++i) if (wcscmp(a->index[i], b->index[i])) return FALSE;
    return TRUE;
}

static DWORD counter_info(PDH_HCOUNTER handle, void *buffer, PDH_COUNTER_INFO_W **result)
{
    DWORD needed = 0, used = INFO_BYTES, code;
    PDH_COUNTER_INFO_W *info = (PDH_COUNTER_INFO_W *)buffer;
    code = (DWORD)PdhGetCounterInfoW(handle, FALSE, &needed, NULL);
    if (code != PDH_MORE_DATA) return code ? code : ERROR_INVALID_DATA;
    if (needed < sizeof(*info) || needed > INFO_BYTES) return ERROR_INSUFFICIENT_BUFFER;
    code = (DWORD)PdhGetCounterInfoW(handle, FALSE, &used, info);
    if (code) return code;
    if (used < sizeof(*info) || used > INFO_BYTES ||
        !bounded_string(buffer, used, info->szFullPath, PATH_CHARS, FALSE)) return ERROR_INVALID_DATA;
    *result = info;
    return ERROR_SUCCESS;
}

static DWORD parse_provider_path(const WCHAR *path, void *buffer, PDH_COUNTER_PATH_ELEMENTS_W **result)
{
    DWORD needed = 0, used = INFO_BYTES, code;
    PDH_COUNTER_PATH_ELEMENTS_W *parts = (PDH_COUNTER_PATH_ELEMENTS_W *)buffer;
    code = (DWORD)PdhParseCounterPathW(path, NULL, &needed, 0);
    if (code != PDH_MORE_DATA) return code ? code : ERROR_INVALID_DATA;
    if (needed < sizeof(*parts) || needed > INFO_BYTES) return ERROR_INSUFFICIENT_BUFFER;
    code = (DWORD)PdhParseCounterPathW(path, parts, &used, 0);
    if (code) return code;
    if (used < sizeof(*parts) || used > INFO_BYTES ||
        !bounded_string(buffer, used, parts->szInstanceName, NAME_CHARS - 12, FALSE) ||
        !bounded_string(buffer, used, parts->szObjectName, PATH_CHARS, FALSE) ||
        !bounded_string(buffer, used, parts->szCounterName, PATH_CHARS, FALSE) ||
        (parts->szParentInstance && !bounded_string(buffer, used, parts->szParentInstance, NAME_CHARS, TRUE)) ||
        (parts->szParentInstance && *parts->szParentInstance) ||
        wcschr(parts->szInstanceName, L'*') || wcschr(parts->szInstanceName, L'#') ||
        wcschr(parts->szObjectName, L'*') || wcschr(parts->szCounterName, L'*')) return ERROR_INVALID_DATA;
    *result = parts;
    return ERROR_SUCCESS;
}

static BOOL prepare_counters(GUARD *g, PDH_HQUERY query, PDH_HCOUNTER wildcard,
                             COUNTERS *counters, void *info_buffer, void *parse_buffer,
                             DWORD *add_code)
{
    PDH_COUNTER_INFO_W *info;
    DWORD i, j;
    counters->localized_code = counter_info(wildcard, info_buffer, &info);
    if (counters->localized_code) { fail(g, R_PDH); return FALSE; }
    wcscpy_s(counters->localized, PATH_CHARS, info->szFullPath);
    if (!expand_topology(g, counters->localized, &counters->baseline)) return FALSE;
    counters->count = counters->baseline.count;
    for (i = 0; i < counters->count && !g->reason; ++i) {
        EXPLICIT_COUNTER *entry = &counters->items[i];
        PDH_COUNTER_PATH_ELEMENTS_W *parts;
        size_t length;
        int got;
        entry->registry_index = i;
        entry->path = counters->baseline.index[i];
        if (parse_provider_path(entry->path, parse_buffer, &parts)) { fail(g, R_TOPOLOGY); return FALSE; }
        length = wcslen(parts->szInstanceName);
        if ((ULONGLONG)counters->name_chars + 2 * length + 14 > NAME_POOL_BYTES / sizeof(WCHAR)) {
            fail(g, R_ALLOC); return FALSE;
        }
        entry->parsed_instance = counters->name_pool + counters->name_chars;
        memcpy(counters->name_pool + counters->name_chars, parts->szInstanceName, (length + 1) * sizeof(WCHAR));
        counters->name_chars += (DWORD)length + 1;
        entry->provider_index = parts->dwInstanceIndex;
        entry->instance = counters->name_pool + counters->name_chars;
        got = swprintf_s(counters->name_pool + counters->name_chars,
                         NAME_POOL_BYTES / sizeof(WCHAR) - counters->name_chars,
                         L"%ls#%lu", parts->szInstanceName, parts->dwInstanceIndex);
        if (got <= 0 || got >= (int)NAME_CHARS) { fail(g, R_RAW); return FALSE; }
        counters->name_chars += (DWORD)got + 1;
        for (j = 0; j < i; ++j) if (!wcscmp(counters->items[j].instance, entry->instance)) {
            fail(g, R_TOPOLOGY); return FALSE;
        }
        *add_code = (DWORD)PdhAddCounterW(query, entry->path, 0, &entry->handle);
        if (*add_code) { fail(g, R_PDH); return FALSE; }
        if (counter_info(entry->handle, info_buffer, &info) || wcscmp(info->szFullPath, entry->path)) {
            fail(g, R_TOPOLOGY); return FALSE;
        }
        entry->type = info->dwType;
        if (PdhGetCounterTimeBase(entry->handle, &entry->timebase) || entry->timebase <= 0 ||
            (i && (entry->type != counters->items[0].type || entry->timebase != counters->items[0].timebase))) {
            fail(g, R_PDH); return FALSE;
        }
    }
    /* Localization-only wildcard never participates in raw/cooked collection. */
    counters->remove_code = (DWORD)PdhRemoveCounter(wildcard);
    if (counters->remove_code) { fail(g, R_PDH); return FALSE; }
    return g->reason == R_NONE;
}

static BOOL collect(GUARD *g, PDH_HQUERY query, COUNTERS *counters,
                    SNAPSHOT *s, void *info_buffer)
{
    DWORD i;
    LARGE_INTEGER q;
    BOOL good = TRUE;
    s->count = 0; s->raw_available = s->topology_unchanged = FALSE;
    s->query_time = 0; s->type = counters->items[0].type; s->timebase = counters->items[0].timebase;
    s->query_code = s->raw_array_code = s->metadata_code = s->timebase_code = NOT_CALLED;
    s->topology_after.count = s->topology_after.chars = 0;
    s->topology_after.available = FALSE; s->topology_after.code = NOT_CALLED;
    if (!expand_topology(g, counters->localized, &s->topology_before) ||
        !same_topology(&counters->baseline, &s->topology_before)) {
        fail(g, R_TOPOLOGY); good = FALSE;
    }
    mark_now(&s->utc_before);
    s->qpc_before = s->qpc_after = 0;
    if (!QueryPerformanceCounter(&q) || q.QuadPart <= 0) { fail(g, R_CLOCK); good = FALSE; }
    else s->qpc_before = q.QuadPart;
    if (good) s->query_code = (DWORD)PdhCollectQueryDataWithTime(query, &s->query_time);
    if (!QueryPerformanceCounter(&q) || q.QuadPart <= 0) { fail(g, R_CLOCK); good = FALSE; }
    else s->qpc_after = q.QuadPart;
    mark_now(&s->utc_after);
    if (s->query_code != ERROR_SUCCESS) { fail(g, R_PDH); good = FALSE; }
    s->raw_array_code = s->metadata_code = s->timebase_code = 0;
    s->count = counters->count;
    ZeroMemory(s->buffer, s->count * sizeof(RAW_ITEM));
    for (i = 0; i < s->count; ++i) {
        RAW_ITEM *item = (RAW_ITEM *)s->buffer + i;
        EXPLICIT_COUNTER *entry = &counters->items[i];
        PDH_COUNTER_INFO_W *info = NULL;
        item->source = entry; item->szName = entry->instance;
        item->raw_code = item->metadata_code = item->timebase_code = NOT_CALLED;
        s->index[i].item = item; s->index[i].original = i;
        if (s->query_code != ERROR_SUCCESS || g->reason) { good = FALSE; continue; }
        item->raw_code = (DWORD)PdhGetRawCounterValue(entry->handle, &item->type, &item->RawValue);
        item->metadata_code = counter_info(entry->handle, info_buffer, &info);
        item->timebase_code = (DWORD)PdhGetCounterTimeBase(entry->handle, &item->timebase);
        if (!item->metadata_code && (wcscmp(info->szFullPath, entry->path) ||
            info->dwType != entry->type || item->type != info->dwType)) item->metadata_code = ERROR_INVALID_DATA;
        if (!item->timebase_code && (item->timebase <= 0 || item->timebase != entry->timebase))
            item->timebase_code = ERROR_INVALID_DATA;
        if (item->raw_code && !s->raw_array_code) s->raw_array_code = item->raw_code;
        if (item->metadata_code && !s->metadata_code) s->metadata_code = item->metadata_code;
        if (item->timebase_code && !s->timebase_code) s->timebase_code = item->timebase_code;
        if (item->raw_code || item->metadata_code || item->timebase_code ||
            !valid_status(item->RawValue.CStatus) || !raw_time(&item->RawValue)) good = FALSE;
    }
    qsort(s->index, s->count, sizeof(INDEX), compare_index);
    if (!expand_topology(g, counters->localized, &s->topology_after) ||
        !same_topology(&counters->baseline, &s->topology_after) ||
        !same_topology(&s->topology_before, &s->topology_after)) {
        fail(g, R_TOPOLOGY); good = FALSE;
    } else s->topology_unchanged = TRUE;
    if (!good) {
        if (!s->raw_array_code && !s->metadata_code && !s->timebase_code) s->raw_array_code = ERROR_INVALID_DATA;
        fail(g, R_PDH);
    }
    s->raw_available = good;
    return good && g->reason == R_NONE;
}

static const EXPLICIT_COUNTER *find_counter(const COUNTERS *counters, const WCHAR *path)
{
    DWORD lower = 0, upper = counters->count;
    while (lower < upper) {
        DWORD middle = lower + (upper - lower) / 2;
        int cmp = wcscmp(path, counters->items[middle].path);
        if (!cmp) return &counters->items[middle];
        if (cmp < 0) upper = middle; else lower = middle + 1;
    }
    return NULL;
}

static void out_registry(OUTPUT *o, const COUNTERS *counters)
{
    DWORD i;
    outf(o, "[");
    for (i = 0; i < counters->count && !o->failed; ++i) {
        const EXPLICIT_COUNTER *entry = &counters->items[i];
        if (i) outf(o, ",");
        outf(o, "{\"counter_index\":%lu,\"instance\":", entry->registry_index);
        out_wide(o, entry->instance); outf(o, ",\"path\":"); out_wide(o, entry->path);
        outf(o, ",\"parsed_instance\":"); out_wide(o, entry->parsed_instance);
        outf(o, ",\"provider_instance_index\":%lu}", entry->provider_index);
    }
    outf(o, "]");
}

static void out_topology(OUTPUT *o, const COUNTERS *counters, const TOPOLOGY *t)
{
    DWORD i, unmapped = 0;
    const WCHAR *p = t->buffer;
    outf(o, "{\"code\":%lu,\"available\":%s,\"qpc_before\":\"%lld\",\"qpc_after\":\"%lld\","
         "\"path_count\":%lu,\"refresh_counters\":true,\"path_indices\":[", t->code,
         t->available ? "true" : "false", (long long)t->qpc_before, (long long)t->qpc_after, t->count);
    for (i = 0; i < t->count && !o->failed; ++i) {
        const EXPLICIT_COUNTER *entry = find_counter(counters, p);
        if (i) outf(o, ",");
        if (entry) outf(o, "%lu", entry->registry_index); else outf(o, "null");
        p += wcslen(p) + 1;
    }
    outf(o, "],\"unmapped_paths\":["); p = t->buffer;
    for (i = 0; i < t->count && !o->failed; ++i) {
        if (!find_counter(counters, p)) {
            if (unmapped++) outf(o, ",");
            outf(o, "{\"position\":%lu,\"path\":", i); out_wide(o, p); outf(o, "}");
        }
        p += wcslen(p) + 1;
    }
    outf(o, "]}");
}

static void out_snapshot(OUTPUT *o, const COUNTERS *counters, const SNAPSHOT *s)
{
    DWORD i;
    if (!s) { outf(o, "null"); return; }
    outf(o, "{\"query_code\":%lu,\"raw_array_code\":%lu,\"metadata_code\":%lu,"
         "\"timebase_code\":%lu,\"counter_type\":%lu,\"timebase\":\"%lld\","
         "\"query_filetime_100ns\":\"%lld\",\"raw_available\":%s,"
         "\"collection\":{\"qpc_before\":\"%lld\",\"qpc_after\":\"%lld\",\"utc_before\":",
         s->query_code, s->raw_array_code, s->metadata_code, s->timebase_code, s->type,
         (long long)s->timebase, (long long)s->query_time, s->raw_available ? "true" : "false",
         (long long)s->qpc_before, (long long)s->qpc_after);
    out_mark(o, &s->utc_before); outf(o, ",\"utc_after\":"); out_mark(o, &s->utc_after);
    outf(o, "},\"collection_mode\":\"explicit_provider_paths\",\"topology_unchanged\":%s,"
         "\"topology_before\":", s->topology_unchanged ? "true" : "false");
    out_topology(o, counters, &s->topology_before); outf(o, ",\"topology_after\":");
    out_topology(o, counters, &s->topology_after); outf(o, ",\"raw\":[");
    for (i = 0; i < s->count && !o->failed; ++i) {
        const RAW_ITEM *item = (RAW_ITEM *)s->buffer + i;
        const PDH_RAW_COUNTER *r = &item->RawValue;
        if (i) outf(o, ",");
        outf(o, "{\"counter_index\":%lu,\"raw_value_code\":%lu,\"metadata_code\":%lu,"
             "\"timebase_code\":%lu,\"counter_type\":%lu,\"timebase\":\"%lld\"",
             item->source->registry_index, item->raw_code, item->metadata_code,
             item->timebase_code, item->type, (long long)item->timebase);
        outf(o, ",\"status\":%lu,\"filetime_100ns\":\"%llu\",\"first\":\"%lld\","
             "\"second\":\"%lld\",\"multi_count\":%lu}", r->CStatus,
             (unsigned long long)raw_time(r), (long long)r->FirstValue,
             (long long)r->SecondValue, r->MultiCount);
    }
    outf(o, "]}");
}

static ULONGLONG out_pairs(OUTPUT *o,
                          const SNAPSHOT *prev, const SNAPSHOT *curr)
{
    DWORD p = 0, c = 0, np = prev ? prev->count : 0, nc = curr->count, emitted = 0;
    ULONGLONG unresolved = 0;
    outf(o, "[");
    while ((p < np || c < nc) && !o->failed) {
        DWORD pb = p, cb = c, pc, cc, calc = NOT_CALLED, cooked_status = NOT_CALLED;
        const WCHAR *name;
        const char *status = "unresolved", *reason = "missing_previous";
        PDH_FMT_COUNTERVALUE cooked;
        BOOL value_available = FALSE;
        int cmp = p == np ? 1 : c == nc ? -1 :
                  wcscmp(prev->index[p].item->szName, curr->index[c].item->szName);
        name = cmp <= 0 ? prev->index[p].item->szName : curr->index[c].item->szName;
        while (p < np && !wcscmp(prev->index[p].item->szName, name)) ++p;
        while (c < nc && !wcscmp(curr->index[c].item->szName, name)) ++c;
        pc = p - pb; cc = c - cb;
        ZeroMemory(&cooked, sizeof(cooked));
        if (pc > 1 || cc > 1) reason = "duplicate_instance";
        else if (!cc) reason = "missing_current";
        else if (!valid_status(curr->index[cb].item->RawValue.CStatus) ||
                 !raw_time(&curr->index[cb].item->RawValue)) reason = "invalid_current_raw";
        else if (!prev) { status = "baseline"; reason = "first_point_no_interval"; }
        else if (!pc) reason = "new_or_reappeared_instance";
        else if (!valid_status(prev->index[pb].item->RawValue.CStatus) ||
                 !raw_time(&prev->index[pb].item->RawValue)) reason = "invalid_previous_raw";
        else if (wcscmp(curr->index[cb].item->source->path, prev->index[pb].item->source->path) ||
                 curr->index[cb].item->source != prev->index[pb].item->source ||
                 curr->index[cb].item->type != prev->index[pb].item->type ||
                 curr->index[cb].item->timebase != prev->index[pb].item->timebase ||
                 curr->metadata_code || prev->metadata_code || curr->timebase_code ||
                 prev->timebase_code || curr->type != prev->type ||
                 curr->timebase != prev->timebase) reason = "counter_metadata_changed_or_invalid";
        else {
            PDH_RAW_COUNTER *newer = &curr->index[cb].item->RawValue;
            PDH_RAW_COUNTER *older = &prev->index[pb].item->RawValue;
            if (raw_time(newer) <= raw_time(older) || newer->SecondValue <= older->SecondValue ||
                newer->FirstValue < older->FirstValue || newer->MultiCount != older->MultiCount)
                reason = "nonmonotonic_reset_or_reused_instance";
            else {
                /* Required API ordering: rawValue1 NEWER, rawValue2 OLDER. */
                calc = (DWORD)PdhCalculateCounterFromRawValue(curr->index[cb].item->source->handle,
                                  PDH_FMT_DOUBLE | PDH_FMT_NOCAP100, newer, older, &cooked);
                if (calc == ERROR_SUCCESS) {
                    cooked_status = cooked.CStatus;
                    value_available = _finite(cooked.doubleValue) != 0;
                }
                if (calc != ERROR_SUCCESS || !valid_status(cooked_status) || !value_available)
                    reason = "calculation_or_cooked_status_invalid";
                else if (cooked.doubleValue < 0) reason = "negative_cooked_value";
                else { status = "paired"; reason = "raw_continuity_only"; }
            }
        }
        if (!strcmp(status, "unresolved")) ++unresolved;
        if (emitted++) outf(o, ",");
        outf(o, "{\"counter_index\":%lu", cc ? curr->index[cb].item->source->registry_index :
             prev->index[pb].item->source->registry_index);
        outf(o, ",\"previous_index\":");
        if (pc == 1) outf(o, "%lu", prev->index[pb].original); else outf(o, "null");
        outf(o, ",\"current_index\":");
        if (cc == 1) outf(o, "%lu", curr->index[cb].original); else outf(o, "null");
        outf(o, ",\"previous_matches\":%lu,\"current_matches\":%lu,\"status\":\"%s\","
             "\"reason\":\"%s\",\"calculate_code\":%lu,\"cooked_status\":%lu,\"cooked\":",
             pc, cc, status, reason, calc, cooked_status);
        if (value_available) outf(o, "%.17g", cooked.doubleValue); else outf(o, "null");
        outf(o, "}");
    }
    outf(o, "]");
    /* An empty/unavailable snapshot is a coverage ambiguity, never zero GPU use. */
    if (!curr->raw_available || !curr->count || (prev && (!prev->raw_available || !prev->count)))
        ++unresolved;
    return unresolved;
}

static ULONGLONG record_bound(const COUNTERS *counters, const SNAPSHOT *prev,
                              const SNAPSHOT *curr, BOOL include_registry)
{
    DWORD i;
    ULONGLONG bytes = 4096;
    const SNAPSHOT *sets[2] = {prev, curr};
    /* Variable counter strings appear once in the first-point registry. Raw and
     * union pairs retain fixed-width values, status text and registry indices.
     * Each topology occurrence is an index; unknown paths retain literal text.
     * Reserve the entire complete row before writing any bytes. */
    if (include_registry) for (i = 0; i < counters->count; ++i) {
        const EXPLICIT_COUNTER *entry = &counters->items[i];
        bytes += ((ULONGLONG)wcslen(entry->instance) + (ULONGLONG)wcslen(entry->path) +
                  (ULONGLONG)wcslen(entry->parsed_instance)) * 6 + 256;
    }
    for (i = 0; i < 2; ++i) if (sets[i]) {
        DWORD j;
        const TOPOLOGY *topologies[2] = {&sets[i]->topology_before, &sets[i]->topology_after};
        /* 1024 covers one raw item plus its possible separate union pair,
         * including all DWORD/LONGLONG decimal digits and fixed reason text. */
        bytes += (ULONGLONG)sets[i]->count * 1024;
        for (j = 0; j < 2; ++j) {
            DWORD k;
            const WCHAR *p = topologies[j]->buffer;
            for (k = 0; k < topologies[j]->count; ++k) {
                bytes += 16; /* One DWORD/null index, comma and margin. */
                if (!find_counter(counters, p)) bytes += (ULONGLONG)wcslen(p) * 6 + 128;
                p += wcslen(p) + 1;
            }
        }
    }
    return bytes;
}

static BOOL emit_point(OUTPUT *o, const COUNTERS *counters, const SNAPSHOT *prev,
                       const SNAPSHOT *curr, DWORD index, BOOL baseline, BOOL final_sample,
                       const char *stop_kind, ULONGLONG *unresolved)
{
    LONGLONG gap = prev ? curr->qpc_after - prev->qpc_after : 0;
    ULONGLONG bound = record_bound(counters, prev, curr, index == 0);
    if (bound > LINE_BYTES || o->bytes > OUTPUT_BYTES - TERMINAL_RESERVE ||
        bound > OUTPUT_BYTES - TERMINAL_RESERVE - o->bytes) {
        fail(o->guard, R_OUTPUT_CAP); return FALSE;
    }
    outf(o, "{\"schema\":\"" SCHEMA "\",\"event\":\"%s\",\"index\":%lu,"
         "\"counter_path\":", baseline ? "baseline" :
         curr->query_code || curr->raw_array_code || curr->metadata_code || curr->timebase_code ?
         "collection_error" : "sample", index);
    out_wide(o, COUNTER_PATH);
    outf(o, ",\"qpc_frequency\":\"%lld\",\"final_sample\":%s,\"stop_kind\":\"%s\","
         "\"sample_gap_qpc\":\"%lld\",\"sample_gap_ms\":%.3f,\"sample_gap_valid\":%s,"
         "\"pair_continuity_only\":true,\"instance_generation_verified\":false,"
         "\"raw_timestamp_semantics\":\"provider_FILETIME_preserved\","
         "\"counter_encoding\":\"explicit-registry-v1\"",
         (long long)o->guard->frequency.QuadPart, final_sample ? "true" : "false", stop_kind,
         (long long)gap, 1000.0 * (double)gap / (double)o->guard->frequency.QuadPart,
         gap >= 0 && gap <= o->guard->frequency.QuadPart * SAMPLE_GAP_MS / 1000 ? "true" : "false");
    if (index == 0) { outf(o, ",\"counter_registry\":"); out_registry(o, counters); }
    outf(o, ",\"previous\":"); out_snapshot(o, counters, prev);
    outf(o, ",\"current\":"); out_snapshot(o, counters, curr);
    outf(o, ",\"pairs\":"); *unresolved = out_pairs(o, prev, curr);
    outf(o, ",\"unresolved_pairs\":%llu,\"acceptance\":false,\"attribution_qualified\":false}\n",
         (unsigned long long)*unresolved);
    return flush_output(o);
}

static BOOL parse_seconds(const WCHAR *s, ULONGLONG *value)
{
    ULONGLONG n = 0;
    size_t i;
    if (!s[0]) return FALSE;
    for (i = 0; s[i]; ++i) {
        if (s[i] < L'0' || s[i] > L'9' || n > 120) return FALSE;
        n = n * 10 + (s[i] - L'0');
    }
    if (n < 1 || n > 120) return FALSE;
    *value = n; return TRUE;
}

static BOOL absolute_path(const WCHAR *input, WCHAR *output)
{
    size_t i, n = wcslen(input);
    DWORD got;
    BOOL drive = n >= 3 && ((input[0] >= L'A' && input[0] <= L'Z') ||
                           (input[0] >= L'a' && input[0] <= L'z')) && input[1] == L':' &&
                           (input[2] == L'\\' || input[2] == L'/');
    BOOL unc = n >= 5 && input[0] == L'\\' && input[1] == L'\\' && input[2] != L'?' &&
               input[2] != L'.' && input[2] != L'\\';
    if ((!drive && !unc) || n >= PATH_CHARS || input[n - 1] == L'\\' ||
        input[n - 1] == L'/' || input[n - 1] == L'.' || input[n - 1] == L' ') return FALSE;
    for (i = 0; i < n; ++i)
        if (input[i] < 0x20 || wcschr(L"\"<>|*?", input[i]) ||
            (input[i] == L':' && !(drive && i == 1))) return FALSE;
    got = GetFullPathNameW(input, PATH_CHARS, output, NULL);
    return got != 0 && got < PATH_CHARS;
}

static int marker_state(const WCHAR *path, DWORD *code)
{
    DWORD attrs = GetFileAttributesW(path);
    if (attrs != INVALID_FILE_ATTRIBUTES) {
        *code = ERROR_SUCCESS;
        return attrs & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT) ? -1 : 1;
    }
    *code = GetLastError();
    return *code == ERROR_FILE_NOT_FOUND || *code == ERROR_PATH_NOT_FOUND ? 0 : -1;
}

static BOOL allocate_topology(TOPOLOGY *t)
{
    t->buffer = (WCHAR *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, EXPAND_BYTES);
    t->index = (WCHAR **)HeapAlloc(GetProcessHeap(), 0, MAX_ITEMS * sizeof(WCHAR *));
    t->code = NOT_CALLED;
    return t->buffer && t->index;
}

static void free_topology(TOPOLOGY *t)
{
    if (t->index) HeapFree(GetProcessHeap(), 0, t->index);
    if (t->buffer) HeapFree(GetProcessHeap(), 0, t->buffer);
}

int wmain(int argc, WCHAR **argv)
{
    GUARD g;
    OUTPUT out;
    SNAPSHOT storage[2], *prev = &storage[0], *curr = &storage[1], *swap;
    PDH_HQUERY query = NULL;
    PDH_HCOUNTER counter = NULL;
    COUNTERS counters;
    void *info = NULL, *parse = NULL;
    HANDLE thread = NULL;
    WCHAR stop[PATH_CHARS] = L"";
    ULONGLONG seconds = 0, unresolved = 0, unresolved_total = 0, output_before_terminal;
    DWORD open_code = NOT_CALLED, add_code = NOT_CALLED, close_code = NOT_CALLED;
    DWORD marker_code = NOT_CALLED, samples = 0;
    BOOL plan = FALSE, got_stop = FALSE, got_seconds = FALSE, baseline_emitted = FALSE;
    BOOL query_closed = FALSE, joined = FALSE, monitor_available = TRUE, ended = FALSE, success;
    const char *stop_kind = "error";
    LONGLONG deadline = 0, next = 0;
    MARK begin, end;
    int i;
    ZeroMemory(&g, sizeof(g)); ZeroMemory(&out, sizeof(out)); ZeroMemory(storage, sizeof(storage));
    InitializeSRWLock(&g.memory_lock);
    ZeroMemory(&counters, sizeof(counters));
    counters.localized_code = counters.remove_code = counters.baseline.code = NOT_CALLED;
    out.guard = &g; g.min_physical = g.min_commit = UINT64_MAX;
    if (!QueryPerformanceFrequency(&g.frequency) || g.frequency.QuadPart <= 0) g.reason = R_CLOCK;
    for (i = 1; i < argc && !g.reason; ++i) {
        if (!wcscmp(argv[i], L"--plan") && !plan) plan = TRUE;
        else if (!wcscmp(argv[i], L"--stop") && !got_stop && i + 1 < argc) {
            got_stop = absolute_path(argv[++i], stop); if (!got_stop) g.reason = R_CLI;
        } else if (!wcscmp(argv[i], L"--seconds") && !got_seconds && i + 1 < argc) {
            got_seconds = parse_seconds(argv[++i], &seconds); if (!got_seconds) g.reason = R_CLI;
        } else g.reason = R_CLI;
    }
    if (!got_stop || !got_seconds) g.reason = R_CLI;
    mark_now(&begin);
    /* Binary stdout makes the counted 64 MiB output cap include exact bytes. */
    if (_setmode(_fileno(stdout), _O_BINARY) == -1) fail(&g, R_IO);
    if (plan || g.reason) { if (plan) stop_kind = "plan"; goto report; }
    if (marker_state(stop, &marker_code) != 0) { fail(&g, R_MARKER); goto cleanup; }
    g.abort_event = CreateEventW(NULL, TRUE, FALSE, NULL);
    g.done_event = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (!g.abort_event || !g.done_event) { fail(&g, R_THREAD); goto cleanup; }
    if (!memory_sample(&g, TRUE)) goto cleanup;
    for (i = 0; i < 2; ++i) {
        storage[i].buffer = HeapAlloc(GetProcessHeap(), 0, RAW_BYTES);
        storage[i].index = (INDEX *)HeapAlloc(GetProcessHeap(), 0, MAX_ITEMS * sizeof(INDEX));
        if (!storage[i].buffer || !storage[i].index ||
            !allocate_topology(&storage[i].topology_before) ||
            !allocate_topology(&storage[i].topology_after)) { fail(&g, R_ALLOC); goto cleanup; }
    }
    info = HeapAlloc(GetProcessHeap(), 0, INFO_BYTES);
    parse = HeapAlloc(GetProcessHeap(), 0, INFO_BYTES);
    counters.items = (EXPLICIT_COUNTER *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY,
                                                       MAX_ITEMS * sizeof(EXPLICIT_COUNTER));
    counters.name_pool = (WCHAR *)HeapAlloc(GetProcessHeap(), 0, NAME_POOL_BYTES);
    if (!info || !parse || !counters.items || !counters.name_pool ||
        !allocate_topology(&counters.baseline)) { fail(&g, R_ALLOC); goto cleanup; }
    if (!memory_sample(&g, TRUE)) goto cleanup;
    thread = CreateThread(NULL, 0, monitor_thread, &g, 0, NULL);
    if (!thread) { fail(&g, R_THREAD); goto cleanup; }
    if (g.reason) goto cleanup;
    open_code = (DWORD)PdhOpenQueryW(NULL, 0, &query);
    if (open_code != ERROR_SUCCESS) { query = NULL; fail(&g, R_PDH); goto cleanup; }
    add_code = (DWORD)PdhAddEnglishCounterW(query, COUNTER_PATH, 0, &counter);
    if (add_code != ERROR_SUCCESS) { fail(&g, R_PDH); goto cleanup; }
    if (!prepare_counters(&g, query, counter, &counters, info, parse, &add_code)) goto cleanup;
    counter = NULL; /* Removed localization-only handle; query owns exact handles. */
    if (!memory_sample(&g, FALSE)) goto cleanup;
    if (marker_state(stop, &marker_code) != 0) { fail(&g, R_MARKER); goto cleanup; }
    {
        BOOL collected = collect(&g, query, &counters, prev, info);
        if (!emit_point(&out, &counters, NULL, prev, 0, collected, FALSE, "none", &unresolved))
            goto cleanup;
        unresolved_total += unresolved;
        baseline_emitted = collected;
        if (!collected || g.reason) goto cleanup;
    }
    deadline = prev->qpc_after + (LONGLONG)seconds * g.frequency.QuadPart;
    next = prev->qpc_before + g.frequency.QuadPart * SAMPLE_MS / 1000;
    while (!g.reason) {
        LARGE_INTEGER now;
        DWORD wait;
        int marker = marker_state(stop, &marker_code);
        BOOL final_sample;
        if (marker < 0) { fail(&g, R_MARKER); break; }
        QueryPerformanceCounter(&now);
        final_sample = marker == 1 || now.QuadPart >= deadline;
        if (final_sample || now.QuadPart >= next) {
            BOOL collected;
            stop_kind = final_sample ? (marker == 1 ? "marker" : "deadline") : "none";
            collected = collect(&g, query, &counters, curr, info);
            ++samples;
            if (curr->qpc_after < prev->qpc_after || curr->qpc_after - prev->qpc_after >
                g.frequency.QuadPart * SAMPLE_GAP_MS / 1000) fail(&g, R_SAMPLE_GAP);
            if (!emit_point(&out, &counters, prev, curr, samples, FALSE, final_sample,
                            stop_kind, &unresolved)) break;
            unresolved_total += unresolved;
            if (!collected || g.reason) break;
            swap = prev; prev = curr; curr = swap;
            if (final_sample) { ended = TRUE; break; }
            next = prev->qpc_before + g.frequency.QuadPart * SAMPLE_MS / 1000;
        }
        wait = WaitForSingleObject(g.abort_event, MEMORY_POLL_MS);
        if (wait != WAIT_TIMEOUT && wait != WAIT_OBJECT_0) { fail(&g, R_THREAD); break; }
    }

cleanup:
    /* This process owns exactly this query; closing it releases its own counters. */
    if (query) {
        close_code = (DWORD)PdhCloseQuery(query);
        query_closed = close_code == ERROR_SUCCESS;
        if (!query_closed) fail(&g, R_CLOSE);
    }
    if (thread) {
        SetEvent(g.done_event); joined = WaitForSingleObject(thread, 1000) == WAIT_OBJECT_0;
        if (!joined) fail(&g, R_THREAD);
        monitor_available = joined; CloseHandle(thread);
    }
    for (i = 0; i < 2; ++i) {
        if (storage[i].index) HeapFree(GetProcessHeap(), 0, storage[i].index);
        if (storage[i].buffer) HeapFree(GetProcessHeap(), 0, storage[i].buffer);
        free_topology(&storage[i].topology_before);
        free_topology(&storage[i].topology_after);
    }
    if (info) HeapFree(GetProcessHeap(), 0, info);
    if (parse) HeapFree(GetProcessHeap(), 0, parse);
    if (counters.items) HeapFree(GetProcessHeap(), 0, counters.items);
    if (counters.name_pool) HeapFree(GetProcessHeap(), 0, counters.name_pool);
    free_topology(&counters.baseline);
    /* A failed join leaves thread-owned events until process exit. */
    if (monitor_available) {
        if (g.done_event) CloseHandle(g.done_event);
        if (g.abort_event) CloseHandle(g.abort_event);
        g.abort_event = g.done_event = NULL;
    }

report:
    mark_now(&end);
    output_before_terminal = out.bytes;
    success = !plan && !g.reason && baseline_emitted && ended && joined && query_closed;
    if (g.reason) stop_kind = plan ? "plan" : "error";
    outf(&out, "{\"schema\":\"" SCHEMA "\",\"event\":\"terminal\",\"status\":\"%s\","
         "\"reason\":\"%s\",\"stop_kind\":\"%s\",\"stop\":",
         success ? "complete" : plan && !g.reason ? "planned" : "invalid",
         reason_name(g.reason), stop_kind);
    out_wide(&out, stop);
    outf(&out, ",\"seconds\":%llu,\"baseline_emitted\":%s,\"samples\":%lu,"
         "\"unresolved_pairs_total\":\"%llu\",\"pair_continuity_only\":true,"
         "\"instance_generation_verified\":false,\"query_closed\":%s,"
         "\"query_open_code\":%lu,\"counter_add_code\":%lu,\"query_close_code\":%lu,"
         "\"marker_code\":%lu,\"not_called_code\":4294967295,\"pdh_query_called\":%s",
         (unsigned long long)seconds, baseline_emitted ? "true" : "false", samples,
         (unsigned long long)unresolved_total, query_closed ? "true" : "false", open_code,
         add_code, close_code, marker_code, open_code != NOT_CALLED ? "true" : "false");
    outf(&out, ","
         "\"nominal_sample_ms\":500,\"sample_gap_cap_ms\":1500,\"output_cap_bytes\":%llu,"
         "\"output_bytes_before_terminal\":\"%llu\",\"allocation_cap_bytes\":%lu,"
         "\"success\":%s,\"acceptance\":false,\"attribution_qualified\":false",
         (unsigned long long)OUTPUT_BYTES, (unsigned long long)output_before_terminal,
         (unsigned long)OWNED_ALLOCATION_BYTES,
         success ? "true" : "false");
    outf(&out, ",\"collection_mode\":\"explicit_provider_paths\",\"counter_encoding\":\"explicit-registry-v1\","
         "\"line_cap_bytes\":%llu,\"explicit_counter_count\":%lu,"
         "\"localized_path_code\":%lu,\"localization_counter_remove_code\":%lu,"
         "\"counter_occurrence_identity_only\":true,\"localized_wildcard_path\":",
         (unsigned long long)LINE_BYTES, counters.count, counters.localized_code, counters.remove_code);
    out_wide(&out, counters.localized);
    outf(&out, ","
         "\"monitor\":{\"available\":%s,\"samples\":%lu,\"memory_code\":%lu,"
         "\"min_physical_bytes\":\"%llu\",\"min_commit_bytes\":\"%llu\","
         "\"max_private_commit_bytes\":\"%llu\",\"max_gap_ms\":%.3f},\"qpc_frequency\":\"%lld\",\"begin\":",
         monitor_available && g.samples ? "true" : "false",
         monitor_available ? g.samples : 0, monitor_available ? g.memory_code : 0,
         (unsigned long long)(monitor_available && g.samples ? g.min_physical : 0),
         (unsigned long long)(monitor_available && g.samples ? g.min_commit : 0),
         (unsigned long long)(monitor_available ? g.max_private : 0),
         monitor_available && g.frequency.QuadPart ?
           1000.0 * (double)g.max_gap_qpc / (double)g.frequency.QuadPart : 0,
         (long long)g.frequency.QuadPart);
    out_mark(&out, &begin); outf(&out, ",\"end\":"); out_mark(&out, &end); outf(&out, "}\n");
    if (!flush_output(&out)) {
        fprintf(stderr, "GPU PDH collector: receipt write/flush failed or exceeded cap; output is invalid.\n");
        success = FALSE;
    }
    if (!monitor_available) ExitProcess(1); /* Monitor still references this stack. */
    return success || (plan && !g.reason && !out.failed) ? 0 : 1;
}
