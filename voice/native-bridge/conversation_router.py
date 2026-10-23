"""Scope-bound, bounded dialogue proposals; no business execution authority."""

import asyncio
import ipaddress
import json
import math
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from urllib.parse import urlsplit

from conversation_admission import (AdmissionRequest, AdmissionUnavailable, PreparedChat, run_admitted_chat,
    _strict_json, _reject_duplicates, _invalid_constant, notify_terminal)

from business_tasks import Agent, StoreInvalid, bounded_identifier
from route_proposal import ProposalContract, RouteProposal, ProposalError, PRODUCTION_SYSTEM_PROMPT
from routing_policy import RoutingDecision, ProposalObservation, ContextBudgetExceeded, policy_snapshot, clarify, deterministic, evaluate_choice


INTENTS = frozenset({"status_query", "clarification", "amend_task", "new_task",
                     "stop_speaking", "cancel_task", "uncertain", "continue_task", "grounded_answer"})
_MAX_REQUEST_BYTES = 16384
_MAX_RESPONSE_BYTES = 8192
_MAX_ROUTE_BYTES = 64


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
    grounded_answers_enabled: bool = False

    def __post_init__(self):
        if type(self.grounded_answers_enabled) is not bool:
            raise StoreInvalid('invalid grounded context')
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
        if isinstance(raw, str):
            try: raw = raw.encode('utf-8')
            except UnicodeError:
                raise ProposalError('syntax_rejected', syntax=False, bounds=None) from None
        if not isinstance(raw, bytes) or len(raw) > _MAX_ROUTE_BYTES:
            raise ProposalError('bounds_rejected', bounds=False)
        try:
            # Parse independently of object/schema validation (valid arrays are
            # syntactically JSON, though never valid choices).
            data = json.loads(raw.decode('utf-8'), object_pairs_hook=_reject_duplicates,
                              parse_constant=_invalid_constant)
        except (UnicodeError, ValueError, RecursionError):
            raise ProposalError('syntax_rejected', syntax=False, bounds=True) from None
        RouteProposal.decode(data)
        return data

    def _observe_admission(self, snapshot):
        """Private immutable telemetry hook; no payload, socket, or send authority."""

    async def classify(self, text, context):
        request = AdmissionRequest(self.timeout_seconds)
        return (await self._run_request(request, text, context, prepared=False))[0]

    async def classify_prepared(self, text, contract):
        request = AdmissionRequest(self.timeout_seconds)
        return (await self._run_request(request, text, contract, prepared=True))[0]

    @staticmethod
    def _consume(future):
        if not future.cancelled(): future.exception()

    def _notify_terminal(self, request):
        notify_terminal(request, self._observe_admission)

    def _observe_bypass(self, reason):
        request = AdmissionRequest(self.timeout_seconds)
        request.update(stage='bypass', reason=reason, worker_outstanding=False)
        try:
            self._notify_terminal(request)
        except Exception:
            # Local delivery never waits for telemetry or its worker pool.
            pass

    async def _run_request(self, request, text, context, *, prepared):
        def prepare():
            if not isinstance(text, str) or len(text) > 4000 or not text.strip():
                raise ProposalError('bounds_rejected', bounds=False)
            contract = context if prepared else ProposalContract(context)
            data = contract.model_data()
            request = {"model": self.model, "messages": [
                {"role": "system", "content": PRODUCTION_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps({"utterance": text, "context": data}, ensure_ascii=False, separators=(",", ":"))}],
                "temperature": 0, "max_tokens": 24, "cache_prompt": False,
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": "route", "strict": True, "schema": contract.schema()}}}
            payload = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            catalog = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode('utf-8')
            return PreparedChat(payload, catalog, contract)
        return await run_admitted_chat(request, host=self.host, port=self.port,
            token_file=self.token_file, prepare=prepare,
            decode_content=lambda content, binding: (self.decode_route(content), binding),
            observe=self._observe_admission)


class ConversationRouter:
    def __init__(self, model=None):
        self.model = model

    async def decide(self, text: str, context: RoutingContext) -> RoutingDecision:
        started = time.perf_counter()
        decision = await self._decide(text, context)
        return replace(decision, route_elapsed_ms=(time.perf_counter() - started) * 1000)

    async def _decide(self, text, context):
        if not isinstance(text, str) or len(text) > 4000 or not text.strip():
            if isinstance(self.model, LoopbackConversationModel): self.model._observe_bypass('bounds')
            return clarify(reason='schema')
        try:
            snapshot = policy_snapshot(context)
        except (StoreInvalid, ValueError, TypeError):
            return clarify(reason='schema')
        # Only matching uses stripped text. The coordinator retains the original.
        matching = text.strip()
        local = deterministic(snapshot, matching)
        if local is not None:
            if isinstance(self.model, LoopbackConversationModel): self.model._observe_bypass('local')
            return local
        if self.model is None:
            return clarify(snapshot, 'unavailable')
        if isinstance(self.model, LoopbackConversationModel):
            # Build/serialize the contract in the request worker under its deadline.
            prepared = snapshot
        else:
            try:
                prepared = ProposalContract(snapshot)
                prepared.model_data()
            except (StoreInvalid, ValueError, TypeError):
                return clarify(snapshot, 'context_budget')
        started = time.perf_counter()
        decision = await self._model_decision(text, prepared)
        return replace(decision, model_elapsed_ms=(time.perf_counter() - started) * 1000)

    async def _model_decision(self, text, prepared):
        model = self.model
        loopback = isinstance(model, LoopbackConversationModel)
        snapshot = prepared if loopback else prepared.snapshot
        contract = None if loopback else prepared
        request = AdmissionRequest(model.timeout_seconds) if loopback else None
        started = time.perf_counter()
        try:
            call = (model._run_request(request, text, snapshot, prepared=False)
                    if loopback else model.classify(text, snapshot))
            pending = asyncio.create_task(call)
            try:
                done, _ = await asyncio.wait((pending,), timeout=2.0)
                if not done:
                    raise TimeoutError('conversation deadline')
                raw = pending.result()
                if loopback:
                    raw, contract = raw
            except asyncio.CancelledError:
                # The public owner must seal before its child can handle cancellation.
                if request is not None:
                    request.retire('cancelled')
                    model._notify_terminal(request)
                raise
            except TimeoutError:
                if request is not None: request.retire('timeout')
                raise
            finally:
                if not pending.done():
                    pending.cancel()
                    # Cancellation-resistant results are discarded, never rebound.
                    def consume(future):
                        if not future.cancelled(): future.exception()
                    pending.add_done_callback(consume)
            # Fake/in-process models have the same bounded dict contract.
            try: encoded = json.dumps(raw, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            except (TypeError, ValueError, UnicodeError):
                raise ProposalError('shape_rejected', shape=False) from None
            if len(encoded) > _MAX_ROUTE_BYTES:
                raise ProposalError('bounds_rejected', bounds=False)
            option = contract.decode(raw)
            if time.perf_counter() - started > 2.0:
                raise TimeoutError('conversation deadline')
            observed = ProposalObservation('decoded', option.candidate.intent, option.meaning, option.domain,
                                           True, True, True, True)
            return replace(evaluate_choice(snapshot, text, option), proposal=observed)
        except ProposalError as error:
            return replace(clarify(snapshot, 'schema'), proposal=ProposalObservation(error.stage, **error.facts))
        except TimeoutError:
            if request is not None:
                request.retire('timeout')
                model._notify_terminal(request)
            return replace(clarify(snapshot, 'timeout'), proposal=ProposalObservation('timeout'))
        except ContextBudgetExceeded:
            return replace(clarify(snapshot, 'context_budget'), proposal=ProposalObservation('context_budget'))
        except OSError:
            return replace(clarify(snapshot, 'unavailable'), proposal=ProposalObservation('unavailable'))
        except (ValueError, StoreInvalid, KeyError, TypeError):
            return replace(clarify(snapshot, 'schema'), proposal=ProposalObservation('schema_rejected'))

    async def route(self, text: str, context: RoutingContext) -> Route:
        return (await self.decide(text, context)).route
