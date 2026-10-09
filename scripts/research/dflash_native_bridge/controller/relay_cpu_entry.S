// Host-only Windows CPU mock call/continuation substrate; never a native seam.
    .text
    .globl hgn_mock_run
hgn_mock_run:
    pushq %rbp
    pushq %rbx
    pushq %rdi
    pushq %rsi
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15
    // Commit each Windows guard page before relay XSAVE/callback stack use.
    movq %rsp,%r11
    movl $64,%ecx
.Lcommit:
    subq $4096,%rsp
    movb $0,(%rsp)
    loop .Lcommit
    movq %r11,%rsp
    subq $8192,%rsp
    movq %rsp,mock_expected+56(%rip)
    movq mock_expected+32(%rip),%rax
    movq %rax,16(%rsp)
    movq mock_record(%rip),%rax
    movq %rax,120(%rsp)
    movq mock_aggregate(%rip),%rax
    movq %rax,8(%rsp)
    movl $42,0x6a0(%rsp)
    leaq -128(%rsp),%rdi
    movl $128,%ecx
    movb $0x5a,%al
    cld
    rep stosb
    fninit
    fld1
    ldmxcsr .Lmxcsr(%rip)
    movdqu .Lxmm(%rip),%xmm0
    movq mock_mask(%rip),%rax
    movq %rax,%rdx
    shrq $32,%rdx
    xsave64 mock_before_xstate(%rip)
    movq mock_expected+0(%rip),%rax
    movq mock_expected+8(%rip),%rbx
    movq mock_expected+16(%rip),%rcx
    movq mock_expected+24(%rip),%rdx
    movq mock_expected+32(%rip),%rsi
    movq mock_expected+40(%rip),%rdi
    movq mock_expected+48(%rip),%rbp
    movq mock_expected+64(%rip),%r8
    movq mock_expected+72(%rip),%r9
    movq mock_expected+80(%rip),%r10
    movq mock_expected+88(%rip),%r11
    movq mock_expected+96(%rip),%r12
    movq mock_expected+104(%rip),%r13
    movq mock_expected+112(%rip),%r14
    movq mock_expected+120(%rip),%r15
    // Set DF while keeping the native red zone intact.
    leaq -128(%rsp),%rsp
    pushq $0x646
    popfq
    leaq 128(%rsp),%rsp
    jmp *mock_relay_target(%rip)
    .globl hgn_mock_stock
hgn_mock_stock:
    movl $0,mock_observed_action(%rip)
    jmp .Lcapture
    .globl hgn_mock_scalar
hgn_mock_scalar:
    movl $1,mock_observed_action(%rip)
    jmp .Lcapture
    .globl hgn_mock_ready
hgn_mock_ready:
    movl $2,mock_observed_action(%rip)
.Lcapture:
    movq %rax,mock_observed+0(%rip)
    movq %rbx,mock_observed+8(%rip)
    movq %rcx,mock_observed+16(%rip)
    movq %rdx,mock_observed+24(%rip)
    movq %rsi,mock_observed+32(%rip)
    movq %rdi,mock_observed+40(%rip)
    movq %rbp,mock_observed+48(%rip)
    movq %rsp,mock_observed+56(%rip)
    movq %r8,mock_observed+64(%rip)
    movq %r9,mock_observed+72(%rip)
    movq %r10,mock_observed+80(%rip)
    movq %r11,mock_observed+88(%rip)
    movq %r12,mock_observed+96(%rip)
    movq %r13,mock_observed+104(%rip)
    movq %r14,mock_observed+112(%rip)
    movq %r15,mock_observed+120(%rip)
    leaq -128(%rsp),%rsp
    pushfq
    popq mock_observed+128(%rip)
    leaq 128(%rsp),%rsp
    movq mock_mask(%rip),%rax
    movq %rax,%rdx
    shrq $32,%rdx
    xsave64 mock_after_xstate(%rip)
    leaq -128(%rsp),%rsi
    leaq mock_redzone(%rip),%rdi
    movl $128,%ecx
    cld
    rep movsb
    addq $8192,%rsp
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rsi
    popq %rdi
    popq %rbx
    popq %rbp
    ret
    .p2align 4
.Lxmm:
    .quad 0x1122334455667788,0x99aabbccddeeff00
.Lmxcsr:
    .long 0x1f80
