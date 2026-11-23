# Halogen 0.20.7 native WSL lookup with Flexible cache

The native WSL lookup table reduced the first measured **8,221-token**
request from **8.201–8.327 s to 7.046 s** over HTTP. The two follow-up
questions still reused 8,192 of their 8,227 input tokens. All nine
answers matched the corresponding controls byte for byte, including
identical native MTP head counts.

| Lookup table | Request | Input / reused | API Prefill tok/s | API Decode tok/s | MTP head accepted/drafted | HTTP (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Windows before | First fixture | 8,221 / 0 | 915.80 | 91.36 | 11/11 | 8.327 |
| WSL ext4 | First fixture | 8,221 / 0 | 1,083.98 | 100.46 | 11/11 | 7.046 |
| Windows after | First fixture | 8,221 / 0 | 930.18 | 91.04 | 11/11 | 8.201 |
| Windows before | Follow-up A | 8,227 / 8,192 | 175.97 | 91.04 | 10/10 | 0.344 |
| WSL ext4 | Follow-up A | 8,227 / 8,192 | 216.05 | 100.46 | 10/10 | 0.297 |
| Windows after | Follow-up A | 8,227 / 8,192 | 178.48 | 91.04 | 10/10 | 0.339 |
| Windows before | Follow-up B | 8,227 / 8,192 | 181.82 | 73.12 | 10/11 | 0.369 |
| WSL ext4 | Follow-up B | 8,227 / 8,192 | 221.10 | 78.08 | 10/11 | 0.328 |
| Windows after | Follow-up B | 8,227 / 8,192 | 185.78 | 74.07 | 10/11 | 0.363 |

Each arm started one private engine and sent the same three frozen
[factual questions](halogen0207-shared-prefix-20261123.md) through
Chat Completions. All arms used v2/r2-HT4, one slot, one 32,768-position
pool, BF16 KV, paired 8192 prefill, Flexible cache, Thinking Off,
Vision Off and REV:N Performance. The middle arm mounted the verified
same lookup tensor read-only from ext4. The lookup read for the first
fixture took 2.8 s on ext4 and 4.5 s and 4.4 s in the Windows controls.
The configuration requires the retained local lookup receipt.

HTTP time uses Windows QPC from dispatch through response EOF. Each
cell is one observation and each answer contains 13 output tokens.
The application's startup checks sent short prompts before the fixture.
OS file-cache residency was unknown. Follow-up API Prefill rates count
the 35 newly processed tokens. Treat the phase rates and short
follow-up differences as descriptive observations.
[WSL phase-clock audit](../research/halogen0207-phase-clock-audit-20261123.md)

## Windows PowerShell 5.1

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Halogen-ServiceNow.ps1 -Profile CurrentCachedText32K -PrefillTokens 8192 -NativeLookup -ConsoleTrace
~~~

For the measured reuse pattern, split the first user message into the
stable long text and the changing question as shown in the
[shared-prefix request example](halogen0207-shared-prefix-20261123.md#opt-in-powershell-51-profile).

## Evidence

The nine requests completed with at least 25.59 GiB of sampled reserve.
The private engines were closed, and the regular single-slot server
was restored on port 8840.

Retained request bytes, wire responses and lifecycle records are under
`server/.local/halogen-update-20261122/primary0207/lookup-flexible-prep-v1/lookup-flexible-run-v1`.

| Artifact | SHA-256 |
| --- | --- |
| Completed lifecycle handle | `7c7026841fb8ce3c777444e0e3af8584a19a367799db90b278e792bbd39e3b36` |
| Independent response and lookup audit | `df9a4a8670cb6a299e93bb3d48ed5afd4bb0756ce85d79dcf05f8b0644bd2acc` |
