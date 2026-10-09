#include "retained_relay.h"
    .section .hgnmock,"xr"
    .p2align 4
    .globl hgn_dflash_templates_begin
hgn_dflash_templates_begin:

    .macro HGN_DFLASH_RESTORE native_cfa
    movq %rbp,%rsp
    popq %rax
    popq %rbx
    popq %rcx
    popq %rdx
    popq %rsi
    popq %rdi
    popq %rbp
    leaq 8(%rsp),%rsp
    popq %r8
    popq %r9
    popq %r10
    popq %r11
    popq %r12
    popq %r13
    popq %r14
    popq %r15
    popfq
    leaq HGN_DFLASH_RED_ZONE(%rsp),%rsp
    .endm

    .macro HGN_DFLASH_EXIT n,name
    .byte 0xe9
    .globl hgn_dflash_relay_\n\()_\name\()_delta
hgn_dflash_relay_\n\()_\name\()_delta:
    .long HGN_DFLASH_REL32_SENTINEL
    .endm

    .macro HGN_DFLASH_SITE n,native_cfa
    .p2align 4
    .globl hgn_dflash_relay_\n\()_begin
hgn_dflash_relay_\n\()_begin:
    .if \n == 1
    .else
    .endif
    endbr64
    leaq -HGN_DFLASH_RED_ZONE(%rsp),%rsp
    pushfq
    pushq %r15
    pushq %r14
    pushq %r13
    pushq %r12
    pushq %r11
    pushq %r10
    pushq %r9
    pushq %r8
    leaq -8(%rsp),%rsp
    pushq %rbp
    pushq %rdi
    pushq %rsi
    pushq %rdx
    pushq %rcx
    pushq %rbx
    pushq %rax
    leaq HGN_DFLASH_CAPTURE_RESERVE(%rsp),%rax
    movq %rax,56(%rsp)
    movq %rsp,%rbp
    leaq -HGN_DFLASH_INVOCATION_RESERVE(%rsp),%rsp
    movq $0,-16(%rbp)             // Invocation.action = Stock.

    .globl hgn_dflash_relay_\n\()_mandatory_gate
hgn_dflash_relay_\n\()_mandatory_gate:
    // Mandatory integer gate precedes ALL callback/enabled/TLS/XSAVE checks.
    movq hgn_dflash_relay_\n\()_config+HGN_DFLASH_CFG_LANE(%rip),%r10
    testq %r10,%r10
    je .Ldispatch_\n
    cmpl $1,HGN_DFLASH_LANE_CONFIGURED(%r10)
    jne .Ldispatch_\n
    .if \n == 2
    movq 56(%rbp),%r11
    movq 8(%r11),%r11             // Aggregate at original RSP+8.
    testq %r11,%r11
    je .Ldispatch_\n
    cmpq $0,8(%r11)              // Actual null-cache branch predicate.
    jne .Ldispatch_\n
    movq (%r11),%r11
    testq %r11,%r11
    je .Ldispatch_\n
    cmpq HGN_DFLASH_LANE_MODEL(%r10),%r11
    jne .Ldispatch_\n
    movl 0xc8(%r11),%eax
    cmpl HGN_DFLASH_LANE_SLOT(%r10),%eax
    jne .Ldispatch_\n
    cmpl $0,0x2e8(%r11)
    jne .Ldispatch_\n
    cmpl $0,0x18(%r11)
    jne .Ldispatch_\n
    cmpl $-1,0x40(%r11)
    jne .Ldispatch_\n
    cmpl $-1,0x48(%r11)
    jne .Ldispatch_\n
    cmpl $-1,0x58(%r11)
    jne .Ldispatch_\n
    xorl %eax,%eax
    movl $1,%ecx
    lock cmpxchgl %ecx,HGN_DFLASH_LANE_LOCK(%r10)
    jne .Ldispatch_\n             // Busy retains quarantine; no callback.
    movl $0,HGN_DFLASH_LANE_READY_ENABLED(%r10)
    cmpl $1,HGN_DFLASH_LANE_PHASE(%r10)
    je .Lfresh_pending_\n
    cmpl $0,HGN_DFLASH_LANE_PHASE(%r10)
    je .Lreset_unlock_\n
    cmpq $-1,HGN_DFLASH_LANE_GENERATION(%r10)
    je .Lreset_unlock_\n
    lock incq HGN_DFLASH_LANE_GENERATION(%r10)
    movq $0,HGN_DFLASH_LANE_REQUEST(%r10)
    movq $0,HGN_DFLASH_LANE_BIRTH(%r10)
    movq $0,HGN_DFLASH_LANE_ROUND(%r10)
    movl $0,HGN_DFLASH_LANE_PHASE(%r10)
    jmp .Lreset_unlock_\n
.Lfresh_pending_\n:
    movq HGN_DFLASH_LANE_GENERATION(%r10),%rax
    movq %rax,HGN_DFLASH_LANE_FRESH_RESET(%r10)
.Lreset_unlock_\n:
    movl $0,HGN_DFLASH_LANE_LOCK(%r10)
    .elseif (\n == 3) || (\n == 4)
    cmpl $0,HGN_DFLASH_LANE_PHASE(%r10)
    je .Ldispatch_\n
    .if \n == 3
    movq 16(%rbp),%rax            // Initial SETE common join: Model = RCX.
    .else
    movq 0(%rbp),%rax             // Chunk SETE common join: Model = RAX.
    .endif
    testq %rax,%rax
    je .Ldispatch_\n
    cmpq HGN_DFLASH_LANE_MODEL(%r10),%rax
    jne .Ldispatch_\n
    movl 0xc8(%rax),%ecx
    cmpl HGN_DFLASH_LANE_SLOT(%r10),%ecx
    jne .Ldispatch_\n
    movb $0,0xb7d(%rax)
    movl $-1,0x40(%rax)
    .else
    cmpl $0,HGN_DFLASH_LANE_PHASE(%r10)
    je .Ldispatch_\n
    .if \n == 0
    movq 32(%rbp),%r11            // Entry Request = saved RSI.
    .else
    movq 8(%rbp),%r11             // Preparation Request = saved RBX.
    .endif
    testq %r11,%r11
    je .Ldispatch_\n
    movq 0x108(%r11),%rax
    testq %rax,%rax
    je .Ldispatch_\n
    cmpq HGN_DFLASH_LANE_MODEL(%r10),%rax
    jne .Ldispatch_\n
    .if \n == 0
    cmpq 40(%rbp),%rax            // Saved native RDI must match Model.
    jne .Ldispatch_\n
    .endif
    movl 0xc8(%rax),%ecx
    cmpl HGN_DFLASH_LANE_SLOT(%r10),%ecx
    jne .Ldispatch_\n
    movl $0x7fffffff,0x224(%r11)
    movb $0,0xb7d(%rax)
    movl $-1,0x40(%rax)
    .if \n == 0
    movq $1,-16(%rbp)             // Retained slot defaults to Scalar.
    movq HGN_DFLASH_LANE_ROUND(%r10),%rax
    cmpq $-1,%rax
    je .Lmandatory_loss_\n
    leaq 1(%rax),%rcx
    lock cmpxchgq %rcx,HGN_DFLASH_LANE_ROUND(%r10)
    jne .Lmandatory_loss_\n
    jmp .Ldispatch_\n
.Lmandatory_loss_\n:
    lock incq HGN_DFLASH_LANE_LOSS(%r10)
    movl $0,HGN_DFLASH_LANE_READY_ENABLED(%r10)
    .else
    movb $1,24(%rbp)              // Force saved DL, preserve remaining RDX.
    .endif
    .endif

.Ldispatch_\n:
    .if \n == 0
    .globl hgn_dflash_relay_0_optional_begin
hgn_dflash_relay_0_optional_begin:
    // Only Entry can promote Scalar to Ready. Prepare/PostReset never call C.
    cmpq $1,-16(%rbp)
    jne .Lchoose_\n
    cmpl $1,hgn_dflash_relay_\n\()_config+HGN_DFLASH_CFG_ENABLED(%rip)
    jne .Lchoose_\n
    movq hgn_dflash_relay_\n\()_config+HGN_DFLASH_CFG_RUNTIME_ENABLED(%rip),%r10
    testq %r10,%r10
    je .Lchoose_\n
    cmpb $1,(%r10)
    jne .Lchoose_\n
    movq hgn_dflash_relay_\n\()_config+HGN_DFLASH_CFG_IN_FLIGHT(%rip),%r11
    lock incq (%r11)
    cmpb $1,(%r10)
    jne .Lactive_restore_\n
    movq hgn_dflash_relay_\n\()_config+HGN_DFLASH_CFG_STACK_TLS_OFFSET(%rip),%r10
    movq %gs:HGN_DFLASH_TLS_STACK_LOW(%r10),%r11
    movq %gs:HGN_DFLASH_TLS_STACK_HIGH(%r10),%rcx
    movq 56(%rbp),%rax
    testq %r11,%r11
    je .Lloss_\n
    cmpq %r11,%rcx
    jbe .Lloss_\n
    cmpq %rcx,%rax
    jae .Lloss_\n
    subq %r11,%rax
    jb .Lloss_\n
    cmpq hgn_dflash_relay_\n\()_config+HGN_DFLASH_CFG_REQUIRED_STACK(%rip),%rax
    jb .Lloss_\n
    movl hgn_dflash_relay_\n\()_config+HGN_DFLASH_CFG_XSAVE_BYTES(%rip),%ecx
    leaq HGN_DFLASH_XSAVE_PAD(%rcx),%rax
    movq %rbp,%rsp
    subq %rax,%rsp
    andq $-64,%rsp
    movq %rsp,-8(%rbp)
    cld
    movq %rsp,%rdi
    xorl %eax,%eax
    rep stosb
    movq hgn_dflash_relay_\n\()_config+HGN_DFLASH_CFG_XCR0(%rip),%rax
    movq %rax,%rdx
    shrq $32,%rdx
    xsave64 (%rsp)
    fninit
    ldmxcsr .Lmxcsr_\n(%rip)
    xorl %edi,%edi
    movq %rbp,%rsi
    leaq -16(%rbp),%rdx
    movq hgn_dflash_relay_\n\()_config+HGN_DFLASH_CFG_LANE(%rip),%rcx
    movq hgn_dflash_relay_\n\()_config+HGN_DFLASH_CFG_PROVIDER(%rip),%r8
    call *hgn_dflash_relay_\n\()_config+HGN_DFLASH_CFG_CALLBACK(%rip)
    movq -8(%rbp),%rdi
    movq hgn_dflash_relay_\n\()_config+HGN_DFLASH_CFG_XCR0(%rip),%rax
    movq %rax,%rdx
    shrq $32,%rdx
    xrstor64 (%rdi)
    jmp .Lactive_restore_\n
.Lloss_\n:
    movq hgn_dflash_relay_\n\()_config+HGN_DFLASH_CFG_LOSS_COUNTER(%rip),%r11
    lock incq (%r11)
    movq hgn_dflash_relay_\n\()_config+HGN_DFLASH_CFG_LANE(%rip),%r10
    movl $0,HGN_DFLASH_LANE_READY_ENABLED(%r10)
.Lactive_restore_\n:
    movq hgn_dflash_relay_\n\()_config+HGN_DFLASH_CFG_IN_FLIGHT(%rip),%r11
    lock decq (%r11)
    .endif
.Lchoose_\n:
    .if \n == 0
    cmpq $2,-16(%rbp)
    je .Lready_\n
    cmpq $1,-16(%rbp)
    je .Lscalar_\n
    .endif
    HGN_DFLASH_RESTORE \native_cfa
    .if \n == 0
    cmpl $0,0x11c(%rsi)           // Exact displaced CMP. Resume native JLE.
    .elseif \n == 1
    movq 0x108(%rbx),%rdi
    .elseif \n == 2
    movq 8(%rsp),%rax
    .elseif \n == 3
    movq 0x180(%rax),%rsi
    .else
    leaq 0x328(%r14),%rax
    .endif
    HGN_DFLASH_EXIT \n,stock
    .if \n == 0
.Lready_\n:
    HGN_DFLASH_RESTORE \native_cfa
    HGN_DFLASH_EXIT \n,ready
.Lscalar_\n:
    HGN_DFLASH_RESTORE \native_cfa
    HGN_DFLASH_EXIT \n,scalar
    .endif
    .globl hgn_dflash_relay_\n\()_code_end
hgn_dflash_relay_\n\()_code_end:
    .balign 8
    .globl hgn_dflash_relay_\n\()_config
hgn_dflash_relay_\n\()_config:
    .long 0,0
    .quad 0,0,0,0,0,0,0,0,0       // Entire template configuration is inert.
.Lmxcsr_\n:
    .long 0x1f80
    .balign 8
    .globl hgn_dflash_relay_\n\()_end
hgn_dflash_relay_\n\()_end:
    .endm
    HGN_DFLASH_SITE 0,HGN_DFLASH_HANDLER_CFA
    HGN_DFLASH_SITE 1,HGN_DFLASH_PREPARE_CFA
    HGN_DFLASH_SITE 2,HGN_DFLASH_HANDLER_CFA
    HGN_DFLASH_SITE 3,HGN_DFLASH_HANDLER_CFA
    HGN_DFLASH_SITE 4,HGN_DFLASH_CHUNK_CFA
    .globl hgn_dflash_templates_end
hgn_dflash_templates_end:
