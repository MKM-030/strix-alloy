# Standalone real-serving kernel identity bootstrap

This candidate is default-off and has no serving lifecycle or entrypoint caller.
The Python launcher loads a separately compiled native bridge in its own main
thread, observes the frozen private own-socket kernel PID/TGID, removes only the
declared added CAP_BPF, writes one fresh private receipt and executes the held
exact flash_serve image with `os.execve(fd, argv, environment)`. No additional
task is substituted for the task whose identity was observed.

The new sources are `scripts/benchmarks/halogen_serving_kernel_bootstrap.py`,
`halogen_serving_kernel_identity.c` and `halogen_serving_kernel_identity.h` in
the same directory. The existing `halogen_kernel_pid_self.h` remains frozen at
SHA256 `21c311d0d5dd458bca7f84b611dc734a9db1a4182938841629c98ed8efd718eb`.
The exact engine is `/usr/local/bin/flash_serve`, 26,052,768 bytes, SHA256
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.

## Sealed plan and activation

The plan schema is `halogen.serving-kernel-identity.plan.v1`. Its exact fields
are `schema`, `enabled`, `nonce`, `service_run_id`, `container_id`,
`manifest_sha256`, `bootstrap_sha256`, `native_source_sha256`,
`frozen_header_sha256`, `native_helper_path`, `native_helper_sha256`,
`native_helper_bytes`, `engine_sha256`, `engine_bytes`, `argv_sha256`,
`environment_sha256` and `capability_policy`. Unknown and duplicate fields
are rejected. `nonce` and `service_run_id` are fresh nonzero 16-byte values
encoded as lowercase hex; `container_id` is the full lowercase 64-character ID.
The native helper must be a pinned regular file under `/candidate/`.

The controller seals the complete argv list and complete environment dictionary
with `digest_json`, which hashes UTF-8 canonical JSON with sorted keys, compact
separators and ASCII escapes. The plan and receipt store those hashes, never
plaintext arguments, environment values or credentials. The controller must
provide the SHA256 of the complete plan bytes separately. Manifest and native
source digests are controller-supplied provenance bindings; the launcher checks
the executable Python source and compiled library bytes against their own pins.
The build controller must verify the declared source-to-library relationship.

`capability_policy` has exactly `only_added: "CAP_BPF"`, `baseline_masks` and
`expected_before_masks`. Both mask objects have exactly `effective`, `permitted`,
`inheritable`, `bounding` and `ambient`, each an unsigned 64-bit integer. The
baseline excludes BPF; before differs only by BPF and includes it in effective,
permitted and bounding. Existing effective CAP_SETPCAP is required to remove
BPF from bounding; the helper does not add it. The baseline must come from an
independent owned observation before the controller adds BPF.

Import and `check` perform no native probing or capability mutation. Launch
requires both the plan's `enabled: true` and explicit `--activate`; its API also
defaults to `activate=False`. A controller can validate its sealed plan offline:

```text
python scripts/benchmarks/halogen_serving_kernel_bootstrap.py check --plan PLAN.json --plan-sha256 PLAN_SHA256
```

After separately qualifying the candidate, an owned controller would invoke
`launch --plan PLAN.json --plan-sha256 PLAN_SHA256 --activate --` followed by
the exact sealed engine argv. The accepted argv contains seven ordered pairs:
`--ck /models/...`, `--port`, `--bind 127.0.0.1`, `--slots 1`, `--ctx`,
`--max-tok` and `--kv-pool`; context and KV pool values must match. There are no
FC shadow, D-wire or provider settings in this contract.

## Identity, cleanup and receipt boundaries

The bootstrap requires one main OS task and compares PID, birth ticks, boot ID,
UID, PID namespace inode, namespace PID chain and capability state before and
after the native call and again before exec. Native kernel PID/TGID and
namespace IDs remain separate fields. Native code checks the runtime capability
extent rather than truncating to compile-time headers. It calls the unchanged
own-socket helper and attempts all BPF-only removal steps even if probing fails:
ambient LOWER, bounding DROP, and capset clearing BPF in E/P/I. Success requires
every non-BPF bit unchanged, BPF absent in all five sets, closed probe references
and the same sole main task. It has no constructor, pins, global attachment,
exec, privilege-adding fallback or change to securebits, UID or no-new-privileges.

The Python side holds and hashes the engine FD, rehashes it before exec and
executes that FD. It also rechecks the held source and library bytes. These are
bounded observations of the owned files, not protection against a concurrent
hostile writer; the qualifying controller must own the candidate files and
launch boundary.

The launcher requires the full container ID as a complete token in its own
`/proc/self/cgroup` view. A private cgroup namespace exposing only `0::/` fails
before native probing. An outer system-proc receipt naming the container does
not satisfy this requirement. CPU qualification must establish the actual
self-view CID and proc mount binding; admission must not be weakened to accept
`/`. Inspection uses the same proc/PID namespace view as the bootstrap.

The receipt is `/tmp/halogen-serving-kernel-NONCE.json`, created with O_EXCL,
O_NOFOLLOW and mode 0600. An existing path, including a dangling symlink, is
rejected before native work, and O_EXCL also protects the final publication.
It binds the nonce/run/container/plan and source/image hashes, identity,
before/after capabilities and Linux monotonic sampling bounds. Its stage is
`pre-exec-intent`, `post_exec_verified` is false and `qualifications` is false.
Publication alone never attests successful exec. Any failure forbids exec;
after native mutation the caller must exit rather than retry or create a child.

Read-only `inspect` revalidates the sealed plan and private receipt, live
birth/boot/namespace/container, exact baseline capability masks, current
command-line hash and the actual `/proc/PID/exe` image. It samples image and
argv again after the final birth check because exec preserves PID and birth.
It returns a separate observation with `post_exec_verified: true`; it never
rewrites the pre-exec receipt or promotes GPU attribution/serving qualification.
These proc observations describe the sampled interval and cannot guarantee a
process will not change afterwards. CLI output contains only safe identity and
hash metadata; failure details are redacted.

## Native build and separate CPU qualification

No native build, WSL execution, BPF execution, serving launch or GPU/NPU/provider
action was performed for this implementation. A Linux owned build controller
can compile the bridge without changing the frozen header:

```sh
gcc -std=c11 -O2 -Wall -Wextra -Werror -fPIC -shared \
  -Wl,-z,relro,-z,now -Wl,-z,noexecstack -I scripts/benchmarks \
  scripts/benchmarks/halogen_serving_kernel_identity.c \
  -o /candidate/halogen_serving_kernel_identity.so
```

This command is a proposed build, not a verified build result. The ABI is 144
bytes, version 1, with capability masks at offset 64. Source pin, exported ABI,
reported frozen-header pin and compiled library hash must all be recorded by
the controller.

Qualification should first use an owned CPU identity reporter independent of
the exact-engine launcher. Record a sole main task's PID, birth/boot/namespace,
full self-view CID and all five baseline masks; add only BPF while preserving
the baseline and existing SETPCAP. Load the bridge in process with ctypes,
call the exact ABI with activation 1, check native PID/TGID, closure and all
five exact baseline masks, then exec a held harmless reporter FD. The reporter
must show the same PID, birth, boot and namespace with BPF absent in every set.
Check refusal for inactive/wrong ABI arguments, a mismatched pin, a stale nonce
and an extra task; do not retry a task after irreversible capability removal.
Only after that separate evidence may an owned real-serving candidate use this
launcher. Existing lifecycle and entrypoint files remain untouched.

Offline regression checks are:

```text
python -m unittest scripts/benchmarks/halogen_serving_kernel_bootstrap_test.py scripts/benchmarks/halogen_gpu_copy_attribution_test.py
python -m py_compile scripts/benchmarks/halogen_serving_kernel_bootstrap.py scripts/benchmarks/halogen_serving_kernel_bootstrap_test.py
```

The bootstrap tests simulate proc/native/exec boundaries; they verify refusal,
fresh publication, byte pins, secret-free receipts and stale/same-birth exec
changes. They do not qualify Linux runtime or native capability behavior.
