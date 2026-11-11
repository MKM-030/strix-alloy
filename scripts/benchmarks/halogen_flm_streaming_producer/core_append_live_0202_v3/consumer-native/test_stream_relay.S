.text
.globl hgn_fixture_run
.type hgn_fixture_run,@function
.hidden hgn_fixture_mode
.hidden hgn_fixture_path
.hidden hgn_fixture_speculative
.hidden hgn_fixture_prepare_frame
.hidden hgn_fixture_verify
hgn_fixture_run:
    pushq %rbp
    pushq %r15
    pushq %r14
    pushq %r13
    pushq %r12
    pushq %rbx
    subq $0x508, %rsp
    movl %edi, hgn_fixture_mode(%rip)
    movq %rsp, %rdi
    call hgn_fixture_prepare_frame
    cld
    leaq -128(%rsp), %rdi
    movl $128, %ecx
    movl $0x6b, %eax
    rep stosb
    movq $0x101, %rax
    movq $0x202, %rbx
    movq $0x303, %rcx
    movq $0x404, %rdx
    movq $3, %rsi
    movq $0x606, %rdi
    movq $0x707, %rbp
    movq $0x808, %r8
    movq $0x909, %r9
    movq $0xa0a, %r10
    movq $0xb0b, %r11
    movq $0xc0c, %r12
    leaq hgn_fixture_speculative(%rip), %r13
    movq $0xe0e, %r14
    movq $0xf0f, %r15
    cmpq %rax, %rax
    cld
    jmp hgn0202_stream_relay
.size hgn_fixture_run, .-hgn_fixture_run

.globl hgn_fixture_fallback
.type hgn_fixture_fallback,@function
hgn_fixture_fallback:
    movl $0, hgn_fixture_path(%rip)
    jmp .Lcapture
.size hgn_fixture_fallback, .-hgn_fixture_fallback
.globl hgn_fixture_consume
.type hgn_fixture_consume,@function
hgn_fixture_consume:
    movl $1, hgn_fixture_path(%rip)
.Lcapture:
    leaq -128(%rsp), %rsp
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
    movq %rsp, %rdi
    leaq 256(%rsp), %rsi
    call hgn_fixture_verify
    leaq 256(%rsp), %rsp
    addq $0x508, %rsp
    popq %rbx
    popq %r12
    popq %r13
    popq %r14
    popq %r15
    popq %rbp
    ret
.size hgn_fixture_consume, .-hgn_fixture_consume
.section .note.GNU-stack,"",@progbits
