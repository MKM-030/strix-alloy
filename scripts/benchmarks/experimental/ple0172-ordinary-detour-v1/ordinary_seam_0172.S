/* Exact 0.17.2 ordinary-reader interior seam; no engine entrypoint ABI change.
 * Native frame RSP is 16-byte aligned at RVA 0x17ec18c. Host code in the
 * retained PLE function has no YMM/ZMM live state; preserve all GPRs, flags,
 * x87, MXCSR and all 16 XMM registers across the baseline-ISA C dispatcher.
 */
.text
.globl ple0172_ordinary_seam
.hidden ple0172_ordinary_seam
.type ple0172_ordinary_seam,@function
ple0172_ordinary_seam:
    pushfq
    subq $664, %rsp
    fxsave64 (%rsp)
    movq %rax, 512(%rsp)
    movq %rbx, 520(%rsp)
    movq %rcx, 528(%rsp)
    movq %rdx, 536(%rsp)
    movq %rsi, 544(%rsp)
    movq %rdi, 552(%rsp)
    movq %rbp, 560(%rsp)
    movq %r8, 568(%rsp)
    movq %r9, 576(%rsp)
    movq %r10, 584(%rsp)
    movq %r11, 592(%rsp)
    movq %r12, 600(%rsp)
    movq %r13, 608(%rsp)
    movq %r14, 616(%rsp)
    movq %r15, 624(%rsp)
    cld
    leaq 672(%rsp), %rdi
    leaq 512(%rsp), %rsi
    call ple0172_ordinary_dispatch
    movq %rax, 640(%rsp)
    fxrstor64 (%rsp)
    movq 512(%rsp), %rax
    movq 520(%rsp), %rbx
    movq 528(%rsp), %rcx
    movq 536(%rsp), %rdx
    movq 544(%rsp), %rsi
    movq 552(%rsp), %rdi
    movq 560(%rsp), %rbp
    movq 568(%rsp), %r8
    movq 576(%rsp), %r9
    movq 584(%rsp), %r10
    movq 592(%rsp), %r11
    movq 600(%rsp), %r12
    movq 608(%rsp), %r13
    movq 616(%rsp), %r14
    movq 624(%rsp), %r15
    addq $664, %rsp
    popfq
    jmp *-32(%rsp)
.size ple0172_ordinary_seam,.-ple0172_ordinary_seam
.section .note.GNU-stack,"",@progbits
