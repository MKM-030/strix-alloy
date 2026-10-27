"""Pipecat text/context pipeline behind SCC's existing native media boundary.

The injected OmniConversation remains the sole model protocol receive owner.
Pipecat owns context-frame processing, async generation tasks, sentence
aggregation and interruption flushing. NativeDuplex remains the authority for
business submission, semantic release and every playback generation check.
Queued candidate text is never added to assistant history as heard speech.
"""
import asyncio
from dataclasses import dataclass, field, replace
import json
import time

from omni_conversation import CandidateReply, KEY, SCOPE, _snapshot
from pipecat.frames.frames import (
    AggregatedTextFrame, ControlFrame, InterruptionFrame, LLMFullResponseEndFrame,
    LLMFullResponseStartFrame, LLMMessagesUpdateFrame, LLMTextFrame, StartFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMUserAggregator, LLMUserAggregatorParams,
)
from pipecat.processors.aggregators.llm_text_processor import LLMTextProcessor
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.turns.user_turn_strategies import ExternalUserTurnStrategies
from pipecat.utils.text.simple_text_aggregator import SimpleTextAggregator
from pipecat.workers.runner import WorkerRunner


@dataclass
class _Operation:
    text: str
    key: dict
    callback: object
    done: asyncio.Future
    submitted_at: float = field(default_factory=time.monotonic)
    identity: object = None
    first_at: float | None = None
    callback_failed: bool = False


@dataclass
class _RequestFrame(ControlFrame):
    operation: _Operation


@dataclass
class _BindingFrame(ControlFrame):
    operation: _Operation


@dataclass
class _FinishedFrame(ControlFrame):
    operation: _Operation
    candidate: CandidateReply
    interruptible: bool = field(default=False, init=False)


@dataclass
class _ContextAppliedFrame(ControlFrame):
    applied: asyncio.Future
    interruptible: bool = field(default=False, init=False)


def _context_snapshot(context):
    # The framework's context is the input source for model requests. Restore
    # the tuple-shaped application schema after its JSON representation.
    value = json.loads(context.get_messages()[1]['content'])
    for name in ('raw_inputs', 'public_findings', 'capability_limits', 'required_children'):
        if name in value:
            value[name] = tuple(value[name])
    for child in value.get('required_children', ()):
        child['evidence_ids'] = tuple(child['evidence_ids'])
    return value


class _OmniModelProcessor(FrameProcessor):
    """Thin service adapter; framework tasks keep observations nonblocking."""
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.generation = None

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, _RequestFrame):
            snapshot = _context_snapshot(self.owner.context)
            self.generation = self.create_task(self._generate(frame.operation, snapshot))
        elif isinstance(frame, _ContextAppliedFrame):
            if not frame.applied.done():
                frame.applied.set_result(True)
        else:
            await self.push_frame(frame, direction)

    async def _generate(self, operation, snapshot):
        async def delta(text, identity):
            if not self.owner._valid(operation, identity):
                return
            if operation.identity is None:
                operation.identity = identity
                operation.first_at = time.monotonic()
                await self.push_frame(_BindingFrame(operation))
            elif identity != operation.identity:
                raise ValueError('Model identity changed during a response')
            await self.push_frame(LLMTextFrame(text))
        try:
            await self.push_frame(LLMFullResponseStartFrame())
            if tuple(snapshot[name] for name in SCOPE) != tuple(operation.key[name] for name in SCOPE):
                result = CandidateReply(cancelled=True, failure='superseded')
            else:
                result = await self.owner.conversation.respond(
                    operation.text, snapshot, operation.key, on_delta=delta)
            if result.failure is None and not result.cancelled:
                await self.push_frame(LLMFullResponseEndFrame())
            else:
                await self.push_frame(InterruptionFrame())
            await self.push_frame(_FinishedFrame(operation, result))
        except asyncio.CancelledError:
            if not operation.done.done():
                operation.done.set_result(CandidateReply(cancelled=True, failure='superseded'))
            raise
        except Exception:
            await self.push_frame(InterruptionFrame())
            await self.push_frame(_FinishedFrame(operation, CandidateReply(failure='unavailable')))

    async def cleanup(self):
        if self.generation is not None and not self.generation.done():
            await self.cancel_task(self.generation)
        await super().cleanup()


class _CandidateSink(FrameProcessor):
    def __init__(self, owner):
        super().__init__()
        self.owner, self.operation = owner, None

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            self.owner._started.set()
        elif isinstance(frame, _BindingFrame):
            self.operation = frame.operation
        elif isinstance(frame, AggregatedTextFrame):
            op = self.operation
            if op is not None and self.owner._valid(op, op.identity) and op.callback is not None:
                candidate = CandidateReply(text=frame.text.strip(), identity=op.identity,
                    authoritative_whisper_text=op.text, submitted_at=op.submitted_at,
                    first_valid_text_at=op.first_at)
                if candidate.text:
                    try:
                        await op.callback(candidate)
                    except Exception:
                        op.callback_failed = True
        elif isinstance(frame, InterruptionFrame):
            self.operation = None
        elif isinstance(frame, _FinishedFrame):
            op, candidate = frame.operation, frame.candidate
            if op.callback_failed:
                candidate = replace(candidate, text='', failure='output_callback_failed')
            elif candidate.failure is None and not self.owner._valid(op, candidate.identity):
                candidate = replace(candidate, text='', cancelled=True, failure='superseded')
            if not op.done.done():
                op.done.set_result(candidate)
            self.operation = None
        await self.push_frame(frame, direction)


class PipecatDialogue:
    """One selected, in-process Pipecat pipeline per native call.

    ``on_sentence(CandidateReply)`` receives each sentence once while the
    model continues. The returned full CandidateReply is completion metadata;
    callers must not enqueue it again. ``observe`` updates sanitized context
    without starting a model turn or any business operation. Native must still
    check observation/revision/epoch identity at release and playback.
    """
    sentence_streaming = True

    def __init__(self, conversation):
        self.conversation = conversation
        self.context = LLMContext()
        self._started = asyncio.Event()
        self._scope = self._operation = self._worker = self._runner = self._run = None
        self._call_id = self._seed = None
        self._closed = False

    @property
    def output_epoch(self):
        return self.conversation.output_epoch

    async def start(self, call_id, output_epoch, seed_rules):
        if self._runner is not None or self._closed:
            raise ValueError('Dialogue already started or closed')
        try:
            ref = await self.conversation.start(call_id, output_epoch, seed_rules)
            self._call_id, self._seed = call_id, seed_rules
            user = LLMUserAggregator(self.context, params=LLMUserAggregatorParams(
                user_turn_strategies=ExternalUserTurnStrategies(enable_interruptions=False),
                audio_idle_timeout=0, user_idle_timeout=0, empty_user_turn=None))
            self._model = _OmniModelProcessor(self)
            pipeline = Pipeline([user, self._model,
                LLMTextProcessor(text_aggregator=SimpleTextAggregator(language='de')),
                _CandidateSink(self)])
            self._worker = PipelineWorker(pipeline, enable_rtvi=False, enable_turn_tracking=False,
                idle_timeout_secs=None, cancel_timeout_secs=1, setup_timeout_secs=5,
                start_timeout_secs=5, params=PipelineParams(send_initial_empty_metrics=False))
            self._runner = WorkerRunner(handle_sigint=False, handle_sigterm=False)
            await self._runner.add_workers(self._worker)
            self._run = asyncio.create_task(self._runner.run())
            await asyncio.wait_for(self._started.wait(), 5)
        except BaseException:
            await self.close()
            raise
        return ref

    def _prepare(self, snapshot, key):
        if (self._closed or self._worker is None or type(key) is not dict
                or key.keys() != set(KEY) or key.get('call_id') != self._call_id
                or type(key.get('output_epoch')) is not int or key['output_epoch'] != self.output_epoch
                or type(key.get('request_id')) is not str or not 0 < len(key['request_id']) <= 128):
            raise ValueError('Invalid dialogue context')
        encoded = _snapshot(snapshot, key)
        scope = tuple(key[name] for name in SCOPE)
        if self._scope is not None and (scope[:2] != self._scope[:2]
                or any(new < old for new, old in zip(scope[2:], self._scope[2:]))):
            raise ValueError('Regressing dialogue context')
        return encoded, scope

    def _messages(self, encoded, text=None):
        if text is None:
            text = next((m['content'] for m in reversed(self.context.get_messages())
                         if m['role'] == 'user'), None)
        messages = [dict(role='system', content=self._seed), dict(role='system', content=encoded)]
        if text is not None:
            messages.append(dict(role='user', content=text))
        return messages

    async def observe(self, trusted_snapshot, response_key):
        try:
            encoded, scope = self._prepare(trusted_snapshot, response_key)
        except Exception:
            # The shared snapshot validator raises the application's ProtocolError.
            return False
        self._scope = scope
        applied = asyncio.get_running_loop().create_future()
        await self._worker.queue_frames([
            LLMMessagesUpdateFrame(self._messages(encoded), run_llm=False),
            _ContextAppliedFrame(applied)])
        try:
            return await asyncio.wait_for(applied, 2)
        except TimeoutError:
            return False

    def _valid(self, operation, identity):
        return (not self._closed and not operation.callback_failed
                and self._operation is operation and identity is not None
                and self._scope == tuple(operation.key[name] for name in SCOPE)
                and tuple(getattr(identity, name, None) for name in KEY)
                    == tuple(operation.key[name] for name in KEY)
                and self.conversation.is_stream_current(identity))

    def is_current(self, identity):
        return (not self._closed and identity is not None and self._scope is not None
                and tuple(getattr(identity, name, None) for name in SCOPE) == self._scope
                and self.conversation.is_stream_current(identity))

    async def respond(self, final_asr_text, trusted_snapshot, response_key, *, on_sentence=None):
        if self._operation is not None:
            return CandidateReply(failure='busy')
        try:
            encoded, scope = self._prepare(trusted_snapshot, response_key)
            if type(final_asr_text) is not str or not 0 < len(final_asr_text) <= 4000:
                raise ValueError('Invalid final ASR text')
            if on_sentence is not None and not callable(on_sentence):
                raise ValueError('Invalid output callback')
        except Exception:
            return CandidateReply(failure='invalid_input')
        self._scope = scope
        op = _Operation(final_asr_text, dict(response_key), on_sentence,
                        asyncio.get_running_loop().create_future())
        self._operation = op
        try:
            await self._worker.queue_frames([
                LLMMessagesUpdateFrame(self._messages(encoded, final_asr_text), run_llm=False),
                _RequestFrame(op)])
            return await asyncio.wait_for(asyncio.shield(op.done), 35)
        except (asyncio.CancelledError, TimeoutError):
            # A cancelled request may not leave a generation feeding the next
            # turn. Cancelling the owned model task also closes its protocol
            # session through OmniConversation's existing abort path.
            if self._model.generation is not None and not self._model.generation.done():
                await self._model.cancel_task(self._model.generation)
            await self._worker.queue_frame(InterruptionFrame())
            raise
        finally:
            self._operation = None

    def invalidate(self, new_epoch, reason):
        # Source epoch changes synchronously before any pipeline await.
        drain = self.conversation.invalidate(new_epoch, reason)
        async def invalidate_pipeline():
            if self._worker is not None and not self._closed:
                await self._worker.queue_frame(InterruptionFrame())
            await drain
        return invalidate_pipeline()

    async def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            await self.conversation.close()
        finally:
            if self._runner is not None:
                await self._runner.cancel()
            if self._run is not None:
                try:
                    await asyncio.wait_for(self._run, 3)
                except (asyncio.CancelledError, TimeoutError):
                    self._run.cancel()
                    await asyncio.gather(self._run, return_exceptions=True)
