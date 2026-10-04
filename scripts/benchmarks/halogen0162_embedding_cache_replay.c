/* Bounded replay of the exact original M1 and shared GPU cache core.
 * Root alone compiles/runs under the existing hardware ownership and 22/18-GiB
 * guard. No checkpoint, server, embedding gather/RMS, hidden FC, NPU or full
 * head is loaded here. Synthetic keys select two frozen normalized BF16 rows;
 * the two original GPU FC outputs must match independently frozen hashes.
 * One 5120-byte cache entry makes eviction/reset checks unambiguous.
 *
 * Compilation (root only): gcc -O2 -Wall -Wextra -Werror
 * -D__HIP_PLATFORM_AMD__ -I<reviewed HIP include>
 * -DECACHE_BUILD_C_SHA=\"<reviewed cache .c SHA256>\"
 * -DECACHE_BUILD_H_SHA=\"<reviewed cache .h SHA256>\"
 * halogen0162_embedding_cache_replay.c -ldl -lcrypto -o <new binary>
 * The compile envelope must independently hash this source, frozen replay,
 * cache C/header and resulting binary. Compile-time pins are reported as such.
 * Usage (11 arguments): ENGINE HSACO HIP_LIBRARY HIP_SHA E_WEIGHT E_WEIGHT_SHA
 * A_E_INPUT A_E_SHA B_E_INPUT B_E_SHA NEW_OUTPUT_DIRECTORY.
 */
#define main frozen_original_fc_oracle_entry_unused
#include "halogen0162_fc_replay.c"
#undef main
#include <math.h>
#include <time.h>
#define HALOGEN_EMBEDDING_CACHE_CORE_ONLY 1
#include "halogen0162_mtp_embedding_cache.c"

#ifndef ECACHE_BUILD_C_SHA
#error Independently pinned cache C source hash required at compile time
#endif
#ifndef ECACHE_BUILD_H_SHA
#error Independently pinned cache header hash required at compile time
#endif
#define ORACLE_SOURCE_SHA "8535dbe608b49f8bbad8a962359de59e78df1bd0b9cae922045277b6a1d77826"
#define FIXED_E_WEIGHT_SHA "ec6ac9d2e6111b3cf9df7cc408afd555cd33ac291e5613d4000d58cd8a51107d"
#define CACHE_CYCLES 3u
#define CACHE_STEPS 8u
#define CACHE_ROWS (CACHE_CYCLES * CACHE_STEPS)
static const char *fixed_input_hashes[2]={
    "97079c27ab56da44c2ab29780c856be79803d402caf754acfbf7d187fbe34892",
    "8104e72375af48ab130c04b01fe68399e1d6c84951f9aa45c67a54b7d00db6ce"};
static const char *fixed_output_hashes[2]={
    "e474b8c6a93ccc515d7c2e96b1bda4305fd64147d1ed622594953dd260ee9e88",
    "c3625f78e90423e54aec273ca8aa9a8580dde1e4ce3edb45c1feb4b036678c31"};
static const unsigned labels[CACHE_STEPS]={0,0,1,1,0,0,1,1};
static const int32_t keys[CACHE_STEPS]={11,11,22,22,11,11,11,11};
static const int hit_expected[CACHE_STEPS]={0,1,0,1,0,1,0,1};

/* These pointers are scoped to this standalone process's sealed HIP library.
 * The frozen oracle's renamed entry has independent local API variables. */
API(hipMalloc,hipError_t,(void **,size_t));
API(hipFree,hipError_t,(void *));
API(hipMemcpy,hipError_t,(void *,const void *,size_t,hipMemcpyKind));
API(hipMemcpyAsync,hipError_t,(void *,const void *,size_t,hipMemcpyKind,hipStream_t));
API(hipStreamSynchronize,hipError_t,(hipStream_t));
API(hipEventCreateWithFlags,hipError_t,(hipEvent_t *,unsigned));
API(hipEventRecord,hipError_t,(hipEvent_t,hipStream_t));
API(hipEventQuery,hipError_t,(hipEvent_t));
API(hipEventSynchronize,hipError_t,(hipEvent_t));
API(hipEventElapsedTime,hipError_t,(float *,hipEvent_t,hipEvent_t));
API(hipEventDestroy,hipError_t,(hipEvent_t));
API(hipModuleLaunchKernel,hipError_t,(hipFunction_t,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,hipStream_t,void **,void **));

static int core_status(hipError_t status,const char *operation) {
    if (status==hipSuccess) return 0;
    fail(operation,(int)status);return -1;
}
static int core_allocate(void **pointer,size_t bytes) {
    return core_status(p_hipMalloc(pointer,bytes),"cache-core-allocation");
}
static int core_release(void *pointer) {
    return core_status(p_hipFree(pointer),"cache-core-free");
}
static int core_copy(void *to,const void *from,size_t bytes,int kind,void *stream) {
    if (kind!=3 || stream!=NULL || bytes!=ECACHE_ROW_BYTES) {
        fail("cache-core-copy-ABI",0);return -1;
    }
    return core_status(p_hipMemcpyAsync(to,from,bytes,hipMemcpyDeviceToDevice,NULL),"cache-core-ordered-D2D");
}
static int core_synchronize(void *stream) {
    if (stream!=NULL) {fail("cache-core-default-stream-required",0);return -1;}
    return core_status(p_hipStreamSynchronize(NULL),"cache-core-stream-drain");
}
static int core_event_create(void **event,unsigned flags) {
    hipEvent_t result=NULL;
    int status=core_status(p_hipEventCreateWithFlags(&result,flags),"cache-core-event-create");
    if (!status) *event=(void *)result;
    return status;
}
static int core_event_record(void *event,void *stream) {
    if (stream!=NULL) {fail("cache-core-event-default-stream-required",0);return -1;}
    return core_status(p_hipEventRecord((hipEvent_t)event,NULL),"cache-core-event-record");
}
static int core_event_query(void *event) {
    hipError_t status=p_hipEventQuery((hipEvent_t)event);
    if (status==hipSuccess) return 0;
    if (status==hipErrorNotReady) return 1;
    return core_status(status,"cache-core-event-query");
}
static int core_event_destroy(void *event) {
    return core_status(p_hipEventDestroy((hipEvent_t)event),"cache-core-event-destroy");
}
struct original_context {hipFunction_t function;void *weight;};
static int original_m1(void *opaque,const uint16_t *input,uint16_t *output) {
    struct original_context *context=opaque;
    void *input_argument=(void *)input,*output_argument=output;
    int64_t k=2560,n=2560;
    void *arguments[5]={&context->weight,&input_argument,&output_argument,&k,&n};
    launch_attempts++;
    hipError_t status=p_hipModuleLaunchKernel(context->function,160,1,1,256,1,1,0,NULL,arguments,NULL);
    if (status!=hipSuccess) return core_status(status,"original-M1-launch");
    launches_ok++;return 0;
}
struct cache_row {
    unsigned cycle,step,label,measured,completed,callback_delta;
    int32_t token;
    int expected_hit,actual_hit;
    float original_gpu_ms,cache_gpu_ms;
    double original_host_ms,cache_host_ms;
    char original_sha[65],cache_sha[65];
};
static struct cache_row rows[CACHE_ROWS];
static unsigned event_records,event_waits,event_elapsed,event_creates,event_destroys;
static uint16_t poison[WIDTH],observed[WIDTH];

static int timed_call(struct original_context *original,struct ecache_state *cache,
                      unsigned use_cache,int32_t key,uint16_t *input,uint16_t *output,
                      hipEvent_t first,hipEvent_t last,float *gpu_ms,double *host_ms,int *result) {
    struct timespec started,finished;
    if (clock_gettime(CLOCK_MONOTONIC,&started)) return fail("timing-start",errno);
    if (p_hipEventRecord(first,NULL)!=hipSuccess) return fail("timing-start-event",0);
    event_records++;
    int status=use_cache?ecache_apply(cache,key,input,output,original_m1,original):original_m1(original,input,output);
    if (status<0) return fail("timed-call-failed",status);
    if (p_hipEventRecord(last,NULL)!=hipSuccess) return fail("timing-end-event",0);
    event_records++;
    if (p_hipEventSynchronize(last)!=hipSuccess) return fail("timing-end-wait",0);
    event_waits++;
    if (clock_gettime(CLOCK_MONOTONIC,&finished)) return fail("timing-finish",errno);
    *host_ms=(double)(finished.tv_sec-started.tv_sec)*1000.0+(double)(finished.tv_nsec-started.tv_nsec)/1000000.0;
    if (p_hipEventElapsedTime(gpu_ms,first,last)!=hipSuccess) return fail("timing-elapsed",0);
    event_elapsed++;
    if (!isfinite(*gpu_ms) || *gpu_ms<0 || !isfinite(*host_ms) || *host_ms<0) return fail("invalid-timing",0);
    *result=status;return 1;
}

int main(int argc,char **argv) {
    if (argc!=12) {
        fputs("Expected ENGINE HSACO HIP_LIBRARY HIP_SHA E_WEIGHT E_WEIGHT_SHA A_E_INPUT A_E_SHA B_E_INPUT B_E_SHA NEW_OUTPUT_DIRECTORY\n",stderr);
        return 2;
    }
    int dirfd=-1,reportfd=-1,enginefd=-1,codefd=-1,runtimefd=-1;
    void *library=NULL,*code=NULL,*weight=NULL,*device_weight=NULL,*device_input=NULL,*device_output=NULL;
    hipModule_t module=NULL;
    struct original_context original={0};
    struct ecache_state cache={0};
    struct ecache_stats final_stats={0};
    unsigned cache_closed=0,completed=0,canonical=0,files_rechecked=0;
    unsigned drained=0,cleanup_failures=0,host_close_failures=0,own_allocations=0,own_frees=0;
    hipEvent_t timing_events[2]={NULL,NULL};
    struct stat engine_identity,code_identity,runtime_identity,weight_identity;
    char weight_sha[65]={0},code_sha[65]={0};
    int runtime_version=0,driver_version=0,passed=0;
    const char *wave=getenv("HALOGEN_LQ8_WAVE");
    API(hipGetDeviceCount,hipError_t,(int *));
    API(hipGetDevicePropertiesR0600,hipError_t,(hipDeviceProp_t *,int));
    API(hipSetDevice,hipError_t,(int));
    API(hipRuntimeGetVersion,hipError_t,(int *));
    API(hipDriverGetVersion,hipError_t,(int *));
    API(hipModuleLoadData,hipError_t,(hipModule_t *,const void *));
    API(hipModuleGetFunction,hipError_t,(hipFunction_t *,hipModule_t,const char *));
    API(hipModuleUnload,hipError_t,(hipModule_t));
    if (argv[11][0]!='/' || mkdir(argv[11],0700)) {fputs("Exclusive output directory required\n",stderr);return 2;}
    dirfd=open(argv[11],O_DIRECTORY|O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (dirfd<0) {fail("output-directory-open",errno);goto cleanup;}
    reportfd=openat(dirfd,"cache-replay.json",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (reportfd<0) {fail("exclusive-report-open",errno);goto cleanup;}
    if (wave && strcmp(wave,"1")) {fail("original-wave-default-or-one-required",0);goto cleanup;}
    if (!valid_sha(argv[4]) || !valid_sha(ECACHE_BUILD_C_SHA) || !valid_sha(ECACHE_BUILD_H_SHA) ||
            strcmp(argv[6],FIXED_E_WEIGHT_SHA) || strcmp(argv[8],fixed_input_hashes[0]) || strcmp(argv[10],fixed_input_hashes[1])) {
        fail("independent-frozen-source-fixture-pins-required",0);goto cleanup;
    }
    enginefd=open_regular(argv[1],ENGINE_BYTES,ENGINE_BYTES,&engine_identity);
    codefd=open_regular(argv[2],CODE_BYTES,CODE_BYTES,&code_identity);
    runtimefd=open_regular(argv[3],0,128<<20,&runtime_identity);
    if (enginefd<0 || codefd<0 || runtimefd<0) goto cleanup;
    if (!hash_file(enginefd,ENGINE_SHA) || !verify_identity(enginefd,&engine_identity) ||
            !hash_file(runtimefd,argv[4]) || !verify_identity(runtimefd,&runtime_identity)) goto cleanup;
    code=malloc(CODE_BYTES);weight=malloc(WEIGHT_BYTES);
    if (!code || !weight) {fail("bounded-host-payload-allocation",errno);goto cleanup;}
    if (!read_exact(codefd,code,CODE_BYTES) || !verify_identity(codefd,&code_identity) ||
            !hash_memory(code,CODE_BYTES,code_sha) || strcmp(code_sha,CODE_SHA)) {
        fail("sealed-codeobject-differs",0);goto cleanup;
    }
    if (lseek(enginefd,CODE_OFFSET,SEEK_SET)!=CODE_OFFSET) {fail("embedded-code-seek",errno);goto cleanup;}
    unsigned char block[16384];size_t offset=0;
    while (offset<CODE_BYTES) {
        size_t amount=CODE_BYTES-offset;if (amount>sizeof block) amount=sizeof block;
        if (!read_exact(enginefd,block,amount)) goto cleanup;
        if (memcmp(block,(const unsigned char *)code+offset,amount)) {fail("original-embedded-code-mismatch",0);goto cleanup;}
        offset+=amount;
    }
    if (!verify_identity(enginefd,&engine_identity) ||
            !load_bytes(argv[5],argv[6],weight,WEIGHT_BYTES,weight_sha,&weight_identity) ||
            !load_fixture(&fixtures[0],0,argv[7],argv[8]) || !load_fixture(&fixtures[2],0,argv[9],argv[10]) ||
            !verify_again(argv[3],argv[4],(size_t)runtime_identity.st_size,&runtime_identity)) goto cleanup;
    library=dlopen(argv[3],RTLD_NOW|RTLD_LOCAL);
    if (!library) {fail("pinned-HIP-library-open",0);goto cleanup;}
    RESOLVE(hipGetDeviceCount);RESOLVE(hipGetDevicePropertiesR0600);RESOLVE(hipSetDevice);
    RESOLVE(hipRuntimeGetVersion);RESOLVE(hipDriverGetVersion);RESOLVE(hipModuleLoadData);
    RESOLVE(hipModuleGetFunction);RESOLVE(hipModuleLaunchKernel);RESOLVE(hipModuleUnload);
    RESOLVE(hipMalloc);RESOLVE(hipFree);RESOLVE(hipMemcpy);RESOLVE(hipMemcpyAsync);RESOLVE(hipStreamSynchronize);
    RESOLVE(hipEventCreateWithFlags);RESOLVE(hipEventRecord);RESOLVE(hipEventQuery);
    RESOLVE(hipEventSynchronize);RESOLVE(hipEventElapsedTime);RESOLVE(hipEventDestroy);
    int count=0;hipDeviceProp_t properties;
    memset(&properties,0,sizeof properties);
    HIP_OK(p_hipGetDeviceCount(&count),"GPU-count");
    HIP_OK(p_hipGetDevicePropertiesR0600(&properties,0),"GPU-properties");
    if (count!=1 || strcmp(properties.gcnArchName,"gfx1151") || properties.warpSize!=32) {
        fail("single-original-gfx1151-wave32-required",count);goto cleanup;
    }
    HIP_OK(p_hipSetDevice(0),"GPU-select");
    HIP_OK(p_hipRuntimeGetVersion(&runtime_version),"runtime-version");
    HIP_OK(p_hipDriverGetVersion(&driver_version),"driver-version");
    HIP_OK(p_hipModuleLoadData(&module,code),"original-module-load");module_loads++;
    HIP_OK(p_hipModuleGetFunction(&original.function,module,KERNEL_EMBEDDING),"original-exact-M1-symbol");
    HIP_OK(p_hipMalloc(&device_weight,WEIGHT_BYTES),"GPU-weight-allocation");own_allocations++;
    HIP_OK(p_hipMalloc(&device_input,ECACHE_ROW_BYTES),"GPU-input-allocation");own_allocations++;
    HIP_OK(p_hipMalloc(&device_output,ECACHE_ROW_BYTES),"GPU-output-allocation");own_allocations++;
    if (((uintptr_t)device_weight&15) || ((uintptr_t)device_input&1) || ((uintptr_t)device_output&1)) {
        fail("original-pointer-alignment-required",0);goto cleanup;
    }
    original.weight=device_weight;
    HIP_OK(p_hipMemcpy(device_weight,weight,WEIGHT_BYTES,hipMemcpyHostToDevice),"unchanged-raw-Q8-copy");copies_ok++;
    for (size_t index=0;index<WIDTH;index++) poison[index]=0x7fc0;
    for (unsigned label=0;label<2;label++) {
        struct fixture *fixture=&fixtures[label*2];
        HIP_OK(p_hipMemcpy(device_input,fixture->input,ECACHE_ROW_BYTES,hipMemcpyHostToDevice),"canonical-normalized-input-copy");copies_ok++;
        HIP_OK(p_hipMemcpy(device_output,poison,ECACHE_ROW_BYTES,hipMemcpyHostToDevice),"canonical-output-poison");copies_ok++;
        if (original_m1(&original,device_input,device_output)) goto cleanup;
        HIP_OK(p_hipStreamSynchronize(NULL),"canonical-stream-wait");synchronizations_ok++;
        HIP_OK(p_hipMemcpy(fixture->output,device_output,ECACHE_ROW_BYTES,hipMemcpyDeviceToHost),"canonical-output-copy");copies_ok++;
        if (!hash_memory(fixture->output,ECACHE_ROW_BYTES,fixture->output_sha) || strcmp(fixture->output_sha,fixed_output_hashes[label])) {
            fail("frozen-original-GPU-output-hash-mismatch",0);goto cleanup;
        }
        canonical++;
    }
    for (unsigned index=0;index<2;index++) {
        HIP_OK(p_hipEventCreateWithFlags(&timing_events[index],0),"timing-event-create");event_creates++;
    }
    struct ecache_ops operations={.abi_version=ECACHE_ABI_VERSION,.allocate=core_allocate,.release=core_release,
        .copy_async=core_copy,.stream_synchronize=core_synchronize,.event_create=core_event_create,
        .event_record=core_event_record,.event_query=core_event_query,.event_destroy=core_event_destroy};
    unsigned char generation[16]={0};generation[0]=1;
    if (ecache_init(&cache,&operations,generation,1)) {fail("cache-core-init",0);goto cleanup;}
    for (unsigned cycle=0;cycle<CACHE_CYCLES;cycle++) {
        if (cycle) {
            generation[0]=(unsigned char)(1+cycle*2);
            if (ecache_reset(&cache,generation)) {fail("cache-cycle-reset",0);goto cleanup;}
        }
        for (unsigned step=0;step<CACHE_STEPS;step++) {
            struct cache_row *row=&rows[cycle*CACHE_STEPS+step];
            unsigned label=labels[step];struct fixture *fixture=&fixtures[label*2];
            row->cycle=cycle;row->step=step;row->label=label;row->measured=cycle!=0;
            row->token=keys[step];row->expected_hit=hit_expected[step];
            if (step==6) {
                generation[0]=(unsigned char)(2+cycle*2);
                if (ecache_reset(&cache,generation)) {fail("cache-generation-reset",0);goto cleanup;}
            }
            HIP_OK(p_hipMemcpy(device_input,fixture->input,ECACHE_ROW_BYTES,hipMemcpyHostToDevice),"row-input-copy");copies_ok++;
            HIP_OK(p_hipMemcpy(device_output,poison,ECACHE_ROW_BYTES,hipMemcpyHostToDevice),"row-native-poison");copies_ok++;
            int status=0;
            if (!timed_call(&original,&cache,0,row->token,device_input,device_output,timing_events[0],timing_events[1],
                            &row->original_gpu_ms,&row->original_host_ms,&status)) goto cleanup;
            HIP_OK(p_hipMemcpy(observed,device_output,ECACHE_ROW_BYTES,hipMemcpyDeviceToHost),"row-native-output-copy");copies_ok++;
            if (memcmp(observed,fixture->output,ECACHE_ROW_BYTES) || !hash_memory(observed,ECACHE_ROW_BYTES,row->original_sha) ||
                    strcmp(row->original_sha,fixed_output_hashes[label])) {fail("row-native-output-mismatch",0);goto cleanup;}
            HIP_OK(p_hipMemcpy(device_output,poison,ECACHE_ROW_BYTES,hipMemcpyHostToDevice),"row-cache-poison");copies_ok++;
            unsigned before=launches_ok;
            if (!timed_call(&original,&cache,1,row->token,device_input,device_output,timing_events[0],timing_events[1],
                            &row->cache_gpu_ms,&row->cache_host_ms,&status)) goto cleanup;
            row->actual_hit=status==ECACHE_HIT;row->callback_delta=launches_ok-before;
            if (status!=row->expected_hit || row->callback_delta!=(row->expected_hit?0u:1u)) {
                fail("cache-hit-miss-or-original-launch-count-mismatch",status);goto cleanup;
            }
            HIP_OK(p_hipMemcpy(observed,device_output,ECACHE_ROW_BYTES,hipMemcpyDeviceToHost),"row-cache-output-copy");copies_ok++;
            if (memcmp(observed,fixture->output,ECACHE_ROW_BYTES) || !hash_memory(observed,ECACHE_ROW_BYTES,row->cache_sha) ||
                    strcmp(row->cache_sha,fixed_output_hashes[label])) {fail("row-cache-output-mismatch",0);goto cleanup;}
            row->completed=1;completed++;
        }
    }
    if (!verify_again(argv[1],ENGINE_SHA,ENGINE_BYTES,&engine_identity) ||
            !verify_again(argv[2],CODE_SHA,CODE_BYTES,&code_identity) ||
            !verify_again(argv[3],argv[4],(size_t)runtime_identity.st_size,&runtime_identity) ||
            !verify_again(argv[5],argv[6],WEIGHT_BYTES,&weight_identity) ||
            !verify_again(argv[7],argv[8],ECACHE_ROW_BYTES,&fixtures[0].input_identity) ||
            !verify_again(argv[9],argv[10],ECACHE_ROW_BYTES,&fixtures[2].input_identity)) goto cleanup;
    files_rechecked=1;
cleanup:
    if (library && p_hipStreamSynchronize) {
        if (p_hipStreamSynchronize(NULL)==hipSuccess) drained=1;else cleanup_failures++;
    }
    if (cache.initialized) {
        if (!drained) cleanup_failures++;
        else if (ecache_close(&cache)) {cleanup_failures++;drained=0;}
        else cache_closed=1;
        final_stats=cache.stats;
    }
    for (unsigned index=0;index<2;index++) {
        if (timing_events[index]) {
            if (!drained || !p_hipEventDestroy || p_hipEventDestroy(timing_events[index])!=hipSuccess) cleanup_failures++;
            else event_destroys++;
        }
    }
    void *owned_pointers[3]={device_output,device_input,device_weight};
    for (unsigned index=0;index<3;index++) if (owned_pointers[index]) {
        if (!drained || !p_hipFree || p_hipFree(owned_pointers[index])!=hipSuccess) cleanup_failures++;
        else own_frees++;
    }
    if (module) {
        if (!drained || !p_hipModuleUnload || p_hipModuleUnload(module)!=hipSuccess) cleanup_failures++;
        else module_unloads++;
    }
    if (library && drained && dlclose(library)) cleanup_failures++;
    if (enginefd>=0 && close(enginefd)) host_close_failures++;
    if (codefd>=0 && close(codefd)) host_close_failures++;
    if (runtimefd>=0 && close(runtimefd)) host_close_failures++;
    if (!library || drained) {free(code);free(weight);}
    if (cleanup_failures) fail("GPU-cleanup-failed",(int)cleanup_failures);
    if (host_close_failures) fail("host-input-close-failed",(int)host_close_failures);
    passed=!error_reason && files_rechecked && completed==CACHE_ROWS && canonical==2 && drained && cache_closed &&
        launch_attempts==38 && launches_ok==38 && own_allocations==3 && own_frees==3 &&
        module_loads==1 && module_unloads==1 && event_creates==2 && event_destroys==2 &&
        event_records==96 && event_waits==48 && event_elapsed==48 &&
        final_stats.calls==24 && final_stats.hits==12 && final_stats.misses==12 &&
        final_stats.original_calls==12 && final_stats.captures==12 && final_stats.failures==0 &&
        final_stats.allocations==1 && final_stats.frees==1 && final_stats.evictions==6 && final_stats.resets==5 &&
        final_stats.copy_enqueues==24 && final_stats.event_queries==18 && final_stats.pending_fallbacks==0 &&
        final_stats.events_created==1 && final_stats.events_destroyed==1 && final_stats.stream_drains==6;
    if (reportfd>=0) {
        FILE *report=fdopen(reportfd,"w");
        if (!report) {
            fail("report-stream-open",errno);passed=0;
            if (close(reportfd)) host_close_failures++;
            reportfd=-1;
        }
        else {
            reportfd=-1;
            fprintf(report,"{\"schema\":\"halogen0162.original-q8-embedding-cache-replay.v1\",\"passed\":%s,"
                    "\"successful_process_exit_required\":true,"
                    "\"engine_sha256\":\"%s\",\"codeobject_sha256\":\"%s\",\"runtime_sha256\":\"%s\","
                    "\"frozen_replay_source_sha256\":\"%s\",\"compile_time_cache_source_sha256\":\"%s\","
                    "\"compile_time_cache_header_sha256\":\"%s\",\"runtime_version\":%d,\"driver_version\":%d,"
                    "\"capacity\":1,\"cache_row_GPU_bytes\":5120,\"event_driver_memory_excluded\":true,"
                    "\"warmup_cycles\":1,\"measured_cycles\":2,\"shared_core_only\":true,"
                    "\"paired_order\":\"original_then_cache\",\"selected_hit_rate_is_synthetic\":true,"
                    "\"synthetic_token_keys\":true,\"checkpoint_loaded\":false,\"server_restarted\":false,"
                    "\"embedding_gather_RMS_qualified\":false,\"head_integration_qualified\":false,"
                    "\"pending_lookup_behavior_qualified\":false,\"live_model_lifetime_qualified\":false,"
                    "\"acceptance_claim\":false,\"end_to_end_throughput_qualified\":false,\"NPU_executed\":false,"
                    "\"scope\":\"shared core only; native M1 on frozen normalized BF16 A/B; hit, eviction and generation reset\","
                    "\"timing_scope\":\"event and monotonic enqueue-through-end-event-wait for original M1 or cache apply; includes cache D2D/publication/event query; excludes input/poison/output copies, reset/setup, hashing and validation\","
                    "\"original_GPU_outputs_verified\":%u,\"completed_calls\":%u,\"launch_attempts\":%u,\"launches_ok\":%u,"
                    "\"input_validation_copies\":%u,\"immutable_files_rechecked\":%s,\"cleanup_errors\":%u,"
                    "\"own_allocations\":%u,\"own_frees\":%u,\"module_loads\":%u,\"module_unloads\":%u,"
                    "\"timing_event_creates\":%u,\"timing_event_destroys\":%u,\"timing_event_records\":%u,"
                    "\"timing_event_waits\":%u,\"timing_event_elapsed\":%u,"
                    "\"cache_closed\":%s,\"cache_stats\":{\"calls\":%" PRIu64 ",\"hits\":%" PRIu64 ",\"misses\":%" PRIu64 ","
                    "\"original_calls\":%" PRIu64 ",\"captures\":%" PRIu64 ",\"pending_fallbacks\":%" PRIu64 ","
                    "\"evictions\":%" PRIu64 ",\"failures\":%" PRIu64 ",\"resets\":%" PRIu64 ",\"stream_drains\":%" PRIu64 ","
                    "\"copy_enqueues\":%" PRIu64 ",\"event_queries\":%" PRIu64 ",\"allocations\":%" PRIu64 ",\"frees\":%" PRIu64 ","
                    "\"events_created\":%" PRIu64 ",\"events_destroyed\":%" PRIu64 "},"
                    "\"error\":\"%s\",\"error_code\":%d,\"rows\":[",
                    passed?"true":"false",ENGINE_SHA,CODE_SHA,argv[4],ORACLE_SOURCE_SHA,ECACHE_BUILD_C_SHA,ECACHE_BUILD_H_SHA,
                    runtime_version,driver_version,canonical,completed,launch_attempts,launches_ok,copies_ok,
                    files_rechecked?"true":"false",cleanup_failures,own_allocations,own_frees,module_loads,module_unloads,
                    event_creates,event_destroys,event_records,event_waits,event_elapsed,cache_closed?"true":"false",
                    final_stats.calls,final_stats.hits,final_stats.misses,final_stats.original_calls,final_stats.captures,
                    final_stats.pending_fallbacks,final_stats.evictions,final_stats.failures,final_stats.resets,final_stats.stream_drains,
                    final_stats.copy_enqueues,final_stats.event_queries,final_stats.allocations,final_stats.frees,
                    final_stats.events_created,final_stats.events_destroyed,
                    error_reason?error_reason:"",error_code);
            unsigned written=0;
            for (unsigned index=0;index<CACHE_ROWS;index++) if (rows[index].completed) {
                struct cache_row *row=&rows[index];
                fprintf(report,"%s{\"cycle\":%u,\"step\":%u,\"label\":\"%s\",\"measured\":%s,\"token\":%" PRId32 ","
                        "\"expected_hit\":%s,\"actual_hit\":%s,\"original_callback_delta\":%u,\"original_gpu_ms\":%.9g,"
                        "\"cache_gpu_ms\":%.9g,\"original_host_ms\":%.12g,\"cache_host_ms\":%.12g,"
                        "\"original_output_sha256\":\"%s\",\"cache_output_sha256\":\"%s\",\"byte_equal\":true}",
                        written++?",":"",row->cycle,row->step,row->label?"B":"A",row->measured?"true":"false",row->token,
                        row->expected_hit?"true":"false",row->actual_hit?"true":"false",row->callback_delta,
                        (double)row->original_gpu_ms,(double)row->cache_gpu_ms,row->original_host_ms,row->cache_host_ms,
                        row->original_sha,row->cache_sha);
            }
            fputs("]}\n",report);
            if (fflush(report) || ferror(report) || fsync(fileno(report))) {fail("report-write-flush",errno);passed=0;}
            if (fclose(report)) {fail("report-close",errno);passed=0;}
        }
    } else passed=0;
    if (dirfd>=0) {
        if (fsync(dirfd)) {fail("report-directory-fsync",errno);passed=0;}
        if (close(dirfd)) {fail("report-directory-close",errno);passed=0;}
    }
    fprintf(stderr,"embedding-cache replay passed=%d complete=%u native_launches=%u hit=%" PRIu64 " miss=%" PRIu64 " error=%s\n",
            passed,completed,launches_ok,final_stats.hits,final_stats.misses,error_reason?error_reason:"");
    /* A failed drain retains live GPU/module/library resources. Terminate this
     * owned standalone process without running runtime destructors on them. */
    if (library && !drained) _exit(1);
    return passed?0:1;
}
