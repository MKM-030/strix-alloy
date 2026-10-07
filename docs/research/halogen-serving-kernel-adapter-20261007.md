# Isolated real-serving kernel identity adapter

The candidate adapter is `scripts/benchmarks/halogen_serving_kernel_adapter.py`.
No installed entrypoint, service lifecycle default, admission threshold or user
interface file was changed. Preparation and four focused tests ran offline.
Actual adapter integration into flash_serve remains unexecuted here.

## Reviewed boundary

`service.py:263` accepts only the frozen adapted entrypoint and substitutes
exactly five API launch sites with `/candidate/auth_api.py`. Its Docker command
at line 318 already adds SYS_PTRACE and disables seccomp, and runs the lease
supervisor before Bash `all`. The frozen `all` launch at entrypoint lines
2113–2115 receives the final expanded engine variables; `ENGINE_PID=$!` at
2116 lets the existing traps, wait, watchdog and lease supervision follow the
same task when Python replaces itself with the held exact engine FD.

The generator independently pins service source, frozen adapted entrypoint and
the authenticated result. Its default output is byte-for-byte the existing
authenticated service entrypoint. Explicit `prepare --activate` changes two
locations in a private copy: a refusal guard before configured NPU startup in
`all`, and the single engine command wrapped by the adapter. It preserves all
five API substitutions and every existing PID, wait and signal line.

The pure `isolate_command(service.command(candidate_manifest), activate=True)`
adds only `--cap-add=BPF` and `--cgroupns=host` beside the exact existing
SYS_PTRACE/seccomp configuration. It rejects an unexpected capability addition,
privileged mode, cap-drop setting or existing cgroup override. With activation
omitted it returns the original command. Root must retain normal admission,
ownership, lease, source/mount and environment validation around the private
manifest overlay; this function performs no Docker action.

CAP_BPF initially also belongs to ancestor lease/Bash tasks in the candidate
container. The native bridge removes it from the engine task before exec.
Receipts explicitly set `ancestor_bpf_removal_claimed: false`; this adapter does
not claim container-wide removal or promote GPU Copy attribution. Other task
capabilities are outside this receipt's qualification scope.

## Exact pins and prepared review files

| Item | SHA256 |
| --- | --- |
| Adapter source, 13,472 bytes | `35b22ba3445dd30249c86856fbb04b995fc45eed127ab8fda317cd1fbc3ba5bc` |
| Windows service wrapper, 18,786 bytes | `b075839734127c0926cff9bde4c485bbbd5b0096c4c038ff07beeeacf8fa37c1` |
| service.py | `e8b34cad609aef2dfe32c3f183baa9c9bb4e30114e6e65668664e133f5271ac6` |
| Frozen adapted entrypoint | `e68722b13e6d5f5cb43fbda89f3ea3c92c13be5a8da96113c91b4cfee08a1033` |
| Authenticated entrypoint | `f3ee2640146141aa87b0455e01384c93a1c41fcfa256a9d30ba04105b46564b0` |
| Active private candidate, 133,794 bytes | `f75006c898c1ca04760e1701aa12f10bb887c1cc805a9b648c898fd9e9dbfb1b` |
| Exact wrapped engine boundary plus PID assignment | `a964ef325bab47b4efa1bf91b0a9d3622369eba887d2ebcdee92674c4edd1543` |
| Bootstrap source | `8abeccd17d5bc7dd4e61a4596aa3b7b90caf76256b07568a8d0f649ced8d7961` |
| Native C source | `973380e0e77b9f221a1761ad35f227544e47872b8ab2427a24f6d13e98cb7c97` |
| Frozen own-socket header | `21c311d0d5dd458bca7f84b611dc734a9db1a4182938841629c98ed8efd718eb` |
| Root-compiled helper, 20,800 bytes | `de97fe27f61943ee23b8df54866ece915b7c2a9f55b8768b18fa56c03f67df37` |

The prepared candidate and exact fragment are under
`server/.local/optimization9h-20261004/serving-kernel-adapter-review-3bb5202ce1f64659b042efab30fd8489/`:
`entrypoint-service-kernel-candidate.sh` and `exact-engine-boundary.sh`.
They were generated for review and were not executed.

Root's matching SYS_PTRACE baseline and real bridge/drop/held-Python-FD exec
qualification passed in
`server/.local/optimization9h-20261004/cpu-identity-qualification-0bc8624506f44df1aef72695be05ee4b/result.json`.
The independent no-BPF baseline is
`baseline/baseline-f40d48ecf74243bb81ba28b06ac35ecd.json`, SHA256
`f74b8e9741fb42d6167cd16c50caa853b4aedbe89c3079b5aae836f195673671`.
This is the Windows evidence-copy hash. The original Linux root-owned 0600 file
is `/home/revn/halogen-re/cpu-identity-0bc8624506f44df1aef72695be05ee4b/baseline-f40d48ecf74243bb81ba28b06ac35ecd.json`,
SHA256 `71ee78d171e4c75e064c74932b4b716c55736f6448bdd1432c50182f8bfde7e6`.
Its E/P/bounding masks are each 2,819,368,443 and I/ambient are zero. Qualification
added only BPF to the otherwise matching SYS_PTRACE container. The adapter reads
that measured receipt and never derives the baseline by clearing BPF from its
current masks.

## Policy, final environment and private mounting

The exact policy schema is `halogen.serving-kernel-identity.adapter-policy.v1`.
Fields are `schema`, `enabled`, `scope`, `nonce`, `service_run_id`, `container_id`,
`manifest_sha256`, `service_sha256`, `upstream_entrypoint_sha256`,
`authenticated_entrypoint_sha256`, `candidate_entrypoint_sha256`,
`adapter_sha256`, `bootstrap_sha256`, `native_source_sha256`,
`frozen_header_sha256`, `native_helper_path`, `native_helper_sha256`,
`native_helper_bytes`, `baseline_receipt_path`, `baseline_receipt_sha256` and
`argv_sha256`. `enabled` must be true and `scope` must be `all-engine-task-only`.
Unknown/duplicate fields are rejected. Nonces/run IDs use fresh nonzero
lowercase 32-character hex; the container ID is its actual full 64-character ID.
The no-BPF baseline must come from a different nonce and container.

The owned controller creates the candidate container, then seals the policy
with its actual CID before start. Mount the policy at
`/candidate/serving-kernel-adapter-policy.json` and its separately supplied
lowercase SHA256 sidecar at `/candidate/serving-kernel-adapter-policy.sha256`.
Both are read-only. The sidecar permits CID binding after Docker create without
changing the fixed reviewed command. Preserve policy writes and seal before
start; the sidecar is not runtime configuration to update after launch.

Additional read-only mounts are the adapter, bootstrap, native helper at
`/candidate/halogen_serving_kernel_identity.so`, and the original Linux-native
0600 independent receipt at `/candidate/serving-kernel-baseline.json`. Mount the
private candidate at the existing `/candidate/entrypoint-wsl-candidate.sh` path.
Do not mutate the installed copy. Update the private manifest's mount map and
entrypoint pin before using existing ownership validation. Bind the reviewed
adapter/capability/cgroup delta in that private manifest, without a circular
reference to the final policy hash; the subsequent adapter receipt binds both
manifest and policy hashes.

The policy's argv digest is the controller's expected full ordered engine argv,
sealed with the bootstrap's canonical `digest_json`. The adapter sees Bash's
fully expanded argv and the complete environment after actual setup. It hashes
that environment in process after restoring Bash's direct-engine `_` value to
the validated engine executable path, preserves it and writes a fresh 0600
`/tmp/halogen-serving-adapter-plan-NONCE.json` containing only the standard
bootstrap fields and hashes. It also writes
`/tmp/halogen-serving-adapter-binding-NONCE.json`, binding policy, manifest,
sources, candidate, independent baseline and final argv/environment digests.
No plaintext environment, argv or credentials appear in these artifacts or
adapter output. The binding stage remains pre-exec intent and unqualified.
The source policy authorizes sealing the observed final environment; its
environment digest is not an independently predicted post-setup digest.

The adapter requires explicit `--activate` independently of the enabled policy,
checks v2/NPU-free scope, rejects reused receipt paths, and delegates the existing
bootstrap. The bootstrap requires the actual full CID in self cgroup, sole main
task, exact capability delta and source/image pins, observes real kernel PID,
closes the probe, removes only BPF, rechecks the task and held bytes, then execs
the frozen exact flash_serve. Native kernel PID/TGID remains separate from the
same-proc-view namespace chain.

## Root review and inert boundary check before actual use

Reproduce the private candidate without launching anything:

```text
python scripts/benchmarks/halogen_serving_kernel_adapter.py prepare --entrypoint backends/halogen-wsl2-0.16.2/.local/entrypoint-wsl.sh --service-script backends/halogen-wsl2-0.16.2/scripts/service.py --output PRIVATE_CANDIDATE.sh --activate
```

For the one inert CPU boundary check, execute only the pinned extracted fragment,
with a harmless stub mounted at the adapter path and a harmless SHA sidecar.
Define checkpoint, port, slots, context, max-token and pool variables, plus a
synthetic environment sentinel. Do not execute the full entrypoint, which has
real setup actions. The stub should record only argv/environment digests and
its own PID. After the exact fragment, wait for `$ENGINE_PID` and confirm that
it equals the stub's PID, the argv digest matches the expected 15 arguments,
the synthetic environment reached the stub and no sentinel plaintext entered
receipt/log output. This qualifies the exact shell expansion and background
PID boundary, not native behavior or engine startup. Root separately reviews
the four focused offline tests and the complete candidate diff.

After a separately owned admitted real-engine start, inspect with the bootstrap
inside the same container proc/PID view, supplying the fresh launch-plan SHA
from the adapter binding. A root-only read-only Docker exec can run
`python3 -I /candidate/halogen_serving_kernel_bootstrap.py inspect --plan
/tmp/halogen-serving-adapter-plan-NONCE.json --plan-sha256 LAUNCH_PLAN_SHA`.
Inspection checks birth/boot/namespace/full CID, exact baseline capabilities,
actual exe hash and repeated argv/image samples. Collect private receipts with
root-owned reads; the previous CPU attempt demonstrated that non-root reads of
root 0600 files must fail. Publication alone never proves exec. A new engine
receipt must not retroactively attest old traces or Copy-counter ownership.

The inert stub and shell driver are also in the private review directory.
`boundary-stub.py` is 3,799 bytes, SHA256
`86b49c9a0d72aef69828259d12b1bd9dd8a0c85e86e2b264ca21015d7ae8c7c1`;
`boundary-driver.sh` is 701 bytes, SHA256
`d56917c3058dc5e0abb77d7999b8ad31a65819d27d8414f5b149571262d3e749`.
The stub's golden vector and engine observation both use the restored original
engine `_`; the engine stage actually modifies its environment before hashing.
The driver checks the entire environment digest, synthetic canary digest and
child PID. It writes fresh root 0600 artifacts to a Linux-native private mount.

## Isolated Windows execution wrapper

`scripts/benchmarks/halogen_serving_kernel_service_wrapper.py` imports the exact
original service source, keeps its `__file__` so the guard subprocess remains
the original `service.py --guard`, and delegates to original `service.main`.
Only four in-memory seams are replaced: service_entrypoint, build_manifest,
command and r.docker create/start interception. The original stock admission,
60-second stability observation, 40/131 GiB start limits, 18 GiB runtime reserve,
lease/guard, startup monitoring, authenticated smoke checks, stop and cleanup
continue to run. Original source/defaults are untouched; Python hooks, sys.path
and the temporary ALLOY_MANAGED setting restore when main exits. ALLOY_MANAGED
prevents the original interactive token-value print; new output contains no
credential plaintext.

The root plan schema is `halogen.serving-kernel-identity.service-overlay.v1`.
Its exact fields are schema, enabled, nonce, scope, image, source_sha256,
service_argv_sha256, helper, baseline and policy_directory. Scope is
`v2-all-engine-task-only`, and both plan enabled and explicit --activate are
required. The source map covers all seven fixed wrapper/service/adapter/
bootstrap/native/header paths. Helper binds Linux path, SHA and bytes. Baseline
binds Windows path/raw SHA separately from the original Linux path/raw SHA;
the root-only Linux checker also requires canonical parsed-JSON equality.
Windows pin reads use O_BINARY so CRLF bytes are hashed without translation.
The baseline's owner/mode/hash requirements remain unchanged.

The wrapper prepares fresh root-owned Linux 0700 policy directories and empty
0600 policy/SHA files before Docker create, adds only read-only mounts to the
private manifest and records the reviewed BPF/cgroup delta. It computes the
expected final argv from the frozen entrypoint variables, including the
entrypoint's min(max-token arena, context) clamp. Before create/start it rechecks
all local source pins and both independently pinned baseline representations.
After create, it verifies the full actual CID, stock ownership, image,
SYS_PTRACE+BPF only, host cgroup namespace, every read-only binding and declared
environment before filling the same placeholder inodes with the CID-bound
policy. It binds the exact bytes of the already persisted private manifest.
Final seal/CID checks complete before delegating the stock Docker start.

The prepared root plan is
`server/.local/optimization9h-20261004/serving-kernel-adapter-review-3bb5202ce1f64659b042efab30fd8489/sealed-service-overlay-plan.json`,
2,045 bytes, SHA256
`7bf60692518fd3d49ad6ddf91fb48ece47868110ba16b1e05b3dca0d6b13c118`,
nonce `0d625f65bbd7407f866b105cc36c325d`. It seals normal arguments
`--checkpoint v2 --context-size 262144 --serve-seconds 0 --startup-timeout 900`.
It passed local source/baseline/argument validation without runtime action.

The exact isolated startup CLI is:

```text
python scripts/benchmarks/halogen_serving_kernel_service_wrapper.py --plan server/.local/optimization9h-20261004/serving-kernel-adapter-review-3bb5202ce1f64659b042efab30fd8489/sealed-service-overlay-plan.json --plan-sha256 7bf60692518fd3d49ad6ddf91fb48ece47868110ba16b1e05b3dca0d6b13c118 --activate -- --checkpoint v2 --context-size 262144 --serve-seconds 0 --startup-timeout 900
```

Root's private capture runner may wrap the instance's original_docker delegate
only for the exact start CID. That delegate runs after all stock and overlay
checks, so a finite 12-second recorder starts immediately before Docker start.
The wrapper has no capture option or changed capture default. Keep the proven
VM/Guest/context provider settings and use the existing maximum 256 MiB decoder
bound. Require complete decoder summary and zero loss; an output-limit abort
cannot support attribution. This is a creation identity capture, with no token
throughput series and no diagnostic repetition if incomplete.

Normal stop remains `python backends/halogen-wsl2-0.16.2/scripts/service.py --stop`;
it targets the stock state written by the delegated controller. After root-owned
terminal/cleanup checks, restore the visible HistoricalStock service with its
existing normal launcher and saved options, using the permanent 40/131/18 GiB
limits. Do not use the isolated wrapper for that restoration. This agent did not
run any of these commands or perform a hardware action.

Focused offline validation is
`python -m unittest scripts/benchmarks/halogen_serving_kernel_adapter_test.py`.
Actual candidate review, inert Linux shell check and real-engine post-exec
inspection belong to root; this agent performed no WSL, device or start action.
