#include "native_frame_relay.h"
#include "native_frame_install.h"

#if !defined(__linux__) || !defined(__x86_64__)
#error "native frame installation requires Linux x86-64 SysV"
#endif

    .text
    .p2align 4
    .globl halogen_nohit_frame_observer
    .hidden halogen_nohit_frame_observer
    .hidden halogen_nohit_installed_observation
    .type halogen_nohit_frame_observer,@function
halogen_nohit_frame_observer:
    .cfi_startproc simple
    .cfi_def_cfa %rsp,8
    .cfi_offset %rip,-8
    endbr64
    // Normal SysV leaf CALL/RET. Read only this owned view and RegisterImage;
    // do not follow any native address stored in the saved registers.
    movq (%rdi),%rsi
    testq %rsi,%rsi
    je .Lobserver_done
    xorl %eax,%eax
    movl $1,%edx
    lock cmpxchgl %edx,halogen_nohit_installed_observation(%rip)
    jne .Lobserver_done
    leaq halogen_nohit_installed_observation+HGN_INSTALL_OBSERVATION_REGISTERS(%rip),%rdi
    movl $17,%ecx
    // Relay saved DF and cleared it before this ordinary C ABI entry.
    rep movsq
    // Aligned release publication on x86-64. No writer ever changes ready=2.
    movl $2,halogen_nohit_installed_observation(%rip)
.Lobserver_done:
    ret
    .cfi_endproc
    .size halogen_nohit_frame_observer,.-halogen_nohit_frame_observer

    .p2align 4
    .globl halogen_nohit_native_stock_resume
    .hidden halogen_nohit_native_stock_resume
    .globl halogen_nohit_installed_stock_delta
    .hidden halogen_nohit_installed_stock_delta
    .type halogen_nohit_native_stock_resume,@function
halogen_nohit_native_stock_resume:
    .cfi_startproc simple
    // Relay has restored original RSP/RBP before its direct JMP to this pad.
    .cfi_def_cfa %rsp,HGN_RELAY_NATIVE_CFA
    .cfi_offset %rip,-8
    .cfi_offset %rbp,-16
    .cfi_offset %r15,-24
    .cfi_offset %r14,-32
    .cfi_offset %r13,-40
    .cfi_offset %r12,-48
    .cfi_offset %rbx,-56
    endbr64
    .byte 0xe9
halogen_nohit_installed_stock_delta:
    // Intentional link-time sentinel. Installer patches this ONE displacement
    // in the copied RW island before RX publication; never executes the template.
    .long 0x5a17c0de
    .cfi_endproc
    .size halogen_nohit_native_stock_resume,.-halogen_nohit_native_stock_resume

    .section .hgn_nohit_observation,"aw",@progbits
    .p2align 3
    .globl halogen_nohit_installed_observation
    .hidden halogen_nohit_installed_observation
    .type halogen_nohit_installed_observation,@object
halogen_nohit_installed_observation:
    .zero HGN_INSTALL_OBSERVATION_BYTES
    .size halogen_nohit_installed_observation,.-halogen_nohit_installed_observation
    .section .note.GNU-stack,"",@progbits
