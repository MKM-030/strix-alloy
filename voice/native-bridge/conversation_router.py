"""Scope-bound, bounded dialogue proposals; no business execution authority."""

import asyncio
import http.client
import ipaddress
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from business_tasks import Agent, StoreInvalid, bounded_identifier
from route_proposal import ProposalContract, RouteProposal, PRODUCTION_SYSTEM_PROMPT
from routing_policy import RoutingDecision, ContextBudgetExceeded, policy_snapshot, clarify, deterministic, evaluate


INTENTS = frozenset({"status_query", "clarification", "amend_task", "new_task",
                     "stop_speaking", "cancel_task", "uncertain", "continue_task"})
_MAX_REQUEST_BYTES = 16384
_MAX_RESPONSE_BYTES = 8192
_MAX_ROUTE_BYTES = 2048


@dataclass(frozen=True)
class Route:
    intent: str
    task_id: str = ""
    agent_alias: str = ""
    reply: str = ""


@dataclass
class RoutingContext:
    scope_id: str
    tasks: list[dict]
    focus_task_id: str = ""
    last_question: str = ""
    agents: list[Agent] = field(default_factory=list)
    question_task_id: str = ""
    question_version: int | None = None
    workflow_task_id: str = ""
    question_id: str = ""
    question_source: str = ""

    def __post_init__(self):
        bounded_identifier(self.scope_id)
        bounded_identifier(self.focus_task_id, optional=True)
        if not isinstance(self.tasks, list) or len(self.tasks) > 8:
            raise StoreInvalid("invalid routing tasks")
        ids = set()
        for task in self.tasks:
            if not isinstance(task, dict) or task.get("scope_id") != self.scope_id:
                raise StoreInvalid("invalid routing task scope")
            task_id = bounded_identifier(task.get("task_id"))
            if task_id in ids:
                raise StoreInvalid("duplicate routing task")
            ids.add(task_id)
            for key in ('open_question', 'retained_text', 'previous_question'):
                value = task.get(key)
                if value is not None and (not isinstance(value, str) or len(value) > 4000):
                    raise StoreInvalid('invalid routing text')
            for key in ('context_version', 'previous_question_version', 'previous_operation_version', 'latest_operation_version'):
                value = task.get(key)
                if value is not None and (type(value) is not int or value < 0):
                    raise StoreInvalid('invalid routing version')
            for key in ('previous_question_id', 'previous_operation_id', 'latest_operation_id'):
                if key in task:
                    bounded_identifier(task[key])
        if self.focus_task_id and self.focus_task_id not in ids:
            raise StoreInvalid("invalid focus task")
        bounded_identifier(self.question_task_id, optional=True)
        if self.question_task_id and self.question_task_id not in ids:
            raise StoreInvalid('invalid question task')
        if not isinstance(self.last_question, str) or len(self.last_question) > 4000:
            raise StoreInvalid("invalid last question")
        bounded_identifier(self.workflow_task_id, optional=True)
        if self.workflow_task_id and self.workflow_task_id not in ids:
            raise StoreInvalid('invalid workflow task')
        if self.question_version is not None and (type(self.question_version) is not int or self.question_version < 0):
            raise StoreInvalid('invalid question version')
        if not isinstance(self.agents, list) or len(self.agents) > 16 or any(not isinstance(a, Agent) for a in self.agents):
            raise StoreInvalid("invalid routing agents")
        if len({a.alias for a in self.agents}) != len(self.agents):
            raise StoreInvalid("duplicate routing agent")

    def model_data(self):
        return policy_snapshot(self).model_data()


def _reject_duplicates(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("duplicate JSON key")
        output[key] = value
    return output


def _invalid_constant(value):
    raise ValueError("nonfinite JSON value")


def _strict_json(raw, max_bytes):
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not isinstance(raw, bytes) or len(raw) > max_bytes:
        raise ValueError("JSON too large")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates,
                           parse_constant=_invalid_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("invalid JSON") from error
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("nonfinite JSON value")
        if isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return value


class LoopbackConversationModel:
    """OpenAI-compatible classifier on a literal loopback IP, with bounded I/O."""

    def __init__(self, http, url, model, token_file, timeout_seconds=2.0):
        if http is not None:
            raise ValueError("custom conversation HTTP transports are not supported")
        parsed = urlsplit(url)
        try:
            host = ipaddress.ip_address(parsed.hostname or "")
        except ValueError:
            raise ValueError("conversation endpoint must be a literal loopback address") from None
        if parsed.scheme != "http" or not host.is_loopback or parsed.username or parsed.password or parsed.fragment or parsed.query:
            raise ValueError("conversation endpoint must be pinned loopback HTTP")
        if not parsed.port or parsed.port in (8840, 8841, 8823) or parsed.path != "/v1/chat/completions":
            raise ValueError("invalid conversation endpoint")
        if not isinstance(model, str) or not model or len(model) > 128:
            raise ValueError("invalid conversation model")
        if type(timeout_seconds) not in (float, int) or not 0 < timeout_seconds <= 2.0:
            raise ValueError("invalid conversation timeout")
        self.url = url
        self.host = str(host)
        self.port = parsed.port
        self.path = parsed.path + ("?" + parsed.query if parsed.query else "")
        self.model = model
        self.token_file = Path(token_file) if token_file else None
        self.timeout_seconds = float(timeout_seconds)

    @staticmethod
    def decode_route(raw):
        data = _strict_json(raw, _MAX_ROUTE_BYTES)
        RouteProposal.decode(data)
        return data

    def _request(self, payload):
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token_file:
            token = self.token_file.read_text(encoding="utf-8").strip()
            if not token or len(token) > 4096 or "\r" in token or "\n" in token:
                raise ValueError("invalid private conversation token")
            headers["Authorization"] = "Bearer " + token
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout_seconds)
        try:
            connection.request("POST", self.path, body=payload, headers=headers)
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError("conversation endpoint error")
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_RESPONSE_BYTES:
                raise ValueError("conversation response too large")
            return raw
        finally:
            connection.close()

    async def classify(self, text, context):
        snapshot = policy_snapshot(context)
        data = snapshot.model_data()
        request = {"model": self.model, "messages": [
            {"role": "system", "content": PRODUCTION_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"utterance": text, "context": data}, ensure_ascii=False)}],
            "temperature": 0, "max_tokens": 128,
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "route", "strict": True,
                "schema": ProposalContract(snapshot).schema()}}}
        payload = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(payload) > _MAX_REQUEST_BYTES:
            raise ContextBudgetExceeded("conversation request too large")
        raw = await asyncio.wait_for(asyncio.to_thread(self._request, payload), self.timeout_seconds)
        envelope = _strict_json(raw, _MAX_RESPONSE_BYTES)
        choices = envelope.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise ValueError("invalid conversation envelope")
        message = choices[0].get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ValueError("invalid conversation content")
        return self.decode_route(message["content"])


class ConversationRouter:
    def __init__(self, model=None):
        self.model = model

    async def decide(self, text: str, context: RoutingContext) -> RoutingDecision:
        if not isinstance(text, str) or len(text) > 4000 or not text.strip():
            return clarify(reason='schema')
        try:
            snapshot = policy_snapshot(context)
        except (StoreInvalid, ValueError, TypeError):
            return clarify(reason='schema')
        # Only matching uses stripped text. The coordinator retains the original.
        matching = text.strip()
        local = deterministic(snapshot, matching)
        if local is not None:
            return local
        if self.model is None:
            return clarify(snapshot, 'unavailable')
        try:
            snapshot.model_data()
        except (StoreInvalid, ValueError, TypeError):
            return clarify(snapshot, 'context_budget')
        try:
            contract = ProposalContract(snapshot)
            raw = await asyncio.wait_for(self.model.classify(matching, snapshot), timeout=2.0)
            proposal = contract.decode(raw)
            return evaluate(snapshot, matching, proposal)
        except TimeoutError:
            return clarify(snapshot, 'timeout')
        except ContextBudgetExceeded:
            return clarify(snapshot, 'context_budget')
        except (ValueError, OSError, StoreInvalid, KeyError, TypeError):
            return clarify(snapshot, 'schema')

    async def route(self, text: str, context: RoutingContext) -> Route:
        return (await self.decide(text, context)).route
