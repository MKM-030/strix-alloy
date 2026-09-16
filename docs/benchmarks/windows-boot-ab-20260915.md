# Windows boot-state A/B — prepared, not executed (2026-09-15)

The frontier review is right that my earlier "the IOMMU effect is not testable on Windows" was too strong.
This is the prepared, reversible experiment. **I have not changed BCD or rebooted the machine** — a reboot
into a modified boot entry is a disruptive, hard-to-reverse action on the founder's workstation, and this
box reports DMA protection as a *required* security property, so the call is the operator's.

## What we verified read-only (baseline, arm A)

```
HypervisorPresent            = true      <- the Windows hypervisor runs in ALL our measurements
VBS status (2=running)       = 2
SecurityServicesRunning      = [2]        (HVCI)
RequiredSecurityProperties   = [1,2,3]    (3 = DMA protection required on this machine)
DeviceGuard Locked           = 0          (not UEFI-locked — so a test entry is permissible)
Credential Guard LsaCfgFlags = 0          (not enabled — no locked-Credential-Guard removal risk)
```

Two consequences:

1. **"We shut WSL down" never meant "no hypervisor".** `wsl --shutdown` stops the WSL utility VM; it does
   not stop the host hypervisor. So every number in `current-numbers-20260915.md` was taken with the
   hypervisor and HVCI running. That is a fair baseline, but it is not the only possible one.
2. **A no-hypervisor boot is mechanically available here.** `Locked = 0` and Credential Guard off mean we
   are not fighting a UEFI lock. That is exactly the condition the review said to check first.

## The mechanisms, kept separate

| mechanism | what changing it tests | what it does NOT establish |
| --- | --- | --- |
| HVCI / Memory Integrity | cost of that feature | that VBS/Hyper-V/IOMMU remapping is off |
| `vsmlaunchtype off` (arm B) | cost of the VSM/VBS environment | that the hypervisor is absent |
| `hypervisoriommupolicy disable` (arm C) | the hypervisor's IOMMU policy | system-wide AMD-Vi disablement |
| `hypervisorlaunchtype off` (arm D) | native Windows with no hypervisor | that drivers stopped using IOMMU domains |

These are four different experiments. Do **not** compare A directly to C and attribute it all to the IOMMU.

## Arms

Leave firmware IOMMU, SVM, Secure Boot, the 96 GB carve, drivers and power settings unchanged throughout.

| arm | hypervisor | VSM/VBS | hv IOMMU policy | compare |
| --- | --- | --- | --- | --- |
| **A** baseline | running | as-is | as-is | — |
| **D** no hypervisor | off | off | inherited | **A vs D** (run first: broadest) |
| **B** no VSM | running | off | as-is | B vs A |
| **C** no hv IOMMU policy | running | off | disable | **B vs C** (the narrow IOMMU question) |

Order: **A → D → A**, then **B → C → B**.

## Expected magnitude (be realistic)

The source numbers, correctly read: **ROCm/MoE 1.8–3.2%**, **ROCm/dense 3.7–6.0%**; the 26–32% figures were
**Vulkan**. Applied to our 1057 t/s that is **≈1076–1091 t/s**, i.e. still short of ilintar's 1204. And the
source compared Linux `iommu=pt` vs `amd_iommu=off` — not Windows security states — so even that is a
hypothetical transfer. **Budget zero to a few percent; the test is worth running because it is bounded and
reversible, not because a large gain is supported.**

## How to run it

Both scripts are in `kernel-work/`. Neither reboots for you.

```powershell
# 1. Baseline + confirm state (read-only, elevated for the bcdedit part)
.\Collect-StrixWindowsState.ps1 -Label A-baseline -OutputRoot C:\Projects\REV-N-ornith-eval-20260911\kernel-work\windows-ab
.\windows-boot-ab.ps1 -Status

# 2. Dry run first: shows the plan, changes nothing
.\windows-boot-ab.ps1 -Arm D

# 3. Arm it (elevated). Copies the CURRENT entry; the original is never modified.
.\windows-boot-ab.ps1 -Arm D -ConfirmArm

# 4. Reboot yourself, then verify the state actually changed
.\Collect-StrixWindowsState.ps1 -Label D-no-hypervisor
.\windows-boot-ab.ps1 -Status
#    arm D requires HypervisorPresent = False. If it did not change, the arm is INVALID, not a null result.

# 5. Measure on the armed boot (same command as our baseline)
#    powershell -File kernel-work\measure-ilintar-rebase.ps1 -Sizes "16384" -Repeats 3

# 6. Return to normal for the next boot
.\windows-boot-ab.ps1 -Restore
#    and after the final arm:  .\windows-boot-ab.ps1 -RemoveAll
```

`safe`: the script exports BCD before touching anything, records every test-entry GUID in
`windows-ab/boot-ab-state.json`, arms test entries with `bootsequence` (next boot only, so the boot after
that returns to normal automatically), and never uses `/set` on the original entry.

## Gates before declaring anything

- **NPU must still work.** Keep firmware IOMMU on (the Linux XDNA driver needs AMD IOMMU/SVA; the Windows
  behaviour under each BCD policy is unproven). Run a real NPU workload per arm — device enumeration is not
  proof of execution.
  **Honest limitation:** this box has an **"NPU Compute Accelerator Device" (ComputeAccelerator class,
  `CM_PROB_NONE` at baseline)**, but **no NPU inference runtime is installed** (no FLM/FastFlowLM under
  `C:\AI`). So `npu-smoke.ps1` can only prove the **device+driver still load and are healthy** — a
  *necessary* gate, not the execution proof the review asks for. If the device disappears or reports a
  problem code on an arm, that arm is invalid. If a runtime is added later, wire it into `npu-smoke.ps1`.
- **Reject the arm if the runtime state did not change.** Configuration output is not proof.
- **At least two boots per arm** — the source's own noise floor worsened from 0.2% at two boots to 2.0% at
  five, and we have been burned by rep-0 vs rep-1 artefacts repeatedly.
- Do not collect the state snapshot inside a timed interval.
- Do not disable Windows services to fake a no-hypervisor state; that is not the same experiment.
