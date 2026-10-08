/* Exact Halogen 0.17.2 internal seams, reached by JMP rather than CALL.
 * Dispatcher ABI (SysV): uintptr_t(void *native_rsp, uint64_t *saved_gprs).
 * saved_gprs order: rax, rbx, rcx, rdx, rsi, rdi, rbp, r8, r9, r10,
 *                   r11, r12, r13, r14, r15.
 * A dispatcher may change that block and returns the continuation address.
 *
 * The pinned prologues leave native RSP aligned to 16 bytes:
 * launcher 0x18011e0: six pushes + sub 0x38;
 * worker   0x1865530: six pushes + sub 0x108;
 * consumer 0x17eeb20: six pushes + sub 0x28.
 * Dynamic alignment below also accepts the other possible RSP alignment.
 * FXSAVE64 preserves x87, MXCSR and XMM0..15. These native functions have
 * no live YMM/ZMM state; dispatchers must be built without AVX/AVX2/AVX512.
 * The native non-leaf frames have no live data in the SysV red zone.
 */
.text
.macro PLE0172_NATIVE_SEAM name, dispatcher
.p2align 4
.globl \name
.hidden \name
.type \name,@function
\name:
    pushfq
    pushq %r15
    pushq %r14
    pushq %r13
    pushq %r12
    pushq %r11
    pushq %r10
    pushq %r9
    pushq %r8
    pushq %rbp
    pushq %rdi
    pushq %rsi
    pushq %rdx
    pushq %rcx
    pushq %rbx
    pushq %rax
    /* r12 now points to the 120-byte mutable GPR block. RFLAGS follows it;
     * the unmodified native RSP is block + 128, independent of alignment.
     */
    movq %rsp, %r12
    subq $544, %rsp
    andq $-16, %rsp
    fxsave64 (%rsp)
    movq %r12, 512(%rsp)
    cld
    leaq 128(%r12), %rdi
    movq %r12, %rsi
    call \dispatcher
    movq %rax, 520(%rsp)
    fxrstor64 (%rsp)
    movq 512(%rsp), %r12
    movq 520(%rsp), %rax
    /* Keep the destination below the GPR block so JMP can use memory after
     * every GPR, RFLAGS and the original native RSP have been restored.
     */
    movq %rax, -8(%r12)
    movq %r12, %rsp
    popq %rax
    popq %rbx
    popq %rcx
    popq %rdx
    popq %rsi
    popq %rdi
    popq %rbp
    popq %r8
    popq %r9
    popq %r10
    popq %r11
    popq %r12
    popq %r13
    popq %r14
    popq %r15
    popfq
    jmp *-136(%rsp)
.size \name,.-\name
.endm

PLE0172_NATIVE_SEAM ple0172_native_launch_seam, ple0172_native_launch_dispatch
PLE0172_NATIVE_SEAM ple0172_native_copy_seam, ple0172_native_copy_dispatch
PLE0172_NATIVE_SEAM ple0172_native_complete_seam, ple0172_native_complete_dispatch
PLE0172_NATIVE_SEAM ple0172_native_consumer_seam, ple0172_native_consumer_dispatch
.section .note.GNU-stack,"",@progbits
