"""Inventory Halogen binary seams relevant to an external NPU draft bridge."""
import argparse, json, subprocess
P=argparse.ArgumentParser(); P.add_argument("--binary-linux",required=True)
P.add_argument("--out",required=True); a=P.parse_args()
p=subprocess.run(["wsl.exe","-d","Ubuntu-24.04","--","strings","-a",a.binary_linux],
                 capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=180)
if p.returncode: raise SystemExit(p.stderr)
text=p.stdout
caps={
 "legacy_drafter_taps":"--drafter-taps" in text,
 "legacy_drafter_hidden":"--drafter-hidden" in text,
 "legacy_drafter_ingest_bench":"--drafter-ingest-bench" in text,
 "legacy_drafter_round_bench":"--drafter-round-bench" in text,
 "current_tap_from_scan":"HALOGEN_TAP_FROM_SCAN" in text,
 "current_mtp_prefill":"HALOGEN_MTP_PREFILL" in text,
 "mtp_target_hidden":"drafter.target_hidden" in text,
 "mtp_head":"HALOGEN_MTP_HEAD" in text,
}
result={"schema":1,"binary_linux":a.binary_linux,"capabilities":caps,
 "online_external_state_export":False,
 "offline_state_export":caps["legacy_drafter_taps"] and caps["legacy_drafter_hidden"],
 "current_internal_tap_path":caps["current_tap_from_scan"],
 "notes":[
  "HALOGEN_TAP_FROM_SCAN and HALOGEN_MTP_PREFILL are internal boolean switches, not IPC/export endpoints.",
  "Static xref inspection of flash_serve 0.15.1 shows both default enabled when unset; setting them cannot be claimed as a new speedup.",
  "An online NPU MTP bridge still needs a new state-export/import seam or binary/source support."
 ]}
open(a.out,"w",encoding="utf-8").write(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
