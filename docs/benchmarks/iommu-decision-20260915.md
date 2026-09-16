# IOMMU: what `amd_iommu=off` would cost us, and whether we can measure it (2026-09-15)

The founder asked three things about the IOMMU prefill finding: what the consequences are, whether we
can measure a gain, and whether it is worth doing. This documents the answer *before* anyone changes a
boot parameter.

## What the source finding actually claims

`r/StrixHalo/1wdrkrc` (baldlawyer, harness at `github.com/baldlawyer/strix-halo-iommu-benchmark`):
`amd_iommu=off` raised prefill **+1.8% to +31.6% depending on model**, and most of the
"ROCm beats Vulkan at prefill" gap is the IOMMU. Decode unaffected (±1%). It is **not** a power/clock
effect (package power pinned 99–100 W in both arms; shader clocks *lower* with IOMMU off). The effect
orders with **bytes read per forward pass** (their hypothesis). All of it is **bare-metal Linux** —
`amd_iommu=off` is a Linux kernel command-line parameter.

## The decisive problem: we cannot reproduce it on our fast path

Our speed lives in **two places, neither of which is a bare-metal Linux kernel**:

1. **Native Windows HIP** (clang 24 / TheRock) — this is where our 1057 t/s prefill and 35.5 t/s decode
   come from. `amd_iommu=off` does not exist here; Windows uses **Device Guard / Kernel DMA Protection**,
   and we measured only **HVCI (bit 2)** running, no dedicated IOMMU device exposed
   (`Get-PnpDevice` for `IOMMU|SMMU|DMA Remap` returns nothing).
2. **WSL2** — the guest boots **paravirtualized on Hyper-V** (`Booting paravirtualized kernel on Hyper-V`),
   and `dmesg` shows a **virtual** IOMMU (`Default domain type: Translated`), not AMD-Vi. The guest has no
   `/sys/class/iommu` and `.wslconfig` sets no `kernelCommandLine` (and `amd_iommu=off` is not a settable
   *host* parameter through WSL anyway).

So: **a WSL `amd_iommu=off` test would prove nothing about the host effect.** It would toggle the virtual
IOMMU of a paravirtualized guest, which is a different mechanism. Any number we got from it would be
uninterpretable in either direction.

## Consequences of turning it off (on bare-metal Linux, where it applies)

If someone later runs the ilintar/Halogen stack on bare-metal Linux, `amd_iommu=off` would:

- **Disable the NPU.** The same parameter that removes DMA translation also removes the NPU's device
  path. The founder explicitly wants the NPU used (FastFlowLM etc.). This is the single biggest cost.
- **Turn off DMA translation machine-wide** — a security/isolation change, fine on a dedicated inference
  box, not on a workstation with other users.
- **Only if it is in the AMD-Vi (host) path.** A guest or a container would not see it.

And the gain is **uncertain for us specifically**: their table orders by bytes-read-per-forward, and the
large gains (+26–32%) are **dense, high-byte models**. Qwen3.8-Flash-Next **at decode** reads ~4.25 GB/token
but the MTP point is only at 24–29% of the bandwidth ceiling (overhead/acceptance-bound). Their **ROCm**
column for MoE-ish rows was only **+1.8% to +6.0%** — which, applied to our ~1057 t/s prefill, is
**~+19 to +63 t/s**, i.e. still short of ilintar's 1204. So even if it transferred, it would not by itself
close the prefill gap, and it would cost us the NPU.

## What we measured instead

Because the host IOMMU is not reachable from either of our paths, the honest test of "can we even see the
effect" is a **WSL A/B of the same kernels with the virtual IOMMU in its two states**, recorded as a
*non-transferable* data point. The script is `iommu-ab.sh`; it records `/proc/cmdline` and the `dmesg`
IOMMU lines with the result so the limitation is explicit. **Expectation: no effect**, because the guest
IOMMU is virtual and our WSL path is not the fast path.

## Recommendation

- **Do not change boot parameters now.** The cost (NPU off, machine-wide DMA translation off) is real and
  the benefit is unproven on a MoE; the source's own numbers for the ROCm/MoE rows are the smallest in its
  table.
- **The prefill gap is better attacked with the ilintar rebase** (HIP kernels + F32 PLE fusion + no env
  gates), which is a *software* change on our actual fast path with no NPU cost. That is running.
- **If we ever move to bare-metal Linux**, the IOMMU test becomes cheap and meaningful — and at that point
  it is a one-line grub change with an obvious A/B. Note it in the backlog as a future option, not a now
  option.
