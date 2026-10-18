# Native Windows Hipfire

Local Windows x64 source port of [Hipfire](https://github.com/warpfront/hipfire), based on upstream `ddee82c7464946c86f946d89af1b5634f212d466`, the retained `native-mtp-drafted-counter.patch`, then the Windows patch under `patches/`. The counter instrumentation reports actual offered MTP drafts so acceptance uses the prior WSL denominator. The retained source snapshot already contains it; the snapshot is not a pristine upstream checkout. Hipfire and Kaden Schutt attribution and upstream licenses are retained there.

The final dedicated-memory source passed a native Windows release build and a complete 16K MTP cohort on the installed HIP 7.2 runtime (`gfx1151`). Three measured requests averaged **1,240.2 prefill / 26.53 decode tok/s**, with **210/330 = 63.64% native draft acceptance**. These are Hipfire pipeline wall-time rates, with its first-token convention; see [the measurements and limits](../../docs/benchmarks/hipfire-native-windows-20261018.md). They establish functional native inference for this fixture, not a speed record or independent full-model numerical equivalence.

The first release link exposed Linux `dlopen`/`dlsym`/`dlclose` references in the optional loaded-code diagnostic. The exported eleven-file patch includes the root-owned repair: Linux retains its resolver; other platforms explicitly report that ROCr diagnostic unavailable.

Windows host allocation sizing subtracts 18 GiB from both available physical RAM and available process commit, then takes their minimum. GPU sizing uses dedicated memory only with exact HIP R0600 LUID/AMD DXGI node-0 identity and a valid native adapter-global PDH `Dedicated Usage` sample. It takes the minimum of HIP free, dedicated capacity minus global usage, and LOCAL budget minus process usage; shared RAM is never added. Missing proof falls back to the reserved host allowance, and zero host allowance admits no device capacity. Normal node mask 1 is accepted; mask 0 is allowed only for the qualified gfx1151 integrated single-visible-device tuple, whose real HIP allocation was observed in matching DXGI LOCAL node-0 and PDH phys-0 counters. Other masks remain conservative. Keep the continuous host reserve guard during loading because these are volatile snapshots.

`Build.ps1` requires existing pinned upstream source (pristine or the retained counted snapshot), an installed Windows x64 Rust toolchain, a populated Cargo cache, HIP SDK 7.2 and an x64 Visual Studio Developer/Native Tools shell with the Windows SDK. It downloads nothing: Cargo runs `--locked --offline`. Missing dependencies must already be available in the supplied Cargo cache. The wrapper does not install drivers, Rust, models or kernel packs.

```powershell
.\backends\hipfire-windows\Build.ps1 `
  -SourcePath 'E:\strix-alloy\hipfire-mq2-ddee82\src' `
  -BuildRoot 'E:\builds\hipfire-native-example' `
  -RustToolchainPath 'E:\builds\rust\toolchains\1.99.1-x86_64-pc-windows-msvc' `
  -CargoHome 'E:\builds\cargo-cache'
```

Use your actual installed toolchain/cache paths. The wrapper verifies touched baseline files plus Cargo manifests/lockfile, copies source into a fresh `BuildRoot\src` without Git metadata/output caches, detects the counter patch with `git apply --reverse --check`, and applies it only when absent and applicable. It verifies the exact counted `common.rs`/`qwen.rs` hashes, then checks/applies the Windows patch and verifies touched output hashes before building CLI/daemon. The retained source is unchanged. Outputs are `BuildRoot\bin\hipfire.exe`, `daemon.exe` and `build-receipt.json`. Select a fresh build root for another build; this wrapper never deletes a checkout.

`Start.ps1` runs the native CLI in the foreground with an existing local MQ2 model and its existing rank-q4 PLE table at the full model path plus `.ple-q4`. Keep their retained bytes and binding intact; the wrapper neither converts nor copies them. It requires an existing bearer-key file, whose value is handled only by Hipfire's `--api-key-file` support. The wrapper does not read or log the token. Use a new empty private state directory for each launch.

```powershell
.\backends\hipfire-windows\Start.ps1 `
  -BinaryDirectory 'E:\builds\hipfire-native-example\bin' `
  -ModelPath 'E:\models\existing-mq2-model' `
  -StatePath 'E:\builds\hipfire-native-run-01' `
  -ApiKeyFile 'E:\private\hipfire-api-key' `
  -ListenAddress '127.0.0.1' -Port 11439 -MaxSequence 32768
```

The private config selects legacy KV, HIP replay, native MTP **K2 with n-gram takeover off**, q4 PLE, the measured inline-q8 GDN path, guarded UMA, one serving lane and vision/NPU/DFlash off. PLE hot-store, load-fill and prewarm budgets are zero. Existing unrelated `HIPFIRE_*` process overrides are cleared for the launch and restored on exit. The CLI bind syntax is `serve --model PATH ADDRESS PORT`, with no detach flag; Ctrl-C controls the foreground process. Configuration is written through the pinned native `config set` command. `HIPFIRE_DAEMON_BIN` binds the selected matching daemon explicitly.

The first real load can compile exact registry kernels with the installed SDK into the private state directory. No model/driver download is requested. Device identity, memory admission, table binding, module compilation and loading can still refuse with their actual error; these wrappers do not disable those checks. Windows remains single GPU with legacy KV and HIP dispatch; Redline/ROCr, VMM KV, NPU and Unix cache workers are outside this port.

Both scripts parse without errors under Windows PowerShell 5.1.26100.7462. The native source was built through the root-owned existing-toolchain runner; the fresh-copy `Build.ps1` wrapper has not itself performed a complete build. `Start.ps1` launched the real authenticated HTTP service and returned the exact requested response, with an unauthenticated `/v1/models` request rejected with 401. That startup exposed upstream defaults K7/n-grams on; the final launcher explicitly writes the cohort's K2/n-grams-off settings instead. Its final configuration was accepted by the actual native CLI and verified in the resulting TOML without another model reload. The K2 JSONL cohort and HTTP smoke are distinct checks; the short first-use HTTP request is not a performance sample.

The native API base is `http://127.0.0.1:11439/v1`. Use `Authorization: Bearer <the existing key-file value>` and `Content-Type: application/json`. Select the model ID returned by `/v1/models`. Sampling belongs in the JSON body; the HTTP smoke used `temperature: 0`, `enable_thinking: false`, `stream: false` and `max_tokens: 32`. The foreground window shows Hipfire startup and per-request logs. For continuous physical/commit reserve enforcement, retain an external owned supervisor as used in qualification; this thin launcher does not implement that watchdog itself.
