# Reproduce the Halogen capacity benchmarks

The original capacity examples below target the authenticated local Halogen 0.15.1
backend. The later managed-client sections also cover the pinned 0.16.2 backend.
They preserve raw engine timings and independently measured Windows/WSL
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

## Prefix-cache shape test

This is a separate warm-prefix experiment, not a cold PP throughput benchmark.
After a core run has created `prompt-8192-prose.txt`, stop the backend cleanly and
restart with `-PromptCache Exact` (or `Flexible`). Wait for READY before running
this command, with `$Out` pointing to the completed core run from above:

```powershell
$CacheOut = Join-Path $Backend ('.local\benchmarks\cache-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
python .\scripts\benchmarks\cache_shapes.py `
  --backend $Backend --mode Exact --drafter mtp --context 262144 `
  --prompt-file (Join-Path $Out 'prompt-8192-prose.txt') --output $CacheOut
```

Four explicit layouts are tested: the original single message, a slightly longer
single message, a system document and a document in history. Each has one initial
request and two identical repeats, requesting 64 output tokens. The initial request
may itself reuse a previous case's prefix, so inspect both initial and repeat
`cache_n` rather than labeling every first request cold. No real client messages
are automatically padded or rearranged. `--drafter serial` selects the non-MTP control.

The [measured follow-up](../../docs/benchmarks/halogen-cache-gufo-followup-20260930.md)
records the exact-8192 miss alongside working reuse cases, not just the best result.
Cache misses are retained as results; output hashes expose any cold/warm difference.
Flexible mode has no universal bit-identical-to-cold guarantee, even when one test
happens to match. Keep cache Off for the PP512/PP2048 kernel-throughput comparison.

## Article-format, filled-context comparison

`article_bench.py` measures the three-turn workload through the managed gateway
on port 8840. It uses the column definitions and occupied-context geometry of
Reddit post `1wu0m53`, with a disclosed replacement coding corpus. It does not
reproduce the article's separate Aider exercise suite or its unpublished prompts.

Use the same matching tokenizer JSON as the checkpoint. Its digest and the twelve
public code-file digests are pinned in `article-corpus-manifest.json`. Preparation
retrieves text as benchmark data and does not execute it or download model weights.

```powershell
$Py = '.\server\.local\venv\Scripts\python.exe'
$Work = Join-Path (Get-Location) ('server\.local\benchmarks\article-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$Tokenizer = 'C:\AI\models\Flash-Next\tokenizer.json' # Matching local tokenizer export.
& $Py .\scripts\benchmarks\prepare_article_inputs.py --work $Work --tokenizer $Tokenizer
& $Py -m pip install --target "$Work\vendor" --no-deps 'tokenizers==0.23.2'
```

Start the desired managed backend, wait for READY, and use a second PowerShell
terminal for measurement. Do not launch another model alongside the selected one.
The following runs the 256K-capacity / 50%-filled case on an already ready GUFO:

```powershell
& $Py .\scripts\benchmarks\article_bench.py `
  --work $Work --backend gufo --context 262144 --fill 131072 `
  --token-file '.\backends\halogen-wsl2-0.15.1\.local\api-token.txt' --reps 2
```

Backend labels are `gufo`, `projfix`, `halogen-v2`, and `halogen-w4b`. The active
model ID and allocated capacity must match; the client never starts or swaps an
engine. Halogen should use Exact cache for this conversational test. Native profiles
must be explicitly configured for the requested capacity, then stopped/restarted;
changing the client's `--context` does not resize a running model.

| Allocated capacity | Initial input target | Interpretation |
|---:|---:|---|
| 65536 | 32768 | 64K, half occupied |
| 131072 | 65536 | 128K, half occupied |
| 131072 | 98304 | 128K, three-quarters occupied |
| 262144 | 131072 | 256K, half occupied |

Each result keeps exact observed input/output counts, first-token latency, engine
phase counters, cache statistics, acceptance counts, output text and retrieval grade.
The reported three-turn time is normalized to 1000 output tokens per turn; it is not
the elapsed job duration. Truncation is reported, not counted as a completed coding
exercise. Inputs/code outputs are never executed. Review raw files before publishing:
they include workload text and local run IDs, although no API-key values are written.

### Readiness-gated repeats and cold driver controls

The article client now waits for Halogen's own startup validation to finish,
not just an open gateway port. Use `--tag ready-confirmed` (or another unique
alphanumeric tag) to repeat a cell without replacing its earlier evidence.
Original failed/partial runs should remain alongside the replacement.

For a before/after comparison, retain the **original calibrated prompt files**.
Restart the selected engine with cache Off, then run this independent client:

```powershell
$ColdOut = Join-Path (Get-Location) ('server/.local/cold-v2-repeat-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$Prompts = 'C:\Benchmarks\prior-v2-prompts' # Contains prompt-512-prose.txt and prompt-2048-prose.txt.
& $Py .\scripts\benchmarks\gateway_cold.py `
  --profile '.\server\.local\halogen-mtp-shallow-262k.json' `
  --backend halogen-v2 --context 262144 --prompts $Prompts --output $ColdOut `
  --token-file '.\backends\halogen-wsl2-0.15.1\.local\api-token.txt'
```

This sends PP512/PP2048 probes and 128-token prose generation through port 8840,
with a warmup and three measured repeats. Halogen serial/MTP ordering alternates.
Native engines use their configured draft mode, not a silently changed one.
Actual counts, cache misses, prompt/output hashes and raw/calibrated timings are
retained. The client does not start, resize, update or swap any engine.
A driver-only attribution requires matching the other conditions; the mere fact
that one run happened after a driver install does not establish causation.

### Native capacity profiles without replacing your default

An existing native profile's argument vector and metadata must agree. To create
an isolated 64K GUFO configuration from the already qualified local profile:

```powershell
$Profile = Join-Path $Work 'gufo-64k.json'
& $Py .\scripts\benchmarks\prepare_native_profile.py `
  --source '.\server\.local\qualified-gufo.json' --context 65536 --output $Profile
# First stop the existing controller and confirm STOPPED with completed cleanup.
& $Py .\server\controller.py run --config $Profile --port 8840
```

The helper changes only the context argument and its metadata in a new file. It
preserves binary/library pins and never marks an unqualified runtime qualified.
Passing operator checks is not proof that the new capacity fits: the controller's
memory checks and actual measured run remain necessary. The tool never overwrites
an output file or changes your registered default. Keep these profiles in `.local/`.
For Halogen, the existing managed `Start.ps1 -ContextSize ...` path already supports
these capacities; use `-PromptCache Exact` for the conversation matrix and `Off`
for the separate cold controls.

## Additional Halogen reserve observation and larger cold inputs

The October 1 investigation established fresh baselines; it did not promote a new
allocator or prefill setting. [Results and limits](../../docs/benchmarks/halogen-placement-baseline-20261001.md)
include 27 retained PP512/PP2048/PP8192 requests and the recorded Windows memory floor.

In a separate PowerShell 7 terminal, before starting Halogen, run the additional
monitor and leave that terminal open:

```powershell
$Root = (Get-Location).Path
$Watch = Join-Path $Root ('server\.local\reserve-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
.\server\.local\venv\Scripts\python.exe -B -u `
  .\scripts\benchmarks\halogen_reserve_watch.py --repo $Root --out $Watch
```

It observes the next managed Halogen run and requests an ordinary owned stop below
18 GiB available, providing margin above 16 GiB. Existing 12 GiB guards remain intact.
This extra observer is not automatically installed as a Windows service, and cannot
guarantee an instantaneous floor against outside allocations or process termination.
It exits after that owned run stops. It writes local memory samples, not API keys.

`gateway_cold.py` accepts `--sizes 512 2048 8192 16384` (or the separately reviewed 32768 point).
The default remains 512/2048. Supply existing exact-length `prompt-<size>-prose.txt`
files via `--prompts`; insufficient capacity/output room and duplicate sizes fail.
The documented core Halogen benchmark can generate exact 8192-token inputs. Name a
new output directory for every run, and never report a warm prefix-cache hit as cold PP.

For the matched three-engine follow-up, create a new immutable set of bounded prose
inputs with the local, pinned tokenizer. This command only writes text and hashes;
it does not start a model or alter a profile:

```powershell
$Py = '.\server\.local\venv\Scripts\python.exe'
$Prompts = '.\server\.local\cold-inputs-20261002'
& $Py -B .\scripts\benchmarks\prepare_gateway_prompts.py `
  --tokenizer '.\server\.local\benchmarks\driver-compare-20260930-214302\tokenizer.json' `
  --output $Prompts
```

Run only after an isolated 18 GiB-reserve profile is READY, with no competing
traffic and a new output path. Repeat separately for `gufo`, `projfix` and
`halogen-v2` (or explicitly `halogen-w4b`) using matching managed profiles:

```powershell
& $Py -B .\scripts\benchmarks\gateway_cold.py `
  --profile '.\server\.local\gufo-serial-control-262k.json' `
  --backend gufo --context 262144 --sizes 512 2048 8192 16384 `
  --prompts $Prompts --output '.\server\.local\cold-gufo-new' `
  --token-file '.\backends\halogen-wsl2-0.15.1\.local\api-token.txt'
```

The gateway itself observes and calibrates the actual chat-template token count
for each size, then requires exact PP lengths, 128 generated TG tokens, zero cached
tokens and no output clamp. A one-token PP probe has no meaningful decode rate.
Samples retain request/prompt/output hashes, phase and acceptance counters when
exposed, and 0.2-second host RAM/commit observations. These are **not** VRAM peaks;
unknown speculative acceptance is reported as null, never zero. Source-level
tests do not require a running model. Later commands for the other profiles and
the three-turn/quality gates are in `server/.local/NEXT_STEPS.json`.

The cold runner requires `--profile` and refuses a managed run whose recorded
profile SHA-256 differs from those exact file bytes. It also confines raw output
to `server/.local`. For the complete ordered 10-profile matrix, use the two-
terminal commands in `NEXT_STEPS.json`: GUFO serial/Latin/lookup/disk, PROJFIX
serial/64 checkpoints/host MTP, then Halogen 2048 control/4096/8192. The common
`reddit_bench.py` records matched prompt bytes (text-token target labels, not
exact chat-token PP), serial and available speculative TG128, three coding/tool
turns, occupied-context TG128, phase/wall timings, memory minima, hashes and
available draft acceptance. `quality_gate.py` requires same-backend functional
and deterministic hash parity; valid top-N logprobs, when returned by *both*
configurations, are compared as a proxy, never full-logit equivalence. An
unsupported or malformed logprob response is recorded as unavailable.
`compare_reddit.py` compares control/candidate raw workload samples by case and
repetition, including cross-mode serial/MTP comparisons. It refuses different
harness/tokenizer revisions, input hashes and token counts, and records output
hash drift; the ordered matrix invokes it after collecting candidate quality.

## Three-turn agent recording and matched comparison

`halogen_agent_bench.py` records an already READY managed Halogen profile. It never
starts, stops, swaps or clears an engine. Use the existing server Python environment
with `tokenizers` available, the reviewed profile/tokenizer bytes, and the current
managed controller run ID. The client enforces the matching profile/run identity
and 18 GiB host physical/commit reserve. All raw paths must be under `server/.local`.

```powershell
$Py = '.\server\.local\venv\Scripts\python.exe'
$Profile = '.\server\.local\upgrade0162\stock.json' # Prepared, reviewed local profile.
$Tokenizer = '.\server\.local\upgrade0162\tokenizer.json'
$Vendor = '.\server\.local\upgrade0162\vendor' # Existing tokenizers 0.23.2 folder.
$env:PYTHONPATH = (Resolve-Path $Vendor).Path
$RunId = '<READY managed controller run ID>'
$ProfileSha = (Get-FileHash $Profile -Algorithm SHA256).Hash.ToLowerInvariant()
$TokenizerSha = (Get-FileHash $Tokenizer -Algorithm SHA256).Hash.ToLowerInvariant()
$AgentOut = '.\server\.local\agent-control-new'
& $Py -B .\scripts\benchmarks\halogen_agent_bench.py run `
  --profile $Profile --profile-sha256 $ProfileSha --run-id $RunId `
  --tokenizer $Tokenizer --tokenizer-sha256 $TokenizerSha `
  --mode serial --reps 3 --max-tokens 256 --out $AgentOut
```

These local profile/tokenizer/vendor paths refer to the prepared October 3 setup;
substitute the matching reviewed local files when reproducing elsewhere. A vendored
tokenizer package must be on `PYTHONPATH`; the server venv alone does not provide it
in this setup. The command neither downloads a dependency nor prepares a profile.

If the reviewed local vendor folder is absent, obtain the same pinned tokenizer
package in a new isolated folder, then use that folder for `PYTHONPATH`:

```powershell
$Vendor = Join-Path (Get-Location) ('server\.local\agent-vendor-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
& $Py -m pip install --target $Vendor --only-binary=:all: --no-deps 'tokenizers==0.23.2'
$env:PYTHONPATH = (Resolve-Path $Vendor).Path
& $Py -B -c "import tokenizers; print(tokenizers.__version__)"
```

This setup command retrieves the tokenizer library; the matching tokenizer JSON
and reviewed managed profile must already be supplied locally. Retain the package
version and its installation provenance with the raw recording.

The first run snapshots the public repository sources and constructs a deterministic
shared system prefix of at least 8192 tokenizer text tokens. The three turns request
a function edit, two tests after an explicitly synthetic file/test-report payload,
and a follow-up function edit. Three repetitions mean nine measured calls, with no
separate warmup. The next turn retains the complete actual assistant message,
including any reasoning fields. Actual API input counts include chat framing and
are recorded separately from local text counts.

For a speculative or cache candidate, use its reviewed profile pins and READY run
ID, a fresh output directory, and both `--workload "$AgentOut\workload"` and
`--control $AgentOut`. Reusing the immutable workload prevents changed repository
snapshots from changing the comparison. For an Off/Exact/Flexible timing series,
hold prefill chunk and token arena explicitly at 32768 across all three profiles;
otherwise inherited chunk behavior is not controlled by the comparison.
The client records hits and misses equally and does not enforce cold requests.
The published fixed-32768 Exact run recorded zero hits; its passing checks therefore
do not establish correctness after an Exact warm hit. A comparison with chunk unset
must separately retain the effective engine behavior and its combined deployment scope.

An offline comparison requires no live engine:

```powershell
& $Py -B .\scripts\benchmarks\halogen_agent_bench.py compare `
  --control $AgentOut --candidate '.\server\.local\agent-candidate-new' `
  --out '.\server\.local\agent-comparison-new.json'
```

Inspect `summary.json` for both `passed_execution` and `passed_quality`, plus the
comparison when supplied. Execution success alone does not establish code quality.
`length` outputs are incomplete. Function outputs use bounded restricted grading;
the test turn checks the required straight-line AST shape without running pytest.
This is a small synthetic coding fixture, not an Aider exercise result. Comparisons
require matching harness/workload/tokenizer identities and retain input/output,
actual token-count and finish-reason drift. Draft/cache counters remain unknown
when absent. Per-call host memory samples are not VRAM peaks.

## Functional, strict-format and first-token quality gate

Run `quality_gate.py` separately on the same READY managed profile, with a new
output directory. `--structured-json` constrains only the JSON/tool-JSON cases:

```powershell
& $Py -B .\scripts\benchmarks\quality_gate.py `
  --profile $Profile --run-id $RunId --mode serial --structured-json `
  --out '.\server\.local\quality-control-new'
```

Repeat with the candidate profile/run ID and `--control` pointing to the control's
`quality.json`; the suite revision and structured policy must match. The ten checks
separate functional success from strict formatting and include code, multilingual
responses, long-context retrieval, memory and interleaved state checks. Keep real
strict-format failures, including correct JSON wrapped in unwanted Markdown.

When supported, separate one-token requests compare exposed top-N probabilities
(top 5 on the pinned 0.16.2 API). This is a target-model prefill proxy, not full-logit
or MTP draft-logit equivalence. Grammar-masked JSON cases omit that incompatible
probe and record it as unavailable. Auxiliary/probe/repetition calls contribute to
the recorded host-memory minimum. See the [0.16.2 report](../../docs/benchmarks/halogen0162-upgrade-20261003.md)
for preserved harness/API failures and the current qualification status.

## Research-only standalone n-gram extraction

`halogen_ngram_extract.py` copies the reviewed lookup tensor into a canonical
single-entry HGN v2 file without model execution or tensor conversion. No real
large-table extraction has been completed in the 2026-10-03 investigation; fixture
tests do not establish a deployed model variant or measured inference performance.

The CLI accepts only the pinned 124068083904-byte w4b source with SHA256
`9c116bbc01f77b7a15464c1a124eb3325b286089b8a2a6f2856c9b246a235bd6`,
the reviewed `layers.1.ple.ngram_embedding.weight` storage/shape, and a previously
reviewed `bounded_hash.py` receipt from the same host/filesystem. That receipt must
match the complete current source file identity; copying a receipt between Windows
and WSL does not supply the required identity. Output and receipt must be new files
in existing directories, with enough space for the 51200246144-byte output.

```powershell
# Research invocation only; use the reviewed source and same-host checksum receipt.
$Source = 'C:\Research\reviewed-w4b.hgn'
$Receipt = 'C:\Research\reviewed-w4b.hash.json'
$Extracted = 'C:\Research\ngram-standalone-new.hgn'
& $Py -B .\scripts\benchmarks\halogen_ngram_extract.py $Source $Extracted `
  --source-receipt $Receipt --verify-xor
```

Reads are bounded to 8 MiB. Payload and full output SHA256 are computed during the
copy; source/output identities are rechecked before the receipt is published. XOR32
is checked when NumPy is available, and `--verify-xor` requires it for this large
payload. Omitting the flag can leave XOR verification unavailable, which the receipt
records explicitly. The default receipt path is `<output>.receipt.json`; `--receipt`
selects another new path. The script refuses existing outputs, source/output aliases,
parent traversal and symlink/reparse paths. Generated receipts contain private paths
and must be sanitized before publication.

## Selected-ten-expert ONNX prototype

`halogen_npu_expert_onnx.py` retains single-expert conversion and adds bounded
q4c extraction of ten selected MTP experts through `--hgn`, `--manifest`,
`--expert-ids` and `--out`. The graph fixes those IDs and accepts dynamic routing
coefficients. `--check-model`, `--provider cpu|npu`, `--reps` and `--report`
provide a separate replay with numerical checks and execution-provider attribution.
The NPU path refuses CPU fallback; compilation and warm-up are reported separately.
Optional `--ep-dir` selects a complete byte-identical copy of the installed
provider directory, verified before loading, for the measured local resource-path workaround.

See the [conversion and qualification report](../../docs/research/halogen-npu-top10-20261004.md)
for commands, measured evidence and the missing native Halogen state interface.
Coordinate hardware replay with engine cleanup and the 18 GiB physical/commit
guard. This is a sparse expert prototype, not full MTP or live Halogen offload.
