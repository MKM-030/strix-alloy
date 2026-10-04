/* Windows x64, research-only access-violation metadata collector.
 * No CRT, payload reads, stack walks, dumps, instruction hooks, or device APIs.
 * See halogen_qmoe_fault_capture.md for the ABI, build, and limitations.
 */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <tlhelp32.h>
#include <stdint.h>

#if !defined(_WIN32) || !defined(_M_X64)
#error This collector requires native Windows x64.
#endif

#define MODULE_LIMIT 512U
#define PATH_CHARS 1024U
#define RECORD_BYTES 8192U
#define RECORD_LIMIT 8L

struct module_entry {
    uintptr_t base;
    DWORD bytes;
    DWORD path_truncated;
    WCHAR path[PATH_CHARS];
};

struct record_builder {
    DWORD used;
    BOOL valid;
};

static SRWLOCK lifecycle_lock = SRWLOCK_INIT;
static HANDLE output_file = INVALID_HANDLE_VALUE;
static PVOID handler_cookie;
static volatile LONG enabled;
static volatile LONG writer_active;
static volatile LONG records_attempted;
static BOOL started_once;
static DWORD module_count;
static struct module_entry module_map[MODULE_LIMIT];
static char record_buffer[RECORD_BYTES];

static void append_char(struct record_builder *builder, char value)
{
    if (builder->used < RECORD_BYTES) {
        record_buffer[builder->used++] = value;
    } else {
        builder->valid = FALSE;
    }
}

static void append_text(struct record_builder *builder, const char *text)
{
    while (*text != '\0') {
        append_char(builder, *text++);
    }
}

static void append_hex(struct record_builder *builder, uint64_t value)
{
    static const char digits[] = "0123456789abcdef";
    unsigned int shift;
    append_text(builder, "\"0x");
    for (shift = 64U; shift != 0U; shift -= 4U) {
        append_char(builder, digits[(value >> (shift - 4U)) & 15U]);
    }
    append_char(builder, '"');
}

static void append_field(struct record_builder *builder, const char *name,
                         uint64_t value)
{
    append_text(builder, ",\"");
    append_text(builder, name);
    append_text(builder, "\":");
    append_hex(builder, value);
}

/* ASCII JSON with escaped UTF-16 code units: no locale/CRT conversion. */
static void append_path(struct record_builder *builder, const WCHAR *path)
{
    static const char digits[] = "0123456789abcdef";
    DWORD index;
    append_char(builder, '"');
    for (index = 0U; index < PATH_CHARS && path[index] != L'\0'; ++index) {
        unsigned int value = (unsigned int)path[index];
        if (value >= 32U && value < 127U && value != '"' && value != '\\') {
            append_char(builder, (char)value);
        } else {
            append_text(builder, "\\u");
            append_char(builder, digits[(value >> 12U) & 15U]);
            append_char(builder, digits[(value >> 8U) & 15U]);
            append_char(builder, digits[(value >> 4U) & 15U]);
            append_char(builder, digits[value & 15U]);
        }
    }
    append_char(builder, '"');
}

/* Lookup only collector-owned, immutable metadata. No loader calls in VEH. */
static const struct module_entry *lookup_module(uintptr_t rip)
{
    DWORD index;
    for (index = 0U; index < module_count; ++index) {
        const struct module_entry *entry = &module_map[index];
        if (rip >= entry->base && rip - entry->base < (uintptr_t)entry->bytes) {
            return entry;
        }
    }
    return NULL;
}

static LONG CALLBACK capture_exception(PEXCEPTION_POINTERS pointers)
{
    struct record_builder builder = {0U, TRUE};
    DWORD saved_last_error = GetLastError();
    const EXCEPTION_RECORD *exception;
    const CONTEXT *context;
    const struct module_entry *module;
    LONG record_number;
    DWORD written;
    const char *access_type = "unknown";

    if (InterlockedCompareExchange(&enabled, 0L, 0L) == 0L ||
        pointers == NULL || pointers->ExceptionRecord == NULL ||
        pointers->ContextRecord == NULL) {
        SetLastError(saved_last_error);
        return EXCEPTION_CONTINUE_SEARCH;
    }
    exception = pointers->ExceptionRecord;
    if (exception->ExceptionCode != EXCEPTION_ACCESS_VIOLATION ||
        InterlockedCompareExchange(&writer_active, 1L, 0L) != 0L) {
        SetLastError(saved_last_error);
        return EXCEPTION_CONTINUE_SEARCH;
    }
    /* No wait: recursive or simultaneous exceptions skip the busy writer. */
    if (InterlockedCompareExchange(&enabled, 0L, 0L) == 0L ||
        records_attempted >= RECORD_LIMIT) {
        InterlockedExchange(&writer_active, 0L);
        SetLastError(saved_last_error);
        return EXCEPTION_CONTINUE_SEARCH;
    }
    record_number = ++records_attempted;
    context = pointers->ContextRecord;
    module = lookup_module((uintptr_t)context->Rip);
    if (exception->NumberParameters >= 1U) {
        if (exception->ExceptionInformation[0] == 0U) access_type = "read";
        else if (exception->ExceptionInformation[0] == 1U) access_type = "write";
        else if (exception->ExceptionInformation[0] == 8U) access_type = "execute";
    }

    append_text(&builder, "{\"schema\":\"halogen_qmoe_av_v1\",\"record\":");
    append_char(&builder, (char)('0' + record_number));
    append_field(&builder, "thread_id", (uint64_t)GetCurrentThreadId());
    append_field(&builder, "exception_code", exception->ExceptionCode);
    append_field(&builder, "exception_flags", exception->ExceptionFlags);
    append_field(&builder, "exception_address", (uintptr_t)exception->ExceptionAddress);
    append_field(&builder, "parameter_count", exception->NumberParameters);
    append_text(&builder, ",\"av_type\":\"");
    append_text(&builder, access_type);
    append_text(&builder, "\",\"av_operation\":");
    if (exception->NumberParameters >= 1U) {
        append_hex(&builder, exception->ExceptionInformation[0]);
    } else {
        append_text(&builder, "null");
    }
    append_text(&builder, ",\"fault_address\":");
    if (exception->NumberParameters >= 2U) {
        append_hex(&builder, exception->ExceptionInformation[1]);
    } else {
        append_text(&builder, "null");
    }
    append_field(&builder, "rip", context->Rip);
    append_field(&builder, "snapshot_module_count", module_count);
    if (module != NULL) {
        append_text(&builder, ",\"module_lookup\":\"arm_snapshot\",\"module_path\":");
        append_path(&builder, module->path);
        append_text(&builder, ",\"module_path_truncated\":");
        append_text(&builder, module->path_truncated ? "true" : "false");
        append_field(&builder, "module_base", module->base);
        append_field(&builder, "module_offset", context->Rip - module->base);
        append_field(&builder, "module_size", module->bytes);
    } else {
        append_text(&builder, ",\"module_lookup\":\"unknown\",\"module_path\":null,"
                              "\"module_base\":null,\"module_offset\":null");
    }
    append_field(&builder, "context_flags", context->ContextFlags);
    append_field(&builder, "rax", context->Rax);
    append_field(&builder, "rbx", context->Rbx);
    append_field(&builder, "rcx", context->Rcx);
    append_field(&builder, "rdx", context->Rdx);
    append_field(&builder, "rsi", context->Rsi);
    append_field(&builder, "rdi", context->Rdi);
    append_field(&builder, "rbp", context->Rbp);
    append_field(&builder, "rsp", context->Rsp);
    append_field(&builder, "r8", context->R8);
    append_field(&builder, "r9", context->R9);
    append_field(&builder, "r10", context->R10);
    append_field(&builder, "r11", context->R11);
    append_field(&builder, "r12", context->R12);
    append_field(&builder, "r13", context->R13);
    append_field(&builder, "r14", context->R14);
    append_field(&builder, "r15", context->R15);
    append_field(&builder, "eflags", context->EFlags);
    append_field(&builder, "mxcsr", context->MxCsr);
    append_field(&builder, "cs", context->SegCs);
    append_field(&builder, "ss", context->SegSs);
    append_text(&builder, "}\r\n");

    /* One bounded synchronous write, no retry, allocation, formatting CRT,
     * file opening, flushing, loader API, or memory probe in the handler.
     * A failure/partial write remains best effort; it cannot handle the AV.
     */
    if (builder.valid) {
        (void)WriteFile(output_file, record_buffer, builder.used, &written, NULL);
    }
    InterlockedExchange(&writer_active, 0L);
    SetLastError(saved_last_error);
    return EXCEPTION_CONTINUE_SEARCH;
}

static DWORD snapshot_modules(void)
{
    HANDLE snapshot;
    MODULEENTRY32W module;
    DWORD failure = ERROR_SUCCESS;
    BOOL more;

    snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32,
                                      GetCurrentProcessId());
    if (snapshot == INVALID_HANDLE_VALUE) return GetLastError();
    module.dwSize = sizeof(module);
    more = Module32FirstW(snapshot, &module);
    if (!more) failure = GetLastError();
    while (more) {
        struct module_entry *entry;
        DWORD length;
        if (module_count >= MODULE_LIMIT) {
            failure = ERROR_INSUFFICIENT_BUFFER;
            break;
        }
        entry = &module_map[module_count++];
        entry->base = (uintptr_t)module.modBaseAddr;
        entry->bytes = module.modBaseSize;
        length = GetModuleFileNameW(module.hModule, entry->path, PATH_CHARS);
        if (length == 0U) {
            DWORD index = 0U;
            while (index + 1U < MAX_PATH && module.szExePath[index] != L'\0') {
                entry->path[index] = module.szExePath[index];
                ++index;
            }
            entry->path[index] = L'\0';
            entry->path_truncated = (index == MAX_PATH - 1U);
        } else {
            entry->path[PATH_CHARS - 1U] = L'\0';
            entry->path_truncated = (length >= PATH_CHARS);
        }
        more = Module32NextW(snapshot, &module);
        if (!more && GetLastError() != ERROR_NO_MORE_FILES) failure = GetLastError();
    }
    (void)CloseHandle(snapshot);
    return failure;
}

static BOOL valid_output_path(const WCHAR *path)
{
    DWORD index;
    if (path == NULL ||
        !((path[0] >= L'A' && path[0] <= L'Z') ||
          (path[0] >= L'a' && path[0] <= L'z')) ||
        path[1] != L':' || path[2] != L'\\' || path[3] == L'\0') return FALSE;
    for (index = 3U; index < 32767U && path[index] != L'\0'; ++index) {
        if (path[index] == L':') return FALSE; /* no alternate stream */
    }
    return index < 32767U && path[index - 1U] != L'\\';
}

/* C ABI: DWORD __cdecl start_capture(const wchar_t *absolute_local_path).
 * 0 = armed; otherwise Win32 error code. No overwrite and no path creation.
 * Parent calls once, after all runtime DLLs load, immediately before the run.
 */
__declspec(dllexport) DWORD __cdecl start_capture(const WCHAR *path)
{
    DWORD failure = ERROR_SUCCESS;
    AcquireSRWLockExclusive(&lifecycle_lock);
    if (started_once) {
        failure = ERROR_ALREADY_EXISTS;
    } else if (!valid_output_path(path)) {
        failure = ERROR_INVALID_NAME;
    } else {
        module_count = 0U;
        failure = snapshot_modules();
        if (failure == ERROR_SUCCESS) {
            output_file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL,
                                      CREATE_NEW, FILE_ATTRIBUTE_NORMAL |
                                      FILE_FLAG_WRITE_THROUGH, NULL);
            if (output_file == INVALID_HANDLE_VALUE) {
                failure = GetLastError();
            } else if (GetFileType(output_file) != FILE_TYPE_DISK) {
                failure = ERROR_INVALID_HANDLE;
            } else {
                handler_cookie = AddVectoredExceptionHandler(1UL, capture_exception);
                if (handler_cookie == NULL) failure = ERROR_NOT_ENOUGH_MEMORY;
            }
            if (failure != ERROR_SUCCESS && output_file != INVALID_HANDLE_VALUE) {
                (void)CloseHandle(output_file);
                output_file = INVALID_HANDLE_VALUE;
            }
        }
        if (failure == ERROR_SUCCESS) {
            started_once = TRUE;
            InterlockedExchange(&enabled, 1L);
        }
    }
    ReleaseSRWLockExclusive(&lifecycle_lock);
    return failure;
}

/* Call only from an ordinary, quiescent host thread, never from a handler.
 * 0 = disabled/removed/closed. Keep the DLL loaded for the process lifetime.
 */
__declspec(dllexport) DWORD __cdecl stop_capture(void)
{
    DWORD failure = ERROR_SUCCESS;
    AcquireSRWLockExclusive(&lifecycle_lock);
    InterlockedExchange(&enabled, 0L);
    if (handler_cookie != NULL) {
        if (RemoveVectoredExceptionHandler(handler_cookie) == 0UL) {
            failure = ERROR_INVALID_HANDLE;
        } else {
            handler_cookie = NULL;
        }
    }
    while (InterlockedCompareExchange(&writer_active, 0L, 0L) != 0L) Sleep(0UL);
    if (output_file != INVALID_HANDLE_VALUE) {
        if (!CloseHandle(output_file) && failure == ERROR_SUCCESS) failure = GetLastError();
        output_file = INVALID_HANDLE_VALUE;
    }
    ReleaseSRWLockExclusive(&lifecycle_lock);
    return failure;
}

/* /ENTRY:DllMain, /NODEFAULTLIB: no CRT initialization or loader-lock work. */
BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved)
{
    (void)instance;
    (void)reason;
    (void)reserved;
    return TRUE;
}
