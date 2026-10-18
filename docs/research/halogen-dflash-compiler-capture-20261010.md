# Halogen 0.17.3: compiler repair and partial capture

The private compiler image resolved the worker's missing C compiler. The image
preserves 10,192 protected stock paths; the exact mounted Python 3.14/Triton
worker compiled and imported an isolated C extension using `/usr/bin/gcc`.
The compiler image and CPU receipts are local. No host driver, model, or firmware
was installed and no public commit or push was made.

One frozen natural-text request used 16,384 input tokens and 128 requested output
tokens, capture-only/provider off, Cache Off, temperature 0/seed 1, MTP2/PLD3,3,
KV capacity 17,408, and arena/chunk 8,192. The corrected HC geometry passed the
first Birth with zero loss. Actual terminal receipts record 227 fence-qualified
ingestion packets: 16,384 prefill rows and 99 decode rows.

The request did **not** complete. The worker locally reported `Retired`, but native
retirement was neither requested nor acknowledged; native generation drain also
failed. The subsequent native entry was refused, native exited 125, and the API
returned 502. An exporter failure can emit the same terminal packet as a requested
retirement. The worker's local `Retired` state therefore does not prove a successful
joint shutdown. The exact original loss branch remains under investigation.
Existing owner, fence, entry, and retirement checks remain intact.

Capture tool session 6675 ended with exit 1. Supplemental restore session 72335
ended with exit 0. Their coordinator identities were checked closed. Both
historical memory-recovery failures are preserved; independent unchanged 35 GiB
physical/131 GiB commit admission restored normal serving. The normal server was
freshly verified ready/open with controller 18152, backend 35912, console 24148,
context 262,144 and endpoint `http://127.0.0.1:8840/v1`. These are timestamped
observations, not a guarantee that process IDs remain current.

There is no full capture qualification, new serving cohort, NPU production,
or measured acceleration from this attempt. The qualified natural 16K reference
remains **1,833.70 prefill tok/s, 43.05 decode tok/s and 180/399 = 45.11% combined
API MTP+PLD acceptance**. Native MTP-only acceptance is not isolated in that result.
The complete acceleration goal remains active and unachieved; automation is
paused. Do not replay the unchanged compiler trial.

The next bounded trial will publish the existing first-failure loss trace, allowing
source contention to be distinguished from a true decode geometry/outcome error
before changing scheduling. Component diagnostics are not serving token rates.

Local evidence under
`server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/`:

- `dflash-triton-compiler-source-preparation-20261010/root-image-comparison-with-start-files.json`
- `dflash-triton-compiler-source-preparation-20261010/root-cpu-compiler-check-exec.json`
- `dflash-root-hc-subchunk-compiler-map-advice-launch-20261010/trial/startup-native-runtime/native-result/native-terminal.json`
- `dflash-root-hc-subchunk-compiler-map-advice-launch-20261010/trial/startup-native-runtime/worker-result/worker-retired.json`
- `dflash-root-hc-subchunk-compiler-map-advice-launch-20261010/trial/retained-startup-runtime.json`
- `dflash-root-hc-subchunk-compiler-map-advice-launch-20261010/trial/continuation-terminal-checkpoint.json`
- `dflash-checkpoint-20261009/compiler-capture-terminal-checkpoint.json`

The raw files were retained once, and the native/worker receipt digests are bound
by the terminal checkpoint. No second runtime copy or unchanged trial was made.
