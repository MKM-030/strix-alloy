# Halogen 0.20.7 Responses system-prefix reuse

Flexible cache reused **8,448 of 8,498 input tokens** on each of two
independent questions sent to **/v1/responses** with identical
instructions. Complete Windows HTTP time fell from **4.298–4.403 s**
to **0.250–0.271 s** across the two questions. Including the first
request, the three-request sequence took **8.183 s** with Flexible
cache and **16.283 s** and **16.103 s** with Cache Off.

| Cache mode | Request | Input / reused | API Prefill tok/s | API Decode tok/s | Head accepted/drafted | HTTP (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Off before | First request | 8,498 / 0 | 1,036.71 | 43.04 | 2/2 | 7.548 |
| Flexible | First request | 8,498 / 0 | 1,018.92 | 61.22 | 2/2 | 7.662 |
| Off after | First request | 8,498 / 0 | 1,041.55 | 61.35 | 2/2 | 7.492 |
| Off before | Follow-up A | 8,498 / 0 | 1,786.49 | 47.54 | 2/2 | 4.403 |
| Flexible | Follow-up A | 8,498 / 8,448 | 251.51 | 64.66 | 2/2 | 0.250 |
| Off after | Follow-up A | 8,498 / 0 | 1,825.29 | 66.67 | 2/2 | 4.298 |
| Off before | Follow-up B | 8,498 / 0 | 1,819.08 | 43.92 | 2/2 | 4.331 |
| Flexible | Follow-up B | 8,498 / 8,448 | 227.07 | 58.94 | 2/2 | 0.271 |
| Off after | Follow-up B | 8,498 / 0 | 1,817.87 | 61.86 | 2/2 | 4.314 |

Each row is one observation with three reported output tokens. All
three expected revision numbers matched byte for byte across modes
for the corresponding question. Each request accepted two of two
native head drafts. Flexible mode may produce different text on
other workloads. Rates in the API describe the native phase clock.
The cached follow-up Prefill rates count only the **50 processed
tokens**. The comparison of complete requests uses Windows QPC.
[WSL phase-clock audit](../research/halogen0207-phase-clock-audit-20261123.md)

## Conditions and request shape

Each request supplied a frozen synthetic repository corpus as the stable
instructions string and a different fact question as input. The pinned
renderer produced an 8,460-token system snapshot boundary, and the
engine reported 64-token snapshot alignment. Live usage and native
logs recorded the 8,448 reused tokens.

Each arm started one private Halogen 0.20.7 v2/r2-HT4 engine with a
32,768-position context and pool, one slot, paired 8192 prefill
settings, BF16 KV, Windows lookup, Thinking Off, Vision Off and
REV:N Performance. Only the cache mode changed. The same request
bytes ran in each arm, at temperature 0 and a 32-token output cap.
The application issued short startup checks before the first fixture.
OS file-cache residency remained unknown.

Use the measured opt-in profile with Windows PowerShell 5.1.

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Halogen-ServiceNow.ps1 -Profile CurrentCachedText32K -PrefillTokens 8192 -ConsoleTrace
~~~

Send the same long instructions string and change the question in
input on each Responses request. The tested path keeps the model
settings and the system text identical across questions.

~~~json
{
  "model": "halogen-v2",
  "instructions": "Stable long system instructions or reference text",
  "input": "The changing question",
  "temperature": 0,
  "reasoning": {"effort": "none"},
  "max_output_tokens": 32
}
~~~

## Evidence

The three private engines closed after the measurements. The regular
single-slot server was restored on port 8840.

Raw request and response bytes, launch and restoration receipts, and the
independent API and engine-log audit are retained under
`server/.local/halogen-update-20261122/primary0207/responses-system-cache-prep-v1/responses-system-cache-run-v1`.

| Artifact | SHA-256 |
| --- | --- |
| Completed lifecycle handle | `bf856a853d035803c750fd9f5f85954e2845f20374c3e89918b3433704a2aee1` |
| Independent wire and engine-log audit | `4da17530171da0e887acc0a36c3a1571bb2397769e8f2c655f60ad0b5f579423` |
