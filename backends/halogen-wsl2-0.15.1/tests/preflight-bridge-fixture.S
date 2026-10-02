.text
.macro enter_frame
    push %rbp
    push %rbx
    push %r12
    push %r13
    push %r14
    push %r15
    sub $120, %rsp
    .irp off,0,8,16,24,32,40,48,56,64,72,80,88,96,104,112
    movq $0x5a5a, \off(%rsp)
    .endr
    mov fixture_begin(%rip), %rax
    mov %rax, 8(%rsp)
    lea fixture_object(%rip), %rax
    mov %rax, 16(%rsp)
    mov fixture_aggregate(%rip), %rax
    mov %rax, 88(%rsp)
    mov fixture_end(%rip), %r14
    mov fixture_floor(%rip), %rdx
    mov fixture_available(%rip), %rsi
.endm
.macro snapshot_frame target
    .irp off,0,8,16,24,32,40,48,56,64,72,80,88,96,104,112
    mov \off(%rsp), %rax
    mov %rax, \target+\off(%rip)
    .endr
.endm
.macro leave_frame
    mov 88(%rsp), %rcx
    cmp fixture_aggregate(%rip), %rcx
    jne fixture_abort
    add $120, %rsp
    pop %r15
    pop %r14
    pop %r13
    pop %r12
    pop %rbx
    pop %rbp
    ret
.endm
.macro snapshot target
    mov %rax, \target(%rip)
    mov %rbx, \target+8(%rip)
    mov %rcx, \target+16(%rip)
    mov %rdx, \target+24(%rip)
    mov %rsi, \target+32(%rip)
    mov %rdi, \target+40(%rip)
    mov %rbp, \target+48(%rip)
    mov %rsp, \target+56(%rip)
    mov %r8, \target+64(%rip)
    mov %r9, \target+72(%rip)
    mov %r10, \target+80(%rip)
    mov %r11, \target+88(%rip)
    mov %r12, \target+96(%rip)
    mov %r13, \target+104(%rip)
    mov %r14, \target+112(%rip)
    mov %r15, \target+120(%rip)
    pushfq
    popq \target+128(%rip)
    mov 88(%rsp), %rax
    mov %rax, \target+136(%rip)
.endm
.globl fixture_abi
.type fixture_abi,@function
fixture_abi:
    enter_frame
    mov $0xb1, %rbx
    mov $0xc1, %rcx
    mov $0xd1, %rdi
    mov $0xe1, %rbp
    mov $0x81, %r8
    mov $0x91, %r9
    mov $0xa1, %r10
    mov $0xb2, %r11
    mov $0xc2, %r12
    mov $0xd2, %r13
    mov $0xf2, %r15
    fninit
    fld1
    fldpi
    ldmxcsr fixture_mxcsr(%rip)
    .irp reg,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
    movdqu fixture_vector(%rip), %xmm\reg
    pslld $\reg, %xmm\reg
    .endr
    fxsave64 fixture_fp_before(%rip)
    pushq $0x247
    popfq
    snapshot_frame fixture_frame_before
    snapshot fixture_before
    call *fixture_bridge(%rip)
    snapshot fixture_after
    snapshot_frame fixture_frame_after
    fxsave64 fixture_fp_after(%rip)
    fninit
    ldmxcsr fixture_default_mxcsr(%rip)
    leave_frame
.size fixture_abi,.-fixture_abi
.globl fixture_original
fixture_original:
    mov 96(%rsp), %rax
    ret
.globl fixture_admission
.type fixture_admission,@function
fixture_admission:
    enter_frame
    .p2align 4
.globl fixture_site
fixture_site:
    mov 88(%rsp), %rax
    add %rdx, %rax
    sub %rsi, %rax
    mov 48(%rsp), %r13
    mov 8(%rsp), %r15
    .byte 0x0f,0x87,0x1f,0x08,0x00,0x00
    mov $1, %eax
    leave_frame
    .org fixture_site+0x83a, 0x90
    xor %eax, %eax
    leave_frame
.size fixture_admission,.-fixture_admission
.globl fixture_bad_signature
fixture_bad_signature:
    .fill 32,1,0x90
fixture_abort:
    ud2
.section .rodata
fixture_mxcsr: .long 0x3f80
fixture_default_mxcsr: .long 0x1f80
fixture_vector: .quad 0x123456789abcdef0,0x1122334455667788
.section .note.GNU-stack,"",@progbits
