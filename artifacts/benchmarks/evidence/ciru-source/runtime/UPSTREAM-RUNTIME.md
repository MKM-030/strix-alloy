# GLM5.3 Flash CIRU STRIX IU4 runtime packages

This directory is the self-contained runtime-engine deliverable.
The 128K default (131,200 tokens, 12 GiB KV and 8 GiB host staging per rank) passed the
bounded 131,000-token generation/restart/reuse gate on packaged dev9.
The earlier minimal packaged 64K NHI functional gate passed, including
useful disk-prefix reuse on dev8. This is not a new full
performance or quality qualification; see the
[versioned gate report](../../benchmarks/packaged-nhi-gate.md).
It does not depend on a GitHub repository. `INSTALL-RUNTIME.sh` installs the
documented layout:

- `/srv/llm/runtime/vllm-glm53-strix`
- `/srv/llm/runtime/aiter-gfx1151`
- `/srv/llm/venvs/vllm-rocm10-gfx1151`
- `/srv/llm/runtime/vllm-glm53-strix/runtime-env.sh`

The same runtime environment supplies FastAPI, httpx, and Uvicorn for the
Apache-2.0 mirrored generation frontend under
`../generation-frontend/`. External-launcher TP2 generation must enter through
that frontend (port 8083 by default), which submits an identical request to
both rank-local port 8100 APIs, returns rank 0, and drains rank 1. The frontend
may run on either node and has no CiruStrixLink application dependency.

The current candidate identities are:

- vLLM source base: `9255fd9fb9fedf4b29d574a8d8bb21d93892cc98`, plus the
  uncommitted Python-only store/load group projection, Mamba cached-state
  indexing, and paired prefix admission fixes; this is not a new dev9 commit.
- vLLM runtime version: `0.1.0rc2.dev9+g9255fd9fb9.rocm100`
- vLLM wheel:
  `vllm-0.1.0rc2.dev9+g9255fd9fb9.rocm100-cp314-cp314-linux_x86_64.whl`
- Patched vLLM source archive:
  `GLM5.3-Flash-CIRU-STRIX-IU4-vllm-source-v0.1.0-rc2-dev9.tar.gz`
- AITER: `ec6b1a5d0bdbc9d43f9375dcc1516f87efac1c57`
  (identity-only child of `2fe3fff6adb4ecbdc0aa2b9c2ce9618b5e6b3046`)
- AITER Composable Kernel: `fdf4bb7fcc984811cef48ce817d89aac064b984a`
- Python: 3.14.3
- ROCm: 10.0.0, gfx1151
- PyTorch: 2.13.0+rocm10.0.0
- TileLang: 0.1.10, with Apache TVM FFI 0.1.10 (required for fused GLM mHC)

TileLang is a production dependency, not optional profiling tooling. Omitting it
silently sends this model's mHC operations through vLLM's unfused Torch fallback.
The completed requirements repair pins TileLang and its prerequisites. With
NHI, DFlash2 k7, the 64K profile, prefix caching enabled, and the default
2,304-token batch budget, the packaged 2,048-prompt / 128-output check measured
402.455 prompt tokens/s, 5.089 s TTFT, 23.686 decode tokens/s (excluding prefill),
and 56.593% draft acceptance. The production pair was restored to that
configuration for that check; these are recorded 64K results, not qualification
of the newly requested 128K default.

A matched cache-off comparison used a 20,499-token prompt plus 128 generated
tokens: the 2,304-token budget gave 395.305 prompt tokens/s and 51.856 s TTFT;
8,192 gave 377.484 prompt tokens/s and 54.304 s TTFT. The larger budget did not
help this workload and is not endorsed as the production default. Earlier
cache-off recovery checks with the 8,192 budget measured 425 prompt tokens/s
at 2,048 prompt tokens and 391 at 8,119 prompt tokens.

A 20,480-token batch budget did not pass startup with the 64K/6 GiB KV profile:
the engine required 10.35 GiB of KV allocation, so there is no speed result
for that budget. The disk-prefix-qualified default remains 2,304;
`MAX_NUM_BATCHED_TOKENS` permits explicit experimental overrides. These are
bounded performance checks, not a full context sweep or broad acceptance or
quality requalification. The separate bounded 128K generation/restart/reuse
gate passed; 64K remains the lower-memory fallback and 256K is experimental.

The model launcher defaults to `CONTEXT_PROFILE=128k`. Fresh user/NHI service
installations select context profile 2; existing selections are preserved.
Use `glm53-context 2` or `sudo glm53-nhi-context USER 2` on both nodes to move
an existing installation to that default for its next paired start. Profile 1
retains 64K/6 GiB KV, and profile 3 is unvalidated 256K/24 GiB KV; all use the
8 GiB host tier and the default 2,304-token batch budget.

The production launcher defaults `VLLM_NHI_TIMEOUT_MS` to 30,000 so a rank's
first-use JIT compilation does not trigger the former one-second peer timeout.
This is a failure deadline, not an added delay: successful exchanges return
immediately.

The vLLM and AITER wheels are built on Ubuntu 24.04 (glibc 2.39, GCC 13) and
are tagged `cp314-cp314-linux_x86_64`. Their compiled extensions are qualified
without Nix-store, `/srv/llm/work`, or other host-specific RPATH/RUNPATH
entries. They are not manylinux wheels and should be treated as Ubuntu 24.04+
or equivalently compatible x86-64 artifacts.

## NixOS installation

Import the included module from your NixOS configuration, then rebuild the
host once:

```nix
{
  imports = [ /path/to/runtime/packages/nixos-module.nix ];
}
```

```bash
sudo nixos-rebuild switch
```

The module enables `programs.nix-ld` for the portable Python/ROCm wheels and
publishes `CIRU_HOST_LIBRARY_PATH` for login sessions. Enter the included
development shell and run the installer from this directory:

```bash
cd /path/to/GLM5.3-Flash-CIRU-STRIX-IU4/runtime/packages
nix-shell ./shell.nix
bash ./INSTALL-RUNTIME.sh
exit
```

`shell.nix` provides `uv`, GCC, CMake, Ninja, Make, Git, `pkg-config`, `xxd`,
and the standard archive/file commands. It also exports the same
`CIRU_HOST_LIBRARY_PATH` used by `runtime-env.sh`. No Nix-store path is
embedded in the packaged wheels or shared objects.

At install time, `INSTALL-RUNTIME.sh` writes the shell's evaluated path as one
inert line in
`/srv/llm/runtime/vllm-glm53-strix/ciru-host-library-path.txt`.
`runtime-env.sh` reads that data file only when `CIRU_HOST_LIBRARY_PATH` is
absent; it never sources the file as shell code. User and privileged NHI
services therefore do not depend on a login manager or `nix-shell`
environment inheriting the variable. The generated file is host-specific
install state and is not embedded in any packaged wheel or shared object.

After installation, the release root's `run-node.sh` automatically enters this
packaged `shell.nix` when `nix-shell` is available. This supplies Triton with
the NixOS compiler wrappers and host development headers it needs during
initialization. Other Linux hosts launch directly with their installed
toolchain.

The source archives have no `.git` directory and retain the upstream license
and notice files. The dev9 vLLM archive retains dev8's two matching
projections: `_build_partial_tail_store_jobs` remaps physical KV
group IDs before aligned/partial stores, and `update_state_after_alloc`
selects the same transferable groups from physical block allocations before
loading. The second change fixes dev7's load-allocation assertion after a
successful cache lookup. Dev9 additionally indexes cached recurrent states
using the Mamba group's 2,304-token block size, not the global 64-token block
size (source slot 55 rather than 2,015 in the observed failure), and coordinates
capacity-bounded prefix admission across the mirrored external-launcher ranks.
The final positive cached-read gate passed: both ranks admitted 129,024 tokens
and loaded 1,600,792,576 cache bytes onto GPU. The earlier repair-write request
completed without GPU cache hits and was not counted as the read gate.
Native extensions are unchanged.
The archive's `ciru-release/DEV9_CACHE_PATCH.md` records the Python delta.
The candidate launcher caps prefill at 2,304 batched tokens to materialize the
KDA checkpoint. The AITER archive contains
the exact Composable Kernel submodule contents. The separately packaged
seven-kernel source archive excludes prior build output and shared objects.

`requirements-runtime.lock` pins only the direct production requirements for
this local HTTP serving profile, mirrored frontend, and AITER JIT. The
installer resolves their transitive dependencies. ROCm/PyTorch is installed
as a separate exact stack;
cloud SDKs, telemetry exporters, profiling/benchmark tools, docs/tests,
training packages, and unused alternate kernel/model-streaming stacks are not
part of the public runtime resolution.

The live isolated install identified and fixed two omissions in the original
package: `runtime-env.sh` now accepts ROCm 10's `_rocm_sdk_core` plus
`_rocm_sdk_libraries` wheel layout, and the production lock includes
`model-hosting-container-standards==0.1.16` as required by vLLM.

The installer also runs `python -m rocm_sdk init` after installing the AMD stack.
This expands the already-installed development bundle and its device links into
`_rocm_sdk_devel`, providing the compiler/library layout used by the fused
kernels. It is installation work, not a model startup or a per-request check.

## Privileged NHI runtime staging

The `CAP_SYS_RAWIO`-bearing system service requires a separate root-owned
runtime, conventionally `/opt/ciru/glm53-iu4`. Copy the venv, vLLM source,
AITER source, runtime environment, and gfx1151 libraries there before using
`install-nhi-system-service.sh`. Copy the complete CPython 3.14.3 runtime too:
copying a UV-created venv alone leaves its interpreter symlink pointing into
the original user's home directory.

With CPython staged at `/opt/ciru/glm53-iu4/python`, the required relationships
are:

- `venv/bin/python` resolves to
  `/opt/ciru/glm53-iu4/python/bin/python3.14`; the `python3` and `python3.14`
  aliases must resolve into that same root-owned runtime.
- `venv/pyvenv.cfg` contains
  `home = /opt/ciru/glm53-iu4/python/bin`.
- The full staged tree and its symlinks are owned by `root:root`, with no
  group/other write permission. Directories must be traversable and files
  readable by the service user; preserve executable bits on programs. The
  staging repair uses `chmod -R u=rwX,go=rX` on this exact runtime tree, not on
  model data or user home directories.

Do not hardlink a user-owned source tree into this privileged tree: changing
ownership would also change the source inode. Use copies or reflinks. The
packaged launcher invokes the staged Python as
`python -m torch.distributed.run`, avoiding stale copied `torchrun` shebangs.
This runtime relocation is a separate operator step; the public NHI service
installer validates the paths but does not automate the Python copy/relink.

`runtime-env.sh` defaults `AITER_JIT_DIR` to the service user's writable
`${XDG_CACHE_HOME:-$HOME/.cache}/GLM5.3-Flash-CIRU-STRIX-IU4/aiter` directory.
When that directory lacks `module_aiter_core.so`, it seeds the module from
`$VLLM_VENV/var/aiter-jit-gfx1151/module_aiter_core.so` if the packaged module
is present. Existing JIT modules are never overwritten. This keeps the
privileged runtime tree immutable while avoiding an unnecessary AITER core
C++ rebuild on the first use of a new cache. An explicit `AITER_JIT_DIR`
continues to override the default.

### NixOS host compiler for the NHI service

The capability-bearing system service does not enter the user launcher's
`nix-shell`. Its host-side Triton launcher builds require the Nix compiler
wrappers and their standard headers; bare ROCm clang is not a replacement.
Add this Nix-managed systemd drop-in to the host configuration on both nodes,
then apply the NixOS configuration before starting the pair:

```nix
{ pkgs, ... }: {
  environment.etc."systemd/system.attached/GLM5.3-Flash-CIRU-STRIX-IU4-nhi@.service.d/10-nixos-toolchain.conf".text = ''
    [Service]
    Environment="CC=${pkgs.stdenv.cc}/bin/cc"
    Environment="CXX=${pkgs.stdenv.cc}/bin/c++"
  '';
}
```

`runtime-env.sh` preserves these explicit `CC`/`CXX` values. The drop-in is
host configuration, not an embedded build-host path in the public wheel.

### Host-staging scratch versus persistent prefix storage

The packaged NHI unit sets
`TemporaryFileSystem=/dev/shm:rw,nosuid,nodev,mode=1777,size=16G`. Each service
therefore owns an isolated tmpfs for `vllm_offload_<engineid>.mmap` and related
runtime scratch; that mount disappears when the service stops. The 16 GiB
value is a limit, not a preallocated reservation. This avoids a stopped
instance's 8 GiB staging file remaining alongside the next instance's file.

The disk prefix cache under `PREFIX_CACHE_ROOT` is separate local-NVMe data
and survives this scratch teardown. The 8 GiB tier passed earlier 64K restart/reuse:
dev8 admitted 2,304 cached tokens and loaded 127,419,136 bytes to GPU on each
rank after reading the compatible dev7-written cache. No allocation failures
were observed. The one-token replay is a cache-functional check, not a TG or
quality benchmark, and does not establish a guaranteed free-memory reserve.

The later 128K dev9 gate replayed the same 131,000-token request after restart
and admitted 129,024 cached tokens on both ranks, with 7.568 s TTFT and actual
GPU loading. The 8 GiB setting still limits RAM staging only: the filesystem
tier has no automatic eviction or byte quota, and the long-prompt test required
substantial NVMe headroom. See the [gate report](../../benchmarks/packaged-nhi-gate.md)
and [storage guidance](../../README.md#persistent-disk-prefix-cache).

## Kernel source licensing

`GLM5.3-Flash-CIRU-STRIX-IU4-kernels-source-v0.1.0-rc1.tar.gz` is the clean
source snapshot for the seven model-specific native libraries. The release
owner approved Apache-2.0 for the six Ciru-authored groups: `dense-kda`,
`m4-residual`, `m8-align`, `resident-g128`, `top8-epilogue`, and `iu4-m1`.
Their sources and Ciru-authored builders carry SPDX/copyright headers, and the
archive includes the full Apache-2.0 `LICENSE` plus a concise provenance
`NOTICE`. A provenance audit found no outside permission blocker in those
groups.

The `nhi-m8-bf16` sources are not relicensed. The bridge retains its MIT SPDX
identifiers, and the bundled USB4STREAM Linux UAPI header retains
`GPL-2.0 WITH Linux-syscall-note`; those files are byte-identical to the
previous qualified source snapshot.

This runtime-engine bundle alone is not the complete model payload. The two
rank payloads and seven qualified model-specific shared libraries must also be
present before an end-to-end model launch is possible.
