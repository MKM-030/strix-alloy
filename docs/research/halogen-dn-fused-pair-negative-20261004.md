# Paired DN negative evidence — 2026-10-04

Reject `HALOGEN_DN_FUSED_PAIR=1` for the pinned v0.16.2 stock configuration.
The candidate failed the startup API arithmetic smoke check before becoming
ready, so there are no candidate benchmark samples and no speed comparison.
Do not retry this candidate within the current optimization window.

## Matched retained artifacts

Stock control: `server/.local/optimization9h-20261004/dn-pair-stock8k-a`,
profile SHA256
`e535484cdfd5ce3de4afc110a630296e5e5c556e2968ee22d118416cc6e37c1a`,
backend run `6b4eac3895a6460b905821f20f455f1f`.

Candidate: `server/.local/optimization9h-20261004/dn-pair8k-1`, profile
`server/.local/optimization9h-20261004/dn-fused-pair1.json`, SHA256
`875cbe67c93e8367adf6673e8cd98c1edf365adee45d21558ce2259c29cb9d23`,
backend run `cc61bc6e0a2d47ba8c595479777f6739`.

Fresh profile readback shows the engine differs only by
`kernel_controls={"HALOGEN_DN_FUSED_PAIR":1}`. Both retained plans have the
same 50-entry source seal. The candidate backend manifest confirms
`HALOGEN_DN_FUSED_PAIR=1`, cache Off, context 262144, and one slot.

## Executed result and limits

Stock reached ready and retained nine measured samples. Repeated output
hashes and serial/MTP cross-mode hashes passed. Its newest measured cohorts
were PP8192/TG1 1605.07 ± 15.65 tok/s, MTP TG128 46.874 ± 0.448 tok/s,
serial TG128 36.357 ± 0.093 tok/s, and MTP acceptance 60% (sample standard
deviations; three measured samples per cohort).

Candidate `terminal.json` records `ready=false` and
`error="Incorrect startup answer: arithmetic"`. The retained controller log
also contains that error. The existing smoke check requests only the number
for `17 + 25` and requires the normalized answer `42`; the incorrect answer
was not retained in a dedicated arithmetic artifact. The controller exited
before ready, and the retained run contains no cold benchmark directory.

Both run results prove cleanup and unchanged source seals. Candidate backend
outcome also records recovery successful. This is evidence that the candidate
does not pass this configuration's admission check; it is not a measured
performance regression or a localized diagnosis of the kernel arithmetic.
No sources, frozen runners, or launch settings were changed by this audit.

## Stock PP drift and wrapper audit

The initial `stock8k-c` control (backend
`429329cc1b1a4aa882e9ca09beae1269`, about 2026-10-03 23:52 UTC) and newest
`dn-pair-stock8k-a` control (about 2026-10-04 04:25 UTC) have the same stock
profile SHA256. Retained `cold-analysis.json` reports the following means;
the ± values are sample standard deviations across three measured requests.

| Metric | Initial stock | Newest stock |
| --- | ---: | ---: |
| Corrected PP8192/TG1 tok/s | 1731.31 ± 3.91 | 1605.07 ± 15.65 |
| PP8192/TG1 request wall seconds | 4.75530 | 5.12831 |
| Native raw PP8192/TG1 tok/s | 1731.2223 | 1481.6023 |
| PP8192/TG1 mono/raw clock ratio | 1.0000521 | 1.0833332 |
| Corrected MTP TG128 tok/s | 46.591 ± 0.077 | 46.874 ± 0.448 |
| Corrected serial TG128 tok/s | 35.781 ± 0.419 | 36.357 ± 0.093 |

Corrected PP8192/TG1 fell 7.29%, while its request wall increased 7.84%.
The clock correction changes the raw rate substantially but does not remove
the slowdown; retained raw/QPC ratios remain approximately one in both runs.
MTP and serial TG128 prefill also fell 6.03% and 5.75%, respectively.
Acceptance stayed at 60%, and corresponding prompt, request and output hashes
match the retained historic comparison. Thus 1731.31 tok/s is an earlier
control, not the newest stock baseline.

SHA256-matched git blobs locate the initial backend `service.py`, backend
`Start.ps1` and `server/controller.py` at `b77a3bd`, and the newest versions
at `1c5e198`; `kernel_controls.py` matches `d950029` and `afb8276`,
respectively. Their diffs add opt-in matmul-plan and lookup-source support,
plus admission of the optional `HALOGEN_FLASH_NGRAM_RANDOM` control. The stock
profile has no tuning/control keys, and neither manifest has a matmul or lookup
receipt. New default startup work consists of module imports, sealing the
added source files, and revalidation calls that return immediately on `None`.
No changed native stock launch or measured inference path was identified.

Both manifests have identical engine environments, image, checkpoint,
context, slots, service durations and generated entrypoint SHA256. Both bridge
adapters and the C preflight bridge are also identical; mount changes are
limited to the per-run entrypoint and state directories. The ignored outer
runner's seal changed, and its old bytes are not available through git. The
current runner's idle retry runs before and after the complete unchanged cold
client invocation, outside individual request timing. Profile-generation
changes do not alter the sealed stock input.

Native allocation remained 62.1 GiB weights, 7.2 GiB KV and 12.3 GiB working
memory (81.6 GiB total), with no retained compaction stalls. Minimum available
memory was 21.62 versus 22.45 GiB; commit headroom was 111.73 versus 114.02 GiB.
The 8076-token calibration lookup took 4.9 versus 4.6 seconds, and no retained
measured-request lookup stall establishes an SSD cause. These sequential
controls establish PP drift but do not isolate thermal, competing-load,
page-cache or wrapper causation.
