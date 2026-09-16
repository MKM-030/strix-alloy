# Boot arms: D blocked by VBS, C breaks the GPU — the boot lever is closed (2026-09-15)

## Result

| arm | BCD setting applied? | runtime effect | usable? |
| --- | --- | --- | --- |
| **A** baseline (normal) | — | hypervisor + VBS + HVCI running | **yes** |
| **D** no hypervisor | yes (`hypervisorlaunchtype Off`, `vsmlaunchtype Off`) | **overridden — hypervisor still ran** | yes (but not the arm we wanted) |
| **C** no VSM + no hv IOMMU policy | yes (`hypervisoriommupolicy Disable`, `vsmlaunchtype Off`) | **ROCm/HIP device access broken** | **NO — cannot run inference** |

Both arms were armed correctly (verified by reading the settings back off the booted entry), so these are
real runtime results, not configuration mistakes.

## Arm D: VBS forces the hypervisor

Booted the test entry `{f26c7218-…}` ("Strix bench - no hypervisor") with
`hypervisorlaunchtype Off` **and** `vsmlaunchtype Off` both set — yet:

```
HypervisorPresent = True
VBS status        = 2 (running)
SecurityServicesRunning = [2] (HVCI)
```

Independent confirmation: **WSL2 still worked on that boot**, and WSL2 requires the hypervisor.
Cause: this box has `EnableVirtualizationBasedSecurity = 1` and
`RequiredSecurityProperties = [1, 2, 3]` (base virtualization **required**). VBS cannot run without the
hypervisor, so the boot flag is overridden. **Arm D is unreachable without disabling VBS.**

## Arm C: the GPU stops working

Booted `{f26c7219-…}` ("Strix bench - no VSM + no hv IOMMU policy") with
`vsmlaunchtype Off` and `hypervisoriommupolicy Disable`. The measurement run produced **no numbers** —
so I checked why, and reproduced it independently with `gpu-probe.ps1`:

| | healthy boot | arm C boot |
| --- | --- | --- |
| stdout device enumeration | `found 1 ROCm devices (Total VRAM: 110456 MiB)` | **empty (0 bytes)** |
| first failure | — | `cudaMemGetInfo failed (invalid argument), returning 0/0` at **0.30 s** |
| reaches `threadpool init` | yes | **no** |
| reaches `listening on` | yes | **no** |
| total stderr | full startup | 899 bytes, then the process dies |

**The HIP/ROCm runtime cannot query the GPU at all on arm C**, so the server dies during model load. Two
independent runs (19:04:56 and 19:05:06) plus my own probe reproduced it exactly.

*Caveat, stated honestly:* I did not isolate **which** of the two C settings (vsmlaunchtype Off vs the
hypervisor IOMMU policy) breaks it, and I am not going to spend more reboots finding out — the practical
answer is the same either way.

**Note this is a boot-entry setting, not damage.** Rebooting to the normal entry restores the GPU (as it
did for arm D → arm C). It is fully reversible.

## Why this closes the boot lever

- **D** is blocked by a security posture we are not going to tear down for a few percent.
- **C** is not merely non-improving — it is **incompatible with our inference stack**.
- **B** sets `vsmlaunchtype off` with the hypervisor running. It shares the one setting most likely to be
  responsible for the C breakage, and VBS ignored the same flag on D. Expected outcome: either it also
  breaks the GPU, or VBS overrides it. Not worth a reboot each way.

The source finding was also always small: **1.8–3.2%** for MoE on ROCm, on bare-metal Linux with no
hypervisor at all. Windows cannot reach that state, and when it gets close, it breaks the driver.

## What this is worth

**A real negative result, cheaply bought** (3 reboots): the Windows boot-state lever is closed. That
matters because it removes a whole branch from the plan and stops us spending more time on it. It also
confirms our baseline is honest — every number we have was taken with VBS + hypervisor + HVCI active,
which is the machine's normal state.

## Also:**

- NPU device healthy on every arm (`CM_PROB_NONE`) — no regression.
- The arm-C measurement attempt left the 17:10 baseline JSONs untouched; **no stale numbers were
  overwritten with arm-C data**, so our baseline record is intact.
- `ilintar-rebase.log` mixes UTF-8 and UTF-16 lines (PowerShell `Out-File` default vs `Tee-Object`),
  which is why it displayed as mojibake. Cosmetic, but it made the log harder to read than it should be.

## Next

1. **Reboot** — `-Restore` already armed the normal entry, so this returns the machine to full function.
2. After that boot, `.\windows-boot-ab.ps1 -RemoveAll` to delete the two test entries.
3. Back to the main lever: the **target forward pass is ~80% of decode and all of prefill.**
