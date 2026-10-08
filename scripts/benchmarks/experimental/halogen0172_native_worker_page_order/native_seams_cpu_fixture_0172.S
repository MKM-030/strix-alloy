/* CPU-only fixture. This file deliberately poisons even callee-saved GPRs in
 * its private dispatch stubs to ensure the seam restores its own saved block.
 * It enters each real production seam by JMP, at native RSP mod 16 = 0 or 8.
 */
.text
.globl ple0172_fixture_run
.type ple0172_fixture_run,@function
ple0172_fixture_run:
    pushq %rbp
    pushq %rbx
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15
    subq $1448, %rsp
    movq %rsp, ple0172_fixture_host_rsp(%rip)
    fxsave64 (%rsp)
    movq %rdi, ple0172_fixture_input(%rip)
    movq %rsi, ple0172_fixture_output(%rip)
    movq 0(%rdi), %rax
    movq %rax, ple0172_fixture_target(%rip)
    leaq 1376(%rsp), %rax
    cmpq $0, 8(%rdi)
    je .Lnative_aligned
    subq $8, %rax
.Lnative_aligned:
    movq %rax, ple0172_fixture_native_rsp(%rip)
    movq 32(%rdi), %rdx
    movq %rdx, 16(%rax)
    fninit
    fldcw .Lseed_cw(%rip)
    fld1
    fldpi
    ldmxcsr .Lseed_mxcsr(%rip)
    movdqu .Lseed_xmm+0(%rip), %xmm0
    movdqu .Lseed_xmm+16(%rip), %xmm1
    movdqu .Lseed_xmm+32(%rip), %xmm2
    movdqu .Lseed_xmm+48(%rip), %xmm3
    movdqu .Lseed_xmm+64(%rip), %xmm4
    movdqu .Lseed_xmm+80(%rip), %xmm5
    movdqu .Lseed_xmm+96(%rip), %xmm6
    movdqu .Lseed_xmm+112(%rip), %xmm7
    movdqu .Lseed_xmm+128(%rip), %xmm8
    movdqu .Lseed_xmm+144(%rip), %xmm9
    movdqu .Lseed_xmm+160(%rip), %xmm10
    movdqu .Lseed_xmm+176(%rip), %xmm11
    movdqu .Lseed_xmm+192(%rip), %xmm12
    movdqu .Lseed_xmm+208(%rip), %xmm13
    movdqu .Lseed_xmm+224(%rip), %xmm14
    movdqu .Lseed_xmm+240(%rip), %xmm15
    fxsave64 208(%rsi)
    movq %rax, %rsp
    movabsq $0x1111111111111111, %rax
    movabsq $0x2222222222222222, %rbx
    movabsq $0x3333333333333333, %rcx
    movabsq $0x4444444444444444, %rdx
    movabsq $0x5555555555555555, %rsi
    movabsq $0x6666666666666666, %rdi
    movabsq $0x7777777777777777, %rbp
    movabsq $0x8888888888888888, %r8
    movabsq $0x9999999999999999, %r9
    movabsq $0xaaaaaaaaaaaaaaaa, %r10
    movabsq $0xbbbbbbbbbbbbbbbb, %r11
    movabsq $0xcccccccccccccccc, %r12
    movabsq $0xdddddddddddddddd, %r13
    movabsq $0xeeeeeeeeeeeeeeee, %r14
    movabsq $0xffffffffffffffff, %r15
    pushq $0xed7
    popfq
    pushfq
    popq ple0172_fixture_expected_flags(%rip)
    jmp *ple0172_fixture_target(%rip)
.size ple0172_fixture_run,.-ple0172_fixture_run

.globl ple0172_fixture_resume
.type ple0172_fixture_resume,@function
ple0172_fixture_resume:
    movq $1, ple0172_fixture_chosen_resume(%rip)
    jmp .Lcapture
.size ple0172_fixture_resume,.-ple0172_fixture_resume
.globl ple0172_fixture_alternate_resume
.type ple0172_fixture_alternate_resume,@function
ple0172_fixture_alternate_resume:
    movq $2, ple0172_fixture_chosen_resume(%rip)
    jmp .Lcapture
.size ple0172_fixture_alternate_resume,.-ple0172_fixture_alternate_resume

.globl ple0172_fixture_cmp_replay
.type ple0172_fixture_cmp_replay,@function
ple0172_fixture_cmp_replay:
    /* Exactly the six overwritten CMP bytes and the helper's register-free
     * absolute jump, followed by a native-style conditional at its target.
     */
    .byte 0x48,0x83,0x7c,0x24,0x10,0x00
    .byte 0xff,0x25,0x00,0x00,0x00,0x00
    .quad .Lnative_conditional
.Lnative_conditional:
    movq $3, ple0172_fixture_chosen_resume(%rip)
    je .Lcmp_zero
    movq $2, ple0172_fixture_branch(%rip)
    jmp .Lcapture
.Lcmp_zero:
    movq $1, ple0172_fixture_branch(%rip)
    jmp .Lcapture
.size ple0172_fixture_cmp_replay,.-ple0172_fixture_cmp_replay

.Lcapture:
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
    movq %rsp, %r12
    cld
    movq ple0172_fixture_output(%rip), %rdi
    fxsave64 720(%rdi)
    movq %r12, %rsi
    movl $16, %ecx
    rep movsq
    movq ple0172_fixture_output(%rip), %rdi
    leaq 128(%r12), %rax
    movq %rax, 128(%rdi)
    movq ple0172_fixture_host_rsp(%rip), %rsp
    fxrstor64 (%rsp)
    addq $1448, %rsp
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rbx
    popq %rbp
    ret

.macro FIXTURE_DISPATCH name, seam
.globl \name
.hidden \name
.type \name,@function
\name:
    pushq %rbp
    leaq 8(%rsp), %rcx
    movl $\seam, %edx
    call ple0172_fixture_callback
    fninit
    fldz
    ldmxcsr .Lclobber_mxcsr(%rip)
    pxor %xmm0, %xmm0
    pxor %xmm1, %xmm1
    pxor %xmm2, %xmm2
    pxor %xmm3, %xmm3
    pxor %xmm4, %xmm4
    pxor %xmm5, %xmm5
    pxor %xmm6, %xmm6
    pxor %xmm7, %xmm7
    pxor %xmm8, %xmm8
    pxor %xmm9, %xmm9
    pxor %xmm10, %xmm10
    pxor %xmm11, %xmm11
    pxor %xmm12, %xmm12
    pxor %xmm13, %xmm13
    pxor %xmm14, %xmm14
    pxor %xmm15, %xmm15
    popq %rbp
    cld
    xorl %edx, %edx
    movabsq $0xdededededededede, %rbx
    movabsq $0xdededededededede, %rcx
    movabsq $0xdededededededede, %rdx
    movabsq $0xdededededededede, %rsi
    movabsq $0xdededededededede, %rdi
    movabsq $0xdededededededede, %rbp
    movabsq $0xdededededededede, %r8
    movabsq $0xdededededededede, %r9
    movabsq $0xdededededededede, %r10
    movabsq $0xdededededededede, %r11
    movabsq $0xdededededededede, %r12
    movabsq $0xdededededededede, %r13
    movabsq $0xdededededededede, %r14
    movabsq $0xdededededededede, %r15
    ret
.size \name,.-\name
.endm
FIXTURE_DISPATCH ple0172_native_launch_dispatch, 0
FIXTURE_DISPATCH ple0172_native_copy_dispatch, 1
FIXTURE_DISPATCH ple0172_native_complete_dispatch, 2
FIXTURE_DISPATCH ple0172_native_consumer_dispatch, 3

.section .rodata
.p2align 4
.Lseed_cw: .short 0x077f
.p2align 2
.Lseed_mxcsr: .long 0x5f80
.Lclobber_mxcsr: .long 0x1f80
.p2align 4
.Lseed_xmm:
    .quad 0x0706050403020100,0x0f0e0d0c0b0a0908
    .quad 0x1716151413121110,0x1f1e1d1c1b1a1918
    .quad 0x2726252423222120,0x2f2e2d2c2b2a2928
    .quad 0x3736353433323130,0x3f3e3d3c3b3a3938
    .quad 0x4746454443424140,0x4f4e4d4c4b4a4948
    .quad 0x5756555453525150,0x5f5e5d5c5b5a5958
    .quad 0x6766656463626160,0x6f6e6d6c6b6a6968
    .quad 0x7776757473727170,0x7f7e7d7c7b7a7978
    .quad 0x8786858483828180,0x8f8e8d8c8b8a8988
    .quad 0x9796959493929190,0x9f9e9d9c9b9a9998
    .quad 0xa7a6a5a4a3a2a1a0,0xafaeadacabaaa9a8
    .quad 0xb7b6b5b4b3b2b1b0,0xbfbebdbcbbbab9b8
    .quad 0xc7c6c5c4c3c2c1c0,0xcfcecdcccbcac9c8
    .quad 0xd7d6d5d4d3d2d1d0,0xdfdedddcdbdad9d8
    .quad 0xe7e6e5e4e3e2e1e0,0xefeeedecebeae9e8
    .quad 0xf7f6f5f4f3f2f1f0,0xfffefdfcfbfaf9f8
.section .note.GNU-stack,"",@progbits
