# Strix Alloy

One Windows-facing control and API layer for version-pinned local inference engines,
with explicit availability, reproducible measurements and no silent fallback.
**This is an experimental integration branch, not a universally qualified kernel bundle.**

## Current implementations

| Backend | Status | Entry point |
|---|---|---|
| **Halogen WSL2 0.19.1** | Current v2 text serving with one 32K slot and a 2K prefill arena | [Update and measurements](docs/research/halogen0191-update-20261107.md) |
| **Halogen WSL2 0.18.22** | Retained independently captured frozen 8K/16K phase measurements | [Earlier measurements](docs/benchmarks/halogen01822-raw-8k16k-20261101.md) |
| **Halogen WSL2 0.18.16** | Retained independently captured 8K/16K phase measurements | [Earlier phase measurements](docs/benchmarks/halogen01816-natural-8k16k-20261026-evening.md) |
| **Hipfire native Windows** | Source port with completed 16K MTP cohort; 1,240.2 prefill / 26.53 decode tok/s, 63.64% acceptance | [Build, run and measurement limits](backends/hipfire-windows/README.md) |
| **Halogen WSL2 0.16.2** | Pinned v2 upgrade and sampled filled-context comparison measured with an 18 GiB reserve | [Install and run](backends/halogen-wsl2-0.16.2/README.md) |
| **Halogen WSL2 0.15.1** | w4b + overlay and v2 tested at 262144 capacity; authenticated continuous serving | [Install and run](backends/halogen-wsl2-0.15.1/README.md) |
| **Managed Windows endpoint** | Owns one selected engine and serves one stable streaming API on port 8840 | [server/Start.ps1](server/README.md) |
| Native llama.cpp / PROJFIX | Fast serial pinned-host placement; 31-33 t/s short-prompt decode at 262144 capacity; explicit legacy MTP retained | [Prepare and register](backends/projfix-windows/README.md) |
| GUFO native Windows | Latest qualified TheRock 10.2.0a20260930 with source-level numeric compatibility; native and managed text serving | [Build, qualify and register](backends/gufo-windows/README.md) |
| Halogen 0.15.0 / 0.14.2 / 0.13.8 | Retained explicit rollback packages; never run alongside another large model | Version-specific `backends/` directories |

For BYOLLM in ServiceNow, use the [canonical documentation](docs/servicenow-byollm/README.md). It separates the immutable 19 October 2.0 baseline from the 2.1 working consolidation and later deltas; see [batch status](docs/servicenow-byollm/batch-status.md).

For the current installed Halogen text configuration, use Windows PowerShell 5.1:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Halogen-ServiceNow.ps1 -Profile CurrentText32K -Slots 1 -KvPoolPositions 32768 -Concurrency 1 -PrefillTokens 2048 -ConsoleTrace
```

This command selects 0.19.1, v2, one 32768-position slot, a 32768-position
KV pool, paired 2048 prefill settings, adaptive MTP gate 0.90, PLD `3,3`,
Cache Off, Thinking Off and Vision Off. It keeps the existing ServiceNow token and endpoint on port 8840.
Stop an existing managed session through its normal controls before changing
profiles. See the [ServiceNow guide](docs/integrations/halogen-servicenow.md).

The separate generic launcher uses PowerShell 7:

```powershell
.\server\Setup.ps1
.\server\Start.ps1 -Backend Halogen -Checkpoint v2 -ContextSize 262144
```

The managed default is v2, 129024 context positions, cache Off and no time-based
shutdown. API base: `http://127.0.0.1:8840/v1`; model `halogen-v2`. The existing
backend token is reused. Stop and confirm cleanup before changing engine/checkpoint.
Native/GUFO adapter slots do not imply they have passed current qualification.

## Measurements and implementation evidence

The frozen 8192-token fixture contains synthetic prose. The 16384-token fixture
contains a contiguous novel excerpt. Their request identities are documented
in the [workload classification](docs/benchmarks/halogen-8k-workload-classification-20261107.md).

The 7 November 0.19.1 genuine natural-text RAW cohorts completed one excluded
warmup and three measured requests each, with 128 actual output tokens.
The table gives mean RAW midpoint rates, including observer overhead.

| Profile | Native input tokens | Prefill tok/s | Decode tok/s | Native head accepted/drafted |
| --- | --- | --- | --- | --- |
| Two slots, pool 65536, paired 2048 | 8192 | 1185.559992 | 48.802438 | 207/327 (63.30275%) |
| One slot, pool 32768, paired 2048 | 8192 | 1143.700731 | 48.574773 | 207/327 (63.30275%) |
| One slot, pool 32768, paired 2048 | 16384 | 1124.357529 | 49.677162 | 210/321 (65.42056%) |

The two-slot row belongs to the PLD comparison's before arm. The one-slot rows
belong to the separate prefill comparison's before arm. Its paired 4096
candidate completed only the 8K warmup before failing the 22 GiB request-entry
gate. Qualified PLD speedup, 4096-prefill gain and beneficial NPU contribution
remain open. API phase clocks remain unqualified.
[PLD RAW report](docs/benchmarks/halogen0191-pld34-raw-20261107.md),
[prefill RAW report](docs/benchmarks/halogen0191-prefill4096-raw-20261107.md).

The **7 November 17:09:37 UTC** functional check recorded the selected one-slot,
pool-32768, paired-2048 profile ready with controller/backend PIDs
**28972/24440**. Model discovery returned HTTP 401 without authentication and
HTTP 200 with authentication. Authenticated chat returned HTTP 200 and `READY`.
The selection serializes requests while retaining 32K context capacity. The
earlier two-slot gateway had rejected new requests below its 22 GiB memory
admission floor.
[Dated restoration record](docs/research/halogen0191-update-20261107.md#final-functional-check).

A separate copied-log performance study completed one excluded warmup and
three measurements with 3539 input and 1259 generated tokens. RAW midpoint
means were **1161.93 prefill / 105.33 decode tok/s**, with head acceptance
**69/84 (82.14%)** and lookup acceptance **3228/3234 (99.81%)**. The reference
preserves a recorded serial response that omitted the canonical final LF.
The PLD `3,4` candidate failed startup admission before generation, leaving
the three-arm comparison incomplete. The linked reports retain the
workload-specific scope and both earlier failures.
[Copied-log study](docs/benchmarks/halogen0191-pld34log-reference-retry1-raw-20261107.md),
[earlier GPU-gated attempt](docs/benchmarks/halogen0191-pld34log-reference-raw-20261107.md),
[original task-format failure](docs/benchmarks/halogen0191-pld34log-raw-20261107.md).

The subsequent source audit closes another K4 chain-length trial on that log
case and prepares an existing Q8 draft-vocabulary control for a separate frozen
comparison. The selected server retains its current profile while resource
admission is pending. [Mechanism audit and preparation](docs/research/halogen0191-mtp-next-mechanisms-20261107.md).

Earlier two-slot/2048 API observations used the synthetic 8K fixture and natural
16K fixture. Their prefill/decode means were **1191.85 / 46.62 tok/s** and
**1125.72 / 48.98 tok/s**, with native head acceptance **56.78% / 65.42%**.
Each case excluded one warmup and included three measurements. The report
retains paired Windows QPC whole-request clocks, the unavailable OEM mode
readback and the separate one-slot/8192-arena admission failure.
[Earlier 0.19.1 API observations](docs/benchmarks/halogen0191-natural-8k16k-20261107.md).

[Halogen 0.18.22, independently captured frozen 8K/16K inputs](docs/benchmarks/halogen01822-raw-8k16k-20261101.md)
records **1917.24 / 55.17 tok/s** prefill/decode at 8192 actual input tokens
and **1913.00 / 46.86 tok/s** at 16384, with native head acceptance
**66.04% / 52.68%**. Each row excludes a warmup and averages three runs.
All direct RAW phase brackets fit the paired Windows QPC whole-request times.
Native timing agrees within these cohorts; the earlier API-only clock
counterexamples remain historical evidence. No new maximum or causal
engine-version speedup is claimed. That 1 November record includes its
normal-profile restoration snapshot.

The later [paired 16K workspace comparison](docs/benchmarks/halogen01822-arena16384-20261101.md)
completed before/candidate/after controls and rejected the larger workspace:
the 16K answer changed and acceptance fell to 49.12%. Paired 8192 was selected for that historical cohort;
the report retains all six rows rather than selecting a new maximum.

[Halogen 0.18.22, 1 November](docs/benchmarks/halogen01822-natural-8k16k-20261101.md)
records complete 8K/16K cohorts before and after restoring the separately
verified OEM Performance mode. Complete HTTP means fell from 9.2516 to 6.8961
seconds and from 16.7409 to 11.9060 seconds. Native head acceptance remains
66.04% / 52.68%. API phase durations exceed whole HTTP time in the Performance
window, so those reported token rates are provisional; no new RAW best result
or engine-version speedup is claimed. That dated run ended with serving online. The historical
`MeasuredText32K` preset still selects 0.18.16.

[Halogen 0.18.16, frozen 8K/16K inputs](docs/benchmarks/halogen01816-natural-8k16k-20261026-evening.md)
records **2033.12 / 56.93 tok/s** prefill/decode at 8192 actual input tokens
and **2002.08 / 49.63 tok/s** at 16384. Native head acceptance was **66.04%**
and **52.68%**. These are directly observed RAW phase rates; the 8K native API
reported 1876.97 / 52.47 tok/s. The report preserves both clocks and the exact
workloads. The subsequent [native policy campaign](docs/benchmarks/halogen01816-native-policy-campaign-20261026.json)
did not qualify gate 0.95, gate 0.85 or PLD `3,7` for promotion.

[Native CPU ASR, 27 October](docs/local-voice/native-asr-component-20261027.md)
records one synthetic C-ABI qualification and a separate synthetic TTS-to-ASR
HTTP check. These component timings do not establish phone-call quality or
change the Halogen serving results above.

The [27 October worktree consolidation](docs/integration/worktree-consolidation-20261027.md)
records the integrated histories, E: checkout comparison, validation and retained
private runtime assets. Integrating experimental source does not enable it.

The [physical cleanup follow-up](docs/integration/worktree-cleanup-20261027.md)
records actual directory removal, preserved assets and measured disk space.

[Native Windows Hipfire, 18 October 2026](docs/benchmarks/hipfire-native-windows-20261018.md)
records the full model cohort, dedicated-memory repair, native phase conventions and retained historical best values.

[Halogen 0.16.2, GUFO and PROJFIX sampled comparison](docs/benchmarks/strix-alloy-article-comparison-20261003.md)
includes filled-context timing, MTP acceptance, coding results and the retained PROJFIX reserve stop.
[The matched lookup-thread experiment](docs/benchmarks/halogen0162-gather-20261004.md)
separates the warm file-cache effect from thread tuning.
[The selected-ten-expert ONNX prototype](docs/research/halogen-npu-top10-20261004.md)
records sparse conversion and provider qualification; it does not implement online Halogen MTP offload.

[Halogen placement investigation and fresh baselines](docs/benchmarks/halogen-placement-baseline-20261001.md) records measured PP512/PP2048/PP8192 rates and the supplementary 16 GiB reserve target; no new optimization was promoted.

[PROJFIX decode restored](docs/integration/projfix-decode-restored-20261001.md) records the measured placement fix and output checks. The [initial recovery report](docs/integration/projfix-recovery-20261001.md) preserves the earlier slow and failed configurations.

[Article-format filled-context and display-driver comparison](docs/benchmarks/strix-alloy-article-driver-comparison-20260930.md)
separates completed three-turn measurements, short-prompt before/after controls, and failed or non-comparable configurations.

[Latest-SDK numerical validation and PP512/PP2048 measurements](docs/integration/gufo-latest-sdk-20260930.md)
include the controlled compiler/runtime matrix, unchanged numerical tests and the new AMD driver.

[Current w4b/v2 PP512, PP2048 and 262K results](docs/benchmarks/halogen0151-v2-262k-20260930.md)
include raw and clock-calibrated rates, memory observations and gateway overhead.
[Reproduction scripts](scripts/benchmarks/README.md) and the
[source-by-source research review](docs/integration/unified-review-20260930.md)
separate measured changes from unqualified ideas.
[Prefix-cache behavior and GUFO diagnostics](docs/benchmarks/halogen-cache-gufo-followup-20260930.md)
show where cache reuse works, where it still misses, and the remaining native-engine gates.

The [earlier 0.15.0 benchmark](docs/benchmarks/halogen0150-pp2048-20260929.md) remains
a historical baseline, including its previously refused 262K admission; it is not the current limit.
The read-only `app/select-backend.ps1` remains discovery, not the managed launcher.

## Published native Windows backend

The remainder of this page describes the existing native v0.1.1 package, not
Halogen, GUFO, or a new combined binary download.

The native release below remains v0.1.1. For the retained repository layout
and historical backend qualification notes, see
[backends and limitations](docs/user/backends.md).

Windows-native Qwen inference on AMD Strix Halo, built on [pwilkin's `llama.cpp` fork](https://github.com/pwilkin/llama.cpp/tree/strix-halo).

### What this is

An experimental Windows package for running **Qwen3.8-Flash-Next** locally on an AMD Strix Halo APU — the Ryzen AI Max / Max+ 300 series with a Radeon 8060S (`gfx1151`, RDNA 3.5). No Linux, no WSL, no CUDA, no datacenter GPU. It runs the model on the machine under your desk while you use Windows for everything else.

Scope is deliberately narrow: one model family, one GPU architecture, one operating system, measured on one box — stated plainly rather than generalised.

### Why I built it

My old desktop stopped working. It was still on DDR3, and rather than rebuild around it I bought a **BOSGAME M5 with 128 GB of unified memory**. I still have an **RTX 2070 SUPER** I want to put back to use.

The M5 is also my everyday Windows PC. I want to work on it, develop on it and play games — not turn it into a dedicated Linux inference server. That is the whole reason for this project.

I am also building **REV:N**, an AI-driven GTA V / FiveM project, and it needs local models. `strix-alloy` is the local-inference side of that work, not the game itself.

**The plan I am working toward** is the M5's 8060S handling inference and the RTX 2070 SUPER acting as an eGPU for games, with Windows available throughout. **That is a goal, not a validated result.** Nothing in this release uses a second GPU, and simultaneous gaming plus inference has not been tested. The numbers below are inference-only.

### Download and run

strix-alloy documents and distributes the tested llama.cpp configuration and Windows HIP changes used to run Qwen3.8-Flash-Next on Strix Halo. Download the external GGUF files, optionally add the matching MTP sidecar, and load them with a compatible llama-server using your normal model-launch workflow. Use the server's existing web UI or your preferred client. **No separate strix-alloy application is required** - the package is a llama.cpp runtime plus one launch script.

| Item | Required? | Source | Use |
| --- | --- | --- | --- |
| Qwen3.8-Flash-Next PROJFIX GGUF shards (9 files, ~100 GB) | Yes | [ilintar/qwen3.8-flash-next-gguf-strix-halo](https://huggingface.co/ilintar/qwen3.8-flash-next-gguf-strix-halo) - `Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf` … `-00009-of-00009.gguf` | Start shard 1 with the compatible server |
| Matching shared MTP sidecar (2.6 GiB) | Optional | Same repo: [`mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf`](https://huggingface.co/ilintar/qwen3.8-flash-next-gguf-strix-halo/resolve/main/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf) | Enables the tested MTP flags. The gain is **workload-dependent** - it is largest on short-context instructed decoding and shrinks as context grows; the measured figures are in [Current numbers](#current-numbers) below |
| Windows llama.cpp runtime (HIP/ROCm) | Only if your existing runtime lacks the model or shared-MTP support | The [v0.1.1 release](https://github.com/MKM-030/strix-alloy/releases/tag/v0.1.1) archive (v0.1.0 is superseded), or build from source with [`setup/`](setup/) | The same normal `llama-server` workflow |

Weights stay on your disk and are never bundled or auto-downloaded; the upstream repo is Apache-2.0 and the files are unchanged from the publisher (verified by size and SHA-256, see [`config/model-manifest.example.json`](config/model-manifest.example.json)). No separate tokenizer or PLE file is needed.

```powershell
# 1. fetch the weights (native -hf loading is not used; download first, then point -m at shard 1)
hf download ilintar/qwen3.8-flash-next-gguf-strix-halo `
  --include "Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-*.gguf" `
  --local-dir C:\AI\models\qwen38-flash\projfix

# 2. start the server - this is the whole command, no wrapper and no config file
& .\runtime\llama-server.exe `
  -m C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf `
  --alias Qwen3.8-Flash-Next -dev ROCm0 -ngl 99 -fa on -fit off --load-mode none `
  -ctk f16 -ctv f16 -c 32768 -b 2048 -ub 2048 --parallel 1 `
  --host 127.0.0.1 --port 8826 --seed 1234 --jinja
#    append for the MTP profile:
#      -md <path>\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf
#      --spec-type draft-mtp --spec-draft-device ROCm0 --spec-draft-ngl 99 --spec-draft-n-max 2
```

`app/launch-flash-next.ps1` is a thin template around that command - it checks the shard set is complete, refuses to start a second copy on an occupied port, and prints the command it runs. Use it or ignore it; it is an ordinary server window that stops when closed.

```powershell
.\app\launch-flash-next.ps1 -ModelDir <dir> [-DraftPath <sidecar.gguf>]
.\app\launch-flash-next.ps1 -PrintOnly -ModelDir <same>   # show the command, start nothing
.\app\launch-flash-next.ps1 -Stop                         # stop it again
```

Once ready, the server's own chat page is at `http://127.0.0.1:8826` and the OpenAI-compatible API is `http://127.0.0.1:8826/v1`, model id `Qwen3.8-Flash-Next` - point LM Studio, Z Code or a `curl` at it. Note that importing the GGUF into another runtime (LM Studio, Ollama, a stock llama.cpp build) does **not** bring these kernels or this flag set with it; the same weights on a different runtime are a different measurement.

For desktop use, the [client connection guide](docs/user/client-connections.md) covers the corrected shortcut, optional `-OpenBrowser`, ZCode and Unsloth setup, and the current Codex compatibility status. No agent flag is required to connect an API client.

**Set your GPU carve first.** In BIOS/UEFI, reserve **96 GB** as dedicated graphics memory. The model needs about 72 GB of device memory. A small carve loads but runs several times slower; a 0.5 GB carve will not load. The carve is a reservation of system RAM, **not** a separate memory bank and **not** isolation.

Full details, troubleshooting and uninstall: **[docs/user/README.md](docs/user/README.md)**. You do **not** need a compiler, the ROCm SDK, Git or Python to run the runtime - those are only needed to build it from source.

### Current numbers

Published measurements, 17 September 2026. Native Windows HIP, TheRock SDK, IQ4_NL "PROJFIX", 96 GB carve. MTP runs use a shared Q8_0 draft head.

| Measurement | Result | Conditions |
|---|---:|---|
| Synthetic serial, `llama-bench tg128` | **31.49 ± 0.17 t/s** | No drafter; pseudorandom token inputs |
| Synthetic prefill, `pp16384` | **892.59 ± 22.50 t/s** | Batch and microbatch 16384 |
| Served serial decode | **28.3 t/s** | 16,384-token context; no drafter |
| Served MTP decode | **45.31 t/s** | Warm median, one 259-token instructed prompt; draft depth two |
| Served MTP, long-context ladder | **31.0–32.8 t/s** | Separate tests at 16,384–251,904 occupied tokens |
| Maximum-prefill serving setup | **1,031 t/s at 16k; 812 at 251,904** | Warm, no drafter, microbatch 16384 |

`±` is sample standard deviation. These are **different workloads and configurations**, not one combined performance promise — 31.49 without speculation and 45.31 with MTP do not measure the same thing.

For context, on speculative serving Halogen publishes 45.3 t/s (mean over ten prompt shapes) and CIRU 44.53 t/s on a 12,960-token replay. Our 45.31 is one prompt's median, so a tie is not established. The [full comparison](docs/benchmarks/engine-comparison.md) separates synthetic, served-serial, MTP and prefill results with pinned sources; the [claim ledger](docs/benchmarks/CLAIM-LEDGER.md) records every correction, including figures I had to withdraw.

### Requirements and honest limitations

- **Tested configuration:** one Ryzen AI Max+ 395 / Radeon 8060S box, Windows 11, 128 GB unified memory, 96 GB carve. Other Strix Halo variants are untested.
- **Models are external.** Nothing is bundled and nothing is downloaded automatically.
- **The 96 GB carve is not isolation.** It reserves part of the same physical RAM Windows uses.
- **The eGPU / simultaneous gaming setup is unvalidated** and is not part of this release.
- **Open correctness items remain:** state handling after partial draft acceptance, and full multi-turn / long-context quality validation. Completing a 251k request shows capacity, not accuracy. Speculative decoding is not guaranteed bit-identical to serial decoding in the first ~2050 tokens.

### Credits and collaboration

Built on [pwilkin / ilintar](https://github.com/pwilkin/llama.cpp)'s `strix-halo` engine and its Qwen kernels and PROJFIX quantization; on [llama.cpp](https://github.com/ggml-org/llama.cpp); on [Qwen](https://github.com/QwenLM)'s model; and on [AMD's TheRock](https://github.com/ROCm/TheRock) HIP SDK. I learned from [Halogen / peonist-ai](https://github.com/peonist-ai/halogen-flash-server), [CIRU](https://github.com/ciru-ai/Qwen3.8-Flash-CIRU-STRIX-IU4), [olliehm](https://github.com/olliehm/qwen-flash-next-windows), [myhacsint](https://github.com/myhacsint/llama.cpp), [stew675](https://github.com/stew675/llama-cpp-rdna-boosts), [SixVolts](https://github.com/SixVolts/llama-halo-hybrid), [halo-box](https://github.com/halo-box/strix-llama.cpp), [drluoto](https://github.com/drluoto/llama.cpp) and the r/StrixHalo community. [Full credits](docs/CREDITS.md).

Most of the kernel work is theirs. My contribution is the Windows integration, local patches, tested configurations and the measurement trail. I am not trying to beat these projects — I would rather share findings and patches with them.

### Developers and researchers

- **Build from source:** [`setup/README.md`](setup/README.md) creates a fresh engine checkout at the pinned base revision, applies the ordered [patch series](engine-patches/) and builds with checked exit codes.
- **Benchmark evidence and kernel experiments:** [`docs/benchmarks/`](docs/benchmarks/) - including negative results and retractions.
- **Reproduce the runtime archive:** [`packaging/build-release.ps1`](packaging/build-release.ps1).

**Maintenance status:** the published native package remains v0.1.1. Local backend
integration and controlled performance research continue separately; experimental
source and unsuccessful candidates are retained with their qualification limits.
