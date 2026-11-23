# Halogen 0.20.7 staggered natural requests on one engine

Dispatching the short request at the first visible text of the long
request reduced the time to complete both answers by **8.23–8.30%**.
Mean aggregate delivery increased from **39.57–39.60 to 43.15 output
tok/s**, including Prefill and the Windows HTTP path. Each response
took longer from its own dispatch. All 24 responses matched the
corresponding sequential output bytes, token count and finish reason.

| Schedule | Mean pair HTTP | Mean completed output tok/s | Long request HTTP | Short request HTTP | Short completion after long first text |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sequential before | 16.172 s | 39.57 | 13.172 s | 3.000 s | 12.171 s |
| Staggered | 14.830 s | 43.15 | 14.830 s | 3.991 s | 3.991 s |
| Sequential after | 16.161 s | 39.60 | 13.153 s | 3.007 s | 12.156 s |

The long request's first text arrived after 4.033 s in the staggered
window and 4.002–4.005 s in the controls. Its average longest gap
between visible chunks grew from 55 ms to 544 ms. For the short request,
waiting from its own dispatch to first text increased from 0.889–0.901 s
to 1.006 s. Both answers had interleaved visible output in every
measured staggered pair, with 2.971–2.991 s of intersecting delivery
windows. These client timestamps establish when the responses arrived.

| Actual input / output | Schedule | API Prefill tok/s | API Decode tok/s | Native MTP accepted/drafted |
| --- | --- | ---: | ---: | ---: |
| 8,192 / 512 | Sequential before | 2,080.26 | 55.84 | 747/1,197 (62.41%) |
| 8,192 / 512 | Staggered | 2,056.23 | 47.42 | 753/1,188 (63.38%) |
| 8,192 / 512 | Sequential after | 2,056.52 | 55.97 | 747/1,197 (62.41%) |
| 1,536 / 128 | Sequential before | 1,753.73 | 60.64 | 192/267 (71.91%) |
| 1,536 / 128 | Staggered | 1,645.19 | 42.88 | 195/261 (74.71%) |
| 1,536 / 128 | Sequential after | 1,730.40 | 60.79 | 192/267 (71.91%) |

Each schedule ran one excluded warmup and three measured pairs on one
Halogen 0.20.7 v2/r2-HT4 engine with two slots and a shared 32,768-position
BF16 KV pool. The fixed novel prompts used temperature 0, seed 1,
8,192-token Prefill chunk and arena, Thinking Off, Vision Off, Cache Off,
and REV:N Performance. Sequential dispatch waited for the long response
EOF. Staggered dispatch followed its first visible SSE content. The
short request's host memory check ran after release and before dispatch.
Each request retained the 22 GiB entry and 18 GiB runtime limits.
The minimum runtime sample was 27.60 GiB. The minimum physical and
commit readings immediately before the short requests were 27.62 and
117.28 GiB.

Windows QPC measures the complete interval from long dispatch to the later
EOF. API rates use the respective native phase fields. The guest UTC
timestamps jumped backwards twice, so the native completion check follows
the log's line order. The scheduling
change qualified the aggregate two-response workload. The regular service
was restored to the single-slot 32K profile on port 8840.
[Two-slot profile and simultaneous-arrival comparison](halogen0207-two-slot-scheduling-20261123.md)

## Evidence

Raw SSE, response bytes, QPC dispatch and receive intervals, admission
and restoration receipts are retained under
`server/.local/halogen-update-20261122/primary0207/staggered-decode-prep-v1/staggered-decode-run-v1`.

| Artifact | SHA-256 |
| --- | --- |
| Reviewed runner | `ec769d4742dcad1be1243ddceb7809408148ac165b3d256ced909ed73cee53c4` |
| Reviewed collector | `ceae52f3a7edf13184e76c13b888b6160633765ef4c6c4490ce44257b83e44c9` |
| Terminal comparison | `f409cd0a9bd5bff4b624f0752b5ae85064e845e342ace95e04a1c8b8da94561f` |
| Independent replay of the 24 raw SSE responses | `c2f2bc80de42800a66ef55151c222e09b097156d3e232eeca9c83d58a65546ad` |
| Standard server and Voice readiness | `ada053b62f1481ea4f486dfde632d2a81fae5653a17df6e3a9ad6e76ef51840e` |
