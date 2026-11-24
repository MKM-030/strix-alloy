# Strix Alloy update: four Halogen streams on a 64 GB Strix Halo

I finally sat down to see how much context I could keep live on my Ryzen
AI Max+ 395 box. I'm running Halogen 0.20.7 v2 through Strix Alloy on
Windows/WSL2, with BF16 KV.

With four short code requests going at once, I got **144.15 tok/s** in the
window where all four were generating, about 5% behind Halogen's published
151. From the first HTTP request to the last response finishing, I got
133.39 tok/s. Same 384-token output length per stream as Halogen, with
different prompts.

The long-context part was more interesting to me. I filled one, two and
then three sessions to about 262K each. All three runs finished. I also
got four sessions through at about 131K each. Here's what the aggregate
rates looked like.

| Context per session, input + output | Shared Decode tok/s | Full HTTP tok/s | MTP head acceptance |
| --- | ---: | ---: | ---: |
| 1 × 262K | 46.45 | 0.80 | 67.05% |
| 2 × ~262K | 30.64 | 6.03 | 63.77% |
| 3 × ~262K | 65.64 | 10.23 | 73.20% |
| 4 × ~131K | 96.87 | 32.49 | 77.02% |

The long runs used different output lengths and arrival schedules. The
one-session run, for example, generated just 128 tokens after reading a
262,016-token prompt. The short-code run is the closest match to Halogen's
published setup.

With three contexts around 196K, I could take the fourth to 49,152 tokens
and finish, with just over 6 GiB of Windows RAM to spare. At 65,536 it
finished reading all four prompts, then the memory guard stopped the run.
Three almost-full 262K sessions plus a fourth at 32K also hit the guard.
The separate attempt to start a pool big enough for four full 262K
contexts didn't make it to the first request.

If anyone has tried this on a 64 GB Linux box, I'm curious how far you got
with BF16 KV. I put the exact inputs, rates and memory figures in the
[Strix Alloy README and benchmark notes](https://github.com/MKM-030/strix-alloy#halogen-concurrency-benchmarks).
