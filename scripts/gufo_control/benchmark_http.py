"""One bounded loopback request with native metrics and sanitized wire evidence.

This transport performs no readiness polling, retries, tool execution, profile
admission, output-file writes, or workload correctness assessment.
"""

import base64
from dataclasses import dataclass
import json
import math
import threading
import time

from . import smoke_http


@dataclass(frozen=True)
class RequestLimits:
    max_prompt_tokens: int
    max_completion_tokens: int
    cache_policy: str = "cold"
    request_bytes: int = 262144

    def __post_init__(self):
        for name, maximum in (("max_prompt_tokens", 262144),
                              ("max_completion_tokens", 8192), ("request_bytes", 262144)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("invalid_" + name)
        if self.cache_policy not in ("cold", "allow"):
            raise ValueError("invalid_cache_policy")


def _parse_json_response(body, path):
    value = smoke_http._json_object(body)
    if "error" in value:
        raise smoke_http.SmokeError("json_server_error")
    choices = value.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise smoke_http.SmokeError("malformed_json_choices")
    choice = choices[0]
    if "index" in choice and (type(choice["index"]) is not int or choice["index"] != 0):
        raise smoke_http.SmokeError("malformed_json_choices")
    tools, models = {}, []
    content, reasoning = "", ""
    if path == "/v1/completions":
        content = choice.get("text")
    else:
        message = choice.get("message")
        if not isinstance(message, dict):
            raise smoke_http.SmokeError("malformed_json_message")
        content = message.get("content")
        content = "" if content is None else content
        reasoning = message.get("reasoning_content")
        reasoning = "" if reasoning is None else reasoning
        if "tool_calls" in message:
            smoke_http._merge_tool_calls(message["tool_calls"], tools, streaming=False)
    if not isinstance(content, str) or not isinstance(reasoning, str):
        raise smoke_http.SmokeError("malformed_json_content")
    if "model" in value:
        if not isinstance(value["model"], str) or not value["model"]:
            raise smoke_http.SmokeError("malformed_response_model")
        models.append(value["model"])
    if not isinstance(value.get("usage"), dict) or not isinstance(value.get("timings", {}), dict):
        raise smoke_http.SmokeError("missing_or_bad_usage_timings")
    return {"visible_answer": content, "reasoning_content": reasoning,
            "tool_calls": list(tools.values()), "finish_reason": choice.get("finish_reason"),
            "first_visible_content_ms": None, "first_tool_call_ms": None,
            "first_useful_output_ms": None, "observed_models": models,
            "usage": value["usage"], "timings": value.get("timings", {})}


def _record_evidence(result, raw, parts, key, *, wire=False):
    """Replace the ASCII secret before encoding; preserve receive boundaries."""
    secret = key.encode("ascii") if isinstance(key, str) and key and key.isascii() else b""

    def sanitize(data):
        clean = data.replace(secret, b"*" * len(secret)) if secret else data
        if clean != data:
            result["evidence_redacted"] = True
        return clean

    raw = sanitize(raw)
    result.update(raw_response=raw.decode("utf-8", "replace"),
                  raw_response_base64=base64.b64encode(raw).decode("ascii"),
                  raw_response_is_partial_wire=wire)
    joined = sanitize(b"".join(part for part, _ in parts))
    evidence, offset = [], 0
    for part, arrived in parts:
        clean = joined[offset:offset+len(part)]
        offset += len(part)
        evidence.append({"utf8": clean.decode("utf-8", "replace"),
                         "base64": base64.b64encode(clean).decode("ascii"),
                         "byte_count": len(clean), "arrived_monotonic": arrived})
    result["body_parts"] = evidence


def _rates(metrics, errors, *, pp1):
    for native, fallback, label in (("engine_prefill_ms", "engine_timing_prompt_ms", "prefill_ms"),
                                    ("engine_decode_ms", "engine_timing_predicted_ms", "decode_ms")):
        a, b = metrics.get(native), metrics.get(fallback)
        if a is not None and b is not None and a != b:
            errors.append(label + "_disagrees")
    proposed, accepted = metrics.get("draft_tokens"), metrics.get("draft_tokens_accepted")
    if proposed is not None and accepted is not None and accepted > proposed:
        errors.append("draft_acceptance_exceeds_proposed")

    def rate(count, duration):
        if errors or count is None or duration is None or duration <= 0:
            return None
        try:
            value = count * 1000 / duration
            return value if math.isfinite(value) else None
        except OverflowError:
            return None

    prefill = metrics.get("engine_prefill_ms")
    decode = metrics.get("engine_decode_ms")
    metrics.update(
        http_pp_tokens_per_second=rate(metrics.get("new_prefill_tokens"), metrics.get("http_duration_ms")) if pp1 else None,
        engine_pp_tokens_per_second=rate(metrics.get("new_prefill_tokens"), prefill if prefill is not None else metrics.get("engine_timing_prompt_ms")),
        engine_tg_tokens_per_second=rate(metrics.get("completion_tokens"), decode if decode is not None else metrics.get("engine_timing_predicted_ms")),
        mtp_acceptance=accepted/proposed if not errors and accepted is not None and proposed else None,
        common_window_decode_tokens_per_second=None)


def request_once(*, port: int, api_key: str, path: str, request: dict,
                 limits: RequestLimits, deadline: float,
                 cancel: threading.Event | None = None) -> dict:
    """Return a structured observation; KeyboardInterrupt/SystemExit propagate."""
    result = {"success": False, "error": None, "request": None,
              "endpoint": None, "path": path if isinstance(path, str) else None,
              "status": None, "response_headers": {}, "raw_response": "",
              "raw_response_base64": "", "raw_response_is_partial_wire": False,
              "body_parts": [], "evidence_redacted": False, "post_attempted": False,
              "submitted_monotonic": None, "completed_monotonic": None,
              "visible_answer": "", "reasoning_content": "", "tool_calls": [],
              "finish_reason": None, "truncated": None, "usage": None, "timings": None,
              "observed_models": [], "model_matches_request": None,
              "validation_errors": [], "unavailable_metrics": [],
              "metrics": {"http_duration_ms": None, "first_visible_content_ms": None,
                          "first_tool_call_ms": None, "first_useful_output_ms": None}}
    _rates(result["metrics"], [], pp1=False)
    try:
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("invalid_port")
        result["endpoint"] = f"http://127.0.0.1:{port}"
        if (not isinstance(api_key, str) or not api_key or len(api_key) > 256
                or not api_key.isascii() or any(ch.isspace() or ord(ch) < 33 or ord(ch) == 127 for ch in api_key)):
            raise ValueError("invalid_private_key")
        if path not in ("/v1/chat/completions", "/v1/completions"):
            raise ValueError("invalid_path")
        if not isinstance(limits, RequestLimits):
            raise ValueError("invalid_limits")
        limits.__post_init__()
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise ValueError("invalid_deadline")
        if cancel is not None and not isinstance(cancel, threading.Event):
            raise ValueError("invalid_cancel")
        cancel = cancel if cancel is not None else threading.Event()
        if not isinstance(request, dict):
            raise ValueError("invalid_request")
        if not isinstance(request.get("model"), str) or not request["model"].strip():
            raise ValueError("invalid_model")
        if type(request.get("max_tokens")) is not int or not 1 <= request["max_tokens"] <= limits.max_completion_tokens:
            raise ValueError("invalid_max_tokens")
        if type(request.get("stream")) is not bool:
            raise ValueError("invalid_stream")
        if path == "/v1/chat/completions" and not isinstance(request.get("messages"), list):
            raise ValueError("invalid_messages")
        if path == "/v1/completions" and not isinstance(request.get("prompt"), str):
            raise ValueError("invalid_prompt")
        body = json.dumps(request, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        result["request"] = json.loads(body)
        if len(body) > limits.request_bytes:
            raise smoke_http.SmokeError("request_body_limit")
        smoke_http._check(deadline, cancel)
        result["post_attempted"] = True
        result["submitted_monotonic"] = time.monotonic()
        status, headers, raw, submitted, completed, parts = smoke_http._exchange(
            "POST", path, body, api_key, deadline, cancel, host="127.0.0.1",
            port=port, request_limit=limits.request_bytes)
        result.update(status=status, response_headers=headers,
                      submitted_monotonic=submitted, completed_monotonic=completed)
        result["metrics"]["http_duration_ms"] = (completed-submitted)*1000
        _record_evidence(result, raw, parts, api_key)
        if status != 200:
            raise smoke_http.SmokeError(f"completion_http_{status}")
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if request["stream"]:
            if content_type != "text/event-stream":
                raise smoke_http.SmokeError("wrong_completion_content_type")
            parsed = smoke_http.parse_sse_response(parts, submitted)
        else:
            if content_type != "application/json":
                raise smoke_http.SmokeError("wrong_completion_content_type")
            parsed = _parse_json_response(raw, path)
        result.update(parsed)
        metrics, errors, unavailable = smoke_http._validate_usage(
            parsed["usage"], parsed["timings"], max_prompt_tokens=limits.max_prompt_tokens,
            max_completion_tokens=request["max_tokens"], cache_policy=limits.cache_policy)
        gufo = parsed["usage"].get("gufo", {})
        if isinstance(gufo, dict):
            for flag in ("cache_hit", "cache_disk_hit"):
                if flag in gufo and type(gufo[flag]) is not bool:
                    errors.append("invalid_usage.gufo." + flag)
        metrics.update(result["metrics"])
        for name in ("first_visible_content_ms", "first_tool_call_ms", "first_useful_output_ms"):
            metrics[name] = parsed[name]
        if parsed["finish_reason"] not in ("stop", "length", "tool_calls"):
            errors.append("invalid_finish_reason")
        else:
            result["truncated"] = parsed["finish_reason"] == "length"
        for tool in parsed["tool_calls"]:
            if not tool["function"]["name"]:
                errors.append("missing_tool_function_name")
        if parsed["finish_reason"] == "tool_calls" and not parsed["tool_calls"]:
            errors.append("missing_tool_calls")
        if parsed["observed_models"]:
            result["model_matches_request"] = all(model == request["model"] for model in parsed["observed_models"])
            if not result["model_matches_request"]:
                errors.append("response_model_mismatch")
        _rates(metrics, errors, pp1=request["max_tokens"] == 1 and metrics.get("completion_tokens") == 1)
        result.update(metrics=metrics, validation_errors=errors, unavailable_metrics=unavailable)
        if errors:
            raise smoke_http.SmokeError("validation_failed")
        result["success"] = True
    except smoke_http.SmokeError as exc:
        result["error"] = exc.code
        if exc.raw_response:
            result.update(status=getattr(exc, "status", None), response_headers=getattr(exc, "headers", {}))
            _record_evidence(result, exc.raw_response, getattr(exc, "body_parts", []), api_key, wire=True)
        if hasattr(exc, "submitted"):
            result["submitted_monotonic"] = exc.submitted
    except (ValueError, TypeError, UnicodeError, OverflowError) as exc:
        result["error"] = "invalid_request_" + type(exc).__name__
    except Exception as exc:
        result["error"] = "unexpected_" + type(exc).__name__
    finally:
        if result["completed_monotonic"] is None:
            result["completed_monotonic"] = time.monotonic()
        if result["submitted_monotonic"] is not None:
            result["metrics"]["http_duration_ms"] = (result["completed_monotonic"]-result["submitted_monotonic"])*1000
    if isinstance(api_key, str) and api_key:
        sanitized = smoke_http._redact(result, api_key)
        if sanitized != result:
            sanitized["evidence_redacted"] = True
        result = sanitized
    return result
