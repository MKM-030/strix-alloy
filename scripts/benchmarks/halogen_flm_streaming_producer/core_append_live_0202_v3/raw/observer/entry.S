.text
.globl _ZNSt6chrono3_V212steady_clock3nowEv
.type _ZNSt6chrono3_V212steady_clock3nowEv,@function
_ZNSt6chrono3_V212steady_clock3nowEv:
    endbr64
    mov (%rsp), %rdi
    lea 8(%rsp), %rsi
    mov %r14, %rdx
    mov %rbx, %rcx
    mov %r15, %r8
    jmp hgn_phase_now
.size _ZNSt6chrono3_V212steady_clock3nowEv,.-_ZNSt6chrono3_V212steady_clock3nowEv
.section .note.GNU-stack,"",@progbits
