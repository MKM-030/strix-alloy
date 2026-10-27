"""Local, single-request Qwen audio workers. Start one process per virtualenv."""
import argparse
import io
import logging
import os
from pathlib import Path
import secrets
import threading

MAX_FILE = 20 * 1024 * 1024
MAX_DURATION = 60.0
MIN_FREE_GIB = 18
MODEL_IDS = {
    "asr": "Qwen/Qwen3-ASR-0.6B",
    "tts": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
}
ALIASES = {"asr": "qwen3-asr-0.6b", "tts": "qwen3-tts-0.6b"}
VOICES = {
    "ryan": "Ryan", "aiden": "Aiden", "vivian": "Vivian",
    "serena": "Serena", "uncle_fu": "Uncle_Fu", "dylan": "Dylan",
    "eric": "Eric", "ono_anna": "Ono_Anna", "sohee": "Sohee",
}
LOG = logging.getLogger("audio-worker")


from starlette.exceptions import HTTPException as RequestError


class BodyTooLarge(RequestError):
    def __init__(self):
        super().__init__(413, "Request too large")


class RequestGate:
    """Authenticate before parsing; reject overlap and oversized streamed bodies."""
    def __init__(self, app, token, lock, mode):
        self.app, self.token, self.lock, self.mode = app, token, lock, mode

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse
        headers = dict(scope["headers"])
        expected = ("Bearer " + self.token).encode()
        if not secrets.compare_digest(headers.get(b"authorization", b""), expected):
            return await JSONResponse({"detail": "Unauthorized"}, 401)(scope, receive, send)
        limit = MAX_FILE + 1024 * 1024 if self.mode == "asr" else 64 * 1024
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "Invalid Content-Length"}, 400)(scope, receive, send)
        if length < 0 or length > limit:
            return await JSONResponse({"detail": "Request too large"}, 413)(scope, receive, send)
        acquired = scope["method"] == "POST"
        if acquired and not self.lock.acquire(blocking=False):
            return await JSONResponse({"detail": "Audio worker is busy"}, 503,
                headers={"Retry-After": "1"})(scope, receive, send)
        received = 0
        response_started = False

        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooLarge()
            return message

        async def tracked_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, bounded_receive, tracked_send)
        except BodyTooLarge:
            if not response_started:
                await JSONResponse({"detail": "Request too large"}, 413)(scope, receive, send)
        finally:
            if acquired:
                self.lock.release()


def ensure_memory_reserve():
    import psutil
    if psutil.virtual_memory().available < MIN_FREE_GIB * 1024 ** 3:
        from fastapi import HTTPException
        raise HTTPException(503, "Insufficient free memory; 18 GiB reserve required",
                            headers={"Retry-After": "10"})


def decode_audio(data):
    import numpy as np
    import soundfile as sf
    from fastapi import HTTPException
    if not data:
        raise HTTPException(400, "Empty audio")
    if len(data) > MAX_FILE:
        raise HTTPException(413, "Audio exceeds 20 MiB")
    try:
        info = sf.info(io.BytesIO(data))
    except Exception:
        raise HTTPException(415, "Unsupported or invalid audio; send PCM WAV")
    if info.samplerate < 8000 or info.samplerate > 192000 or info.channels > 8:
        raise HTTPException(400, "Unsupported audio dimensions")
    if info.frames <= 0:
        raise HTTPException(400, "Empty audio")
    if info.frames / info.samplerate > MAX_DURATION:
        raise HTTPException(413, "Audio exceeds 60 seconds")
    try:
        samples, rate = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    except Exception:
        raise HTTPException(415, "Cannot decode audio; send PCM WAV")
    if len(samples) / rate > MAX_DURATION or not np.isfinite(samples).all():
        raise HTTPException(400, "Invalid audio samples")
    return samples.mean(axis=1), rate


def create_app(mode, token, backend):
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.responses import Response
    from pydantic import BaseModel, ConfigDict, Field
    if mode not in MODEL_IDS or not token:
        raise ValueError("A supported mode and authentication token are required")
    app = FastAPI(title="Local Qwen Audio", docs_url=None, redoc_url=None, openapi_url=None)
    lock = threading.Lock()
    app.add_middleware(RequestGate, token=token, lock=lock, mode=mode)

    @app.get("/health")
    def health():
        result = {"status": "ready", "mode": mode, "model": getattr(backend, "model_id", MODEL_IDS[mode]),
                "voice": getattr(backend, "voice_name", None),
                "device": "cpu", "dtype": getattr(backend, "dtype", "float32"),
                "busy": lock.locked(), "max_parallel": 1}
        if getattr(backend, "runtime", None) == "crispasr":
            result["runtime"] = "crispasr"
        return result

    def check_model(name):
        if name not in (getattr(backend, "model_id", MODEL_IDS[mode]), ALIASES[mode]):
            raise HTTPException(400, "Unsupported model")

    def inference_error():
        LOG.error("Model inference failed")
        return HTTPException(500, "Audio inference failed; check worker status")

    if mode == "asr":
        @app.post("/v1/audio/transcriptions")
        def transcriptions(file: UploadFile = File(...), model: str = Form(...),
                           language: str = Form("de"), response_format: str = Form("json")):
            check_model(model)
            if response_format != "json":
                raise HTTPException(400, "Only JSON transcription responses are supported")
            languages = {"de": "German", "german": "German", "en": "English",
                         "english": "English", "auto": None}
            if language.lower() not in languages:
                raise HTTPException(400, "Language must be de, en, or auto")
            samples, rate = decode_audio(file.file.read(MAX_FILE + 1))
            ensure_memory_reserve()
            try:
                text = backend.transcribe(samples, rate, languages[language.lower()])
            except Exception:
                raise inference_error() from None
            return {"text": text}
    else:
        class SpeechRequest(BaseModel):
            model_config = ConfigDict(extra="forbid", strict=True)
            model: str
            input: str = Field(min_length=1, max_length=1500)
            voice: str = "scc-demo" if getattr(backend, "voice_profile", None) else "Ryan"
            response_format: str = "wav"

        @app.post("/v1/audio/speech")
        def speech(request: SpeechRequest):
            import soundfile as sf
            check_model(request.model)
            if request.response_format != "wav":
                raise HTTPException(400, "Only WAV output is supported")
            if getattr(backend, "voice_profile", None):
                voice = "scc-demo" if request.voice.lower() in ("scc-demo", "scc demo") else None
            else:
                voice = VOICES.get(request.voice.lower())
            if voice is None:
                raise HTTPException(400, "Unsupported voice for this worker")
            text = request.input.strip()
            if not text:
                raise HTTPException(400, "Speech text cannot be empty")
            ensure_memory_reserve()
            try:
                waveform, rate = backend.synthesize(text, voice)
                output = io.BytesIO()
                sf.write(output, waveform, rate, format="WAV", subtype="PCM_16")
                return Response(output.getvalue(), media_type="audio/wav")
            except Exception:
                raise inference_error() from None
    return app


def cpu_dtype(name):
    import torch
    if name not in ("float32", "bfloat16"):
        raise ValueError("CPU dtype must be float32 or bfloat16")
    if name == "bfloat16" and not getattr(torch.cpu, "_is_avx512_bf16_supported", lambda: False)():
        raise RuntimeError("BF16 requires supported AVX512 BF16 CPU instructions; use float32")
    return torch.float32 if name == "float32" else torch.bfloat16


class QwenBackend:
    def __init__(self, mode, threads, dtype="float32", voice_profile=None):
        import torch
        torch_dtype = cpu_dtype(dtype)
        self.dtype = dtype
        self.voice_profile = voice_profile
        self.model_id = MODEL_IDS[mode]
        self.voice_name = None
        if voice_profile:
            if mode != "tts":
                raise ValueError("A voice profile is only supported for TTS")
            from prepare_demo_voice import BASE_MODEL, read_voice_profile
            profile = read_voice_profile(voice_profile, BASE_MODEL)
            self.model_id = BASE_MODEL
            self.voice_name = profile["name"]
        ensure_memory_reserve()
        torch.set_num_threads(threads)
        torch.set_num_interop_threads(1)
        self.mode = mode
        from huggingface_hub import snapshot_download
        from huggingface_hub.errors import LocalEntryNotFoundError
        try:
            source = snapshot_download(self.model_id, local_files_only=True)
        except LocalEntryNotFoundError:
            source = snapshot_download(self.model_id, max_workers=2)
        if mode == "asr":
            from qwen_asr import Qwen3ASRModel
            self.model = Qwen3ASRModel.from_pretrained(
                source, device_map="cpu", dtype=torch_dtype,
                max_inference_batch_size=1, max_new_tokens=256)
        else:
            from qwen_tts import Qwen3TTSModel
            self.model = Qwen3TTSModel.from_pretrained(
                source, device_map="cpu", dtype=torch_dtype, attn_implementation="sdpa")
            if voice_profile:
                from prepare_demo_voice import load_or_create_clone_prompt
                self.clone_prompt, _ = load_or_create_clone_prompt(self.model, voice_profile)
        ensure_memory_reserve()

    def transcribe(self, audio, sample_rate, language):
        return self.model.transcribe(audio=(audio, sample_rate), language=language)[0].text

    def synthesize(self, text, voice):
        if self.voice_profile:
            waveforms, rate = self.model.generate_voice_clone(
                text=text, language="German", voice_clone_prompt=self.clone_prompt,
                max_new_tokens=2048)
        else:
            waveforms, rate = self.model.generate_custom_voice(
                text=text, language="German", speaker=voice, max_new_tokens=2048)
        return waveforms[0], rate


def create_backend(mode, threads, dtype, voice_profile, asr_runtime="torch",
                   asr_model=None, asr_library=None):
    if asr_runtime == "torch":
        if asr_model or asr_library or dtype == "mixed-gguf":
            raise ValueError("Native ASR assets require the explicit crispasr runtime")
        return QwenBackend(mode, threads, dtype, voice_profile)
    if (asr_runtime != "crispasr" or mode != "asr" or voice_profile
            or dtype != "mixed-gguf" or not asr_model or not asr_library):
        raise ValueError("CrispASR requires ASR mode, mixed-gguf and explicit qualified local assets")
    from native_qwen_asr import NativeQwenASR
    ensure_memory_reserve()
    backend = NativeQwenASR(asr_model, asr_library, threads)
    try:
        ensure_memory_reserve()
    except BaseException:
        backend.close()
        raise
    return backend


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["asr", "tts"], required=True)
    parser.add_argument("--port", type=int)
    parser.add_argument("--dtype", choices=["float32", "bfloat16", "mixed-gguf"], default="float32")
    parser.add_argument("--asr-runtime", choices=["torch", "crispasr"], default="torch")
    parser.add_argument("--asr-model", help="Qualified local Qwen0.6 GGUF; crispasr only")
    parser.add_argument("--asr-library", help="Qualified local CrispASR DLL; crispasr only")
    parser.add_argument("--threads", type=int, default=6, choices=range(1, 9))
    parser.add_argument("--token-file", default=r"C:\Projects\strix-alloy-clean\server\.local\servicenow-api-token.txt")
    parser.add_argument("--cache-dir", default=r"E:\SCC-Voice\models")
    parser.add_argument("--voice-profile", help="Directory containing the validated synthetic German voice profile")
    args = parser.parse_args()
    token = Path(args.token_file).read_text(encoding="utf-8-sig").strip()
    if not token:
        raise SystemExit("Authentication token file is empty")
    os.environ["HF_HOME"] = args.cache_dir
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("OMP_NUM_THREADS", str(args.threads))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    LOG.info("Loading %s worker on CPU with %s threads and %s (%s)",
             args.mode, args.threads, args.dtype, args.asr_runtime)
    backend = create_backend(args.mode, args.threads, args.dtype, args.voice_profile,
                             args.asr_runtime, args.asr_model, args.asr_library)
    LOG.info("%s worker ready", args.mode)
    try:
        import uvicorn
        uvicorn.run(create_app(args.mode, token, backend), host="127.0.0.1",
                    port=args.port or (8851 if args.mode == "asr" else 8852),
                    access_log=False, log_level="warning")
    finally:
        close = getattr(backend, "close", None)
        if close is not None:
            close()


if __name__ == "__main__":
    main()
