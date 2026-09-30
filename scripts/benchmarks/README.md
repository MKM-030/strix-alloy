# Reproduce the Halogen capacity benchmarks

These scripts measure the authenticated local Halogen 0.15.1 backend, not arbitrary
engines. They preserve raw engine timings and independently measured Windows/WSL
clock intervals. Calibrated phase rates are derived approximations, not engine speedups.
They do not change clock synchronization or kernel math.

Start the desired checkpoint with cache disabled; wait for READY. Use a second
PowerShell 7 terminal. Keep downloads, builds, games and other inference traffic out
of the timed run. Use a new output directory for each run/checkpoint.

```powershell
$Backend = '.\backends\halogen-wsl2-0.15.1'
$Out = Join-Path $Backend ('.local\benchmarks\manual-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
python .\scripts\benchmarks\halogen_bench.py `
  --backend $Backend --workdir $Out --context 262144 --suite core --reps 3
```

Core includes PP512, PP2048 and PP8192, plus PP512/PP2048 followed by 128 generated
tokens in prose and repetitive workloads, each serial and MTP. The script calibrates
exact input lengths including the chat template, checks zero cached input, actual output
length, server identity and serial/MTP output hashes. Warmup is excluded from statistics.
A one-token prefill probe has no meaningful decode interval and is not a TG benchmark.

The output directory contains private machine paths and run identities: review and
sanitize before publishing it. The bundled report exports do not expose API tokens.
Never run Python with `-O`: assertions are part of benchmark validation.

## Official ten-task serving comparison

This separate workload uses the upstream short prompts, a 256-token maximum and
low-effort thinking. It is not PP2048/TG128. Download only the pinned public JSON
input (not executable code), verify its digest and put it in the chosen output folder:

```powershell
New-Item -ItemType Directory -Force $Out | Out-Null
$InputFile = Join-Path $Out 'eval-prompts.json'
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/82c92af2289f6f1086ab8362b18669ccff36968b/tools/eval-prompts.json' -OutFile $InputFile
if ((Get-FileHash $InputFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne '23df9feb5ec2b343f675bb08dc6c0c2286e17dd6d73acf4e7d363d0c0c49922b') { throw 'Prompt-set digest changed' }
python .\scripts\benchmarks\halogen_bench.py `
  --backend $Backend --workdir $Out --context 262144 --suite serving --reps 3
```

Retain slow samples and actual early-EOS token counts. Compare identical conditions,
including weights, MTP mode, cache state, temperature, power and occupied depth.
Capacity and depth are different axes. A 262144-capacity server processing 512 tokens
is not a test of a filled 262144-token conversation.

The original calibration verifies Linux raw-clock intervals against Windows QPC. A
clock-rate change inside a request can still affect phase-level accuracy. Raw fields,
request wall time and calibrated fields are all retained so this is inspectable.
