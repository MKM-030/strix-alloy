// Micro-test 2: discriminate WHEN graph replay stops seeing new data over DXG.
//  A) relaunch same graph with unchanged data            -> expect MATCH
//  B) change input via a DEVICE kernel, then replay      -> expect MATCH if staleness is host-write-only
//  C) change input via host memcpy, run DIRECT kernels   -> sanity that direct path sees new data
//  D) change input via host memcpy, then replay          -> repeat of the failing case
#include <hip/hip_runtime.h>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

#define CK(x) do { hipError_t e_ = (x); if (e_ != hipSuccess) { \
    fprintf(stderr, "HIP error %s at %s:%d\n", hipGetErrorString(e_), __FILE__, __LINE__); exit(1); } } while (0)

__global__ void scale_kernel(const float * in, float * out, int n, float a) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) out[i] = a * in[i];
}

__global__ void add_kernel(const float * x, const float * y, float * out, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) out[i] = x[i] + y[i];
}

__global__ void fill_kernel(float * out, int n, float a) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) out[i] = a;
}

static double check(const std::vector<float> & got, const std::vector<float> & ref) {
    double e = 0;
    for (size_t i = 0; i < got.size(); i++) e = fmax(e, fabs(got[i] - ref[i]));
    return e;
}

int main() {
    const int N = 1 << 16;   // 64K floats = 256 KB, fast to memcpy
    const size_t bytes = N * sizeof(float);
    float * d_in, * d_tmp, * d_bias, * d_out;
    CK(hipMalloc(&d_in, bytes));
    CK(hipMalloc(&d_tmp, bytes));
    CK(hipMalloc(&d_bias, bytes));
    CK(hipMalloc(&d_out, bytes));
    hipStream_t stream;
    CK(hipStreamCreate(&stream));

    std::vector<float> h_in(N), h_bias(N), h_ref(N), h_got(N);
    const float alpha = 2.5f;
    const int blocks = (N + 255) / 256;
    void * args_scale[] = {&d_in, &d_tmp, (void *) &N, (void *) &alpha};
    void * args_add[]   = {&d_tmp, &d_bias, (void *) &N, &d_out};

    auto set_inputs = [&](float in0, float bias0) {
        for (int i = 0; i < N; i++) { h_in[i] = in0 + 0.001f * i; h_bias[i] = bias0; }
    };
    auto calc_ref = [&]() { for (int i = 0; i < N; i++) h_ref[i] = alpha * h_in[i] + h_bias[i]; };
    auto upload = [&]() {
        CK(hipMemcpy(d_in, h_in.data(), bytes, hipMemcpyHostToDevice));
        CK(hipMemcpy(d_bias, h_bias.data(), bytes, hipMemcpyHostToDevice));
    };
    auto read_out = [&]() { CK(hipMemcpy(h_got.data(), d_out, bytes, hipMemcpyDeviceToHost)); };

    // ---- capture ----
    set_inputs(0.0f, 1.0f);
    upload();
    CK(hipStreamBeginCapture(stream, hipStreamCaptureModeRelaxed));
    CK(hipLaunchKernel((const void *) scale_kernel, dim3(blocks), dim3(256), args_scale, 0, stream));
    CK(hipLaunchKernel((const void *) add_kernel, dim3(blocks), dim3(256), args_add, 0, stream));
    hipGraph_t graph;
    CK(hipStreamEndCapture(stream, &graph));
    hipGraphExec_t exec;
    CK(hipGraphInstantiate(&exec, graph, nullptr, nullptr, 0));
    printf("captured+instantiated\n");

    // A) replay with unchanged data
    CK(hipGraphLaunch(exec, stream));
    CK(hipStreamSynchronize(stream));
    read_out();
    calc_ref();
    printf("A replay unchanged-data:      err=%.6g %s\n", check(h_got, h_ref), check(h_got, h_ref) == 0 ? "MATCH" : "MISMATCH");

    // B) change data via DEVICE kernel, then replay
    CK(hipLaunchKernel((const void *) fill_kernel, dim3(blocks), dim3(256),
        std::vector<void *>{&d_in, (void *) &N, (void *) &alpha}.data(), 0, stream));
    // h_in now must mirror the device fill: in[i] = 2.5 (constant)
    for (int i = 0; i < N; i++) { h_in[i] = 2.5f; }
    h_bias.assign(N, 1.0f);   // bias unchanged from capture (1.0)
    calc_ref();
    CK(hipStreamSynchronize(stream));
    CK(hipGraphLaunch(exec, stream));
    CK(hipStreamSynchronize(stream));
    read_out();
    printf("B device-written new data:    err=%.6g %s\n", check(h_got, h_ref), check(h_got, h_ref) == 0 ? "MATCH" : "MISMATCH");

    // C) host memcpy new data + DIRECT kernels (sanity)
    set_inputs(7.0f, -3.0f);
    upload();
    void * args_scale2[] = {&d_in, &d_tmp, (void *) &N, (void *) &alpha};
    void * args_add2[]   = {&d_tmp, &d_bias, (void *) &N, &d_out};
    CK(hipLaunchKernel((const void *) scale_kernel, dim3(blocks), dim3(256), args_scale2, 0, stream));
    CK(hipLaunchKernel((const void *) add_kernel, dim3(blocks), dim3(256), args_add2, 0, stream));
    CK(hipStreamSynchronize(stream));
    read_out();
    calc_ref();
    printf("C direct after host memcpy:   err=%.6g %s\n", check(h_got, h_ref), check(h_got, h_ref) == 0 ? "MATCH" : "MISMATCH");

    // D) host memcpy new data + replay (the failing case)
    set_inputs(-1.0f, 5.0f);
    upload();
    CK(hipGraphLaunch(exec, stream));
    CK(hipStreamSynchronize(stream));
    read_out();
    calc_ref();
    printf("D replay after host memcpy:   err=%.6g %s\n", check(h_got, h_ref), check(h_got, h_ref) == 0 ? "MATCH" : "MISMATCH");

    // D2) same again with a fresh sync + small sleep before replay
    set_inputs(-2.0f, 6.0f);
    upload();
    CK(hipDeviceSynchronize());
    CK(hipGraphLaunch(exec, stream));
    CK(hipStreamSynchronize(stream));
    read_out();
    calc_ref();
    printf("D2 replay after memcpy+devsync: err=%.6g %s\n", check(h_got, h_ref), check(h_got, h_ref) == 0 ? "MATCH" : "MISMATCH");

    // D3) host memcpy via pinned staging buffer instead of pageable
    float * h_pin;
    CK(hipHostMalloc(&h_pin, bytes));
    for (int i = 0; i < N; i++) { h_in[i] = 10.0f + 0.001f * i; h_bias[i] = 0.5f; h_pin[i] = h_in[i]; }
    CK(hipMemcpy(d_in, h_pin, bytes, hipMemcpyHostToDevice));
    for (int i = 0; i < N; i++) h_pin[i] = 0.5f;
    CK(hipMemcpy(d_bias, h_pin, bytes, hipMemcpyHostToDevice));
    CK(hipDeviceSynchronize());
    CK(hipGraphLaunch(exec, stream));
    CK(hipStreamSynchronize(stream));
    read_out();
    calc_ref();
    printf("D3 replay after pinned memcpy:  err=%.6g %s\n", check(h_got, h_ref), check(h_got, h_ref) == 0 ? "MATCH" : "MISMATCH");
    CK(hipHostFree(h_pin));

    printf("done\n");
    return 0;
}
