#include "native_frame_relay.h"

#if !defined(__linux__) || !defined(__x86_64__)
#error "native frame relay requires Linux x86-64 SysV GNU assembly"
#endif

    .text
    .p2align 4
    .globl halogen_nohit_native_frame_relay
    .hidden halogen_nohit_native_frame_relay
    .hidden halogen_nohit_relay_configuration
    .hidden halogen_nohit_frame_observer
    .hidden halogen_nohit_native_stock_resume
    .type halogen_nohit_native_frame_relay,@function
halogen_nohit_native_frame_relay:
    .cfi_startproc simple
    // JMP from the pinned decoder body, not SysV function entry. Native caller
    // rules remain in its original stack throughout; captured live RBP=request.
    .cfi_def_cfa %rsp,HGN_RELAY_NATIVE_CFA
    .cfi_offset %rip,-8
    .cfi_offset %rbp,-16
    .cfi_offset %r15,-24
    .cfi_offset %r14,-32
    .cfi_offset %r13,-40
    .cfi_offset %r12,-48
    .cfi_offset %rbx,-56
    endbr64

    // First stack movement is flag-neutral and protects all original red-zone
    // bytes. Every original GPR and PUSHFQ image is saved before any clobber.
    leaq -HGN_RELAY_RED_ZONE(%rsp),%rsp
    .cfi_adjust_cfa_offset HGN_RELAY_RED_ZONE
    pushfq
    .cfi_adjust_cfa_offset 8
    pushq %r15
    .cfi_adjust_cfa_offset 8
    pushq %r14
    .cfi_adjust_cfa_offset 8
    pushq %r13
    .cfi_adjust_cfa_offset 8
    pushq %r12
    .cfi_adjust_cfa_offset 8
    pushq %r11
    .cfi_adjust_cfa_offset 8
    pushq %r10
    .cfi_adjust_cfa_offset 8
    pushq %r9
    .cfi_adjust_cfa_offset 8
    pushq %r8
    .cfi_adjust_cfa_offset 8
    leaq -8(%rsp),%rsp              // Original-RSP slot, populated after capture.
    .cfi_adjust_cfa_offset 8
    pushq %rbp
    .cfi_adjust_cfa_offset 8
    pushq %rdi
    .cfi_adjust_cfa_offset 8
    pushq %rsi
    .cfi_adjust_cfa_offset 8
    pushq %rdx
    .cfi_adjust_cfa_offset 8
    pushq %rcx
    .cfi_adjust_cfa_offset 8
    pushq %rbx
    .cfi_adjust_cfa_offset 8
    pushq %rax
    .cfi_adjust_cfa_offset 8

    leaq HGN_RELAY_ENTRY_RESERVE(%rsp),%rax
    movq %rax,56(%rsp)
    movq %rsp,%rbp
    .cfi_def_cfa %rbp,HGN_RELAY_CAPTURE_CFA

    cmpl $1,halogen_nohit_relay_configuration+HGN_RELAY_CFG_ENABLED(%rip)
    jne .Lrestore_integer
    // A nested invocation owns its own stack image. Lower headroom causes a
    // stock bypass before xstate mutation or callback, never scratch reuse.
    cmpq halogen_nohit_relay_configuration+HGN_RELAY_CFG_STACK_HIGH(%rip),%rax
    ja .Lrestore_integer
    movq %rax,%rcx
    subq halogen_nohit_relay_configuration+HGN_RELAY_CFG_STACK_LOW(%rip),%rcx
    jb .Lrestore_integer
    cmpq halogen_nohit_relay_configuration+HGN_RELAY_CFG_REQUIRED_STACK(%rip),%rcx
    jb .Lrestore_integer

    // Dynamic standard XSAVE allocation + metadata gap + alignment slack. No
    // fixed 1024-byte image. Startup bounds size and the whole stack footprint.
    movl halogen_nohit_relay_configuration+HGN_RELAY_CFG_XSAVE_BYTES(%rip),%eax
    leaq HGN_RELAY_ALLOC_PAD(%rax),%rax
    subq %rax,%rsp
    andq $-64,%rsp
    movq %rsp,-56(%rbp)             // NativeFrameView.standard_xsave_area
    movq %rbp,-64(%rbp)             // NativeFrameView.registers
    movq halogen_nohit_relay_configuration+HGN_RELAY_CFG_XCR0(%rip),%rax
    movq %rax,-48(%rbp)             // NativeFrameView.xcr0_mask
    movl halogen_nohit_relay_configuration+HGN_RELAY_CFG_XSAVE_BYTES(%rip),%ecx
    movq %rcx,-40(%rbp)             // NativeFrameView.xsave_bytes
    movq 56(%rbp),%rax
    movq %rax,-32(%rbp)             // NativeFrameView.original_rsp
    movq halogen_nohit_relay_configuration+HGN_RELAY_CFG_SCOPE(%rip),%rax
    movq %rax,-24(%rbp)             // NativeFrameView.scope

    // Initialize the COMPLETE image, including all header/reserved bytes, on
    // this invocation. DF has already been saved; clearing it admits C ABI use.
    cld
    movq %rsp,%rdi
    xorl %eax,%eax
    rep stosb
    movq -48(%rbp),%rax
    movq %rax,%rdx
    shrq $32,%rdx
    xsave64 (%rsp)                 // EDX:EAX = complete enabled XCR0 mask.

    // Establish x87 mode and ordinary masked C floating-point environment only
    // AFTER save. AMD's architectural error-pointer limitations are in admission
    // and FRAME_RELAY.md; this is not a literal physical-x87 metadata promise.
    fninit
    ldmxcsr .Lcallback_mxcsr(%rip)
    leaq -64(%rbp),%rdi
    // RSP is 64-aligned here, hence16-aligned immediately before real CALL.
    // Hidden direct linkage avoids PLT/indirect callback entry and lazy lookup.
    call halogen_nohit_frame_observer

    movq -56(%rbp),%rdi
    movq -48(%rbp),%rax
    movq %rax,%rdx
    shrq $32,%rdx
    xrstor64 (%rdi)                // Fullmask, including XSTATE_BV=0 components.

.Lrestore_integer:
    movq %rbp,%rsp
    .cfi_def_cfa %rsp,HGN_RELAY_CAPTURE_CFA
    popq %rax
    .cfi_adjust_cfa_offset -8
    popq %rbx
    .cfi_adjust_cfa_offset -8
    popq %rcx
    .cfi_adjust_cfa_offset -8
    popq %rdx
    .cfi_adjust_cfa_offset -8
    popq %rsi
    .cfi_adjust_cfa_offset -8
    popq %rdi
    .cfi_adjust_cfa_offset -8
    popq %rbp
    .cfi_adjust_cfa_offset -8
    leaq 8(%rsp),%rsp              // Original-RSP value was observational only.
    .cfi_adjust_cfa_offset -8
    popq %r8
    .cfi_adjust_cfa_offset -8
    popq %r9
    .cfi_adjust_cfa_offset -8
    popq %r10
    .cfi_adjust_cfa_offset -8
    popq %r11
    .cfi_adjust_cfa_offset -8
    popq %r12
    .cfi_adjust_cfa_offset -8
    popq %r13
    .cfi_adjust_cfa_offset -8
    popq %r14
    .cfi_adjust_cfa_offset -8
    popq %r15
    .cfi_adjust_cfa_offset -8
    popfq
    .cfi_adjust_cfa_offset -8
    leaq HGN_RELAY_RED_ZONE(%rsp),%rsp
    .cfi_adjust_cfa_offset -HGN_RELAY_RED_ZONE
    // Sole intended GPR/native-stack mutation: the displaced LEA RAX effect.
    // No RET, fabricated return, flag-changing instruction or indirect native jump.
    leaq 0x1e8(%rbp),%rax
    jmp halogen_nohit_native_stock_resume
    .cfi_endproc
    .size halogen_nohit_native_frame_relay,.-halogen_nohit_native_frame_relay

    .section .rodata
    .p2align 2
.Lcallback_mxcsr:
    .long 0x1f80
    .section .note.GNU-stack,"",@progbits
