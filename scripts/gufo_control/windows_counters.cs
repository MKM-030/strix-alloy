using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

[StructLayout(LayoutKind.Sequential)]
public struct GufoFileTime { public uint Low, High; }

[StructLayout(LayoutKind.Sequential)]
public struct GufoPdhRawCounter {
  public uint CStatus;
  public GufoFileTime TimeStamp;
  public long FirstValue, SecondValue;
  public uint MultiCount;
}

[StructLayout(LayoutKind.Sequential)]
public struct GufoPdhRawItem { public IntPtr Name; public GufoPdhRawCounter Value; }

[StructLayout(LayoutKind.Sequential)]
public struct GufoPdhFormattedValue { public uint CStatus; public long LargeValue; }

[StructLayout(LayoutKind.Sequential)]
public struct GufoPdhFormattedItem { public IntPtr Name; public GufoPdhFormattedValue Value; }

public sealed class GufoPdhObservation {
  public string Path, Instance;
  public uint Type, Status, FormattedStatus;
  public long RawValue, CookedValue;
  public ulong LocalFileTime;
}

public sealed class GufoPdhRow {
  public string path, instance, timestamp_utc;
  public long raw_value, cooked_value;
  public uint status;
}

public interface IGufoPdhApi {
  int Open(out IntPtr query);
  int Add(IntPtr query, string path, out IntPtr counter);
  int Collect(IntPtr query);
  GufoPdhObservation[] Read(IntPtr counter, string path, bool wildcard);
  int Close(IntPtr query);
}

public static class GufoPdhCollector {
  public const uint RawCount=65536, LargeRawCount=65792;
  public static readonly string[] Paths={
    @"\Memory\Available Bytes", @"\Memory\Committed Bytes", @"\Memory\Commit Limit",
    @"\GPU Adapter Memory(*)\Dedicated Usage", @"\GPU Adapter Memory(*)\Shared Usage",
    @"\GPU Adapter Memory(*)\Total Committed" };

  [DllImport("kernel32.dll", SetLastError=true)]
  static extern bool LocalFileTimeToFileTime(ref GufoFileTime local, out GufoFileTime utc);

  public static string FileTimeUtc(ulong localValue) {
    if(localValue==0) throw new InvalidOperationException("missing PDH timestamp");
    var local=new GufoFileTime { Low=(uint)localValue, High=(uint)(localValue>>32) };
    GufoFileTime utc;
    if(!LocalFileTimeToFileTime(ref local,out utc)) throw new InvalidOperationException("PDH timestamp conversion failed");
    ulong ticks=((ulong)utc.High<<32)|utc.Low;
    return DateTime.FromFileTimeUtc(checked((long)ticks)).ToString("o");
  }

  public static GufoPdhRow Validate(GufoPdhObservation o) {
    if(o==null || String.IsNullOrWhiteSpace(o.Path) || (o.Type!=RawCount && o.Type!=LargeRawCount)
       || (o.Status!=0 && o.Status!=1) || (o.FormattedStatus!=0 && o.FormattedStatus!=1)
       || o.RawValue<0 || o.CookedValue<0 || o.RawValue!=o.CookedValue)
      throw new InvalidOperationException("invalid PDH byte gauge");
    return new GufoPdhRow { path=o.Path, instance=o.Instance, raw_value=o.RawValue,
      cooked_value=o.CookedValue, status=o.Status, timestamp_utc=FileTimeUtc(o.LocalFileTime) };
  }

  public static GufoPdhRow[] Collect(IGufoPdhApi api) {
    if(IntPtr.Size!=8) throw new InvalidOperationException("x64 required");
    if(Marshal.SizeOf(typeof(GufoPdhRawCounter))!=40 ||
       Marshal.OffsetOf(typeof(GufoPdhRawCounter),"FirstValue").ToInt32()!=16 ||
       Marshal.SizeOf(typeof(GufoPdhRawItem))!=48 ||
       Marshal.SizeOf(typeof(GufoPdhFormattedItem))!=24)
      throw new InvalidOperationException("PDH layout mismatch");
    IntPtr query=IntPtr.Zero;
    Check(api.Open(out query),"open");
    if(query==IntPtr.Zero) throw new InvalidOperationException("null PDH query");
    try {
      var counters=new IntPtr[Paths.Length];
      for(int i=0;i<Paths.Length;i++) Check(api.Add(query,Paths[i],out counters[i]),"add");
      Check(api.Collect(query),"collect");
      var rows=new List<GufoPdhRow>();
      for(int i=0;i<Paths.Length;i++) {
        GufoPdhObservation[] values=api.Read(counters[i],Paths[i],i>=3);
        if(values==null || values.Length==0 || values.Length>1024 || (i<3 && values.Length!=1))
          throw new InvalidOperationException("missing or excessive PDH instances");
        foreach(var value in values) rows.Add(Validate(value));
      }
      return rows.ToArray();
    } finally { Check(api.Close(query),"close"); }
  }

  public static void Check(int status,string action) {
    if(status!=0) throw new InvalidOperationException("PDH "+action+" failed: 0x"+status.ToString("x8"));
  }
}

public sealed class GufoNativePdhApi : IGufoPdhApi {
  const uint MoreData=0x800007d2, FormatLarge=0x400, NoScale=0x1000;
  const int MaxBuffer=262144, MaxItems=1024;
  [DllImport("pdh.dll", CharSet=CharSet.Unicode, EntryPoint="PdhOpenQueryW")]
  static extern int OpenNative(string dataSource, IntPtr userData, out IntPtr query);
  [DllImport("pdh.dll", CharSet=CharSet.Unicode, EntryPoint="PdhAddEnglishCounterW")]
  static extern int AddNative(IntPtr query, string path, IntPtr userData, out IntPtr counter);
  [DllImport("pdh.dll", EntryPoint="PdhCollectQueryData")]
  static extern int CollectNative(IntPtr query);
  [DllImport("pdh.dll", EntryPoint="PdhCloseQuery")]
  static extern int CloseNative(IntPtr query);
  [DllImport("pdh.dll", EntryPoint="PdhGetRawCounterValue")]
  static extern int RawNative(IntPtr counter,out uint type,out GufoPdhRawCounter value);
  [DllImport("pdh.dll", EntryPoint="PdhGetFormattedCounterValue")]
  static extern int FormattedNative(IntPtr counter,uint format,out uint type,out GufoPdhFormattedValue value);
  [DllImport("pdh.dll", EntryPoint="PdhGetRawCounterArrayW")]
  static extern int RawArrayNative(IntPtr counter,ref uint bytes,out uint items,IntPtr buffer);
  [DllImport("pdh.dll", EntryPoint="PdhGetFormattedCounterArrayW")]
  static extern int FormattedArrayNative(IntPtr counter,uint format,ref uint bytes,out uint items,IntPtr buffer);
  [DllImport("pdh.dll", EntryPoint="PdhGetCounterInfoW")]
  static extern int InfoNative(IntPtr counter,bool explain,ref uint bytes,IntPtr buffer);

  public int Open(out IntPtr query) { return OpenNative(null,IntPtr.Zero,out query); }
  public int Add(IntPtr query,string path,out IntPtr counter) { return AddNative(query,path,IntPtr.Zero,out counter); }
  public int Collect(IntPtr query) { return CollectNative(query); }
  public int Close(IntPtr query) { return CloseNative(query); }

  static uint TypeOf(IntPtr counter) {
    uint bytes=0;
    int status=InfoNative(counter,false,ref bytes,IntPtr.Zero);
    if((uint)status!=MoreData || bytes<8 || bytes>MaxBuffer)
      throw new InvalidOperationException("invalid PDH counter metadata size");
    IntPtr buffer=Marshal.AllocHGlobal((int)bytes);
    try {
      GufoPdhCollector.Check(InfoNative(counter,false,ref bytes,buffer),"counter info");
      return unchecked((uint)Marshal.ReadInt32(buffer,4));
    } finally { Marshal.FreeHGlobal(buffer); }
  }

  static ulong Timestamp(GufoFileTime time) { return ((ulong)time.High<<32)|time.Low; }
  static string MachinePath(string path) { return @"\\"+Environment.MachineName+path; }

  public GufoPdhObservation[] Read(IntPtr counter,string path,bool wildcard) {
    uint type=TypeOf(counter);
    if(type!=GufoPdhCollector.RawCount && type!=GufoPdhCollector.LargeRawCount)
      throw new InvalidOperationException("PDH counter is not a byte gauge");
    if(!wildcard) {
      uint rawType,formattedType;
      GufoPdhRawCounter raw; GufoPdhFormattedValue fmt;
      GufoPdhCollector.Check(RawNative(counter,out rawType,out raw),"raw value");
      GufoPdhCollector.Check(FormattedNative(counter,FormatLarge|NoScale,out formattedType,out fmt),"formatted value");
      if(rawType!=type || formattedType!=type) throw new InvalidOperationException("PDH type changed");
      return new [] { new GufoPdhObservation { Path=MachinePath(path), Instance=null,
        Type=type, Status=raw.CStatus, FormattedStatus=fmt.CStatus,
        RawValue=raw.FirstValue, CookedValue=fmt.LargeValue, LocalFileTime=Timestamp(raw.TimeStamp) } };
    }
    var rawItems=GetRawArray(counter);
    var fmtItems=GetFormattedArray(counter);
    if(rawItems.Count!=fmtItems.Count) throw new InvalidOperationException("PDH instance mismatch");
    var result=new List<GufoPdhObservation>();
    foreach(var pair in rawItems) {
      GufoPdhFormattedValue fmt;
      if(!fmtItems.TryGetValue(pair.Key,out fmt)) throw new InvalidOperationException("PDH instance mismatch");
      var raw=pair.Value;
      result.Add(new GufoPdhObservation { Path=MachinePath(path.Replace("(*)","("+pair.Key+")")),
        Instance=pair.Key, Type=type, Status=raw.CStatus, FormattedStatus=fmt.CStatus,
        RawValue=raw.FirstValue, CookedValue=fmt.LargeValue, LocalFileTime=Timestamp(raw.TimeStamp) });
    }
    return result.ToArray();
  }

  static int BoundedSize(uint bytes,uint items) {
    if(bytes==0 || bytes>MaxBuffer || items==0 || items>MaxItems)
      throw new InvalidOperationException("PDH instance array bound exceeded");
    return (int)bytes;
  }

  static Dictionary<string,GufoPdhRawCounter> GetRawArray(IntPtr counter) {
    uint bytes=0,items;
    if((uint)RawArrayNative(counter,ref bytes,out items,IntPtr.Zero)!=MoreData)
      throw new InvalidOperationException("PDH raw sizing failed");
    IntPtr buffer=Marshal.AllocHGlobal(BoundedSize(bytes,items));
    try {
      GufoPdhCollector.Check(RawArrayNative(counter,ref bytes,out items,buffer),"raw array");
      BoundedSize(bytes,items);
      var result=new Dictionary<string,GufoPdhRawCounter>(StringComparer.OrdinalIgnoreCase);
      int size=Marshal.SizeOf(typeof(GufoPdhRawItem));
      if((ulong)items*(ulong)size>(ulong)bytes) throw new InvalidOperationException("PDH raw array truncated");
      for(int i=0;i<items;i++) {
        var item=(GufoPdhRawItem)Marshal.PtrToStructure(IntPtr.Add(buffer,i*size),typeof(GufoPdhRawItem));
        string name=Marshal.PtrToStringUni(item.Name);
        if(String.IsNullOrWhiteSpace(name) || result.ContainsKey(name))
          throw new InvalidOperationException("duplicate PDH instance");
        result.Add(name,item.Value);
      }
      return result;
    } finally { Marshal.FreeHGlobal(buffer); }
  }

  static Dictionary<string,GufoPdhFormattedValue> GetFormattedArray(IntPtr counter) {
    uint bytes=0,items;
    if((uint)FormattedArrayNative(counter,FormatLarge|NoScale,ref bytes,out items,IntPtr.Zero)!=MoreData)
      throw new InvalidOperationException("PDH formatted sizing failed");
    IntPtr buffer=Marshal.AllocHGlobal(BoundedSize(bytes,items));
    try {
      GufoPdhCollector.Check(FormattedArrayNative(counter,FormatLarge|NoScale,ref bytes,out items,buffer),"formatted array");
      BoundedSize(bytes,items);
      var result=new Dictionary<string,GufoPdhFormattedValue>(StringComparer.OrdinalIgnoreCase);
      int size=Marshal.SizeOf(typeof(GufoPdhFormattedItem));
      if((ulong)items*(ulong)size>(ulong)bytes) throw new InvalidOperationException("PDH formatted array truncated");
      for(int i=0;i<items;i++) {
        var item=(GufoPdhFormattedItem)Marshal.PtrToStructure(IntPtr.Add(buffer,i*size),typeof(GufoPdhFormattedItem));
        string name=Marshal.PtrToStringUni(item.Name);
        if(String.IsNullOrWhiteSpace(name) || result.ContainsKey(name))
          throw new InvalidOperationException("duplicate PDH instance");
        result.Add(name,item.Value);
      }
      return result;
    } finally { Marshal.FreeHGlobal(buffer); }
  }
}
