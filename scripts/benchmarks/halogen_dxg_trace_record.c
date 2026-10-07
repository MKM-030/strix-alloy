/* Source-only bounded DxgKrnl recorder. Link Advapi32.lib and Psapi.lib.
 * No privilege changes, process launches, session enumeration or name-based stop.
 * StartTrace/EnableTraceEx2/ControlTrace are documented Microsoft controller APIs:
 * https://learn.microsoft.com/windows/win32/api/evntrace/nf-evntrace-starttracew
 * https://learn.microsoft.com/windows/win32/api/evntrace/nf-evntrace-enabletraceex2
 * https://learn.microsoft.com/windows/win32/api/evntrace/nf-evntrace-controltracew
 * https://learn.microsoft.com/windows/win32/api/evntrace/ns-evntrace-event_trace_properties
 * https://learn.microsoft.com/windows/win32/etw/logging-mode-constants
 * NO_PER_PROCESSOR_BUFFERING omits processor numbers and may increase contention
 * at high event rates. Zero loss does not establish attribution or a speed gain.
 * --capture-state requests provider rundown before and after the work window.
 * The API result is retained; even success does not prove rundown completeness.
 * Ctrl+C/Break signal main-thread cleanup. Forced termination cannot guarantee it.
 */
#define WIN32_LEAN_AND_MEAN
#define _WIN32_WINNT 0x0602
#include <windows.h>
#include <evntrace.h>
#include <evntprov.h>
#include <psapi.h>
#include <stdio.h>
#include <wchar.h>
#include <wctype.h>
#include <stdint.h>
#include <stdlib.h>
#include <errno.h>
#include <stddef.h>

#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "psapi.lib")

#define PATH_CHARS 1024
#define GIB (UINT64_C(1024) * 1024 * 1024)
#define POOL_BYTES (UINT64_C(64) * 64 * 1024)
#define FILE_BYTES (UINT64_C(64) * 1024 * 1024)
#define PRIVATE_BYTES (UINT64_C(16) * 1024 * 1024)
#define KEYWORD_MASK UINT64_C(0x04900845) /* Retained DxgKrnl keyword inventory. */
#define NOT_CALLED ((ULONG)0xffffffffu)
#define POLL_MS 100u
#define MAX_GAP_MS 250u

static const WCHAR SESSION_NAME[] = L"StrixAlloy-GpuCopy";
static WCHAR session_name[64] = L"StrixAlloy-GpuCopy";
static const GUID DXG_PROVIDER = {
    0x802ec45a, 0x1e99, 0x4b83, {0x99, 0x20, 0x87, 0xc9, 0x82, 0x77, 0xba, 0x9d}
};

typedef struct {
    EVENT_TRACE_PROPERTIES p;
    WCHAR session[64];
    WCHAR file[PATH_CHARS];
} PROPERTIES;

typedef struct {
    LONGLONG before, after;
    ULONGLONG utc;
    SYSTEMTIME st;
} MARK;

enum REASON {
    R_NONE, R_CLI, R_CLOCK, R_OUTPUT, R_START_MEMORY, R_GUARD_API,
    R_RESERVE, R_PRIVATE, R_GAP, R_CANCEL, R_START, R_QUERY,
    R_POOL, R_LOSS, R_FILE, R_ENABLE, R_STOP, R_THREAD, R_RECEIPT
};

typedef struct {
    HANDLE abort_event, done_event;
    LARGE_INTEGER frequency;
    volatile LONG reason;
    ULONG memory_code;
    ULONGLONG min_physical, min_commit, max_private;
    LONGLONG last_qpc, max_gap_qpc;
    ULONG samples;
} GUARD;

typedef struct {
    ULONG buffer_kib, minimum, maximum, allocated, free_buffers;
    ULONG events_lost, log_buffers_lost, realtime_buffers_lost, written;
    BOOL available, pool_observed;
} STATS;

static HANDLE g_abort_event;
static volatile LONG g_cancelled;

static const char *reason_name(LONG reason)
{
    static const char *const names[] = {
        "none", "invalid_cli", "clock_failed", "output_refused",
        "start_reserve_below_22gib", "memory_query_failed",
        "runtime_reserve_below_18gib", "private_commit_above_16mib",
        "monitor_gap_above_250ms", "cancelled", "start_failed",
        "query_failed", "buffer_pool_rejected", "trace_loss",
        "file_full_or_size_query_failed", "enable_failed", "stop_failed",
        "monitor_thread_failed", "receipt_io_failed"
    };
    return reason >= R_NONE && reason <= R_RECEIPT ? names[reason] : "unknown";
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

static void print_mark(const MARK *m)
{
    printf("{\"qpc_before\":%lld,\"qpc_after\":%lld,\"utc_filetime_100ns\":%llu,"
           "\"utc\":\"%04u-%02u-%02uT%02u:%02u:%02u.%03uZ\"}",
           (long long)m->before, (long long)m->after, (unsigned long long)m->utc,
           (unsigned)m->st.wYear, (unsigned)m->st.wMonth, (unsigned)m->st.wDay,
           (unsigned)m->st.wHour, (unsigned)m->st.wMinute, (unsigned)m->st.wSecond,
           (unsigned)m->st.wMilliseconds);
}

static void json_wide(const WCHAR *s)
{
    char utf8[PATH_CHARS * 4];
    int n = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, s, -1,
                               utf8, (int)sizeof(utf8), NULL, NULL);
    int i;
    putchar('"');
    if (n > 0) for (i = 0; i < n - 1; ++i) {
        unsigned char c = (unsigned char)utf8[i];
        if (c == '"' || c == '\\') { putchar('\\'); putchar(c); }
        else if (c < 0x20) printf("\\u%04x", (unsigned)c);
        else putchar(c);
    }
    putchar('"');
}

static void json_guid(const GUID *guid)
{
    if (!guid) { printf("null"); return; }
    printf("\"%08lx-%04x-%04x-%02x%02x-%02x%02x%02x%02x%02x%02x\"",
           (unsigned long)guid->Data1, (unsigned)guid->Data2, (unsigned)guid->Data3,
           (unsigned)guid->Data4[0], (unsigned)guid->Data4[1],
           (unsigned)guid->Data4[2], (unsigned)guid->Data4[3],
           (unsigned)guid->Data4[4], (unsigned)guid->Data4[5],
           (unsigned)guid->Data4[6], (unsigned)guid->Data4[7]);
}

static BOOL session_receipt(const char *event, TRACEHANDLE trace, const WCHAR *path,
                            const GUID *guid, ULONG query_code, const MARK *when)
{
    /* Flush ownership evidence before enabling the provider. These JSONL records
     * support manual review after forced termination; they never adopt a session. */
    printf("{\"event\":\"%s\",\"session\":", event);
    json_wide(session_name);
    printf(",\"trace_handle\":\"0x%016llx\",\"output\":",
           (unsigned long long)trace);
    json_wide(path); printf(",\"session_guid\":"); json_guid(guid);
    printf(",\"query_code\":%lu,\"at\":", query_code);
    print_mark(when); printf("}\n");
    /* stdio preserves its error indicator across all preceding writes. Always
     * attempt the flush, then reject either write or flush failure. */
    {
        int flush_code = fflush(stdout);
        return flush_code == 0 && !ferror(stdout);
    }
}

static void abort_guard(GUARD *g, LONG reason)
{
    InterlockedCompareExchange(&g->reason, reason, R_NONE);
    SetEvent(g->abort_event);
}

static BOOL WINAPI console_handler(DWORD type)
{
    if (type != CTRL_C_EVENT && type != CTRL_BREAK_EVENT) return FALSE;
    InterlockedExchange(&g_cancelled, 1);
    if (g_abort_event) SetEvent(g_abort_event);
    return TRUE;
}

static BOOL memory_sample(GUARD *g, BOOL admission)
{
    MEMORYSTATUSEX ms;
    PERFORMANCE_INFORMATION pi;
    PROCESS_MEMORY_COUNTERS_EX pm;
    LARGE_INTEGER q;
    ULONGLONG commit;
    LONGLONG gap;
    ZeroMemory(&ms, sizeof(ms)); ms.dwLength = (DWORD)sizeof(ms);
    ZeroMemory(&pi, sizeof(pi)); pi.cb = (DWORD)sizeof(pi);
    ZeroMemory(&pm, sizeof(pm)); pm.cb = (DWORD)sizeof(pm);
    if (!GlobalMemoryStatusEx(&ms) || !GetPerformanceInfo(&pi, (DWORD)sizeof(pi)) ||
        !GetProcessMemoryInfo(GetCurrentProcess(), (PROCESS_MEMORY_COUNTERS *)&pm,
                              (DWORD)sizeof(pm))) {
        g->memory_code = GetLastError();
        abort_guard(g, R_GUARD_API); return FALSE;
    }
    if (pi.CommitLimit < pi.CommitTotal || !pi.PageSize) {
        g->memory_code = ERROR_INVALID_DATA;
        abort_guard(g, R_GUARD_API); return FALSE;
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
    if (gap > g->frequency.QuadPart * MAX_GAP_MS / 1000) abort_guard(g, R_GAP);
    if (ms.ullAvailPhys < (admission ? 22 : 18) * GIB ||
        commit < (admission ? 22 : 18) * GIB)
        abort_guard(g, admission ? R_START_MEMORY : R_RESERVE);
    if ((ULONGLONG)pm.PrivateUsage > PRIVATE_BYTES) abort_guard(g, R_PRIVATE);
    return g->reason == R_NONE;
}

static DWORD WINAPI monitor_thread(void *context)
{
    GUARD *g = (GUARD *)context;
    for (;;) {
        DWORD wait;
        memory_sample(g, FALSE);
        wait = WaitForSingleObject(g->done_event, POLL_MS);
        if (wait == WAIT_OBJECT_0) break;
        if (wait != WAIT_TIMEOUT) { abort_guard(g, R_THREAD); break; }
    }
    memory_sample(g, FALSE);
    return 0;
}

static void init_properties(PROPERTIES *b, const WCHAR *output, BOOL start)
{
    ZeroMemory(b, sizeof(*b));
    b->p.Wnode.BufferSize = (ULONG)sizeof(*b);
    b->p.LoggerNameOffset = (ULONG)offsetof(PROPERTIES, session);
    b->p.LogFileNameOffset = (ULONG)offsetof(PROPERTIES, file);
    if (start) {
        b->p.Wnode.Flags = WNODE_FLAG_TRACED_GUID;
        b->p.Wnode.ClientContext = 1; /* QPC; ordinary session GUID is generated. */
        b->p.BufferSize = 64; /* KiB, not Wnode.BufferSize bytes. */
        b->p.MinimumBuffers = 64; b->p.MaximumBuffers = 64;
        b->p.LogFileMode = EVENT_TRACE_FILE_MODE_SEQUENTIAL |
                           EVENT_TRACE_NO_PER_PROCESSOR_BUFFERING;
        b->p.MaximumFileSize = 64; /* MiB; USE_KBYTES_FOR_SIZE is not set. */
        b->p.FlushTimer = 1;
        wcscpy_s(b->session, _countof(b->session), session_name);
        wcscpy_s(b->file, _countof(b->file), output);
    }
}

static void save_stats(STATS *s, const EVENT_TRACE_PROPERTIES *p, BOOL pool_observed)
{
    s->buffer_kib = p->BufferSize; s->minimum = p->MinimumBuffers;
    s->maximum = p->MaximumBuffers; s->allocated = p->NumberOfBuffers;
    s->free_buffers = p->FreeBuffers; s->events_lost = p->EventsLost;
    s->log_buffers_lost = p->LogBuffersLost;
    s->realtime_buffers_lost = p->RealTimeBuffersLost;
    s->written = p->BuffersWritten; s->available = TRUE;
    s->pool_observed = pool_observed;
}

static void validate_loss(GUARD *g, const STATS *s)
{
    if (s->events_lost || s->log_buffers_lost || s->realtime_buffers_lost)
        abort_guard(g, R_LOSS);
}

static void validate_stats(GUARD *g, const STATS *s)
{
    ULONGLONG size = (ULONGLONG)s->buffer_kib * 1024;
    if (!size || !s->allocated || !s->minimum || !s->maximum ||
        s->minimum != s->maximum || s->allocated > s->maximum ||
        size * s->minimum > POOL_BYTES || size * s->maximum > POOL_BYTES ||
        size * s->allocated > POOL_BYTES) abort_guard(g, R_POOL);
    validate_loss(g, s);
}

static void print_stats(const STATS *s)
{
    if (!s->available) { printf("null"); return; }
    printf("{\"statistics_available\":true,\"pool_observed\":%s,"
           "\"events_lost\":%lu,\"log_buffers_lost\":%lu,"
           "\"realtime_buffers_lost\":%lu,\"buffers_written\":%lu",
           s->pool_observed ? "true" : "false", s->events_lost,
           s->log_buffers_lost, s->realtime_buffers_lost, s->written);
    if (s->pool_observed)
        printf(",\"buffer_kib\":%lu,\"minimum\":%lu,\"maximum\":%lu,"
               "\"allocated\":%lu,\"free\":%lu,\"pool_bytes\":%llu,\"adjusted\":%s",
               s->buffer_kib, s->minimum, s->maximum, s->allocated, s->free_buffers,
               (unsigned long long)s->buffer_kib * 1024 * s->allocated,
               s->buffer_kib != 64 || s->minimum != 64 || s->maximum != 64 ||
               s->allocated != 64 ? "true" : "false");
    putchar('}');
}

static BOOL parse_u64(const WCHAR *s, int base, ULONGLONG *value)
{
    WCHAR *end;
    if (!s[0] || s[0] == L'-' || s[0] == L'+' || s[0] == L' ' || s[0] == L'\t')
        return FALSE;
    errno = 0; *value = _wcstoui64(s, &end, base);
    return errno != ERANGE && end != s && !*end;
}

static BOOL output_path(const WCHAR *input, WCHAR *output)
{
    size_t i, n = wcslen(input);
    DWORD got;
    BOOL drive = n >= 3 && ((input[0] >= L'A' && input[0] <= L'Z') ||
                            (input[0] >= L'a' && input[0] <= L'z')) &&
                 input[1] == L':' && (input[2] == L'\\' || input[2] == L'/');
    BOOL unc = n >= 5 && input[0] == L'\\' && input[1] == L'\\' &&
               input[2] != L'?' && input[2] != L'.' && input[2] != L'\\';
    if ((!drive && !unc) || n >= PATH_CHARS) return FALSE;
    for (i = 0; i < n; ++i)
        if (input[i] < 0x20 || wcschr(L"\"<>|*?", input[i]) ||
            (input[i] == L':' && !(drive && i == 1))) return FALSE;
    got = GetFullPathNameW(input, PATH_CHARS, output, NULL);
    if (!got || got >= PATH_CHARS || got < 4 || _wcsicmp(output + got - 4, L".etl"))
        return FALSE;
    return TRUE;
}

int wmain(int argc, WCHAR **argv)
{
    GUARD g;
    PROPERTIES props;
    STATS last = {0}, final = {0};
    MARK begin = {0}, start_return = {0}, enabling = {0}, enabled = {0}, stopping = {0};
    MARK stop_return = {0}, end = {0}, state_begin = {0}, state_return = {0};
    MARK final_state_begin = {0}, final_state_return = {0};
    TRACEHANDLE trace = 0;
    GUID session_guid = {0};
    HANDLE output = INVALID_HANDLE_VALUE, thread = NULL;
    WCHAR path[PATH_CHARS] = L"";
    WCHAR stop_path[PATH_CHARS] = L"";
    ULONGLONG seconds = 0, keywords = 0x845, number, file_size = 0;
    ULONG start_code = NOT_CALLED, enable_code = NOT_CALLED, query_code = NOT_CALLED;
    ULONG stop_code = NOT_CALLED, output_code = NOT_CALLED, stop_attempts = 0;
    ULONG state_code = NOT_CALLED, final_state_code = NOT_CALLED;
    BOOL plan = FALSE, got_output = FALSE, got_seconds = FALSE, got_keywords = FALSE;
    BOOL owned = FALSE, started = FALSE, closed = FALSE, interval_complete = FALSE;
    BOOL handler = FALSE, joined = FALSE, monitor_available = TRUE, success;
    BOOL session_guid_available = FALSE;
    BOOL capture_state = FALSE, stopped_by_marker = FALSE, got_stop = FALSE, got_session = FALSE;
    int i;
    ZeroMemory(&g, sizeof(g));
    g.min_physical = g.min_commit = UINT64_MAX;
    if (!QueryPerformanceFrequency(&g.frequency) || !g.frequency.QuadPart)
        g.reason = R_CLOCK;
    for (i = 1; i < argc && g.reason == R_NONE; ++i) {
        if (!wcscmp(argv[i], L"--plan") && !plan) plan = TRUE;
        else if (!wcscmp(argv[i], L"--capture-state") && !capture_state) capture_state = TRUE;
        else if (!wcscmp(argv[i], L"--session") && !got_session && i + 1 < argc) {
            const WCHAR *candidate = argv[++i];
            size_t length = wcslen(candidate), j;
            got_session = length > wcslen(SESSION_NAME) + 1 && length < _countof(session_name) &&
                          !wcsncmp(candidate, SESSION_NAME, wcslen(SESSION_NAME)) &&
                          candidate[wcslen(SESSION_NAME)] == L'-';
            for (j = wcslen(SESSION_NAME) + 1; got_session && j < length; ++j)
                if (!iswxdigit(candidate[j]) && candidate[j] != L'-') got_session = FALSE;
            if (!got_session) g.reason = R_CLI;
            else wcscpy_s(session_name, _countof(session_name), candidate);
        } else if (!wcscmp(argv[i], L"--stop-file") && !got_stop && i + 1 < argc) {
            const WCHAR *candidate = argv[++i];
            DWORD length = GetFullPathNameW(candidate, PATH_CHARS, stop_path, NULL);
            size_t n = wcslen(candidate);
            got_stop = n >= 3 && candidate[1] == L':' &&
                       (candidate[2] == L'\\' || candidate[2] == L'/') &&
                       length > 0 && length < PATH_CHARS;
            if (!got_stop) g.reason = R_CLI;
        }
        else if (!wcscmp(argv[i], L"--output") && !got_output && i + 1 < argc) {
            got_output = output_path(argv[++i], path);
            if (!got_output) g.reason = R_CLI;
        } else if (!wcscmp(argv[i], L"--seconds") && !got_seconds && i + 1 < argc) {
            got_seconds = parse_u64(argv[++i], 10, &seconds) && seconds >= 1 && seconds <= 30;
            if (!got_seconds) g.reason = R_CLI;
        } else if (!wcscmp(argv[i], L"--keywords") && !got_keywords && i + 1 < argc) {
            got_keywords = parse_u64(argv[++i], 0, &number) && number != 0 &&
                           !(number & ~KEYWORD_MASK);
            if (!got_keywords) g.reason = R_CLI; else keywords = number;
        } else g.reason = R_CLI;
    }
    if (!got_output || !got_seconds) g.reason = R_CLI;
    if (got_stop && (!_wcsicmp(stop_path, path) ||
                     GetFileAttributesW(stop_path) != INVALID_FILE_ATTRIBUTES)) g.reason = R_CLI;
    mark_now(&begin);
    if (plan || g.reason != R_NONE) goto report;

    g.abort_event = CreateEventW(NULL, TRUE, FALSE, NULL);
    g.done_event = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (!g.abort_event || !g.done_event) { g.reason = R_THREAD; goto cleanup; }
    if (!memory_sample(&g, TRUE)) goto cleanup;
    /* CREATE_NEW refuses an existing output atomically. Keep this read handle
     * open, permitting ETW's writer but not pathname deletion/replacement.
     * If ETW's sharing mode is incompatible, StartTrace fails and is reported. */
    output = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                         NULL, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
    if (output == INVALID_HANDLE_VALUE) {
        output_code = GetLastError(); g.reason = R_OUTPUT; goto cleanup;
    }
    output_code = ERROR_SUCCESS;
    g_abort_event = g.abort_event;
    handler = SetConsoleCtrlHandler(console_handler, TRUE);
    if (!handler) { g.reason = R_THREAD; goto cleanup; }
    /* Recheck the 22 GiB admission after output/handler setup, before the
     * monitor starts sharing this state and immediately before session start. */
    if (!memory_sample(&g, TRUE)) goto cleanup;
    thread = CreateThread(NULL, 0, monitor_thread, &g, 0, NULL);
    if (!thread) { g.reason = R_THREAD; goto cleanup; }
    if (g_cancelled || WaitForSingleObject(g.abort_event, 0) == WAIT_OBJECT_0) {
        if (g_cancelled) abort_guard(&g, R_CANCEL);
        goto cleanup;
    }
    init_properties(&props, path, TRUE);
    mark_now(&begin);
    start_code = StartTraceW(&trace, session_name, &props.p);
    mark_now(&start_return);
    if (start_code != ERROR_SUCCESS) { abort_guard(&g, R_START); goto cleanup; }
    owned = started = TRUE; /* ERROR_ALREADY_EXISTS never establishes ownership. */
    if (!session_receipt("session_started", trace, path, NULL, NOT_CALLED, &start_return)) {
        abort_guard(&g, R_RECEIPT);
        fprintf(stderr, "DxgKrnl recorder: startup receipt write/flush failed; owned-handle cleanup follows.\n");
        goto cleanup;
    }
    init_properties(&props, path, FALSE);
    query_code = ControlTraceW(trace, NULL, &props.p, EVENT_TRACE_CONTROL_QUERY);
    if (query_code != ERROR_SUCCESS) { abort_guard(&g, R_QUERY); goto cleanup; }
    session_guid = props.p.Wnode.Guid; session_guid_available = TRUE;
    {
        MARK queried;
        mark_now(&queried);
        if (!session_receipt("session_queried", trace, path, &session_guid,
                             query_code, &queried)) {
            abort_guard(&g, R_RECEIPT);
            fprintf(stderr, "DxgKrnl recorder: query receipt write/flush failed; owned-handle cleanup follows.\n");
            goto cleanup;
        }
    }
    save_stats(&last, &props.p, TRUE); validate_stats(&g, &last);
    if (g.reason != R_NONE || g_cancelled) goto cleanup;
    mark_now(&enabling);
    enable_code = EnableTraceEx2(trace, &DXG_PROVIDER, EVENT_CONTROL_CODE_ENABLE_PROVIDER,
                                TRACE_LEVEL_VERBOSE, keywords, 0, 100, NULL);
    if (enable_code != ERROR_SUCCESS) { abort_guard(&g, R_ENABLE); goto cleanup; }
    mark_now(&enabled);
    if (capture_state) {
        mark_now(&state_begin);
        state_code = EnableTraceEx2(trace, &DXG_PROVIDER, EVENT_CONTROL_CODE_CAPTURE_STATE,
                                   TRACE_LEVEL_VERBOSE, keywords, 0, 1000, NULL);
        mark_now(&state_return);
    }
    if (g_cancelled) abort_guard(&g, R_CANCEL);
    if (g.reason != R_NONE) goto cleanup;
    /* A flushed ready record gives the lifecycle coordinator an exact barrier.
     * It proves enable returned, never that the provider emitted full rundown. */
    {
        MARK ready;
        mark_now(&ready);
        printf("{\"event\":\"capture_ready\",\"session\":"); json_wide(session_name);
        printf(",\"enable_code\":%lu,\"capture_state_requested\":%s,"
               "\"capture_state_code\":%lu,\"qpc_frequency\":%lld,\"at\":",
               enable_code, capture_state ? "true" : "false", state_code,
               (long long)g.frequency.QuadPart);
        print_mark(&ready); printf("}\n");
        if (fflush(stdout) || ferror(stdout)) { abort_guard(&g, R_RECEIPT); goto cleanup; }
    }
    for (;;) {
        LARGE_INTEGER now, size;
        DWORD wait;
        QueryPerformanceCounter(&now);
        if (g_cancelled) abort_guard(&g, R_CANCEL);
        if (g.reason != R_NONE) break;
        if (got_stop && GetFileAttributesW(stop_path) != INVALID_FILE_ATTRIBUTES) {
            stopped_by_marker = TRUE; interval_complete = TRUE; break;
        }
        if (!GetFileSizeEx(output, &size) || size.QuadPart < 0) {
            abort_guard(&g, R_FILE); break;
        }
        file_size = (ULONGLONG)size.QuadPart;
        if (file_size >= FILE_BYTES) { abort_guard(&g, R_FILE); break; }
        init_properties(&props, path, FALSE);
        query_code = ControlTraceW(trace, NULL, &props.p, EVENT_TRACE_CONTROL_QUERY);
        if (query_code != ERROR_SUCCESS) { abort_guard(&g, R_QUERY); break; }
        save_stats(&last, &props.p, TRUE); validate_stats(&g, &last);
        if (g.reason != R_NONE) break;
        if (now.QuadPart - enabled.after >= (LONGLONG)seconds * g.frequency.QuadPart) {
            interval_complete = TRUE; break;
        }
        wait = WaitForSingleObject(g.abort_event, POLL_MS);
        if (wait != WAIT_TIMEOUT && wait != WAIT_OBJECT_0) {
            abort_guard(&g, R_THREAD); break;
        }
    }

cleanup:
    if (g_cancelled) abort_guard(&g, R_CANCEL);
    if (owned && enable_code == ERROR_SUCCESS && capture_state && g.reason == R_NONE) {
        mark_now(&final_state_begin);
        final_state_code = EnableTraceEx2(trace, &DXG_PROVIDER, EVENT_CONTROL_CODE_CAPTURE_STATE,
                                         TRACE_LEVEL_VERBOSE, keywords, 0, 1000, NULL);
        mark_now(&final_state_return);
    }
    /* Every post-start path, including enable denial, stops only this exact
     * returned handle. No named fallback, orphan adoption or foreign cleanup. */
    while (owned && stop_attempts < 3) {
        init_properties(&props, path, FALSE);
        if (!stop_attempts) mark_now(&stopping);
        ++stop_attempts;
        stop_code = ControlTraceW(trace, NULL, &props.p, EVENT_TRACE_CONTROL_STOP);
        mark_now(&stop_return);
        if (stop_code == ERROR_SUCCESS) {
            /* STOP may already have deallocated the pool. Only successful QUERY
             * observations establish pool geometry; final STOP supplies losses. */
            save_stats(&final, &props.p, FALSE); validate_loss(&g, &final);
            owned = FALSE; closed = TRUE;
        } else if (stop_code == ERROR_WMI_INSTANCE_NOT_FOUND || stop_code == ERROR_MORE_DATA) {
            /* Absent/STOP with MORE_DATA: closed, but no usable final stats. */
            owned = FALSE; closed = TRUE;
            abort_guard(&g, R_STOP);
        } else {
            abort_guard(&g, R_STOP);
            if (stop_attempts < 3) Sleep(POLL_MS);
        }
    }
    if (thread) {
        SetEvent(g.done_event);
        joined = WaitForSingleObject(thread, 1000) == WAIT_OBJECT_0;
        if (!joined) abort_guard(&g, R_THREAD);
        monitor_available = joined;
        CloseHandle(thread);
    }
    if (output != INVALID_HANDLE_VALUE) {
        LARGE_INTEGER size;
        if (!GetFileSizeEx(output, &size) || size.QuadPart < 0) abort_guard(&g, R_FILE);
        else {
            file_size = (ULONGLONG)size.QuadPart;
            if (file_size >= FILE_BYTES) abort_guard(&g, R_FILE);
        }
        CloseHandle(output);
    }
    if (handler) SetConsoleCtrlHandler(console_handler, FALSE);
    g_abort_event = NULL;
    /* Keep these two unnamed events until process exit, including after a
     * successful join: a console callback dispatched before unregistering may
     * still hold the abort handle. Process exit releases them. A failed join
     * also forbids reading the monitor's mutable statistics or stack unwinding. */

report:
    mark_now(&end);
    success = !plan && g.reason == R_NONE && started && closed && !owned &&
              interval_complete && joined && final.available &&
              start_code == ERROR_SUCCESS && enable_code == ERROR_SUCCESS &&
              stop_code == ERROR_SUCCESS;
    printf("{\"event\":\"recorder_receipt\",\"mode\":\"%s\",\"status\":\"%s\",\"reason\":\"%s\","
           "\"session\":", plan ? "plan" : "capture", success ? "complete" :
           (plan && g.reason == R_NONE ? "planned" : "invalid"), reason_name(g.reason));
    json_wide(session_name);
    printf(",\"provider\":"
           "\"802ec45a-1e99-4b83-9920-87c98277ba9d\",\"output\":");
    json_wide(path);
    printf(",\"stop_file\":");
    if (got_stop) json_wide(stop_path); else printf("null");
    printf(",\"trace_handle\":");
    if (started) printf("\"0x%016llx\"", (unsigned long long)trace); else printf("null");
    printf(",\"session_guid\":"); json_guid(session_guid_available ? &session_guid : NULL);
    printf(",\"seconds\":%llu,\"keywords\":\"0x%llx\",\"requested_buffer_kib\":64,"
           "\"requested_minimum\":64,\"requested_maximum\":64,\"pool_cap_bytes\":%llu,"
           "\"file_cap_bytes\":%llu,\"file_bytes\":%llu,\"qpc_frequency\":%lld,"
           "\"start_code\":%lu,\"enable_code\":%lu,\"last_query_code\":%lu,"
           "\"stop_code\":%lu,\"stop_attempts\":%lu,\"output_code\":%lu,"
           "\"not_called_code\":4294967295,\"session_started\":%s,"
           "\"owned_session_closed\":%s,\"owned_session_may_remain\":%s,"
           "\"requested_interval_complete\":%s,\"capture_state_requested\":%s,"
           "\"capture_state_code\":%lu,\"final_capture_state_code\":%lu,"
           "\"stopped_by_marker\":%s,"
           "\"capture_state_support\":\"inspect-emitted-records\",\"rundown_complete\":false,"
           "\"success\":%s,\"attribution_qualified\":false,\"speed_gain\":false,"
           "\"session_api_called\":%s,\"monitor\":{\"available\":%s,\"samples\":%lu,"
           "\"min_physical_bytes\":%llu,\"min_commit_bytes\":%llu,"
           "\"max_private_commit_bytes\":%llu,\"max_gap_ms\":%.3f,"
           "\"memory_code\":%lu},\"begin\":",
           (unsigned long long)seconds, (unsigned long long)keywords,
           (unsigned long long)POOL_BYTES, (unsigned long long)FILE_BYTES,
           (unsigned long long)file_size, (long long)g.frequency.QuadPart,
           start_code, enable_code, query_code, stop_code, stop_attempts, output_code,
           started ? "true" : "false", closed ? "true" : "false", owned ? "true" : "false",
           interval_complete ? "true" : "false", capture_state ? "true" : "false",
           state_code, final_state_code, stopped_by_marker ? "true" : "false", success ? "true" : "false",
           start_code != NOT_CALLED ? "true" : "false",
           monitor_available && g.samples ? "true" : "false",
           monitor_available ? g.samples : 0,
           (unsigned long long)(monitor_available && g.samples ? g.min_physical : 0),
           (unsigned long long)(monitor_available && g.samples ? g.min_commit : 0),
           (unsigned long long)(monitor_available ? g.max_private : 0),
           monitor_available && g.frequency.QuadPart ?
               1000.0 * (double)g.max_gap_qpc / (double)g.frequency.QuadPart : 0,
           monitor_available ? g.memory_code : 0);
    print_mark(&begin); printf(",\"start_return\":");
    if (start_code != NOT_CALLED) print_mark(&start_return); else printf("null");
    printf(",\"enable_begin\":");
    if (enable_code != NOT_CALLED) print_mark(&enabling); else printf("null");
    printf(",\"enabled\":");
    if (enable_code == ERROR_SUCCESS) print_mark(&enabled); else printf("null");
    printf(",\"capture_state_begin\":");
    if (state_code != NOT_CALLED) print_mark(&state_begin); else printf("null");
    printf(",\"capture_state_return\":");
    if (state_code != NOT_CALLED) print_mark(&state_return); else printf("null");
    printf(",\"final_capture_state_begin\":");
    if (final_state_code != NOT_CALLED) print_mark(&final_state_begin); else printf("null");
    printf(",\"final_capture_state_return\":");
    if (final_state_code != NOT_CALLED) print_mark(&final_state_return); else printf("null");
    printf(",\"stop_begin\":");
    if (stop_attempts) print_mark(&stopping); else printf("null");
    printf(",\"stop_return\":");
    if (stop_attempts) print_mark(&stop_return); else printf("null");
    printf(",\"end\":"); print_mark(&end);
    printf(",\"last_query_stats\":"); print_stats(&last);
    printf(",\"final_stats\":"); print_stats(&final); printf("}\n");
    {
        int flush_code = fflush(stdout);
        if (flush_code != 0 || ferror(stdout)) {
            /* Preserve the first failure even though a broken output stream
             * cannot carry an amended JSON receipt. Exit status rejects it. */
            InterlockedCompareExchange(&g.reason, R_RECEIPT, R_NONE);
            success = FALSE;
            fprintf(stderr, "DxgKrnl recorder: final receipt write/flush failed; receipt is invalid.\n");
            if (!monitor_available) ExitProcess(1);
            return 1;
        }
    }
    /* Exit without unwinding a stack that an unjoined monitor still references. */
    if (!monitor_available) ExitProcess(1);
    return success || (plan && g.reason == R_NONE) ? 0 : 1;
}
