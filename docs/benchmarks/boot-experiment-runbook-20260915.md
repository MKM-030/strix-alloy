# Boot experiment runbook — what to run, in order (2026-09-15)

Everything here runs on **native Windows**. Arm D removes the hypervisor, which **also stops WSL2 on that
boot** — so do not plan WSL work during a test boot. Our measurement scripts are all native, so this is fine.

## Fixed since the first attempt

Two bugs in `windows-boot-ab.ps1` v1, both found from the founder's paste and reproduced:

1. **`Set-StrictMode -Version Latest` + `[pscustomobject]@{}`** threw *"The property 'Name' cannot be found"*
   on the empty state object. Removed StrictMode (and switched state to a hashtable).
2. **This system's `bcdedit` rejects `{current}` and `{default}`** — `/enum {current}` returns *"The specified
   entry type is invalid"* even elevated. Only `{bootmgr}`, `ACTIVE`, `all`, `firmware` parse. The script now
   uses `ACTIVE` and resolves the concrete GUID from `/v` output.

**Nothing was armed by the failed attempt.** The v1 throw happened at the state-loading line, *before* any
`bcdedit` call, and no state file was written (verified: `windows-ab/boot-ab-state.json` does not exist).
The next boot is completely normal.

## Before you restart (ELEVATED PowerShell — your prompt was already `C:\windows\system32>`)

```powershell
cd C:\Projects\REV-N-ornith-eval-20260911\kernel-work

# 1. READ-ONLY: confirm bcdedit works elevated and the current-entry GUID resolves.
.\windows-boot-ab.ps1 -Diagnose
```

You should see `Resolved current-entry GUID = {xxxxxxxx-....}`. If it says `<NOT RESOLVED>`, stop and paste
the output — the arming command would also refuse, so nothing can go wrong, but we would fix it first.

```powershell
# 2. Read-only inventory (BitLocker already checked: Protection Off, no key protectors -> no recovery key needed)
.\Collect-StrixWindowsState.ps1 -Label A-baseline -OutputRoot .\windows-ab
.\npu-smoke.ps1 -Label A-baseline
.\windows-boot-ab.ps1 -Status

# 3. DRY RUN: prints the plan, changes nothing (works without elevation too)
.\windows-boot-ab.ps1 -Arm D

# 4. ARM for the NEXT BOOT ONLY (creates a copy; the original entry is never touched)
.\windows-boot-ab.ps1 -Arm D -ConfirmArm
```

**Your restart signal:** step 4 prints `ARMED: the NEXT boot uses {…}` and `bootsequence: ... exit=0`.
If it prints a warning instead, do **not** reboot — tell me.

The test entry runs for exactly one boot; the boot after that returns to normal automatically. If the
machine fails to boot it falls through to the normal entry on the next attempt.

## After the restart

```powershell
# 5. PROVE the state actually changed. Arm D requires HypervisorPresent = False.
.\windows-boot-ab.ps1 -Status
.\Collect-StrixWindowsState.ps1 -Label D-no-hypervisor
.\npu-smoke.ps1 -Label D-no-hypervisor
#    If HypervisorPresent is still True, the arm is INVALID (not a null result). Tell me and we stop.

# 6. Measure the same thing we measure at baseline
powershell -File .\measure-ilintar-rebase.ps1 -Sizes "16384" -Repeats 3

# 7. Return to normal for the boot after this one
.\windows-boot-ab.ps1 -Restore
```

Then repeat for **B** (no VSM) and **C** (no VSM + no hv IOMMU policy), and finally run
`.\windows-boot-ab.ps1 -RemoveAll` to delete the test entries.

## What we are looking for

- **Prefill @16k** vs the 1025–1057 t/s range we measure with the hypervisor on.
- Expectation from the source (correctly read): **zero to a few percent**. A large gain would itself be
  interesting but is not the prior.
- **Do not** attribute an A→C difference to the IOMMU — A vs D is the broad test, B vs C is the narrow one.
- **NPU must survive.** `npu-smoke.ps1` proves the device is still healthy; it cannot prove execution (no NPU
  runtime is installed on this box). If the device disappears or takes a problem code, the arm is invalid.

## Notes

- `windows-boot-ab.ps1` exports BCD to `windows-ab/bcd-backup-*` before changing anything, and records every
  test-entry GUID in `windows-ab/boot-ab-state.json`.
- It will refuse to run without elevation, and it never reboots for you.
- Test boot entries share the registry and all security policy — that is why we change only BCD, and why
  registry "debloat" scripts are explicitly not part of this.
