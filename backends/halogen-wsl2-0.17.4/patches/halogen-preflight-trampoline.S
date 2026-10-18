/* Exact flash_serve x86-64 SysV call-site adapter. No AVX/YMM/ZMM state is
 * live across this audited site (the enclosing engine function uses none).
 * FXSAVE64 covers its x87, MMX, MXCSR and all sixteen XMM registers. */
.text
.p2align 4
.globl halogen_preflight_trampoline
.protected halogen_preflight_trampoline
.type halogen_preflight_trampoline,@function
.hidden halogen_preflight_bridge_demand
halogen_preflight_trampoline:
    /* Entry rsp = engine frame - 8, hence rsp mod 16 == 8. */
    pushfq
    push %rcx
    push %rdx
    push %rdi
    push %rsi
    push %r8
    push %r9
    push %r10
    push %r11
    /* 72 bytes pushed: rsp now 16-byte aligned. The SysV C callee saves
     * rbx, rbp, r12-r15. Only rax is intentionally replaced. */
    sub $512, %rsp
    fxsave64 (%rsp)
    lea 592(%rsp), %rdi
    mov %r14, %rsi
    mov 560(%rsp), %rdx
    call halogen_preflight_bridge_demand
    fxrstor64 (%rsp)
    add $512, %rsp
    pop %r11
    pop %r10
    pop %r9
    pop %r8
    pop %rsi
    pop %rdi
    pop %rdx
    pop %rcx
    popfq
    ret
.size halogen_preflight_trampoline,.-halogen_preflight_trampoline
.section .note.GNU-stack,"",@progbits
