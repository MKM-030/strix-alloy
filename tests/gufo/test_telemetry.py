"""Synthetic scope and failure fixtures for the read-only Windows snapshot."""
import copy
from datetime import datetime, timedelta, timezone
import json
import subprocess
import unittest
from unittest.mock import patch

from gufo_control.telemetry import TelemetryError, collect_snapshot, normalize_snapshot

G = 1 << 30
NOW = datetime(2026, 9, 26, 12, 0, 1, tzinfo=timezone.utc)
STAMP = "2026-09-26T12:00:00Z"
LUID = "0x00000000_0x000111c1"
INSTANCE = "luid_" + LUID + "_phys_0"


def fixture():
    rows = []
    for label, value in (("available bytes", 53 * G), ("committed bytes", 15 * G), ("commit limit", 224 * G)):
        rows.append(dict(path="\\\\host\\memory\\" + label, instance=None, raw_value=value,
                         cooked_value=value, status=0, timestamp_utc=STAMP))
    for label, value in (("dedicated usage", G), ("shared usage", G // 4), ("total committed", 2 * G)):
        rows.append(dict(path="\\\\host\\gpu adapter memory(" + INSTANCE + ")\\" + label,
                         instance=INSTANCE, raw_value=value, cooked_value=value,
                         status=0, timestamp_utc=STAMP))
    return dict(schema=1, provider="PDH/Get-Counter;DXGI/EnumAdapters1",
                adapters=[dict(luid=LUID, vendor_id=0x1002, device_id=0x1586,
                               subsystem_id=0x801d2014, flags=0,
                               description="AMD Radeon(TM) 8060S Graphics",
                               dedicated_video_memory=64 * G)], counters=rows, processes=[])


class TelemetryTests(unittest.TestCase):
    def normalize(self, raw, **kw):
        args = dict(captured_monotonic=100., now_monotonic=101., now_utc=NOW)
        args.update(kw)
        return normalize_snapshot(raw, **args)

    def rejects(self, edit):
        raw = fixture()
        edit(raw)
        with self.assertRaises(TelemetryError):
            self.normalize(raw)

    def test_exact_scopes_and_independent_committed_value(self):
        raw = fixture()
        original = copy.deepcopy(raw)
        result = self.normalize(raw)
        self.assertEqual(raw, original)
        self.assertEqual(result["adapter_luid"], LUID)
        self.assertEqual(result["gpu_scope"], "adapter_aggregate")
        self.assertEqual(result["host_scope"], "host_global")
        self.assertEqual(result["inventory_scope"], "known_engine_and_guest_names")
        self.assertEqual(result["available_physical_bytes"], 53 * G)
        self.assertEqual(result["commit_headroom_bytes"], 209 * G)
        self.assertEqual(result["adapter_total_committed_bytes"], 2 * G)
        self.assertNotEqual(result["adapter_total_committed_bytes"], result["adapter_dedicated_bytes"] + result["adapter_shared_bytes"])
        self.assertEqual(result["sample_utc_min"], NOW.replace(second=0).isoformat())
        self.assertEqual(result["sample_utc_max"], NOW.replace(second=0).isoformat())
        self.assertEqual(result["raw"], raw)

    def test_other_adapter_is_not_summed(self):
        raw = fixture()
        for row in list(raw["counters"][3:]):
            row = dict(row)
            row["path"] = row["path"].replace("0x000111c1", "0x00014fe1")
            row["instance"] = row["instance"].replace("0x000111c1", "0x00014fe1")
            row["raw_value"] = row["cooked_value"] = 10 * G
            raw["counters"].append(row)
        self.assertEqual(self.normalize(raw)["adapter_dedicated_bytes"], G)

    def test_adapter_identity_rejections(self):
        for edit in (
            lambda r: r["adapters"].append(copy.deepcopy(r["adapters"][0])),
            lambda r: r["adapters"][0].update(device_id=1),
            lambda r: r["adapters"][0].update(vendor_id=True),
            lambda r: r["adapters"][0].update(flags=2),
            lambda r: r["adapters"][0].update(description=" "),
            lambda r: r["adapters"][0].update(description="Another Radeon"),
            lambda r: r["adapters"][0].update(subsystem_id=-1),
            lambda r: r["adapters"][0].update(subsystem_id=0),
            lambda r: r["adapters"].append(None),
            lambda r: r["adapters"][0].update(luid="bad"),
        ):
            with self.subTest(edit=edit): self.rejects(edit)

    def test_counter_identity_rejections(self):
        for edit in (
            lambda r: r["counters"].append(copy.deepcopy(r["counters"][3])),
            lambda r: r["counters"].pop(3),
            lambda r: r["counters"][3].update(instance="luid_0x00000000_0x000111c1_phys_1"),
            lambda r: r["counters"][3].update(path=r["counters"][3]["path"].replace("phys_0", "phys_1"), instance=INSTANCE.replace("phys_0", "phys_1")),
            lambda r: r["counters"][0].update(instance=INSTANCE),
            lambda r: r["counters"][3].update(path="\\\\host\\gpu adapter memory(bad)\\dedicated usage"),
            lambda r: r["counters"][0].update(path="\\\\host\\memory\\unknown"),
            lambda r: r["counters"].append(None),
        ):
            with self.subTest(edit=edit): self.rejects(edit)

    def test_counter_health_and_value_rejections(self):
        for edit in (
            lambda r: r["counters"][3].update(status=0xc0000bc6),
            lambda r: r["counters"][3].update(raw_value=-1),
            lambda r: r["counters"][3].update(raw_value=True),
            lambda r: r["counters"][3].update(raw_value=1 << 64),
            lambda r: r["counters"][3].update(cooked_value=1.5),
            lambda r: r["counters"][3].update(cooked_value=1 << 10000),
            lambda r: r["counters"][3].update(cooked_value=float("nan")),
            lambda r: r["counters"][3].update(cooked_value=True),
            lambda r: r["counters"][0].update(timestamp_utc="2026-09-26T11:59:55Z"),
            lambda r: r["counters"][0].update(timestamp_utc="2026-09-26T12:00:02Z"),
            lambda r: r["counters"][0].update(timestamp_utc="bad"),
            lambda r: r["counters"][1].update(raw_value=225 * G),
            lambda r: r["counters"][3].update(raw_value=65 * G),
        ):
            with self.subTest(edit=edit): self.rejects(edit)

    def test_schema_time_and_collection_bounds(self):
        for edit in (
            lambda r: r.update(schema=True),
            lambda r: r.update(provider="other"),
            lambda r: r.update(counters=[]),
            lambda r: r.update(processes=None),
            lambda r: r.update(adapters="bad"),
        ):
            with self.subTest(edit=edit): self.rejects(edit)
        for args in (dict(captured_monotonic=1 << 10000), dict(now_monotonic=float("inf")),
                     dict(now_monotonic=99.), dict(now_monotonic=106.),
                     dict(now_utc=NOW.replace(tzinfo=None))):
            with self.subTest(args=args), self.assertRaises(TelemetryError):
                self.normalize(fixture(), **args)

    def test_inventory_exact_names_and_integrity(self):
        raw = fixture()
        raw["processes"] = [dict(pid=123, name="vmmemWSL"), dict(pid=456, name="notepad"),
                            dict(pid=789, name="LM Studio"), dict(pid=321, name="gufo"),
                            dict(pid=0, name="Idle")]
        self.assertEqual(self.normalize(raw)["other_inference_pids"], [123, 321, 789])
        for edit in (
            lambda r: r["processes"].append(dict(pid=True, name="gufo")),
            lambda r: r["processes"].append(dict(pid=0, name="gufo")),
            lambda r: r["processes"].extend((dict(pid=123, name="gufo"), dict(pid=123, name="notepad"))),
            lambda r: r["processes"].append(dict(pid=777, name=" ")),
            lambda r: r["processes"].append(None),
        ):
            with self.subTest(edit=edit): self.rejects(edit)

    def test_counter_order_does_not_matter(self):
        raw = fixture()
        raw["counters"].reverse()
        self.assertEqual(self.normalize(raw)["adapter_total_committed_bytes"], 2 * G)

    @patch("gufo_control.telemetry.os.name", "nt")
    @patch("gufo_control.telemetry.subprocess.run")
    @patch("gufo_control.telemetry.time.monotonic", side_effect=[100., 101.])
    def test_collect_normalizes_real_subprocess_boundary(self, monotonic, run):
        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls.fromtimestamp(NOW.timestamp(), tz)
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps(fixture()).encode(), b"")
        with patch("gufo_control.telemetry.datetime", FrozenDatetime):
            self.assertEqual(collect_snapshot()["adapter_luid"], LUID)
        self.assertEqual(run.call_args.kwargs["timeout"], 5)
        self.assertEqual(run.call_args.kwargs["creationflags"], subprocess.CREATE_NO_WINDOW)

    @patch("gufo_control.telemetry.os.name", "nt")
    @patch("gufo_control.telemetry.subprocess.run")
    def test_collect_fails_closed_at_process_boundary(self, run):
        failures = (subprocess.CompletedProcess([], 1, b"{}", b"failure"),
                    subprocess.CompletedProcess([], 0, b"\xff", b""),
                    subprocess.CompletedProcess([], 0, b"{", b""),
                    subprocess.CompletedProcess([], 0, b"x" * (2 * 1024 * 1024 + 1), b""))
        for value in failures:
            run.return_value = value
            with self.subTest(value=len(value.stdout)), self.assertRaises(TelemetryError):
                collect_snapshot()
        run.side_effect = subprocess.TimeoutExpired("powershell", 5)
        with self.assertRaises(TelemetryError): collect_snapshot()

    @patch("gufo_control.telemetry.os.name", "nt")
    @patch("gufo_control.telemetry.struct.calcsize", return_value=4)
    def test_collect_rejects_32_bit_python(self, calcsize):
        with self.assertRaises(TelemetryError):
            collect_snapshot()


if __name__ == "__main__":
    unittest.main()
