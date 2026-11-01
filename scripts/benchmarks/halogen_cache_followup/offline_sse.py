"""Pure offline Halogen 0.18.22 SSE accounting; never opens a connection or runs a model.

Callers provide byte chunks and receipt QPC ticks. Times describe completed SSE
event receipt, not token generation or isolated GPU phases. Artificial fixtures
and retained streams never become qualified hardware measurements in this module.
"""
from __future__ import annotations

import codecs
import copy
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from typing import Any, Sequence


class ProtocolError(ValueError):
    """The offline stream or frozen cohort is not valid for this experiment."""


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ProtocolError(name + " must be a strict integer >= " + str(minimum))
    return value


def _number(value: Any, name: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError(name + " must be a finite nonnegative number")
    try:
        valid = math.isfinite(value) and value >= 0
    except (OverflowError, ValueError):
        valid = False
    if not valid:
        raise ProtocolError(name + " must be a finite nonnegative number")
    return value


def _object(value: Any, name: str) -> dict:
    if not isinstance(value, dict):
        raise ProtocolError(name + " must be an object")
    return value


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _json_constant(value: str) -> None:
    raise ProtocolError("nonfinite JSON number: " + value)


@dataclass(frozen=True)
class ScopeCounters:
    rounds: int
    drafted: int
    accepted: int

    @classmethod
    def parse(cls, value: Any, name: str) -> ScopeCounters:
        data = _object(value, name)
        for key in ("rounds", "drafted", "accepted"):
            if key not in data:
                raise ProtocolError(name + "." + key + " is missing")
        result = cls(*(_integer(data[key], name + "." + key)
                       for key in ("rounds", "drafted", "accepted")))
        if result.accepted > result.drafted:
            raise ProtocolError(name + " accepted exceeds drafted")
        if result.rounds == 0 and result.drafted != 0:
            raise ProtocolError(name + " has drafts without rounds")
        return result

    def as_dict(self) -> dict:
        return {"rounds": self.rounds, "drafted": self.drafted, "accepted": self.accepted}


@dataclass(frozen=True)
class SpeculationLedger:
    rounds: int
    head: ScopeCounters
    lookup: ScopeCounters
    grammar: ScopeCounters

    @property
    def drafted(self) -> int:
        return self.head.drafted + self.lookup.drafted + self.grammar.drafted

    @property
    def accepted(self) -> int:
        return self.head.accepted + self.lookup.accepted + self.grammar.accepted

    @classmethod
    def parse(cls, timings: dict) -> SpeculationLedger:
        data = _object(timings.get("speculation"), "timings.speculation")
        if data.get("drafter") != "mtp":
            raise ProtocolError("the explicit native mtp speculation ledger is required")
        if "rounds" not in data:
            raise ProtocolError("speculation.rounds is missing")
        rounds = _integer(data["rounds"], "speculation.rounds")
        scopes = [ScopeCounters.parse(data.get(name), "speculation." + name)
                  for name in ("head", "lookup", "grammar")]
        result = cls(rounds, *scopes)
        if rounds != sum(scope.rounds for scope in scopes):
            raise ProtocolError("speculation round accounting drift")
        for key, expected in (("draft_n", result.drafted),
                              ("draft_n_accepted", result.accepted)):
            if key not in timings or _integer(timings[key], key) != expected:
                raise ProtocolError(key + " disagrees with the separate native scopes")
        return result

    def as_dict(self) -> dict:
        return {"drafter": "mtp", "rounds": self.rounds, "drafted": self.drafted,
                "accepted": self.accepted,
                "head": self.head.as_dict(), "lookup": self.lookup.as_dict(),
                "grammar": self.grammar.as_dict()}


@dataclass(frozen=True)
class CompletionObservation:
    evidence_kind: str
    response_id: str
    model: str
    created: int
    prompt_tokens: int
    cached_tokens: int
    processed_tokens: int
    output_tokens: int
    finish_reason: str
    content: str
    response_sha256: str
    first_content_seconds: float
    end_to_end_seconds: float
    native_phase_observations: dict
    speculation: SpeculationLedger

    def as_dict(self) -> dict:
        return {
            "evidence_kind": self.evidence_kind,
            "qualifies_hardware_measurement": False,
            "response_id": self.response_id, "model": self.model, "created": self.created,
            "prompt_tokens": self.prompt_tokens, "cached_tokens": self.cached_tokens,
            "processed_tokens": self.processed_tokens, "output_tokens": self.output_tokens,
            "finish_reason": self.finish_reason, "content": self.content,
            "response_sha256": self.response_sha256,
            "first_content_seconds": self.first_content_seconds,
            "end_to_end_seconds": self.end_to_end_seconds,
            "native_phase_rates_are_observations_only": True,
            "native_phase_observations": copy.deepcopy(self.native_phase_observations),
            "speculation": self.speculation.as_dict(),
        }


class OfflineChatStream:
    """Incremental UTF-8, LF/CRLF and multiline-data SSE parser.

    first_content_seconds starts at start_qpc and ends at the chunk that
    completes the first nonempty content event. Empty role frames do not count.
    A complete finish frame, separate include_usage frame and DONE are required.
    Positive actual output <= max_output_tokens with stop/length is accepted.
    """

    def __init__(self, *, start_qpc: int, qpc_frequency: int,
                 expected_prompt_tokens: int | None = None,
                 max_output_tokens: int = 128,
                 evidence_kind: str = "artificial-fixture") -> None:
        self.start_qpc = _integer(start_qpc, "start_qpc")
        self.qpc_frequency = _integer(qpc_frequency, "qpc_frequency", 1)
        self.max_output_tokens = _integer(max_output_tokens, "max_output_tokens", 1)
        self.expected_prompt_tokens = (None if expected_prompt_tokens is None else
                                       _integer(expected_prompt_tokens, "expected_prompt_tokens", 1))
        if evidence_kind not in ("artificial-fixture", "retained-stream"):
            raise ProtocolError("evidence_kind must label an artificial fixture or retained stream")
        self.evidence_kind = evidence_kind
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
        self._line_buffer = ""
        self._data_lines: list[str] = []
        self._last_qpc = self.start_qpc
        self._first_content_qpc: int | None = None
        self._done_qpc: int | None = None
        self._content: list[str] = []
        self._finish_reason: str | None = None
        self._timings: dict | None = None
        self._usage: dict | None = None
        self._identity: tuple[str, str, int] | None = None
        self._saw_initial_role = False
        self._closed = False
        self._failed = False
        self._result: CompletionObservation | None = None

    def feed(self, data: bytes, received_qpc: int) -> None:
        if self._closed or self._failed:
            raise ProtocolError("cannot feed a closed or failed offline stream")
        try:
            if not isinstance(data, bytes):
                raise ProtocolError("feed accepts bytes only")
            tick = _integer(received_qpc, "received_qpc")
            if tick < self._last_qpc:
                raise ProtocolError("QPC stamps must be monotone and not precede start_qpc")
            self._last_qpc = tick
            self._line_buffer += self._decoder.decode(data, final=False)
            while "\n" in self._line_buffer:
                line, self._line_buffer = self._line_buffer.split("\n", 1)
                if line.endswith("\r"):
                    line = line[:-1]
                if "\r" in line:
                    raise ProtocolError("bare CR is not supported; use LF or CRLF")
                self._line(line, tick)
        except UnicodeDecodeError as error:
            self._failed = True
            raise ProtocolError("invalid or truncated UTF-8") from error
        except ProtocolError:
            self._failed = True
            raise

    def _line(self, line: str, tick: int) -> None:
        if line == "":
            if self._data_lines:
                payload = "\n".join(self._data_lines)
                self._data_lines = []
                self._event(payload, tick)
            return
        if line.startswith(":"):
            return
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "data":
            self._data_lines.append(value)
        # Standard event/id/retry and unknown SSE fields do not alter data.

    def _event(self, payload: str, tick: int) -> None:
        if self._done_qpc is not None:
            raise ProtocolError("duplicate DONE or data event after DONE")
        if payload == "[DONE]":
            if self._finish_reason is None or self._usage is None:
                raise ProtocolError("DONE requires both final choice and final usage")
            self._done_qpc = tick
            return
        try:
            frame = json.loads(payload, object_pairs_hook=_json_pairs, parse_constant=_json_constant)
        except (json.JSONDecodeError, RecursionError) as error:
            raise ProtocolError("invalid JSON SSE data") from error
        frame = _object(frame, "SSE frame")
        if "error" in frame and frame["error"] is not None:
            raise ProtocolError("error frame prevents successful completion")
        response_id, model = frame.get("id"), frame.get("model")
        if not isinstance(response_id, str) or not response_id or not isinstance(model, str) or not model:
            raise ProtocolError("normal frames require nonempty id and model strings")
        created = _integer(frame.get("created"), "frame.created")
        if frame.get("object") != "chat.completion.chunk":
            raise ProtocolError("normal frames require the chat.completion.chunk object")
        identity = (response_id, model, created)
        if self._identity is None:
            self._identity = identity
        elif identity != self._identity:
            raise ProtocolError("response id/model/created identity drift across SSE frames")
        choices = frame.get("choices")
        if not isinstance(choices, list):
            raise ProtocolError("choices must be an explicit array")
        usage = frame.get("usage")
        if len(choices) == 0:
            if self._usage is not None:
                raise ProtocolError("duplicate final usage")
            if self._finish_reason is None:
                raise ProtocolError("usage arrived before the final choice")
            self._usage = copy.deepcopy(_object(usage, "final usage"))
            timings = _object(frame.get("timings"), "final usage timings")
            # Python equality treats True == 1 and 1.0 == 1. Terminal copies
            # must agree in JSON types too; otherwise an invalid count can hide.
            if json.dumps(timings, sort_keys=True, separators=(",", ":")) != json.dumps(
                    self._timings, sort_keys=True, separators=(",", ":")):
                raise ProtocolError("the two terminal timings copies disagree")
            return
        if len(choices) != 1:
            raise ProtocolError("exactly one choice is required")
        if self._finish_reason is not None or self._usage is not None:
            raise ProtocolError("choice data after final choice or final usage")
        if usage is not None:
            raise ProtocolError("usage must be a separate terminal frame")
        choice = _object(choices[0], "choice")
        if _integer(choice.get("index"), "choice.index") != 0:
            raise ProtocolError("choice.index must be zero")
        delta = _object(choice.get("delta"), "choice.delta")
        for key in ("reasoning_content", "reasoning", "tool_calls", "function_call"):
            if key in delta:
                raise ProtocolError("reasoning or tool deltas are outside the text-only cohort")
        if any(key not in ("content", "role") for key in delta):
            raise ProtocolError("unsupported non-text delta")
        if "role" in delta and delta["role"] != "assistant":
            raise ProtocolError("only assistant role deltas are allowed")
        content = delta.get("content", "")
        if not isinstance(content, str):
            raise ProtocolError("delta.content must be text")
        reason = choice.get("finish_reason")
        if not self._saw_initial_role:
            if delta != {"role": "assistant", "content": ""} or reason is not None or "timings" in frame:
                raise ProtocolError("missing initial empty assistant role frame")
            self._saw_initial_role = True
            return
        if "role" in delta:
            raise ProtocolError("duplicate or misplaced assistant role frame")
        if reason is not None:
            if reason not in ("stop", "length"):
                raise ProtocolError("finish_reason must be stop or length")
            if delta:
                raise ProtocolError("final choice must have an empty delta")
            self._finish_reason = reason
            self._timings = copy.deepcopy(_object(frame.get("timings"), "final timings"))
            return
        if "timings" in frame:
            raise ProtocolError("native timings must be terminal observations")
        if content:
            if self._first_content_qpc is None:
                self._first_content_qpc = tick
            self._content.append(content)

    def finish(self) -> CompletionObservation:
        if self._failed:
            raise ProtocolError("the offline stream has already failed")
        if self._result is not None:
            return self._result
        self._closed = True
        try:
            remainder = self._decoder.decode(b"", final=True)
            self._line_buffer += remainder
            if self._line_buffer or self._data_lines:
                raise ProtocolError("truncated SSE line or event")
            if self._done_qpc is None:
                raise ProtocolError("missing terminal DONE")
            self._result = self._account()
            return self._result
        except UnicodeDecodeError as error:
            self._failed = True
            raise ProtocolError("invalid or truncated UTF-8") from error
        except ProtocolError:
            self._failed = True
            raise

    def _account(self) -> CompletionObservation:
        if self._first_content_qpc is None:
            raise ProtocolError("no nonempty content event")
        usage = _object(self._usage, "usage")
        timings = _object(self._timings, "timings")
        required = ("prompt_n", "cache_n", "predicted_n", "prompt_ms", "predicted_ms",
                    "prompt_per_second", "predicted_per_second")
        for key in required:
            if key not in timings:
                raise ProtocolError("timings." + key + " is required")
        for key in timings:
            if key.startswith("max_tokens_clamped_"):
                raise ProtocolError("max_tokens was clamped")
        for key in ("disk_restore_n", "prefix_n"):
            if key in timings:
                value = _integer(timings[key], "timings." + key)
                if key == "disk_restore_n" and value != 0:
                    raise ProtocolError("disk restore is outside the frozen workload")
        if "disk_restore_ms" in timings and _number(timings["disk_restore_ms"], "disk_restore_ms") != 0:
            raise ProtocolError("disk restore time is outside the frozen workload")
        full = _integer(usage.get("prompt_tokens"), "usage.prompt_tokens", 1)
        output = _integer(usage.get("completion_tokens"), "usage.completion_tokens", 1)
        total = _integer(usage.get("total_tokens"), "usage.total_tokens")
        cached = _integer(timings["cache_n"], "timings.cache_n")
        processed = _integer(timings["prompt_n"], "timings.prompt_n")
        predicted = _integer(timings["predicted_n"], "timings.predicted_n")
        details = _object(usage.get("prompt_tokens_details", {}), "prompt_tokens_details")
        usage_cached = _integer(details.get("cached_tokens", 0), "cached_tokens")
        completion_details = _object(usage.get("completion_tokens_details", {}), "completion_tokens_details")
        if _integer(completion_details.get("reasoning_tokens", 0), "reasoning_tokens") != 0:
            raise ProtocolError("reasoning tokens are outside the Thinking-Off cohort")
        if _integer(completion_details.get("end_of_turn_kept", 0), "end_of_turn_kept") != 0:
            raise ProtocolError("kept reasoning/tool end markers are outside the text-only cohort")
        if "tool_call_from_reasoning" in completion_details:
            hidden_tool = completion_details["tool_call_from_reasoning"]
            if not isinstance(hidden_tool, bool) or hidden_tool:
                raise ProtocolError("tool_call_from_reasoning must be false when present")
        if (full != cached + processed or cached != usage_cached or predicted != output
                or total != full + output or output > self.max_output_tokens):
            raise ProtocolError("usage/cache/processed/output accounting drift")
        if self.expected_prompt_tokens is not None and full != self.expected_prompt_tokens:
            raise ProtocolError("actual full prompt disagrees with the externally frozen expected count")
        phases = {key: _number(timings[key], "timings." + key)
                  for key in ("prompt_ms", "predicted_ms", "prompt_per_second", "predicted_per_second")}
        ledger = SpeculationLedger.parse(timings)
        content = "".join(self._content)
        return CompletionObservation(
            evidence_kind=self.evidence_kind, response_id=self._identity[0],
            model=self._identity[1], created=self._identity[2],
            prompt_tokens=full, cached_tokens=cached,
            processed_tokens=processed, output_tokens=output, finish_reason=self._finish_reason,
            content=content, response_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            first_content_seconds=(self._first_content_qpc-self.start_qpc)/self.qpc_frequency,
            end_to_end_seconds=(self._done_qpc-self.start_qpc)/self.qpc_frequency,
            native_phase_observations=phases, speculation=ledger,
        )


@dataclass(frozen=True)
class FollowupPair:
    session_id: str
    warmup: bool
    turn1: CompletionObservation
    turn2: CompletionObservation


def _distribution(values: list[float]) -> dict:
    return {"values_seconds": values, "mean_seconds": statistics.fmean(values),
            "median_seconds": statistics.median(values), "min_seconds": min(values),
            "max_seconds": max(values)}


def _pooled_scope(observations: list[CompletionObservation], name: str) -> dict:
    accepted = sum(getattr(item.speculation, name).accepted for item in observations)
    drafted = sum(getattr(item.speculation, name).drafted for item in observations)
    return {"accepted": accepted, "drafted": drafted,
            "ratio": accepted/drafted if drafted else None}


def _turn_summary(observations: list[CompletionObservation]) -> dict:
    return {
        "first_content_latency": _distribution([x.first_content_seconds for x in observations]),
        "end_to_end_latency": _distribution([x.end_to_end_seconds for x in observations]),
        "actual_full_input_tokens": [x.prompt_tokens for x in observations],
        "cached_tokens": [x.cached_tokens for x in observations],
        "actual_processed_tokens": [x.processed_tokens for x in observations],
        "actual_output_tokens": [x.output_tokens for x in observations],
        "finish_reasons": [x.finish_reason for x in observations],
        "response_sha256": [x.response_sha256 for x in observations],
        "response_ids": [x.response_id for x in observations],
        "models": [x.model for x in observations],
        "created": [x.created for x in observations],
        "head_acceptance": _pooled_scope(observations, "head"),
        "lookup_acceptance": _pooled_scope(observations, "lookup"),
        "grammar_acceptance": _pooled_scope(observations, "grammar"),
        "native_phase_observations": [copy.deepcopy(x.native_phase_observations) for x in observations],
        "native_phase_rates_are_observations_only": True,
    }


def summarize_followups(pairs: Sequence[FollowupPair], *, cache_mode: str) -> dict:
    """Require one excluded warmup pair plus three complete offline pairs.

    This provides descriptive offline accounting only. Matching workload/profile/
    run identities, inter-arm output checks, real cache isolation, memory guards,
    and any hardware qualification remain outside this network-free module.
    """
    if cache_mode not in ("Off", "Flexible"):
        raise ProtocolError("cache_mode must be Off or Flexible")
    if len(pairs) != 4:
        raise ProtocolError("one warmup plus three complete pairs are required")
    seen = set()
    evidence_kinds = set()
    for index, pair in enumerate(pairs):
        if not isinstance(pair, FollowupPair):
            raise ProtocolError("every item must be a FollowupPair")
        if (not isinstance(pair.session_id, str) or not pair.session_id
                or pair.session_id in seen):
            raise ProtocolError("session IDs must be nonempty and distinct")
        seen.add(pair.session_id)
        if not isinstance(pair.warmup, bool) or pair.warmup != (index == 0):
            raise ProtocolError("only the first pair must be the excluded warmup")
        for observation in (pair.turn1, pair.turn2):
            if not isinstance(observation, CompletionObservation):
                raise ProtocolError("both turns must be completed offline observations")
            evidence_kinds.add(observation.evidence_kind)
        if pair.turn1.cached_tokens != 0:
            raise ProtocolError("turn1 was not cold: cache_n is nonzero")
        if pair.turn2.processed_tokens <= 0:
            raise ProtocolError("turn2 must process positive new tokens")
        if cache_mode == "Flexible" and pair.turn2.cached_tokens <= 0:
            raise ProtocolError("Flexible turn2 did not exhibit an actual cache hit")
        if cache_mode == "Off" and pair.turn2.cached_tokens != 0:
            raise ProtocolError("CacheOff turn2 unexpectedly reused input")
    if len(evidence_kinds) != 1:
        raise ProtocolError("cannot mix artificial and retained evidence kinds")
    warmup, measured = pairs[0], pairs[1:]
    return {
        "evidence_kind": next(iter(evidence_kinds)),
        "qualifies_hardware_measurement": False,
        "cache_mode": cache_mode, "warmup_pair_count": 1, "measured_pair_count": 3,
        "warmup_pairs": [{"session_id": warmup.session_id, "turn1": warmup.turn1.as_dict(),
                          "turn2": warmup.turn2.as_dict()}],
        "measured_session_ids": [pair.session_id for pair in measured],
        "turn1": _turn_summary([pair.turn1 for pair in measured]),
        "turn2": _turn_summary([pair.turn2 for pair in measured]),
        "promotion_requires_external_checks": [
            "frozen request/profile/runtime identities and observed memory reserves",
            "matched output hashes/counts and quality across cache arms",
            "interleaved conversation isolation sentinels",
        ],
    }
