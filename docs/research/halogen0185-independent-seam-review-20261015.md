# Halogen 0.18.5 demand seam — independent static review, 15 October 2026

**The fresh five-byte call hook preserves the retained bridge contract when the aggregate frame offset changes from88 to80.** This finding is static evidence, not a runtime qualification. No engine, WSL, container, model or hardware was executed by this reviewer. The only executed decoder was the existing native Windows LLVM tool.

Root supplied the extracted engine at `server/.local/halogen0185-update-20261015/extracted/flash_serve`,27220912bytes, SHA256`cfbf55629838dc83e72daf8159745de1d7db9548b034c15b0948618e8fbf1464`. A separate LLVM invocation covered all4232bytes/1010 decoded instructions of the fresh enclosing function. Concatenating the decoded instruction bytes reproduced the exact ELF file span. The generic retained FDE reader confirmed the independently selected function bounds.

| Reviewed identity | Result |
|---|---|
| Function RVA | `[0x1994590,0x1995618)` |
| Function file range | `[0x1993590,0x1994618)` |
| Function SHA256 | `f7c94cdacf73de7d79197c5a1e954ca08a229a6b5afbd6d24e3de0fe3e822286` |
| Hook RVA / file | `0x1994c4f` / `0x1993c4f` |
| Unique17-byte signature | `488b4424504801d04c29f80f870d080000` |
| Replaced instruction | `mov rax,[rsp+0x50]`, exactly5bytes |
| Resume / native rejection RVA | `0x1994c54` / `0x199546d` |

The old full signature is no longer the appropriate anchor because upstream changed the memory reader, spill layout and allocation registers. The new native gate is `mov rax,[rsp+0x50]; add rax,rdx; sub rax,r15; ja reject`. The bridge replaces only the mov's aggregate demand with computed host demand. The native floor addition, available-memory subtraction and unsigned rejection remain intact.

The merged range lengths accumulate in r15 and are saved to frame+0x50 at0x1994b5b. The merged range begin is frame+0x10; r14 remains its end. The mapping object is frame+8. The original floor argument is moved from entryrdx to r14, saved at frame+0x40, and reloaded into rdx immediately before the hook. The new MemAvailable and CmaFree scanner computes the effective available byte value into r15 before the gate; its strings, subtraction,1024-byte fallback and shift are independently checked. The SysV C bridge preserves r15, so the new native CMA adjustment survives the hook.

The function pushes six callee-saved registers and reserves0x198bytes, leaving its frame16-byte aligned. The injected call pushes8bytes; the trampoline pushes72bytes and reserves512bytes for FXSAVE64. Therefore original frame=`trampoline_rsp+592` and savedrdx=`trampoline_rsp+560`, exactly as in the retained trampoline. The whole enclosing function contains no AVX/YMM/ZMM/opmask instruction. No direct branch or call targets the interior of the five-byte replacement. The first instruction after the call target is a valid instruction boundary.

The bridge already rejects host-demand-plus-floor overflow, so preserving native subtraction/JA retains its intended unsigned comparison. The simpler repair is exact new image/function/site/signature pins, aggregate frame+80, and unchanged trampoline save/restore source. There is no need to replace the new memory reader or native rejection branch.

The adapter worker separately derives and checks seven direct helper functions, reference identities, branches and unwind rules. This review does not assert whole-function equivalence to0.18.1: the enclosing function changed. Indirect callbacks, compiled products, loader/HIP providers, actual vector/model values, reserve policy and live startup remain separate root-owned checks.

Reproducible review files are `server/.local/halogen0185-update-20261015/release-review/check_seam.py`, `seam-review.json`, and `fresh-function.txt`. The review script only reads the engine and writes its own evidence directory; it does not patch source, ELF bytes or serving state.
