# Strata lookup complement: retire unchanged same-history no-hit drafting

Date: 2026-10-06. Scope: retained source/disassembly, bounded ELF constants/string reads, existing owned-token fixtures, and a read-only policy reconstruction. No Strata/Halogen code, engine request, compiler, test suite, WSL, hardware, service action or new download was used. Only this report was written; the earlier frozen assessments remain unchanged.

## Decision

Retire unchanged Strata `SuffixDrafter`/`PromptLookupSource` over the same committed request history as a complement to native **PLD3,3 hash misses**. With native full prompt indexing, an accepted Strata self-history match necessarily supplies a key already present in native lookup. Four saved positions and a longer backward match can change **which continuation is selected at a hit**; they cannot create coverage at a genuine key miss.

The native default bulk-index lookback is zero, meaning no initial indexing restriction. `HALOGEN_PLD=3,3` changes the trigram width/proposal cap independently of `HALOGEN_PLD_LOOKBACK`. A positive lookback override could create a coverage difference if the external source owns earlier unindexed tokens, but that is a different history policy and requires the actual request value and complete owned history. No such coverage is established here.

A bounded reconstruction of the existing fifteen frozen round prefixes found **zero native known-history candidates and zero Strata self-history candidates**, even using the complete available 8,192-ID shifted seed rather than only its last 512 IDs. It supplies no example or yield for hit-only older/longer selection either. Actual native hit, map, row allowance and opening counters remain unobserved.

This follow-up narrows the first-candidate priority in the [earlier Strata source assessment](strata0140-halogen-source-assessment-20261006.md). The honest remaining independent mechanisms are an independently loaded neural producer or a separately owned external retrieval corpus. Strata's pending-MTP lookup chaining is also a distinct *hybrid native-chain extension*, requiring a different insertion/state boundary; it is not the retired same-prefix no-hit proposer.

## Exact native history and selection

The pinned native executable is `backends/halogen-wsl2-0.16.2/.local/flash_serve`, SHA256 `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`. Retained host text is `server/.local/optimization9h-20261004/mtp-route-static-20261004/host-text-disassembly.txt`, SHA256 `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9`. Roles below are data/control-flow inferences from this stripped image, not exported function names.

For history `H` of length `N` and width `w=3`, the map associates a hash of `H[j-3:j]` with continuation index `j`. The hash starts at `0x14650fb0739d0383`; for each zero-extended int32 ID it performs XOR, multiplication by `0x100000001b3` modulo 2^64, then XOR with its own unsigned shift by 29.

| Retained instructions | Concrete behavior |
|---|---|
| `0x17592a0..0x175953f` | Bulk helper appends every supplied token to the vector. It starts indexing continuation positions at `max(old_length,w)`; a positive limit can further raise that start to `new_length-limit`. It loops while `j<new_length`. The limit changes indexing, not vector contents. |
| `0x1759440..0x1759450` | Obtains the mapped value for each window hash and writes `j` to it. Increasing iteration order leaves the newest continuation for a repeated key. |
| `0x1759550..0x175971e` | Single-token append first extends the vector, then hashes the preceding `w` IDs and stores continuation `j=new_length-1`. Newly appended output is therefore the available continuation; the current trailing window itself is not indexed without a following token. |
| `0x1759a40..0x1759bbc` | Map helper compares 64-bit keys, returns the existing node's int32 value at `+0x10`, or creates one value for that key. It does not retain four occurrences or compare longer token sequences. |
| `0x172d390..0x172d3b7`, `0x172da98..0x172dcac` | Reads the request-owned vector and hashes exactly its current trailing width. |
| `0x172dcac..0x172ddb0` | Looks up that hash key by bucket/list and goes to stock no-proposal seam `0x172d3bd` on a missing key. No backward exact-token match or longest-match ranking occurs. |
| `0x172ddb2..0x172ddc9`, subsequent copy branches | Reads the single stored continuation `j`, caps count by `N-j` and actual native allowance, then copies following IDs. Opening comparison and target verification occur later. |

Hash collisions can select a false continuation at a native **hit**; they do not make an exact indexed trigram's key disappear. The argument here concerns a coherent, fully indexed history. It does not infer map validity after an unsupported reset or qualify a live read interval.

The no-proposal seam also receives nonpositive allowance, disabled/invalid width and insufficient-context paths. A second lookup cannot override a zero B or the native policy/state bounds. Opening rejection is a separate later branch to `0x172d42b`, not a native hash miss.

## The bulk limit is resolved, not assumed

The relevant main-parser chain is bounded and concrete:

1. At `0x171af8c..0x171af9b`, main copies constant `0x13b80` into its stack `+0xe8`. The constant's little-endian int32 lanes are `[64,0,1,1]`; the second lane initializes stack `+0xec` to **zero**.
2. At `0x171b028..0x171b048`, the optional `HALOGEN_PLD_LOOKBACK` environment string at `.rodata` `0x291d7` is parsed as base-10 integer and written to stack `+0xec`. Missing environment retains zero. Separately, `0x171afac..0x171afd9` parses `HALOGEN_PLD` with `%d,%d` into `+0xd8/+0xdc`. Constant `0x13df0` has lanes `[64,3,3,32]`, establishing those default 3/3 fields.
3. At `0x171b5a2/0x171b5aa`, main copies the `+0xe8/+0xec` qword into packed options `+0x294/+0x298`. Main aggregate `A` begins at stack `+0x180`, so options begin at `A+0xf8`=`main RSP+0x278`; lookback is options `+0x20`.
4. Handler `0x171c4ce` retains its incoming aggregate A. At `0x171c5c2/0x171c5c9` it saves `A+0xf8` at outer `RSP+0x670`. Both request-constructor callers (`0x1720288/0x172028f` and `0x172a401/0x172a408`) subtract eight from RSP before loading `[rsp+0x678]`, therefore load that **original `+0x670`** options pointer.
5. Request constructor `0x1749d77..0x1749d90` copies the option record to request `+0xe0`; options `+0x20` lands at request `+0x100`. At `0x1749ee5`, it passes that int32 value as ECX to the bulk-index helper.

The two directly read constant byte strings are:

| `.rodata` file/RVA | Exact 16 bytes |
|---|---|
| `0x13b80` | `40000000000000000100000001000000` |
| `0x13df0` | `40000000030000000300000020000000` |

The inspected parser establishes the default and override provenance. It does not observe a captured request's field or rule out inherited/per-request overrides. The earlier owner audit explicitly separates full vector content from this indexing limit; its source does not itself pin a runtime option value.

## Why Strata's normal self lookup is redundant at a true miss

Pinned Strata commit: `1735d6471df29b42c26170efaac1f1446a58640f`. [`SuffixDrafter::append`/`propose`](https://github.com/Niko1221/Strata/blob/1735d6471df29b42c26170efaac1f1446a58640f/src/spec/suffix_drafter.cpp) stores the four most recent positions for a trigram-derived hash. `propose` skips the current suffix position, compares actual token IDs backward, and selects the longest qualifying match, newest on a tie. The generator uses maximum match 64. With ordinary committed-history append, the current suffix occupies one of the four positions, so at most three earlier keyed occurrences are considered.

If it returns a candidate from position `p`, then `p<N-1` and at least three actual trailing IDs match. Set `j=p+1`. Consequently `3<=j<N` and `H[j-3:j]==H[N-3:N]`. The native bulk/append mechanism has indexed that continuation under exactly the hash queried at the native seam, provided full indexing and the same history. Therefore:

`Strata self-history proposal exists => native queried key exists`.

Changing to a longer minimum match only removes candidates. Keeping four positions changes ranking after a key exists. Truncating Strata to the last 512 IDs also cannot create an exact match absent from the larger fully indexed native history. No hook implementation or hardware experiment is needed to establish this coverage relation.

## Distinct hit selection and the existing cheap screen

At an actual native hit, Strata could choose an older occurrence with a longer backward match rather than the native newest trigram continuation. That is a real algorithmic difference. A future hit-only replacement at `0x172e95f` must still retain the native first-head opening comparison, actual destination extent, `min(stock_n,3,B)`, constraints, target verification and accepted-prefix/replay authority. A different continuation could pass the gate or improve later prefix agreement; it could also fail the gate or reduce stock acceptance. Longer source match is not an acceptance or speed measurement.

The existing manifest `docs/research/halogen-independent-proposer-workload-20261006.json` has SHA256 `1f3a2fbfafe1a8fd90f99c23dac49f3f0028644d5f010fcd057edfcce26a4919`. Its shifted native seed `00-tokens-i32.bin` is 32,768 bytes, SHA256 `dc1b73cc84046ca0fe0ed09520540eed9c06e2682fbd23eeff7077209f7ee31b`. The seed and all fifteen authoritative replay-file hashes were checked before reconstruction. Only previously committed output IDs were appended at each prefix; future labels and cached-head references were reserved for evaluation, never lookup input.

One bounded arithmetic reconstruction used the 8,192 available seed IDs plus committed outputs before each of the fifteen frozen bases `8192,8193,8196,8199,8202,8205,8208,8209,8212,8215,8218,8220,8223,8224,8227`. It reconstructed the native 64-bit hash/latest-known-continuation rule and Strata's 64-bit key/four-position/backward-match rule, with width 3 and maximum match 64. It was not an execution of either engine or a timing test.

| Reconstructed result | Count |
|---|---:|
| Native known-history hash candidates | 0/15 |
| Strata self-history candidates | 0/15 |
| Different candidate blocks | 0/15 |
| Cases with any earlier position in the current Strata key's slot | 0/15 |
| Cases where the omitted original first-ID trigram could exactly equal the queried suffix | 0/15 |

At every case, Strata's keyed positions contain only the current suffix itself. Consequently candidate-prefix and opening-quality comparisons have no candidate denominator here; zero candidates must not be presented as an acceptance percentage. The omitted initial prompt ID was not guessed. The trace is a shifted-input head replay rather than a copy of the entire native PLD vector/map, and native hash collisions/actual request options/eligibility are not observed. Native hit, opening and stock-count fields therefore remain **null**. This one family supports retirement on the available data, not a population-wide hit-rate estimate. A genuinely hit-rich retained raw-ID family would be needed to screen older/longer selection; text outputs and aggregate draft counters cannot supply it.

## Pending-MTP chaining is a different prefix and boundary

[`propose_after`](https://github.com/Niko1221/Strata/blob/1735d6471df29b42c26170efaac1f1446a58640f/src/spec/suffix_drafter.cpp) temporarily extends the suffix with pending draft IDs without indexing them or committing them. [`PromptLookupSource`](https://github.com/Niko1221/Strata/blob/1735d6471df29b42c26170efaac1f1446a58640f/include/strata/spec/draft_source.hpp) and the [generator's lookup-chain branch](https://github.com/Niko1221/Strata/blob/1735d6471df29b42c26170efaac1f1446a58640f/src/program/generate.cpp#L10708) use that prefix **after** MTP drafting, then append returned lookup IDs to the same verifier window.

Native PLD's query uses committed/current history before its no-hit fallback obtains the MTP chain. Controller `0x173b644..0x173b6c1` obtains the first head ID and later IDs through `0x17dcb40/0x17dcde0`, then directly constructs/verifies the chain at `0x173b6c3..0x173b6f6`. No intervening PLD map search or longer-match selection appears in that bounded controller path. Its PLD append occurs after commit/output (`0x173b825`), not after each unverified draft.

A suffix ending in one or two pending MTP IDs can therefore have a historical match when the committed suffix did not. This is structurally distinct and could append a third proposal to a native depth2 chain within a separately proved width/allowance. It requires actual owned pending IDs, capacity, insertion before native verification, and native MTP/target commit/replay semantics; those IDs are not available at the current no-hit seam as a completed chain. Native cached head IDs remain an opening **gate**, not oracle input to a claimed independent predictor. A hybrid chain-extension audit must be labeled accordingly. No such integration or yield is established by this report.

## Independent data mechanisms and next priority

[`DraftSource` selection](https://github.com/Niko1221/Strata/blob/1735d6471df29b42c26170efaac1f1446a58640f/src/spec/draft_source.cpp) can consult sources beyond the request, such as a separately owned code/retrieval corpus. That could supply a continuation missing from request history. Its source registry starts empty and the interface does not provide a corpus. This retained fifteen-case family is not an independent external corpus; using its future outputs would leak labels. No suitable independently owned raw-ID corpus was identified in this bounded audit.

Keep the existing independently loaded producer work as the concrete independent route. Retain hit-only older/longer lookup and pending-MTP chain extension as separately scoped source mechanisms, with the former unexercised by current data and the latter needing a new state/insertion boundary. Do not build a redundant same-history no-hit feed merely because its source is available, and do not substitute Strata-engine benchmarking for the Halogen goal. All added live acceptance, readiness, overhead, authoritative committed-token rate and serving gain remain null/unmeasured.
