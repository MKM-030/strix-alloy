# Root-owned CPU build handoff

This is a recipe, not a build receipt. The source agent did not execute WSL,
compile/load an ELF, or run the C harness. Root's established toolchain is
Ubuntu-24.04 / user `revn`, GCC 13.3.0, Linux x86-64 LP64. Build only in the
fresh output below. No engine, model, observer preload or device is invoked.

Run this exact PowerShell command as root's authorized CPU preparation step:

```powershell
$phaseCpuBuildScript = @'
set -eu
src=/mnt/c/Projects/strix-alloy-clean/scripts/benchmarks/experimental/halogen0181_phase_clocks
out=/mnt/c/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/halogen0181-phase-clock-cpu-build-20261012
test ! -e "$out"
mkdir "$out"
/usr/bin/gcc --version > "$out/compiler.txt"
/usr/bin/gcc -dumpmachine > "$out/compiler-target.txt"
test "$(/usr/bin/gcc -dumpmachine)" = x86_64-linux-gnu
test "$(/usr/bin/gcc -dumpfullversion)" = 13.3.0
python3 -B - "$src" "$out" <<'PY'
import hashlib,json,pathlib,sys
src,out=map(pathlib.Path,sys.argv[1:])
raw=(src/'source-pins.json').read_bytes();pins=json.loads(raw)
for name,pin in pins['files'].items():
    data=(src/name).read_bytes()
    assert len(data)==pin['bytes'] and hashlib.sha256(data).hexdigest()==pin['sha256'],name
(out/'source-pins.json').write_bytes(raw)
(out/'source-pin-check.json').write_text(json.dumps(dict(source_pins_sha256=hashlib.sha256(raw).hexdigest(),source_files_verified=len(pins['files']),engine_loaded=False,hardware_accessed=False))+'\n')
PY
cd "$src"
/usr/bin/gcc -m64 -march=x86-64 -O2 -std=gnu11 -fPIC -fno-builtin -fno-stack-protector -fvisibility=hidden -Wall -Wextra -shared phase_clock.c phase_clock_entry.S -Wl,--version-script=phase_clock.map -Wl,--no-undefined -Wl,-z,relro,-z,now,-z,noexecstack -ldl -o "$out/libhalogen0181_phase_clock.so" 2> "$out/observer-build.stderr.txt"
/usr/bin/gcc -m64 -march=x86-64 -O2 -std=gnu11 -fno-builtin -fno-stack-protector -Wall -Wextra core_host_test.c -ldl -o "$out/core_host_test" 2> "$out/core-build.stderr.txt"
"$out/core_host_test" > "$out/core-host-test.stdout.txt"
/usr/bin/readelf --wide --dyn-syms "$out/libhalogen0181_phase_clock.so" > "$out/observer-dyn-syms.txt"
/usr/bin/readelf --wide --version-info "$out/libhalogen0181_phase_clock.so" > "$out/observer-versions.txt"
/usr/bin/readelf --wide --program-headers "$out/libhalogen0181_phase_clock.so" > "$out/observer-program-headers.txt"
/usr/bin/nm -D --defined-only "$out/libhalogen0181_phase_clock.so" > "$out/observer-defined-symbols.txt"
/usr/bin/objdump -d "$out/libhalogen0181_phase_clock.so" > "$out/observer-disassembly.txt"
python3 -B - "$out" <<'PY'
import hashlib,json,pathlib,sys
out=pathlib.Path(sys.argv[1]);names={line.split()[-1] for line in (out/'observer-defined-symbols.txt').read_text().splitlines()}
assert names=={'GLIBCXX_3.4.19','_ZNSt6chrono3_V212steady_clock3nowEv@@GLIBCXX_3.4.19'},names
assert 'C producer fixtures passed:' in (out/'core-host-test.stdout.txt').read_text()
files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(out.iterdir()) if p.is_file()}
(out/'cpu-build-receipt.json').write_text(json.dumps(dict(schema='halogen0181.passive-observer-cpu-build.v1',compiler='GCC13.3.0',mock_C_harness_passed=True,files=files,engine_started=False,observer_loaded_into_engine=False,live_engine_provider_binding_verified=False,actual_engine_phase_stamps_available=False,hardware_accessed=False,phase_count_scope_qualified=False,qualified_token_rates_available=False),indent=2)+'\n')
PY
'@
& 'C:\Windows\System32\wsl.exe' --distribution Ubuntu-24.04 --user revn --exec /bin/bash -c $phaseCpuBuildScript
```

Review the build stderr and entry disassembly. The assembly entry captures the
original return PC, caller SP, R14/RBX/R15 and tail-jumps to the C wrapper; the
mock exercises unchanged return value and one real chrono call, native Request
moves, ID reuse rejection, off/unrelated bypass, RAW failure and short writes.
The DSO is an inert build artifact until root separately authorizes a capture.

The minimum later capture must also record Decode-begin `predicted_count=1` and
the final native D/API count. Static bytes establish that the native count is
initialized to one before the clock call. They do not establish that count128
is 128 token-generation operations entirely inside the measured Decode phase.
Actual count delta is preserved as a diagnostic observation; full phase count
scope stays unqualified until minimal runtime proof closes the first-token
boundary. No `128 / phase_seconds`, historical reconstruction or rescaling is
authorized by CPU build or mock fixtures.
