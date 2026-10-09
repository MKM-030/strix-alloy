#include "shadow_relay.h"
#if !defined(__linux__) || !defined(__x86_64__)
#error "CPU relay qualifier requires Linux x86-64 SysV GNU assembly"
#endif
    .text
    .hidden hgn_probe_before_xsave,hgn_probe_after_xsave,hgn_probe_caller_xsave
    .hidden hgn_probe_seed_xsave,hgn_probe_poison_xsave,hgn_probe_poison_snapshot
    .hidden hgn_probe_before,hgn_probe_after,hgn_probe_patterns,hgn_probe_red_zone
    .hidden hgn_probe_mask,hgn_probe_target,hgn_probe_branch

    // Independent flag-neutral raw snapshot. Before CALL, expected entry RSP
    // is caller RSP-8. Flag extraction stays below that future entry's red zone.
    .macro SNAPSHOT dest, future_call
    movq %rax,\dest+0(%rip)
    movq %rbx,\dest+8(%rip)
    movq %rcx,\dest+16(%rip)
    movq %rdx,\dest+24(%rip)
    movq %rsi,\dest+32(%rip)
    movq %rdi,\dest+40(%rip)
    movq %rbp,\dest+48(%rip)
    movq %rsp,\dest+56(%rip)
    movq %r8,\dest+64(%rip)
    movq %r9,\dest+72(%rip)
    movq %r10,\dest+80(%rip)
    movq %r11,\dest+88(%rip)
    movq %r12,\dest+96(%rip)
    movq %r13,\dest+104(%rip)
    movq %r14,\dest+112(%rip)
    movq %r15,\dest+120(%rip)
    .if \future_call
    leaq -8(%rsp),%rax
    movq %rax,\dest+56(%rip)
    movq \dest+0(%rip),%rax
    .endif
    leaq -(128+8*\future_call)(%rsp),%rsp
    .cfi_adjust_cfa_offset (128+8*\future_call)
    pushfq
    .cfi_adjust_cfa_offset 8
    popq \dest+128(%rip)
    .cfi_adjust_cfa_offset -8
    leaq (128+8*\future_call)(%rsp),%rsp
    .cfi_adjust_cfa_offset -(128+8*\future_call)
    .endm

    .p2align 4
    .globl hgn_shadow_probe_run
    .hidden hgn_shadow_probe_run
    .type hgn_shadow_probe_run,@function
hgn_shadow_probe_run:
    .cfi_startproc
    endbr64
    pushq %rbp
    .cfi_adjust_cfa_offset 8
    .cfi_offset %rbp,-16
    pushq %r15
    .cfi_adjust_cfa_offset 8
    .cfi_offset %r15,-24
    pushq %r14
    .cfi_adjust_cfa_offset 8
    .cfi_offset %r14,-32
    pushq %r13
    .cfi_adjust_cfa_offset 8
    .cfi_offset %r13,-40
    pushq %r12
    .cfi_adjust_cfa_offset 8
    .cfi_offset %r12,-48
    pushq %rbx
    .cfi_adjust_cfa_offset 8
    .cfi_offset %rbx,-56
    leaq -8(%rsp),%rsp
    .cfi_adjust_cfa_offset 8         // 16-aligned before the genuine CALL.
    movq hgn_probe_mask(%rip),%rax
    movq %rax,%rdx
    shrq $32,%rdx
    xsave64 hgn_probe_caller_xsave(%rip)
    xrstor64 hgn_probe_seed_xsave(%rip)
    xsave64 hgn_probe_before_xsave(%rip)
    cld
    leaq -136(%rsp),%rdi            // Future entry S=P-8; its red zone S-128..S-1.
    movl $16,%ecx
    movabsq $0x1122334455667788,%rax
    rep stosq
    movq hgn_probe_patterns+0(%rip),%rax
    movq hgn_probe_patterns+8(%rip),%rbx
    movq hgn_probe_patterns+16(%rip),%rcx
    movq hgn_probe_patterns+24(%rip),%rdx
    movq hgn_probe_patterns+32(%rip),%rsi
    movq hgn_probe_patterns+40(%rip),%rdi
    movq hgn_probe_patterns+48(%rip),%rbp
    movq hgn_probe_patterns+64(%rip),%r8
    movq hgn_probe_patterns+72(%rip),%r9
    movq hgn_probe_patterns+80(%rip),%r10
    movq hgn_probe_patterns+88(%rip),%r11
    movq hgn_probe_patterns+96(%rip),%r12
    movq hgn_probe_patterns+104(%rip),%r13
    movq hgn_probe_patterns+112(%rip),%r14
    movq hgn_probe_patterns+120(%rip),%r15
    leaq -136(%rsp),%rsp
    .cfi_adjust_cfa_offset 136
    pushq $0xcd7
    .cfi_adjust_cfa_offset 8
    popfq
    .cfi_adjust_cfa_offset -8
    leaq 136(%rsp),%rsp
    .cfi_adjust_cfa_offset -136
    SNAPSHOT hgn_probe_before,1
    call *hgn_probe_target(%rip)     // Real RA and balanced shadow-stack entry.
    cld
    movq hgn_probe_mask(%rip),%rax
    movq %rax,%rdx
    shrq $32,%rdx
    xrstor64 hgn_probe_caller_xsave(%rip)
    leaq 8(%rsp),%rsp
    .cfi_adjust_cfa_offset -8
    popq %rbx
    .cfi_adjust_cfa_offset -8
    .cfi_restore %rbx
    popq %r12
    .cfi_adjust_cfa_offset -8
    .cfi_restore %r12
    popq %r13
    .cfi_adjust_cfa_offset -8
    .cfi_restore %r13
    popq %r14
    .cfi_adjust_cfa_offset -8
    .cfi_restore %r14
    popq %r15
    .cfi_adjust_cfa_offset -8
    .cfi_restore %r15
    popq %rbp
    .cfi_adjust_cfa_offset -8
    .cfi_restore %rbp
    ret
    .cfi_endproc
    .size hgn_shadow_probe_run,.-hgn_shadow_probe_run

    .p2align 4
    .globl hgn_shadow_probe_stock
    .hidden hgn_shadow_probe_stock
    .type hgn_shadow_probe_stock,@function
hgn_shadow_probe_stock:
    .cfi_startproc
    endbr64
    cmpl $0,0x48(%rdi)
    je hgn_shadow_probe_taken
    jmp hgn_shadow_probe_fallthrough
    .cfi_endproc
    .size hgn_shadow_probe_stock,.-hgn_shadow_probe_stock

    .macro STOCK_EXIT name, which
    .p2align 4
    .globl \name
    .hidden \name
    .type \name,@function
\name:
    .cfi_startproc
    endbr64
    movl $\which,hgn_probe_branch(%rip) // MOV preserves the stock CMP flags.
    SNAPSHOT hgn_probe_after,0
    movq hgn_probe_mask(%rip),%rax
    movq %rax,%rdx
    shrq $32,%rdx
    xsave64 hgn_probe_after_xsave(%rip)
    cld
    leaq -128(%rsp),%rsi
    leaq hgn_probe_red_zone(%rip),%rdi
    movl $16,%ecx
    rep movsq
    ret                            // Returns the genuine entry CALL, no fake RA.
    .cfi_endproc
    .size \name,.-\name
    .endm
    STOCK_EXIT hgn_shadow_probe_taken,1
    STOCK_EXIT hgn_shadow_probe_fallthrough,0

    .p2align 4
    .globl hgn_shadow_probe_poison
    .hidden hgn_shadow_probe_poison
    .type hgn_shadow_probe_poison,@function
hgn_shadow_probe_poison:
    .cfi_startproc
    endbr64
    pushq %rbp
    .cfi_adjust_cfa_offset 8
    .cfi_offset %rbp,-16
    pushq %rbx
    .cfi_adjust_cfa_offset 8
    .cfi_offset %rbx,-24
    pushq %r12
    .cfi_adjust_cfa_offset 8
    .cfi_offset %r12,-32
    pushq %r13
    .cfi_adjust_cfa_offset 8
    .cfi_offset %r13,-40
    pushq %r14
    .cfi_adjust_cfa_offset 8
    .cfi_offset %r14,-48
    pushq %r15
    .cfi_adjust_cfa_offset 8
    .cfi_offset %r15,-56
    movq hgn_probe_mask(%rip),%rax
    movq %rax,%rdx
    shrq $32,%rdx
    xrstor64 hgn_probe_poison_xsave(%rip) // Every admitted xstate component.
    xsave64 hgn_probe_poison_snapshot(%rip)
    movl $0x0101,%eax
    movl $0x0202,%ebx
    movl $0x0303,%ecx
    movl $0x0404,%edx
    movl $0x0505,%esi
    movl $0x0606,%edi
    movl $0x0707,%ebp
    movl $0x0808,%r8d
    movl $0x0909,%r9d
    movl $0x1010,%r10d
    movl $0x1111,%r11d
    movl $0x1212,%r12d
    movl $0x1313,%r13d
    movl $0x1414,%r14d
    movl $0x1515,%r15d
    pushq $2                       // Ordinary arithmetic flags differ; DF stays0.
    .cfi_adjust_cfa_offset 8
    popfq
    .cfi_adjust_cfa_offset -8
    popq %r15
    .cfi_adjust_cfa_offset -8
    .cfi_restore %r15
    popq %r14
    .cfi_adjust_cfa_offset -8
    .cfi_restore %r14
    popq %r13
    .cfi_adjust_cfa_offset -8
    .cfi_restore %r13
    popq %r12
    .cfi_adjust_cfa_offset -8
    .cfi_restore %r12
    popq %rbx
    .cfi_adjust_cfa_offset -8
    .cfi_restore %rbx
    popq %rbp
    .cfi_adjust_cfa_offset -8
    .cfi_restore %rbp
    ret
    .cfi_endproc
    .size hgn_shadow_probe_poison,.-hgn_shadow_probe_poison
    .section .note.GNU-stack,"",@progbits
