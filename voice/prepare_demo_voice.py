"""Prepare a portable, synthetic German SCC voice using official Qwen APIs.

The reference WAV and transcript are the source of truth. The tensor-only prompt
cache can be recreated and must never be loaded using unrestricted pickle.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import gc
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import pickle
import tempfile
import time
from uuid import uuid4

DESIGN_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
BASE_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
REFERENCE_TEXT = (
    "Guten Tag, ich begleite Sie bei der Einrichtung Ihres neuen Laptops. "
    "Wir prüfen zuerst die Anmeldung und richten danach Ihre Arbeitsumgebung ein. "
    "Dabei erkläre ich Ihnen jeden Schritt."
)
VOICE_DESCRIPTION = (
    "An adult female voice with a warm, clear medium-low register. "
    "Native standard German pronunciation. Calm, confident and approachable, "
    "like a knowledgeable IT service colleague. Conversational delivery, "
    "moderate pace, precise consonants and natural short pauses. "
    "Clean close-microphone speech with restrained expression."
)
SAMPLE_TEXT = (
    "Willkommen beim SCC Service Desk. Ich helfe Ihnen mit Ihrem neuen Laptop. "
    "Welche Anwendungen benötigen Sie für Ihre Arbeit?"
)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_voice_profile(folder, expected_model=None):
    folder = Path(folder)
    profile = json.loads((folder / "voice.json").read_text(encoding="utf-8"))
    if profile.get("schema_version") != 1:
        raise ValueError("Unsupported synthetic voice profile version")
    if profile.get("kind") != "designed_synthetic_voice":
        raise ValueError("The demo voice profile must describe a synthetic voice")
    if profile.get("language") != "German":
        raise ValueError("The SCC demo voice profile must use German")
    if not isinstance(profile.get("reference_text"), str) or not profile["reference_text"].strip():
        raise ValueError("The reference transcript is missing")
    if expected_model and profile.get("base_model") != expected_model:
        raise ValueError("Base model does not match the voice profile")
    if _sha256(folder / "reference.wav") != profile.get("reference_sha256"):
        raise ValueError("The reference audio hash does not match the voice profile")
    return profile


def prompt_cache_key(profile, package_version):
    source = {key: profile[key] for key in (
        "schema_version", "kind", "language", "base_model", "reference_text", "reference_sha256"
    )}
    source["qwen_tts_version"] = package_version
    return hashlib.sha256(json.dumps(source, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def load_or_create_clone_prompt(model, folder, expected_model=BASE_MODEL):
    import torch
    from qwen_tts import VoiceClonePromptItem

    folder = Path(folder)
    profile = read_voice_profile(folder, expected_model)
    key = prompt_cache_key(profile, version("qwen-tts"))
    cache = folder / "prompt.pt"
    if cache.is_file():
        try:
            payload = torch.load(cache, map_location="cpu", weights_only=True)
            if isinstance(payload, dict) and payload.get("source_key") == key:
                items = payload.get("items")
                if not isinstance(items, list) or not items:
                    raise ValueError("The synthetic voice prompt cache has no items")
                for item in items:
                    if not torch.is_tensor(item.get("ref_spk_embedding")):
                        raise ValueError("Missing voice embedding in prompt cache")
                    if item.get("ref_code") is not None and not torch.is_tensor(item["ref_code"]):
                        raise ValueError("Invalid reference codes in prompt cache")
                return [VoiceClonePromptItem(**item) for item in items], profile
        except (OSError, EOFError, RuntimeError, ValueError, TypeError, KeyError, AttributeError, pickle.UnpicklingError):
            # A cache is disposable. The already validated WAV/transcript remain
            # authoritative; never fall back to unrestricted pickle loading.
            pass
    prompts = model.create_voice_clone_prompt(
        ref_audio=str(folder / "reference.wav"),
        ref_text=profile["reference_text"],
        x_vector_only_mode=False,
    )
    items = [{key: value.detach().cpu() if torch.is_tensor(value) else value
              for key, value in asdict(prompt).items()} for prompt in prompts]
    temporary = cache.with_name(cache.name + "." + uuid4().hex + ".tmp")
    try:
        torch.save({"source_key": key, "items": items}, temporary)
        temporary.replace(cache)
    finally:
        temporary.unlink(missing_ok=True)
    return prompts, profile


def load_model(model_id, dtype="bfloat16", threads=6):
    import torch
    from qwen_tts import Qwen3TTSModel

    torch.set_num_threads(threads)
    return Qwen3TTSModel.from_pretrained(
        model_id, device_map="cpu", dtype=getattr(torch, dtype), attn_implementation="sdpa"
    )


def prepare_reference(folder, dtype="bfloat16", threads=6, seed=20261012):
    import soundfile as sf
    import torch

    folder = Path(folder).resolve()
    if (folder / "voice.json").exists():
        return read_voice_profile(folder, BASE_MODEL)
    if folder.exists():
        raise ValueError("The output directory exists without a complete voice profile; choose a new output directory")
    folder.parent.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(seed)
    model = load_model(DESIGN_MODEL, dtype, threads)
    started = time.perf_counter()
    wavs, sr = model.generate_voice_design(
        text=REFERENCE_TEXT, language="German", instruct=VOICE_DESCRIPTION, max_new_tokens=1024
    )
    elapsed = time.perf_counter() - started
    del model
    gc.collect()
    with tempfile.TemporaryDirectory(prefix=".scc-voice-", dir=folder.parent) as temporary:
        staging = Path(temporary)
        sf.write(staging / "reference.wav", wavs[0], sr, subtype="PCM_16")
        profile = {
            "schema_version": 1, "name": "SCC Demo", "kind": "designed_synthetic_voice",
            "language": "German", "design_model": DESIGN_MODEL, "base_model": BASE_MODEL,
            "reference_text": REFERENCE_TEXT, "description": VOICE_DESCRIPTION,
            "reference_sample_rate": sr, "reference_sha256": _sha256(staging / "reference.wav"),
            "qwen_tts_version": version("qwen-tts"), "seed": seed,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "reference_generation_seconds": round(elapsed, 3),
            "reference_audio_seconds": round(len(wavs[0]) / sr, 3),
        }
        _write_json(staging / "voice.json", profile)
        try:
            staging.rename(folder)
        except OSError:
            if (folder / "voice.json").is_file():
                return read_voice_profile(folder, BASE_MODEL)
            raise
    return profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cache-dir", help="Hugging Face home; omit to use the current service environment")
    parser.add_argument("--dtype", choices=("bfloat16", "float32"), default="bfloat16")
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--seed", type=int, default=20261012)
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be positive")
    if args.cache_dir:
        os.environ["HF_HOME"] = args.cache_dir
    import soundfile as sf

    folder = Path(args.output_dir)
    print("Preparing synthetic German reference", flush=True)
    profile = prepare_reference(folder, args.dtype, args.threads, args.seed)
    print("Preparing reusable Base prompt", flush=True)
    base = load_model(BASE_MODEL, args.dtype, args.threads)
    prompts, _ = load_or_create_clone_prompt(base, folder)
    started = time.perf_counter()
    wavs, sr = base.generate_voice_clone(
        text=SAMPLE_TEXT, language="German", voice_clone_prompt=prompts, max_new_tokens=1024
    )
    elapsed = time.perf_counter() - started
    sf.write(folder / "sample.wav", wavs[0], sr, subtype="PCM_16")
    report = {
        "voice": profile["name"], "kind": profile["kind"], "model": BASE_MODEL,
        "dtype": args.dtype, "threads": args.threads, "sample_text": SAMPLE_TEXT,
        "sample_rate": sr, "generation_seconds": round(elapsed, 3),
        "audio_seconds": round(len(wavs[0]) / sr, 3),
        "asr_validated": False,
    }
    _write_json(folder / "validation.json", report)
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
