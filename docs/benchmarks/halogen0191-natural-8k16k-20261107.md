# Halogen 0.19.1 natural 8K/16K API observations

On 7 November 2026, the selected **0.19.1** v2 text profile completed the frozen
8K and 16K requests with one excluded warmup and three measured repetitions per
input. The server had two 32K slots, a 65536-position KV pool and a paired
2048-token prefill chunk and arena. The collector sent requests serially.

| Actual input tokens | API-reported prefill tok/s | API-reported decode tok/s | Native head acceptance | Complete HTTP QPC mean, s |
| ---: | ---: | ---: | ---: | ---: |
| 8192 | 1191.85 | 46.62 | 201 / 354 = 56.78% | 9.666991 |
| 16384 | 1125.72 | 48.98 | 210 / 321 = 65.42% | 17.241034 |

Each phase-rate column is the arithmetic mean of three API-reported values.
Acceptance sums accepted and proposed native-head tokens across those same
three requests. Lookup and grammar each proposed zero tokens. The
[numeric report](halogen0191-natural-8k16k-20261107.json) retains all eight
requests, warmup labels, individual timings, counters and output hashes.

## Clock scope

Windows QPC measured each complete HTTP response before response persistence.
For all eight requests, the API-reported prefill plus decode duration fell
inside that whole-request interval. The residual ranged from 20.836 to
91.431 milliseconds, including warmups. Independent RAW phase capture remains
unqualified for this cohort. The JSON retains `api_phase_clock_qualified=false`
and `RAW_observer_used=false`.

## Request and runtime configuration

Each request used 128 output tokens, temperature 0, seed 1, native MTP,
Cache Off with `prompt_cache_policy=no_store`, and Thinking Off. Every response
reported 128 output tokens and zero reasoning tokens. No input tokens were
reused from cache. The 8192-token case uses Chat Completions and the 16384-token
case uses Completions. Their frozen request bytes and SHA256 identities are
retained separately.

The server selected context 32768, slots 2, pool 65536, gateway concurrency 2,
prefill chunk 2048, arena 2048, Vision Off, adaptive MTP gate 0.90, PLD `3,3` and
prefetch 0. Runtime reserve remained 18/18 GiB and requests required 22/22 GiB
headroom at entry. The OEM operating-mode getter was unavailable to the
non-elevated process.

The measured controller and backend runs were
`f18c4e89b8ad41f6b1a25791f8a9d68b` and
`3103ec5ec2dc457c93ce99ebb50164b5`. Both were ready before and after collection.
The profile SHA256 is
`0d92158fe58e5ae278eba173aa4d40a0f4978cbc6d8e0bb5e5ca45c44c713cca`.
The JSON includes immutable image, extracted artifact and collector pins.

## Output identity and historical context

All four requests within each current input case produced the same output
hash. The hashes differ from the retained 0.18.22 cohort using the same frozen
request bytes.

| Input tokens | 0.19.1 output SHA256 | Historical 0.18.22 output SHA256 |
| ---: | --- | --- |
| 8192 | `6c2a1acb30c8e2adf0c8ab7ca18f1cbf81ab59c3ad70dc8b2b0d8a1908d0f6ad` | `7a75932a0a22967f4f93083f03bcc263b514c49ce8fe01edf609af7b786f507b` |
| 16384 | `3e2006924876543bf1392e158463f080079dfba796162370a504e253feb3255d` | `940e8b3abd3e9ecb0f0d3b14ec3e1df6140eb83c99d219b6b6e2ac27112f7dec` |

The earlier cohort used one slot and paired 8192 prefill settings. The current
record changes engine version, slot count and prefill settings, with current
OEM mode unverified. The historical report preserves its own operating-mode
observations and phase-clock limits. [Historical 0.18.22 cohort](halogen01822-natural-8k16k-20261101.md).

A separate one-slot candidate with paired 8192 prefill settings completed one
excluded warmup. Its collector then failed the 22 GiB request-entry reserve
check, leaving zero measured repetitions. The table above uses the complete
two-slot 2048 cohort. The current bare launcher selects paired 2048 settings.

## Final serving state

The independent final observation at **13:04 UTC** recorded the restored normal
two-slot 2048 profile ready, with matching 0.19.1 API/engine versions and
request-entry admission ready. Its controller run is
`c0f914b3674d46ff8e22e5059d84900e` and backend run is
`df10d3939eb84bb28088fc93c2ce2b67`. The profile SHA256 matches the measured
two-slot profile. The JSON keeps the measured and restored runtime identities
as separate records.

## Reproduce the selected profile

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Halogen-ServiceNow.ps1 -Profile CurrentText32K -Slots 2 -KvPoolPositions 65536 -Concurrency 2 -PrefillTokens 2048
```

The frozen prompts, warmup procedure and measurement method define this cohort.
Ordinary ServiceNow requests have their own input and output budgets. The
integration guide documents the stable `halogen-v2` model and public credential.
[ServiceNow integration](../integrations/halogen-servicenow.md),
[release and compatibility work](../research/halogen0191-update-20261107.md).
