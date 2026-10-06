#include "native_frame_relay.h"

#if !defined(__linux__) || !defined(__x86_64__)
#error "real register harness requires Linux x86-64 SysV GNU assembly"
#endif

    .text
    .hidden halogen_nohit_native_frame_relay
    .hidden halogen_nohit_relay_configuration
    .hidden halogen_probe_before_xsave
    .hidden halogen_probe_after_xsave
    .hidden halogen_probe_caller_xsave
    .hidden halogen_probe_init_xsave
    .hidden halogen_probe_before_registers
    .hidden halogen_probe_after_registers
    .hidden halogen_probe_observer_registers
    .hidden halogen_probe_register_pattern
    .hidden halogen_probe_red_zone_after
    .hidden halogen_probe_observer_count
    .hidden halogen_probe_noninit

    // Independent RIP-relative raw snapshot: stores do not clobber registers or
    // flags. Only the PUSHFQ extraction moves RSP, below a protected red zone.
    .macro raw_snapshot destination
    movq %rax,\destination+0(%rip)
    movq %rbx,\destination+8(%rip)
    movq %rcx,\destination+16(%rip)
    movq %rdx,\destination+24(%rip)
    movq %rsi,\destination+32(%rip)
    movq %rdi,\destination+40(%rip)
    movq %rbp,\destination+48(%rip)
    movq %rsp,\destination+56(%rip)
    movq %r8,\destination+64(%rip)
    movq %r9,\destination+72(%rip)
    movq %r10,\destination+80(%rip)
    movq %r11,\destination+88(%rip)
    movq %r12,\destination+96(%rip)
    movq %r13,\destination+104(%rip)
    movq %r14,\destination+112(%rip)
    movq %r15,\destination+120(%rip)
    leaq -128(%rsp),%rsp
    .cfi_adjust_cfa_offset 128
    pushfq
    .cfi_adjust_cfa_offset 8
    popq \destination+128(%rip)
    .cfi_adjust_cfa_offset -8
    leaq 128(%rsp),%rsp
    .cfi_adjust_cfa_offset -128
    .endm

    .macro set_xmm_pattern
    movdqu .Lseed_vector(%rip),%xmm0
    movdqu .Lseed_vector(%rip),%xmm1
    movdqu .Lseed_vector(%rip),%xmm2
    movdqu .Lseed_vector(%rip),%xmm3
    movdqu .Lseed_vector(%rip),%xmm4
    movdqu .Lseed_vector(%rip),%xmm5
    movdqu .Lseed_vector(%rip),%xmm6
    movdqu .Lseed_vector(%rip),%xmm7
    movdqu .Lseed_vector(%rip),%xmm8
    movdqu .Lseed_vector(%rip),%xmm9
    movdqu .Lseed_vector(%rip),%xmm10
    movdqu .Lseed_vector(%rip),%xmm11
    movdqu .Lseed_vector(%rip),%xmm12
    movdqu .Lseed_vector(%rip),%xmm13
    movdqu .Lseed_vector(%rip),%xmm14
    movdqu .Lseed_vector(%rip),%xmm15
    .endm
    .macro set_ymm_pattern source
    vmovdqu \source(%rip),%ymm0
    vmovdqu \source(%rip),%ymm1
    vmovdqu \source(%rip),%ymm2
    vmovdqu \source(%rip),%ymm3
    vmovdqu \source(%rip),%ymm4
    vmovdqu \source(%rip),%ymm5
    vmovdqu \source(%rip),%ymm6
    vmovdqu \source(%rip),%ymm7
    vmovdqu \source(%rip),%ymm8
    vmovdqu \source(%rip),%ymm9
    vmovdqu \source(%rip),%ymm10
    vmovdqu \source(%rip),%ymm11
    vmovdqu \source(%rip),%ymm12
    vmovdqu \source(%rip),%ymm13
    vmovdqu \source(%rip),%ymm14
    vmovdqu \source(%rip),%ymm15
    .endm

    .p2align 4
    .globl halogen_nohit_mock_handler
    .hidden halogen_nohit_mock_handler
    .type halogen_nohit_mock_handler,@function
halogen_nohit_mock_handler:
    .cfi_startproc
    endbr64
    // Exact retained native six-save/0x2648 body shape, entered by genuine CALL.
    pushq %rbp
    .cfi_def_cfa_offset 16
    .cfi_offset %rbp,-16
    pushq %r15
    .cfi_def_cfa_offset 24
    .cfi_offset %r15,-24
    pushq %r14
    .cfi_def_cfa_offset 32
    .cfi_offset %r14,-32
    pushq %r13
    .cfi_def_cfa_offset 40
    .cfi_offset %r13,-40
    pushq %r12
    .cfi_def_cfa_offset 48
    .cfi_offset %r12,-48
    pushq %rbx
    .cfi_def_cfa_offset 56
    .cfi_offset %rbx,-56
    leaq -0x2648(%rsp),%rsp
    .cfi_def_cfa_offset HGN_RELAY_NATIVE_CFA

    movq halogen_nohit_relay_configuration+HGN_RELAY_CFG_XCR0(%rip),%rax
    movq %rax,%rdx
    shrq $32,%rdx
    xsave64 halogen_probe_caller_xsave(%rip)
    xrstor64 halogen_probe_init_xsave(%rip) // Actual architectural init state, BV0.
    cmpl $0,halogen_probe_noninit(%rip)
    je .Lseed_complete
    fld1
    fldpi
    set_xmm_pattern
    testq $4,halogen_nohit_relay_configuration+HGN_RELAY_CFG_XCR0(%rip)
    jz .Lseed_complete
    set_ymm_pattern .Lseed_vector
.Lseed_complete:
    movq halogen_nohit_relay_configuration+HGN_RELAY_CFG_XCR0(%rip),%rax
    movq %rax,%rdx
    shrq $32,%rdx
    xsave64 halogen_probe_before_xsave(%rip)
    cld
    leaq -128(%rsp),%rdi
    movl $16,%ecx
    movabsq $0x1122334455667788,%rax
    rep stosq
    movq halogen_probe_register_pattern+0(%rip),%rax
    movq halogen_probe_register_pattern+8(%rip),%rbx
    movq halogen_probe_register_pattern+16(%rip),%rcx
    movq halogen_probe_register_pattern+24(%rip),%rdx
    movq halogen_probe_register_pattern+32(%rip),%rsi
    movq halogen_probe_register_pattern+40(%rip),%rdi
    movq halogen_probe_register_pattern+48(%rip),%rbp
    movq halogen_probe_register_pattern+64(%rip),%r8
    movq halogen_probe_register_pattern+72(%rip),%r9
    movq halogen_probe_register_pattern+80(%rip),%r10
    movq halogen_probe_register_pattern+88(%rip),%r11
    movq halogen_probe_register_pattern+96(%rip),%r12
    movq halogen_probe_register_pattern+104(%rip),%r13
    movq halogen_probe_register_pattern+112(%rip),%r14
    movq halogen_probe_register_pattern+120(%rip),%r15
    // Protected PUSH/POPFQ seeds ordinary arithmetic+DF state, excluding TF/RF.
    leaq -128(%rsp),%rsp
    .cfi_adjust_cfa_offset 128
    pushq $0xcd7
    .cfi_adjust_cfa_offset 8
    popfq
    .cfi_adjust_cfa_offset -8
    leaq 128(%rsp),%rsp
    .cfi_adjust_cfa_offset -128
    raw_snapshot halogen_probe_before_registers
    jmp halogen_nohit_native_frame_relay

    .globl halogen_nohit_native_stock_resume
    .hidden halogen_nohit_native_stock_resume
halogen_nohit_native_stock_resume:
    // Direct target inside mock native handler. No fabricated return address.
    raw_snapshot halogen_probe_after_registers
    movq halogen_nohit_relay_configuration+HGN_RELAY_CFG_XCR0(%rip),%rax
    movq %rax,%rdx
    shrq $32,%rdx
    xsave64 halogen_probe_after_xsave(%rip)
    cld
    leaq -128(%rsp),%rsi
    leaq halogen_probe_red_zone_after(%rip),%rdi
    movl $16,%ecx
    rep movsq
    // Return the normal caller's architectural xstate and ABI callee registers.
    movq halogen_nohit_relay_configuration+HGN_RELAY_CFG_XCR0(%rip),%rax
    movq %rax,%rdx
    shrq $32,%rdx
    xrstor64 halogen_probe_caller_xsave(%rip)
    leaq 0x2648(%rsp),%rsp
    .cfi_def_cfa_offset 56
    popq %rbx
    .cfi_def_cfa_offset 48
    .cfi_restore %rbx
    popq %r12
    .cfi_def_cfa_offset 40
    .cfi_restore %r12
    popq %r13
    .cfi_def_cfa_offset 32
    .cfi_restore %r13
    popq %r14
    .cfi_def_cfa_offset 24
    .cfi_restore %r14
    popq %r15
    .cfi_def_cfa_offset 16
    .cfi_restore %r15
    popq %rbp
    .cfi_def_cfa_offset 8
    .cfi_restore %rbp
    ret
    .cfi_endproc
    .size halogen_nohit_mock_handler,.-halogen_nohit_mock_handler

    .p2align 4
    .globl halogen_nohit_frame_observer
    .hidden halogen_nohit_frame_observer
    .type halogen_nohit_frame_observer,@function
halogen_nohit_frame_observer:
    .cfi_startproc
    endbr64
    // Leaf real callback, no runtime/libc/syscall. Preserve SysV callee registers.
    incq halogen_probe_observer_count(%rip)
    movq 0(%rdi),%rsi
    leaq halogen_probe_observer_registers(%rip),%rdi
    movl $17,%ecx
    cld
    rep movsq
    fninit
    fld1
    testq $4,halogen_nohit_relay_configuration+HGN_RELAY_CFG_XCR0(%rip)
    jz .Lobserver_sse
    set_ymm_pattern .Lobserver_vector
    jmp .Lobserver_registers
.Lobserver_sse:
    pcmpeqd %xmm0,%xmm0
    pcmpeqd %xmm1,%xmm1
    pcmpeqd %xmm2,%xmm2
    pcmpeqd %xmm3,%xmm3
    pcmpeqd %xmm4,%xmm4
    pcmpeqd %xmm5,%xmm5
    pcmpeqd %xmm6,%xmm6
    pcmpeqd %xmm7,%xmm7
    pcmpeqd %xmm8,%xmm8
    pcmpeqd %xmm9,%xmm9
    pcmpeqd %xmm10,%xmm10
    pcmpeqd %xmm11,%xmm11
    pcmpeqd %xmm12,%xmm12
    pcmpeqd %xmm13,%xmm13
    pcmpeqd %xmm14,%xmm14
    pcmpeqd %xmm15,%xmm15
.Lobserver_registers:
    xorl %eax,%eax
    movl $0x1111,%ecx
    movl $0x2222,%edx
    movl $0x3333,%esi
    movl $0x4444,%edi
    movl $0x5555,%r8d
    movl $0x6666,%r9d
    movl $0x7777,%r10d
    movl $0x8888,%r11d
    cld
    ret
    .cfi_endproc
    .size halogen_nohit_frame_observer,.-halogen_nohit_frame_observer

    .section .rodata
    .p2align 5
.Lseed_vector:
    .quad 0x0102030405060708,0x1122334455667788,0x8877665544332211,0x0807060504030201
.Lobserver_vector:
    .quad 0xf0e0d0c0b0a09080,0x8070605040302010,0x1020304050607080,0x8090a0b0c0d0e0f0
    .section .note.GNU-stack,"",@progbits
