"""Owned, loopback-only native speech probes; no product or ServiceNow calls."""
import argparse
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import wave

import psutil

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "runtime"
OWNER = RUNTIME / "owned-processes.json"
PROFILE = ROOT.parent / "assets" / "scc-demo"
FIXTURE = Path(r"E:\SCC-Voice\voices\scc-demo\sample.wav")
SPEECH = "Guten Tag. Wie kann ich helfen?"
SERVICES = {
    "asr": {
        "port": 8861,
        "health": "/health",
        "args": [
            r"C:\AI\build\whisper.cpp\build\bin\whisper-server.exe",
            "--model", r"C:\AI\models\stt\ggml-turbo-german.bin",
            "--host", "127.0.0.1", "--port", "8861",
            "-l", "de", "-t", "6", "-fa", "-nf",
        ],
    },
    "tts": {
        "port": 8862,
        "health": "/v1/models",
        "args": [
            r"C:\AI\qwentts.cpp\build\Release\tts-server.exe",
            "--model", r"C:\AI\models\qwen3-tts-gguf\qwen-talker-0.6b-base-Q8_0.gguf",
            "--codec", r"C:\AI\models\qwen3-tts-gguf\qwen-tokenizer-12hz-Q8_0.gguf",
            "--alias", "scc-native-qwen3", "--host", "127.0.0.1",
            "--port", "8862", "--lang", "German", "--max-batch", "1",
        ],
    },
}


def dump(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def owners():
    return json.loads(OWNER.read_text()) if OWNER.exists() else {}


def same_process(record):
    try:
        process = psutil.Process(record["pid"])
        return (
            abs(process.create_time() - record["created"]) < 0.01
            and os.path.normcase(process.exe()) == os.path.normcase(record["exe"])
            and process.cmdline() == record["cmdline"]
        )
    except (psutil.Error, KeyError):
        return False


def listening(port):
    return [
        c for c in psutil.net_connections(kind="tcp")
        if c.status == psutil.CONN_LISTEN and c.laddr.port == port
    ]


class ProbeHTTPError(RuntimeError):
    def __init__(self, status, body):
        self.status = status
        super().__init__(f"HTTP {status}: {body[:500]!r}")


def assert_owned_listener(port):
    name = next(key for key, service in SERVICES.items() if service["port"] == port)
    record = owners().get(name)
    if not record or not same_process(record):
        raise RuntimeError(f"{name} ownership is absent or changed")
    if record["cmdline"] != SERVICES[name]["args"]:
        raise RuntimeError(f"{name} configuration changed; refusing reuse")
    sockets = listening(port)
    if not sockets:
        raise OSError(f"{name} has not opened its listener yet")
    if any(c.pid != record["pid"] or c.laddr.ip != "127.0.0.1" for c in sockets):
        raise RuntimeError(f"{name} listener is not owned loopback; refusing HTTP traffic")


def request(port, route, method="GET", body=None, content_type="application/json", timeout=40):
    assert_owned_listener(port)
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    start = time.perf_counter()
    try:
        headers = {"Content-Type": content_type} if body is not None else {}
        conn.request(method, route, body, headers)
        response = conn.getresponse()
        header_seconds = time.perf_counter() - start
        first = response.read(1)
        first_seconds = time.perf_counter() - start
        data = first + response.read(2_000_001)
        complete_seconds = time.perf_counter() - start
        if len(data) > 2_000_000:
            raise RuntimeError("Response exceeded bounded probe size")
        result = {
            "status": response.status,
            "headers_seconds": round(header_seconds, 4),
            "first_body_byte_seconds": round(first_seconds, 4),
            "complete_seconds": round(complete_seconds, 4),
            "content_type": response.getheader("Content-Type"),
            "bytes": len(data),
        }
        if response.status != 200:
            raise ProbeHTTPError(response.status, data)
        return data, result
    finally:
        conn.close()


def health(name):
    service = SERVICES[name]
    raw, timing = request(service["port"], service["health"], timeout=3)
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = raw.decode("utf-8", errors="replace")[:300]
    return {"port": service["port"], "health": payload, **timing}


def start():
    if sys.platform != "win32":
        raise RuntimeError("This launcher is for the inspected Windows host")
    if psutil.virtual_memory().available < 18 * 1024**3:
        raise RuntimeError("Refusing launch: free system RAM is below 18 GiB")
    state = owners()
    for name, service in SERVICES.items():
        if name in state and same_process(state[name]):
            if state[name]["cmdline"] != service["args"]:
                raise RuntimeError(f"{name} configuration changed; stop the owned old service first")
            continue
        if listening(service["port"]):
            raise RuntimeError(f"Port {service['port']} is occupied; not adopting or stopping it")
        for index, value in enumerate(service["args"]):
            if index == 0 or service["args"][index - 1] in ("--model", "--codec"):
                if not Path(value).is_file():
                    raise FileNotFoundError(value)
    RUNTIME.mkdir(exist_ok=True)
    for name, service in SERVICES.items():
        if name not in state or not same_process(state[name]):
            with (RUNTIME / f"{name}.stdout.log").open("ab") as stdout, (RUNTIME / f"{name}.stderr.log").open("ab") as stderr:
                process = subprocess.Popen(
                    service["args"], cwd=ROOT, stdin=subprocess.DEVNULL,
                    stdout=stdout, stderr=stderr,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                )
            identity = psutil.Process(process.pid)
            state[name] = {
                "pid": process.pid, "created": identity.create_time(),
                "exe": identity.exe(), "cmdline": identity.cmdline(),
                "port": service["port"], "owner": "scc-native-speech-validation",
            }
            OWNER.write_text(json.dumps(state, indent=2), encoding="utf-8")
            dump({"spawned": name, "pid": process.pid, "port": service["port"]})
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if not same_process(state[name]):
                raise RuntimeError(f"{name} exited; inspect runtime/{name}.stderr.log")
            try:
                result = health(name)
                sockets = listening(service["port"])
                if not sockets or any(c.pid != state[name]["pid"] or c.laddr.ip != "127.0.0.1" for c in sockets):
                    raise RuntimeError(f"{name} listener ownership/bind mismatch")
                dump({"ready": name, "pid": state[name]["pid"], **result})
                break
            except ProbeHTTPError as error:
                if error.status != 503:
                    raise
                time.sleep(0.5)
            except (OSError, http.client.HTTPException):
                time.sleep(0.5)
        else:
            raise TimeoutError(f"{name} did not become ready within 60 seconds")


def status():
    state = owners()
    for name, service in SERVICES.items():
        record = state.get(name)
        result = {"name": name, "owned_alive": bool(record and same_process(record)), "port": service["port"]}
        if record:
            result["pid"] = record["pid"]
        if result["owned_alive"]:
            try:
                result.update(health(name))
            except Exception as error:
                result["health_error"] = str(error)
        dump(result)
    dump({"free_system_gib": round(psutil.virtual_memory().available / 1024**3, 2)})


def stop():
    for name, record in owners().items():
        if not same_process(record):
            dump({"name": name, "stopped": False, "reason": "identity absent or changed"})
            continue
        process = psutil.Process(record["pid"])
        process.terminate()
        try:
            process.wait(10)
        except psutil.TimeoutExpired:
            if same_process(record):
                process.kill()
                process.wait(5)
        dump({"name": name, "stopped": True, "pid": record["pid"]})


def transcribe(path):
    boundary = "scc-" + uuid.uuid4().hex
    parts = []
    for key, value in (("language", "de"), ("temperature", "0"), ("response_format", "json")):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"fixture.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode())
    parts.extend((path.read_bytes(), f"\r\n--{boundary}--\r\n".encode()))
    raw, result = request(8861, "/inference", "POST", b"".join(parts), "multipart/form-data; boundary=" + boundary)
    result["transcript"] = json.loads(raw)["text"].strip()
    result["fixture"] = str(path)
    return result


def validate():
    state = owners()
    if any(name not in state or not same_process(state[name]) for name in SERVICES):
        raise RuntimeError("Both services must match this launcher's ownership record")
    profile = json.loads((PROFILE / "voice.json").read_text(encoding="utf-8-sig"))
    reference = (PROFILE / "reference.wav").read_bytes()
    if hashlib.sha256(reference).hexdigest() != profile["reference_sha256"]:
        raise RuntimeError("Synthetic SCC voice reference hash mismatch")
    if profile["kind"] != "designed_synthetic_voice":
        raise RuntimeError("Only the existing synthetic SCC reference is authorized")
    results = {"timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "commands": {k: v["args"] for k, v in SERVICES.items()}}
    results["owned_pids"] = {k: v["pid"] for k, v in state.items()}
    results["before_health"] = {name: health(name) for name in SERVICES}
    results["existing_fixture_asr"] = transcribe(FIXTURE)
    dump({"existing_fixture_asr": results["existing_fixture_asr"]})
    voice = {"name": "scc-demo", "ref_text": profile["reference_text"], "wav_b64": base64.b64encode(reference).decode("ascii")}
    raw, registration = request(8862, "/v1/audio/voices", "POST", json.dumps(voice).encode())
    results["voice_registration"] = {**registration, "voice": "SCC Demo", "reference_sha256": profile["reference_sha256"], "response": json.loads(raw)}
    dump({"voice_registration": {k: v for k, v in results["voice_registration"].items() if k != "response"}})
    payload = {"input": SPEECH, "voice": "scc-demo", "response_format": "pcm", "seed": 42, "max_new_tokens": 96}
    raw, synthesis = request(8862, "/v1/audio/speech", "POST", json.dumps(payload).encode(), timeout=45)
    if not raw or len(raw) % 2 or raw.startswith(b"RIFF"):
        raise RuntimeError("TTS did not produce raw PCM16 samples")
    output = RUNTIME / "scc-native-smoke.wav"
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(raw)
    synthesis.update({"text": SPEECH, "sample_rate": 24000, "audio_seconds": round(len(raw) / 48000, 4), "path": str(output), "pcm_sha256": hashlib.sha256(raw).hexdigest()})
    results["tts"] = synthesis
    dump({"tts": synthesis})
    results["tts_roundtrip_asr"] = transcribe(output)
    results["after_health"] = {name: health(name) for name in SERVICES}
    results["free_system_gib"] = round(psutil.virtual_memory().available / 1024**3, 2)
    (ROOT / "validation-result.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    dump({"tts_roundtrip_asr": results["tts_roundtrip_asr"], "report": str(ROOT / "validation-result.json"), "free_system_gib": results["free_system_gib"]})


def warm():
    report = ROOT / "validation-result.json"
    results = json.loads(report.read_text(encoding="utf-8"))
    if "warm_tts" in results:
        raise RuntimeError("The bounded warm check was already recorded")
    payload = {"input": SPEECH, "voice": "scc-demo", "response_format": "pcm", "seed": 42, "max_new_tokens": 96}
    raw, synthesis = request(8862, "/v1/audio/speech", "POST", json.dumps(payload).encode(), timeout=45)
    if not raw or len(raw) % 2 or raw.startswith(b"RIFF"):
        raise RuntimeError("TTS did not produce raw PCM16 samples")
    output = RUNTIME / "scc-native-warm.wav"
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(raw)
    synthesis.update({"text": SPEECH, "sample_rate": 24000, "audio_seconds": round(len(raw) / 48000, 4), "path": str(output), "pcm_sha256": hashlib.sha256(raw).hexdigest()})
    results["warm_tts"] = synthesis
    report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    dump({"warm_tts": synthesis})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("start", "status", "stop", "validate", "warm"))
    action = parser.parse_args().action
    {"start": start, "status": status, "stop": stop, "validate": validate, "warm": warm}[action]()
