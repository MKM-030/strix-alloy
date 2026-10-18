# Halogen 0.18.1 source preparation — 12 October 2026

**The separate source package, fresh demand-seam map, exact API/entrypoint transforms and four actual CPU products are sealed. Installation subsequently completed; actual engine-provider/runtime qualification remains pending.** Root owns installation, all hardware/lifecycle activity and production integration. The last normal start failed before engine creation at about 30.74 GiB available physical against the unchanged 35 GiB startup floor. Source/CPU preparation does not relax that floor.

The [source scout](halogen-driver-update-check-20261012.md) identifies short-request scheduling between prefill chunks, queued human-request precedence, sampled structured output, `prompt_cache_policy: "no_store"`, fork mapping and retry grace. Checkpoints are unchanged according to upstream; no new native decode-rate claim is made. One-request gateway concurrency limits what the scheduler claim can establish under the retained policy.

| Exact 0.18.1 identity | Value |
|---|---|
| Immutable Linux/amd64 image | `ghcr.io/peonist-ai/halogen-flash-server@sha256:f0b39c8908f9897f27ab0a64e964c775e136a7cf7a1bafeb4de0c6d5d1e07e29` |
| Revision / image config digest | `b540030f8abf` / `sha256:0e25efcf50355f12d19947dd95e1b2555b0bed7f3c56e2b9611a8efd5e08ab9f` |
| Image creation metadata | `2026-10-11T19:01:31.127013509Z`; build metadata, not established publication time |
| Engine | 27,096,728 bytes; `d946e7b32a46400884ee7309b909da73f4a6586140cd9f9b94fa9ff583b3c3ab` |
| Upstream entrypoint | 76,874 bytes; `6391eddbd56cc42f1f769c29875ec0357636c66eeb2c8bb0889ffb28b55dd77e` |
| Upstream API | 247,632 bytes; `07cfe472bebee13e19c129ddc8e7fe0359a1e4d261101b78e5a1ba7b40367cdc` |
| HIP header | 476,246 bytes; `a075feec4c32d01b35dfe97e01ef7b55aa62bac7b7590ca7cefc2564668aa6a2` |

Root's metadata/extraction receipts are under `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/halogen0180-normal-bridge-preparation-20261011/halogen0181-{public-metadata,extracted}-20261012/`. Owned extraction containers were closed and removed by root. This source worker performed no container or device operation.

## Fresh map and transformations

The unique 22-byte hook is newly located at **RVA `0x1976780` / file `0x1975780`**. Fresh FDE bounds are RVA `[0x1976140,0x197713c)`, file `[0x1975140,0x197613c)`, with function SHA256 `4b671ff38ae46413c83fbcbbbb8c1ae84d5e98df98eed4618fa0db45f9122d82`. Resume is `0x1976785`; native unsigned rejection is `0x1976f91`.

All eight complete mapped functions retain normalized instruction bytes, 101 literal/import identities, direct-call targets, branch geometry and CFI. The closure has 7,573 bytes and 1,868 instructions, with no AVX/YMM/ZMM/opmask instructions. The measured `+0x4810` code/BSS shift applies only to this closure. Stack/register/flags and FXSAVE64 trampoline offsets are unchanged; trampoline and planner header bytes are retained exactly. Indirect callbacks, actual ranges, forced unwind and runtime remain outside the proof. [Detailed map](../../server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/halogen0181-seam-map-20261012/abi-map.md).

The entrypoint still has one exact `host_preflight` delimiter pair and an unchanged native block. The adapted entrypoint preserves all other upstream bytes: 78,140 bytes, SHA256 `26503194fb141530a8932f89db60aa87e769bfc3a954b913f0fa9e986709c2dd`. Replacing exactly five API launch paths gives the 78,115-byte service entrypoint, SHA256 `1cb87e479117c32c620b58f63233bbf1aaeb8bfa352cf7622a9d9e3829182ba4`.

The new bearer wrapper binds the complete API hash. Authentication, typed defaults, request precedence, effort mapping and forced-tool thinking suppression retain their source contracts; added uvicorn protocol arguments pass through the wrapper. The three companion tool files are byte-identical to 0.18.0. **Cancellation changed:** eligible disconnected requests can retain a slot and up to 16 MiB retry buffer for the native default 20 seconds. Cache Off and `no_store` do not disable this eligibility. Root must qualify cancellation, retry and cleanup; no override, fork/cache feature or concurrency expansion was enabled here.

## Sealed source and CPU scope

The [new package](../../backends/halogen-wsl2-0.18.1/README.md) rebinds version/profile/probe/library identifiers, health expectations and exact engine/function/API/entrypoint pins. Its source manifest includes **41 files**, including the preparation receipt and README; `.local`, credentials, installed products and live profiles were not copied. Old 0.18.0 files and pins remain unchanged.

| Frozen handoff | SHA256 |
|---|---|
| `profiles/sources.json` | `a35a376365d8cac9a256546f763ace11df17fcf166e62688ea8a062fea42dc5a` |
| `profiles/release.json` | `d350e258c5264b0b3464b4dd3c6802fd62d55daeeec23ec60e90968688dd4781` |
| `preparation.json` | `b44d966535b15c10604f77a297f1191857b6445e8d75501df5a1d94fddb4c530` |
| Fresh static map | `c7b303ff85b73b336c9d61b70379f531c48a1e5c21a7c8f13c151a6587d6a342` |
| Root actual CPU build receipt | `e96907592f5a60bf2a56c1efffd0286812f88438f7e3b7ba2495564cf5223b9a` |
| Root CPU image-provider receipt | `9600197ef18d9bfb0fedf45806963affd870613a3f5757cd39d7082d7c20ddf6` |

Root compiled four products with GCC 13.3.0 and executed none. Exact pins are ordinary bridge `6d8c0bf96ae52d0b769bca7c27b64cc668ef7cf902d85518b8ef632f62de4164`, v2 bridge `182125d5df8ca3de18d27c4def6e319baa3a396e886b4e585fb5136e3fabfdea`, private registration `05e1f083afaa659823149ab5b274cfeee691244f5ffed332fbdc5be84eabe8e1`, and probe `d24e64b7dc86482917aca2915165691d60a6d3ec02e4b6e28894ea7ae216e13a`. All 148 include files match the new image's include manifest. Root separately proved CPU image HIP/crypto/libstdc++ provider and loader identity. Actual engine-provider binding is explicitly false.

`cpu_build_pending` is now false; normal runtime/production qualification remains false. The postbuild source-finalization receipt proves compiled inputs unchanged; only release/preparation metadata and source documentation changed after the build. Historical pending-pin receipts and the exact build inputs remain preserved.

## Root-reviewed installation handoff and completion

The original `root-install.json` records a failed credential provisioning attempt, retained unchanged. `root-install-credential-recovery.json` subsequently records `installed=true`, protected matching credential ACLs, preserved model identities, `engine_started=false` and `runtime_qualified=false`. The recovery helper restricted **only its native PowerShell 5.1 child** to the system PS5.1 module directory; no global module setting changed and no credential bytes or hashes were printed. The completed version-local install manifest is `backends/halogen-wsl2-0.18.1/.local/install-manifest.json`.

The controller, manager and PowerShell starter now accept explicit 0.18.1 selection. Native PowerShell 5.1 `PrintOnly` passed; the starter default remains 0.18.0 / Current4K until live qualification. The following paragraphs preserve the original source/install handoff scope.

`PREP/halogen0181-seam-map-20261012/root_install.py` is prepared, SHA256 `874ee71c812cb14c441cd0f2697f072463889fa35fe38a83bcf525d4578fc08c`. Its no-flag mode passed local source/CPU/provider checks with zero external calls, old asset metadata reads or credential access. Root reviews the frozen helper before explicitly adding `--run`.

The helper uses the ordinary version-local installer with **native Windows PowerShell 5.1** and absolute `C:\Windows\System32\wsl.exe`. It reuses the existing 0.18.0 machine's model/tokenizer/lookup locations and complete-file receipts only after exact pre/post file-identity gates; it adds no huge hash or model download. It preserves the old protected backend-token ACL before copying secret bytes to the new separate backend path. Token bytes and hashes are excluded from logs/receipts. The persistent public **8840** endpoint and `server/.local/servicenow-api-token.txt` remain separate and unchanged. The helper does not start an engine, change production selection or alter controller/manage/launcher/STATE.

After root installs, actual engine-provider binding, startup/health, disconnected-request cleanup, lease cleanup and recovery remain required. Explicit 0.18.1 production selection requires root's separate integration because existing manage/starter interfaces exclude it. The serving target preserves v2/full262 context/slot/KV capacity, one slot, fixed MTP2, PLD `3,3`, Cache Off, paired prefill/arena 4,096, Thinking On/medium/2,048 and SDMA 1. Startup remains **35/131 GiB** with **10 consecutive safe seconds**, startup/runtime reserve **18/18 GiB**, and long-measurement entry **22/22 GiB**, with immediate checks, timeout and recovery unchanged. No phase-clock, speed, acceptance or current serving-fit claim follows from this source/CPU handoff.
