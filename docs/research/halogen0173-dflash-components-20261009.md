# Halogen0.17.3 DFlash component checkpoint —2026-10-09

The original Halogen server stayed ready and open on port8840. No lifecycle
operation, live patch or API inference cohort was performed during these
component trials. The latest qualified serving result remains1833.70 prefill
tok/s,43.05 decode tok/s and180/399=45.11% combined MTP+PLD draft-token
acceptance, using16384 actual natural-text input tokens and128 outputs,
ThinkingOff and CacheOff. This is not isolated native-MTP acceptance.

The pretrained drafter uses its actual58 pinned tensors and the actual original
BF16 full-vocabulary head. All new feature stimuli were deterministic synthetic
HCconcat, not features captured from the live target. Source bytes were copied
to immutable directories before each new numerical execution. The exact source
and small raw fixtures/reports are preserved in
`scripts/research/dflash_k3_provider`. Old two-round CPU/GPU observations retain
their source hashes but lack an archive of their original source bytes; they do
not qualify the newer source version.

| Component | Baseline mean | Candidate mean | Cost reduction | Numerical scope |
|---|---:|---:|---:|---|
| Full original head, same already-computed GPU hidden |9.8096ms|7.3745ms|24.82%|744960/744960 logits exactly equal in each pair |
| Complete cached16K GPU draft, repeat KV versus grouped2D, both full-BF16 head |52.7336ms|30.2056ms|42.72%|Same three IDs in all pairs and CPU owner; logits differ |

Each component excluded one warmup per variant and used three alternating
measured pairs. Timings include explicit finite synchronization and host ID
copy. Diagnostic output D2H and error analysis occur outside those intervals.
Neither table row measures target verification, native transport, output tokens
or serving acceptance. No component-millisecond value was converted to tok/s.

The long fixture used16384 synthetic committed rows, capacity16640 and bounded
128-row prefill appends. Both variants shared the same cache, learned weights
and resident full head; storage-address checks passed and the cache/frontier
remained unchanged after paired graph calls. A separate pinned-source CPU owner
recomputed the full context once. All variants predicted IDs25,660,314. The
maximum direct repeat/grouped logit difference was0.109375; maximum error versus
the CPU owner was0.125 for repeat and0.06494140625 for grouped. Long-context
value-level CPU accuracy remains unqualified. The small exact head comparison
does not imply exact long-context backbone arithmetic.

The complete R1 NPU experiment kept all17 actual learned tensors and all input/
derived finite checks. Native BF16 first compiled a `stx`/`hw` partition covering
the fusion and five V GEMMs, but the strict session rejected remaining CPU
nodes before dispatch. A separately labelled native-BF16 mixed session also
failed before dispatch: the CPU EP had no BF16 MatMul implementation for
`layer_0_k_matmul_98`. There are no numerical calls or speed values from either
failed session.

That concrete support mismatch justified one trial of the existing complete
FLOAT graph with explicit BF16 rounding and mixed CPU fallback. It completed
one excluded warmup and three calls on a frozen source-CPU row at position16384.
ORT profiles attribute nodes to both VitisAI and CPU EP; compiler metadata
records `stx`/`hw`. Independent physical NPU device clocks were not measured.
This is a mixed component result, not NPU-only execution.

The three measured host-input-to-owned-KV costs were8.4173,7.4871 and7.7264ms,
mean7.8769ms. This includes input widening, bindings, dispatch, output fence,
finite read and returned-KV copy; native feature capture, D2H, WSL/IPC and GPU
H2D are excluded. The source CPU oracle mean was3.852ms, but checks only final
KV finiteness, while the EP checks every derived value, so those costs are not
an equivalent CPU/NPU A/B.

All outputs were finite and exactly representable as widened BF16, but only
1039/5120 values were exact versus the source CPU output; maximum absolute
error was0.0625. Diagnostic comparisons at the previously established limits
passed1041/5120 values at CPU atol0.0002/rtol0.002 and4490/5120 at NPU
atol0.003/rtol0.03. No limit changed. These are diagnostic checks of existing
projection limits, not a new DFlash accuracy authorization. No source accuracy,
target acceptance or NPU serving gain is qualified. The synchronous NPU route
therefore remains off.

All root component handles are terminal, owned NPU/compiler jobs closed, and
server creation identities remained unchanged. The long GPU run's minimum
physical reserve was20535603200bytes (19.13GiB), above the18GiB runtime floor.
The remaining work is actual owned target-feature capture, fenced transport,
causal provider coordination and a frozen native-verification/serving trial.
Controller/ownership concurrency review fixes are source work and remain
uninstalled. The full acceleration goal is still unachieved.

The companion JSON records hashes, raw archive locations, numerical errors,
unchanged-limit provenance and compiler partitions:
`halogen0173-dflash-components-20261009.json`.
