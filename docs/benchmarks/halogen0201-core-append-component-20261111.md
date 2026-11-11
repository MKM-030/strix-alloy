# NPU intermediate appends: unused head computation removed

The single native component on 11 November 2026 passes **81 exact endpoints,
20,093,670 BF16 values**, with unchanged numerical tolerance. Omitting the
unused output head on intermediate authoritative tokens reduces mean complete
commit-loop time from **2602.9486 to 1626.4810 ms**, or **37.5139% less time**.
This is an actual NPU component result, **not measured Halogen prefill/decode
tok/s, MTP acceptance or a demonstrated engine speedup**.

| Same 128 observed IDs, eight queued16 commit spans | Head on | Intermediate head skipped |
| --- | ---: | ---: |
| Excluded warmup, ms | 2624.7311 | 1604.3656 |
| Measured run 1, ms | 2605.4473 | 1618.2924 |
| Measured run 2, ms | 2598.4880 | 1617.2262 |
| Measured run 3, ms | 2604.9105 | 1643.9245 |
| Arithmetic mean, ms | 2602.9486 | 1626.4810 |
| Median, ms | 2604.9105 | 1618.2924 |
| Intermediate head computations skipped per run | 0 | 120 |

One engine alternates the two modes over eight timed replays: one excluded
warmup and three measurements per mode. No faster run replaces a slower one.
An additional **unmeasured ninth correctness replay** uses groups `1,2,3,4,6`
within each 16-ID span, skips 88 intermediate heads and contributes nine exact
endpoints. It is excluded from both timing means. Timed replays contribute
72 endpoints; the complete comparison contains 81.

[Numeric export, all runs, provider paths and pinned evidence](halogen0201-core-append-component-20261111.json).

## Actual change and timing boundary

The previous append-only path omitted intermediate host row copies and
snapshots but still computed every NPU vocabulary head. The new default-off
bridge temporarily suppresses only the exact six-byte head start/wait calls
at FLM 1.0.12 Qwen DLL RVAs `0x58358` and `0x58393`. It retains scalar layer
execution and completion, **both BO synchronizations**, context advancement,
the final row-producing forward and all native state ownership. This first
candidate isolates unused matrix computation rather than removing readback
and computation together.

The head command reads hidden input and weights and writes logits; its checked
DDR command construction has no recurrent/KV write. Actual endpoint comparison
qualifies this finite execution despite the remaining general AIE scratch/control
questions. Intermediate returned logits are discarded. Every endpoint still
contains the complete owned **248070-word shared-vocabulary** row from a normal
full forward; this is not selected-token agreement or a universal model-quality
claim.

Windows QPC brackets each complete commit span. The totals include authority
validation, scalar native calls, code protection/patch/restore/cache-flush work,
final owned-row processing, snapshot allocation/read/free and Python/native
context checks. Startup, seed/reset, endpoint capture, disk writes and offline
comparisons are outside commit timing. These are complete component costs,
not isolated NPU kernel times; dividing 128 by these durations would not produce
measured large-model throughput.

## Frozen input and exact comparison

The input bundle retains an 8192-token document prefix and 128 already observed
target IDs. The small NPU model receives its last **512 prompt IDs**, then the
same 128 true scalar appends through local context **640**. It is a
teacher-forced component replay. No future teacher sequence is supplied to the
GPU server, no speculative preparation is run and no acceptance is measured.

Endpoints at committed counts `0,16,32,48,64,80,96,112,128` are checked for every
replay against the retained direct sequential FLM reference. The independent
closed-file audit rehashes and byte-compares all candidate/reference pairs,
checks all prefix/context bindings and reconstructs finite values and lowest-ID
greedy results for the nine unique reference rows. All **40,187,340 candidate
bytes** match. No tolerance, output row or slower sample is removed.

## Ownership, guards and retained providers

The actual private bridge is 173056 bytes, SHA256
`063bb3f183bfb2d02304942f628950b80e815aa5f9cf4d15db7801304ae625dc`.
The loaded Qwen provider remains
`81b9349b5eb6cc7af277a41fad3a5dd7aa71321a82f8a484e7a980d80c334fad`.
The JSON retains exact actual paths/hashes for that provider, the bridge,
`q4_npu_eXpress.dll` and System32 `xrt_coreutil.dll`; there are no module
observation errors. The installed provider's disk hash is unchanged.

Mode selection checks the actual loaded provider path and full file hash.
The native guard checks mapped PE identity, original instructions and page
permissions. One serial actor/engine owns the scope; foreign-thread, nested
and second-engine use are rejected. Original instructions, execute permissions
and instruction-cache visibility are restored on normal and exception paths.
Restoration failure is terminal and cannot be reported as successful cleanup.
All **568 suppressed head computations** return with restoration confirmed.

Eleven CPU fake-memory guard cases pass. Fifteen separate Python fake-ABI,
qualifier and monitor cases pass under both Python 3.12 and 3.13. Those are CPU
tests, distinct from this actual NPU component. Their original red failures,
header-closure correction, prior receipts and logs remain preserved. This
audit does not relabel the earlier bulk numerical failure or the incomplete
[real NPU engine comparison](halogen0201-real-npu-catchup-20261111.md).

## Terminal state and limits

Session **65006 exits 0**. Root's terminal receipt confirms coordinator 44372
and native child 10492 are both dead; the retained child handle is closed.
Native state, snapshots and cancellation cleanup succeed. The child lifetime
is 23.812 seconds. Entry remains 22/22 GiB physical/commit, runtime 18/18 GiB,
with a 120-second child limit and no automatic retry. Saved runtime/final
minima are **22.4453 GiB physical** and **112.6577 GiB commit headroom**.

The normal GPU server retains the same controller/backend **32308/41560**,
creation identities, runs and paired8192 profile, ready on port 8840 throughout
the component. Gateway completed/cancelled counts remain **1/0** across the
saved boundaries. There is no GPU lifecycle action, model/driver change or
enabled resident NPU helper in normal serving.

Useful arrival before GPU demand and a complete real engine on/off gain remain
unqualified. Prefill tok/s, decode tok/s, native acceptance and full-engine
benefit stay null for this component. The full acceleration objective remains
open.

The retained read-only verifier is
`server/.local/halogen-update-20261110/primary0201/stateful1012-core-append-component-v1/verify_public_export_v1.py`.
Running it with the existing server Python environment rechecks the closed
evidence and public JSON without loading a DLL, contacting an API or starting
hardware. The independent export passes **890 checks over 309 pinned files**.
