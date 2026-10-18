# Halogen 0.17.4: natural 16K request comparison, 10 October 2026

The normal 0.17.4 backend started successfully and completed the frozen workload. This comparison does **not establish a robust engine speed gain** or new Prefill/Decode token rates. The final 0.17.3 control improved relative to the initial control, and its measured range overlaps 0.17.4.

| Arm | Measured whole-request QPC times (seconds) | Median (seconds) | Combined MTP+PLD acceptance |
|---|---|---:|---:|
| 0.17.3 before | 14.3559809, 13.2994680, 13.6214526 | 13.6214526 | 180/399 = 45.1128% |
| 0.17.4 | 12.7725664, 13.1031053, 12.8247304 | 12.8247304 | 180/399 = 45.1128% |
| 0.17.3 after | 12.8490897, 13.0118104, 12.9611132 | 12.9611132 | 180/399 = 45.1128% |

The inverse-wall ratio for 0.17.4 is 1.06212 against the initial control and only 1.01063 against the final control. The median of the six pooled control measurements is 13.1556392 seconds; its inverse-wall ratio against 0.17.4 is 1.02580. Three measurements per arm and the observed baseline drift do not support a general performance claim.

The workload contains exactly 16,384 natural, nonrepeated input tokens and 128 generated tokens. Request SHA256 is `0b616f5eb0aa779244cdbba4c2c7d42c8ee43ec200fc41f596e8331440f5a28c`. Temperature is 0, seed 1, Thinking Off, prompt cache Off, MTP depth 2, PLD 3,3. Context capacity is 262,144; prefill chunk and maximum prefill workspace token count are both 8,192. Each arm has one excluded warmup and three measured requests. The additional excluded serial request on 0.17.4 returned the same text as its MTP requests. All thirteen requests completed without cancellation or other gateway traffic in their respective cohorts.

QPC measures the complete nonstreaming HTTP request through JSON reception. Native timing fields remain unqualified and are not scaled into Prefill or Decode rates. The native `response.created` values regress between some 0.17.4 requests; they do not establish request order or elapsed time. Host QPC observations are independent of this field. The 0.17.3 arms retain existing phase observation; 0.17.4 uses the normal backend without that observation. This is a configuration difference as well as a version comparison. No NPU producer or substitution was used.

Within each build, all measured outputs and draft counters agree. The 0.17.3 output hash is `bc179b2873f085833dbd1ec05e9aba7703957dfafafdab71bba3d3cfb2f32e4d`; the 0.17.4 hash is `940e8b3abd3e9ecb0f0d3b14ec3e1df6140eb83c99d219b6b6e2ac27112f7dec`. The cross-version text differs. Each MTP request reports 60 accepted of 133 drafted tokens; these API counters combine MTP and PLD and do not isolate MTP-only acceptance.

The original before-arm warmup was retained after a reference-hash literal error was corrected in a separate root collector. It was not repeated. A later continuation failed before sending a measured request because of insufficient entry reserve. Closing 36 exact, retired own PowerShell consoles restored admission; the final continuation sent only the three missing requests. Historical failures, source derivatives and raw warmup remain preserved. This RAM cleanup is not an engine speed claim.

The normal 0.17.3 server was restored ready and idle on port 8840 with its visible PowerShell console. The actual checkpoint records controller 6184/run `77ae4f8e6be3435c9c7a80434c3d335c` and backend 32600/run `bba02ebc99664503ba632af1ad351813`; future continuation must use current identities, not these historical PIDs.

Raw evidence is under `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/halogen0174-normal-aba-preparation-20261010/`: `A-before`, `B`, `A-after`, `comparison.json`, `root-complete-checkpoint.json`, retained source/failure receipts and lifecycle admissions. No public commit or push was made.
