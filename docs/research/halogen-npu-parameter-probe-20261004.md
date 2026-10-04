# Tiny NPU runtime-matrix probe — numerical gate failed, 4 October 2026

Compilation and NPU session initialization completed, but the frozen probe
failed its numerical gate during warm-up after two profiled calls. The CPU
baseline passed four warm-ups and 100 measured alternating A/B calls. This run
does **not** qualify changing runtime matrices on the NPU, dynamic expert
routing, or a Halogen speedup. The declared tolerances remain unchanged.

The guarded run is retained at
[parameter-inputs-20261004](C:/AI/halogen-mtp-npu/parameter-inputs-20261004/result.json).
Its overall status is `failed`: fixtures, graph build and CPU exited 0; NPU
exited 1 with an `AssertionError`. There was no timeout, memory abort or guard
error. The NPU stage took 27.632 seconds within its 180-second deadline.

## Measured outcome

Both reports use ORT 1.25.2, one session, the same graph, seed `2026100402`,
identical A/B input hashes and identical independent NumPy-reference hashes.

| Receipt | CPU | NPU |
| --- | --- | --- |
| Numerical gate | Passed | Failed during warm-up |
| Declared tolerance | `rtol=3e-5`, `atol=3e-6` | `rtol=0.03`, `atol=0.003` |
| Session initialization | 4.3561 ms | 25,512.3529 ms, including compilation |
| Completed replay in report | 4 warm-ups + 100 measured calls | No completed warm-up or measurement arrays retained |
| ORT Node profile | 728 events, only `CPUExecutionProvider` | 2 fused events, both `VitisAIExecutionProvider` |
| Qualified measured host-call statistics | Mean 0.047997 ms; median 0.04405 ms; min 0.0415 ms; p95 0.0683 ms | Unavailable |

The maximum CPU absolute error across all 104 calls was
`4.76837158203125e-07`. The NPU assertion reports **21 of 64 output elements
(32.8%)** outside its declared tolerance, maximum absolute difference **among
violations** `0.04092014`, and maximum relative difference **among violations**
`0.7114075`. For example, output `[0,8]` was `0.006134033203125`, while the
reference was `0.021254995837807655`.
See [cpu.json](C:/AI/halogen-mtp-npu/parameter-inputs-20261004/cpu.json) and
[npu.json](C:/AI/halogen-mtp-npu/parameter-inputs-20261004/npu.json).

The retained
[partial NPU profile](C:/AI/halogen-mtp-npu/parameter-inputs-20261004/npu_2026-10-04_02-29-24_174.json)
contains fused Node durations of 1,858 and 528 microseconds, with corresponding
`model_run` durations of 1,940 and 543 microseconds. These two warm-up events
are partial failure evidence, not a successful 100-call timing result or
device-cycle measurement; their durations also exclude fresh host feed copies.
The frozen loop alternates A then B and asserts before appending each completed
row; the reports retain no completed NPU replay arrays.

## Exact graph and timing scope

The eight-operator synthetic graph has ten expert slots, hidden width 64 and
intermediate width 32. Its float32 inputs are `x[1,64]`,
`W_gate_up[10,64,64]`, `W_down[10,32,64]` and
`routing_weights[10,1,1]`; output is `y[1,64]`. Both expert matrices are runtime
graph inputs. The only initializer is the reduction axis. The retained ONNX
artifact is 710 bytes.

Two independently generated A/B sets change all four inputs. The planned
replay was four excluded alternating warm-ups followed by 100 measured
alternating calls, with every output checked against a separate per-expert
NumPy reference. Pre-session fixture checks require stale A/B values for each
individual input to fail the declared tolerance. The maximum A/B reference
output separation is `1.8723664283752441`. CPU completed that replay; NPU
stopped at the numerical gate during warm-up.

The timed region includes fresh contiguous host feed copies and
`session.run` input transfer, execution and output return. It excludes
reference generation, validation, hashing, session initialization and
warm-up. These are host-call timings. Tensor storage is 246,056 bytes per feed
and 492,112 bytes for the two stored sets. The explicit fixture ceiling is
64 MiB; Python, ORT, provider DLL and compiler memory are outside that ceiling
and were monitored through physical and commit headroom.

This probe used no real expert IDs or checkpoint experts. It does not test
full-width Flash-Next, MTP, target-state handoff, rollback, acceptance, or
Halogen end-to-end performance.

## Placement and retained GEMM lowering

The NPU report declares `cpu_fallback_allowed=false`. The retained
[compiler context](C:/AI/halogen-mtp-npu/parameter-inputs-20261004/vitisai-cache/e749261527f417588c9cbb8dd79677dc4ec181e3aca5312083a95002cd29bd46/context.json)
also records `session.disable_cpu_ep_fallback: "1"`. Although the session
provider list includes CPU EP, that list alone is not execution-placement
evidence. Both profiled Node events name VitisAI EP.

The context has one `metaDef`, `vaiml_par_0`, with the four runtime inputs,
all eight graph-node outputs, device `VAIML`, device name `stx` and
`runnerType: "hw"`. This assigns the graph to one hardware runner in the
retained context. It does not measure every internal cycle or exclude
provider-internal host work.

The retained compiler logs explicitly show BFP16 GEMM instantiation and
emulation for this run:

- [npu-stderr.txt:39](C:/AI/halogen-mtp-npu/parameter-inputs-20261004/npu-stderr.txt:39)
  identifies `kernelName=GemmBfp16`;
  [line 44](C:/AI/halogen-mtp-npu/parameter-inputs-20261004/npu-stderr.txt:44)
  serializes its arguments as `bfloat16,0,1,1`; and
  [line 49](C:/AI/halogen-mtp-npu/parameter-inputs-20261004/npu-stderr.txt:49)
  records `config.enable_bfp16_wts val=1`.
- [npu-stdout.txt:7](C:/AI/halogen-mtp-npu/parameter-inputs-20261004/npu-stdout.txt:7)
  records the actual `aieir_be` command with `--aiearch aie2p`,
  `--enable-partition=0:8` and
  `--Xpreproc=-DAIE_API_EMULATE_BFLOAT16_MMUL_WITH_BFP16=1`.

These observations establish retained BFP16 lowering evidence; **they do not
establish the cause of the numerical mismatch**. No per-operator error
isolation or controlled precision comparison was run. The float32 ONNX
interface and profile dtype alone cannot determine internal GEMM arithmetic.

The run used the existing provider copy, with each copied file checked against
the active catalog by the unchanged builder's `verified_provider_copy`
function. The chosen DLL receipt and compiler VFS argument provide path
evidence; live module-path observation was unavailable. No provider
acquisition or modification was performed.

## Guard, cleanup and memory receipts

The guard checked frozen source identities before each stage and during
monitoring, required terminal/idle GPU-controller state and closed known
engine/NPU ports, and launched suspended children in owned Windows jobs before
verifying their identity and resuming them. Stage deadlines were fixtures
30 seconds, graph build 15 seconds, CPU 30 seconds and NPU 180 seconds.

[result.json](C:/AI/halogen-mtp-npu/parameter-inputs-20261004/result.json)
records all four owned jobs closed, with matching terminal exit codes.
[cleanup.json](C:/AI/halogen-mtp-npu/parameter-inputs-20261004/cleanup.json)
records `own_child_handle_closed=true`, `cleanup_error=null` and no guard
errors. The NPU report records provider unregistration, DLL-directory closure
and bootstrap shutdown as true. The retained final GPU-controller state is
`stopped`, with zero active requests; its earlier heartbeat/memory snapshot is
not used for run-memory measurements. Profile/context PID fields are not used
as live process-identity proof; the guard's owned-child identities are retained
separately in the stage receipts.

The guard admitted at 22 GiB and maintained an 18 GiB floor. Its 57 retained
[memory samples](C:/AI/halogen-mtp-npu/parameter-inputs-20261004/memory.jsonl)
span 31.020 seconds, with a maximum adjacent gap of 0.559 seconds. Minimum
available physical memory was **42.97138595581055 GiB**; minimum commit
headroom was **197.4473762512207 GiB**. These sampled minima match cleanup.
The nominal monitor pause was 0.1 seconds, with checks adding execution time;
this is not an exact 10-Hz sampling claim. Final available physical memory was
47,129,489,408 bytes and final commit headroom was 213,066,625,024 bytes.

## Frozen identities and evidence hashes

The audit independently matched all 17 artifact hashes listed in `result.json`
to the retained files. Additional hashes below bind the final result, memory
log and compiler cache. Source identities are recorded in
[identity.json](C:/AI/halogen-mtp-npu/parameter-inputs-20261004/identity.json).

| Frozen source or provider | SHA-256 |
| --- | --- |
| `halogen_npu_parameter_probe.py` | `ddd476b25f6e434b03390fb0974d54f157fcd26492417641a5ed9cc38fa15a1c` |
| `halogen_npu_parameter_guard.py` | `1aff062a0e8a421240651cc644338539e9eaeec624b6c1aa4643a99a20da8e8e` |
| `test_halogen_npu_parameter_probe.py` | `fb3d3bdb3826a6a80f5974eca1606a247c71d3517387ba08742d7ddf6c77c3f2` |
| Unchanged `halogen_npu_expert_onnx.py` builder | `900a4deb32b86a48c6c132bf1326a3174bc5ef11482fd88b98005d0c40a4b722` |
| Provider-copy manifest | `649a90d988b29c7dd4f8b1b57da902d435fb406db13d5a1cc18086907afa83a1` |
| Chosen `onnxruntime_vitisai_ep.dll` | `95fb8d62d424f400a2f5f4e9f4d1ac1affdb35dd8c3309e85339010f50307352` |

| Retained artifact | SHA-256 |
| --- | --- |
| `result.json` | `9787ace99702ffb1879c50f6b4cc3da0dc720f918deeaeeeb9fb76a3a57385d4` |
| `tiny-input-matrices.onnx` | `4190ad34d24b563d0f8ca6a6ed8ef02ed96c475c99bec794719fe8f8c1e29036` |
| `cpu.json` | `2a674030aa90eec083c5eec084b9834ad57cc05c89e21146167131098ad01968` |
| `npu.json` | `184022b7620d7e878ba26088b771b82651e27f03f812b55f03378ffa2af75aa2` |
| `cpu_2026-10-04_02-29-21_677.json` | `09f28117b661d1d228affb4a932c5f5390f13fc00c8ba3212260c564a0d4054c` |
| `npu_2026-10-04_02-29-24_174.json` | `3e1ab651a7a6cc665295953d1036fd9d9a59ac2ea84192a9e62c360220190ac6` |
| `cleanup.json` | `43e6d9ef8194ffa322e3131ea235dee2d34dbe76883f1e72ef54d3cada61e965` |
| `identity.json` | `c20606c0ebb949366ba6b0f8f81aef627b28773c8467aa5c338e870a7cacacf7` |
| `memory.jsonl` | `d896037eff7b0bae47b3a49346355f60cd0176405be70f881dff647bba9caf85` |
| Cache `context.json` | `8336fa86713daf9dcfbad3489ad611d0675351149e90ea445e617fc34f15a04f` |
| Cache `e749261527f417588c9cbb8dd79677dc4ec181e3aca5312083a95002cd29bd46.rai` | `686428bd2bccedd8a1775c0c19a71858912328cf06b0f46ba4aacbe07ca5c905` |
| `npu-stderr.txt` | `2416ecf609e6d73d4ef4b3b175d5aabbc94ddeb8e44fca5858a7de184959419d` |
| `npu-stdout.txt` | `851107c547587a8c9d9e650b3ff21baff61a901cdc64483ce30b0b57a1806474` |

Earlier preparation evidence is separate: two focused CPU fixtures passed,
and an unguarded CPU preflight completed 100 alternating calls with mean
host-call time 0.049733 ms. Its receipt is
[parameter-preflight-20261004/cpu.json](C:/AI/halogen-mtp-npu/parameter-preflight-20261004/cpu.json).
The guarded CPU mean reported above is 0.047997 ms. Neither CPU result
qualifies the failed NPU replay.

This final audit used retained artifacts only and changed this document only.
The probe, guard and fixtures remain frozen. No hardware rerun, tolerance
change, checkpoint read, installation, provider change or global setting
change was performed by the audit.
