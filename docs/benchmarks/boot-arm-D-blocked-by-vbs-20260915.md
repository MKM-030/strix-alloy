# Boot experiment arm D: BLOCKED by VBS — proven, not inferred (2026-09-15)

## What happened

Arm D was executed correctly and the machine rebooted into it. The evidence:

| check | value | meaning |
| --- | --- | --- |
| `bcdedit /enum {current}` identifier | `{f26c7218-4419-11f1-aa61-e2c00339da35}` | **= the test entry** |
| its description | `Strix bench - no hypervisor` | the copy we made |
| its `hypervisorlaunchtype` | **`Off`** | the setting we asked for |
| its `vsmlaunchtype` | **`Off`** | the setting we asked for |
| machine boot time | 18:57:36 (73 s after the 18:56:23 arm) | this IS the armed boot |
| **`HypervisorPresent`** | **`True`** | ← the hypervisor is running anyway |
| **VBS status** | **`2` (running)** | ← VBS is running anyway |
| `SecurityServicesRunning` | `[2]` (HVCI) | HVCI still on |

**So the BCD settings applied and were overridden at runtime.** The boot entry said "no hypervisor",
Windows ran one anyway — because **VBS requires the hypervisor and this machine has VBS required**:

```
EnableVirtualizationBasedSecurity = 1
SecurityServicesConfigured        = [2, 3]   (HVCI + SystemGuard)
RequiredSecurityProperties        = [1, 2, 3]  (base virtualization REQUIRED)
```

Independent confirmation that the hypervisor is genuinely running: **WSL2 still works on this boot**
(`6.18.33.2-microsoft-standard-WSL2`). WSL2 needs the hypervisor.

**Arm D is unreachable on this machine without disabling VBS.** `vsmlaunchtype Off` did not take
either, so **arm B is likewise blocked**.

## What this means for the measurement programme

1. **Every number we have was taken with VBS + hypervisor + HVCI active.** That was already known as a
   *baseline* fact (the collector had shown `HypervisorPresent = True`), and this experiment confirms it
   deliberately rather than by inference. Our baseline is honest; it is just not the *only* possible one.
2. **The Windows-boot lever is smaller than hoped and now gated on a security trade-off.** The source
   finding was bare-metal Linux with no hypervisor at all, and even there the ROCm/MoE gain was
   **1.8–3.2%**. Reaching that state on Windows requires turning off VBS / Memory Integrity.
3. **Nothing regressed.** NPU device healthy (`CM_PROB_NONE`), recovery entry intact
   (`recoveryenabled Yes` + `recoverysequence`), and `bootsequence` is one-shot so the machine returns to
   the normal entry on the next boot automatically.

## Correction to an earlier claim of mine

I told the founder the first `-Diagnose` failure was "because the shell was **not** elevated". That was
**wrong** — their shell was elevated (it printed `Elevated = True`) and still reported `{current}`. I do
not have a clean account of why `/v` expanded in `bcd-probe.ps1` but not in `-Diagnose`; I am not going
to invent one. It became moot once the probe showed `/copy {current}` works, which is all the arming path
needed.

## The options from here

| option | what it tests | cost |
| --- | --- | --- |
| **Arm C** (`hypervisoriommupolicy disable`) | the hypervisor's *use* of the IOMMU, specifically — the narrow question, separate from B/D | one reboot; **no security change**; may also be overridden |
| **Disable VBS** (Memory Integrity / Core Isolation off) | true no-hypervisor Windows, the closest analogue to the Linux `amd_iommu=off` result | one reboot + **security posture change** (reversible); expected a few percent |
| **Close out boot work** | — | the 80%-verify forward-pass lever is unaffected by any of this |
