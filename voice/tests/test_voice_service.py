"""Configured synthetic voice must retain the authenticated audio contract."""
from types import SimpleNamespace

from test_audio_contract import AUTH, SPEECH, FakeBackend, make_client


def test_synthetic_voice_accepts_alias_and_reports_real_model():
    backend = FakeBackend()
    backend.voice_profile = "fixture-profile"
    backend.voice_name = "SCC Demo"
    backend.model_id = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
    with make_client(backend=backend) as client:
        health = client.get("/health", headers=AUTH).json()
        assert health["model"] == backend.model_id
        assert health["voice"] == "SCC Demo"
        for model in ("qwen3-tts-0.6b", backend.model_id):
            result = client.post("/v1/audio/speech", headers=AUTH,
                                 json={**SPEECH, "voice": "scc-demo", "model": model})
            assert result.status_code == 200
        default = dict(SPEECH)
        del default["voice"]
        assert client.post("/v1/audio/speech", headers=AUTH, json=default).status_code == 200
        assert client.post("/v1/audio/speech", headers=AUTH, json=SPEECH).status_code == 400
        assert client.post("/v1/audio/speech", json={**SPEECH, "voice": "scc-demo"}).status_code == 401
    assert backend.calls == 3


def test_synthetic_voice_backend_uses_validated_clone_prompt():
    from audio_service import QwenBackend
    backend = QwenBackend.__new__(QwenBackend)
    backend.voice_profile = "fixture-profile"
    backend.clone_prompt = ["validated-prompt"]
    observed = {}

    def generate_voice_clone(**arguments):
        observed.update(arguments)
        return [[0.0, 0.1]], 24000

    backend.model = SimpleNamespace(generate_voice_clone=generate_voice_clone)
    assert backend.synthesize("Guten Tag.", "scc-demo") == ([0.0, 0.1], 24000)
    assert observed["voice_clone_prompt"] is backend.clone_prompt
    assert observed["language"] == "German"
    assert observed["text"] == "Guten Tag."
