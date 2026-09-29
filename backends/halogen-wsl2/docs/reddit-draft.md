# Reddit draft — not posted

## Title

Halogen numbers, but on Windows: Qwen 3.8 Flash Next on 128GB Strix Halo

## Post

I got Halogen running through WSL2 on my Ryzen AI Max+ 395 / 8060S, keeping Windows as my everyday desktop. No dual boot or replacement AMD driver.

Best completed measurements with real ~260k-token inputs:

- **66.55 tok/s decode** in a fixed 20-second window; **64.60 tok/s** over the full 2048-token answer.
- **790.92 tok/s prefill** in a separate 32-output-token run.
- **Two full 260k sessions:** 25.45 tok/s each, **50.90 combined**. Both context states verified; no aggregate speedup over solo.

Halogen-like decode on Windows, although prefill still trails native Linux. Different workloads, not a matched parity test; the long output is predictable synthetic text.

Windows idle usage is about **9 GB** on my setup. The successful two-session run left at least **18.86 GB available** in samples.

**Experimental:** three full contexts froze the PC and required a hard restart. That profile is not shipped. Upstream does not support WSL2; this is an independent extension. The public launcher currently offers bounded tests and a **30–300-second foreground API**, not an always-on service; the two-full-context profile is research-only.

[Code, PowerShell setup, comparison with Halogen/pwilkin and raw measurements](https://github.com/MKM-030/strix-alloy-wsl2).

Engine/kernel credit goes to Peonist AI; this repo provides the Windows/WSL integration.
