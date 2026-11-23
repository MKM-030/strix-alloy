# Halogen 0.20.7 assistant-message continuation warmup

Halogen received the same tool output and instruction to copy 32 log lines in
both requests. The candidate inserted the first 428 answer tokens, taken
directly from the tool result, as an unfinished assistant message. It set
`continue_final_message=true` and `add_generation_prompt=false`. The client
prepended that exact prefix to the generated suffix.

| Warmup | Input tokens | Generated tokens | API Prefill tok/s | API Decode tok/s | Native MTP accepted/drafted | Lookup accepted/drafted | Complete HTTP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Control | 3,539 | 1,259 | 1,387.68 | 129.58 | 24/24 | 1,076/1,078 | 12.266 s |
| Continuation | 3,967 | 831 | 1,956.98 | 134.08 | 26/28 | 699/707 | 8.219 s |

Both reconstructed responses stopped naturally with the same 4,933 bytes.
The reference ended with one additional LF. The exact-output check failed and
the runner stopped after the single warmup pair. The 4.047 s difference is a
single client-clock observation on a deterministic copy task. Prompt lookup
supplied most of each arm's accepted drafts, and the candidate generated 428
fewer tokens. General Decode, Prefill and MTP improvements remain unmeasured.

The running 32K v2 service used r2 HT4, greedy sampling, seed 1, Thinking Off,
Cache Off and request-level `no_store`. Both requests ran on the same process,
and the runner checked that no competing gateway requests completed between
them. Raw request, SSE and client-clock receipts stayed under the ignored
`server/.local/halogen-update-20261122/primary0207/native-continue-copy-prep-v1`
directory.

| Evidence | SHA-256 |
| --- | --- |
| Failed cohort summary | `adf6aa75101e5e9a4a89c436fe62de07cb8e951605b45f474b0cc0262ba4b773` |
| Control warmup | `7968e113abc170c9a87844d7ee3ef9bdcbbeda2be0e8df4e65ea765b1a5daebf` |
| Continuation warmup | `8345d1624913c2d6d94a48cdb8a70c4f689c46f37bfed168706efe709bfb130d` |
