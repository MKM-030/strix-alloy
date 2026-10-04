"""Fetch only the pinned ROCr subtree into a fresh ignored private directory.

No Git checkout, package installation, build, process launch or runtime change.
Six HTTP workers; every payload must match its recorded size and Git blob SHA.
Root owns execution and the surrounding resource/time guard.
"""
import argparse
import concurrent.futures as futures
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE_COMMIT = "2b22ab0195cc1461cd9abf3b969e9dd7c10af350"
TREE_SHA = "28542580ed0e1104bfc1795cc7f1a6af03eeca52"
TREE_FILE_SHA256 = "da36a979ce5b43a49f424c1d260d9dffc438be8a555023bad86a26405ebe94eb"
EXPECTED_BLOBS, EXPECTED_BYTES = 436, 8573428
ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "server/.local/rocr-async-spin-source-audit-20261005"
PRIVATE = ROOT / "server/.local"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fetch_blob(entry, source):
    relative = entry["path"]
    url = ("https://raw.githubusercontent.com/ROCm/rocm-systems/" + BASE_COMMIT +
           "/projects/rocr-runtime/" + urllib.parse.quote(relative, safe="/"))
    request = urllib.request.Request(url, headers={"User-Agent": "halogen-private-rocr-source/1",
                                                   "Accept-Encoding": "identity"})
    data = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                length = response.headers.get("Content-Length")
                if length is not None and int(length) != entry["size"]:
                    raise ValueError("source Content-Length differs: " + relative)
                data = response.read(entry["size"] + 1)
            break
        except (urllib.error.URLError, TimeoutError):
            if attempt:
                raise
    if len(data) != entry["size"]:
        raise ValueError("source payload size differs: " + relative)
    blob = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
    if blob != entry["sha"]:
        raise ValueError("source Git blob SHA differs: " + relative)
    target = source.joinpath(*PurePosixPath(relative).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
    if entry["mode"] == "100755":
        os.chmod(target, 0o755)
    return {"path": relative, "bytes": len(data), "git_blob_sha": blob,
            "sha256": digest(data), "url": url, "mode": entry["mode"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, default=PRIVATE)
    args = parser.parse_args()
    parent = args.parent.resolve()
    if parent != PRIVATE.resolve() and PRIVATE.resolve() not in parent.parents:
        raise ValueError("output parent must remain inside repository server/.local")
    tree_bytes = (AUDIT / "pinned-rocr-tree.json").read_bytes()
    if digest(tree_bytes) != TREE_FILE_SHA256:
        raise ValueError("reviewed source tree metadata changed")
    tree = json.loads(tree_bytes)
    spec_bytes = (AUDIT / "candidate-spec.json").read_bytes()
    spec = json.loads(spec_bytes)
    if tree["sha"] != TREE_SHA or tree.get("truncated") or spec["baseCommit"] != BASE_COMMIT:
        raise ValueError("base/tree identity is not the reviewed pin")
    entries = []
    seen = set()
    for entry in tree["tree"]:
        if entry["type"] == "tree":
            continue
        path = PurePosixPath(entry["path"])
        if (entry["type"] != "blob" or entry["mode"] not in ("100644", "100755") or
                path.is_absolute() or ".." in path.parts or "\\" in entry["path"]):
            raise ValueError("unexpected source entry: " + entry["path"])
        if path.parts[0] == "rocrtst" or path.parts[:2] == ("libhsakmt", "tests"):
            continue
        if entry["path"].casefold() in seen:
            raise ValueError("duplicate/case-colliding source path")
        seen.add(entry["path"].casefold())
        entries.append(entry)
    if len(entries) != EXPECTED_BLOBS or sum(e["size"] for e in entries) != EXPECTED_BYTES:
        raise ValueError("source manifest count/size differs from reviewed bound")
    out = parent / ("rocr-private-source-" + uuid.uuid4().hex)
    out.mkdir(parents=True, exist_ok=False)
    source = out / "source/projects/rocr-runtime"
    source.mkdir(parents=True, exist_ok=False)
    result = {"stage": "source_fetch", "passed": False, "out": str(out), "source": str(source),
              "base_commit": BASE_COMMIT, "tree_git_sha": TREE_SHA,
              "tree_file_sha256": digest(tree_bytes), "candidate_spec_sha256": digest(spec_bytes),
              "fetcher_sha256": digest(Path(__file__).read_bytes()),
              "workers": 6, "expected_blobs": EXPECTED_BLOBS, "expected_bytes": EXPECTED_BYTES,
              "started_epoch_ns": time.time_ns(), "receipts": [], "errors": []}
    print(json.dumps({"stage": "source_fetch_started", "out": str(out), "blobs": EXPECTED_BLOBS,
                      "bytes": EXPECTED_BYTES}), flush=True)
    pool = futures.ThreadPoolExecutor(max_workers=6)
    jobs = [pool.submit(fetch_blob, entry, source) for entry in entries]
    try:
        for job in futures.as_completed(jobs, timeout=600):
            result["receipts"].append(job.result())
            if len(result["receipts"]) % 50 == 0:
                print(json.dumps({"stage": "source_fetch_progress", "completed": len(result["receipts"]),
                                  "total": EXPECTED_BLOBS}), flush=True)
        result["passed"] = len(result["receipts"]) == EXPECTED_BLOBS
    except Exception as exc:
        result["errors"].append({"type": type(exc).__name__, "message": str(exc)})
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        result["ended_epoch_ns"] = time.time_ns()
        result["receipts"].sort(key=lambda entry: entry["path"])
        (out / "source-fetch-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"stage": "source_fetch_finished", "passed": result["passed"], "out": str(out),
                      "receipt": str(out / "source-fetch-result.json"), "completed": len(result["receipts"]),
                      "errors": result["errors"]}), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
