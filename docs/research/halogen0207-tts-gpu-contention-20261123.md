# Halogen 0.20.7 and native TTS GPU contention

Moving native speech synthesis from Vulkan to CPU slowed down both Halogen
text delivery and speech synthesis in a paired 8K test. Production TTS
continues to use Vulkan.

Five Windows admission observations report 52–96% Compute activity
for the process that serves Qwen3-TTS on port 8862. Its verified birth
precedes those saved samples. All five occurred around measuring
requests, during admission or settling. They identify a competing
compute workload. An effect on Halogen request time needs a paired
overlap measurement.

Across 571 retained Halogen 0.20.7 admission receipts, 1,153 of 1,187
GPU observations contain no nonzero engine counter. The 34 remaining
observations include 18 Copy counter rows attributed to Windows System
PID 4 by the counter. The largest observed Copy value is 3%. The
archived ETW trace has 180 Copy spans and lacks a complete Linux owner
join. Current Windows driver image hashes still match the pinned
namespace proof. That proof identifies field meanings. The Copy spans
still require actual ownership evidence.
[Earlier Copy attribution implementation](halogen-copy-attribution-implementation-20261007.md)

## CPU and Vulkan speech synthesis

Three new private TTS instances used native Qwen3-TTS Base 0.6B Q8_0,
the same 12 Hz Q8_0 codec, the same synthetic German reference and
one fixed sentence with seed 42. Vulkan preceded and followed the
CPU arm. Each arm excluded one warmup and measured three requests.
The Windows client timed the first complete PCM16 sample and the
response EOF. The native log confirmed the selected backend.

| Backend | Mean first PCM | Mean complete HTTP | Mean real-time factor |
| --- | ---: | ---: | ---: |
| Vulkan before | 44.38 ms | 0.626 s | 0.230 |
| CPU | 255.78 ms | 1.814 s | 0.687 |
| Vulkan after | 44.24 ms | 0.613 s | 0.225 |

All three warm CPU requests completed faster than playback duration.
CPU synthesis took about 2.9 times as long as Vulkan and delayed first
audio by about 0.21 s on this fixture. The matching Vulkan requests
produced identical PCM across both control arms. The CPU requests
produced a different PCM hash. Audio quality and speech recognizer
agreement were outside this component comparison.

The regular Halogen, TTS, ASR and Native services remained available
during collection. The three private TTS processes closed afterward.
The lowest sampled physical or commit reserve was 23.92 GiB.
The native CPU mode is selected with process-local
`GGML_BACKEND=CPU`; the test changed only the private server environment.

The local evidence is retained under
`server/.local/halogen-update-20261122/primary0207/tts-cpu-offload-prep-v1`.
The component summary SHA-256 is
`e6fa717bb309424e9c87e228d79755a3a67abce4c7922b3756bafc5c4d668162`.

## Halogen decode with concurrent speech synthesis

The same speech fixture started when a Windows client received the first
visible text from Halogen. Each arm ran one excluded warmup pair and three
measured pairs. The same Halogen 0.20.7 process served all twelve pairs on
port 8840. Each request contained 8,192 actual novel-prefix input tokens and
returned 128 tokens with greedy MTP, cache off and thinking off. The client
used Windows QPC for both streams. The TTS request used the fixed German
phrase throughout, so its content and length budget were held constant
across arms.

| TTS backend | Halogen API prefill (tok/s) | Halogen API decode (tok/s) | Native MTP acceptance | First visible text to Halogen EOF | Halogen HTTP total | TTS first PCM | TTS HTTP total | Both streams complete |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Vulkan before | 2,067.06 | 49.83 | 65.98% | 2.569 s | 6.596 s | 107.44 ms | 1.329 s | 6.596 s |
| CPU | 2,047.16 | 48.34 | 65.98% | 2.651 s | 6.719 s | 403.85 ms | 2.827 s | 6.895 s |
| Vulkan after | 2,071.91 | 50.14 | 65.98% | 2.553 s | 6.570 s | 103.05 ms | 1.307 s | 6.570 s |

These are means of three measured pairs per arm. Native MTP accepted 64 of
97 proposals in every trial, or 192 of 291 per arm. All twelve Halogen
outputs were byte-identical. Windows measured 3.20% and 3.82% longer text
delivery on CPU relative to the preceding and following Vulkan arms. Both
streams took 4.54% and 4.96% longer to finish. First PCM arrived during
Halogen decode in all twelve pairs. Vulkan speech completed before Halogen
in all pairs and CPU speech finished afterward. The mean speech real-time
factor was 0.503, 1.071 and 0.495, respectively. The lowest sampled physical
or commit reserve was 23.50 GiB.

The native TTS log reports flash attention on for Vulkan and off for CPU.
The paired results describe the complete backend paths under overlap.
The benchmark begins speech synthesis after prefill, includes no no-speech
control, and produces no per-engine GPU Copy attribution. API rates are
descriptive because the native WSL phase clocks can diverge from Windows
elapsed time. The paired Vulkan controls matched PCM hashes by trial, while
CPU produced different PCM. Speech quality was outside the comparison.
[Native phase clocks](halogen0207-phase-clock-audit-20261123.md)

The overlap run retained the per-trial SSE events, PCM, QPC timestamps,
backend logs and summary in `tts-decode-overlap-run-v1` below the evidence
directory above. The overlap summary SHA-256 is
`c7f221456cee43707ab4f338ba8279d8241e7a95e4c7921b84e189f2e7e0a6f7`.
