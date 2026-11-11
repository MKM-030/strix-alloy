# Halogen 0.20.3 NPU: corrected deadline analysis

**There can be native MTP work after a true token is published and before the
existing early external-proposal lookup.** The earlier source review rejected
that possibility too broadly. A bounded current-ELF review now establishes
the cross-invocation ordering; it does not establish enough time for the NPU.
No producer was activated and no new NPU token-rate result exists.

On a successful ordinary step, Halogen publishes the accepted output IDs,
installs the final emitted ID, computes the next MTP opening through
`0x20a0ca0 -> 0x2098850`, caches that result and returns. The existing lookup
at `0x1f96dc6` can then query the final prefix on the next invocation. The
chain path has analogous post-publication preparation. Only the final prefix
of an accepted burst gets this next lookup; an NPU must still advance every
true ID before returning a result for that prefix.

The eager calculation already precedes the early lookup. A proposed second
lookup at `0x1f97df0` therefore adds no established full-head window on that
successful cached path, covers fewer native branches and needs a separately
proved callback contract. Reusing the original callback there would use an
unproved budget register and the wrong token-array layout. No late hook was
implemented or installed.

For the existing early lookup, the useful condition is completion of all
required true NPU work, final-row ownership and return transport before the
same-prefix query. Existing component averages and whole-decode clocks do
not prove that condition. Zero lead, a timely-hit rate and a token-rate gain
are all unproved. The native eager head is already computed; a proposal must
also demonstrate useful verification/acceptance behavior to improve throughput.

The subsequent source check further limits count1: on the normal active-MTP,
null-grammar route, the external first ID must match the cached native opening.
A different first ID falls back; a matching single ID uses the same two-token
verifier input as the ordinary single-head route. It therefore does not improve
that route's first prediction or remove the already completed head. Preempting
a deeper chain and paused/disabled-MTP bypasses are distinct, unmeasured cases.
The earlier three-ID oracle result does not qualify a count1 improvement.

FLM1.0.12 does expose incremental vector prefill without clearing state, but
its present implementation rounds rows to512 and uses a different multi-kernel
MM path. It is not an established cheap authority-burst append. No new bridge,
batch activation, scalar-equivalent BF16 result or speedup is claimed.

The current review binds nine complete native function captures to executable
SHA256 `bf84053705d1e89c214ff64c79ad1276c5fe353d80a9bb0f38ef3bac6645b97c`.
Historical source reports remain unchanged. Private full evidence is retained
under `server/.local/halogen-update-20261111/primary0203/npu-late-poll-contract-v2/`.
The [machine-readable correction](halogen0203-npu-early-window-20261111.json)
pins that evidence. Normal serving and the acceleration objective remain open.
