/* Prepared offline from the pinned 0.17.2 ELF. No runtime qualification. */
#ifndef PRIVATE_PLE_ENGINE_BINDING_0172_V2_H
#define PRIVATE_PLE_ENGINE_BINDING_0172_V2_H
#define PLE_ENGINE_VERSION "0.17.2"
#define PLE_ENGINE_SHA "ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913"
#define PLE_ENGINE_BYTES 26178504u
/* Return-register status semantics require review before a source port. */
#define PLE_WRAPPER_RESULT_ABI_QUALIFIED 0
#define PLE_TARGET_RESULT_ABI_QUALIFIED 0
#define PLE_WRAPPER_RVA ((uintptr_t)0x1803380)
#define PLE_WRAPPER_OFFSET ((off_t)0x1802380)
#define PLE_WRAPPER_BYTES ((size_t)1179)
#define PLE_WRAPPER_SHA "195474d64d3028b4fa7f56221801d4112b7f5398ca0f09d223b544119ee6d716"
static const unsigned char ple_wrapper_signature[32]={0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x83,0xec,0x28,0x41,0x89,0xd0,0x48,0x89,0x74,0x24,0x08,0x48,0x89,0xfb,0x0f,0xb6,0x05,0x70,0x85,0x0f,0x00};
#define PLE_TARGET_RVA ((uintptr_t)0x17f79f0)
#define PLE_TARGET_OFFSET ((off_t)0x17f69f0)
#define PLE_TARGET_BYTES ((size_t)8720)
#define PLE_TARGET_SHA "9ad6517e3a8b8df6b6386f12f9c2d85c2963df96274cfa2d48769539db02d7c3"
static const unsigned char ple_target_signature[32]={0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x81,0xec,0x38,0x01,0x00,0x00,0x41,0x89,0xd0,0x89,0x8c,0x24,0x9c,0x00,0x00,0x00,0xc7,0x47,0x5c,0x00,0x00};
#define PLE_HELPER_RVA ((uintptr_t)0x17ee710)
#define PLE_HELPER_OFFSET ((off_t)0x17ed710)
#define PLE_HELPER_BYTES ((size_t)728)
#define PLE_HELPER_SHA "826bac09ab63de6dae0f2b33820aeb1077ded54e16f7ce63ee5bb9d1e71c90d8"
static const unsigned char ple_helper_signature[32]={0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x81,0xec,0xb8,0x00,0x00,0x00,0x45,0x89,0xcc,0x4c,0x89,0x84,0x24,0xa0,0x00,0x00,0x00,0x49,0x89,0xce,0x49};
#define PLE_FC_RVA ((uintptr_t)0x17a53b0)
#define PLE_FC_OFFSET ((off_t)0x17a43b0)
#define PLE_FC_BYTES ((size_t)8215)
#define PLE_FC_SHA "513f872cd0eff22f7e1a7550e8b36fccab4b93910a09b7531052d518ac6f4659"
static const unsigned char ple_fc_signature[32]={0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x83,0xec,0x48,0x4c,0x89,0xcb,0x45,0x89,0xc5,0x89,0xcd,0x49,0x89,0xd6,0x49,0x89,0xf7,0x49,0x89,0xfc,0x4c};
#define PLE_WRAPPER_TARGET_RETURN ((uintptr_t)0x180353d)
#define PLE_HELPER_RETURN ((uintptr_t)0x17ebca5)
#define PLE_KEY_RETURN ((uintptr_t)0x17ecf19)
#define PLE_CHUNK_GLOBAL ((uintptr_t)0x18fb908)
#define PLE_CHUNK_INIT_GLOBAL ((uintptr_t)0x18fb910)
#define PLE_MODEL_READABLE_EXTENT ((size_t)0xd90)
#define PLE_MODEL_CAPACITY ((size_t)0x2d8)
#define PLE_MODEL_POSITION ((size_t)0x2e0)
#define PLE_MODEL_CALLBACK_OBJECT ((size_t)0x2f8)
#define PLE_MODEL_CALLBACK_MANAGER ((size_t)0x308)
#define PLE_MODEL_CALLBACK_INVOKER ((size_t)0x310)
#define PLE_MODEL_STOP ((size_t)0x318)
#define PLE_MODEL_MIXED_MANAGER_1 ((size_t)0x330)
#define PLE_MODEL_MIXED_MANAGER_2 ((size_t)0x350)
#define PLE_MODEL_NATIVE_THREAD_STATE ((size_t)0x7b0)
#define PLE_MODEL_NATIVE_STAGING_ALLOCATION ((size_t)0x7b8)
#define PLE_MODEL_NATIVE_PREFETCH_FLAG ((size_t)0x7c0)
#define PLE_MODEL_NATIVE_NEXT_TOKENS ((size_t)0x7c8)
#define PLE_MODEL_NATIVE_NEXT_COUNT ((size_t)0x7d0)
#define PLE_SERVING_CALLBACK_MANAGER_RVA ((uintptr_t)0x174b0d0)
#define PLE_SERVING_CALLBACK_INVOKER_RVA ((uintptr_t)0x174ab30)
/* Exact native CPU prefetch functions, not the GPU helper. All have the
 * same five whole push bytes accepted by the existing detour implementation.
 * Retained map: ple0172-prefetch-static-v2, independently reviewed. */
#define PLE_PREFETCH_LAUNCH_RVA ((uintptr_t)0x18011e0)
#define PLE_PREFETCH_LAUNCH_OFFSET ((off_t)0x18001e0)
#define PLE_PREFETCH_LAUNCH_BYTES ((size_t)1379)
#define PLE_PREFETCH_LAUNCH_SHA "40c41d4ca3f669ab5c12ebd25f6ba903fd8daf02c36f04be479fef44f99a0521"
static const unsigned char ple_prefetch_launch_signature[32]={0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x83,0xec,0x38,0x49,0x89,0xf7,0x31,0xc0,0x86,0x46,0x60,0x48,0x89,0xfd,0x48,0xbb,0xcf,0xf7,0x53,0xe3,0xa5};
#define PLE_PREFETCH_WAIT_RVA ((uintptr_t)0x1801e80)
#define PLE_PREFETCH_WAIT_OFFSET ((off_t)0x1800e80)
#define PLE_PREFETCH_WAIT_BYTES ((size_t)659)
#define PLE_PREFETCH_WAIT_SHA "b27cc5a03eaab277b6dc4d795ddaf0f377c4ce425972217ea08b33af668238cd"
static const unsigned char ple_prefetch_wait_signature[32]={0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x83,0xec,0x28,0x41,0x89,0xd5,0x48,0x89,0xf3,0x49,0x89,0xfe,0x0f,0xb6,0x05,0x22,0x9a,0x0f,0x00,0x84,0xc0};
#define PLE_PREFETCH_RUN_RVA ((uintptr_t)0x1865530)
#define PLE_PREFETCH_RUN_OFFSET ((off_t)0x1864530)
#define PLE_PREFETCH_RUN_BYTES ((size_t)2303)
#define PLE_PREFETCH_RUN_SHA "f905b0035b1f131fe93aa95d9a66599669614456e29927c2f52ca78cbea25b9f"
static const unsigned char ple_prefetch_run_signature[32]={0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x81,0xec,0x08,0x01,0x00,0x00,0x48,0x89,0xfd,0x4c,0x8b,0x67,0x08,0x48,0x8b,0x5f,0x10,0x4c,0x8b,0x7b,0x10};
#define PLE_PREFETCH_LAUNCH_RETURN ((uintptr_t)0x17ef05d)
#define PLE_PREFETCH_WAIT_RETURN ((uintptr_t)0x17eeb95)
#define PLE_PREFETCH_PAYLOAD_VTABLE ((uintptr_t)0x18f6a28)
#define PLE_PREFETCH_WORKER_COUNT ((uintptr_t)0x18fb8c8)
#define PLE_PREFETCH_WORKER_COUNT_INIT ((uintptr_t)0x18fb8d0)
#define PLE_MODEL_NATIVE_CURRENT_STATE ((size_t)0x7a8)
#define PLE_MODEL_NATIVE_PREFETCH_STRIDE ((size_t)0x770)
#define PLE_MODEL_NATIVE_PREFETCH_TABLE ((size_t)0x758)
#define PLE_MODEL_NATIVE_PREFETCH_CONSTANTS ((size_t)0x7d8)
#define PLE_MODEL_NATIVE_PREFETCH_CONSTANT_BYTES ((size_t)280)
#define PLE_NATIVE_STATE_READABLE_BYTES ((size_t)0x140)
/* Native initializer1800fb0: default64; explicit parsed int32 clamped1..256. */
#define PLE_PREFETCH_MAX_WORKERS 256u
#endif
