# Halogen 0.17.4: qualified natural 16K RAW phase measurement, 10 October 2026

The completed cohort qualifies Prefill and Decode rates through paired CLOCK_MONOTONIC_RAW phase durations and unchanged native D records. The original 0.17.3 server was restored and freshly verified ready and idle in its visible PowerShell console.

| Run | Prefill tok/s | MTP+PLD decode tok/s | Accepted / drafted |
| --- | ---: | ---: | ---: |
| Warmup, excluded | 1129.82 | 36.11 | 60 / 133 |
| 1 | 1689.38 | 43.61 | 60 / 133 |
| 2 | 1666.32 | 43.52 | 60 / 133 |
| 3 | 1615.34 | 43.56 | 60 / 133 |
| Measured mean | **1657.01** | **43.56** | **180 / 399 = 45.11%** |

Measured Prefill range: 1615.34–1689.38 tok/s; sample SD 37.88. Measured Decode range: 43.52–43.61 tok/s; sample SD 0.04. All three measured runs are included; the warmup is excluded from rate and aggregate acceptance statistics.

Aggregate acceptance is 180/399 = 45.1128%. Scope: combined API MTP+PLD draft-token accounting; native MTP-only acceptance not isolated. Native MTP-only acceptance is not isolated.

Each request has exactly 16,384 natural, nonrepeated input tokens and 128 generated tokens. Temperature is 0, seed 1, Thinking Off, prompt cache Off, MTP depth 2 and PLD 3,3. Context capacity is 262,144; Prefill chunk and arena are both 8,192. One excluded warmup and three measurements completed without replay. Startup admission remains 35/131 GiB physical/commit, request entry 22/22 GiB and runtime 18/18 GiB.

PP is 16384×1e9 divided by summed paired RAW Prefill chunk nanoseconds; TG is 128×1e9 divided by paired RAW Decode nanoseconds. Pairing v2 follows an unambiguous active signed request ID and the exact native start carried through Request moves. Real starts and scheduling/progress clocks stay unchanged. The root qualifier binds every phase pair, stored Prefill duration, unchanged rounded native D, token count, ordered response, backend/API run and deferred arm device/inode.

Whole-request RAW/QPC observations retain the original 0.1% bound. No whole-request ratio or cross-version wall ratio rescales these phase rates. Measurement correction includes instrumentation overhead and does not establish serving acceleration or a robust cross-version engine speed gain.

Request SHA256: `0b616f5eb0aa779244cdbba4c2c7d42c8ee43ec200fc41f596e8331440f5a28c`. Output equality is checked within this 0.17.4 cohort; cross-version text equality is not assumed.

[Numeric results and bound evidence](halogen0174-natural16k-raw-20261010.json). Private responses, native D/RAW journals, memory/QPC observations and lifecycle receipts remain under `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/phase-clock-real16k-v3-0174-preparation-20261010`.
