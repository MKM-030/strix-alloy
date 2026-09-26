# GUFO Live Windows Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement and review this task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a live, fail-closed host/adapter memory snapshot for the GUFO controller without initializing the GPU.

**Architecture:** A read-only Windows PowerShell probe enumerates DXGI adapter identities and gets one timestamped PDH counter sample. A standard-library Python normalizer binds exact hardware/LUID identity, checks scopes, timestamps and values, and returns the existing admission schema. This is collection, not admission, ownership verification, monitoring, or real-profile qualification.

**Tech Stack:** Windows PowerShell 5.1, C# DXGI COM declarations through Add-Type, Python3.12 unittest/subprocess.

## Global Constraints

- Work only in `C:\Projects\strix-alloy-research\integration`, commit only owned paths.
- No model/GPU device/context/workload, WSL, driver/security/service/BIOS/persistent environment changes. DXGI factory enumeration and performance counter queries are read-only.
- Missing/failed/stale readings reject the start. Keep counter provider, scope, adapter LUID and timestamps.
- An external helper's QueryVideoMemoryInfo budget/current usage is per helper, not adapter global; never use it here.
- Do not double-count UMA dedicated and shared as independent physical banks, or equate TotalCommitted to DedicatedUsage+SharedUsage.
- No real memory profile or measured margin is qualified by this collector.

### Task 1: Scoped live snapshot with fixture tests and one real read-only qualification

**Files:**
- Create `scripts/gufo_control/windows_probe.ps1`: read-only single snapshot; no loop/server/process launch.
- Create `scripts/gufo_control/telemetry.py`: pure normalization plus bounded probe invocation.
- Create `tests/gufo/test_telemetry.py`: synthetic complete snapshots exercising acceptance/rejection; small Windows collection test may be explicit/manual rather than every unit run.

**Interfaces:**
- `normalize_snapshot(raw: dict, *, captured_monotonic: float, now_monotonic: float, now_utc: datetime) -> dict`; raises `TelemetryError(ValueError)` on unavailable/ambiguous/stale/malformed data.
- `collect_snapshot() -> dict`; Windows x64 only, calls the checked-in probe with the built-in absolute Windows PowerShell path, no shell, hidden window, five-second subprocess timeout, UTF-8 JSON. Include the raw probe in the result as `raw` for private evidence. No public telemetry upload.
- Returned fields include the existing admission sample keys: available_physical_bytes, commit_headroom_bytes, dedicated_capacity_bytes, adapter_dedicated_bytes, adapter_shared_bytes, adapter_luid, captured_monotonic, gpu_scope=adapter_aggregate, host_scope=host_global, provider, telemetry_ok=True, other_inference_pids. Also retain adapter_total_committed_bytes, host_committed_bytes, host_commit_limit_bytes, sample UTC range, adapter description/PCI IDs and raw observation.
- Known-process inventory covers exact case-insensitive names `gufo`, `llama-server`, `llama-cli`, `ollama`, `ollama_llama_server`, `vmmem`, `vmmemwsl`, `wslhost`, `com.docker.backend`, `docker desktop`, `lm studio`. Label inventory_scope=`known_engine_and_guest_names`; it is not proof no arbitrary renamed inference program exists. Do not query command lines or kill anything. Caller will later exclude/verify its owned PID under separate lifecycle rules; this function does not claim PID ownership.
- This first collector covers host-global and adapter aggregate only. Per-owned-process GPU counters and reclamation checks are subsequent guardian work; do not mislabel this as the entire monitor.

- [ ] **Step 1: Write fixture tests and run RED.** Starting test fixture below uses raw PowerShell output shape. Add failing tests for wrong/multiple adapter identity, software adapter, duplicate/missing/wrong-node counters, stale/future/unhealthy readings, overflow/negative/bool values, contradictory commit, bad process inventory and inconsistent raw/cooked values before implementing corresponding checks.

```python
import copy
from datetime import datetime, timezone
import unittest
from gufo_control.telemetry import TelemetryError, normalize_snapshot

G = 1 << 30
NOW = datetime(2026, 9, 26, 12, 0, 1, tzinfo=timezone.utc)
STAMP = '2026-09-26T12:00:00Z'
LUID = '0x00000000_0x000111c1'
INSTANCE = 'luid_' + LUID + '_phys_0'

def fixture():
    rows = []
    for label, value in [('available bytes', 53*G), ('committed bytes', 15*G), ('commit limit', 224*G)]:
        rows.append(dict(path='\\\\host\\memory\\'+label, instance=None, raw_value=value,
                         cooked_value=value, status=0, timestamp_utc=STAMP))
    for label, value in [('dedicated usage', G), ('shared usage', G//4), ('total committed', 2*G)]:
        rows.append(dict(path='\\\\host\\gpu adapter memory('+INSTANCE+')\\'+label,
                         instance=INSTANCE, raw_value=value, cooked_value=value,
                         status=0, timestamp_utc=STAMP))
    return dict(schema=1, provider='PDH/Get-Counter;DXGI/EnumAdapters1',
                adapters=[dict(luid=LUID, vendor_id=0x1002, device_id=0x1586,
                               subsystem_id=0x801d2014, flags=0, description='AMD Radeon(TM) 8060S Graphics',
                               dedicated_video_memory=64*G)], counters=rows, processes=[])

class TelemetryTests(unittest.TestCase):
    def normalize(self, raw):
        return normalize_snapshot(raw, captured_monotonic=100., now_monotonic=101., now_utc=NOW)
    def test_exact_scopes_and_independent_committed_value(self):
        result = self.normalize(fixture())
        self.assertEqual(result['adapter_luid'], LUID)
        self.assertEqual(result['gpu_scope'], 'adapter_aggregate')
        self.assertEqual(result['host_scope'], 'host_global')
        self.assertEqual(result['available_physical_bytes'], 53*G)
        self.assertEqual(result['commit_headroom_bytes'], 209*G)
        self.assertEqual(result['adapter_total_committed_bytes'], 2*G)
        self.assertNotEqual(result['adapter_total_committed_bytes'], result['adapter_dedicated_bytes'] + result['adapter_shared_bytes'])
    def test_other_adapter_is_not_summed(self):
        raw = fixture()
        for row in list(raw['counters'][3:]):
            row = dict(row)
            row['path'] = row['path'].replace('0x000111c1', '0x00014fe1')
            row['instance'] = row['instance'].replace('0x000111c1', '0x00014fe1')
            row['raw_value'] = row['cooked_value'] = 10*G
            raw['counters'].append(row)
        self.assertEqual(self.normalize(raw)['adapter_dedicated_bytes'], G)
    def test_failed_counter_not_zero(self):
        raw = fixture(); raw['counters'][3]['status'] = 0xc0000bc6
        with self.assertRaises(TelemetryError): self.normalize(raw)
    def test_known_guest_inventory(self):
        raw = fixture(); raw['processes'] = [dict(pid=123, name='vmmemWSL'), dict(pid=456,name='notepad')]
        self.assertEqual(self.normalize(raw)['other_inference_pids'], [123])
```

Run Python with PYTHONPATH=scripts and `-m unittest discover -s tests/gufo -p test_telemetry.py -v`; initial missing module then a nonvalidating stub must fail the scope/rejection assertions.

- [ ] **Step 2: Implement the PowerShell probe.** Start with this complete read-only emitter. Use the API report at `C:\Projects\strix-alloy-research\reports\gufo-scoped-telemetry-20260926.md` as source evidence; the generic delegate form there is replaced below for Windows PowerShell5.1 C# compiler compatibility. Do not loosen errors or substitute CIM data without timestamps/status.

```powershell
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$source = @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class GufoDxgiProbe {
  [StructLayout(LayoutKind.Sequential)] public struct Luid { public uint LowPart; public int HighPart; }
  [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] public struct Desc {
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst=128)] public string Description;
    public uint VendorId, DeviceId, SubSysId, Revision;
    public UIntPtr DedicatedVideoMemory, DedicatedSystemMemory, SharedSystemMemory;
    public Luid AdapterLuid; public uint Flags;
  }
  public class Adapter {
    public string luid, description;
    public uint vendor_id, device_id, subsystem_id, flags;
    public ulong dedicated_video_memory;
  }
  [DllImport("dxgi.dll", ExactSpelling=true)] static extern int CreateDXGIFactory1(ref Guid iid, out IntPtr factory);
  [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int EnumFn(IntPtr self, uint index, out IntPtr adapter);
  [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int DescFn(IntPtr self, out Desc desc);
  static IntPtr Slot(IntPtr obj, int index) { return Marshal.ReadIntPtr(Marshal.ReadIntPtr(obj), index * IntPtr.Size); }
  public static Adapter[] Enumerate() {
    if(IntPtr.Size != 8) throw new InvalidOperationException("x64 required");
    Guid iid=new Guid("770aae78-f26f-4dba-a829-253c83d1b387"); IntPtr factory;
    int hr=CreateDXGIFactory1(ref iid,out factory); if(hr<0) Marshal.ThrowExceptionForHR(hr);
    var items=new List<Adapter>(); bool ended=false;
    try {
      var next=(EnumFn)Marshal.GetDelegateForFunctionPointer(Slot(factory,12),typeof(EnumFn));
      for(uint i=0;i<32;i++) {
        IntPtr adapter; hr=next(factory,i,out adapter);
        if(hr==unchecked((int)0x887A0002)) { ended=true; break; }
        if(hr<0) Marshal.ThrowExceptionForHR(hr);
        try {
          Desc desc; hr=((DescFn)Marshal.GetDelegateForFunctionPointer(Slot(adapter,10),typeof(DescFn)))(adapter,out desc);
          if(hr<0) Marshal.ThrowExceptionForHR(hr);
          items.Add(new Adapter { luid=String.Format("0x{0:x8}_0x{1:x8}",(uint)desc.AdapterLuid.HighPart,desc.AdapterLuid.LowPart),
            description=desc.Description, vendor_id=desc.VendorId, device_id=desc.DeviceId,
            subsystem_id=desc.SubSysId, flags=desc.Flags, dedicated_video_memory=desc.DedicatedVideoMemory.ToUInt64() });
        } finally { Marshal.Release(adapter); }
      }
      if(!ended) throw new InvalidOperationException("adapter enumeration limit exceeded");
    } finally { Marshal.Release(factory); }
    return items.ToArray();
  }
}
'@
Add-Type -TypeDefinition $source
$adapters = @([GufoDxgiProbe]::Enumerate())
$paths = @('\Memory\Available Bytes','\Memory\Committed Bytes','\Memory\Commit Limit',
  '\GPU Adapter Memory(*)\Dedicated Usage','\GPU Adapter Memory(*)\Shared Usage','\GPU Adapter Memory(*)\Total Committed')
$samples = Get-Counter -Counter $paths -MaxSamples 1 -ErrorAction Stop
$rows = @($samples.CounterSamples | ForEach-Object {
  [pscustomobject]@{ path=$_.Path; instance=$_.InstanceName; raw_value=$_.RawValue;
    cooked_value=$_.CookedValue; status=$_.Status; timestamp_utc=$_.Timestamp.ToUniversalTime().ToString('o') }
})
$processes = @(Get-Process -ErrorAction Stop | ForEach-Object {
  [pscustomobject]@{ pid=$_.Id; name=$_.ProcessName }
})
[pscustomobject]@{ schema=1; provider='PDH/Get-Counter;DXGI/EnumAdapters1';
  adapters=$adapters; counters=$rows; processes=$processes } | ConvertTo-Json -Depth 6 -Compress
```

- [ ] **Step 3: Implement normalization and invocation.** Complete starting normalization logic below; add the explicit schema/type/bounds failures described afterwards before calling it qualified. Reject malformed input with TelemetryError, never TypeError/KeyError leaking by accident.

```python
import copy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
from .admission import MAX_BYTES, MAX_SAMPLE_AGE_SECONDS

class TelemetryError(ValueError): pass

PROVIDER = 'PDH/Get-Counter;DXGI/EnumAdapters1'
KNOWN = {'gufo','llama-server','llama-cli','ollama','ollama_llama_server','vmmem',
         'vmmemwsl','wslhost','com.docker.backend','docker desktop','lm studio'}
HOST = {'available bytes':'available_physical_bytes', 'committed bytes':'host_committed_bytes',
        'commit limit':'host_commit_limit_bytes'}
GPU = {'dedicated usage':'adapter_dedicated_bytes','shared usage':'adapter_shared_bytes',
       'total committed':'adapter_total_committed_bytes'}

def integer(value, label, maximum=MAX_BYTES):
    if type(value) is not int or not 0 <= value <= maximum:
        raise TelemetryError('invalid integer: '+label)
    return value

def normalize_snapshot(raw, *, captured_monotonic, now_monotonic, now_utc):
    for stamp in (captured_monotonic, now_monotonic):
        if type(stamp) not in (int,float) or not math.isfinite(stamp) or stamp < 0:
            raise TelemetryError('invalid monotonic timestamp')
    if not 0 <= now_monotonic-captured_monotonic <= MAX_SAMPLE_AGE_SECONDS:
        raise TelemetryError('stale collection')
    if not isinstance(now_utc,datetime) or now_utc.utcoffset() is None:
        raise TelemetryError('timezone-aware UTC reference required')
    if not isinstance(raw,dict) or raw.get('schema') != 1 or raw.get('provider') != PROVIDER:
        raise TelemetryError('unknown telemetry provider/schema')
    for key in ('adapters','counters','processes'):
        if not isinstance(raw.get(key),list) or len(raw[key]) > 10000:
            raise TelemetryError('missing or excessive '+key)
    adapters=[a for a in raw['adapters'] if isinstance(a,dict) and a.get('vendor_id') == 0x1002 and a.get('device_id') == 0x1586 and a.get('flags') == 0]
    if len(adapters) != 1: raise TelemetryError('expected exactly one Radeon8060S adapter')
    adapter=adapters[0]; luid=adapter.get('luid')
    if not isinstance(luid,str) or not re.fullmatch(r'0x[0-9a-fA-F]{8}_0x[0-9a-fA-F]{8}',luid):
        raise TelemetryError('invalid adapter LUID')
    luid=luid.lower(); instance='luid_'+luid+'_phys_0'
    result={'adapter_luid':luid, 'adapter_identity':copy.deepcopy(adapter),
            'dedicated_capacity_bytes':integer(adapter.get('dedicated_video_memory'),'dedicated capacity'),
            'captured_monotonic':captured_monotonic,'provider':PROVIDER,
            'gpu_scope':'adapter_aggregate','host_scope':'host_global',
            'inventory_scope':'known_engine_and_guest_names'}
    stamps=[]
    for row in raw['counters']:
        if not isinstance(row,dict) or not isinstance(row.get('path'),str):
            raise TelemetryError('malformed counter row')
        path=row['path'].lower(); key=None
        for suffix,target in HOST.items():
            if re.fullmatch(r'\\\\[^\\]+\\memory\\'+re.escape(suffix),path): key=target
        match=re.fullmatch(r'\\\\[^\\]+\\gpu adapter memory\((luid_0x[0-9a-f]{8}_0x[0-9a-f]{8}_phys_[0-9]+)\)\\(.+)',path)
        if match:
            if not isinstance(row.get('instance'),str) or row['instance'].lower()!=match[1]:
                raise TelemetryError('counter instance/path disagree')
            if match[1].startswith('luid_'+luid+'_phys_'):
                if match[1]!=instance: raise TelemetryError('unsupported physical-node topology')
                key=GPU.get(match[2])
        if key is None: continue
        if key in result: raise TelemetryError('duplicate counter: '+key)
        status=integer(row.get('status'),'counter status',0xffffffff)
        if status not in (0,1): raise TelemetryError('unhealthy counter: '+key)
        value=integer(row.get('raw_value'),key)
        cooked=row.get('cooked_value')
        if type(cooked) not in (int,float) or not math.isfinite(cooked) or cooked!=value:
            raise TelemetryError('inconsistent raw/cooked bytes: '+key)
        try:
            stamp=datetime.fromisoformat(row['timestamp_utc'].replace('Z','+00:00'))
            if stamp.utcoffset() is None or not 0 <= (now_utc-stamp).total_seconds() <= MAX_SAMPLE_AGE_SECONDS:
                raise ValueError('stale/future counter')
        except (KeyError,TypeError,ValueError,AttributeError) as error:
            raise TelemetryError('invalid counter timestamp') from error
        stamps.append(stamp.isoformat()); result[key]=value
    if any(k not in result for k in (*HOST.values(),*GPU.values())):
        raise TelemetryError('required counter missing')
    if result['host_committed_bytes']>result['host_commit_limit_bytes'] or result['dedicated_capacity_bytes']==0 or result['adapter_dedicated_bytes']>result['dedicated_capacity_bytes']:
        raise TelemetryError('inconsistent memory counters')
    pids=[]; seen=set()
    for proc in raw['processes']:
        if not isinstance(proc,dict) or not isinstance(proc.get('name'),str) or not proc['name'].strip():
            raise TelemetryError('malformed process inventory')
        pid=integer(proc.get('pid'),'PID',0xffffffff)
        if pid in seen: raise TelemetryError('duplicate process PID')
        seen.add(pid)
        if proc['name'].casefold() in KNOWN:
            if pid==0: raise TelemetryError('invalid inference PID')
            pids.append(pid)
    result.update(telemetry_ok=True, other_inference_pids=sorted(pids),
        commit_headroom_bytes=result['host_commit_limit_bytes']-result['host_committed_bytes'],
        sample_utc_min=min(stamps), sample_utc_max=max(stamps), raw=copy.deepcopy(raw))
    return result

def collect_snapshot():
    if os.name!='nt': raise TelemetryError('Windows required')
    executable=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    script=Path(__file__).with_name('windows_probe.ps1').resolve(strict=True)
    started=time.monotonic()
    try:
        completed=subprocess.run([str(executable),'-NoProfile','-NonInteractive','-File',str(script)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
        if completed.returncode or not completed.stdout or len(completed.stdout)>2*1024*1024:
            raise TelemetryError('probe failed or output exceeds limit')
        raw=json.loads(completed.stdout.decode('utf-8-sig'))
    except (OSError,subprocess.TimeoutExpired,ValueError) as error:
        raise TelemetryError('Windows telemetry unavailable: '+str(error)) from error
    return normalize_snapshot(raw,captured_monotonic=started,now_monotonic=time.monotonic(),now_utc=datetime.now(timezone.utc))
```

Strengthen the starting implementation's validation: schema1 must be an int, adapter fields must have strict integer types and bounded PCI/flag values, descriptions nonblank, all list entries structurally valid (not silently discarded), relevant path namespace malformed/unknown counters rejected, counters collection bounded, huge numeric values must not escape as OverflowError from math.isfinite, and host rows cannot falsely carry GPU instance identity. Preserve raw/cooked/timestamp precision semantics. Do not impose TotalCommitted==Dedicated+Shared. Document that English counter paths are required by this initial probe and an unsupported/localized provider fails closed, never guesses.

- [ ] **Step 4: GREEN fixture suite and bounded invocation failures.** Extend tests with finite/huge monotonic inputs, timezone-naive dates, wrong scopes/provider strings, duplicate/reordered counter rows, raw input immutability and known/unknown process names. For collect_snapshot, mock only the process boundary for timeout, invalid JSON/UTF8, nonzero exit and over-limit output; actual normalization must run. Do not execute external models in tests. Verify Windows PowerShell AST parse and a single real collect_snapshot() succeeds on this host within5seconds. If it fails, preserve failure, investigate exact provider/timing/ABI cause and do not raise the freshness window or silently weaken identity. Real collection returns no ownership or admission decision.

- [ ] **Step 5: Run full offline suite once and commit owned files.**

```powershell
$env:PYTHONPATH = Join-Path $PWD 'scripts'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p test_telemetry.py -v
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p 'test_*.py' -v
git diff --check
git add -- scripts/gufo_control/windows_probe.ps1 scripts/gufo_control/telemetry.py tests/gufo/test_telemetry.py
git commit -m 'feat: collect scoped Windows host and adapter memory telemetry'
```

Report RED/GREEN commands/counts, live collection duration, mapped hardware/LUID and numeric counters only, counter status/timestamps, tested PowerShell version, known limitations and any warnings. No process command-line or environment dumps. Full report belongs beside the task brief, not in the public README.
