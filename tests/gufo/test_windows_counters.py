"""Execute the native counter validator with an injectable PDH source on Windows."""
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import unittest


SOURCE = Path(__file__).resolve().parents[2] / "scripts/gufo_control/windows_counters.cs"
HARNESS = r'''
public sealed class GufoFakePdh : IGufoPdhApi {
  public int closes, collects;
  public int mode;
  public int Open(out System.IntPtr query) { query=new System.IntPtr(17); return 0; }
  public int Add(System.IntPtr query, string path, out System.IntPtr counter) { counter=new System.IntPtr(23); return mode==7 ? 5 : 0; }
  public int Collect(System.IntPtr query) { collects++; return 0; }
  public GufoPdhObservation[] Read(System.IntPtr counter, string path, bool wildcard) {
    return new [] { new GufoPdhObservation { Path="\\\\host"+path.Replace("(*)", "(luid_0x00000000_0x000111c1_phys_0)"),
      Instance=wildcard ? "luid_0x00000000_0x000111c1_phys_0" : null,
      Type=mode==2 ? 0x10410400U : 65792U,
      Status=mode==1 ? 0xc0000bc6U : mode==6 ? 1U : 0U,
      FormattedStatus=mode==3 ? 0xc0000bc6U : mode==6 ? 1U : 0U,
      RawValue=mode==4 ? -1 : 123, CookedValue=mode==5 ? 124 : 123,
      LocalFileTime=mode==8 ? 0UL :
        (ulong)System.DateTime.SpecifyKind(System.DateTime.Now,System.DateTimeKind.Utc).ToFileTimeUtc() } };
  }
  public int Close(System.IntPtr query) { closes++; return 0; }
}
public static class GufoNativeHarness {
  public static object Run() {
    var api=new GufoFakePdh();
    var rows=GufoPdhCollector.Collect(api);
    int rejected=0;
    foreach(int mode in new [] {1,2,3,4,5,7,8}) {
      api.mode=mode;
      try { GufoPdhCollector.Collect(api); } catch(System.InvalidOperationException) { rejected++; }
    }
    api.mode=6;
    var newData=GufoPdhCollector.Collect(api);
    var badType=new GufoPdhObservation { Path="x", Type=0x10410400, Status=0,
      FormattedStatus=0, RawValue=1, CookedValue=1, LocalFileTime=0 };
    bool rateRejected=false;
    try { GufoPdhCollector.Validate(badType); } catch(System.InvalidOperationException) { rateRejected=true; }
    return new { rowCount=rows.Length, closes=api.closes, collects=api.collects,
      rejected=rejected, rateRejected=rateRejected, newDataStatus=newData[0].status,
      timestampUtc=rows[0].timestamp_utc,
      rawSize=System.Runtime.InteropServices.Marshal.SizeOf(typeof(GufoPdhRawCounter)),
      rawFirst=System.Runtime.InteropServices.Marshal.OffsetOf(typeof(GufoPdhRawCounter), "FirstValue").ToInt32(),
      rawItemSize=System.Runtime.InteropServices.Marshal.SizeOf(typeof(GufoPdhRawItem)),
      formattedItemSize=System.Runtime.InteropServices.Marshal.SizeOf(typeof(GufoPdhFormattedItem)) };
  }
}
'''


@unittest.skipUnless(os.name == "nt", "native PDH harness requires Windows")
class NativeCounterTests(unittest.TestCase):
    def test_validation_layout_and_query_release(self):
        command = (
            "$ErrorActionPreference='Stop'; "
            "$source=Get-Content -LiteralPath '" + str(SOURCE).replace("'", "''") + "' -Raw; "
            "Add-Type -TypeDefinition ($source + @'\n" + HARNESS + "\n'@); "
            "[GufoNativeHarness]::Run() | ConvertTo-Json -Compress"
        )
        encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
        run = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result["rowCount"], 6)
        self.assertEqual(result["closes"], 9)
        self.assertEqual(result["collects"], 8)
        self.assertEqual(result["rejected"], 7)
        self.assertTrue(result["rateRejected"])
        self.assertEqual(result["newDataStatus"], 1)
        self.assertLess(abs((datetime.fromisoformat(result["timestampUtc"].replace("Z", "+00:00")) -
                             datetime.now(timezone.utc)).total_seconds()), 5)
        self.assertEqual((result["rawSize"], result["rawFirst"]), (40, 16))
        self.assertEqual((result["rawItemSize"], result["formattedItemSize"]), (48, 24))
