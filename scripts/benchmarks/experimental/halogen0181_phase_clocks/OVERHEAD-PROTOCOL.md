# Required overhead and clock evidence before any rate claim

This observer is a diagnostic instrument. Current source delivery contains no
actual engine phase stamps, compiled observer, overhead result or live binding.
The verifier deliberately emits no tok/s. It cannot be enabled by a receipt flag.

Root owns build, actual configuration, tokens, lifecycle, model, guard admission
and all serving requests. Nothing below authorizes a launch when those gates fail.

1. Build the exact source packet and run `core_host_test.c` in a CPU-only Linux
   x86-64 environment. Verify ELF exports: only the versioned chrono symbol under
   GLIBCXX_3.4.19, with the original entry ABI. Record compiler/linker identities,
   commands, exact source pins, actual adapter SHA/size and test output. Build and
   CPU fixtures do not qualify model runtime or clock readings.
2. Bind a fresh source-pinned measurement-only API wrapper to the actual 0.18.1
   `serve_api.py` bytes. Replace its `_done_dict` callback with
   `DObserver(...).wrap(stock_done)` after extracting the stock callable. Root
   must prove that call site/class in the actual API source and preserve the
   normal auth wrapper. No production file replacement is supplied here. Native
   stock parsing happens once; the copied D frame and returned scalar fields are
   recorded after the call, and the identical result object is returned.
3. Root creates a fresh 32hex capture nonce and distinct absent Linux journal and
   optional arming paths. Enable only the new 0.18.1 namespace, preserve the normal
   bridge preload, and bypass the observer completely for residency probes.
   Constructor pin failures are terminal diagnostic preparation failures.
   Arming is an owned empty regular0600 file after readiness. All required
   startup, entry, runtime reserve, idle and contamination gates stay unchanged.
4. Freeze one existing request/profile: same 0.18.1 image, checkpoint, capacity,
   actual input, output cap 128 (at least two outputs required by the native timer),
   temperature, seed, fixed draft/PLD settings, Cache Off, Thinking Off, slot,
   chunk/arena and normal bridge. To relate to historical natural16K, retain its
   exact request bytes. Changing full262/4K to32K/8K requires a new matched cohort;
   it cannot retroactively calibrate historical replies. Use fresh output folders.
5. The measured-overhead protocol is **A-before / B / A-after**, one excluded
   warmup and three measured requests per arm: 12 total bounded requests, no retry.
   A has no chrono observer preload and no D companion; B has both enabled and
   one fresh journal pair. Only instrumentation differs. Root performs deliberate
   owned lifecycle transitions as required. Capture Windows QPC through receipt
   of each complete nonstream response, raw reply hashes, actual counts, output
   hash/finish, combined draft counters, identities/profile/manifest pins and
   memory/contamination evidence. All outputs/work must match across arms.
6. Separately sample guest RAW and host QPC over matched independent clock
   sampling intervals spanning the window. Preserve roundtrip/midpoint uncertainty
   and exact clock sampler source, rather than comparing HTTP duration with native
   first-Prefill-to-last-Decode duration. The predeclared clock gate is 0.1%: RAW/QPC
   disagreement plus its measurement uncertainty must fit within 0.1% for every
   required interval; each phase's two-read endpoint uncertainty must also fit
   within 0.1% of its measured phase. Native/RAW ratios are observed separately
   inside each actual phase; native clock scale is never inferred from HTTP sums.
7. Close the owned D companion, record `failed=false`, fsync the journals and bind
   their final byte hashes to the exact B clients/requests. Require every expected
   request, native D order/ID/count/duration and moved Request fields to match;
   reject nonzero statuses, dropped/torn/missing records, overlapping ownership,
   reused/ambiguous IDs or changed native returns. Supply fresh actual loaded
   engine/provider identity and independent RAW/QPC clock evidence.
   The D journal must contain its successful completion record. Its arm device
   and inode must equal the phase activation's identity. Supply the expected
   actual API source file to the reader, rather than trusting a hash in a header.
8. Publish all nine measured QPC times and the excluded warmups. Report A bookend
   drift and the B QPC mean/median increase against each control and their pooled
   control; an apparent negative overhead is not evidence of zero cost. Source
   pin/binding, clock uncertainty, output, reserve or contamination failure rejects
   the window. Material bookend drift prevents assigning a precise causal overhead.
   Do not subtract a fitted overhead from any native or RAW phase duration.

The C journal directly measures the native-clock call bracket, bookkeeping and
first phase-record write. Its second overhead-record write, wrapper dispatch and
prologue, other forwarded chrono wrappers, unlock/return and the API D companion
are outside that internal cost observation. A/B/A measures their complete effect
on whole-request wall under the frozen workload, with control drift limits; it
does not isolate their individual phase costs. Both measures must accompany any
later **instrumented aggregate RAW phase** tok/s report. The report must retain
the native count convention (Decode starts with `n_gen=1`) and explicit endpoint
uncertainty, and state the observed instrumentation effect. Clean serving phase
rates remain unqualified; no calibrated phase overhead budget or acceleration
result is supplied by this source packet.

The reader's optional `--capture-receipt` is a root-produced JSON receipt with
schema `halogen0181.actual-capture-coupling.v1`, `capture_kind="fresh_actual"`,
the predeclared fresh `nonce`, exact `engine_sha256`, `provider_sha256`,
`api_sha256`, final `clock_journal_sha256` and `native_d_journal_sha256`, plus
`adapter_sha256`, `source_pins_sha256`, `profile_manifest_sha256` and
`client_source_sha256`. It must state `companion_closed=true`,
`companion_failed=false` after close and `api_callable_source_verified=true`
after root verifies the actual stock callable's source/call site.

Its ordered `requests` entries contain the actual `request_epoch`, signed
`request_id`, `prompt_count`, `predicted_count`, `request_path`,
`request_sha256`, `reply_path`, `reply_sha256`, `qpc_start_ticks`,
`qpc_complete_ticks` and `qpc_frequency_hz`. Paths are relative to the receipt
folder; the file-only reader hashes the actual saved request/reply bytes and
rejects escape paths, mismatching final journal hashes or identity/count/order.
QPC completion means receipt of the entire nonstream response. Preserve the
QPC client's pinned source and its raw clock log alongside the receipt; a
receipt must describe real fresh requests and cannot relabel historical cohorts.
This verifies artifact coupling. Trusted recording provenance still requires
root review; asserted fields cannot grant clock calibration, overhead or rates.

The native Decode-begin count is initialized to one before its mapped chrono
call. The observer additionally reads and journals that begin count and the
final count without mutation. Static initialization does not by itself prove
whether the first token-generation work is before or after the timing boundary,
or whether native D/API count128 represents128 operations inside that phase.
Minimum runtime proof must close this first-token/count boundary before any
count-based phase report. Until then, `phase_count_scope_qualified=false` and
only the observed begin/end counts and count delta are reported. Neither
count128/phase-time nor count127/phase-time is assumed valid.

For a new phase, native endpoints lie inside the RAW brackets. RAW elapsed bounds
are `end_before-start_after` and `end_after-start_before`; sum these bounds over
Prefill chunks. Before-to-before elapsed is a direct observed interval. After
the complete evidence above is reviewed, count/upper-duration and count/lower-
duration bound an explicitly instrumented rate. No old timing is rescaled.

If only clock diagnosis is wanted, one isolated natural16K/128 request with a
complete paired capture can distinguish clock scaling from outside-phase work.
It does not complete this overhead protocol and establishes no rate claim.
Gate-only receipts, failed admission, CPU mock stamps and hardware loops are
not phase captures. Current source delivery has no actual engine stamps or
coupled request receipt, so it supplies no diagnosis or speed claim.
