"""Explicitly reuse the immediately preceding measured stock window."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

WORK = Path(__file__).resolve().parent
PREP = WORK.parent
ROOT = PREP.parents[3]
sys.path.insert(0, str(ROOT / 'server'))
from controller import atomic, read


def ref(path):
    return dict(path=str(path), bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == '__main__':
    source = PREP / 'native-i4r-fallback-comparison/after'
    summary = read(source / 'summary.json')
    current = read(ROOT / 'server/.local/current.json')
    backend = read(ROOT / 'backends/halogen-wsl2-0.17.2/.local/current-service.json')
    assert current['phase'] == backend['phase'] == 'ready'
    assert current['run_id'] == summary['controller_run_id']
    assert backend['run_id'] == summary['backend_run_id']
    assert summary['passed'] and summary['measured_repetitions'] == 3
    assert not (WORK / 'before').exists()
    shutil.copytree(source, WORK / 'before')
    shutil.copyfile(PREP / 'native-i4r-fallback-comparison/after-premeasurement-load.json',
        WORK / 'before-premeasurement-load.json')
    record = dict(utc=datetime.now(timezone.utc).isoformat(),
        method='explicit shared stock bookend; no new requests or independent baseline claimed',
        source_window='native-i4r-fallback-comparison/after', source_summary=ref(source / 'summary.json'),
        linked_summary=ref(WORK / 'before/summary.json'),
        controller_run_id=current['run_id'], backend_run_id=backend['run_id'],
        source_receipts=[ref(path) for path in sorted(source.iterdir()) if path.is_file()],
        inference_performed=False)
    atomic(WORK / 'baseline-link.json', record)
    print(json.dumps(dict(linked=True, inference_performed=False, receipt=str(WORK / 'baseline-link.json'))))
