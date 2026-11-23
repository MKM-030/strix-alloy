# Halogen 0.20.7 strict-tool replay

An explicitly selected strict tool exercised grammar drafting on the stock
0.20.7 server. The three measured completions accepted **93 of 96 grammar
drafts (96.88%)** and **243 of 258 MTP-head drafts (94.19%)**. One tool
call was returned per request. The collector treated its arguments as
synthetic extraction output and executed no tool.

| Input / output tokens | API prefill (tok/s) | API decode (tok/s) | Mean HTTP (s) | MTP-head acceptance | Grammar acceptance |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 547 / 135 | 1,070.84 | 87.15 | 1.916974 | 243/258 (94.19%) | 93/96 (96.88%) |

The run replayed the exact request from the
[0.18.5 strict-tool comparison](halogen0185-strict-tool-grammar-20261015.md).
It used the existing one-slot v2/HT4 BF16 server on port 8840,
`REV:N Performance`, cache off, temperature 0, and seed 1.
The synthetic incident values, function name, and serialized arguments
matched the 0.18.5 reference byte for byte. The excluded warmup took
2.315308 s. The three Windows QPC HTTP intervals were 1.759040 s,
1.957567 s, and 2.034314 s. The API recorded 39 neural-head rounds,
30 grammar rounds, and zero lookup drafts in the measured runs.

The three API phase sums exceeded their corresponding complete HTTP
intervals. Prefill and decode retain the API's reported values.
This was a single-configuration replay. It establishes that the forced
strict tool exercised grammar drafting on 0.20.7. It supplies no
isolated estimate of the grammar-drafting speed effect.
[WSL phase-clock audit](../research/halogen0207-phase-clock-audit-20261123.md)

The separate [JSON response-format comparison](halogen0207-json-format-20261123.md)
tested a different extraction request and recorded zero grammar drafts.
The replay used the local Chat Completions endpoint and made no changes
to ServiceNow or the serving profile. The same Halogen instance was
verified ready and idle afterward.

## Evidence

Raw responses and the independently verified QPC records are retained in
`server/.local/halogen-update-20261122/primary0207/strict-grammar-prep-v1/strict-tool-current-replay-v1`.

| Artifact | SHA-256 |
| --- | --- |
| Frozen request | `568e8e617b0d34d2b0da15d4f3e97e4fc73b7cc94b22976f6890f2a3e9226eea` |
| Matched arguments | `113bd5b907fed8ab23ca6d721a7de52f25d85782937dce8ade08f0bf949507b8` |
| Completed run handle | `0dd065324159797b1c7a5030c7cd41be3b8d8a5754912d7301b7f9ad99cbc006` |
| Numeric summary | `5e6d8bdf3440070a48c3907e8bb5134a0b162cfc715d9d01af8d4322b6ee6254` |
| Independent audit | `17c133ed850e374e195699f93c813d3706255739f2be49eade0ff8576df91a3a` |
