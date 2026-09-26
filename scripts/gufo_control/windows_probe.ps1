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
