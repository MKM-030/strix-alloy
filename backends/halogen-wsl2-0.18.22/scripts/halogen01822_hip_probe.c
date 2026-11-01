/* Bounded HIP identity query with no model or explicit device buffers.
 * Build against HIP headers matching the candidate image runtime.
 */
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>
#include <hip/hip_runtime_api.h>

typedef hipError_t (*device_count_fn)(int *);
typedef hipError_t (*device_properties_fn)(hipDeviceProp_t *, int);

int main(void) {
    void *library = dlopen("libamdhip64.so.7", RTLD_NOW | RTLD_LOCAL);
    if (!library) {
        fprintf(stderr, "HIP runtime unavailable: %s\n", dlerror());
        return 1;
    }
    device_count_fn count_fn = (device_count_fn)dlsym(library, "hipGetDeviceCount");
    device_properties_fn properties_fn =
        (device_properties_fn)dlsym(library, "hipGetDevicePropertiesR0600");
    if (!count_fn || !properties_fn) {
        fputs("HIP 6 device query symbols unavailable\n", stderr);
        dlclose(library);
        return 1;
    }
    int count = 0;
    if (count_fn(&count) != hipSuccess || count != 1) {
        fputs("HIP must expose exactly one GPU\n", stderr);
        dlclose(library);
        return 1;
    }
    hipDeviceProp_t properties;
    memset(&properties, 0, sizeof(properties));
    if (properties_fn(&properties, 0) != hipSuccess ||
        strcmp(properties.gcnArchName, "gfx1151") != 0) {
        fputs("HIP GPU is not gfx1151\n", stderr);
        dlclose(library);
        return 1;
    }
    puts(properties.gcnArchName);
    dlclose(library);
    return 0;
}
