# Prospective Halogen 0.20.3 native Z-stream comparison

**No throughput result yet.** This is a new GPU Prefill candidate, separate
from the completed CPU tokenizer comparisons and the incomplete NPU campaign.
Normal0.20.3 serving remains online during preparation.

## Mechanism and scope

The current ELF contains `HALOGEN_DN_Z_STREAM`, absent-environment default0.
Mode1 moves a qualified packed Zprojection to an auxiliary native HIPstream.
A main-stream event precedes its work; the default stream waits for completion
before both Zconsumption paths. These are existing software stream operations,
without a replacement kernel, NPU consumer, fabric/voltage change or new driver.
This internal selector is an experiment, not an upstream support promise.

The source-qualified branch requires M>1280 under the current getter defaults,
the6144x2560 packedZdescriptor, existing BF16/scratch/layout guards,
PREFILL_GEMM/HT_TRUNK_ORIG enabled and KEEP_TRUNK disabled. The two earlier fused
short-step paths reject M>8, so they do not bypass the2048/8192-token branch.
Actual loaded-descriptor applicability must still be observed. Additional
first-use scratch totals159.5MiB, plus a stream and two events. Tiny Decode/MTP
steps are not directly accelerated by this path.

## Frozen comparison

Complete separate cohorts for2048 and, only when meaningful/admitted,8192
actual natural input tokens. Each length has **before0 / candidate1 / after0**,
one excluded warmup and three measurements per arm. Do not combine lengths or
partial cohorts into a headline result.

The2Krequest is a shorter contiguous prefix of the existing real War and Peace
input, retaining its story instruction and closed-thinking frame. The running
serving tokenizer confirmed exactly2048 input IDs and the source8192 count in
13CPU-only tokenize calls. No corpus repetition or padding was introduced;
no inference request was made during preparation. Every measured response must
independently confirm its actual input length and128 output tokens.

Hold v2weights, current ELF/providers, context/pool32768, one slot/concurrency1,
both Prefill controls8192, temperature0/seed1, gate0.90, PLD3,3 and prefetch0
fixed. Cache, Thinking and Vision remain off. All arms use identical prepared
source and RAW instrumentation; their profiles differ only in explicit DNZ0/1.
Omit EXTERNAL_STREAM entirely: no HDO2consumer, TCP capture or NPU helper.

## Evidence and interpretation

- Use the current byte-identical RAWcollector, with phase timestamp brackets
  and independent wholeHTTPQPC. API clocks remain separately labelled.
- Read the native uint64use counter at RVA0x21ca518 immediately before/after
  each request, outside its existing timing window. Bind the exact process,
  ELF and PIE offset0 mapping. Require stockdelta0 and candidatedelta>0; a
  nonexecuted candidate is inapplicable, not evidence of no speed improvement.
- Counter increments count successful native Zjob submissions, not tokens,
  accuracy or independently completed GPU work. Request completion and native
  event joins establish the distinct completion boundary.
- Retain exact responseUTF8, finish reasons, counts, source/provider identities,
  raw timings and scoped acceptance counters. UTF8/count matching is not
  independent native-ID-sequence reconstruction. Keep all-neural acceptance,
  chain counters and any unreconciled counts explicitly separate.
- Report all samples, arithmetic means, brackets/ranges and stock bookend
  drift. Changed trajectories cannot support a causal Decode improvement.
  A partial arm or warmup never becomes a qualified post value.

## Operations

Root alone performs hardware/lifecycle work. Before starting, verify live
process/session handles and current game/Riot/GPU load. Preserve startup30GiB
physical/131GiB commit, each request22/22GiB and runtime18/18GiB. No automatic
rerun after timeout or admission failure. Retain actual handles and evidence.
Restore exact normal sources/profile and leave the32Kserver ready/open after
the finite campaign. Promote only a useful verified complete comparison.

## Other candidates closed in this source pass

An authoritative-only count-one NPU producer would avoid speculative forwards
and state snapshots, but the current sole consumer query precedes the retained
native GPU work. True-token feedback traverses the API afterward. No same-prefix
timely-readiness mechanism is established; aggregate timings cannot supply its
missing per-prefix deadlines. Its unfinished source is quarantined and has not
been integrated or run natively.

PLE NGRAM_ARRIVAL is distinct from PLD draft lookup. Zero PLD proposals cannot
rule out the learned PLEpath. Inspection of mode2 shows it changes one preceding
token ID supplied to the PLElookup job; no equivalent-input optimization was
established, so it will not be enabled as a speed setting.
