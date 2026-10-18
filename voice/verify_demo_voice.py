"""Check the configured synthetic voice through authenticated local ASR/TTS APIs."""
import argparse
import io
import json
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen
from uuid import uuid4


def word_error_rate(reference, transcript):
    def words(text):
        return re.findall(r"\w+", text.casefold(), flags=re.UNICODE)
    expected, actual = words(reference), words(transcript)
    previous = list(range(len(actual) + 1))
    for i, left in enumerate(expected, 1):
        current = [i]
        for j, right in enumerate(actual, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (left != right)))
        previous = current
    return round(previous[-1] / max(len(expected), 1), 3)


def main():
    import soundfile as sf
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=r"E:\SCC-Voice\voices\scc-demo")
    parser.add_argument("--token-file", default=r"C:\Projects\strix-alloy-clean\server\.local\servicenow-api-token.txt")
    args = parser.parse_args()
    folder = Path(args.profile)
    token = Path(args.token_file).read_text(encoding="utf-8-sig").strip()
    if not token:
        raise SystemExit("Empty audio API token")
    headers = {"Authorization": "Bearer " + token}

    def call(url, data=None, content_type=None):
        request_headers = dict(headers)
        if content_type:
            request_headers["Content-Type"] = content_type
        started = time.perf_counter()
        with urlopen(Request(url, data=data, headers=request_headers), timeout=300) as response:
            result = response.read()
        return result, round(time.perf_counter() - started, 3)

    health = {}
    for name, port in (("asr", 8851), ("tts", 8852)):
        data, _ = call("http://127.0.0.1:%s/health" % port)
        health[name] = json.loads(data)
    if health["tts"].get("voice") != "SCC Demo":
        raise SystemExit("The synthetic SCC Demo voice is not selected")
    text = "Wie heißt Ihr neuer Mitarbeiter? Ich plane die Lieferung nach Hamburg."
    body = json.dumps({"model": "qwen3-tts-0.6b", "voice": "scc-demo",
                       "input": text, "response_format": "wav"}).encode()
    audio, tts_seconds = call("http://127.0.0.1:8852/v1/audio/speech", body, "application/json")
    (folder / "service-check.wav").write_bytes(audio)
    info = sf.info(io.BytesIO(audio))
    if info.frames <= 0 or info.samplerate != 24000:
        raise SystemExit("Unexpected TTS waveform")
    boundary = "scc-" + uuid4().hex
    multipart = (
        '--%s\r\nContent-Disposition: form-data; name="model"\r\n\r\nqwen3-asr-0.6b\r\n'
        '--%s\r\nContent-Disposition: form-data; name="language"\r\n\r\nde\r\n'
        '--%s\r\nContent-Disposition: form-data; name="file"; filename="check.wav"\r\n'
        'Content-Type: audio/wav\r\n\r\n' % (boundary, boundary, boundary)
    ).encode() + audio + ('\r\n--%s--\r\n' % boundary).encode()
    result, asr_seconds = call("http://127.0.0.1:8851/v1/audio/transcriptions", multipart,
                               "multipart/form-data; boundary=" + boundary)
    transcript = json.loads(result)["text"]
    wer = word_error_rate(text, transcript)
    report = {"ok": wer <= 0.25, "health": health, "expected": text,
              "transcript": transcript, "word_error_rate": wer,
              "tts_seconds": tts_seconds, "asr_seconds": asr_seconds,
              "audio_seconds": round(info.frames / info.samplerate, 3),
              "sample_rate": info.samplerate, "audio_bytes": len(audio)}
    (folder / "service-validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
