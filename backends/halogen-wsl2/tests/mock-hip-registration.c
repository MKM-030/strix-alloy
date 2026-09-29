#include <stddef.h>
#include <stdlib.h>
#include <string.h>

int mock_register_calls, mock_unregister_calls, mock_malloc_calls, mock_free_calls, mock_copy_calls;
int mock_fail_register, mock_fail_malloc, mock_fail_copy, mock_fail_free;
void *mock_last_device;

int hipHostRegister(void *host, size_t bytes, unsigned flags) {
    (void)host; (void)bytes; (void)flags;
    ++mock_register_calls;
    return mock_fail_register ? 7 : 0;
}
int hipHostUnregister(void *host) {
    (void)host;
    ++mock_unregister_calls;
    return 0;
}
int hipHostGetDevicePointer(void **device, void *host, unsigned flags) {
    (void)flags;
    *device = host;
    return 0;
}
int hipMalloc(void **device, size_t bytes) {
    ++mock_malloc_calls;
    if (mock_fail_malloc) return 8;
    *device = malloc(bytes);
    mock_last_device = *device;
    return *device ? 0 : 8;
}
int hipMemcpy(void *device, const void *host, size_t bytes, int kind) {
    (void)kind;
    ++mock_copy_calls;
    if (mock_fail_copy) return 9;
    memcpy(device, host, bytes);
    return 0;
}
int hipFree(void *device) {
    ++mock_free_calls;
    if (mock_fail_free) return 10;
    free(device);
    return 0;
}
