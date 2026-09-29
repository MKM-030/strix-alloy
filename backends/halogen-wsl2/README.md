# Strix Alloy WSL2

## Halogen numbers, but on Windows

**Independent extension for Peonist AI's Halogen on Windows (experimental WSL2 support).** Run Qwen 3.8 Flash Next on a 128 GiB Strix Halo PC while keeping your Windows desktop—no dual boot.

Similar-order decode to published Halogen Linux results; prefill still trails. **Not a matched Linux/Windows parity claim.** Upstream [does not support WSL2](https://github.com/peonist-ai/halogen-flash-server#the-host-settings-these-numbers-were-measured-on); this is our unofficial adaptation, not an endorsed release.

> **Experimental, not an unattended service.** A three-full-260k lab test froze the entire PC and required a hard power cycle. Its memory guard could not stop the allocation in time. That profile is not shipped; do not reproduce it. The successful two-full-context profile is also research-only. [Incident and evidence](docs/benchmarks/parallel260k-20260925.md#three-full-contexts-host-freeze).

## Best measured results

Ryzen AI Max+ 395 / Radeon 8060S, Windows 11 + WSL2, pinned Halogen 0.13.8. Rates are tokens/second. These are completed samples, not sustained guarantees.

| Test | Actual input → output | Prefill | Decode |
|---|---|---:|---:|
| Highest completed 260k prefill sample | 260028 → 32 | **790.92** | 36.63, whole answer |
| Highest measured solo decode window | 260042 → 2048 | 763.73 | **66.55** over a fixed 20 s; **64.60** whole answer |
| Two full contexts, generating together | 260041 → 2048 **each** | 756.84 / 759.65 | **25.45 each / 50.90 combined**, same 20 s |
| Three full contexts | No requests started | — | **Host freeze** |

The pair processed **524178 total tokens**, with both full context states verified. Its combined decode was **23.5% below** the same-run solo baseline: concurrency worked, but did not improve throughput. The predictable long-output workload had very high speculative acceptance; it is not a quality benchmark. Shorter-output and failed runs remain in the [full report and raw evidence](docs/benchmarks/parallel260k-20260925.md). The [earlier 60-response suite](docs/benchmarks/upstream-20260924.md) averaged **41.20 MTP decode tok/s**; three smaller 8k clients also completed.

### Alongside Halogen and pwilkin

**Different workloads, precision and timing methods—not an apples-to-apples ranking.** External rows are publisher-reported; no speedup ratio is claimed.

| Backend | Test conditions | Prefill | Decode |
|---|---|---:|---:|
| [Halogen, native Linux](https://github.com/peonist-ai/halogen-flash-server#measured) | 258794 input / 64 output, 1M/YaRN configuration | 1114 | 45.0 |
| [pwilkin / ilintar, native Linux](https://pwilkin.github.io/strix-halo/) | Separate depth-zero pp16384 / tg128, serial means | 1204.31 ± 2.31 | 26.28 ± 0.29 |
| [Strix Alloy / PROJFIX, native Windows](https://github.com/MKM-030/strix-alloy/blob/main/docs/benchmarks/engine-comparison.md) | Separate 16k prefill / 259-token warm MTP test | 1031 | 45.31 median |
| **This WSL2 adaptation** | 260042 input / 2048 output, synthetic text | **763.73** | **64.60 whole answer** |

Halogen also publishes **56.3 tok/s** for a shorter coding-agent workload with MTP + prompt lookup. Text, output length and speculation matter; our highest sample does not establish a faster engine. [Comparison details](docs/benchmarks/parallel260k-20260925.md#native-halogen-comparison).

## Install and use Halogen

Required: **128 GiB Strix Halo**, supported **64 GiB VGM carve**, Windows 11, Ubuntu 24.04 in WSL2, Docker Engine inside that distro, PowerShell 7, Windows Python 3.12+, WSL GCC and OpenSSL development headers. Tested driver: AMD **32.0.31041.1004 / Adrenalin 26.8.1**. WSL ceiling: **56GB**, 24 processors, 32GB swap. Models must be on **native WSL Ext4**, not `/mnt/c`.

Follow the [setup guide](docs/setup.md) for BIOS/driver settings, prerequisites, model files and the pinned AMD DXG library. Setup does not configure Windows/WSL or download the model for you. Then, in PowerShell 7:

```powershell
git clone https://github.com/MKM-030/strix-alloy-wsl2.git
cd strix-alloy-wsl2

# Replace both example paths. First command checks; second builds/installs.
.\Install.ps1 -Distribution Ubuntu-24.04 -ModelDirectory /srv/models/flash-next -DxgLibrary /opt/rocm/lib/librocdxg.so.1
.\Install.ps1 -Install -Distribution Ubuntu-24.04 -ModelDirectory /srv/models/flash-next -DxgLibrary /opt/rocm/lib/librocdxg.so.1

.\Start.ps1 -Profile Single32k
.\Start.ps1 -Profile Serve32k -ServeSeconds 300
```

OpenAI-compatible API: **`http://127.0.0.1:8731/v1`**. Keep the launcher open; serving stops **30–300 seconds after readiness**. Loopback-only, unauthenticated: do not expose it to your network. `Single256k` runs a bounded large-context check, not an always-on 256k API. `Sessions32k` checks smaller parallel requests. [Usage, rollback and qualification limits](docs/setup.md#use-and-remove).

## Other backend / 27B

For **native Windows HIP / llama.cpp**, use the separate [Strix Alloy release and launcher](https://github.com/MKM-030/strix-alloy): PROJFIX GGUF shards plus a matching MTP sidecar, API on port 8826. That is the same Flash Next model on another runtime, with different settings—not a Halogen switch. Keep the projects separate; do not run both large backends together.

The earlier **27B WSL experiment** is **not a supported installer/profile in this release**. [Backend setup and limits](docs/setup.md#native-windows-alternative-and-27b-status). The optional [local-model router](https://github.com/MKM-030/codex-local-model-router) connects a local worker to our ChatGPT/Codex desktop workflow; it is not required for inference.

## Memory and what changed

The working path combines a ROCm/DXG bridge, private copy-on-write mappings, hybrid GPU/host weight placement and a hash-gated **process-local** preflight adaptation. **No installed AMD driver binary was patched, no firmware flashed, no Secure Boot disabled.** This is not a 120 GB VRAM unlock.

Completed weight operations total **73.01 GB payload**. The two-full-context run peaked at **100.29 GB adapter-wide GPU accounting**, with at least **18.86 GB Windows available** in samples. These overlapping counters are **not exact model residency** and must not be added together. Halogen's N-Gram table is already disk-backed. [Memory/methodology](docs/benchmarks/parallel260k-20260925.md).

The owner reports **9 GB Windows idle usage** and a responsive desktop during successful runs. Gaming alongside this WSL profile is untested; the three-context freeze shows the limits. [Community tuning notes](docs/benchmarks/community-tuning-notes.md).

Our original code is [MIT](LICENSE). Engine, AMD libraries and weights are obtained separately under their own terms; no proprietary binaries are redistributed. Credits: [Peonist AI](https://github.com/peonist-ai/halogen-flash-server), Qwen, ROCm/TheRock, Microsoft WSL/DXG, CIRU and pwilkin/ilintar. [Notices](THIRD_PARTY_NOTICES.md) · [Release qualification](docs/release-qualification.md).
