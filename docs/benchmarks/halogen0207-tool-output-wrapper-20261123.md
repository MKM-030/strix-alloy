# Halogen 0.20.7 tool-output wrapper for a ServiceNow handoff

Wrapping the same multiline incident records in `output` reduced mean
Windows HTTP time by **3.43–3.87%**. All twelve responses returned the
same 786 argument bytes for the fictional incident preview.

| Wrapper | API Prefill tok/s | API Decode tok/s | MTP head accepted/drafted | Lookup accepted/drafted | Windows first tool event | Windows full HTTP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `result` before | 1,372.22 | 114.06 | 378/378 (100%) | 108/126 (85.71%) | 0.670 s | 2.474 s |
| `output` | 1,372.98 | 119.61 | 234/234 (100%) | 261/273 (95.60%) | 0.670 s | 2.389 s |
| `result` after | 1,382.93 | 116.76 | 378/378 (100%) | 108/126 (85.71%) | 0.677 s | 2.485 s |

The candidate accepted 87 lookup tokens per answer, versus 36 in both
controls. It used 31 verification rounds per answer, versus 32. Grammar
contributed 57 of 57 accepted drafts across the three measured candidate
requests, versus 63 of 63 in either control. Windows time from the first
tool event to EOF improved by **4.70–4.92%**. Time to that first event
was essentially flat against the first control.

The same public 0.20.7 v2/HT4 instance ran one excluded A/B/A triplet
and three measured triplets. Each request had 874 input and 215 output
tokens, greedy sampling, Thinking Off, Cache Off, and PLD `3,3`. Both
arms used strict arguments for one inert preview. No tool executed and no
request went to ServiceNow. The wrapper changes one rendered prompt token
and exposes 336 tokens to the native LOOK input. The observed improvement
belongs to the complete wrapper change on this synthetic fixture.

The replay reconstructed the exact arguments, native speculation counts
and Windows QPC timings for all twelve original responses. The lowest
sampled request reserve was 30.79 GiB. The raw evidence remains under
`server/.local/halogen-update-20261122/primary0207/servicenow-handoff-lookup-view-20261123-v1/run-stock-wrapper-v1`.
The independent replay SHA-256 is `c32f80c241f0a2205d948175ec9c37d312e4d158a056cb1d4ac4b480aedaf2c9`.
