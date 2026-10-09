"""Acquire only pinned public Python/license text, never model data or packages."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

from contract import OWNER_REVISION

BASE = f"https://raw.githubusercontent.com/PixelML/deepspec-qwen38-flash-next/{OWNER_REVISION}/"
SOURCES = {
    "pixel_modeling.py": BASE + "deepspec/modeling/dspark/qwen3/modeling.py",
    "pixel_common.py": BASE + "deepspec/modeling/dspark/common.py",
    "pixel_epoch7.py": BASE + "serving/plugin/dflash_epoch7.py",
    "pixel_training_config.py": BASE + "config/dflash/dflash_qwen38_flash_next.py",
    "pixel_LICENSE": BASE + "LICENSE",
    "hf_modeling_qwen3.py": "https://raw.githubusercontent.com/huggingface/transformers/v5.16.1/src/transformers/models/qwen3/modeling_qwen3.py",
    "hf_LICENSE": "https://raw.githubusercontent.com/huggingface/transformers/v5.16.1/LICENSE",
}


def main():
    destination = Path(__file__).resolve().parent / "sources"
    destination.mkdir(exist_ok=True)
    receipts = {}
    for name, url in SOURCES.items():
        with urlopen(url, timeout=40) as response:
            body = response.read(2 * 1024 * 1024 + 1)
        if len(body) > 2 * 1024 * 1024:
            raise ValueError("Source unexpectedly exceeds text-only size cap")
        body.decode("utf-8")
        (destination / name).write_bytes(body)
        receipts[name] = {"url": url, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    (destination / "receipts.json").write_text(json.dumps(receipts, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipts, indent=2))


if __name__ == "__main__":
    main()
