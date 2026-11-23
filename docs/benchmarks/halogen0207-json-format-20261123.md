# Halogen 0.20.7 JSON-format comparison

The typed schema took **1.89–2.27% longer** than the broad JSON object
format on this synthetic ServiceNow incident extraction. All 12 responses
returned byte-identical, valid JSON with the same eight fields and values.
The typed schema still provides explicit field and type constraints.

| Format | Input / output tokens | API prefill (tok/s) | API decode (tok/s) | Native MTP head acceptance | Mean HTTP (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `json_object` before | 161 / 95 | 632.04 | 104.23 | 240/252 (95.24%) | 1.096401 |
| Strict `json_schema` | 161 / 95 | 625.37 | 101.55 | 240/264 (90.91%) | 1.121273 |
| `json_object` after | 161 / 95 | 633.37 | 103.60 | 240/252 (95.24%) | 1.100504 |

The one-slot v2/HT4 BF16 server on port 8840 ran the three arms in order
under `REV:N Performance`. Each arm excluded its first request as a warmup
and averaged the next three. The requests used temperature 0, seed 1, cache
off, and thinking off. Only `response_format` changed. Both formats supplied
all field names and types in the same user prompt. The 95 output tokens
and neural-head counters came from the API. Grammar and lookup each
recorded zero drafts in all three arms.

Complete HTTP intervals come from the Windows performance counter.
Both broad controls were within 0.38% of one another. All nine measured
API phase sums exceeded their corresponding complete HTTP intervals.
The table retains the API phase rates as reported. The HTTP intervals
are the basis for the speed comparison. [WSL phase-clock audit](../research/halogen0207-phase-clock-audit-20261123.md)

The excluded warmups took 6.944 s, 1.265 s and 1.114 s, respectively.
The server logged vocabulary and merge initialization. Grammar-state
enumeration took 163 ms for the broad format and 34 ms for the typed schema.
Those observations cover only part of the first-request delay.
The results apply to one short synthetic extraction. The comparison
performed no lifecycle action or NPU offload. The same server was
subsequently verified ready and idle.

## Evidence

The requests, raw responses and QPC pairs are retained in
`server/.local/halogen-update-20261122/primary0207/strict-grammar-prep-v1/json-format-comparison-v1`.
The independent audit verified the hashes of all 12 request/response pairs,
the identical output and field types, the counter totals and the measured
means directly from the raw captures.

| Artifact | SHA-256 |
| --- | --- |
| Plan | `30b7a3c34029e6ba61fddc937b82e3e47b6672cd0bf60375bd32da147734c5c2` |
| Completed run handle | `97c75d0ffdebc588de86717cebb17b1957ff7cfbc59dba965291b24c5983c701` |
| Numeric summary | `1e16eab7851619d080e0e78f9ea67d69698b8d939362aea2bf7bf76813cbd47d` |
| Independent audit | `877a1b352c16cda8c560749744e5019ab37c1d9b3484c431590564c5961668e9` |
