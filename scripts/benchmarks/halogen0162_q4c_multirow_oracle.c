/* Bounded original-kernel arithmetic oracle for 1..64 explicitly sealed tokens.
 * Root alone builds/runs in the pinned image under the existing owned GPU,
 * reserve and deadline guards. This source performs no model/server operation.
 *
 * Rebased selected-rows.q4c is [codebook64][N*codes1280][N*scales160].
 * Original vector v8u<2,false>: blocks_per_row320,total_blocks320*N,
 * grid=ceil(total_blocks/512),block256,optional DeqCb zero. Original scalar:
 * rows=N,width2560,grid=N,block256. HIP supplies all hidden arguments.
 * Both outputs must exactly match every supplied CPU raw BF16 word.
 * Then the ORIGINAL count1 grouped RMS runs once per native vector row,
 * width2560/groups1,grid1/block256,raw gamma unchanged,input/output aliased.
 * Every normalized word must exactly match the separately sealed candidate.
 * There is no replacement arithmetic, tolerance fitting, gather or full table.
 *
 * Binary manifest, little endian, no C structure serialization:
 * header200: magic8 HGMROW1\0,N:u32,width:u32,generation16,sequence:u64,
 * complete/producer-plan/producer-source/pack/tokens SHA256 bytes32 each.
 * N records132: token:u32,raw/norm/codes/scales SHA256 bytes32 each.
 * Root must separately seal preparer/harness/scaffold/manifest/binary bindings.
 * Build: gcc -O2 -Wall -Wextra -Werror -D__HIP_PLATFORM_AMD__
 * -I<reviewed HIP include> -DQ4C_MULTIROW_BUILD_SCAFFOLD_SHA=\"<pin>\"
 * halogen0162_q4c_multirow_oracle.c -ldl -lcrypto -o <fresh binary>.
 * Usage: ENGINE HSACO HIP_LIBRARY HIP_SHA CANDIDATES_DIR MANIFEST MANIFEST_SHA NEW_DIR
 */
#define main frozen_embedding_rms_oracle_entry_unused
#include "halogen0162_embedding_rms_replay.c"
#undef main

#ifndef Q4C_MULTIROW_BUILD_SCAFFOLD_SHA
#error Independently pinned frozen embedding RMS scaffold SHA required
#endif
#define MULTI_SCAFFOLD_SHA "7ea99028014f590a0938d5a06790f51ce571948706d851c16bfcb72f694f4fa8"
#define MULTI_MAX_ROWS ((size_t)64)
#define MULTI_HEADER_BYTES ((size_t)200)
#define MULTI_RECORD_BYTES ((size_t)132)
#define MULTI_MAX_MANIFEST (MULTI_HEADER_BYTES+MULTI_MAX_ROWS*MULTI_RECORD_BYTES)
#define MULTI_MAX_PACK ((size_t)64+MULTI_MAX_ROWS*1440)
#define MULTI_VECTOR_KERNEL "_ZN7halogen12_GLOBAL__N_114k_deq_q4cp_v8uILi2ELb0EEEvPKhPtjjllllNS0_5DeqCbE"
#define MULTI_SCALAR_KERNEL "_ZN7halogen12_GLOBAL__N_110k_deq_q4cpEPKhPtlllll"
#define MULTI_CODEBOOK_SHA "1f2755c994ae6ea3d4a24a5cc2b8066de0971b07eacd76a05c5e111cba8d3679"
#define MULTI_GAMMA_SHA "04c4a570850e06f2d8913da8220d54d4c7f87db6eb6d45480b938e8ba41d6a86"

struct multi_row {
    uint32_t token;
    uint16_t raw_reference[WORDS],norm_reference[WORDS],normalized[WORDS];
    char raw_reference_sha[65],norm_reference_sha[65],codes_sha[65],scales_sha[65];
    char converted_sha[2][65],normalized_sha[65];
    struct stat raw_identity,norm_identity;
    unsigned raw_mismatches[2],raw_nonfinite[2],norm_mismatches,norm_nonfinite,rms_copied;
    size_t first_raw[2],first_norm;
};
static struct multi_row multi_rows[MULTI_MAX_ROWS];
static uint16_t multi_converted[2][MULTI_MAX_ROWS*WORDS],multi_poison[MULTI_MAX_ROWS*WORDS];
static const char *multi_outputs[3]={"vector-raw.u16","scalar-raw.u16","vector-native-norm.u16"};

static uint32_t multi_u32(const unsigned char *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static uint64_t multi_u64(const unsigned char *p) {
    return (uint64_t)multi_u32(p)|((uint64_t)multi_u32(p+4)<<32);
}
static void multi_hex(const unsigned char *p,size_t bytes,char *out) {
    for (size_t i=0;i<bytes;i++) sprintf(out+2*i,"%02x",p[i]);
    out[2*bytes]=0;
}
static unsigned multi_compare(const uint16_t *actual,const uint16_t *expected,size_t *first) {
    unsigned mismatches=0;*first=WORDS;
    for (size_t i=0;i<WORDS;i++) if (actual[i]!=expected[i]) {
        if (!mismatches) *first=i;
        mismatches++;
    }
    return mismatches;
}
static int multi_path(char *out,size_t capacity,const char *directory,const char *name) {
    int n=snprintf(out,capacity,"%s/%s",directory,name);
    return (n>0 && (size_t)n<capacity) || fail("candidate-path-extent",0);
}
static int multi_row_path(char *out,size_t capacity,const char *directory,size_t row,uint32_t token,const char *kind) {
    char name[80];
    int n=snprintf(name,sizeof name,"%03zu-token%" PRIu32 "-%s.u16",row,token,kind);
    return (n>0 && (size_t)n<sizeof name && multi_path(out,capacity,directory,name)) || fail("row-path-extent",0);
}

int main(int argc,char **argv) {
    if (argc!=9) {
        fputs("Expected ENGINE HSACO HIP_LIBRARY HIP_SHA CANDIDATES_DIR MANIFEST MANIFEST_SHA NEW_DIR\n",stderr);return 2;
    }
    if (strcmp(Q4C_MULTIROW_BUILD_SCAFFOLD_SHA,MULTI_SCAFFOLD_SHA) ||
        argv[5][0]!='/' || !valid_sha(argv[4]) || !valid_sha(argv[7])) {
        fputs("Frozen scaffold pin, absolute candidates directory or independent SHA differs\n",stderr);return 2;
    }
    int dirfd=-1,reportfd=-1,outfd[3]={-1,-1,-1},enginefd=-1,codefd=-1,runtimefd=-1,manifestfd=-1;
    void *library=NULL,*code=NULL,*device_pack=NULL,*device_rows=NULL,*device_gamma=NULL;
    hipModule_t module=NULL;hipFunction_t converters[2]={NULL,NULL},rms=NULL;
    unsigned char manifest[MULTI_MAX_MANIFEST],packed[MULTI_MAX_PACK],token_bytes[MULTI_MAX_ROWS*4];
    uint16_t gamma[WORDS];char manifest_sha[65]="",pack_sha[65]="",tokens_sha[65]="",gamma_sha[65]="";
    char complete_sha[65]="",plan_sha[65]="",producer_sha[65]="",generation_hex[33]="",path[4096];
    struct stat engine_identity,code_identity,runtime_identity,manifest_identity,pack_identity,tokens_identity,gamma_identity;
    size_t rows=0,manifest_bytes=0,pack_bytes=0,tensor_bytes=0,rms_copied_rows=0;
    uint64_t sequence=0;unsigned converted_copied[2]={0,0},windows_verified=0,files_rechecked=0;
    unsigned output_files_written=0,file_close_errors=0;char converted_all_sha[2][65]={{0},{0}},norm_all_sha[65]="";
    int runtime_version=0,driver_version=0,passed=0;
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

    if (argv[8][0]!='/' || mkdir(argv[8],0700)) {
        fprintf(stderr,"Exclusive new output directory failed, errno=%d\n",errno);return 2;
    }
    dirfd=open(argv[8],O_DIRECTORY|O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (dirfd<0) {fail("output-directory-open",errno);goto cleanup;}
    reportfd=openat(dirfd,"replay.json",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    for (unsigned i=0;i<3;i++) outfd[i]=openat(dirfd,multi_outputs[i],O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (reportfd<0 || outfd[0]<0 || outfd[1]<0 || outfd[2]<0) {fail("output-exclusive-create",errno);goto cleanup;}
    manifestfd=open_regular(argv[6],0,MULTI_MAX_MANIFEST,&manifest_identity);
    if (manifestfd<0) goto cleanup;
    manifest_bytes=(size_t)manifest_identity.st_size;
    if (manifest_bytes<MULTI_HEADER_BYTES) {fail("manifest-header-extent",0);goto cleanup;}
    if (!read_exact(manifestfd,manifest,manifest_bytes) ||
        !verify_identity(manifestfd,&manifest_identity) || !hash_memory(manifest,manifest_bytes,manifest_sha)) goto cleanup;
    if (strcmp(manifest_sha,argv[7]) || memcmp(manifest,"HGMROW1\0",8)) {fail("sealed-manifest-header",0);goto cleanup;}
    rows=multi_u32(manifest+8);
    if (rows<1 || rows>MULTI_MAX_ROWS || multi_u32(manifest+12)!=WORDS ||
        manifest_bytes!=MULTI_HEADER_BYTES+rows*MULTI_RECORD_BYTES) {fail("bounded-manifest-shape",0);rows=0;goto cleanup;}
    unsigned generation_nonzero=0;for (unsigned i=16;i<32;i++) generation_nonzero|=manifest[i];
    sequence=multi_u64(manifest+32);
    if (!generation_nonzero || sequence>INT64_MAX) {fail("manifest-request-identity",0);goto cleanup;}
    multi_hex(manifest+16,16,generation_hex);multi_hex(manifest+40,32,complete_sha);
    multi_hex(manifest+72,32,plan_sha);multi_hex(manifest+104,32,producer_sha);
    multi_hex(manifest+136,32,pack_sha);multi_hex(manifest+168,32,tokens_sha);
    pack_bytes=64+rows*1440;tensor_bytes=rows*TENSOR_BYTES;
    for (size_t i=0;i<rows;i++) {
        struct multi_row *row=&multi_rows[i];const unsigned char *record=manifest+MULTI_HEADER_BYTES+i*MULTI_RECORD_BYTES;
        row->token=multi_u32(record);row->first_raw[0]=row->first_raw[1]=row->first_norm=WORDS;
        if (row->token>=248320) {fail("original-token-range",0);goto cleanup;}
        for (size_t j=0;j<i;j++) if (multi_rows[j].token==row->token) {fail("duplicate-original-token",0);goto cleanup;}
        multi_hex(record+4,32,row->raw_reference_sha);multi_hex(record+36,32,row->norm_reference_sha);
        multi_hex(record+68,32,row->codes_sha);multi_hex(record+100,32,row->scales_sha);
    }
    char observed[65];
    if (!multi_path(path,sizeof path,argv[5],"selected-rows.q4c") ||
        !load_bytes(path,pack_sha,packed,pack_bytes,observed,&pack_identity) ||
        !multi_path(path,sizeof path,argv[5],"tokens.i32") ||
        !load_bytes(path,tokens_sha,token_bytes,rows*4,observed,&tokens_identity) ||
        !multi_path(path,sizeof path,argv[5],"raw-gamma.u16") ||
        !load_bytes(path,MULTI_GAMMA_SHA,gamma,TENSOR_BYTES,gamma_sha,&gamma_identity)) goto cleanup;
    if (!hash_memory(packed,64,observed) || strcmp(observed,MULTI_CODEBOOK_SHA)) {fail("original-codebook-sha",0);goto cleanup;}
    for (size_t i=0;i<WORDS;i++) if ((gamma[i]&0x7f80)==0x7f80) {fail("nonfinite-raw-gamma",0);goto cleanup;}
    for (size_t i=0;i<rows;i++) {
        struct multi_row *row=&multi_rows[i];char actual[65];
        if (multi_u32(token_bytes+4*i)!=row->token) {fail("sealed-token-order",0);goto cleanup;}
        if (!hash_memory(packed+64+1280*i,1280,observed) || strcmp(observed,row->codes_sha) ||
            !hash_memory(packed+64+1280*rows+160*i,160,observed) || strcmp(observed,row->scales_sha)) {
            fail("selected-original-window-sha",0);goto cleanup;
        }
        if (!multi_row_path(path,sizeof path,argv[5],i,row->token,"raw") ||
            !load_bytes(path,row->raw_reference_sha,row->raw_reference,TENSOR_BYTES,actual,&row->raw_identity) ||
            !multi_row_path(path,sizeof path,argv[5],i,row->token,"norm") ||
            !load_bytes(path,row->norm_reference_sha,row->norm_reference,TENSOR_BYTES,actual,&row->norm_identity)) goto cleanup;
        for (size_t j=0;j<WORDS;j++) {
            if ((row->raw_reference[j]&0x7f80)==0x7f80 || (row->norm_reference[j]&0x7f80)==0x7f80) {
                fail("nonfinite-candidate-reference",0);goto cleanup;
            }
            multi_poison[i*WORDS+j]=0x7fc0;
        }
    }
    windows_verified=1;
    enginefd=open_regular(argv[1],ENGINE_BYTES,ENGINE_BYTES,&engine_identity);
    codefd=open_regular(argv[2],CODE_BYTES,CODE_BYTES,&code_identity);
    runtimefd=open_regular(argv[3],0,128<<20,&runtime_identity);
    if (enginefd<0 || codefd<0 || runtimefd<0) goto cleanup;
    if (!hash_file(enginefd,ENGINE_SHA) || !verify_identity(enginefd,&engine_identity) ||
        !hash_file(runtimefd,argv[4]) || !verify_identity(runtimefd,&runtime_identity)) goto cleanup;
    code=malloc(CODE_BYTES);if (!code) {fail("host-code-allocation",errno);goto cleanup;}
    char code_sha[65];
    if (!read_exact(codefd,code,CODE_BYTES) || !verify_identity(codefd,&code_identity) || !hash_memory(code,CODE_BYTES,code_sha)) goto cleanup;
    if (strcmp(code_sha,CODE_SHA)) {fail("codeobject-sha256-mismatch",0);goto cleanup;}
    unsigned char block[16384];size_t done=0;
    if (lseek(enginefd,CODE_OFFSET,SEEK_SET)!=CODE_OFFSET) {fail("engine-payload-seek",errno);goto cleanup;}
    while (done<CODE_BYTES) {
        size_t n=CODE_BYTES-done;if (n>sizeof block) n=sizeof block;
        if (!read_exact(enginefd,block,n)) goto cleanup;
        if (memcmp(block,(const unsigned char *)code+done,n)) {fail("engine-codeobject-byte-mismatch",0);goto cleanup;}
        done+=n;
    }
    if (!verify_identity(enginefd,&engine_identity) ||
        !verify_again(argv[3],argv[4],(size_t)runtime_identity.st_size,&runtime_identity)) goto cleanup;
    library=dlopen(argv[3],RTLD_NOW|RTLD_LOCAL);
    if (!library) {fail("hip-dlopen",0);fputs(dlerror(),stderr);fputc('\n',stderr);goto cleanup;}
    RESOLVE(hipGetDeviceCount);RESOLVE(hipGetDevicePropertiesR0600);RESOLVE(hipSetDevice);
    RESOLVE(hipRuntimeGetVersion);RESOLVE(hipDriverGetVersion);RESOLVE(hipModuleLoadData);
    RESOLVE(hipModuleGetFunction);RESOLVE(hipModuleLaunchKernel);RESOLVE(hipModuleUnload);
    RESOLVE(hipMalloc);RESOLVE(hipFree);RESOLVE(hipMemcpy);RESOLVE(hipDeviceSynchronize);
    int count=0;hipDeviceProp_t properties;memset(&properties,0,sizeof properties);
    HIP_OK(p_hipGetDeviceCount(&count),"hip-device-count");
    if (count!=1) {fail("exactly-one-gpu-required",count);goto cleanup;}
    HIP_OK(p_hipGetDevicePropertiesR0600(&properties,0),"hip-device-properties");
    if (strcmp(properties.gcnArchName,"gfx1151") || properties.warpSize!=32) {fail("gpu-gfx1151-wave32-required",0);goto cleanup;}
    HIP_OK(p_hipSetDevice(0),"hip-set-device");
    HIP_OK(p_hipRuntimeGetVersion(&runtime_version),"hip-runtime-version");
    HIP_OK(p_hipDriverGetVersion(&driver_version),"hip-driver-version");
    HIP_OK(p_hipModuleLoadData(&module,code),"hip-module-load");module_loads++;
    HIP_OK(p_hipModuleGetFunction(&converters[0],module,MULTI_VECTOR_KERNEL),"hip-vector-symbol");
    HIP_OK(p_hipModuleGetFunction(&converters[1],module,MULTI_SCALAR_KERNEL),"hip-scalar-symbol");
    HIP_OK(p_hipModuleGetFunction(&rms,module,KERNEL),"hip-original-rms-symbol");
    HIP_OK(p_hipMalloc(&device_pack,pack_bytes),"hip-packed-allocation");allocations_ok++;
    HIP_OK(p_hipMalloc(&device_rows,tensor_bytes),"hip-converted-allocation");allocations_ok++;
    HIP_OK(p_hipMalloc(&device_gamma,TENSOR_BYTES),"hip-raw-gamma-allocation");allocations_ok++;
    if ((uintptr_t)device_pack%16 || (uintptr_t)device_rows%16 || (uintptr_t)device_gamma%16) {fail("native-vector-alignment",0);goto cleanup;}
    HIP_OK(p_hipMemcpy(device_pack,packed,pack_bytes,hipMemcpyHostToDevice),"hip-packed-copy");copies_ok++;
    HIP_OK(p_hipMemcpy(device_gamma,gamma,TENSOR_BYTES,hipMemcpyHostToDevice),"hip-raw-gamma-copy");copies_ok++;
    /* Scalar first, vector last: original RMS consumes native vector output directly. */
    for (unsigned pass=0;pass<2;pass++) {
        unsigned mode=1-pass;int64_t native_rows=(int64_t)rows,width=2560,code_offset=64,scale_offset=(int64_t)(64+rows*1280),scale_stride=160;
        uint32_t blocks_per_row=320,total_blocks=(uint32_t)(320*rows);unsigned char optional_codebook[64]={0};
        void *vector_args[9]={&device_pack,&device_rows,&blocks_per_row,&total_blocks,&width,&code_offset,&scale_offset,&scale_stride,&optional_codebook};
        void *scalar_args[7]={&device_pack,&device_rows,&native_rows,&width,&code_offset,&scale_offset,&scale_stride};
        unsigned grid=mode?(unsigned)rows:(total_blocks+511)/512;
        HIP_OK(p_hipMemcpy(device_rows,multi_poison,tensor_bytes,hipMemcpyHostToDevice),"hip-converter-poison");copies_ok++;
        launch_attempts++;
        HIP_OK(p_hipModuleLaunchKernel(converters[mode],grid,1,1,256,1,1,0,NULL,mode?scalar_args:vector_args,NULL),"hip-original-converter-launch");launches_ok++;
        HIP_OK(p_hipDeviceSynchronize(),"hip-converter-synchronize");synchronizations_ok++;
        HIP_OK(p_hipMemcpy(multi_converted[mode],device_rows,tensor_bytes,hipMemcpyDeviceToHost),"hip-converter-output-copy");copies_ok++;
        converted_copied[mode]=1;
        if (!hash_memory(multi_converted[mode],tensor_bytes,converted_all_sha[mode])) goto cleanup;
        for (size_t i=0;i<rows;i++) {
            struct multi_row *row=&multi_rows[i];const uint16_t *actual=multi_converted[mode]+i*WORDS;
            if (!hash_memory(actual,TENSOR_BYTES,row->converted_sha[mode])) goto cleanup;
            row->raw_mismatches[mode]=multi_compare(actual,row->raw_reference,&row->first_raw[mode]);
            for (size_t j=0;j<WORDS;j++) row->raw_nonfinite[mode]+=((actual[j]&0x7f80)==0x7f80);
        }
    }
    for (size_t i=0;i<rows;i++) {
        struct multi_row *row=&multi_rows[i];int32_t width=2560,groups=1;
        size_t offset=i*TENSOR_BYTES;
        if (offset>tensor_bytes-TENSOR_BYTES) {fail("native-rms-row-bounds",0);goto cleanup;}
        void *device_row=(unsigned char *)device_rows+offset;
        void *args[5]={&device_row,&device_gamma,&device_row,&width,&groups};
        launch_attempts++;
        HIP_OK(p_hipModuleLaunchKernel(rms,1,1,1,256,1,1,0,NULL,args,NULL),"hip-original-count1-rms-launch");launches_ok++;
        HIP_OK(p_hipDeviceSynchronize(),"hip-count1-rms-synchronize");synchronizations_ok++;
        HIP_OK(p_hipMemcpy(row->normalized,device_row,TENSOR_BYTES,hipMemcpyDeviceToHost),"hip-rms-output-copy");copies_ok++;
        row->rms_copied=1;rms_copied_rows++;
        if (!hash_memory(row->normalized,TENSOR_BYTES,row->normalized_sha)) goto cleanup;
        row->norm_mismatches=multi_compare(row->normalized,row->norm_reference,&row->first_norm);
        for (size_t j=0;j<WORDS;j++) row->norm_nonfinite+=((row->normalized[j]&0x7f80)==0x7f80);
    }
    if (!verify_again(argv[1],ENGINE_SHA,ENGINE_BYTES,&engine_identity) ||
        !verify_again(argv[2],CODE_SHA,CODE_BYTES,&code_identity) ||
        !verify_again(argv[3],argv[4],(size_t)runtime_identity.st_size,&runtime_identity) ||
        !verify_again(argv[6],argv[7],manifest_bytes,&manifest_identity) ||
        !multi_path(path,sizeof path,argv[5],"selected-rows.q4c") || !verify_again(path,pack_sha,pack_bytes,&pack_identity) ||
        !multi_path(path,sizeof path,argv[5],"tokens.i32") || !verify_again(path,tokens_sha,rows*4,&tokens_identity) ||
        !multi_path(path,sizeof path,argv[5],"raw-gamma.u16") || !verify_again(path,MULTI_GAMMA_SHA,TENSOR_BYTES,&gamma_identity)) goto cleanup;
    for (size_t i=0;i<rows;i++) {
        struct multi_row *row=&multi_rows[i];
        if (!multi_row_path(path,sizeof path,argv[5],i,row->token,"raw") || !verify_again(path,row->raw_reference_sha,TENSOR_BYTES,&row->raw_identity) ||
            !multi_row_path(path,sizeof path,argv[5],i,row->token,"norm") || !verify_again(path,row->norm_reference_sha,TENSOR_BYTES,&row->norm_identity)) goto cleanup;
    }
    files_rechecked=1;
    for (size_t i=0;i<rows;i++) {
        struct multi_row *row=&multi_rows[i];
        if (row->raw_mismatches[0] || row->raw_mismatches[1] || row->norm_mismatches ||
            row->raw_nonfinite[0] || row->raw_nonfinite[1] || row->norm_nonfinite) fail("exact-BF16-word-gate",0);
    }
cleanup: ;
    void *allocations[3]={device_gamma,device_rows,device_pack};
    for (unsigned i=0;i<3;i++) if (allocations[i]) {
        if (!p_hipFree || p_hipFree(allocations[i])!=hipSuccess) cleanup_errors++;else free_ok++;
    }
    if (module) {if (!p_hipModuleUnload || p_hipModuleUnload(module)!=hipSuccess) cleanup_errors++;else module_unloads++;}
    if (library && dlclose(library)) cleanup_errors++;
    int inputs[4]={enginefd,codefd,runtimefd,manifestfd};
    for (unsigned i=0;i<4;i++) if (inputs[i]>=0 && close(inputs[i])) file_close_errors++;
    free(code);if (cleanup_errors) fail("hip-cleanup",(int)cleanup_errors);
    for (unsigned i=0;i<2;i++) {
        if (outfd[i]>=0 && converted_copied[i] && write_exact(outfd[i],multi_converted[i],tensor_bytes)) output_files_written++;
        if (outfd[i]>=0 && close(outfd[i])) file_close_errors++;
    }
    /* Retain only rows actually copied, including a completed prefix on failure. */
    if (outfd[2]>=0 && rms_copied_rows) {
        unsigned char normalized[MULTI_MAX_ROWS*TENSOR_BYTES];
        for (size_t i=0;i<rms_copied_rows;i++) memcpy(normalized+i*TENSOR_BYTES,multi_rows[i].normalized,TENSOR_BYTES);
        hash_memory(normalized,rms_copied_rows*TENSOR_BYTES,norm_all_sha);
        if (write_exact(outfd[2],normalized,rms_copied_rows*TENSOR_BYTES)) output_files_written++;
    }
    if (outfd[2]>=0 && close(outfd[2])) file_close_errors++;
    if (file_close_errors) fail("file-close",(int)file_close_errors);
    passed=!error_reason && files_rechecked && converted_copied[0] && converted_copied[1] && rms_copied_rows==rows &&
        rows && output_files_written==3 && launch_attempts==2+rows && launches_ok==2+rows && synchronizations_ok==2+rows &&
        copies_ok==6+rows && allocations_ok==3 && free_ok==3 && module_loads==1 && module_unloads==1;
    if (reportfd>=0) {
        char report[98304];size_t used=0;
#define MULTI_REPORT(...) do { int n=snprintf(report+used,sizeof report-used,__VA_ARGS__); \
    if (n<0 || (size_t)n>=sizeof report-used) {passed=0;goto report_done;} used+=(size_t)n; } while (0)
        MULTI_REPORT("{\"schema\":\"halogen0162.q4c-multirow-original-kernel-oracle.v1\",\"passed\":%s,"
            "\"scope\":\"bounded rebased selected checkpoint Q4C arithmetic plus original count1 RMS on native vector rows\","
            "\"manifest_sha256\":\"%s\",\"complete_sha256\":\"%s\",\"producer_plan_sha256\":\"%s\",\"producer_sha256\":\"%s\","
            "\"generation_hex\":\"%s\",\"sequence\":%" PRIu64 ",\"selected_rows\":%zu,\"width\":2560,"
            "\"engine_sha256\":\"%s\",\"codeobject_sha256\":\"%s\",\"runtime_sha256\":\"%s\",\"included_scaffold_sha256\":\"%s\","
            "\"codeobject_engine_offset\":331776,\"codeobject_bytes\":17704408,\"runtime_version\":%d,\"driver_version\":%d,"
            "\"pack_sha256\":\"%s\",\"tokens_sha256\":\"%s\",\"raw_gamma_sha256\":\"%s\",\"selected_window_hashes_verified\":%s,"
            "\"pack_bytes\":%zu,\"code_offset\":64,\"scale_offset\":%zu,\"scale_stride\":160,"
            "\"vector_kernel\":\"%s\",\"scalar_kernel\":\"%s\",\"rms_kernel\":\"%s\","
            "\"vector_grid\":[%zu,1,1],\"scalar_grid\":[%zu,1,1],\"rms_grid\":[1,1,1],\"block\":[256,1,1],\"shared_bytes\":0,"
            "\"default_stream\":true,\"hidden_ABI_supplied_by_HIP\":true,\"vector_blocks_per_row\":320,\"vector_total_blocks\":%zu,"
            "\"vector_optional_codebook_all_zero\":true,\"rms_groups\":1,\"rms_input_output_alias\":true,\"raw_gamma_copied_unchanged\":true,"
            "\"device_allocation_bytes\":%zu,\"original_full_table_loader_qualified\":false,\"live_allocation_qualified\":false,\"general_table_parity_qualified\":false,"
            "\"selected_rows_raw_parity_qualified\":%s,\"selected_rows_RMS_parity_qualified\":%s,"
            "\"gather_replayed\":false,\"live_generation_binding_proved\":false,\"native_FC_skip_admitted\":false,\"full_D_parity_qualified\":false,\"full_head_qualified\":false,"
            "\"FC_executed\":false,\"hidden_payload_read\":false,\"npu_executed\":false,\"supported_fabric_clock_overlap_qualified\":false,"
            "\"concurrent_GPU_NPU_inference_allowed\":false,\"acceptance_claim\":false,\"speed_claim\":false,\"tolerance_adjustment\":false,\"arithmetic_fitting\":false,"
            "\"reference_origin\":\"sealed CPU candidate reconstruction, native outputs compared exactly\",\"comparison\":\"all 2560 BF16 words per row, no tolerance\","
            "\"launch_attempts\":%u,\"launches_ok\":%u,\"synchronizations_ok\":%u,\"copies_ok\":%u,\"allocations_ok\":%u,\"free_ok\":%u,"
            "\"module_loads\":%u,\"module_unloads\":%u,\"cleanup_errors\":%u,\"file_close_errors\":%u,\"immutable_files_rechecked\":%s,\"output_files_written\":%u,"
            "\"vector_raw_file\":\"vector-raw.u16\",\"vector_raw_bytes\":%zu,\"vector_raw_sha256\":\"%s\","
            "\"scalar_raw_file\":\"scalar-raw.u16\",\"scalar_raw_bytes\":%zu,\"scalar_raw_sha256\":\"%s\","
            "\"native_norm_file\":\"vector-native-norm.u16\",\"native_norm_bytes\":%zu,\"native_norm_sha256\":\"%s\","
            "\"error\":\"%s\",\"error_code\":%d,\"rows\":[",
            passed?"true":"false",manifest_sha,complete_sha,plan_sha,producer_sha,generation_hex,sequence,rows,
            ENGINE_SHA,CODE_SHA,argv[4],MULTI_SCAFFOLD_SHA,runtime_version,driver_version,pack_sha,tokens_sha,gamma_sha,windows_verified?"true":"false",
            pack_bytes,64+rows*1280,MULTI_VECTOR_KERNEL,MULTI_SCALAR_KERNEL,KERNEL,(320*rows+511)/512,rows,320*rows,pack_bytes+tensor_bytes+TENSOR_BYTES,passed?"true":"false",passed?"true":"false",
            launch_attempts,launches_ok,synchronizations_ok,copies_ok,allocations_ok,free_ok,module_loads,module_unloads,cleanup_errors,file_close_errors,
            files_rechecked?"true":"false",output_files_written,converted_copied[0]?tensor_bytes:0,converted_all_sha[0],converted_copied[1]?tensor_bytes:0,converted_all_sha[1],
            rms_copied_rows*TENSOR_BYTES,norm_all_sha,error_reason?error_reason:"",error_code);
        for (size_t i=0;i<rows;i++) {
            struct multi_row *row=&multi_rows[i];
            MULTI_REPORT("%s{\"index\":%zu,\"token\":%" PRIu32 ",\"raw_reference_sha256\":\"%s\",\"norm_reference_sha256\":\"%s\","
                "\"vector_copied\":%s,\"scalar_copied\":%s,\"rms_copied\":%s,\"vector_raw_sha256\":\"%s\",\"scalar_raw_sha256\":\"%s\",\"native_norm_sha256\":\"%s\","
                "\"vector_raw_mismatches\":%u,\"scalar_raw_mismatches\":%u,\"native_norm_mismatches\":%u,"
                "\"first_vector_raw_index_or_width\":%zu,\"first_scalar_raw_index_or_width\":%zu,\"first_native_norm_index_or_width\":%zu,"
                "\"vector_raw_nonfinite\":%u,\"scalar_raw_nonfinite\":%u,\"native_norm_nonfinite\":%u}",
                i?",":"",i,row->token,row->raw_reference_sha,row->norm_reference_sha,converted_copied[0]?"true":"false",converted_copied[1]?"true":"false",
                row->rms_copied?"true":"false",row->converted_sha[0],row->converted_sha[1],row->normalized_sha,row->raw_mismatches[0],row->raw_mismatches[1],row->norm_mismatches,
                row->first_raw[0],row->first_raw[1],row->first_norm,row->raw_nonfinite[0],row->raw_nonfinite[1],row->norm_nonfinite);
        }
        MULTI_REPORT("]}\n");
        if (!write_exact(reportfd,report,used)) passed=0;
#undef MULTI_REPORT
    } else passed=0;
report_done:
    if (reportfd>=0 && close(reportfd)) passed=0;
    if (dirfd>=0 && close(dirfd)) passed=0;
    fprintf(stderr,"original Q4C multirow oracle passed=%d rows=%zu launches=%u cleanup_errors=%u error=%s code=%d\n",
        passed,rows,launch_attempts,cleanup_errors,error_reason?error_reason:"",error_code);
    return passed?0:1;
}
