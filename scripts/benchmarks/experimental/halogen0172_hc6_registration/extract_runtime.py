"""Read the pinned installed HIP library as inert OCI data; never load it."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tarfile

WORK = Path(__file__).resolve().parent
PREP = WORK.parent
ROOT = PREP.parents[3]
sys.path.insert(0, str(ROOT / 'server'))
from host_frames import frame

def memory():
    sample = frame()
    assert min(sample['available_bytes'], sample['commit_headroom_bytes']) >= 18 * 2**30

def ref(path):
    with path.open('rb') as stream:
        value = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), bytes=path.stat().st_size, sha256=value)

if __name__ == '__main__':
    memory()
    pins = json.loads((PREP/'runtime-inventory/runtime-file-pins.json').read_bytes())
    entry, = [row for row in pins['files'] if row['path'].endswith('/libamdhip64.so.7')]
    digest = entry['source_layer_digest'].removeprefix('sha256:')
    layer = PREP/'oci-layout/blobs/sha256'/digest
    assert ref(layer)['sha256'] == digest
    out = WORK/'installed-libamdhip64.so.7.data'
    assert not out.exists()
    with tarfile.open(layer, mode='r|gz') as archive:
        for item in archive:
            memory()
            if item.name.lstrip('./') != entry['path']:
                continue
            assert item.isfile() and item.size == entry['bytes']
            with archive.extractfile(item) as source, out.open('xb') as dest:
                while data := source.read(65536):
                    memory()
                    dest.write(data)
            break
        else:
            raise ValueError('Pinned library absent')
    saved = ref(out)
    assert saved['bytes'] == entry['bytes'] and saved['sha256'] == entry['sha256']
    receipt = dict(utc=datetime.now(timezone.utc).isoformat(), installed_library=saved,
                   layer_digest=digest, image_digest=pins['image_digest'],
                   inert_data_only=True, runtime_initialized=False)
    (WORK/'runtime-extraction.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
