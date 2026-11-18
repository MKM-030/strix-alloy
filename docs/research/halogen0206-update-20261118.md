# Halogen 0.20.6 update evidence - 18 November 2026

**Historical run `f19220518d3040368449a89b6a116b51` qualified its exact Halogen 0.20.6 source and r2 bridge revision in the managed one-slot 32K text profile.** Later bridge development changed the current 0.20.6 package to hybrid source `946f1885...` and V2 bridge `56e0c4ac...`; that evolved revision was not rerun and is not runtime-qualified. This retained record applies only to the source and bridge pins named below. Halogen 0.20.7 superseded it later on 18 November 2026. The qualified historical instance was subsequently stopped by the managed lifecycle after physical memory fell below the required 18 GiB runtime reserve, not because of a bridge or engine failure. The bounded authenticated request is a functional check, not a performance benchmark. The machine-readable evidence is [halogen0206-update-20261118.json](halogen0206-update-20261118.json).

## Official identity

The [annotated tag](https://api.github.com/repos/peonist-ai/halogen-flash-server/git/tags/aabf3338ff3f53de456647ecbaf2e3410fa3a4e3) `v0.20.6` was made at `2026-11-16T13:24:58Z`, points to public commit `e4ef9b381dcdaa99cffb2ace709f8d3762dede97`, and has tag-object SHA `aabf3338ff3f53de456647ecbaf2e3410fa3a4e3`. GitHub reports the tag unsigned. The [formal releases collection](https://api.github.com/repos/peonist-ai/halogen-flash-server/releases) was empty at the check; there are no formal GitHub Release assets in that collection. OCI signature availability was not established.

Fresh registry reads found both `0.20.6` and `latest` at:

- Image: `ghcr.io/peonist-ai/halogen-flash-server@sha256:f68892a56d8a1182645042574d702374bff402bb986ec4d49304cbe89483dbaf`.
- Config SHA-256: `3f5f2337842b8003f9826e226adcd4ad4a620dd3ed2e3f780dfb9f00dae4dfa6`.
- Image creation: `2026-11-16T08:33:46.643028366Z`; internal revision label: `109f0b78e221`, distinct from the public commit.
- Platform/runtime: Linux amd64, ROCm 10.1.0, Python 3.12.15; 26 layers totaling 946,110,773 compressed bytes.

Raw manifest and config bytes independently matched their registry digests. Sources: [official package](https://github.com/peonist-ai/halogen-flash-server/pkgs/container/halogen-flash-server), [registry manifest](https://ghcr.io/v2/peonist-ai/halogen-flash-server/manifests/0.20.6). The capture retains those raw bytes.

## Passive capture and ownership

The capture ran from `2026-11-18T10:23:36.712309+00:00` to `2026-11-18T10:27:46.636941+00:00`. Its terminal receipt reports completion, with no engine start, model load or accelerator-provider invocation. The extraction container was created but never started, and was removed after ownership and stopped-state checks. The before/after process snapshot preserves the same foreign `llama-server.exe` PID 2928 and its creation identity; Halogen remained offline. These are capture-receipt observations, not claims about inference behavior.

- Evidence directory: `server/.local/halogen-update-20261118/primary0206/capture`.
- Owner: `dec8eab72b49434f88313ed51a2ab624`.
- Container: `codex-extract0206-dec8eab72b49434f88313ed51a2ab624`.
- Container ID: `48129a3537beefc02c120522ee100e9bc8a2500f250a8318d91e5eb41eaf687d`.
- Receipt SHA-256: `58206037ece95debd8863b177b0add241609c8359667f30f012c704eb4935041`.
- Capture-contract SHA-256: `55c5f53a2bc5ffc4598c49465be167761ed931dde4b5c986822c01d42939e9d7`.
- Minimum sampled Windows free physical/commit memory during capture: 30.310/154.184 GiB. These values do not establish runtime capacity.

| Captured artifact | Bytes | SHA-256 |
|---|---:|---|
| flash_serve | 38092616 | `3ed02d3fd6bda4851995e4295c1edd749655a095d997db03955da9052ee8647e` |
| entrypoint-upstream.sh | 100721 | `20ae62fab27b73593d0c90246419279aa6aee2df5930071b2a4aadfecbabdebd` |
| serve_api.py | 346839 | `71240612de5013fa49780de9243adbf60516afe81729f73aa67f98f9fde75c9f` |

The captured entrypoint matches the pinned public source hash. The engine, entrypoint and API differ from the local 0.20.3 release pins. `request_records.py`, `halogen_tools.py`, `tool_parse.py`, the HIP runtime header and the captured HIP/OpenSSL/libstdc++ providers match those old pins. The JSON records every full artifact hash. Equality of those files does not prove a stable engine ABI, a complete transitive dependency match, or which providers a future engine actually loads.

## Changes reported upstream

The following are manufacturer claims from the [pinned changelog](https://github.com/peonist-ai/halogen-flash-server/blob/e4ef9b381dcdaa99cffb2ace709f8d3762dede97/CHANGELOG.md) and [0.20.3-to-0.20.6 comparison](https://github.com/peonist-ai/halogen-flash-server/compare/v0.20.3...v0.20.6); none was measured locally here.

- **0.20.4:** cached short follow-up prompts read 15-50% faster, and 16 simultaneous requests gain about 10-20% total throughput. `tool_choice: "none"` is respected after earlier tool calls.
- **0.20.5:** concurrent decoding gets faster and saved state gets smaller; old disk prompt caches rebuild. Tokenization follows the checkpoint's native pattern for combining-mark scripts. Fixes cover structured JSON, dynamic Claude Code tools, unloaded Halogen model names and unmatched kept-state reuse. The NPU image runtime moves to XRT 2.27.
- **0.20.6:** a new draft head reportedly improves single-request decode by about 4%, image encoding by about four times, and an optional mode improves busy-server throughput. Fixes address repeated shared-prefix prefill near 32,768-token boundaries and a rare busy-session error that could resume another conversation's recycled context.

The last fix is a correctness reason to evaluate the update, independent of its speed claims. It does not establish that the local installation encountered the defect.

## Drafter and configuration migration

The new default v2/ht43 draft file is `qwen38-flash-next-drafter-r2.hgn`: **1,523,568,192 bytes**, publisher SHA-256 `07a7b5b358cb02737ecf85043db0d30b4938aed06ae6311772ea4e40b939696b`. The passive capture initially established this identity from [publisher LFS metadata](https://huggingface.co/peonist-ai/halogen-qwen3.8-flash-next/tree/5c72aeff67617168b2a10e707e1477de6a1adb47). The local installation independently matched its complete-file size and SHA-256, and the qualified runtime selected it. The v2 checkpoint's publisher identity remains 66,687,678,432 bytes and SHA-256 `71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687`, matching the local 0.20.3 pin.

`HALOGEN_CK_OVERLAY` now also selects the drafter; `none` keeps the checkpoint's embedded head. The entrypoint selects an adjacent valid r2 file, and fetches it only with `HALOGEN_DOWNLOAD` set and writable storage. The qualified run selected r2 with `HALOGEN_MTP_GATE_RULE=cost`, `HALOGEN_SAMPLED_GATE=cost` and the retained `HALOGEN_MTP_GATE_P=0.90`.

`HALOGEN_DN_STATE=fp32` restores the earlier state arithmetic, and `HALOGEN_TOKENIZER_NATIVE=0` restores earlier tokenization. `HALOGEN_CONC_MODE=1` is opt-in, chosen at process start, and intended for busy servers; it slows one or two requests and is rejected with GGUF, w4b or disabled MTP. These settings must not silently change the local single-slot baseline. [Pinned flags](https://github.com/peonist-ai/halogen-flash-server/blob/e4ef9b381dcdaa99cffb2ace709f8d3762dede97/docs/FLAGS.md).

## Local r2 bridge migration

The installed publisher r2 drafter changes the v2 memory-registration sequence. It also makes the upstream entrypoint select `HALOGEN_MTP_GATE_RULE=cost` and `HALOGEN_SAMPLED_GATE=cost`; the launcher's retained `HALOGEN_MTP_GATE_P=0.90` no longer describes the complete active policy. The old embedded-head planner expected one main phase followed only by an optional vision phase. A first controlled 0.20.6 run rejected the changed main shape before copying. A second, narrowly instrumented run accepted that exact main shape, completed its copy and then rejected the previously unknown r2 phase. These failures are migration evidence and are not normal runtime qualification.

| Phase | Mapping bytes | Registered range | Aggregate/copy bytes |
|---|---:|---:|---:|
| Shortened v2 main | 66,687,678,432 | `319488:65164120064` | 65,163,800,576 |
| External r2 drafter | 1,523,568,192 | `4096:1523568192` | 1,523,564,096 |

The combined device-copy demand is 66,687,364,672 bytes, below the retained 68,719,476,736-byte cap. CPU fixtures prove the exact phase order, cardinality and r2 mapping identity checks. The final managed run then completed phase 1 at 65,163,800,576 copied bytes and phase 2 at 66,687,364,672 cumulative copied bytes, both with zero host bytes and no preflight rejection.

The historical qualified `hip-register-hybrid.c` SHA-256 is `010b7bc61befa30bff5cde0b4685cc8bf683208ad27f949b4c1d9c7cbe530548`. Its installed 35,192-byte V2 bridge SHA-256 is `23ef2eea91cb2ce448925cc254812269c9520a42da1feb4882143bedeb040c97`. The current evolved package instead contains source `946f1885350d5b6575df73ce3271cfbac4b709b23c0971d570cbb4673e26e201` and a 35,400-byte bridge `56e0c4ac18bcf839d3c41c88bc64caabdf3251c557fb3fb3e194c3e43031b031`; those later artifacts have no 0.20.6 runtime qualification.

The runtime service manifest proves the selected mounts, environment and exact installed adapter products. It does not enumerate the provider objects actually loaded by the engine, so exact runtime provider binding remains unqualified even though the accelerator-backed engine itself ran successfully.

## Final managed runtime evidence

Run `f19220518d3040368449a89b6a116b51` qualified the exact historical bridge pins above in the managed `CurrentText32K` lifecycle. API and engine both reported 0.20.6. Health reported context, slot context and KV pool of 32768, one slot, Vision Off, Cache Off, paired 8192 prefill controls, PLD `3,3`, gate probability `0.90` and the upstream cost policies. Authenticated `/v1/models` returned `halogen-v2`; a bounded request returned exactly `HALOGEN_0206_READY` with stop finish reason and 25 prompt plus 10 completion tokens.

At qualification time, the Windows gateway controller was PID 1256, creation identity `134394753766623624`, run `1b9895d48df1418b9f12cc4ca6ce6b06`; the backend Halogen controller was PID 4344, creation identity `134394753873114825`, run `f19220518d3040368449a89b6a116b51`. Both were Python 3.12 `python.exe` processes. Container `865b780e63ae37c07b3d5ffd43699b2e655cdc4244570329cbea14bc117e0db4` was ready and port 8840 had one listener. The managed receipt records a minimum 20.16350555419922 GiB physical availability, while the backend service log sampled a 117.94 GiB commit minimum through the bounded request. The ServiceNow session receipt SHA-256 is `637c52f208e92e75f3e8c042d0c1f48c0a9c2ac3ffe2241b85a9525a3aeade2f`. The later reserve-triggered stop preserved this evidence and does not invalidate the completed request or bridge qualification.

The configured default one-slot `CurrentText32K` admission is 30 GiB physical and 124 GiB commit headroom. The 30/131 GiB floor applies when capacity opt-in is explicitly selected. Request-entry and runtime reserves remain 22/22 GiB and 18/18 GiB respectively.

## Platform and qualification boundary

Official 0.20.6 still rejects WSL2 when `/dev/dxg` exists without `/dev/kfd`; its supported GPU path requires Linux KFD/DRI and gfx1151. No stable binary bridge ABI or official Hipfire/Windows compatibility contract was established. The local WSL bridge remains a separately maintained adaptation. [Pinned entrypoint](https://github.com/peonist-ai/halogen-flash-server/blob/e4ef9b381dcdaa99cffb2ace709f8d3762dede97/deploy/entrypoint.sh). NPU operation remains optional, with separate Linux driver, firmware, IOMMU and fabric-clock requirements. [Pinned NPU guide](https://github.com/peonist-ai/halogen-flash-server/blob/e4ef9b381dcdaa99cffb2ace709f8d3762dede97/docs/NPU.md).

The local 0.20.3 adapter's hardcoded engine hashes, offsets and frame contract were not treated as evidence for 0.20.6. The versioned package uses a fresh semantic preflight map and rebased entrypoint/API pins against the exact 0.20.6 inputs. Capture completeness, source migration and runtime qualification remain separate claims. The one-slot 32K text mode is qualified only for the recorded `f192...` source/artifact revision; the current evolved 0.20.6 package, capacity opt-in, two-slot operation and vision remain unqualified, and no local 0.20.6 performance benchmark is claimed.
