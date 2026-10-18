# GUFO Reddit workload: native Windows and frozen Halogen replay

28 September 2026, final observations. GUFO and Halogen have each completed both eight-request tables. Halogen replayed the saved GUFO messages and order, including the frozen assistant replies. Its long-context cells miss the unchanged PP-token tolerance: this is a same-input comparison, **not exact benchmark parity**. Historical ten-prompt or 260k results are not substitutes for these observations. No further model run was needed for this report.

## GUFO native Windows versus Halogen WSL2

**Engine-reported tokens/s**, one TG128 sample per cell. PP is about 2048 newly processed tokens. The 128K case means an already cached 131072-token target prefix, not fresh 128K prefill. GUFO uses IQ4_XS plus Q8_0 MTP; Halogen uses its existing HGN model/overlay. This is neither an OS-only comparison nor an answer-quality evaluation.

| Workload | Cached-depth target | GUFO PP | Halogen PP | GUFO decode | Halogen decode |
|---|---:|---:|---:|---:|---:|
| Mixed prose | 0 | 802.88 | 443.01 | 32.57 | 18.14 |
| Mixed prose | 131072 | 525.44 | 561.68* | 26.99 | 26.88* |
| Repetitive | 0 | 825.21 | 724.36 | 83.53 | 66.77 |
| Repetitive | 131072 | 536.05 | 546.91* | 69.89 | 57.15* |

\* Halogen's 64-token-aligned cache restore processes 44/50 more new tokens than GUFO. Its 2098/2099 new tokens exceed the frozen PP2048 ±32 maximum of 2080, although cache depth passes tolerance. Both engines use source indices 3 and 7; excluded first attempts were not substituted for closer or faster values.

| Workload / depth | GUFO cached / new / output | Halogen cached / new / output |
|---|---:|---:|
| Mixed / 0 | 0 / 2040 / 128 | 0 / 2040 / 128 |
| Mixed / 131072 | 131052 / 2054 / 128 | 131008 / 2098 / 128 |
| Repetitive / 0 | 0 / 2034 / 128 | 0 / 2034 / 128 |
| Repetitive / 131072 | 131058 / 2049 / 128 | 131008 / 2099 / 128 |

**Timing caveat:** Halogen's engine time sometimes exceeds the entire measured HTTP exchange. Mixed shallow PP + decode reports 11.6604 s versus 10.797 s HTTP; fresh 130261-token mixed prefix PP reports 203.1842 s versus 191.719 s HTTP. The repetitive prefix repeats this (187.3234 s PP versus 178.485 s HTTP). The cause is unresolved. These are traceable engine statistics, not validated wall-clock PP/TG or evidence of a precise speedup. Do not rescale timings or infer decode by subtracting PP from HTTP. Selected Halogen HTTP wall times are 10.797/8.203 s for mixed shallow/deep and 4.734/5.937 s for repetitive; these are whole-request times.

## GUFO community reference values

Server-stage tokens/s, one accepted TG128 sample per cell, as in the public GUFO table. PP is approximately **2,048 newly processed tokens**, not the cached prefix. `128K` means a previously prepared **131,072-token target** conversation prefix.

| Workload | Cached-depth target | Actual cached / new / output tokens | Our GUFO PP | Our GUFO decode | Windows-port author's decode claim | Pinned GUFO Linux decode |
|---|---:|---:|---:|---:|---:|---:|
| Mixed prose | 0 | 0 / 2040 / 128 | 802.88 | 32.57 | 30.1 | 32.18 |
| Mixed prose | 131072 | 131052 / 2054 / 128 | 525.44 | 26.99 | 29.4 | 28.12 |
| Repetitive | 0 | 0 / 2034 / 128 | 825.21 | 83.53 | 93.8 | 59.41 |
| Repetitive | 131072 | 131058 / 2049 / 128 | 536.05 | 69.89 | 76.1 | 42.32 |

Reference claims: [hiImMate's Windows-port comment](https://www.reddit.com/r/StrixHalo/comments/1wqsv03/comment/pc7bqa5/). Linux artifacts: [mixed](https://github.com/gufo-org/gufo/blob/d9a84f13f35d1f98da22886a12eb25dc7062e392/docs/models/qwen3.8-flash-next/artifacts/single-mtp-gufo.json), [repetitive](https://github.com/gufo-org/gufo/blob/d9a84f13f35d1f98da22886a12eb25dc7062e392/docs/models/qwen3.8-flash-next/artifacts/single-mtp-repetition-gufo.json). These are reference columns, not measurements performed on this PC.

The large repetitive decode result must not be presented as normal mixed-chat throughput. Prompt lookup proposed/accepted 87/87 tokens in our repetitive d0 run and 86/86 in its accepted deep run. Mixed-text decode is around 27–33 tokens/s on this workload. This is not a controlled lookup-on/off study.

## Configuration and comparability

- Windows 11, Ryzen AI Max+ 395 / Radeon 8060S, 128 GB unified-memory machine, existing 64 GiB VGM configuration; no system configuration changed for these measurements.
- Original cache-capable Windows GUFO source `cff564964e8506c0abb3e530cecb55332187ac6c`; executable SHA256 `E7F5B899C54C747EE5038C0598016394D2A70F25EE69AFBB1E02859FD223D943`.
- Existing **UD-IQ4_XS** target plus shared **Q8_0 MTP** sidecar. Both reference GUFO columns use **UD-Q4_K_XL**. This is not a weights-controlled OS comparison.
- One session, context 133,760, greedy temperature 0, thinking off, MTP maximum 7/minimum 1, survival policy, Latin draft vocabulary, prompt lookup enabled, disk cache off. Draft 7 is the public source default assumption: the Reddit author did not publish a full command or explicit draft ceiling. The pinned Linux artifact uses different policy/lookup defaults.
- Original pinned GUFO synthetic generator, mixed then repetitive in separate fresh processes, two calibration probes and one warmup per process. Independent per-table calibration adds two probes versus upstream's shared calibration. No request seed is sent, matching the public request helper.
- Each table required one deep calibration correction. All eight requests per table are retained, including the rejected 130,269-token cache measurements. The tolerance is `max(32, int(target * 0.005))`; those rejected attempts are excluded from the table.
- Each accepted response contains exactly 128 native output tokens. HTTP wall, first-content latency, native PP and native decode are recorded separately. No stream-chunk counting or whole-request output/time substitution is used.
- One sample per cell does not establish variance or statistical superiority. The same workload family does not establish byte-identical reproduction of an unpublished contributor command or request trace.

Pinned Linux PP is 1597.84/1335.91 for mixed and 1602.82/1295.17 for repetitive (d0/deep). Our measured PP is lower; decode proximity does **not** justify claiming full Linux/Windows performance parity.

## Evidence, memory and cleanup

Raw GUFO runs (under `C:/Projects/strix-alloy-research/reports/`):

- `reddit-native-mixed-20260928-v1-runs/20260928T175042Z-77a3e79ffb3e4feb8f414707d9503a74/`
- `reddit-native-repetitive-20260928-v1-runs/20260928T180048Z-d254e48eb64f4d5ca41b834984ce5198/`

Each stores request bodies, raw responses and hashes, native timings/counts, manifests, exact arguments, continuous memory observations, owned-process and five-frame recovery evidence. Both runs exited 0 with cleanup confirmed. The earlier mixed pre-create failure remains preserved separately; it never loaded the model. The slow full identity check was moved before fresh telemetry, without relaxing freshness or memory limits.

Mixed-run independent audit verified a 31.842 GiB minimum available Windows physical memory and 71.297 GiB absolute adapter commitment peak (70.493 GiB above baseline). Those are host/adapter counters, not process-only allocation claims; overlapping UMA counters must not be summed. Runtime floors remained 24 GiB physical available and 12 GiB commit headroom.

Independent repetitive audit also passed: minimum 32.285 GiB available physical memory, all 461 runtime ownership decisions verified, and five fresh recovery observations. Reports: `reddit-native-mixed-audit-20260928.md` and `reddit-native-repetitive-audit-20260928.md` in the research reports folder.

Completed Halogen v6 runs under the same research reports folder:

- `reddit-halogen-mixed-20260928-v6-runs/20260928T200930Z-15f974c58d944b77afba971e6cd7e6e6/`
- `reddit-halogen-repetitive-20260928-v6-runs/20260928T201844Z-8d7862d83bc346aeacd58851a138aec3/`

Independent reports: `reddit-halogen-mixed-v6-audit-20260928.md` and `reddit-halogen-repetitive-v6-audit-20260928.md`. All eight wire/response/semantic-message hashes and serving-ledger rows agree in each table. Every HTTP request completed. The retained comparability flags remain false and the client exits 1 because the deep cell misses PP tolerance, not because transport or memory failed. The generic wrapper message “Replay client failed or exceeded run deadline” is not evidence of a timeout. Raw flags and excluded attempts are unchanged.

Halogen configuration: pinned 0.13.8, existing qualified `PreflightPinned32k` process-local bridge, one slot, context/pool 133888 (256-aligned versus GUFO 133760), cache mode 2/three entries, two branches, inplace enabled, snap3/full disabled, prefill chunk 2048, MAX_TOK 2048. Existing VGM64, WSL cap 56 GB, cgroup 44 and copy48 settings remain unchanged; frozen messages and TG128 output budgets were preserved.

The user explicitly authorized reducing the **private physical runtime floor from 24 to 12 GiB** (“Ja von 24 auf 12”), after separately waiving the 51.25 GiB physical-start estimate. Effective private physical admission remained 24 GiB; commit admission remained 98 GiB and continuous commit headroom 12 GiB. The public guard/installation were not changed.

| Sampled minimum available Windows physical RAM | GUFO mixed | GUFO repetitive | Halogen mixed | Halogen repetitive |
|---|---:|---:|---:|---:|
| GiB | 31.842 | 32.285 | 19.123 | 19.472 |

These are host-availability minima, not model allocations or a controlled residency comparison. Halogen minimum commit headroom was 95.816/111.220 GiB; neither final run tripped its 12/12 GiB floor and guest swap samples were zero. Both exact test containers reached PID 0, running false, OOMKilled false, with empty cleanup errors. Exit 137 reflects the recorded explicit shutdown, not by itself an OOM. Five subsequent direct recovery frames per run exceeded its admission baseline; after the final repetitive run, available Windows memory was 49.42–49.56 GiB. No inference/test helper remained at the post-run process check.

### Validation assessment: share with the stated caveats

Native counts/rate arithmetic, source identity, request order, semantic hashes, ledger consistency, exclusions, terminal state and recovery were independently checked. Single samples do not establish spread, statistical superiority or general answer quality. Weight, cache and timing differences prevent a controlled Linux/Windows parity claim. These findings support disclosure of **engine-reported observations with limitations**, not an unqualified performance headline. No public push, release or Reddit publication was performed.

## Historical admission and failed attempts

The checkpoints below are retained as history. The later user authorization and completed v6 observations above supersede their then-pending status.

### Halogen admission correction

Direct preserved VGM64 single-slot results supersede the initial, overly optimistic two-session KV extrapolation. Windows physical available fell 24.702 GiB at 32K and 25.773 GiB at 256K, even though most of the additional GPU commitment appeared in dedicated accounting. It is not valid to credit the full nominal KV reduction as Windows-free-RAM savings. Adding the proposed 0.337 GiB three-entry cache to the observed 256K fall requires about 50.11 GiB initial available physical memory merely to retain 24 GiB in that planning scenario, before a further uncertainty allowance. Recent recovery of 47.745–48.082 GiB does not meet it. Halogen has **not** been launched under the superseded 47.13 GiB estimate. Additional free host RAM or a separately justified revised allocation plan is required, with 24/12 GiB runtime floors unchanged.

The revised independent review sets **51.25 GiB physical admission**: the 50.110 GiB above plus 1.071 GiB empirical C1 fall spread as engineering uncertainty, rounded upward to the next quarter-GiB. This is an explicit conservative allowance, not a statistical confidence interval or a future-placement guarantee. Commit planning uses 86 GiB growth and therefore 98 GiB fresh headroom. All five private source repairs have passed independent re-review. The direct Windows counter reading at **18:26:41 UTC** reports **47.952 GiB available physical memory** and **204.114 GiB commit headroom**. Physical admission still fails by **3.298 GiB**; no Halogen launch or attempt was made. Fresh admission remains necessary.

### Subsequent user-waived start and actual pressure stop

The user subsequently instructed “Ignorier die Grenze mach weiter”. An explicit private switch waived only the physical **start estimate**, retaining continuous 24 GiB physical / 12 GiB commit floors and 98 GiB commit admission. This did not establish that the configuration would fit.

After preserving and correcting the pre-start defects documented in `reports/reddit-halogen-prelaunch-source-drift-20260928.md`, the v4 run used the **existing qualified process-local preflight bridge**, not the historical hybrid-only path. Halogen requires 256-position KV alignment, so its context/pool was 133888 instead of GUFO's 133760. Frozen request messages and output budgets were unchanged. Full generated-environment comparison against the working deployment passed, permitting only documented context/pool/cache overrides.

Actual v4 load began with 44.446 GiB available Windows physical memory after WSL admission. About 46.97 GiB of weight copies completed, but available memory fell to **23.828 GiB** at 19:12:08 UTC. The supplemental guard began stopping its exact container immediately and confirmed terminal state about three seconds later. Commit headroom was still approximately 131.866 GiB; physical pressure, not commit exhaustion, caused the stop. No server-ready or inference result was obtained. At that checkpoint both Halogen tables were still unmeasured.

Evidence: `reports/reddit-halogen-mixed-20260928-v4-runs/20260928T191033Z-39da4059b3a74403b2501077e330dc9b/`. Terminal state is exited, PID 0, OOMKilled false, exit 137. The outcome retains the supplemental guard's nonzero tripped-release status as a cleanup error; this must not be misreported as an entirely successful run. Separate follow-up found no native/test helper processes and recorded five fresh recovery frames around 45.973–46.007 GiB available and over 201 GiB commit headroom in `post-run-recovery.json`. No next model was launched and no system settings or runtime floors were changed.

After the explicit 12 GiB runtime authorization, v5 reached a healthy server but a buffered HTTP reader failed after a five-second read timeout. Its failure and cleanup remain preserved. V6 uses the remaining absolute request deadline instead of retrying the poisoned reader, with delayed-loopback regression evidence. V6 completed both tables as documented above. No failed or successful attempt was erased or automatically retried.
