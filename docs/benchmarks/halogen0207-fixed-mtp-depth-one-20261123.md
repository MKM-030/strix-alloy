# Halogen 0.20.7 fixed MTP depth one

Fixing MTP depth at one raised the accepted fraction of proposed head
tokens at both input lengths. It added 13 verification rounds per
8K answer and eight per 16K answer. Windows delivery from first text to
EOF took **9.76–9.82% longer at 8K** and **2.61–2.76% longer at 16K**.

| Actual input | Profile and window | API Prefill tok/s | API Decode tok/s | MTP head accepted/drafted | Head rounds per answer | First text to EOF | Full HTTP |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 8,192 | Stock before | 2,074.21 | 57.75 | 192/291 (65.98%) | 62 | 2.217 s | 6.230 s |
| 8,192 | Fixed depth one | 2,048.93 | 52.61 | 153/225 (68.00%) | 75 | 2.433 s | 6.480 s |
| 8,192 | Stock after | 2,055.75 | 57.77 | 192/291 (65.98%) | 62 | 2.216 s | 6.265 s |
| 16,384 | Stock before | 2,061.41 | 55.39 | 180/279 (64.52%) | 66 | 2.310 s | 10.331 s |
| 16,384 | Fixed depth one | 2,057.69 | 53.92 | 159/222 (71.62%) | 74 | 2.374 s | 10.409 s |
| 16,384 | Stock after | 2,066.66 | 55.32 | 180/279 (64.52%) | 66 | 2.314 s | 10.314 s |

Each row averages three measured responses after one excluded warmup.
The frozen non-repetitive novel prefixes generated 128 output tokens
with greedy seed 1, Thinking Off and Cache Off. All 24 replies matched
the reference bytes for their input size. Native lookup and grammar
proposal counts were zero. API phase rates retain their native clock
scope. Windows QPC measures text delivery and full HTTP.

The candidate uses the same r2-HT4 head, Q4 draft vocabulary and joint
verifier as stock. It sets `HALOGEN_MTP_DEPTH=1` and
`HALOGEN_MTP_GATE_P=0`. The measured profile uses one 32K BF16 slot and
paired 8,192-token prefill limits. The native startup log confirmed the
selected fixed or adaptive policy in each arm.

Dividing the complete delivery interval by the reported head round count
gives 32.44 ms at 8K and 32.08 ms at 16K with depth one. The stock values
were 35.74–35.76 ms and 35.01–35.06 ms respectively. This quotient includes
the whole delivery interval. The increase in rounds outweighed the lower
quotient. Accepted drafts per answer fell from 64 to 51 at 8K and from 60
to 53 at 16K. Fixed depth one stays out of the regular profile.

The [earlier fixed-depth-two experiment](halogen0207-fixed-mtp-depth-two-20261123.md)
reached 60.50 API Decode tok/s at 8K with exact output. Its delivery gain
was specific to 8K in that comparison.

## Evidence

Raw requests, SSE, native logs and Windows delivery timings are in
`server/.local/halogen-update-20261122/primary0207/fixed-depth-one-campaign-prep-v1/fixed-depth-one-run-v1`.
The lowest sampled physical or commit reserve was 27.77 GiB. The campaign
restored the regular server on port 8840. Authenticated gateway and backend
checks passed, the private listeners closed, and Native Voice, ASR and TTS
reported ready.
The independent replay reconstructed all 24 responses, MTP scope counts,
native completion order and Windows delivery intervals.

| Evidence | SHA-256 |
| --- | --- |
| Stock before summary | `c09c282c67dd8f649abcd75f7a18d63edf7d5b4790c532cd8975897d42d2246c` |
| Fixed-depth-one summary | `1ec5c93afe6bbcd1655e757cf5d3dd20d8d250ca6267a9314913663ec699a762` |
| Stock after summary | `3d3f7f164b0bf344f6ef75f555b802986dec962b883f508b2c38d0445802b9de` |
| Terminal campaign handle | `0d4a5c13d8922bb5a627b6d5d974b7cbb885d510e3298fe0ef7fe09769791682` |
| Restored stock readiness | `0bb6b28cfce02e9c120da251793721f17e94c3e036c120d358797da1dab8ac44` |
| Independent raw replay | `9def3f02261dc712ee4c97e838f6746e5f0c282402d23cc6d718eef219fc5221` |
