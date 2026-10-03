Title: Halogen 0.16.2 on Windows/WSL2: fresh 128K and 260K numbers

Quick update on my Windows setup. Strix Alloy is now running Halogen 0.16.2 with the v2 weights on my Ryzen AI Max+ 395 / 8060S with 128 GB RAM. I still use Windows as my everyday desktop and run the model through WSL2 in Codex.

I ended up keeping stock compute settings, MTP depth 2 and prompt cache Off. The shorter prose runs look like this:

| Input tokens | Cold prefill tok/s | Serial decode tok/s | MTP decode tok/s | MTP acceptance |
|---:|---:|---:|---:|---:|
| 8,192 | 1,715 | 35.8 | 47.1 | 60.0% |
| 16,384 | 1,681 | 35.5 | 45.3 | 56.3% |

Three measured repeats after warmup, with 128 generated tokens. Prefill uses a separate probe.

I also repeated the synthetic long-context workload from my earlier post, plus a 128K version:

| Actual input: prefill / decode test | Cold prefill tok/s | MTP decode tok/s | MTP acceptance |
|---:|---:|---:|---:|
| 128,034 / 128,048 | 1,621 | 65.4 | 93.9% (1487/1583) |
| 260,028 / 260,042 | 1,369 | 65.0 | 93.9% (1487/1583) |

Each long result is one cold request: a 32-token output cap for the prefill probe, and the full 2,048-token answer for decode. Early EOS is retained. One slot, 262,144-token capacity, zero cached input. Rates use the same clock calibration as the short runs; raw engine timings and wall time are in the report.

The long inputs are repeated filler and the output is predictable numbered paragraphs. This checks speed at depth, not 260K coding quality. Acceptance is accepted/drafted tokens and depends on the task: the separate three-turn coding fixture reached 88.3% (699/792).

My earlier post used Halogen 0.13.8 with w4b weights. This is 0.16.2 with v2, so the comparison includes both the checkpoint and setup changes. The long decode number covers the whole answer, unlike the old 20-second window.

I closed the game for these runs and kept the 18 GiB memory reserve enforced.

[Code and setup](https://github.com/MKM-030/strix-alloy) · [Long-context measurements](https://github.com/MKM-030/strix-alloy/blob/main/docs/benchmarks/halogen0162-long-context-20261003.md)

Thanks again to Peonist AI for Halogen and the engine work. Strix Alloy supplies the Windows/WSL integration.
