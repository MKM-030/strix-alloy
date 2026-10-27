# Halogen policy and prefill qualification implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement each task. Root exclusively controls hardware.

**Goal:** Improve actual prefill/decode and useful speculation on current Halogen, retaining the full NPU/CPU/GPU/SSD objective.

**Architecture:** Test the supported fixed2/gate0 policy against the currently qualified adaptive0.90 policy using frozen natural prompts. Separately qualify serial PP1 with a bounded prefill-only RAW observer because its native duration currently exceeds whole HTTP time. Retain existing NPU failures; no synthetic classifier or changed workload substitutes for native engine acceleration.

**Tech stack:** Windows PowerShell 5.1, project Python 3.12, existing managed WSL2 Halogen 0.18.16, pinned C/assembly observer.

**Spec/evidence:** `docs/benchmarks/halogen01816-oem-performance-20261026.json`; private `primary01816/pp1-input-timing-audit/report.json`, `npu-nextpath-saved-audit/audit.json`, and `mtp-fixed2-aba/packet-pins.json`.

## Global constraints

- One large engine; only Root may stop/start or use GPU/NPU. Leave the working visible server online.
- Startup35 GiB physical /131 GiB commit; runtime18/18 GiB; request entry22/22 GiB. No weakened admission.
- Actual OEM Performance1; preserve drivers, BIOS, voltages, models, global WSL settings and unrelated programs.
- Preserve mixed foreign changes; no commit or push in this turn.
- One excluded warmup plus three measured requests per workload/window; no restart after observation timeout.
- Next source refresh is not before 2026-10-26T05:28:03Z.

## Review focus

- Different MTP policies legitimately change draft counts; require identical requests, output bytes, actual lengths and finish reasons.
- Exclude warmups from both means and aggregate acceptance, retaining their differing counters.
- Native PP1 time is unqualified; never rescale from HTTP or borrow another workload's clock ratio.
- A pending live lifecycle is retained and observed; it never authorizes a second engine.
- A PF-only journal must bind a complete8192-input, single-chunk phase; partial or multiple phases fail validation.

## Tasks

- [x] Saved audits: matched PP1 prompt content; proved serial one-output skips the old observer's decode-end flush; identified absent current NPU proposal/verifier contract.
- [x] CPU-prepare `primary01816/mtp-fixed2-aba/{prepare.py,run.py,test_candidate.py}` and two independent frozen packets; four tests and independent review pass.
- [x] Root binds fresh current server and OEM getter. Run adaptive/fixed2/adaptive, eight requests per window, using the normal lifecycle. Compare complete HTTP QPC against both bookends; require at least3% shorter for both8K and16K before promotion. Restore normal visible adaptive server regardless of candidate result.
- [x] CPU-prepare separate `primary01816/phase-raw-pf-only-observer`, preserving original observer, native chrono return and production sources.
- [x] Independently review PF-only source/tests and current function binding; Root links in the existing CPU-only Linux environment, validates the loader, then prepares a separate finite PP1 cohort with ordinary restoration. No measured phase claim before native/API/endpoints agree.
- [x] Save evidence and qualified changes, keep the server online, and continue the full goal without claiming NPU acceleration from isolated component latency.

## Execution record

The original MTP runner retained its terminal startup failure: a 10-second Docker inspection timeout caused normal backend cleanup during the A_after model load, before any A_after inference. A separate reviewed single-start recovery collected only the eight missing A_after requests. All 24 requests have exact request/output/count/finish parity; all 18 measured requests remain available. Fixed2 loses to both adaptive controls on both workloads and is not promoted. Original failure files and completed A_before/B files remain unchanged.

The separate four-request serial PP1 capture completed and restored the normal visible server. All four journals pass endpoint/API association and independent RAW/native enclosure within complete Windows QPC HTTP intervals. With warmup 0 excluded, RAW Prefill is 1906.2876705 tok/s; native Prefill is 1906.2876093 tok/s. No clock scaling, Decode claim, NPU claim or clean HTTP speedup is inferred from this diagnostic.

Root verified the restored baseline source hashes, removed observer binding/DSO, exact live controller/backend/launcher identities, authenticated health and one owned container. The active visible launcher is 27564, controller run 39495ebc603d49e1b984fdc3f198c139. Only the two proven ended test consoles were closed. Final receipt: `primary01816/final-qualified-recovery-ready/ready.json`. This plan's finite checks are complete; the broader NPU/CPU/GPU/SSD goal remains active and unachieved.
