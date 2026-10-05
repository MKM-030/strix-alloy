# First real independent NPU proposer screen

The direct raw-ID Qwen3.5-0.8B adapter compiled, loaded the pinned language weights and completed one finite NPU screen. This establishes an actual prediction boundary; it does **not** establish higher Halogen throughput or native acceptance. The candidate remains disabled.

| Observed operation | Result |
|---|---:|
| 512-ID clear/prefill, 15 frozen prefixes, first call included | 418.29 ms mean |
| First 512-ID clear/prefill | 427.46 ms |
| Remaining 14 clear/prefills | 417.63 ms mean |
| Three independent proposals, 14 cases, two consumed forwards | 45.22 ms mean |
| Final two-proposal case, one consumed forward | 22.56 ms |
| Ten authoritative single-token appends after a 256-ID seed | 22.46 ms mean per append |
| Exact sequential prefix matches against captured target continuations | 21 / 44 = 47.73% |
| Independent first ID equals the next captured target ID | 11 / 15 |
| Independent first ID equals the captured native head operand | 10 / 15 |

The 47.73% is an **offline exact-prefix statistic**, not native MTP acceptance. Cases share one held-out request family; overlapping prefixes do not constitute 15 independent documents. Actual PLD-hit eligibility, live opening branches, verification/replay cost and concurrent memory interference were not measured. The first prediction comes from committed logits; three predictions consume two model forwards. Command time includes native logits ownership and greedy selection, and excludes binary snapshot writes. This is a bounded component screen, with no warmup-plus-three full-engine cohort or Halogen tok/s result.

The exact-prefix lengths were `0,0,1,2,2,1,0,2,2,3,1,1,3,3,0`. Seven cases covered the consumed speculative prefix; eight did not. At the tested 512-token retained-window cap, advancement also requires a window rebuild. With a shorter seed, insufficient acceptance still requires a rebuild. The observed 45 ms proposal and hundreds of milliseconds for rebuild give no reason to attach this synchronous candidate to the running engine or start a new engine cohort.

Initialization took 17.00 ms for device/manager, 103.11 ms for the model constructor and 2,352.24 ms for Q4NX loading/release. Installed XRT NPU2 device 0 and the pinned FLM 1.0.7 XRT DLL were used through the public C++ interface. Logical history is limited to 512; the DLL requests at least 4,096 device capacity. This does not claim a 512-token device allocation.

The model is `FastFlowLM/Qwen3.5-0.8B-NPU2`, immutable revision `1d16e5eaa2508889fb88eb1bfab1921a30a1a466`, package branch `flm_q4k_high_precision`. The language payload is 560,985,936 bytes, SHA256 `787428ffe87be5e3e5a8fcaf241844b69896ca0c74a41f2432c436739f7ba4e4`. These are separate proposer weights; no target-model weights were separated or changed. Shared defined IDs 0–248069 were used directly, without a chat template or future labels as prediction inputs.

## State-path comparison

After ten count-one proposals with authoritative corrections, both append and fresh complete prefill retained the same 266 IDs. Their greedy next ID was 6574. However, **242,884 / 248,070 BF16 logit words differed**, with maximum absolute difference 1.94140625. Immutable row hashes and the difference summary are retained in JSON. Exact row parity was not achieved; no tolerance was relaxed. Sequential-forward versus parallel-prefill differences alone do not establish their cause or qualify the live append path. No checkpoint restoration was used.

## GPU and CPU applicability

The raw-ID proposer and authoritative append mechanism can use GPU or CPU too. Each needs a compatible real model/runtime boundary, state qualification and measured proposal/rebuild costs. A GPU proposer competes with Halogen for compute and shared DDR; CPU execution can compete with host scheduling. Neither inherits NPU timing or a speed claim. This mechanism targets Decode and supplies no direct ordinary Prefill gain. The previous BF16 GPU H sibling remains disabled after its separate negative paired screen.

## Evidence and lifecycle

[JSON evidence](halogen-npu-independent-proposer-screen-20261006.json), [frozen workload](halogen-independent-proposer-workload-20261006.json), [native bridge](../../scripts/benchmarks/halogen_flm_raw_id_bridge/bridge.cpp), [reference append](halogen-pld-append-reference-20261006.json).

Root compiled MSVC C++20 with `/Zc:__cplusplus`, using the isolated [official XRT 2.21.75 SDK](https://github.com/Xilinx/XRT/releases/tag/2.21.75). One initial compile selected the old-language Boost branch because MSVC did not report its selected standard; that flag corrected the condition. No SDK runtime was installed and no driver, BIOS, voltage or global WSL setting was changed.

The original GPU server was stopped normally with PID, creation time, run IDs, container and profile verified. The native screen completed in 10.59 seconds; its owned job closed. Minimum physical and commit reserves during the screen were 43.85 GiB and 198.70 GiB. Restoration used the unchanged 44/131-GiB admission and stable-60 requirement. The exact receipt and fresh running identities are maintained in `continuation-current.json`. The server is ready and remains open. The full acceleration goal is unachieved.
