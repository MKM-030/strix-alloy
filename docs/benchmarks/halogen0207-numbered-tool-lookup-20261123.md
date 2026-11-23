# Halogen 0.20.7 numbered tool output and prompt lookup

Tab-separated line numbers shortened the mean end-to-end request time
from **6.964 to 5.526 seconds** on a forced strict tool that copied 12
multiline records. The tab layout saved **20.64%** on average and
**17.89–25.11%** in each of the three measured pairs. Every response
returned the same exact argument bytes and generated 613 tokens.

| Tool result layout | Actual input / output | API Prefill tok/s | API Decode tok/s | MTP head | Prompt lookup | Mean full HTTP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `number: record` | 1,351 / 613 | 1,581.87 | 100.51 | 1,350/1,422 (94.94%) | 156/273 (57.14%) | 6.964 s |
| `number\trecord` | 1,335 / 613 | 1,583.98 | 130.91 | 171/171 (100%) | 1,395/1,407 (99.15%) | 5.526 s |

The tab layout used 237 native rounds over the three measured replies,
down from 297. Grammar accepted 36 of 36 drafts in each arm. The head's
proposal count fell from 1,422 to 171 as lookup verified more of the
copied text. Output tokens divided by total Windows HTTP time increased
from **88.03 to 110.93 tok/s**, including request prefill and transport.
API Prefill and Decode use the native phase fields. The phase sums
exceeded the Windows HTTP interval in three of six measured requests.
[Phase clock audit](../research/halogen0207-phase-clock-audit-20261123.md)

## Apply at the tool output producer

Halogen's enabled lookup view recognizes a run of three or more consecutive
line numbers followed by a tab, `→`, or `| `. It removes these prefixes
from the lookup view. In this test the colon case fell back to the full
numbered tool text. Both cases used the same 16 synthetic JSON records,
field schema, model, and instructions to copy records 2 through 13 without
their display prefixes. The applicable payload uses the Chat Completions
`role: tool` message's `content` string. For an array of single-line records:

```javascript
const numberedOutput = records.map((line, index) => `${index}\t${line}`).join("\n");
const toolContent = JSON.stringify({ output: numberedOutput });
```

The normal API tool role and tool call ID remain in the surrounding message.
This format applies to copy-heavy data already owned by the calling tool.
Ordinary prose, free-form MTP gains and the live ServiceNow workflow are
outside the measurement.

## Controls and evidence

All eight requests ran on one Halogen 0.20.7 v2/HT4 32K BF16 slot with
Cache Off, Thinking Off, `prompt_cache_policy=no_store`, temperature 0,
seed 1, PLD `3,3`, and the Windows REV:N Performance profile. One pair
was excluded as warmup. Three measured pairs alternated order. The
runner verified exact tool arguments, token accounting, one strictly
enforced tool, and one completed gateway request per sample. The runner
recorded the returned calls as benchmark output. The lowest sampled physical or commit
reserve was 31.57 GiB. Halogen, Native Voice, TTS and ASR remained ready.

The earlier single tab-format probe confirmed 469 lookup drafts in 67
rounds, a mean of seven with the same `3,3` profile. The probe's offline
token estimate was two high because its Jinja JSON filter sorted tool
keys. Reproducing the native key order matched the actual prompt count.
The probe is outside the measured pairs.

The local fixtures and raw evidence are under
`server/.local/halogen-update-20261122/primary0207/strict-tool-look-format-20261123-v1`.

| Artifact | SHA-256 |
| --- | --- |
| Colon request | `0ae849ce5b8ff19a682de9a7e1f8c0c17d36a1c14180b7ce5990dfe7a6d0cf8f` |
| Tab request | `a19541c3495a295f92fe6a93c9338c5c6def670efba0b2d24ec59c58ca28a4cf` |
| Exact tool arguments | `3c3bbf8af019527a896fb22d902c76ed0e807c3f7d90c0b78370928701eac612` |
| Paired summary | `a2f0b4acf8c6df8fcb7a58d59e44b2275bd96f9ef61e195943dd43b8c5b43c98` |
| Terminal handle | `69060d732f660cf49fc416511f39516adf1f01e9ec62aa44d031d270a1e782a8` |
