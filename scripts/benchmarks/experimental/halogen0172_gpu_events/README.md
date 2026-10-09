# Halogen 0.17.2 sampled stream-event diagnostic

Default-off observer source, CPU-only analyzer and verified metadata-only host
descriptor map from the completed 9 October 2026 diagnostic. No binary, model
weights, activations, credentials or tensor payloads are included.

The exact `gpu_events.c` bytes compiled with the installed WSL CPU compiler:

```sh
gcc -std=c11 -O2 -shared -fPIC -Wall -Wextra -Werror -pthread \
    gpu_events.c -ldl -o libhalogen0172-gpu-events.so
```

Compilation does not initialize HIP or qualify loading into an engine. Root
loaded this observer once in an owned window, ran an excluded warmup and one
diagnostic, exported and closed it, stopped its process normally and restored
stock 0.17.2 with its visible console. It is not enabled in ordinary serving.
The lifecycle, request client and launch/manifest tools depend on the private
preparation layout and are not supplied as portable public launchers.

The analyzer runs on a **private evidence directory**, which must retain
`gpu-events.bin`, `gpu_events.c`, `descriptor-map.json`,
`request-boundaries.json` and `live-export-receipt.json`. For example:

```powershell
& 'server/.local/venv/Scripts/python.exe' -B `
  'scripts/benchmarks/experimental/halogen0172_gpu_events/analyze.py' `
  --evidence-dir 'server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/gpu-event-attribution-20261009'
```

The raw snapshot and retained ELF/native source inputs are intentionally not
public. Descriptor extraction used private inert ELF data; the supplied map
retains the exact registration bytes and their hashes. Image identity must be
validated before using its names for another process.

1/32 Bernoulli sampling, 512 event pairs, an 8,192-sample lifetime cap and a
32 MiB output cap bound the diagnostic. Timings are **instrumented same-stream
brackets**, including possible NULL-stream ordering and marker/runtime gaps.
They are not isolated kernel time, additive GPU time or a busy timeline. Semantic
Prefill/Decode phases are unclassified; hidden runtime, graph, PTDS and earlier
preload work is not fully covered. General error-path and concurrent-capture
transparency remains unqualified. Native-completion notifications are harvest
opportunities, not engine-idle leases. Keep this experiment disabled for serving.

Output parity and record integrity passed for the retained diagnostic. No new
throughput cohort or acceleration is claimed. See
[the report](../../../../docs/research/halogen0172-gpu-event-attribution-20261009.md)
and its adjacent JSON for the evidence and limitations.
