#include "shadow_relay.h"

#if !defined(__linux__) || !defined(__x86_64__)
#error "shadow relay requires Linux x86-64 SysV GNU assembly"
#endif

    .cfi_sections .eh_frame
    .section .hgn_shadow_relay_templates,"ax",@progbits
    .p2align 4
    .globl hgn_shadow_templates_begin
    .hidden hgn_shadow_templates_begin
hgn_shadow_templates_begin:

// This macro emits a self-contained PC-relative code/config template. It has
// no external branch or data relocation: the only external transfer is a real
// indirect CALL through immutable config. Runtime native rel32 fields retain
// conspicuous sentinels until the installer patches the copied island.
    .macro HGN_SHADOW_SITE n, native_cfa, entry
    .p2align 4
    .globl hgn_shadow_relay_\n\()_begin
    .hidden hgn_shadow_relay_\n\()_begin
    .type hgn_shadow_relay_\n\()_begin,@function
hgn_shadow_relay_\n\()_begin:
    .cfi_startproc simple
    .cfi_def_cfa %rsp,\native_cfa
    .cfi_offset %rip,-8
    .if \entry
    .cfi_same_value %rbp
    .cfi_same_value %rbx
    .cfi_same_value %r12
    .cfi_same_value %r13
    .cfi_same_value %r14
    .cfi_same_value %r15
    .else
    // Native handler caller values reside in its existing 0x1a40 frame.
    // Captured live RBP/RBX/etc are not substitutes for these caller values.
    .cfi_offset %rbp,-16
    .cfi_offset %r15,-24
    .cfi_offset %r14,-32
    .cfi_offset %r13,-40
    .cfi_offset %r12,-48
    .cfi_offset %rbx,-56
    .endif
    endbr64

    // Flag-neutral first movement protects the complete native red zone.
    // Capture every integer register and ordinary flags before any scratch use.
    leaq -HGN_SHADOW_RED_ZONE(%rsp),%rsp
    .cfi_adjust_cfa_offset HGN_SHADOW_RED_ZONE
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
    leaq -8(%rsp),%rsp
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
    leaq HGN_SHADOW_CAPTURE_RESERVE(%rsp),%rax
    movq %rax,56(%rsp)             // Frame.gpr[7] = original native RSP.
    movq %rsp,%rbp
    .cfi_def_cfa %rbp,(\native_cfa + HGN_SHADOW_CAPTURE_RESERVE)
    .if \entry
    // At function entry captured callee-save values ARE caller values. RBP is
    // now the image base, so same-value RBP would be wrong while in the relay.
    .cfi_offset %rbx,(8 - (\native_cfa + HGN_SHADOW_CAPTURE_RESERVE))
    .cfi_offset %rbp,(48 - (\native_cfa + HGN_SHADOW_CAPTURE_RESERVE))
    .cfi_offset %r12,(96 - (\native_cfa + HGN_SHADOW_CAPTURE_RESERVE))
    .cfi_offset %r13,(104 - (\native_cfa + HGN_SHADOW_CAPTURE_RESERVE))
    .cfi_offset %r14,(112 - (\native_cfa + HGN_SHADOW_CAPTURE_RESERVE))
    .cfi_offset %r15,(120 - (\native_cfa + HGN_SHADOW_CAPTURE_RESERVE))
    .endif

    cmpl $1,hgn_shadow_relay_\n\()_config+HGN_SHADOW_CFG_ENABLED(%rip)
    jne .Lhgn_restore_\n
    movq hgn_shadow_relay_\n\()_config+HGN_SHADOW_CFG_RUNTIME_ENABLED(%rip),%r10
    cmpb $1,(%r10)
    jne .Lhgn_restore_\n
    // Enter the native-owned close barrier before any observation/loss update.
    // A relay delayed before this increment must recheck disabled afterward.
    movq hgn_shadow_relay_\n\()_config+HGN_SHADOW_CFG_IN_FLIGHT(%rip),%r11
    lock incq (%r11)
    movq hgn_shadow_relay_\n\()_config+HGN_SHADOW_CFG_RUNTIME_ENABLED(%rip),%r10
    cmpb $1,(%r10)
    jne .Lhgn_active_restore_\n
    // No dynamic TLS resolver: installer supplies initial-exec TPOFF for the
    // current thread's already-registered StackBounds. This precedes XSAVE
    // allocation and every xstate mutation or callback.
    movq hgn_shadow_relay_\n\()_config+HGN_SHADOW_CFG_STACK_TLS_OFFSET(%rip),%r10
    movq %fs:HGN_SHADOW_TLS_STACK_LOW(%r10),%r11
    movq %fs:HGN_SHADOW_TLS_STACK_HIGH(%r10),%rcx
    testq %r11,%r11
    je .Lhgn_loss_\n
    cmpq %r11,%rcx
    jbe .Lhgn_loss_\n
    cmpq %rcx,%rax
    jae .Lhgn_loss_\n
    subq %r11,%rax
    jb .Lhgn_loss_\n
    cmpq hgn_shadow_relay_\n\()_config+HGN_SHADOW_CFG_REQUIRED_STACK(%rip),%rax
    jb .Lhgn_loss_\n

    movl hgn_shadow_relay_\n\()_config+HGN_SHADOW_CFG_XSAVE_BYTES(%rip),%ecx
    movq %rcx,%rax
    leaq HGN_SHADOW_XSAVE_PAD(%rax),%rax
    subq %rax,%rsp
    andq $-64,%rsp
    movq %rsp,-8(%rbp)             // Invocation-owned XSAVE-area pointer.
    cld
    movq %rsp,%rdi
    xorl %eax,%eax
    rep stosb                      // All standard XSAVE bytes, header included.
    movq hgn_shadow_relay_\n\()_config+HGN_SHADOW_CFG_XCR0(%rip),%rax
    movq %rax,%rdx
    shrq $32,%rdx
    xsave64 (%rsp)

    // Only after XSAVE may the callback receive an ordinary C FP environment.
    fninit
    ldmxcsr .Lhgn_mxcsr_\n(%rip)
    movl $\n,%edi
    movq %rbp,%rsi
    // RSP is 64-aligned before CALL. The retained target must begin ENDBR64.
    // This CALL and the callback's normal RET preserve shadow-stack balance.
    call *hgn_shadow_relay_\n\()_config+HGN_SHADOW_CFG_CALLBACK(%rip)

    // Callback restored errno before returning. Restore the entire enabled
    // standard XSAVE mask, including components whose XSTATE_BV is zero.
    movq -8(%rbp),%rdi
    movq hgn_shadow_relay_\n\()_config+HGN_SHADOW_CFG_XCR0(%rip),%rax
    movq %rax,%rdx
    shrq $32,%rdx
    xrstor64 (%rdi)
    jmp .Lhgn_active_restore_\n

.Lhgn_loss_\n:
    // A native lifecycle hook bypassed by stack admission is producer loss,
    // not an invisible miss. Stop can race the initial enable read: recheck
    // here so an already-disabled collector does not acquire new loss events.
    // All integer/flag state is saved; this path does not touch xstate or errno.
    movq hgn_shadow_relay_\n\()_config+HGN_SHADOW_CFG_RUNTIME_ENABLED(%rip),%r10
    cmpb $1,(%r10)
    jne .Lhgn_active_restore_\n
    movq hgn_shadow_relay_\n\()_config+HGN_SHADOW_CFG_LOSS_COUNTER(%rip),%r11
    lock incq (%r11)

.Lhgn_active_restore_\n:
    // Every admitted path remains in flight through its final owned update.
    // No callback, TLS admission or loss update occurs after this decrement.
    movq hgn_shadow_relay_\n\()_config+HGN_SHADOW_CFG_IN_FLIGHT(%rip),%r11
    lock decq (%r11)

.Lhgn_restore_\n:
    movq %rbp,%rsp
    .cfi_def_cfa %rsp,(\native_cfa + HGN_SHADOW_CAPTURE_RESERVE)
    popq %rax
    .cfi_adjust_cfa_offset -8
    popq %rbx
    .cfi_adjust_cfa_offset -8
    .if \entry
    .cfi_same_value %rbx
    .endif
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
    .if \entry
    .cfi_same_value %rbp
    .endif
    leaq 8(%rsp),%rsp              // Do not pivot through observational RSP.
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
    .if \entry
    .cfi_same_value %r12
    .endif
    popq %r13
    .cfi_adjust_cfa_offset -8
    .if \entry
    .cfi_same_value %r13
    .endif
    popq %r14
    .cfi_adjust_cfa_offset -8
    .if \entry
    .cfi_same_value %r14
    .endif
    popq %r15
    .cfi_adjust_cfa_offset -8
    .if \entry
    .cfi_same_value %r15
    .endif
    popfq
    .cfi_adjust_cfa_offset -8
    leaq HGN_SHADOW_RED_ZONE(%rsp),%rsp
    .cfi_adjust_cfa_offset -HGN_SHADOW_RED_ZONE

    .globl hgn_shadow_relay_\n\()_replay
    .hidden hgn_shadow_relay_\n\()_replay
hgn_shadow_relay_\n\()_replay:
    // Execute displaced instructions ONLY after original RSP/GPR/flags/xstate
    // restoration. CMP intentionally establishes stock flags before its Jcc.
    .if (\n == 0) || (\n == 1)
    leaq 0x1d0(%rsp),%rdi
    .elseif \n == 2
    movzbl 0x1b0(%r9),%esi
    .elseif \n == 3
    movq 0x10(%rsp),%rax
    .elseif \n == 4
    cmpl $-2,%eax
    .byte 0x0f,0x85                // JNE rel32 -> stock RVA 0x1741270.
    .globl hgn_shadow_relay_4_branch_delta
    .hidden hgn_shadow_relay_4_branch_delta
hgn_shadow_relay_4_branch_delta:
    .long HGN_SHADOW_REL32_SENTINEL
    .elseif \n == 5
    pushq %r15
    .cfi_adjust_cfa_offset 8
    .cfi_offset %r15,-16
    pushq %r14
    .cfi_adjust_cfa_offset 8
    .cfi_offset %r14,-24
    pushq %rbx
    .cfi_adjust_cfa_offset 8
    .cfi_offset %rbx,-32
    .elseif \n == 6
    pushq %rbp
    .cfi_adjust_cfa_offset 8
    .cfi_offset %rbp,-16
    pushq %r15
    .cfi_adjust_cfa_offset 8
    .cfi_offset %r15,-24
    pushq %r14
    .cfi_adjust_cfa_offset 8
    .cfi_offset %r14,-32
    .elseif \n == 7
    pushq %rax
    .cfi_adjust_cfa_offset 8        // Local allocation; no caller-RAX save rule.
    movslq 0xc8(%rdi),%rax
    .elseif \n == 8
    cmpl $0,0x48(%rdi)
    .byte 0x0f,0x84                // JE rel32 -> stock RVA 0x17466be.
    .globl hgn_shadow_relay_8_branch_delta
    .hidden hgn_shadow_relay_8_branch_delta
hgn_shadow_relay_8_branch_delta:
    .long HGN_SHADOW_REL32_SENTINEL
    .else
    .error "unknown shadow relay site"
    .endif
    .fill HGN_SHADOW_REPLAY_BYTES-(.-hgn_shadow_relay_\n\()_replay),1,0x90
    .globl hgn_shadow_relay_\n\()_replay_end
    .hidden hgn_shadow_relay_\n\()_replay_end
    .globl hgn_shadow_relay_\n\()_resume
    .hidden hgn_shadow_relay_\n\()_resume
hgn_shadow_relay_\n\()_replay_end:
hgn_shadow_relay_\n\()_resume:
    .byte 0xe9
    .globl hgn_shadow_relay_\n\()_resume_delta
    .hidden hgn_shadow_relay_\n\()_resume_delta
hgn_shadow_relay_\n\()_resume_delta:
    .long HGN_SHADOW_REL32_SENTINEL
    .globl hgn_shadow_relay_\n\()_code_end
    .hidden hgn_shadow_relay_\n\()_code_end
hgn_shadow_relay_\n\()_code_end:
    .cfi_endproc
    .size hgn_shadow_relay_\n\()_begin,.-hgn_shadow_relay_\n\()_begin
    .balign 8
    .globl hgn_shadow_relay_\n\()_config
    .hidden hgn_shadow_relay_\n\()_config
    .type hgn_shadow_relay_\n\()_config,@object
hgn_shadow_relay_\n\()_config:
    .long 0                        // enabled: template is never a live relay.
    .long 0                        // CPUID-validated standard XSAVE extent.
    .quad 0                        // Complete admitted enabled XCR0 mask.
    .quad 0                        // Complete capture/callback/signal budget.
    .quad 0                        // StackBounds initial-exec TLS TPOFF.
    .quad 0                        // Retained ENDBR64 callback entry.
    .quad 0                        // Retained native-owned atomic loss counter.
    .quad 0                        // Retained native-owned atomic enabled flag.
    .quad 0                        // Retained native-owned atomic in-flight count.
    .size hgn_shadow_relay_\n\()_config,HGN_SHADOW_CFG_BYTES
.Lhgn_mxcsr_\n:
    .long 0x1f80
    .balign 8
    .globl hgn_shadow_relay_\n\()_end
    .hidden hgn_shadow_relay_\n\()_end
hgn_shadow_relay_\n\()_end:
    .endm

    HGN_SHADOW_SITE 0,HGN_SHADOW_HANDLER_CFA,0
    HGN_SHADOW_SITE 1,HGN_SHADOW_HANDLER_CFA,0
    HGN_SHADOW_SITE 2,HGN_SHADOW_HANDLER_CFA,0
    HGN_SHADOW_SITE 3,HGN_SHADOW_HANDLER_CFA,0
    HGN_SHADOW_SITE 4,HGN_SHADOW_HANDLER_CFA,0
    HGN_SHADOW_SITE 5,HGN_SHADOW_ENTRY_CFA,1
    HGN_SHADOW_SITE 6,HGN_SHADOW_ENTRY_CFA,1
    HGN_SHADOW_SITE 7,HGN_SHADOW_ENTRY_CFA,1
    HGN_SHADOW_SITE 8,HGN_SHADOW_ENTRY_CFA,1

    .globl hgn_shadow_templates_end
    .hidden hgn_shadow_templates_end
hgn_shadow_templates_end:
    .section .note.GNU-stack,"",@progbits
