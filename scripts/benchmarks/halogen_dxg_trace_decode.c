/*
 * Offline DxgKrnl evidence materializer. No sessions, ownership joins or live
 * provider calls. Root owns building and using this on its completed own ETL.
 *
 * CLI: --input absolute.etl --output absolute.jsonl
 * Exit: 0 = selected events materialized; 2 = unresolved/no selected events;
 *       3 = aborted or I/O/API failure; 1 = invalid command line.
 * Decode success NEVER supplies zero-loss, rundown or attribution evidence.
 */
#define WIN32_LEAN_AND_MEAN
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <evntrace.h>
#include <evntcons.h>
#include <tdh.h>
#include <psapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <stddef.h>
#include <string.h>
#include <wchar.h>
#include <limits.h>

#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "tdh.lib")
#pragma comment(lib, "psapi.lib")

#define MIB (1024ULL * 1024ULL)
#define GIB (1024ULL * 1024ULL * 1024ULL)
#define FILE_LIMIT (64ULL * MIB)
#define PRIVATE_LIMIT (32ULL * MIB)
#define RESERVE_LIMIT (18ULL * GIB)
#define METADATA_LIMIT (256UL * 1024UL)
#define PROPERTY_LIMIT (64UL * 1024UL)
#define LINE_LIMIT (1024UL * 1024UL)
#define SUMMARY_RESERVE (16ULL * 1024ULL)
#define PATH_CAPACITY 32768

static const GUID dxgkrnl = {
    0x802ec45a, 0x1e99, 0x4b83,
    {0x99, 0x20, 0x87, 0xc9, 0x82, 0x77, 0xba, 0x9d}
};

enum abort_code {
    ABORT_NONE, ABORT_MEMORY_QUERY, ABORT_PRIVATE_COMMIT, ABORT_RESERVE,
    ABORT_METADATA_LIMIT, ABORT_PROPERTY_LIMIT, ABORT_LINE_LIMIT,
    ABORT_OUTPUT_LIMIT, ABORT_WRITE, ABORT_OPEN_TRACE, ABORT_PROCESS_TRACE,
    ABORT_CLOSE_TRACE, ABORT_CLOCK, ABORT_GUARD_THREAD, ABORT_FLUSH
};

typedef struct {
    HANDLE output;
    HANDLE stop_guard;
    volatile LONG abort;
    DWORD abort_status;
    unsigned long long output_bytes;
    unsigned long long all_events, other_events, selected_events, written_events;
    unsigned long long materialized_events, unresolved_events, unresolved_properties;
    unsigned long long peak_private, minimum_physical, minimum_commit;
    unsigned long long guard_samples;
    ULONG buffers_read;
    DWORD clock;
    DWORD process_status, close_status;
    BYTE *metadata, *property;
    char *line;
    size_t line_bytes;
    BOOL line_overflow, write_failed;
} decoder;

static const char *abort_name(LONG code)
{
    static const char *const names[] = {
        "none", "memory-query-failed", "private-commit-limit", "reserve-limit",
        "metadata-limit", "property-limit", "event-line-limit",
        "output-limit", "output-write-failed", "open-trace-failed",
        "process-trace-failed", "close-trace-failed", "unsupported-clock",
        "guard-thread-failed", "output-flush-failed"
    };
    return code >= 0 && code < (LONG)(sizeof(names) / sizeof(names[0]))
        ? names[code] : "unknown-abort";
}

static void stop_decode(decoder *d, LONG code, DWORD status)
{
    if (InterlockedCompareExchange(&d->abort, code, ABORT_NONE) == ABORT_NONE)
        d->abort_status = status;
}

static LONG stopped(decoder *d)
{
    return InterlockedCompareExchange(&d->abort, ABORT_NONE, ABORT_NONE);
}

/* Called by main before/after the watchdog, otherwise by the watchdog only. */
static BOOL check_memory(decoder *d)
{
    MEMORYSTATUSEX m;
    PROCESS_MEMORY_COUNTERS_EX p;
    PERFORMANCE_INFORMATION system;
    unsigned long long commit;
    memset(&m, 0, sizeof(m));
    memset(&p, 0, sizeof(p));
    memset(&system, 0, sizeof(system));
    m.dwLength = sizeof(m);
    p.cb = sizeof(p);
    system.cb = sizeof(system);
    if (!GlobalMemoryStatusEx(&m) ||
        !GetPerformanceInfo(&system, sizeof(system)) ||
        !GetProcessMemoryInfo(GetCurrentProcess(),
            (PROCESS_MEMORY_COUNTERS *)&p, sizeof(p)) ||
        system.CommitLimit < system.CommitTotal) {
        stop_decode(d, ABORT_MEMORY_QUERY, GetLastError());
        return FALSE;
    }
    commit = (unsigned long long)(system.CommitLimit - system.CommitTotal) * system.PageSize;
    ++d->guard_samples;
    if ((unsigned long long)p.PrivateUsage > d->peak_private)
        d->peak_private = (unsigned long long)p.PrivateUsage;
    if (m.ullAvailPhys < d->minimum_physical) d->minimum_physical = m.ullAvailPhys;
    if (commit < d->minimum_commit) d->minimum_commit = commit;
    if ((unsigned long long)p.PrivateUsage > PRIVATE_LIMIT)
        stop_decode(d, ABORT_PRIVATE_COMMIT, ERROR_NOT_ENOUGH_MEMORY);
    else if (m.ullAvailPhys < RESERVE_LIMIT || commit < RESERVE_LIMIT)
        stop_decode(d, ABORT_RESERVE, ERROR_NOT_ENOUGH_MEMORY);
    return stopped(d) == ABORT_NONE;
}

static DWORD WINAPI guard_main(LPVOID context)
{
    decoder *d = (decoder *)context;
    DWORD wait;
    for (;;) {
        if (!check_memory(d)) break;
        wait = WaitForSingleObject(d->stop_guard, 100);
        if (wait == WAIT_OBJECT_0) break;
        if (wait != WAIT_TIMEOUT) {
            stop_decode(d, ABORT_GUARD_THREAD, GetLastError());
            break;
        }
    }
    return 0;
}

static void line_reset(decoder *d)
{
    d->line_bytes = 0;
    d->line_overflow = FALSE;
    d->line[0] = '\0';
}

static void add(decoder *d, const char *format, ...)
{
    int n;
    size_t remaining;
    va_list args;
    if (d->line_overflow) return;
    remaining = LINE_LIMIT - d->line_bytes;
    va_start(args, format);
    n = vsnprintf(d->line + d->line_bytes, remaining, format, args);
    va_end(args);
    if (n < 0 || (size_t)n >= remaining) {
        d->line_overflow = TRUE;
        stop_decode(d, ABORT_LINE_LIMIT, ERROR_BUFFER_OVERFLOW);
        return;
    }
    d->line_bytes += (size_t)n;
}

static void add_wide(decoder *d, const WCHAR *value)
{
    add(d, "\"");
    while (*value && !d->line_overflow) {
        unsigned c = (unsigned)*value++;
        if (c == '"' || c == '\\') add(d, "\\%c", (char)c);
        else if (c < 0x20 || c >= 0x7f) add(d, "\\u%04X", c);
        else add(d, "%c", (char)c);
    }
    add(d, "\"");
}

static void add_hex(decoder *d, const BYTE *bytes, ULONG size)
{
    static const char hex[] = "0123456789abcdef";
    ULONG i;
    if (d->line_overflow) return;
    if ((size_t)size * 2 + 3 > LINE_LIMIT - d->line_bytes) {
        d->line_overflow = TRUE;
        stop_decode(d, ABORT_LINE_LIMIT, ERROR_BUFFER_OVERFLOW);
        return;
    }
    d->line[d->line_bytes++] = '"';
    for (i = 0; i < size; ++i) {
        d->line[d->line_bytes++] = hex[bytes[i] >> 4];
        d->line[d->line_bytes++] = hex[bytes[i] & 15];
    }
    d->line[d->line_bytes++] = '"';
    d->line[d->line_bytes] = '\0';
}

/* A complete line is buffered before writing; reserve space for the summary. */
static BOOL write_line(decoder *d, BOOL final)
{
    DWORD written, remaining;
    size_t offset = 0;
    unsigned long long limit = final ? FILE_LIMIT : FILE_LIMIT - SUMMARY_RESERVE;
    LARGE_INTEGER rollback;
    if (d->line_overflow || d->write_failed) return FALSE;
    if ((unsigned long long)d->line_bytes + 1 > limit - d->output_bytes) {
        stop_decode(d, ABORT_OUTPUT_LIMIT, ERROR_FILE_TOO_LARGE);
        return FALSE;
    }
    d->line[d->line_bytes++] = '\n'; /* add() always leaves one byte free */
    while (offset < d->line_bytes) {
        remaining = (DWORD)(d->line_bytes - offset);
        if (!WriteFile(d->output, d->line + offset, remaining, &written, NULL) ||
            written == 0) {
            DWORD error = GetLastError();
            rollback.QuadPart = (LONGLONG)d->output_bytes;
            /* Only this CREATE_NEW output is touched; retain earlier complete lines. */
            if (!SetFilePointerEx(d->output, rollback, NULL, FILE_BEGIN) ||
                !SetEndOfFile(d->output))
                fwprintf(stderr, L"Output rollback failed; last line may be incomplete.\n");
            d->write_failed = TRUE;
            stop_decode(d, ABORT_WRITE, error ? error : ERROR_WRITE_FAULT);
            return FALSE;
        }
        offset += written;
    }
    d->output_bytes += d->line_bytes;
    return TRUE;
}

static const WCHAR *metadata_name(const BYTE *metadata, ULONG size, ULONG offset)
{
    const WCHAR *name;
    size_t i, characters;
    if (offset == 0 || offset >= size || offset % sizeof(WCHAR) != 0) return NULL;
    characters = (size - offset) / sizeof(WCHAR);
    name = (const WCHAR *)(metadata + offset);
    for (i = 0; i < characters; ++i) if (name[i] == 0) return name;
    return NULL;
}

static BOOL valid_schema(const TRACE_EVENT_INFO *info, ULONG size)
{
    size_t base = offsetof(TRACE_EVENT_INFO, EventPropertyInfoArray);
    if (size < base || info->TopLevelPropertyCount > info->PropertyCount) return FALSE;
    return info->PropertyCount <= (size - base) / sizeof(EVENT_PROPERTY_INFO);
}

static unsigned pointer_width(USHORT flags)
{
    unsigned bits = flags & (EVENT_HEADER_FLAG_32_BIT_HEADER | EVENT_HEADER_FLAG_64_BIT_HEADER);
    if (bits == EVENT_HEADER_FLAG_32_BIT_HEADER) return 4;
    if (bits == EVENT_HEADER_FLAG_64_BIT_HEADER) return 8;
    return 0; /* Never substitute this decoder's pointer width. */
}

static void WINAPI event_record(PEVENT_RECORD event)
{
    decoder *d = (decoder *)event->UserContext;
    TRACE_EVENT_INFO *info = (TRACE_EVENT_INFO *)d->metadata;
    TDH_CONTEXT pointer_context;
    ULONG context_count, metadata_bytes = 0, status, i, emitted = 0;
    unsigned width;
    BOOL unresolved = FALSE, complete = TRUE;
    const char *reason = "none";
    if (stopped(d) != ABORT_NONE) return;
    ++d->all_events;
    if (memcmp(&event->EventHeader.ProviderId, &dxgkrnl, sizeof(GUID)) != 0) {
        ++d->other_events;
        return;
    }
    ++d->selected_events;
    width = pointer_width(event->EventHeader.Flags);
    memset(&pointer_context, 0, sizeof(pointer_context));
    pointer_context.ParameterType = TDH_CONTEXT_POINTERSIZE;
    pointer_context.ParameterValue = width;
    context_count = width ? 1 : 0;
    line_reset(d);
    add(d, "{\"type\":\"event\",\"provider\":\"802ec45a-1e99-4b83-9920-87c98277ba9d\","
        "\"ordinal\":\"%llu\",\"id\":%u,\"version\":%u,\"opcode\":%u,"
        "\"channel\":%u,\"level\":%u,\"task\":%u,\"keyword\":\"0x%016llx\","
        "\"raw_timestamp\":\"%lld\",\"qpc\":",
        d->selected_events, (unsigned)event->EventHeader.EventDescriptor.Id,
        (unsigned)event->EventHeader.EventDescriptor.Version,
        (unsigned)event->EventHeader.EventDescriptor.Opcode,
        (unsigned)event->EventHeader.EventDescriptor.Channel,
        (unsigned)event->EventHeader.EventDescriptor.Level,
        (unsigned)event->EventHeader.EventDescriptor.Task,
        (unsigned long long)event->EventHeader.EventDescriptor.Keyword,
        (long long)event->EventHeader.TimeStamp.QuadPart);
    if (d->clock == 1) add(d, "\"%lld\"", (long long)event->EventHeader.TimeStamp.QuadPart);
    else add(d, "null");
    add(d, ",\"header_pid\":%lu,\"header_tid\":%lu,\"header_flags\":%u,\"pointer_width\":",
        event->EventHeader.ProcessId, event->EventHeader.ThreadId, (unsigned)event->EventHeader.Flags);
    if (width) add(d, "%u", width); else add(d, "null");
    add(d, ",\"payload_bytes\":%u,\"payload_raw_hex\":", (unsigned)event->UserDataLength);
    add_hex(d, (const BYTE *)event->UserData, event->UserDataLength);

    status = TdhGetEventInformation(event, context_count,
        context_count ? &pointer_context : NULL, NULL, &metadata_bytes);
    if (metadata_bytes > METADATA_LIMIT) {
        stop_decode(d, ABORT_METADATA_LIMIT, ERROR_BUFFER_OVERFLOW);
        unresolved = TRUE; complete = FALSE; reason = "metadata-limit";
    } else if (status != ERROR_INSUFFICIENT_BUFFER || metadata_bytes == 0) {
        unresolved = TRUE; complete = FALSE; reason = "tdh-schema-unavailable";
    } else if (stopped(d) != ABORT_NONE) {
        unresolved = TRUE; complete = FALSE; reason = "guard-abort";
    } else {
        memset(d->metadata, 0, metadata_bytes);
        status = TdhGetEventInformation(event, context_count,
            context_count ? &pointer_context : NULL, info, &metadata_bytes);
        if (metadata_bytes > METADATA_LIMIT) {
            stop_decode(d, ABORT_METADATA_LIMIT, ERROR_BUFFER_OVERFLOW);
            unresolved = TRUE; complete = FALSE; reason = "metadata-limit";
        } else if (status != ERROR_SUCCESS || !valid_schema(info, metadata_bytes)) {
            unresolved = TRUE; complete = FALSE; reason = "tdh-schema-error-or-invalid";
        }
    }
    add(d, ",\"tdh_schema_status\":%lu,\"metadata_bytes\":%lu,\"properties\":[", status, metadata_bytes);
    if (!unresolved) {
        for (i = 0; i < info->TopLevelPropertyCount; ++i) {
            const EVENT_PROPERTY_INFO *property = &info->EventPropertyInfoArray[i];
            const WCHAR *name = metadata_name(d->metadata, metadata_bytes, property->NameOffset);
            const WCHAR *map = NULL;
            PROPERTY_DATA_DESCRIPTOR descriptor;
            ULONG property_bytes = 0, property_status = ERROR_SUCCESS;
            const char *property_reason = "none";
            BOOL property_unresolved = FALSE, value_called = FALSE;
            if (stopped(d) != ABORT_NONE) {
                unresolved = TRUE; complete = FALSE; reason = "guard-or-limit-abort";
                break;
            }
            if (emitted++) add(d, ",");
            add(d, "{\"index\":%lu,\"name\":", i);
            if (name) add_wide(d, name); else add(d, "null");
            add(d, ",\"flags\":%lu,\"in_type\":", (ULONG)property->Flags);
            if (property->Flags & PropertyStruct) add(d, "null,\"out_type\":null");
            else add(d, "%u,\"out_type\":%u", (unsigned)property->nonStructType.InType,
                (unsigned)property->nonStructType.OutType);
            add(d, ",\"count\":");
            if (property->Flags & PropertyParamCount) add(d, "null,\"count_property_index\":%u",
                (unsigned)property->countPropertyIndex);
            else add(d, "%u,\"count_property_index\":null", (unsigned)property->count);
            add(d, ",\"length\":");
            if (property->Flags & PropertyParamLength) add(d, "null,\"length_property_index\":%u",
                (unsigned)property->lengthPropertyIndex);
            else add(d, "%u,\"length_property_index\":null", (unsigned)property->length);
            add(d, ",\"map_name\":");
            if (!(property->Flags & (PropertyStruct | PropertyHasCustomSchema)) && property->nonStructType.MapNameOffset)
                map = metadata_name(d->metadata, metadata_bytes, property->nonStructType.MapNameOffset);
            if (map) add_wide(d, map); else add(d, "null");

            if (!name) { property_unresolved = TRUE; property_reason = "invalid-property-name"; }
            else if (property->Flags & PropertyStruct) {
                property_unresolved = TRUE; property_reason = "unsupported-structure";
                add(d, ",\"struct_start_index\":%u,\"struct_members\":%u",
                    (unsigned)property->structType.StructStartIndex,
                    (unsigned)property->structType.NumOfStructMembers);
            } else if (property->Flags & PropertyHasCustomSchema) {
                property_unresolved = TRUE; property_reason = "unsupported-custom-schema";
            } else if (((ULONG)property->Flags & ~0xffUL) != 0) {
                property_unresolved = TRUE; property_reason = "unsupported-property-flags";
            } else if (!width) { property_unresolved = TRUE; property_reason = "unresolved-pointer-width"; }
            else if (((property->Flags & PropertyParamCount) && property->countPropertyIndex >= info->PropertyCount) ||
                ((property->Flags & PropertyParamLength) && property->lengthPropertyIndex >= info->PropertyCount)) {
                property_unresolved = TRUE; property_reason = "invalid-count-or-length-index";
            } else {
                memset(&descriptor, 0, sizeof(descriptor));
                descriptor.PropertyName = (ULONGLONG)(ULONG_PTR)name;
                /* ULONG_MAX is TDH's supported whole-array access, including
                 * schema-counted arrays. No byte offsets or element-size guesses. */
                descriptor.ArrayIndex = ULONG_MAX;
                property_status = TdhGetPropertySize(event, context_count,
                    context_count ? &pointer_context : NULL, 1, &descriptor, &property_bytes);
                if (property_status != ERROR_SUCCESS) {
                    property_unresolved = TRUE; property_reason = "tdh-property-size-error";
                } else if (property_bytes > PROPERTY_LIMIT) {
                    stop_decode(d, ABORT_PROPERTY_LIMIT, ERROR_BUFFER_OVERFLOW);
                    property_unresolved = TRUE; property_reason = "property-limit";
                } else if (stopped(d) != ABORT_NONE) {
                    property_unresolved = TRUE; property_reason = "guard-abort";
                } else if (property_bytes != 0) {
                    value_called = TRUE;
                    property_status = TdhGetProperty(event, context_count,
                        context_count ? &pointer_context : NULL, 1, &descriptor,
                        property_bytes, d->property);
                    if (property_status != ERROR_SUCCESS) {
                        property_unresolved = TRUE; property_reason = "tdh-property-value-error";
                    }
                }
            }
            add(d, ",\"array_access\":\"tdh-whole-property\",\"tdh_status\":%lu,"
                "\"value_call_made\":%s,\"bytes\":%lu,\"raw_hex\":",
                property_status, value_called ? "true" : "false", property_bytes);
            if (property_unresolved) add(d, "null"); else add_hex(d, d->property, property_bytes);
            add(d, ",\"status\":\"%s\",\"unresolved_reason\":\"%s\"}",
                property_unresolved ? "unresolved" : "materialized", property_reason);
            if (property_unresolved) {
                unresolved = TRUE;
                ++d->unresolved_properties;
                reason = "unresolved-property";
            }
            if (d->line_overflow) { complete = FALSE; break; }
        }
        if (emitted != info->TopLevelPropertyCount) complete = FALSE;
    }
    add(d, "],\"properties_emitted\":%lu,\"properties_complete\":%s,"
        "\"status\":\"%s\",\"unresolved_reason\":\"%s\",\"ownership\":\"unresolved\"}",
        emitted, complete ? "true" : "false", unresolved ? "unresolved" : "materialized", reason);
    if (write_line(d, FALSE)) {
        ++d->written_events;
        if (unresolved) ++d->unresolved_events; else ++d->materialized_events;
    }
}

static ULONG WINAPI trace_buffer(PEVENT_TRACE_LOGFILEW logfile)
{
    decoder *d = (decoder *)logfile->Context;
    d->buffers_read = logfile->BuffersRead;
    return stopped(d) == ABORT_NONE;
}

/* Ordinary drive-rooted and UNC file paths only; no device namespaces. */
static BOOL absolute_file_path(const WCHAR *path)
{
    size_t length = wcslen(path);
    const WCHAR *server_end, *share_end;
    if (length < 3 || length >= PATH_CAPACITY) return FALSE;
    if (((path[0] >= L'A' && path[0] <= L'Z') || (path[0] >= L'a' && path[0] <= L'z')) &&
        path[1] == L':' && (path[2] == L'\\' || path[2] == L'/')) return TRUE;
    if (path[0] != L'\\' || path[1] != L'\\' || path[2] == L'?' || path[2] == L'.') return FALSE;
    server_end = wcschr(path + 2, L'\\');
    if (!server_end || server_end == path + 2) return FALSE;
    share_end = wcschr(server_end + 1, L'\\');
    return share_end && share_end != server_end + 1 && share_end[1] != 0;
}

static void trace_header(decoder *d, const EVENT_TRACE_LOGFILEW *logfile,
    const WCHAR *input, const WCHAR *output, unsigned long long input_bytes)
{
    const TRACE_LOGFILE_HEADER *h = &logfile->LogfileHeader;
    line_reset(d);
    add(d, "{\"type\":\"trace_header\",\"schema\":\"halogen.dxg.materialization.v1\",\"input\":");
    add_wide(d, input);
    add(d, ",\"output\":"); add_wide(d, output);
    add(d, ",\"input_bytes\":\"%llu\",\"clock\":{\"type\":\"%s\","
        "\"reserved_flags\":%lu,\"perf_freq\":\"%lld\"},"
        "\"header_statistics\":{\"buffer_size_bytes\":%lu,\"buffers_written\":%lu,"
        "\"buffers_lost\":%lu,\"events_lost\":%lu,\"start_buffers\":%lu,"
        "\"processors\":%lu,\"log_file_mode\":%lu,\"maximum_file_size_etw_megabytes\":%lu,"
        "\"start_time_filetime\":\"%lld\",\"end_time_filetime\":\"%lld\"},"
        "\"logfile_events_lost\":null,\"logfile_events_lost_status\":\"unused-member-not-read\","
        "\"recorder_controltrace_loss_counters\":null,\"zero_loss_evidence\":\"not-supplied\","
        "\"rundown_complete\":null,\"ownership\":\"unresolved\"}",
        input_bytes, h->ReservedFlags == 1 ? "QPC" : "unsupported", h->ReservedFlags,
        (long long)h->PerfFreq.QuadPart, h->BufferSize, h->BuffersWritten,
        h->BuffersLost, h->EventsLost, h->StartBuffers, h->NumberOfProcessors,
        h->LogFileMode, h->MaximumFileSize, (long long)h->StartTime.QuadPart,
        (long long)h->EndTime.QuadPart);
    write_line(d, FALSE);
}

static BOOL write_summary(decoder *d, BOOL trace_opened)
{
    LONG abort = stopped(d);
    BOOL processed = trace_opened && d->process_status == ERROR_SUCCESS &&
        d->close_status == ERROR_SUCCESS && abort == ABORT_NONE;
    BOOL decode_success = processed && d->selected_events != 0 &&
        d->selected_events == d->written_events && d->unresolved_events == 0;
    line_reset(d);
    add(d, "{\"type\":\"summary\",\"decode_success\":%s,\"process_trace_completed\":%s,"
        "\"selected_events_present\":%s,\"abort_reason\":\"%s\",\"abort_status\":%lu,"
        "\"process_trace_status\":%lu,\"close_trace_status\":%lu,"
        "\"events_seen\":\"%llu\",\"other_provider_events\":\"%llu\","
        "\"dxg_events_seen\":\"%llu\",\"dxg_events_written\":\"%llu\","
        "\"materialized_events\":\"%llu\",\"unresolved_events\":\"%llu\","
        "\"events_not_written\":\"%llu\",\"unresolved_properties\":\"%llu\","
        "\"buffers_read\":%lu,\"output_bytes_before_summary\":\"%llu\","
        "\"limits\":{\"input_output_bytes\":\"%llu\",\"metadata_bytes\":%lu,"
        "\"property_bytes\":%lu,\"event_line_bytes\":%lu,\"private_commit_bytes\":\"%llu\","
        "\"physical_commit_reserve_bytes\":\"%llu\",\"guard_interval_ms\":100},"
        "\"memory\":{\"samples\":\"%llu\",\"peak_private_bytes\":\"%llu\","
        "\"minimum_available_physical_bytes\":\"%llu\",\"minimum_available_commit_bytes\":\"%llu\"},"
        "\"recorder_controltrace_loss_counters\":null,\"zero_loss_evidence\":\"not-supplied\","
        "\"coverage_complete\":null,\"rundown_complete\":null,\"ownership\":\"unresolved\","
        "\"qualified_performance_gain\":false}",
        decode_success ? "true" : "false", processed ? "true" : "false",
        d->selected_events ? "true" : "false", abort_name(abort), d->abort_status,
        d->process_status, d->close_status, d->all_events, d->other_events,
        d->selected_events, d->written_events, d->materialized_events,
        d->unresolved_events, d->selected_events - d->written_events,
        d->unresolved_properties, d->buffers_read, d->output_bytes,
        FILE_LIMIT, METADATA_LIMIT, PROPERTY_LIMIT, LINE_LIMIT, PRIVATE_LIMIT,
        RESERVE_LIMIT, d->guard_samples, d->peak_private,
        d->guard_samples ? d->minimum_physical : 0,
        d->guard_samples ? d->minimum_commit : 0);
    return write_line(d, TRUE);
}

int wmain(int argc, WCHAR **argv)
{
    const WCHAR *input_argument = NULL, *output_argument = NULL;
    WCHAR input[PATH_CAPACITY], output[PATH_CAPACITY];
    decoder d;
    EVENT_TRACE_LOGFILEW logfile;
    HANDLE input_handle = INVALID_HANDLE_VALUE, guard = NULL;
    TRACEHANDLE trace = INVALID_PROCESSTRACE_HANDLE;
    LARGE_INTEGER size;
    BY_HANDLE_FILE_INFORMATION input_info;
    DWORD length, error;
    BOOL trace_opened = FALSE, summary_ok = FALSE;
    int i, result = 3;
    if (argc == 2 && wcscmp(argv[1], L"--help") == 0) {
        wprintf(L"Usage: halogen_dxg_trace_decode --input absolute.etl --output absolute.jsonl\n"
            L"Offline only; new output, 64 MiB files, 32 MiB private commit, 18 GiB reserves.\n");
        return 0;
    }
    for (i = 1; i < argc; i += 2) {
        if (i + 1 >= argc) break;
        if (wcscmp(argv[i], L"--input") == 0 && !input_argument) input_argument = argv[i + 1];
        else if (wcscmp(argv[i], L"--output") == 0 && !output_argument) output_argument = argv[i + 1];
        else break;
    }
    if (i != argc || !input_argument || !output_argument ||
        !absolute_file_path(input_argument) || !absolute_file_path(output_argument)) {
        fwprintf(stderr, L"Require --input and --output absolute ordinary file paths.\n");
        return 1;
    }
    length = GetFullPathNameW(input_argument, PATH_CAPACITY, input, NULL);
    if (!length || length >= PATH_CAPACITY) { fwprintf(stderr, L"Invalid input path.\n"); return 1; }
    length = GetFullPathNameW(output_argument, PATH_CAPACITY, output, NULL);
    if (!length || length >= PATH_CAPACITY) { fwprintf(stderr, L"Invalid output path.\n"); return 1; }
    memset(&d, 0, sizeof(d));
    memset(&logfile, 0, sizeof(logfile));
    d.output = INVALID_HANDLE_VALUE;
    d.minimum_physical = d.minimum_commit = ULLONG_MAX;
    d.process_status = d.close_status = ERROR_NOT_READY;
    input_handle = CreateFileW(input, GENERIC_READ, FILE_SHARE_READ, NULL,
        OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL | FILE_FLAG_SEQUENTIAL_SCAN, NULL);
    if (input_handle == INVALID_HANDLE_VALUE) {
        fwprintf(stderr, L"Input open failed: %lu\n", GetLastError()); goto cleanup;
    }
    if (!GetFileSizeEx(input_handle, &size) || !GetFileInformationByHandle(input_handle, &input_info)) {
        fwprintf(stderr, L"Input information failed: %lu\n", GetLastError()); goto cleanup;
    }
    if (size.QuadPart <= 0 || (unsigned long long)size.QuadPart > FILE_LIMIT ||
        (input_info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) {
        fwprintf(stderr, L"Input must be a nonempty regular file of at most 64 MiB.\n"); goto cleanup;
    }
    if (!check_memory(&d)) {
        fwprintf(stderr, L"Admission guard failed: %hs (%lu)\n", abort_name(stopped(&d)), d.abort_status);
        goto cleanup;
    }
    d.metadata = (BYTE *)malloc(METADATA_LIMIT);
    d.property = (BYTE *)malloc(PROPERTY_LIMIT);
    d.line = (char *)malloc(LINE_LIMIT);
    if (!d.metadata || !d.property || !d.line) {
        fwprintf(stderr, L"Bounded buffer allocation failed.\n"); goto cleanup;
    }
    d.output = CreateFileW(output, GENERIC_WRITE, 0, NULL, CREATE_NEW,
        FILE_ATTRIBUTE_NORMAL | FILE_FLAG_SEQUENTIAL_SCAN, NULL);
    if (d.output == INVALID_HANDLE_VALUE) {
        fwprintf(stderr, L"New output creation failed (existing output rejected): %lu\n", GetLastError());
        goto cleanup;
    }
    if (GetFileType(d.output) != FILE_TYPE_DISK) {
        fwprintf(stderr, L"Output must be an ordinary disk file.\n");
        goto cleanup;
    }
    d.stop_guard = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (!d.stop_guard) { stop_decode(&d, ABORT_GUARD_THREAD, GetLastError()); goto finish; }
    guard = CreateThread(NULL, 0, guard_main, &d, 0, NULL);
    if (!guard) { stop_decode(&d, ABORT_GUARD_THREAD, GetLastError()); goto finish; }
    logfile.LogFileName = input;
    logfile.ProcessTraceMode = PROCESS_TRACE_MODE_EVENT_RECORD | PROCESS_TRACE_MODE_RAW_TIMESTAMP;
    logfile.EventRecordCallback = event_record;
    logfile.BufferCallback = trace_buffer;
    logfile.Context = &d;
    if (stopped(&d) != ABORT_NONE) goto finish;
    trace = OpenTraceW(&logfile);
    if (trace == INVALID_PROCESSTRACE_HANDLE) {
        stop_decode(&d, ABORT_OPEN_TRACE, GetLastError()); goto finish;
    }
    trace_opened = TRUE;
    d.clock = logfile.LogfileHeader.ReservedFlags;
    trace_header(&d, &logfile, input, output, (unsigned long long)size.QuadPart);
    if (d.clock != 1 || logfile.LogfileHeader.PerfFreq.QuadPart <= 0)
        stop_decode(&d, ABORT_CLOCK, ERROR_NOT_SUPPORTED);
    if (stopped(&d) == ABORT_NONE) {
        d.process_status = ProcessTrace(&trace, 1, NULL, NULL);
        if (d.process_status != ERROR_SUCCESS)
            stop_decode(&d, ABORT_PROCESS_TRACE, d.process_status);
    }
finish:
    if (trace != INVALID_PROCESSTRACE_HANDLE) {
        d.close_status = CloseTrace(trace);
        trace = INVALID_PROCESSTRACE_HANDLE;
        if (d.close_status != ERROR_SUCCESS) stop_decode(&d, ABORT_CLOSE_TRACE, d.close_status);
    }
    if (guard) {
        SetEvent(d.stop_guard);
        WaitForSingleObject(guard, INFINITE);
        CloseHandle(guard); guard = NULL;
    }
    check_memory(&d);
    /* Flush event data before claiming completion in a summary. */
    if (!FlushFileBuffers(d.output)) stop_decode(&d, ABORT_FLUSH, GetLastError());
    summary_ok = write_summary(&d, trace_opened);
    if (!FlushFileBuffers(d.output)) {
        error = GetLastError();
        stop_decode(&d, ABORT_FLUSH, error);
        summary_ok = FALSE;
        fwprintf(stderr, L"Final output flush failed: %lu; summary durability unverified.\n", error);
    }
    if (stopped(&d) == ABORT_NONE && summary_ok)
        result = d.selected_events && d.unresolved_events == 0 ? 0 : 2;
    if (result == 3)
        fwprintf(stderr, L"Materialization aborted: %hs (%lu); zero-loss evidence not supplied.\n",
            abort_name(stopped(&d)), d.abort_status);
cleanup:
    if (input_handle != INVALID_HANDLE_VALUE) CloseHandle(input_handle);
    if (d.output != INVALID_HANDLE_VALUE) CloseHandle(d.output);
    if (d.stop_guard) CloseHandle(d.stop_guard);
    free(d.metadata); free(d.property); free(d.line);
    return result;
}
