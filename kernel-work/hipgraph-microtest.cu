// Micro-test: HIP graph capture / instantiate / replay over DXG, with numerical verification.
// Proves the runtime path llama.cpp's GGML_HIP_GRAPHS relies on actually works here:
//   capture 2 kernels into a graph, instantiate, replay with updated input values,
//   verify results match the same computation run directly on the stream.
// Build: hipcc -O2 -o hipgraph-microtest hipgraph-microtest.cu
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

int main() {
    const int N = 1 << 20;
    const size_t bytes = N * sizeof(float);
    float * d_in, * d_tmp, * d_bias, * d_out;
    CK(hipMalloc(&d_in, bytes));
    CK(hipMalloc(&d_tmp, bytes));
    CK(hipMalloc(&d_bias, bytes));
    CK(hipMalloc(&d_out, bytes));
    hipStream_t stream;
    CK(hipStreamCreate(&stream));

    std::vector<float> h_in(N), h_bias(N), h_ref(N), h_got(N);
    for (int i = 0; i < N; i++) { h_in[i] = 0.001f * i; h_bias[i] = 1.0f; }
    CK(hipMemcpy(d_in, h_in.data(), bytes, hipMemcpyHostToDevice));
    CK(hipMemcpy(d_bias, h_bias.data(), bytes, hipMemcpyHostToDevice));

    const float alpha = 2.5f;
    const int blocks = (N + 255) / 256;

    void * args_scale[] = {&d_in, &d_tmp, (void *) &N, (void *) &alpha};
    void * args_add[]   = {&d_tmp, &d_bias, (void *) &N, &d_out};
    void * args_add2[]  = {&d_tmp, &d_bias, (void *) &N, &d_out};

    // ---- capture: out = alpha*in + bias ----
    CK(hipStreamBeginCapture(stream, hipStreamCaptureModeRelaxed));
    CK(hipLaunchKernel((const void *) scale_kernel, dim3(blocks), dim3(256), args_scale, 0, stream));
    CK(hipLaunchKernel((const void *) add_kernel, dim3(blocks), dim3(256), args_add, 0, stream));
    hipGraph_t graph;
    CK(hipStreamEndCapture(stream, &graph));
    size_t nodes = 0;
    CK(hipGraphGetNodes(graph, nullptr, &nodes));
    printf("captured graph with %zu nodes\n", nodes);

    hipGraphExec_t exec;
    CK(hipGraphInstantiate(&exec, graph, nullptr, nullptr, 0));
    printf("instantiated OK\n");

    // ---- replay 1, verify against direct execution ----
    CK(hipGraphLaunch(exec, stream));
    CK(hipStreamSynchronize(stream));
    CK(hipMemcpy(h_got.data(), d_out, bytes, hipMemcpyDeviceToHost));
    CK(hipLaunchKernel((const void *) scale_kernel, dim3(blocks), dim3(256), args_scale, 0, stream));
    CK(hipLaunchKernel((const void *) add_kernel, dim3(blocks), dim3(256), args_add2, 0, stream));
    CK(hipStreamSynchronize(stream));
    CK(hipMemcpy(h_ref.data(), d_out, bytes, hipMemcpyDeviceToHost));
    double maxerr1 = 0;
    for (int i = 0; i < N; i++) maxerr1 = fmax(maxerr1, fabs(h_got[i] - h_ref[i]));
    printf("replay1 vs direct: max abs err = %.6g -> %s\n", maxerr1, maxerr1 == 0 ? "MATCH" : "MISMATCH");

    // ---- replay 2 with changed input values (tests reuse across changing data, like expert ids/positions) ----
    for (int i = 0; i < N; i++) { h_in[i] = 7.0f - 0.002f * i; h_bias[i] = -3.0f; }
    CK(hipMemcpy(d_in, h_in.data(), bytes, hipMemcpyHostToDevice));
    CK(hipMemcpy(d_bias, h_bias.data(), bytes, hipMemcpyHostToDevice));
    CK(hipGraphLaunch(exec, stream));   // same instantiated graph, new data
    CK(hipStreamSynchronize(stream));
    CK(hipMemcpy(h_got.data(), d_out, bytes, hipMemcpyDeviceToHost));
    double maxerr2 = 0;
    for (int i = 0; i < N; i++) {
        float ref = alpha * h_in[i] + h_bias[i];
        maxerr2 = fmax(maxerr2, fabs(h_got[i] - ref));
    }
    printf("replay2 (new data, same graph): max abs err = %.6g -> %s\n", maxerr2, maxerr2 == 0 ? "MATCH" : "MISMATCH");

    // ---- timing: 1000 replays vs 1000 direct pairs ----
    hipEvent_t e0, e1;
    CK(hipEventCreate(&e0));
    CK(hipEventCreate(&e1));
    float ms_graph, ms_direct;
    CK(hipEventRecord(e0, stream));
    for (int r = 0; r < 1000; r++) CK(hipGraphLaunch(exec, stream));
    CK(hipEventRecord(e1, stream));
    CK(hipEventSynchronize(e1));
    CK(hipEventElapsedTime(&ms_graph, e0, e1));

    CK(hipEventRecord(e0, stream));
    for (int r = 0; r < 1000; r++) {
        CK(hipLaunchKernel((const void *) scale_kernel, dim3(blocks), dim3(256), args_scale, 0, stream));
        CK(hipLaunchKernel((const void *) add_kernel, dim3(blocks), dim3(256), args_add2, 0, stream));
    }
    CK(hipEventRecord(e1, stream));
    CK(hipEventSynchronize(e1));
    CK(hipEventElapsedTime(&ms_direct, e0, e1));
    printf("2000 kernels x1000: graph %.1f us/iter, direct %.1f us/iter\n", ms_graph, ms_direct);

    bool ok = maxerr1 == 0 && maxerr2 == 0 && nodes == 2u;
    printf("%s\n", ok ? "MICROTEST PASS" : "MICROTEST FAIL");
    return ok ? 0 : 1;
}
