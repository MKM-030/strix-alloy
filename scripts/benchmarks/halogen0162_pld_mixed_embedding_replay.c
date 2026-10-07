/* Finite original-GPU batch versus prepared-prefix/native-tail component.
 * Source preparation only: root alone reviews, compiles and executes under its
 * exclusive owned process/container/deadline/reserve guard. Frozen v3 unchanged.
 * Includes only the sealed FC host scaffold; its renamed entry is never called.
 * Original gather/RMS/M1/M2/M3/M4/seed kernels, default stream, block256.
 * Private two-row raw fixture table with SYNTHETIC IDs0/1; no live table/token,
 * NPU, transport, hidden-RMS, full-head/state/acceptance or token-rate claim.
 * Four warmup+sixteen measured pairs for each k2/k3/k4, starting A and B.
 * GPU setup supplies original M1 prefix projections and original M4 hidden
 * projections; prefix/hidden assembly, copies, poison and validation are untimed.
 * B(k)=full-k gather/RMS/Mk; T(1)=offset correction gather/RMS/M1.
 * Each path then executes original full-k seed into separate output storage.
 * Exact E/seed parity and repeat stability are mandatory; no tolerance/fitting.
 * Build ROOT ONLY: gcc -O2 -Wall -Wextra -Werror -D__HIP_PLATFORM_AMD__
 *  -I<reviewed-hip-include> -DMIXED_COMPONENT_BUILD_SHA=\"<source-sha256>\"
 *  halogen0162_pld_mixed_embedding_replay.c -ldl -lcrypto -lm -o <new-binary>
 * Pin this source AND included halogen0162_fc_replay.c in the compile envelope.
 * Usage (19 arguments after executable): ENGINE HSACO HIP_LIBRARY HIP_SHA
 *  E_WEIGHT E_SHA H_WEIGHT H_SHA A_RAW A_RAW_SHA B_RAW B_RAW_SHA GAMMA GAMMA_SHA
 *  A_H_NORM A_H_SHA B_H_NORM B_H_SHA NEW_OUTPUT_DIRECTORY
 */
#define main frozen_original_fc_oracle_entry_unused
#include "halogen0162_fc_replay.c"
#undef main
#include <math.h>
#include <time.h>

#ifndef MIXED_COMPONENT_BUILD_SHA
#error Independently pinned mixed component C source hash required at compile time
#endif
#define ORACLE_SOURCE_SHA "8535dbe608b49f8bbad8a962359de59e78df1bd0b9cae922045277b6a1d77826"
#define MIXED_CASES 6u
#define MIXED_WARMUPS 4u
#define MIXED_REPS 16u
#define MIXED_PAIRS (MIXED_WARMUPS+MIXED_REPS)
#define E_ROW_BYTES (WIDTH*sizeof(uint16_t))
#define E_BATCH_BYTES (4u*E_ROW_BYTES)
#define H_BATCH_BYTES (4u*MAX_TENSOR_BYTES)
#define GATHER_SYMBOL "_ZN7halogen12_GLOBAL__N_114k_embed_gatherEPKtPKiPt"
#define RMS_SYMBOL "_ZN7halogen12_GLOBAL__N_117k_rmsnorm_groupedEPKtS2_Ptii"
#define SEED_SYMBOL "_ZN7halogen12_GLOBAL__N_116k_hyper_seed_addEPKtS2_Pt"

static const char *fc_symbols[4]={KERNEL_EMBEDDING,
    "_ZN7halogen12_GLOBAL__N_16k_lq8wILi2ELi16ELi1EEEvPKhPKtPtll",
    "_ZN7halogen12_GLOBAL__N_16k_lq8wILi3ELi16ELi1EEEvPKhPKtPtll",KERNEL_HIDDEN};
static const char *input_names[7]={"embedding-weight","hidden-weight","A-raw",
    "B-raw","raw-gamma","A-hidden-norm","B-hidden-norm"};
static const char *input_pins[7]={
    "ec6ac9d2e6111b3cf9df7cc408afd555cd33ac291e5613d4000d58cd8a51107d",
    "018511894df3996e3a2fcb1dff60860c45a808b65036fd38db472b6e985bdd3f",
    "af284c0101ac76b7562b3d9e19cfc6721266f282358d8f313a09b961435ee374",
    "e14b7e6b5bd1a53d1e0c26d0eb9d2356728668a89a2e591707c463cc1e2b01b4",
    "04c4a570850e06f2d8913da8220d54d4c7f87db6eb6d45480b938e8ba41d6a86",
    "bf43576e6a9d47efb9a15bcba42d74618ade2ea64b025e747d1c6960e2ddff34",
    "0a46c80b3de775d94eee31b1ca4b3927fe8368353f12f5a40314d88591a31711"};
static const char *runtime_pin="6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5";
static const char *norm_pins[2]={
    "97079c27ab56da44c2ab29780c856be79803d402caf754acfbf7d187fbe34892",
    "8104e72375af48ab130c04b01fe68399e1d6c84951f9aa45c67a54b7d00db6ce"};
static const char *e_pins[2]={
    "e474b8c6a93ccc515d7c2e96b1bda4305fd64147d1ed622594953dd260ee9e88",
    "c3625f78e90423e54aec273ca8aa9a8580dde1e4ce3edb45c1feb4b036678c31"};
static const char *h_pins[2]={
    "9a5ee795e87adaf5b1778dfc5e108789fbef4731b5d8d323bf6279435c743fcc",
    "cd2b863552798729181fe5670859f3f272ddd694370c2803b84271b3c456a138"};

API(hipGetDeviceCount,hipError_t,(int *));
API(hipGetDevicePropertiesR0600,hipError_t,(hipDeviceProp_t *,int));
API(hipSetDevice,hipError_t,(int));
API(hipRuntimeGetVersion,hipError_t,(int *));
API(hipDriverGetVersion,hipError_t,(int *));
API(hipModuleLoadData,hipError_t,(hipModule_t *,const void *));
API(hipModuleGetFunction,hipError_t,(hipFunction_t *,hipModule_t,const char *));
API(hipModuleLaunchKernel,hipError_t,(hipFunction_t,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,hipStream_t,void **,void **));
API(hipModuleUnload,hipError_t,(hipModule_t));
API(hipMalloc,hipError_t,(void **,size_t));
API(hipFree,hipError_t,(void *));
API(hipMemcpy,hipError_t,(void *,const void *,size_t,hipMemcpyKind));
API(hipDeviceSynchronize,hipError_t,(void));
API(hipEventCreateWithFlags,hipError_t,(hipEvent_t *,unsigned));
API(hipEventRecord,hipError_t,(hipEvent_t,hipStream_t));
API(hipEventSynchronize,hipError_t,(hipEvent_t));
API(hipEventElapsedTime,hipError_t,(float *,hipEvent_t,hipEvent_t));
API(hipEventDestroy,hipError_t,(hipEvent_t));

enum buffer_id {D_TABLE,D_GAMMA,D_EW,D_HW,D_HNORM,D_EATLAS,D_HATLAS,D_IDS_A,D_IDS_B,
    D_HIDS_A,D_HIDS_B,D_INPUT,D_STOCK_E,D_SLAB,D_HIDDEN,D_STOCK_SEED,D_MIXED_SEED,D_BUFFERS};
static const size_t buffer_bytes[D_BUFFERS]={2*E_ROW_BYTES,E_ROW_BYTES,WEIGHT_BYTES,
    WEIGHT_BYTES,2*MAX_TENSOR_BYTES,2*E_ROW_BYTES,2*MAX_TENSOR_BYTES,16,16,64,64,
    E_BATCH_BYTES,E_BATCH_BYTES,E_BATCH_BYTES,H_BATCH_BYTES,H_BATCH_BYTES,H_BATCH_BYTES};
static void *device[D_BUFFERS];
static hipFunction_t gather_function,rms_function,seed_function,fc_functions[4];
static hipEvent_t events[3];
static unsigned event_creates,event_records,event_waits,event_elapsed,event_destroys;
static unsigned drain_attempts,drain_ok,component_pairs,parity_pairs,outputs_written;
static uint16_t raw_rows[2][WIDTH],gamma_row[WIDTH],h_norm_rows[2][MAX_WORDS];
static uint16_t e_oracle[2][WIDTH],h_oracle[2][MAX_WORDS],normalized[2][WIDTH];
static uint16_t poison[4*MAX_WORDS];
static int32_t ids[2][4]={{0,1,0,1},{1,0,1,0}};
static int32_t hidden_ids[2][16];

struct path_timing {float branch_ms,seed_ms,total_ms;double host_ms;};
struct pair_timing {struct path_timing path[2];unsigned completed,measured,stock_first;};
struct component_case {
    unsigned k,label,completed,copied_mask;
    uint16_t e[2][4*WIDTH],seed[2][4*MAX_WORDS],seed_reference[4*MAX_WORDS];
    char e_sha[2][65],seed_sha[2][65];
    struct pair_timing timing[MIXED_PAIRS];
};
static struct component_case cases[MIXED_CASES];

static int status_ok(hipError_t status,const char *reason) {
    return status==hipSuccess || fail(reason,(int)status);
}
static void *offset(void *base,size_t bytes) {return (unsigned char *)base+bytes;}
static int copy_bytes(void *to,const void *from,size_t bytes,hipMemcpyKind kind) {
    if (!status_ok(p_hipMemcpy(to,from,bytes,kind),"component-copy")) return 0;
    copies_ok++;return 1;
}
static int kernel(hipFunction_t function,unsigned grid,void **args) {
    launch_attempts++;
    if (!status_ok(p_hipModuleLaunchKernel(function,grid,1,1,256,1,1,0,NULL,args,NULL),
                   "component-original-kernel-launch")) return 0;
    launches_ok++;return 1;
}
static int gather_rows(void *table,void *tokens,void *output,unsigned count) {
    void *args[3]={&table,&tokens,&output};return kernel(gather_function,count,args);
}
static int rms_rows(void *tensor,unsigned count) {
    int32_t width=2560,groups=1;void *gamma=device[D_GAMMA];
    void *args[5]={&tensor,&gamma,&tensor,&width,&groups};return kernel(rms_function,count,args);
}
static int fc_rows(void *weight,void *input,void *output,unsigned count) {
    if (count<1 || count>4) return fail("component-FC-count",0);
    int64_t k=2560,n=2560;void *args[5]={&weight,&input,&output,&k,&n};
    return kernel(fc_functions[count-1],160,args);
}
static int seed_rows(void *embedding,void *output,unsigned count) {
    void *hidden=device[D_HIDDEN];void *args[3]={&embedding,&hidden,&output};
    return kernel(seed_function,count,args);
}
static int sync_device(void) {
    if (!status_ok(p_hipDeviceSynchronize(),"component-setup-synchronize")) return 0;
    synchronizations_ok++;return 1;
}
static int event_record(unsigned index) {
    if (!status_ok(p_hipEventRecord(events[index],NULL),"component-event-record")) return 0;
    event_records++;return 1;
}
static int finite_words(const uint16_t *data,size_t words) {
    for (size_t i=0;i<words;i++)
        if ((data[i]&0x7f80)==0x7f80) return fail("nonfinite-or-unfilled-component-output",0);
    return 1;
}
static int frozen_rows(const uint16_t *data,size_t row_words,const char **pins) {
    for (unsigned i=0;i<2;i++) {
        char digest[65];
        if (!finite_words(data+i*row_words,row_words) ||
            !hash_memory(data+i*row_words,row_words*sizeof(uint16_t),digest)) return 0;
        if (strcmp(digest,pins[i])) return fail("component-frozen-oracle-mismatch",0);
    }
    return 1;
}
static int timed_path(unsigned mixed,unsigned count,unsigned label,struct path_timing *timing) {
    unsigned accepted=count-1;
    void *input=mixed?offset(device[D_INPUT],accepted*E_ROW_BYTES):device[D_INPUT];
    void *output=mixed?offset(device[D_SLAB],accepted*E_ROW_BYTES):device[D_STOCK_E];
    void *tokens=mixed?offset(device[label?D_IDS_B:D_IDS_A],accepted*sizeof(int32_t)):
        device[label?D_IDS_B:D_IDS_A];
    unsigned work=mixed?1:count;
    struct timespec started,finished;
    if (clock_gettime(CLOCK_MONOTONIC,&started)) return fail("component-clock-start",errno);
    if (!event_record(0) || !gather_rows(device[D_TABLE],tokens,input,work) ||
        !rms_rows(input,work) || !fc_rows(device[D_EW],input,output,work) || !event_record(1) ||
        !seed_rows(device[mixed?D_SLAB:D_STOCK_E],device[mixed?D_MIXED_SEED:D_STOCK_SEED],count) ||
        !event_record(2)) return 0;
    if (!status_ok(p_hipEventSynchronize(events[2]),"component-end-event-wait")) return 0;
    event_waits++;
    if (clock_gettime(CLOCK_MONOTONIC,&finished)) return fail("component-clock-end",errno);
    timing->host_ms=(double)(finished.tv_sec-started.tv_sec)*1000.0+
        (double)(finished.tv_nsec-started.tv_nsec)/1000000.0;
    if (!status_ok(p_hipEventElapsedTime(&timing->branch_ms,events[0],events[1]),"component-B-or-T-elapsed")) return 0;
    event_elapsed++;
    if (!status_ok(p_hipEventElapsedTime(&timing->seed_ms,events[1],events[2]),"component-seed-elapsed")) return 0;
    event_elapsed++;
    if (!status_ok(p_hipEventElapsedTime(&timing->total_ms,events[0],events[2]),"component-total-elapsed")) return 0;
    event_elapsed++;
    return (isfinite(timing->branch_ms) && timing->branch_ms>0 &&
        isfinite(timing->seed_ms) && timing->seed_ms>0 &&
        isfinite(timing->total_ms) && timing->total_ms>0 &&
        isfinite(timing->host_ms) && timing->host_ms>=0) || fail("component-invalid-timing",0);
}
static int validate_pair(struct component_case *c,unsigned iteration) {
    size_t e_bytes=c->k*E_ROW_BYTES,s_bytes=c->k*MAX_TENSOR_BYTES;
    for (unsigned path=0;path<2;path++) {
        if (!copy_bytes(c->e[path],device[path?D_SLAB:D_STOCK_E],e_bytes,hipMemcpyDeviceToHost)) return 0;
        c->copied_mask|=1u<<(2*path);
        if (!copy_bytes(c->seed[path],device[path?D_MIXED_SEED:D_STOCK_SEED],s_bytes,hipMemcpyDeviceToHost)) return 0;
        c->copied_mask|=1u<<(2*path+1);
        if (!finite_words(c->e[path],c->k*WIDTH) || !finite_words(c->seed[path],c->k*MAX_WORDS) ||
            !hash_memory(c->e[path],e_bytes,c->e_sha[path]) ||
            !hash_memory(c->seed[path],s_bytes,c->seed_sha[path])) return 0;
    }
    if (memcmp(c->e[0],c->e[1],e_bytes) || memcmp(c->seed[0],c->seed[1],s_bytes))
        return fail("component-exact-stock-mixed-parity-failed",0);
    for (unsigned row=0;row<c->k;row++)
        if (memcmp(c->e[0]+row*WIDTH,e_oracle[ids[c->label][row]],E_ROW_BYTES))
            return fail("component-batch-versus-frozen-M1-row-mismatch",0);
    if (!iteration) memcpy(c->seed_reference,c->seed[0],s_bytes);
    else if (memcmp(c->seed_reference,c->seed[0],s_bytes))
        return fail("component-seed-repeat-instability",0);
    parity_pairs++;return 1;
}

int main(int argc,char **argv) {
    if (argc!=20) {
        fputs("Expected ENGINE HSACO HIP_LIBRARY HIP_SHA E_WEIGHT E_SHA H_WEIGHT H_SHA A_RAW A_RAW_SHA B_RAW B_RAW_SHA GAMMA GAMMA_SHA A_H_NORM A_H_SHA B_H_NORM B_H_SHA NEW_OUTPUT_DIRECTORY\n",stderr);
        return 2;
    }
    int dirfd=-1,reportfd=-1,enginefd=-1,codefd=-1,runtimefd=-1,outfd[MIXED_CASES][4];
    for (unsigned i=0;i<MIXED_CASES;i++) for (unsigned j=0;j<4;j++) outfd[i][j]=-1;
    void *library=NULL,*code=NULL,*weights[2]={NULL,NULL};hipModule_t module=NULL;
    struct stat engine_identity,code_identity,runtime_identity,input_identity[7];
    char input_sha[7][65]={{0}},code_sha[65]={0},filenames[MIXED_CASES][4][64]={0};
    unsigned files_rechecked=0,file_close_errors=0;
    int runtime_version=0,driver_version=0,passed=0;
    const char *wave=getenv("HALOGEN_LQ8_WAVE");
    const char *wave_binding=wave?(strcmp(wave,"1")?"rejected":"1"):"unset-native-default1";
    if (argv[19][0]!='/' || mkdir(argv[19],0700)) {
        fprintf(stderr,"Exclusive output directory failed, errno=%d\n",errno);return 2;
    }
    dirfd=open(argv[19],O_DIRECTORY|O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (dirfd<0) {fail("component-output-directory-open",errno);goto cleanup;}
    reportfd=openat(dirfd,"mixed-replay.json",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (reportfd<0) {fail("component-report-exclusive-open",errno);goto cleanup;}
    for (unsigned i=0;i<MIXED_CASES;i++) {
        cases[i].k=2+i/2;cases[i].label=i%2;
        for (unsigned j=0;j<4;j++) {
            int n=snprintf(filenames[i][j],sizeof filenames[i][j],"%c-k%u-%s-%s.u16",
                cases[i].label?'B':'A',cases[i].k,j<2?"stock":"mixed",j%2?"seed":"embedding");
            if (n<0 || (size_t)n>=sizeof filenames[i][j]) {fail("component-output-name",0);goto cleanup;}
            outfd[i][j]=openat(dirfd,filenames[i][j],O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
            if (outfd[i][j]<0) {fail("component-output-exclusive-open",errno);goto cleanup;}
        }
    }
    if (!valid_sha(MIXED_COMPONENT_BUILD_SHA) || !valid_sha(argv[4]) || strcmp(argv[4],runtime_pin) ||
        (wave && strcmp(wave,"1"))) {fail("component-build-runtime-or-wave-pin",0);goto cleanup;}
    enginefd=open_regular(argv[1],ENGINE_BYTES,ENGINE_BYTES,&engine_identity);
    codefd=open_regular(argv[2],CODE_BYTES,CODE_BYTES,&code_identity);
    runtimefd=open_regular(argv[3],0,128<<20,&runtime_identity);
    if (enginefd<0 || codefd<0 || runtimefd<0) goto cleanup;
    if (!hash_file(enginefd,ENGINE_SHA) || !verify_identity(enginefd,&engine_identity) ||
        !hash_file(runtimefd,runtime_pin) || !verify_identity(runtimefd,&runtime_identity)) goto cleanup;
    code=malloc(CODE_BYTES);
    if (!code) {fail("component-host-code-allocation",errno);goto cleanup;}
    if (!read_exact(codefd,code,CODE_BYTES) || !verify_identity(codefd,&code_identity) ||
        !hash_memory(code,CODE_BYTES,code_sha)) goto cleanup;
    if (strcmp(code_sha,CODE_SHA)) {fail("component-codeobject-pin",0);goto cleanup;}
    unsigned char block[16384];size_t done=0;
    if (lseek(enginefd,CODE_OFFSET,SEEK_SET)!=CODE_OFFSET) {fail("component-engine-payload-seek",errno);goto cleanup;}
    while (done<CODE_BYTES) {
        size_t bytes=CODE_BYTES-done;if (bytes>sizeof block) bytes=sizeof block;
        if (!read_exact(enginefd,block,bytes)) goto cleanup;
        if (memcmp(block,(unsigned char *)code+done,bytes)) {fail("component-engine-shader-byte-mismatch",0);goto cleanup;}
        done+=bytes;
    }
    if (!verify_identity(enginefd,&engine_identity)) goto cleanup;
    for (unsigned i=0;i<2;i++) {
        weights[i]=malloc(WEIGHT_BYTES);
        if (!weights[i]) {fail("component-host-weight-allocation",errno);goto cleanup;}
    }
    void *input_targets[7]={weights[0],weights[1],raw_rows[0],raw_rows[1],gamma_row,h_norm_rows[0],h_norm_rows[1]};
    size_t input_bytes[7]={WEIGHT_BYTES,WEIGHT_BYTES,E_ROW_BYTES,E_ROW_BYTES,E_ROW_BYTES,MAX_TENSOR_BYTES,MAX_TENSOR_BYTES};
    for (unsigned i=0;i<7;i++) {
        if (strcmp(argv[6+2*i],input_pins[i])) {fail("component-frozen-input-argument-pin",0);goto cleanup;}
        if (!load_bytes(argv[5+2*i],input_pins[i],input_targets[i],input_bytes[i],input_sha[i],&input_identity[i])) goto cleanup;
        if (i>=2 && !finite_words(input_targets[i],input_bytes[i]/sizeof(uint16_t))) goto cleanup;
    }
    if (!verify_again(argv[3],runtime_pin,(size_t)runtime_identity.st_size,&runtime_identity)) goto cleanup;
    library=dlopen(argv[3],RTLD_NOW|RTLD_LOCAL);
    if (!library) {fail("component-HIP-dlopen",0);fputs(dlerror(),stderr);fputc('\n',stderr);goto cleanup;}
    RESOLVE(hipGetDeviceCount);RESOLVE(hipGetDevicePropertiesR0600);RESOLVE(hipSetDevice);
    RESOLVE(hipRuntimeGetVersion);RESOLVE(hipDriverGetVersion);RESOLVE(hipModuleLoadData);
    RESOLVE(hipModuleGetFunction);RESOLVE(hipModuleLaunchKernel);RESOLVE(hipModuleUnload);
    RESOLVE(hipMalloc);RESOLVE(hipFree);RESOLVE(hipMemcpy);RESOLVE(hipDeviceSynchronize);
    RESOLVE(hipEventCreateWithFlags);RESOLVE(hipEventRecord);RESOLVE(hipEventSynchronize);
    RESOLVE(hipEventElapsedTime);RESOLVE(hipEventDestroy);
    int count=0;hipDeviceProp_t properties;memset(&properties,0,sizeof properties);
    HIP_OK(p_hipGetDeviceCount(&count),"component-device-count");
    if (count!=1) {fail("component-exactly-one-GPU-required",count);goto cleanup;}
    HIP_OK(p_hipGetDevicePropertiesR0600(&properties,0),"component-device-properties");
    if (strcmp(properties.gcnArchName,"gfx1151") || properties.warpSize!=32) {
        fail("component-exactly-one-gfx1151-wave32-required",0);goto cleanup;
    }
    HIP_OK(p_hipSetDevice(0),"component-set-device");
    HIP_OK(p_hipRuntimeGetVersion(&runtime_version),"component-runtime-version");
    HIP_OK(p_hipDriverGetVersion(&driver_version),"component-driver-version");
    HIP_OK(p_hipModuleLoadData(&module,code),"component-module-load");module_loads++;
    HIP_OK(p_hipModuleGetFunction(&gather_function,module,GATHER_SYMBOL),"component-gather-symbol");
    HIP_OK(p_hipModuleGetFunction(&rms_function,module,RMS_SYMBOL),"component-RMS-symbol");
    HIP_OK(p_hipModuleGetFunction(&seed_function,module,SEED_SYMBOL),"component-seed-symbol");
    for (unsigned i=0;i<4;i++)
        HIP_OK(p_hipModuleGetFunction(&fc_functions[i],module,fc_symbols[i]),"component-FC-symbol");
    for (unsigned i=0;i<D_BUFFERS;i++) {
        HIP_OK(p_hipMalloc(&device[i],buffer_bytes[i]),"component-device-allocation");allocations_ok++;
        if ((uintptr_t)device[i]&15) {fail("component-device-alignment16",0);goto cleanup;}
    }
    for (unsigned i=0;i<3;i++) {
        HIP_OK(p_hipEventCreateWithFlags(&events[i],0),"component-event-create");event_creates++;
    }
    for (size_t i=0;i<4*MAX_WORDS;i++) poison[i]=0x7fc0;
    for (unsigned label=0;label<2;label++)
        for (unsigned row=0;row<4;row++) for (unsigned stream=0;stream<4;stream++)
            hidden_ids[label][4*row+stream]=4*ids[label][row]+(int32_t)stream;
    if (!copy_bytes(device[D_TABLE],raw_rows,sizeof raw_rows,hipMemcpyHostToDevice) ||
        !copy_bytes(device[D_GAMMA],gamma_row,sizeof gamma_row,hipMemcpyHostToDevice) ||
        !copy_bytes(device[D_EW],weights[0],WEIGHT_BYTES,hipMemcpyHostToDevice) ||
        !copy_bytes(device[D_HW],weights[1],WEIGHT_BYTES,hipMemcpyHostToDevice) ||
        !copy_bytes(device[D_HNORM],h_norm_rows,sizeof h_norm_rows,hipMemcpyHostToDevice)) goto cleanup;
    for (unsigned label=0;label<2;label++)
        if (!copy_bytes(device[label?D_IDS_B:D_IDS_A],ids[label],sizeof ids[label],hipMemcpyHostToDevice) ||
            !copy_bytes(device[label?D_HIDS_B:D_HIDS_A],hidden_ids[label],sizeof hidden_ids[label],hipMemcpyHostToDevice)) goto cleanup;
    /* Canonical GPU arithmetic and prefix preparation are outside all brackets. */
    if (!gather_rows(device[D_TABLE],device[D_IDS_A],device[D_INPUT],2) ||
        !rms_rows(device[D_INPUT],2) || !sync_device() ||
        !copy_bytes(normalized,device[D_INPUT],sizeof normalized,hipMemcpyDeviceToHost) ||
        !frozen_rows(&normalized[0][0],WIDTH,norm_pins)) goto cleanup;
    for (unsigned label=0;label<2;label++)
        if (!fc_rows(device[D_EW],offset(device[D_INPUT],label*E_ROW_BYTES),
                     offset(device[D_EATLAS],label*E_ROW_BYTES),1) ||
            !fc_rows(device[D_HW],offset(device[D_HNORM],label*MAX_TENSOR_BYTES),
                     offset(device[D_HATLAS],label*MAX_TENSOR_BYTES),4)) goto cleanup;
    if (!sync_device() ||
        !copy_bytes(e_oracle,device[D_EATLAS],sizeof e_oracle,hipMemcpyDeviceToHost) ||
        !copy_bytes(h_oracle,device[D_HATLAS],sizeof h_oracle,hipMemcpyDeviceToHost) ||
        !frozen_rows(&e_oracle[0][0],WIDTH,e_pins) ||
        !frozen_rows(&h_oracle[0][0],MAX_WORDS,h_pins)) goto cleanup;
    for (unsigned index=0;index<MIXED_CASES;index++) {
        struct component_case *c=&cases[index];unsigned accepted=c->k-1;
        void *tokens=device[c->label?D_IDS_B:D_IDS_A];
        if (!gather_rows(device[D_EATLAS],tokens,device[D_SLAB],accepted) ||
            !gather_rows(device[D_HATLAS],device[c->label?D_HIDS_B:D_HIDS_A],device[D_HIDDEN],4*c->k) ||
            !sync_device()) goto cleanup;
        for (unsigned iteration=0;iteration<MIXED_PAIRS;iteration++) {
            struct pair_timing *t=&c->timing[iteration];t->measured=iteration>=MIXED_WARMUPS;
            t->stock_first=(iteration%2)==0;c->copied_mask=0;
            /* Preserve ready prefix. Poison only the correction slot of slab. */
            if (!copy_bytes(device[D_STOCK_E],poison,c->k*E_ROW_BYTES,hipMemcpyHostToDevice) ||
                !copy_bytes(offset(device[D_SLAB],accepted*E_ROW_BYTES),poison,E_ROW_BYTES,hipMemcpyHostToDevice) ||
                !copy_bytes(device[D_STOCK_SEED],poison,c->k*MAX_TENSOR_BYTES,hipMemcpyHostToDevice) ||
                !copy_bytes(device[D_MIXED_SEED],poison,c->k*MAX_TENSOR_BYTES,hipMemcpyHostToDevice)) goto cleanup;
            for (unsigned order=0;order<2;order++) {
                unsigned path=t->stock_first?order:1-order;
                if (!timed_path(path,c->k,c->label,&t->path[path])) goto cleanup;
            }
            if (!validate_pair(c,iteration)) goto cleanup;
            t->completed=1;c->completed++;component_pairs++;
        }
    }
    if (!verify_again(argv[1],ENGINE_SHA,ENGINE_BYTES,&engine_identity) ||
        !verify_again(argv[2],CODE_SHA,CODE_BYTES,&code_identity) ||
        !verify_again(argv[3],runtime_pin,(size_t)runtime_identity.st_size,&runtime_identity)) goto cleanup;
    for (unsigned i=0;i<7;i++)
        if (!verify_again(argv[5+2*i],input_pins[i],input_bytes[i],&input_identity[i])) goto cleanup;
    files_rechecked=1;
cleanup:
    /* Drain all attempted setup/timing work before releasing its allocations. */
    if (launch_attempts) {
        drain_attempts++;
        if (!p_hipDeviceSynchronize || p_hipDeviceSynchronize()!=hipSuccess) cleanup_errors++;
        else drain_ok++;
    }
    for (unsigned i=0;i<3;i++) if (events[i]) {
        if (!p_hipEventDestroy || p_hipEventDestroy(events[i])!=hipSuccess) cleanup_errors++;
        else event_destroys++;
    }
    for (unsigned i=0;i<D_BUFFERS;i++) if (device[i]) {
        if (!p_hipFree || p_hipFree(device[i])!=hipSuccess) cleanup_errors++;
        else free_ok++;
    }
    if (module) {if (!p_hipModuleUnload || p_hipModuleUnload(module)!=hipSuccess) cleanup_errors++;else module_unloads++;}
    if (library && dlclose(library)) cleanup_errors++;
    if (enginefd>=0 && close(enginefd)) file_close_errors++;
    if (codefd>=0 && close(codefd)) file_close_errors++;
    if (runtimefd>=0 && close(runtimefd)) file_close_errors++;
    free(code);free(weights[0]);free(weights[1]);
    for (unsigned i=0;i<MIXED_CASES;i++) for (unsigned j=0;j<4;j++) {
        struct component_case *c=&cases[i];
        if (outfd[i][j]>=0 && (c->copied_mask&(1u<<j))) {
            const void *data=j%2?(void *)c->seed[j/2]:(void *)c->e[j/2];
            size_t bytes=c->k*(j%2?MAX_TENSOR_BYTES:E_ROW_BYTES);
            if (write_exact(outfd[i][j],data,bytes)) outputs_written++;
        }
        if (outfd[i][j]>=0 && close(outfd[i][j])) file_close_errors++;
    }
    if (dirfd>=0 && fsync(dirfd)) fail("component-output-directory-fsync",errno);
    if (cleanup_errors) fail("component-HIP-cleanup",(int)cleanup_errors);
    if (file_close_errors) fail("component-file-close",(int)file_close_errors);
    passed=!error_reason && files_rechecked && component_pairs==MIXED_CASES*MIXED_PAIRS &&
        parity_pairs==component_pairs && launches_ok==978 && launch_attempts==978 &&
        copies_ok==972 && synchronizations_ok==8 && allocations_ok==D_BUFFERS && free_ok==D_BUFFERS &&
        module_loads==1 && module_unloads==1 && event_creates==3 && event_destroys==3 &&
        event_records==720 && event_waits==240 && event_elapsed==720 &&
        drain_attempts==1 && drain_ok==1 && outputs_written==24;
    if (!passed && !error_reason) fail("component-final-counter-contract",0);
    if (reportfd>=0) {
        FILE *report=fdopen(reportfd,"w");
        if (!report) {fail("component-report-fdopen",errno);close(reportfd);}
        else {
            fprintf(report,"{\"schema\":\"halogen0162.pld-mixed-embedding-component.v1\",\"passed\":%s,"
                "\"scope\":\"bounded synthetic A/B row assembly; original GPU prefix and correction; no live table/NPU/full-head/acceptance/token-rate claim\","
                "\"source_compile_time_sha256\":\"%s\",\"included_fc_source_sha256\":\"%s\","
                "\"engine_sha256\":\"%s\",\"codeobject_sha256\":\"%s\",\"runtime_sha256\":\"%s\","
                "\"runtime_version\":%d,\"driver_version\":%d,\"halogen_lq8_wave\":\"%s\","
                "\"fixed_original_kernels_used\":true,\"native_dispatcher_executed\":false,"
                "\"prefix_prepared_by_original_M1\":true,\"hidden_prepared_by_original_M4\":true,"
                "\"full_hidden_seed_count_preserved\":true,\"synthetic_table_ids\":[0,1],"
                "\"warmup_pairs_per_case\":%u,\"measured_pairs_per_case\":%u,"
                "\"timing_scope\":\"stream0 event B(k) or T(1), full-k seed, and total; setup/prefix/hidden/copies/validation excluded; host enqueue gaps/events included\","
                "\"npu_executed\":false,\"transport_qualified\":false,\"full_head_qualified\":false,"
                "\"live_skip_admitted\":false,\"acceptance_claim\":false,\"end_to_end_throughput_qualified\":false,"
                "\"launch_attempts\":%u,\"launches_ok\":%u,\"copies_ok\":%u,\"setup_synchronizations_ok\":%u,"
                "\"allocations_ok\":%u,\"frees_ok\":%u,\"module_loads\":%u,\"module_unloads\":%u,"
                "\"event_creates\":%u,\"event_records\":%u,\"event_waits\":%u,\"event_elapsed\":%u,\"event_destroys\":%u,"
                "\"cleanup_drain_attempts\":%u,\"cleanup_drain_ok\":%u,\"cleanup_errors\":%u,\"file_close_errors\":%u,"
                "\"immutable_files_rechecked\":%s,\"completed_pairs\":%u,\"exact_parity_pairs\":%u,"
                "\"output_files_written\":%u,\"error\":\"%s\",\"error_code\":%d,\"inputs\":[",
                passed?"true":"false",MIXED_COMPONENT_BUILD_SHA,ORACLE_SOURCE_SHA,ENGINE_SHA,CODE_SHA,runtime_pin,
                runtime_version,driver_version,wave_binding,MIXED_WARMUPS,MIXED_REPS,
                launch_attempts,launches_ok,copies_ok,synchronizations_ok,allocations_ok,free_ok,module_loads,module_unloads,
                event_creates,event_records,event_waits,event_elapsed,event_destroys,drain_attempts,drain_ok,
                cleanup_errors,file_close_errors,files_rechecked?"true":"false",component_pairs,parity_pairs,
                outputs_written,error_reason?error_reason:"",error_code);
            for (unsigned i=0;i<7;i++)
                fprintf(report,"%s{\"name\":\"%s\",\"sha256\":\"%s\"}",i?",":"",input_names[i],input_sha[i]);
            fputs("],\"cases\":[",report);
            for (unsigned i=0;i<MIXED_CASES;i++) {
                struct component_case *c=&cases[i];double branch_delta=0,total_delta=0,stock=0,tail=0;
                unsigned measured=0;
                for (unsigned j=0;j<MIXED_PAIRS;j++) if (c->timing[j].completed && c->timing[j].measured) {
                    struct pair_timing *t=&c->timing[j];measured++;
                    stock+=t->path[0].branch_ms;tail+=t->path[1].branch_ms;
                    branch_delta+=(double)t->path[0].branch_ms-t->path[1].branch_ms;
                    total_delta+=(double)t->path[0].total_ms-t->path[1].total_ms;
                }
                fprintf(report,"%s{\"label\":\"%c\",\"k\":%u,\"accepted_prefix\":%u,\"native_correction_rows\":1,"
                    "\"native_tail_token_offset_bytes\":%u,\"native_tail_E_offset_bytes\":%zu,\"seed_count\":%u,"
                    "\"completed_pairs\":%u,\"measured_pairs\":%u,\"B_mean_ms\":%.12g,\"T_mean_ms\":%.12g,"
                    "\"B_minus_T_mean_ms\":%.12g,\"full_seed_total_delta_mean_ms\":%.12g,\"outputs\":[",
                    i?",":"",c->label?'B':'A',c->k,c->k?c->k-1:0,4*(c->k?c->k-1:0),
                    (c->k?c->k-1:0)*E_ROW_BYTES,c->k,c->completed,measured,
                    measured?stock/measured:0,measured?tail/measured:0,
                    measured?branch_delta/measured:0,measured?total_delta/measured:0);
                for (unsigned j=0;j<4;j++)
                    fprintf(report,"%s{\"file\":\"%s\",\"copied\":%s,\"sha256\":\"%s\"}",j?",":"",filenames[i][j],
                        c->copied_mask&(1u<<j)?"true":"false",j%2?c->seed_sha[j/2]:c->e_sha[j/2]);
                fputs("],\"timings\":[",report);unsigned emitted=0;
                for (unsigned j=0;j<MIXED_PAIRS;j++) if (c->timing[j].completed) {
                    struct pair_timing *t=&c->timing[j];
                    fprintf(report,"%s{\"iteration\":%u,\"measured\":%s,\"stock_first\":%s,"
                        "\"B_ms\":%.9g,\"T_ms\":%.9g,\"B_minus_T_ms\":%.12g,"
                        "\"stock_seed_ms\":%.9g,\"mixed_seed_ms\":%.9g,"
                        "\"stock_total_ms\":%.9g,\"mixed_total_ms\":%.9g,"
                        "\"stock_host_ms\":%.12g,\"mixed_host_ms\":%.12g,\"exact_parity\":true}",
                        emitted++?",":"",j,t->measured?"true":"false",t->stock_first?"true":"false",
                        (double)t->path[0].branch_ms,(double)t->path[1].branch_ms,
                        (double)t->path[0].branch_ms-t->path[1].branch_ms,
                        (double)t->path[0].seed_ms,(double)t->path[1].seed_ms,
                        (double)t->path[0].total_ms,(double)t->path[1].total_ms,t->path[0].host_ms,t->path[1].host_ms);
                }
                fputs("]}",report);
            }
            fputs("]}\n",report);
            int report_bad=ferror(report);
            if (fflush(report)) report_bad=1;
            if (fsync(fileno(report))) report_bad=1;
            if (fclose(report)) report_bad=1;
            if (report_bad) {fail("component-report-persist",errno);passed=0;}
        }
    }
    if (dirfd>=0 && close(dirfd)) {fail("component-directory-close",errno);passed=0;}
    if (error_reason) {fprintf(stderr,"Mixed component failed: %s code=%d\n",error_reason,error_code);passed=0;}
    return passed?0:1;
}
