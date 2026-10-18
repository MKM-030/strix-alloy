using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text;
using System.Web.Script.Serialization;

// Same DXGI and PDH collectors as windows_probe.ps1, without a PowerShell
// startup and two C# source compilations on every telemetry sample.
public static class GufoProbeMain {
  public static int Main(string[] args) {
    try {
      uint ownedPid = 0;
      if (args.Length != 0 && (args.Length != 2 || args[0] != "--owned-pid"
          || !UInt32.TryParse(args[1], out ownedPid) || ownedPid == 0))
        throw new ArgumentException("invalid probe arguments");
      var adapters = GufoDxgiProbe.Enumerate();
      var rows = GufoPdhCollector.Collect(new GufoNativePdhApi());
      object owned = new { available = false, reason = "not_requested" };
      if (ownedPid != 0) {
        try {
          owned = new { available = true,
            counters = GufoPdhCollector.CollectProcess(new GufoNativePdhApi()) };
        } catch {
          owned = new { available = false, reason = "process_counters_unavailable" };
        }
      }
      var processes = new List<object>();
      var observed = Process.GetProcesses();
      try {
        if (observed.Length > 10000) throw new InvalidOperationException("inventory bound");
        foreach (var process in observed)
          processes.Add(new { pid = process.Id, name = process.ProcessName });
      } finally {
        foreach (var process in observed) process.Dispose();
      }
      var serializer = new JavaScriptSerializer { MaxJsonLength = 2 * 1024 * 1024,
        RecursionLimit = 16 };
      string json = serializer.Serialize(new { schema = 1,
        provider = "PDH/native-gauges;DXGI/EnumAdapters1",
        adapters = adapters, counters = rows, processes = processes, owned = owned });
      if (Encoding.UTF8.GetByteCount(json) > 2 * 1024 * 1024)
        throw new InvalidOperationException("output bound");
      Console.OutputEncoding = new UTF8Encoding(false);
      Console.WriteLine(json);
      return 0;
    } catch (Exception error) {
      Console.Error.WriteLine("native_probe_failed:" + error.GetType().Name);
      return 2;
    }
  }
}
