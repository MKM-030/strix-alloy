/* Small original-Q4C-shader oracle; root alone builds/runs under owned GPU
 * admission, reserve and deadline. No server loading, injection or replacement.
 *
 * The source pack is exactly 1504 unchanged checkpoint bytes rebased as
 * [64-byte codebook][1280-byte codes][160-byte scales]. Row count=1,width=2560,
 * code offset=64,scale offset=1344,scale stride=160. This is selected-row layout
 * parity, never an original full-table allocation/loader or live-state proof.
 *
 * Default aligned absent-override route: k_deq_q4cp_v8u<2,false>, grid1/block256,
 * public ptr/ptr/u32/u32/i64/i64/i64/i64/64-byte DeqCb at offsets
 * 0/8/16/20/24/32/40/48/56. Unroll2 covers 512 blocks per workgroup;
 * blocks_per_row=total_blocks=320. The optional DeqCb is all-zero as in the
 * loader's null optional codebook path. Metadata: LDS64,kernarg376,align8,wave32.
 * Scalar original sibling uses ptr/ptr/i64/i64/i64/i64/i64,grid1/block256.
 * HIP supplies hidden ABI values via its ordinary module API.
 *
 * Each conversion is copied device-to-device into actual row14367 of a private
 * hipMalloc-owned 14368-row BF16 table (73564160 bytes), then the original
 * k_embed_gather copies that row with actual ID14367,grid1/block256. No pointer
 * is rebased outside an allocation, and no borrowed allocation proof is used.
 * Every output is retained even on numerical mismatch. Exact BF16-word gates
 * compare each converter with the independently pinned CPU reference, gather
 * with converter, and gather with reference. A mismatch qualifies nothing.
 *
 * Root build: gcc -O2 -Wall -Wextra -Werror -D__HIP_PLATFORM_AMD__
 * -I<reviewed HIP include> -DQ4C_BUILD_SCAFFOLD_SHA=\"<independent SHA>\"
 * halogen0162_q4c_row_oracle.c -ldl -lcrypto -o <new binary>.
 * Compile envelope separately pins this source, included scaffold and binary.
 * Usage: ENGINE HSACO HIP_LIBRARY HIP_SHA NATIVE_PACK PACK_SHA CPU_ROW NEW_DIR.
 */
#define main frozen_embedding_rms_oracle_entry_unused
#include "halogen0162_embedding_rms_replay.c"
#undef main

#ifndef Q4C_BUILD_SCAFFOLD_SHA
#error Independently pinned frozen embedding RMS scaffold SHA required
#endif
#define Q4C_SCAFFOLD_SHA "7ea99028014f590a0938d5a06790f51ce571948706d851c16bfcb72f694f4fa8"
#define Q4C_PACK_BYTES ((size_t)1504)
#define Q4C_TOKEN ((int32_t)14367)
#define Q4C_TABLE_ROWS ((size_t)14368)
#define Q4C_TABLE_BYTES (Q4C_TABLE_ROWS * TENSOR_BYTES)
#define Q4C_REFERENCE_SHA "af284c0101ac76b7562b3d9e19cfc6721266f282358d8f313a09b961435ee374"
#define Q4C_VECTOR_KERNEL "_ZN7halogen12_GLOBAL__N_114k_deq_q4cp_v8uILi2ELb0EEEvPKhPtjjllllNS0_5DeqCbE"
#define Q4C_SCALAR_KERNEL "_ZN7halogen12_GLOBAL__N_110k_deq_q4cpEPKhPtlllll"
#define Q4C_GATHER_KERNEL "_ZN7halogen12_GLOBAL__N_114k_embed_gatherEPKtPKiPt"
static const char *q4c_window_sha[3]={
    "1f2755c994ae6ea3d4a24a5cc2b8066de0971b07eacd76a05c5e111cba8d3679",
    "47b6702d51297b13cc90632f2f746d42b0c5fc97d06fcf778dbad225aac8cbcb",
    "79cc173820638d74f37a9340782a92e4d620b8a53cff138d17c7ebebeaafeabb"};
static const char *q4c_output_names[4]={"vector-converted.u16","vector-gathered.u16",
    "scalar-converted.u16","scalar-gathered.u16"};
struct q4c_result {
    uint16_t converted[WORDS],gathered[WORDS];
    char converted_sha[65],gathered_sha[65];
    unsigned converted_copied,gathered_copied,completed,nonfinite;
    unsigned converter_reference_mismatches,gather_converter_mismatches,gather_reference_mismatches;
    size_t first_converter_reference,first_gather_converter,first_gather_reference;
};
static struct q4c_result q4c_results[2];

static unsigned q4c_compare(const uint16_t *actual,const uint16_t *expected,size_t *first) {
    unsigned mismatches=0;*first=WORDS;
    for (size_t i=0;i<WORDS;i++) if (actual[i]!=expected[i]) {
        if (!mismatches) *first=i;
        mismatches++;
    }
    return mismatches;
}

int main(int argc,char **argv) {
    if (argc!=9) {
        fputs("Expected ENGINE HSACO HIP_LIBRARY HIP_SHA NATIVE_PACK PACK_SHA CPU_ROW NEW_DIR\n",stderr);
        return 2;
    }
    if (strcmp(Q4C_BUILD_SCAFFOLD_SHA,Q4C_SCAFFOLD_SHA)) {
        fputs("Frozen scaffold compile pin differs\n",stderr);return 2;
    }
    int dirfd=-1,reportfd=-1,outfd[4]={-1,-1,-1,-1},enginefd=-1,codefd=-1,runtimefd=-1;
    void *library=NULL,*code=NULL,*device_pack=NULL,*device_row=NULL,*device_gather=NULL,*device_ids=NULL,*device_table=NULL;
    hipModule_t module=NULL;hipFunction_t converters[2]={NULL,NULL},gather=NULL;
    unsigned char packed[Q4C_PACK_BYTES];uint16_t reference[WORDS],poison_row[WORDS];
    char pack_sha[65]="",reference_sha[65]="";
    struct stat engine_identity,code_identity,runtime_identity,pack_identity,reference_identity;
    int runtime_version=0,driver_version=0,passed=0,files_rechecked=0,window_hashes_verified=0;
    unsigned output_files_written=0,file_close_errors=0,memsets_ok=0;
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
    API(hipMemset,hipError_t,(void *,int,size_t));
    API(hipDeviceSynchronize,hipError_t,(void));

    for (unsigned i=0;i<2;i++) {
        q4c_results[i].first_converter_reference=WORDS;
        q4c_results[i].first_gather_converter=WORDS;
        q4c_results[i].first_gather_reference=WORDS;
    }

    if (argv[8][0]!='/' || mkdir(argv[8],0700)) {
        fprintf(stderr,"Exclusive new output directory failed, errno=%d\n",errno);return 2;
    }
    dirfd=open(argv[8],O_DIRECTORY|O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (dirfd<0) {fail("output-directory-open",errno);goto cleanup;}
    reportfd=openat(dirfd,"replay.json",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    for (unsigned i=0;i<4;i++) outfd[i]=openat(dirfd,q4c_output_names[i],O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (reportfd<0 || outfd[0]<0 || outfd[1]<0 || outfd[2]<0 || outfd[3]<0) {fail("output-exclusive-create",errno);goto cleanup;}
    if (!valid_sha(argv[4]) || !valid_sha(argv[6])) {fail("independent-sha-format",0);goto cleanup;}
    enginefd=open_regular(argv[1],ENGINE_BYTES,ENGINE_BYTES,&engine_identity);
    codefd=open_regular(argv[2],CODE_BYTES,CODE_BYTES,&code_identity);
    runtimefd=open_regular(argv[3],0,128<<20,&runtime_identity);
    if (enginefd<0 || codefd<0 || runtimefd<0) goto cleanup;
    if (!hash_file(enginefd,ENGINE_SHA) || !verify_identity(enginefd,&engine_identity) ||
        !hash_file(runtimefd,argv[4]) || !verify_identity(runtimefd,&runtime_identity)) goto cleanup;
    code=malloc(CODE_BYTES);
    if (!code) {fail("host-code-allocation",errno);goto cleanup;}
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
        !load_bytes(argv[5],argv[6],packed,Q4C_PACK_BYTES,pack_sha,&pack_identity) ||
        !load_bytes(argv[7],Q4C_REFERENCE_SHA,reference,TENSOR_BYTES,reference_sha,&reference_identity)) goto cleanup;
    const size_t offsets[3]={0,64,1344},extents[3]={64,1280,160};
    for (unsigned i=0;i<3;i++) {
        char observed[65];
        if (!hash_memory(packed+offsets[i],extents[i],observed)) goto cleanup;
        if (strcmp(observed,q4c_window_sha[i])) {fail("checkpoint-window-sha256-mismatch",0);goto cleanup;}
    }
    window_hashes_verified=1;
    for (size_t i=0;i<WORDS;i++) {
        if ((reference[i]&0x7f80)==0x7f80) {fail("nonfinite-reference",0);goto cleanup;}
        poison_row[i]=0x7fc0;
    }
    if (!verify_again(argv[3],argv[4],(size_t)runtime_identity.st_size,&runtime_identity)) goto cleanup;
    library=dlopen(argv[3],RTLD_NOW|RTLD_LOCAL);
    if (!library) {fail("hip-dlopen",0);fputs(dlerror(),stderr);fputc('\n',stderr);goto cleanup;}
    RESOLVE(hipGetDeviceCount);RESOLVE(hipGetDevicePropertiesR0600);RESOLVE(hipSetDevice);
    RESOLVE(hipRuntimeGetVersion);RESOLVE(hipDriverGetVersion);RESOLVE(hipModuleLoadData);
    RESOLVE(hipModuleGetFunction);RESOLVE(hipModuleLaunchKernel);RESOLVE(hipModuleUnload);
    RESOLVE(hipMalloc);RESOLVE(hipFree);RESOLVE(hipMemcpy);RESOLVE(hipMemset);RESOLVE(hipDeviceSynchronize);
    int count=0;hipDeviceProp_t properties;
    memset(&properties,0,sizeof properties);
    HIP_OK(p_hipGetDeviceCount(&count),"hip-device-count");
    if (count!=1) {fail("exactly-one-gpu-required",count);goto cleanup;}
    HIP_OK(p_hipGetDevicePropertiesR0600(&properties,0),"hip-device-properties");
    if (strcmp(properties.gcnArchName,"gfx1151") || properties.warpSize!=32) {fail("gpu-gfx1151-wave32-required",0);goto cleanup;}
    HIP_OK(p_hipSetDevice(0),"hip-set-device");
    HIP_OK(p_hipRuntimeGetVersion(&runtime_version),"hip-runtime-version");
    HIP_OK(p_hipDriverGetVersion(&driver_version),"hip-driver-version");
    HIP_OK(p_hipModuleLoadData(&module,code),"hip-module-load");module_loads++;
    HIP_OK(p_hipModuleGetFunction(&converters[0],module,Q4C_VECTOR_KERNEL),"hip-vector-symbol");
    HIP_OK(p_hipModuleGetFunction(&converters[1],module,Q4C_SCALAR_KERNEL),"hip-scalar-symbol");
    HIP_OK(p_hipModuleGetFunction(&gather,module,Q4C_GATHER_KERNEL),"hip-gather-symbol");
    HIP_OK(p_hipMalloc(&device_pack,Q4C_PACK_BYTES),"hip-packed-allocation");allocations_ok++;
    HIP_OK(p_hipMalloc(&device_row,TENSOR_BYTES),"hip-converted-allocation");allocations_ok++;
    HIP_OK(p_hipMalloc(&device_gather,TENSOR_BYTES),"hip-gather-allocation");allocations_ok++;
    HIP_OK(p_hipMalloc(&device_ids,sizeof(int32_t)),"hip-token-allocation");allocations_ok++;
    HIP_OK(p_hipMalloc(&device_table,Q4C_TABLE_BYTES),"hip-owned-table-allocation");allocations_ok++;
    if ((uintptr_t)device_pack%16 || (uintptr_t)device_row%16 || (uintptr_t)device_table%16) {fail("native-vector-alignment",0);goto cleanup;}
    HIP_OK(p_hipMemset(device_table,0xa5,Q4C_TABLE_BYTES),"hip-owned-table-poison");memsets_ok++;
    HIP_OK(p_hipMemcpy(device_pack,packed,Q4C_PACK_BYTES,hipMemcpyHostToDevice),"hip-packed-copy");copies_ok++;
    int32_t token=Q4C_TOKEN;
    HIP_OK(p_hipMemcpy(device_ids,&token,sizeof token,hipMemcpyHostToDevice),"hip-actual-token-copy");copies_ok++;
    for (unsigned i=0;i<2;i++) {
        struct q4c_result *result=&q4c_results[i];
        int64_t rows=1,width=2560,code_offset=64,scale_offset=1344,scale_stride=160;
        uint32_t blocks_per_row=320,total_blocks=320;unsigned char optional_codebook[64]={0};
        void *vector_args[9]={&device_pack,&device_row,&blocks_per_row,&total_blocks,&width,
            &code_offset,&scale_offset,&scale_stride,&optional_codebook};
        void *scalar_args[7]={&device_pack,&device_row,&rows,&width,&code_offset,&scale_offset,&scale_stride};
        HIP_OK(p_hipMemcpy(device_row,poison_row,TENSOR_BYTES,hipMemcpyHostToDevice),"hip-converter-poison");copies_ok++;
        HIP_OK(p_hipMemcpy(device_gather,poison_row,TENSOR_BYTES,hipMemcpyHostToDevice),"hip-gather-poison");copies_ok++;
        launch_attempts++;
        HIP_OK(p_hipModuleLaunchKernel(converters[i],1,1,1,256,1,1,0,NULL,i?scalar_args:vector_args,NULL),"hip-original-converter-launch");launches_ok++;
        HIP_OK(p_hipDeviceSynchronize(),"hip-converter-synchronize");synchronizations_ok++;
        HIP_OK(p_hipMemcpy(result->converted,device_row,TENSOR_BYTES,hipMemcpyDeviceToHost),"hip-converter-output-copy");copies_ok++;
        result->converted_copied=1;
        if (!hash_memory(result->converted,TENSOR_BYTES,result->converted_sha)) goto cleanup;
        result->converter_reference_mismatches=q4c_compare(result->converted,reference,&result->first_converter_reference);
        /* Real allocation + real selected ID, with an independently bounded D2D write. */
        const size_t destination_offset=(size_t)Q4C_TOKEN*TENSOR_BYTES;
        if (destination_offset>Q4C_TABLE_BYTES-TENSOR_BYTES) {fail("owned-table-row-bounds",0);goto cleanup;}
        void *selected_row=(unsigned char *)device_table+destination_offset;
        HIP_OK(p_hipMemcpy(selected_row,device_row,TENSOR_BYTES,hipMemcpyDeviceToDevice),"hip-converter-to-owned-table");copies_ok++;
        void *gather_args[3]={&device_table,&device_ids,&device_gather};
        launch_attempts++;
        HIP_OK(p_hipModuleLaunchKernel(gather,1,1,1,256,1,1,0,NULL,gather_args,NULL),"hip-original-gather-launch");launches_ok++;
        HIP_OK(p_hipDeviceSynchronize(),"hip-gather-synchronize");synchronizations_ok++;
        HIP_OK(p_hipMemcpy(result->gathered,device_gather,TENSOR_BYTES,hipMemcpyDeviceToHost),"hip-gather-output-copy");copies_ok++;
        result->gathered_copied=1;
        if (!hash_memory(result->gathered,TENSOR_BYTES,result->gathered_sha)) goto cleanup;
        result->gather_converter_mismatches=q4c_compare(result->gathered,result->converted,&result->first_gather_converter);
        result->gather_reference_mismatches=q4c_compare(result->gathered,reference,&result->first_gather_reference);
        for (size_t j=0;j<WORDS;j++) result->nonfinite+=((result->converted[j]&0x7f80)==0x7f80)+((result->gathered[j]&0x7f80)==0x7f80);
        result->completed=1;
    }
    if (!verify_again(argv[1],ENGINE_SHA,ENGINE_BYTES,&engine_identity) ||
        !verify_again(argv[2],CODE_SHA,CODE_BYTES,&code_identity) ||
        !verify_again(argv[3],argv[4],(size_t)runtime_identity.st_size,&runtime_identity) ||
        !verify_again(argv[5],argv[6],Q4C_PACK_BYTES,&pack_identity) ||
        !verify_again(argv[7],Q4C_REFERENCE_SHA,TENSOR_BYTES,&reference_identity)) goto cleanup;
    files_rechecked=1;
    for (unsigned i=0;i<2;i++) if (q4c_results[i].converter_reference_mismatches ||
        q4c_results[i].gather_converter_mismatches || q4c_results[i].gather_reference_mismatches || q4c_results[i].nonfinite)
        fail("exact-BF16-word-gate",0);
cleanup: ;
    void *allocations[5]={device_table,device_ids,device_gather,device_row,device_pack};
    for (unsigned i=0;i<5;i++) if (allocations[i]) {
        if (!p_hipFree || p_hipFree(allocations[i])!=hipSuccess) cleanup_errors++;else free_ok++;
    }
    if (module) {if (!p_hipModuleUnload || p_hipModuleUnload(module)!=hipSuccess) cleanup_errors++;else module_unloads++;}
    if (library && dlclose(library)) cleanup_errors++;
    if (enginefd>=0 && close(enginefd)) file_close_errors++;
    if (codefd>=0 && close(codefd)) file_close_errors++;
    if (runtimefd>=0 && close(runtimefd)) file_close_errors++;
    free(code);
    if (cleanup_errors) fail("hip-cleanup",(int)cleanup_errors);
    for (unsigned i=0;i<4;i++) {
        struct q4c_result *result=&q4c_results[i/2];
        unsigned copied=(i%2)?result->gathered_copied:result->converted_copied;
        if (outfd[i]>=0 && copied && write_exact(outfd[i],(i%2)?result->gathered:result->converted,TENSOR_BYTES)) output_files_written++;
        if (outfd[i]>=0 && close(outfd[i])) file_close_errors++;
    }
    if (file_close_errors) fail("file-close",(int)file_close_errors);
    passed=!error_reason && files_rechecked && q4c_results[0].completed && q4c_results[1].completed &&
        output_files_written==4 && launch_attempts==4 && launches_ok==4 && synchronizations_ok==4 && copies_ok==12 &&
        allocations_ok==5 && free_ok==5 && memsets_ok==1 && module_loads==1 && module_unloads==1;
    if (reportfd>=0) {
        char report[12288];size_t used=0;
        int n=snprintf(report,sizeof report,
            "{\"schema\":\"halogen0162.q4c-selected-row-original-kernel-oracle.v1\",\"passed\":%s,"
            "\"scope\":\"original scalar/default-v8u2 conversion of rebased selected checkpoint row and original gather of actual ID14367 from private allocation; full-table loader/live model unqualified\","
            "\"engine_sha256\":\"%s\",\"codeobject_sha256\":\"%s\",\"runtime_sha256\":\"%s\",\"included_scaffold_sha256\":\"%s\","
            "\"native_pack_sha256\":\"%s\",\"reference_sha256\":\"%s\",\"reference_origin\":\"pinned CPU reconstruction, compared against original GPU conversion\","
            "\"checkpoint_sha256_lineage\":\"71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687\","
            "\"checkpoint_whole_file_rehashed_by_harness\":false,\"selected_window_hashes_verified\":%s,"
            "\"codeobject_engine_offset\":331776,\"codeobject_bytes\":17704408,\"runtime_version\":%d,\"driver_version\":%d,"
            "\"token\":14367,\"width\":2560,\"selected_rows\":1,\"pack_bytes\":1504,\"code_offset\":64,\"scale_offset\":1344,\"scale_stride\":160,"
            "\"private_table_rows\":14368,\"private_table_bytes\":73564160,\"private_table_selected_row_offset\":73559040,"
            "\"private_allocations_from_successful_hipMalloc\":%s,\"borrowed_allocation_proof\":false,\"pointer_rebased_outside_allocation\":false,"
            "\"gather_kernel\":\"%s\",\"grid\":[1,1,1],\"block\":[256,1,1],\"shared_bytes\":0,\"default_stream\":true,\"hidden_ABI_supplied_by_HIP\":true,"
            "\"vector_blocks_per_row\":320,\"vector_total_blocks\":320,\"vector_unroll\":2,\"optional_codebook_all_zero\":true,"
            "\"vector_public_offsets\":[0,8,16,20,24,32,40,48,56],\"vector_public_sizes\":[8,8,4,4,8,8,8,8,64],"
            "\"vector_static_LDS_bytes\":64,\"vector_kernarg_bytes\":376,\"kernarg_alignment\":8,\"wave_size\":32,"
            "\"comparison\":\"all 2560 BF16 words exactly; no tolerance or arithmetic fitting\",\"native_cpu_conversion_parity_qualified\":%s,"
            "\"selected_private_table_gather_qualified\":%s,\"original_full_table_loader_qualified\":false,\"live_model_allocation_qualified\":false,"
            "\"general_table_parity_qualified\":false,\"full_head_qualified\":false,\"acceptance_claim\":false,\"speed_claim\":false,"
            "\"launch_attempts\":%u,\"launches_ok\":%u,\"synchronizations_ok\":%u,\"copies_ok\":%u,\"allocations_ok\":%u,\"free_ok\":%u,\"memsets_ok\":%u,"
            "\"module_loads\":%u,\"module_unloads\":%u,\"cleanup_errors\":%u,\"file_close_errors\":%u,\"immutable_files_rechecked\":%s,\"output_files_written\":%u,"
            "\"error\":\"%s\",\"error_code\":%d,\"converters\":[",
            passed?"true":"false",ENGINE_SHA,CODE_SHA,valid_sha(argv[4])?argv[4]:"",Q4C_BUILD_SCAFFOLD_SHA,
            pack_sha,reference_sha,window_hashes_verified?"true":"false",runtime_version,driver_version,allocations_ok==5?"true":"false",Q4C_GATHER_KERNEL,
            passed?"true":"false",passed?"true":"false",launch_attempts,launches_ok,synchronizations_ok,copies_ok,
            allocations_ok,free_ok,memsets_ok,module_loads,module_unloads,cleanup_errors,file_close_errors,
            files_rechecked?"true":"false",output_files_written,error_reason?error_reason:"",error_code);
        if (n<0 || (size_t)n>=sizeof report) {passed=0;goto report_done;}
        used=(size_t)n;
        for (unsigned i=0;i<2;i++) {
            struct q4c_result *result=&q4c_results[i];
            n=snprintf(report+used,sizeof report-used,
                "%s{\"mode\":\"%s\",\"kernel\":\"%s\",\"completed\":%s,\"converted_copied\":%s,\"gathered_copied\":%s,"
                "\"converted_sha256\":\"%s\",\"gathered_sha256\":\"%s\",\"converted_file\":\"%s\",\"gathered_file\":\"%s\","
                "\"converter_reference_mismatches\":%u,\"gather_converter_mismatches\":%u,\"gather_reference_mismatches\":%u,"
                "\"first_converter_reference_index_or_width\":%zu,\"first_gather_converter_index_or_width\":%zu,\"first_gather_reference_index_or_width\":%zu,\"nonfinite_words\":%u}",
                i?",":"",i?"scalar":"default-aligned-v8u2-optional-codebook-false",i?Q4C_SCALAR_KERNEL:Q4C_VECTOR_KERNEL,
                result->completed?"true":"false",result->converted_copied?"true":"false",result->gathered_copied?"true":"false",
                result->converted_sha,result->gathered_sha,q4c_output_names[2*i],q4c_output_names[2*i+1],
                result->converter_reference_mismatches,result->gather_converter_mismatches,result->gather_reference_mismatches,
                result->first_converter_reference,result->first_gather_converter,result->first_gather_reference,result->nonfinite);
            if (n<0 || (size_t)n>=sizeof report-used) {passed=0;goto report_done;}
            used+=(size_t)n;
        }
        if (sizeof report-used<4) {passed=0;goto report_done;}
        memcpy(report+used,"]}\n",3);used+=3;
        if (!write_exact(reportfd,report,used)) passed=0;
    } else passed=0;
report_done:
    if (reportfd>=0 && close(reportfd)) passed=0;
    if (dirfd>=0 && close(dirfd)) passed=0;
    fprintf(stderr,"original Q4C row oracle passed=%d launches=%u cleanup_errors=%u error=%s code=%d\n",
        passed,launch_attempts,cleanup_errors,error_reason?error_reason:"",error_code);
    return passed?0:1;
}
