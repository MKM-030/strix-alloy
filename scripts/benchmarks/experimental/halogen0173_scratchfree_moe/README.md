# Halogen 0.17.3 scratch-free MoE component sources

This source-only experiment prepares a default-off, one-shot capture of one
exact native **N=3 FL** operation and a separate component replay. Capture
forwards the original launch exactly once with its original arguments, including
when capture checks fail. It never loads or substitutes the candidate in
serving. No runtime parity or performance results are included here yet.

## Pins and capture

The engine is pinned to SHA256
`af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7`.
`mapped_pins.h` and `capture_abi.py` describe the mapped native instruction,
registration, launch and argument-layout checks. The private `delivery-seal.json`
pins all 13 existing sources and these separately built artifacts:

| Artifact | SHA256 |
|---|---|
| Capture DSO | `7a4290ac6f697fd764fd5afaab05cffdac234a0b673c647389a8b7db3befaa91` |
| Replay DSO | `7a597d24c5213eafb0c8fa90d824e2aea70038cf1c936f0c5f56695a101612d1` |
| Native reference object | `18937428b544e8a5ef1dae31db97f36136e8cdeca90e6c49458ef831b822a039` |
| `owner512` candidate object | `e75f5b7dbee4f32668c1bd900b10720c910afbd1838389781275580df7932704` |

Keep `ALLOY0173_FL_CAPTURE_ENABLE` unset for default-off operation.
`apply_manifest.py` explicitly composes capture with the normal guarded service,
preserves existing preloads and uses a fresh capture path bound to its run ID.
Residency queries bypass capture. Only the first exact matching launch is
claimed; incomplete captures must be rejected.

The private capture retains the real input, routing, metadata, residual,
selected expert slices and stock output, with complete-header, extent,
task-map and zero-counter checks. It copies at most 25,344,000 selected weight
bytes; the maximum complete capture is 25,419,244 bytes. `capture_format.py`
reports metadata and hashes without publishing tensor payloads.

## Qualification sequence

1. Export one complete private capture before normal owned shutdown. Preserve
   its SHA256, backend run/container identity and the source/artifact seal.
2. Use `invoke_replay.py --check-only` with explicit `--seal`, `--library`,
   `--native`, `--candidate` and `--capture` paths to verify artifact pins and
   capture structure without loading the replay DSO or executing hardware.
3. In a separately controlled hardware run, replay the exact native reference
   first. Require all **7,680 BF16 output values** to match the captured stock
   output bit for bit, with zero counters and intact guards. Then require the same exact
   match for the candidate; either mismatch stops qualification.
4. After parity, retain all **nine measured AB/BA timing pairs**. The initial
   warm-up pair is excluded; each timed batch contains eight launches. Recheck
   both outputs, guards and counters after every pair, require untouched
   candidate scratch and successful cleanup.

Hardware replay remains separate from serving and uses the existing 22 GiB
entry and 18 GiB runtime physical/commit reserve guards. `replay.c` does not make
model/API requests or install a launch hook. Component timing cannot be
converted into tokens per second or claimed as a serving gain. Any later
serving integration requires its own full output/state and complete Prefill/
Decode qualification after these component gates pass.
