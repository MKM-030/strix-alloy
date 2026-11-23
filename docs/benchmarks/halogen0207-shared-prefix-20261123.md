# Halogen 0.20.7 shared-prefix cache

Flexible cache reused **8,192 of 8,227 input tokens** on two distinct
questions about the same novel excerpt. Each response contained 13 tokens
and was byte-identical across all three profiles. The two follow-ups
took **0.357 s and 0.387 s** over HTTP with a populated cache, compared
with **4.239–4.366 s** in the two Cache Off controls. This is a
**90.89–91.82%** reduction across the four matched comparisons.

| Cache profile | Request | Total / processed input | API prefill (tok/s) | API decode (tok/s) | MTP head accepted / drafted | HTTP (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Off before | Seed | 8,221 / 8,221 | 884.64 | 50.08 | 11/11 | 8.803 |
| Off before | Question A | 8,227 / 8,227 | 1,831.80 | 75.76 | 10/10 | 4.366 |
| Off before | Question B | 8,227 / 8,227 | 1,843.54 | 64.39 | 10/11 | 4.366 |
| Flexible | Seed | 8,221 / 8,221 | 911.97 | 93.59 | 11/11 | 8.427 |
| Flexible | Question A | 8,227 / 35 | 181.44 | 89.53 | 10/10 | 0.357 |
| Flexible | Question B | 8,227 / 35 | 182.29 | 73.08 | 10/11 | 0.387 |
| Off after | Seed | 8,221 / 8,221 | 914.43 | 91.04 | 11/11 | 8.535 |
| Off after | Question A | 8,227 / 8,227 | 1,875.83 | 93.93 | 10/10 | 4.239 |
| Off after | Question B | 8,227 / 8,227 | 1,889.31 | 72.59 | 10/11 | 4.245 |

Total HTTP time including the seed was 9.170 s with Flexible and
17.535 s and 17.019 s with Cache Off. Each row is one observation.
The API's prefill rate uses the processed-token column, so the warm
rows represent 35 tokens of prefill. Compare latency using the Windows
QPC measurements. [WSL phase-clock audit](../research/halogen0207-phase-clock-audit-20261123.md)

## Workload and conditions

The native first-message lead feature received two text blocks in
one user message. The pinned tokenizer and chat template produced the
same token IDs from the split and unsplit forms and placed the shared
prefix at 8,192 tokens. All three profiles received the same split
requests and used v2/r2-HT4, BF16 KV, one 32K slot, 8,192-token prefill
chunk and arena, temperature 0, seed 1, Thinking Off, and
`REV:N Performance`. The lowest sampled request reserve was 25.52 GiB.
Each answer was factually correct on this fixture. Head counts matched
for each request, with no lookup or grammar drafts.

The original measurement process exited after a transient Windows
file-access error during startup of the final control. The control
engine continued loading. The recovery process verified its ownership
and collected the three final requests on that same launch, then
restored the normal server on port 8840. Both process receipts and
all nine responses were retained.

## Opt-in PowerShell 5.1 profile

At a planned start, select the measured 8,192-token configuration:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Halogen-ServiceNow.ps1 -Profile CurrentCachedText32K -PrefillTokens 8192 -ConsoleTrace
```

On `/v1/chat/completions`, use two text blocks in the same first user
message. Keep the lead text identical across questions. The case
measured here uses `prompt_cache_policy: "default"`.

```json
{
  "model": "halogen-v2",
  "temperature": 0,
  "prompt_cache_policy": "default",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "Long shared reference text ..."},
        {"type": "text", "text": "\n\nQuestion for this request ..."}
      ]
    }
  ]
}
```

The lead must meet the native 2,048-token threshold. The pinned
`/v1/responses` adapter joins plain text blocks before the lead can
be marked. Flexible cache can change warm output on other prompts.
Check outputs and cache counts on the intended workload before using
this profile for an integration.
[Publisher cache flags](https://github.com/peonist-ai/halogen-flash-server/blob/dea807d22a638c67553abea876344a8192054a94/docs/FLAGS.md#speed-levers)

## Evidence

Raw captures and ownership records are retained under
`server/.local/halogen-update-20261122/primary0207/first-message-lead-prep-v1`.

| Artifact | SHA-256 |
| --- | --- |
| Offline token parity | `b9d1a0b9e514cf8a45a9e42ed9256008141951ea337f83a2d0ce55add07f27a7` |
| Original campaign handle | `9603bc7cc3764edf48dee85fd230a6bca8e8b70169de2d44d18a91179f032476` |
| Recovered nine-request summary | `c3714f7bb83a0ee3e727c7ca5ec7fefc99563ac00aa2b02129666ba21182fa90` |
| Independent response audit | `fa8867fa265716651a1f9d64df2c901691dc61293d580d589d8e60b817d7b5ed` |
| Completed recovery and restoration | `b716efe59079a2908ac1105d8584e6f6f56907c77118a71b899b274991930cd0` |
