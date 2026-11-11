.text
.p2align 4
.globl hgn0203_stream_relay
.type hgn0203_stream_relay,@function
.hidden hgn0203_stream_consume_snapshot
.hidden hgn0203_stream_native_fallback
.hidden hgn0203_stream_native_consume
hgn0203_stream_relay:
    /* Reserve the native redzone without modifying its incoming flags. */
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
    cld
    movq %rsp, %rdi
    call hgn0203_stream_consume_snapshot
    testl %eax, %eax
    jle .Lfallback
    movl %eax, %eax
    movq %rax, (%rsp)
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
    leaq 128(%rsp), %rsp
    jmp *hgn0203_stream_native_consume(%rip)
.Lfallback:
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
    leaq 128(%rsp), %rsp
    leaq 0x268(%r13), %rdi
    jmp *hgn0203_stream_native_fallback(%rip)
.size hgn0203_stream_relay, .-hgn0203_stream_relay
.section .note.GNU-stack,"",@progbits
