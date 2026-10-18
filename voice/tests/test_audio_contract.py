"""Behavioral HTTP contract tests; model inference is replaced at its boundary."""
import importlib.util
import io
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_service_contract_available():
    assert importlib.util.find_spec("audio_service") is not None, "Audio service is missing"


def make_client(mode="tts", backend=None):
    from fastapi.testclient import TestClient
    from audio_service import create_app
    return TestClient(create_app(mode, "test-secret", backend or FakeBackend()))


class FakeBackend:
    def __init__(self):
        self.fail = False
        self.calls = 0

    def transcribe(self, audio, sample_rate, language):
        self.calls += 1
        return "Guten Tag."

    def synthesize(self, text, voice):
        import numpy as np
        self.calls += 1
        if self.fail:
            raise RuntimeError("private implementation detail")
        return np.zeros(2400, dtype="float32"), 24000


AUTH = {"Authorization": "Bearer test-secret"}
SPEECH = {"model": "qwen3-tts-0.6b", "input": "Guten Tag.", "voice": "Ryan", "response_format": "wav"}


def wav(seconds=0.1):
    import numpy as np
    import soundfile as sf
    output = io.BytesIO()
    sf.write(output, np.zeros(int(16000 * seconds)), 16000, format="WAV", subtype="PCM_16")
    return output.getvalue()


def test_authentication_precedes_body_parsing():
    with make_client() as client:
        assert client.get("/health").status_code == 401
        assert client.post("/v1/audio/speech", content=b"not json").status_code == 401
        assert client.get("/health", headers=AUTH).json()["status"] == "ready"


def test_speech_returns_real_wav_and_correct_mime():
    import soundfile as sf
    with make_client() as client:
        response = client.post("/v1/audio/speech", json=SPEECH, headers=AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    samples, sr = sf.read(io.BytesIO(response.content))
    assert sr == 24000 and len(samples) == 2400


def test_speech_rejects_invalid_models_formats_voices_and_lengths():
    backend = FakeBackend()
    with make_client(backend=backend) as client:
        for change in [
            {"model": "https://example.com/arbitrary-model"},
            {"voice": "unknown-person"},
            {"response_format": "mp3"},
            {"input": "x" * 1501},
            {"input": "   "},
            {"input": 123},
        ]:
            response = client.post("/v1/audio/speech", json={**SPEECH, **change}, headers=AUTH)
            assert response.status_code in (400, 422)
    assert backend.calls == 0


def test_asr_accepts_uploaded_wav_and_transcription_shape():
    with make_client("asr") as client:
        response = client.post("/v1/audio/transcriptions", headers=AUTH,
            data={"model": "qwen3-asr-0.6b", "language": "de"},
            files={"file": ("recording.wav", wav(), "audio/wav")})
    assert response.status_code == 200
    assert response.json() == {"text": "Guten Tag."}


def test_asr_rejects_duration_before_inference():
    backend = FakeBackend()
    with make_client("asr", backend) as client:
        response = client.post("/v1/audio/transcriptions", headers=AUTH,
            data={"model": "qwen3-asr-0.6b"},
            files={"file": ("long.wav", wav(60.1), "audio/wav")})
    assert response.status_code == 413
    assert backend.calls == 0


def test_asr_rejects_large_body_before_decode():
    with make_client("asr") as client:
        response = client.post("/v1/audio/transcriptions", headers=AUTH,
            content=b"x" * (21 * 1024 * 1024 + 1))
    assert response.status_code == 413


def test_asr_rejects_unknown_codec_and_remote_url():
    with make_client("asr") as client:
        response = client.post("/v1/audio/transcriptions", headers=AUTH,
            data={"model": "qwen3-asr-0.6b"},
            files={"file": ("bad.wav", b"not an audio file", "audio/wav")})
        assert response.status_code == 415
        assert client.post("/v1/audio/transcriptions", headers=AUTH,
            json={"model": "qwen3-asr-0.6b", "audio": "https://example.com/audio.wav"}).status_code == 422


def test_failure_releases_worker_and_hides_exception():
    backend = FakeBackend()
    with make_client(backend=backend) as client:
        backend.fail = True
        failed = client.post("/v1/audio/speech", headers=AUTH, json=SPEECH)
        assert failed.status_code == 500
        assert "private implementation" not in failed.text
        backend.fail = False
        assert client.post("/v1/audio/speech", headers=AUTH, json=SPEECH).status_code == 200


def test_concurrent_inference_returns_busy_without_queueing():
    class BlockingBackend(FakeBackend):
        entered = threading.Event()
        release = threading.Event()
        def synthesize(self, text, voice):
            self.entered.set()
            assert self.release.wait(5)
            return super().synthesize(text, voice)

    backend = BlockingBackend()
    with make_client(backend=backend) as client, ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(client.post, "/v1/audio/speech", headers=AUTH, json=SPEECH)
        assert backend.entered.wait(5)
        try:
            second = client.post("/v1/audio/speech", headers=AUTH, json=SPEECH)
            assert second.status_code == 503
            assert second.headers["retry-after"] == "1"
        finally:
            backend.release.set()
        assert first.result().status_code == 200
    assert backend.calls == 1


def test_streamed_body_limit_returns_413_and_releases_worker():
    backend = FakeBackend()
    with make_client(backend=backend) as client:
        oversized = client.post("/v1/audio/speech", headers={**AUTH, "Content-Type": "application/json"},
            content=iter([b'{"input":"', b"x" * (65 * 1024), b'"}']))
        assert oversized.status_code == 413
        assert backend.calls == 0
        assert client.post("/v1/audio/speech", headers=AUTH, json=SPEECH).status_code == 200


def test_dtype_validation_rejects_unknown_or_unsupported_cpu_type(monkeypatch):
    import pytest
    import torch
    import audio_service
    resolve = getattr(audio_service, "cpu_dtype", None)
    assert callable(resolve), "Explicit CPU dtype validation is required"
    assert resolve("float32") is torch.float32
    with pytest.raises(ValueError):
        resolve("float16")
    monkeypatch.setattr(torch.cpu, "_is_avx512_bf16_supported", lambda: False)
    with pytest.raises(RuntimeError, match="BF16"):
        resolve("bfloat16")
