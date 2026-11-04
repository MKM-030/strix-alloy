"""Independent Native conversation while the existing VA business turn waits.

The VA remains the only business executor. Caller input is kept verbatim and
submitted once, serially, after readiness. Optional local conversation never
consumes those original messages or invents a name-validation workflow.
"""
import asyncio
from collections import deque
from dataclasses import dataclass, replace
import importlib.util
import hashlib
import json
import logging
from startup_reason import startup_reason, caller_create_failure_notice
import math
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit
from types import SimpleNamespace

from conversation_repair import (conversational_snapshot,
                                 NATURAL_CONVERSATION_PROMPT, _polar, _pure_kind,
                                 _passive_signal)
from conversation_claims import unproven_storage_or_check_claim
from native_backend import BackendControlChanged, BackendEvent, BackendState, ControlBinding, ControlGate
from spoken_output import spoken_text
from servicenow_voice_context import (build_servicenow_voice_context,
                                     append_servicenow_context)

LOG = logging.getLogger('native-voice')


class BackendTurnUnavailable(RuntimeError):
    """The submitted turn has no usable completion; its outcome remains unknown."""


class BackendConversationEnded(BackendTurnUnavailable):
    """Observed terminal closure; no further input may use this conversation."""


def validate_conversation_url(value):
    if type(value) is not str:
        raise ValueError('Conversation URL must be a string')
    if not value:
        return ''
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == 'ws' and parsed.hostname == '127.0.0.1'
                 and parsed.port is not None and 1 <= parsed.port <= 65535
                 and parsed.username is None and parsed.password is None
                 and not parsed.query and not parsed.fragment and parsed.path in ('', '/'))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Conversation must use an explicit loopback WebSocket URL')
    return value


class DurationUpdates:
    """At most two quiet updates per VA request, after real PCM has drained."""
    def __init__(self, delay=8):
        self.delay = delay if type(delay) in (int, float) and math.isfinite(delay) and 0 < delay <= 3600 else 8
        self.start(0)

    def start(self, now):
        self.started = self.quiet_since = now
        self.audio_until = now
        self.count = 0
        self.last_sent = None

    @staticmethod
    def remaining_audio_seconds(queued_bytes):
        return max(0, queued_bytes) / 48000

    def due(self, now, *, queued_bytes=0, synthesizing=False, user_busy=False,
            output_pending=False, local_busy=False):
        remaining = self.remaining_audio_seconds(queued_bytes)
        if remaining or synthesizing or user_busy or output_pending or local_busy:
            self.audio_until = max(self.audio_until, now + remaining)
            self.quiet_since = max(now, self.audio_until)
            return False
        if self.count >= 2:
            return False
        # Actual silence starts after buffered PCM, not when synthesis ended.
        self.quiet_since = max(self.quiet_since, self.audio_until)
        spacing = self.delay if self.count == 0 else 15
        return now - self.quiet_since >= spacing

    def sent(self, now):
        self.count += 1
        self.last_sent = now
        self.quiet_since = now


def _progress_key(text):
    return re.sub(r'[\W_]+', ' ', text.casefold()).strip()


def _generic_processing_label(value):
    # Match complete generic statements only; a specific object or result stays public.
    filler = r'(?:(?:gerade|aktuell|derzeit|noch|jetzt|nun|weiterhin|weiter|erneut|nochmals) )*'
    subject = (r'(?:(?:ihr(?:e[nrms]?)?|dein(?:e[nrms]?)?|eur(?:e[nrms]?)?|'
               r'den|die|das|diese[nrms]?) )?'
               r'(?:input|eingaben?|anfragen?|anliegen|angaben|informationen)')
    active = (r'(?:ich (?:verarbeite|bearbeite|prüfe|pruefe|überprüfe|ueberpruefe)|'
              r'wir (?:verarbeiten|bearbeiten|prüfen|pruefen|überprüfen|ueberpruefen))')
    if re.fullmatch(rf'(?:{active} {filler}{subject}|{subject} (?:wird|werden) '
                    rf'{filler}(?:verarbeitet|bearbeitet|geprüft|geprueft|überprüft|ueberprueft))', value):
        return True
    return value in {
        'einen moment bitte', 'einen kurzen moment bitte', 'bitte warten sie',
        'bitte warten sie einen moment', 'bitte haben sie geduld',
        'ich arbeite daran', 'ich bin noch dran',
        'ich warte auf die rückmeldung', 'ich warte noch auf die rückmeldung',
    }


def _generic_processing_reply(text):
    # Suppress only whole generic-only notices, including a polite wait tail.
    # A concrete clause or a question preserves the complete public reply.
    parts = [part.strip() for part in re.split(r'[.!?]+(?:\s+|$)|[\r\n]+', text) if part.strip()]
    return bool(parts) and all(_generic_processing_label(_progress_key(part)) for part in parts)


def _forward_solicitation(text):
    # A preliminary planner declaration can solicit a later field without '?'.
    # Only the genuine input control may own that solicitation.
    value = _progress_key(text)
    return bool(re.search(r'\b(?:als nächstes|als nächsten schritt|benötige|benötigen|'
        r'brauche|brauchen|nennen sie|geben sie|teilen sie)\b', value)
        and re.search(r'\b(?:eintrittsdatum|eintritt|startdatum|datum|adresse|'
                      r'geburtsdatum|kostenstelle|abteilung|standort)\b', value))


def _polar_answer(text):
    # Pure acknowledgments can also answer a native confirmation. Mixed
    # corrections/requests remain original business text, never local consent.
    if _pure_kind(text) == 'backchannel':
        return True
    value = _progress_key(text)
    return bool(re.fullmatch(r'(?:ja(?: (?:genau(?: so)?|bitte|das stimmt|das ist richtig|'
        r'das ist korrekt))?|nein(?: danke)?|genau(?: so)?|richtig|korrekt|'
        r'ich bestätige(?: das)?|einverstanden)', value))


def _non_speech_annotation(text):
    # Only a complete, known acoustic annotation is non-speech. Marked names
    # and spoken complaints about noise remain ordinary caller text.
    match = re.fullmatch(r'\s*(?:\*{1,2}([^*\r\n]+)\*{1,2}|\[([^\]\r\n]+)\]|\(([^)\r\n]+)\))\s*', text)
    if match is None:
        return False
    label = _progress_key(next(value for value in match.groups() if value is not None))
    return label in {'föhnen', 'foehnen', 'föhn', 'foehn', 'husten', 'hustet', 'räuspern',
        'raeuspern', 'lachen', 'lacht', 'seufzen', 'atmen', 'atemgeräusch', 'rauschen',
        'hintergrundgeräusch', 'geräusch', 'geräusche', 'musik', 'stille', 'unverständlich',
        'unverstaendlich', 'no speech', 'blank audio', 'noise', 'silence'}


def _question_kind(text):
    """Optional conversation never decides whether raw input reaches ServiceNow."""
    return 'help' if isinstance(text, str) and text.strip() and len(text) <= 4000 else None


def _noncompletion_ordering(text, occurrence):
    """Recognize only clear noncompletion grammar around one bestellt predicate.

    This grants no result authority. Ambiguous/positive ordering stays held;
    actual ServiceNow results retain their separate native backend speech lane.
    """
    if len(text) > 1200 or re.search(r'''[:“”„"'«»–—]|\s-\s''', text):
        return False
    start, end = occurrence.span()
    left = next((m.end() for m in reversed(tuple(re.finditer(r'[.!?;\n]', text[:start])))), 0)
    following_boundary = re.search(r'[.!?;\n]', text[end:])
    right = end + following_boundary.start() if following_boundary else len(text)
    sentence = text[left:right].casefold()
    if re.search(r'\b(?:falls|wenn|sofern)\b', sentence):
        return False
    before, after = text[left:start].casefold(), text[end:right].casefold()
    separators = r',|\b(?:und|aber|sondern|doch|jedoch|dennoch)\b'
    boundaries = tuple(re.finditer(separators, before))
    head = before[boundaries[-1].end():] if boundaries else before
    tail = re.split(separators, after, maxsplit=1)[0]
    clause = head + 'bestellt' + tail
    # Keep exception/ellipsis tails: "nichts bestellt, außer einem Laptop"
    # and "nicht bestellt, sondern der Monitor" still imply a real order.
    if (re.search(r'\b(?:sondern|aber|jedoch|doch|hingegen|außer|ausser|ausgenommen|abgesehen)\b|'
                  r'\bbis auf\b|\bmit ausnahme\b|\bes sei denn\b', sentence)
            or re.search(r'\b(?:nur|bloß|bloss|lediglich|allein)\b|\bnicht\s+erst\b|'
                         r'\b(?:fast|beinahe|kaum)\s+(?:nichts|kein\w*)\b', clause)):
        return False
    negatives = re.findall(r'\b(?:nicht|nichts|kein(?:e|en|em|er|es|s)?|nie|niemals|'
                           r'keineswegs|keinesfalls|ohne)\b', clause)
    if len(negatives) > 1:
        return False
    modal = r'\b(?:kann|können|könnte|könnten|soll|sollen|sollte|sollten|muss|müssen|müsste|müssten|darf|dürfen|dürfte|dürften|würde|würden)\b'
    if re.match(r'\s+werden\b', tail) and (re.search(modal, head) or
            re.match(r'^\s*(?:wie|ob)\b', head) and re.search(modal, tail)):
        return True
    if re.match(r'^\s*wie\b', head) and re.match(r'\s+(?:wird|werden)\b', tail):
        return True
    if (len(negatives) != 1 or re.search(r'\bnicht\b.*\bdass\b', before)
            or re.match(r'^\s*(?:dass|ob)\b', head) or re.search(separators, after)):
        return False
    # Require a simple finite predicate, not approximate quantities or a
    # generic kein/adjunct phrase. This is deliberately no general parser.
    return bool(re.search(r'\b(?:wurde|wurden|wird|werden|ist|sind|war|waren|habe|haben|hat|hast|habt|hatte|hatten)\s+'
        r'(?:(?:noch|bisher|bislang|aktuell|derzeit)\s+)?(?:nicht|nichts)\s*$', head)
        and re.fullmatch(r'\s*(?:(?:worden|werden|wurde|wurden|wird|ist|sind|war|waren|habe|hat|haben|hatte|hatten)\s*)*', tail))


class _JsonSocket:
    def __init__(self, websocket, http):
        self.websocket, self.http = websocket, http

    async def send_json(self, event):
        await self.websocket.send_json(event)

    async def receive_json(self):
        from aiohttp import WSMsgType
        message = await self.websocket.receive()
        if message.type != WSMsgType.TEXT:
            raise RuntimeError('Conversation socket ended')
        return message.json()

    async def close(self):
        try:
            await self.websocket.close()
        finally:
            await self.http.close()


def _conversation_class():
    root = Path(__file__).resolve().parent.parent / 'optional-omni'
    for name in ('omni_protocol', 'omni_conversation'):
        path = root / (name + '.py')
        if name in sys.modules:
            if Path(sys.modules[name].__file__).resolve() != path.resolve():
                raise RuntimeError('Unexpected optional conversation module')
            continue
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    return sys.modules['omni_conversation'].OmniConversation


async def open_conversation(url, call_id, epoch, *, controller_url='', controller_token_file='', call_settings=None):
    from aiohttp import ClientSession, ClientTimeout
    if controller_url:
        conversation_class = _conversation_class()
        from local_llm_socket import LocalTextSocket
        from pipecat_dialogue import PipecatDialogue
        source = LocalTextSocket(controller_url, controller_token_file)
        adapter = conversation_class(lambda: source,
            deadlines={'handshake_seconds': 3, 'turn_seconds': 20, 'control_seconds': 1})
        dialogue = PipecatDialogue(adapter)
        dialogue.controller_transport = source
        try:
            await dialogue.start(call_id, epoch, NATURAL_CONVERSATION_PROMPT + '\n' +
                                 build_servicenow_voice_context(call_settings).system_prompt_fragment)
            LOG.info('Voice independent dialogue call=%s pipeline=pipecat controller_selected=true', call_id)
            return dialogue
        except BaseException:
            await dialogue.close()
            raise
    http = ClientSession(trust_env=False, timeout=ClientTimeout(total=12))
    try:
        async with asyncio.timeout(4):
            websocket = await http.ws_connect(validate_conversation_url(url), heartbeat=20, max_msg_size=65536)
        adapter = _conversation_class()(lambda: _JsonSocket(websocket, http),
            deadlines={'handshake_seconds': 3, 'turn_seconds': 10, 'control_seconds': 1})
        from pipecat_dialogue import PipecatDialogue
        dialogue = PipecatDialogue(adapter)
        await dialogue.start(call_id, epoch, NATURAL_CONVERSATION_PROMPT + '\n' +
                             build_servicenow_voice_context(call_settings).system_prompt_fragment)
        LOG.info('Voice independent dialogue call=%s pipeline=pipecat-1.13 sentence_streaming=true', call_id)
        return dialogue
    except BaseException:
        await http.close()
        raise


@dataclass(frozen=True)
class _PublicFinding:
    request: int
    task_revision: int
    sequence: int
    observed_at: float
    text: str


@dataclass(frozen=True)
class _BootstrapObservation:
    revision: int
    fingerprint: str
    exposed_question: tuple
    native_question: tuple | None


@dataclass(frozen=True)
class _PendingObservation:
    turn: tuple
    epoch: int
    fingerprint: str


@dataclass(frozen=True)
class _Output:
    text: str
    turn: object
    epoch: int
    task_revision: int
    observation_revision: int | _BootstrapObservation | _PendingObservation | None
    kind: str
    request: int | None = None
    identity: object = None
    expires_at: float | None = None
    question_binding: object = None
    control_binding: object = None
    backend_event: object = None
    fallback_snapshot: object = None


@dataclass(frozen=True)
class _SpeechLease:
    output: object
    generation: int
    epoch: int
    source_owner: object
    identity: object


class NativeDuplex:
    def __init__(self, call, *, context_publisher=None, context_reconciler=None,
                 conversation_factory=open_conversation, clock=time.monotonic):
        self.call, self.clock = call, clock
        self._control_gate = ControlGate()
        self._backend_receipts = {}
        self._backend_outputs = deque()
        self._backend_input_closed = False
        self._turn_speech_started = deque(maxlen=128)
        self._help_failure_seen = deque(maxlen=16)
        if conversation_factory is open_conversation:
            self._factory = lambda url, call_id, epoch: open_conversation(url, call_id, epoch,
                controller_url=getattr(call.config, 'conversation_http_url', ''),
                controller_token_file=getattr(call.config, 'conversation_token_file', ''), call_settings=call.call_settings)
        else:
            self._factory = conversation_factory
        self._context_publisher = context_publisher
        self._context_reconciler = context_reconciler
        self._context_snapshot = ''
        self._context_publish_revision = 0
        self._context_pending = None
        self._context_ready = asyncio.Event()
        self._context_full = False
        self._context_candidate = None
        self._context_covered = set()
        self.conversation = None
        self._dialogue_turn = None
        self._dialogue_observation_state = None
        self._dialogue_discard_count = 0
        self._model_failed = False
        self.epoch = 1
        self.task_revision = self.context_revision = 1
        self._request = 0
        self._reply_revision = 1
        self._public_findings = deque(maxlen=8)
        self._public_sequence = 0
        self._pending = deque()
        # Kept empty for the existing context/status interface. Early original
        # messages live only in _pending and are not parked as supplements.
        self._supplements = deque()
        self._submission_onsets = {}
        self._spoken_history = deque(maxlen=8)
        self._spoken_sequence = 0
        self._input_questions = {}
        self._raw = deque()
        self._outputs = deque()
        self._output_ready = asyncio.Event()
        self._local_questions = asyncio.Queue(maxsize=16)
        self._local_busy = False
        self._active_kind = None
        self._active_output = None
        self._speech = self._spoken_question = self._interrupted_speech = None
        self._passive_question_reasked = None
        self._synthesis_task = None
        self._backend = None
        self._bootstrap_state = 'ready'
        self._bootstrap_onset = None
        self._incoming_turn = None
        self._backend_unavailable = False
        self._bootstrap_failure_reason = ''
        self._automatic_progress_seen = set()
        self._workers = set()
        self._invalidations = set()
        self._observations = set()
        self._closed = False
        self._last_input_generation = call.playback.generation
        self.updates = DurationUpdates(getattr(call.call_settings, 'filler_delay_seconds', None))

    @property
    def busy(self):
        # Startup counts as owned activity for Native's inactivity timer, not
        # as proof that a caller's business request has been submitted.
        return (self.bootstrap_pending or self._backend is not None
                or bool(self._pending) and not self._backend_unavailable)

    @property
    def bootstrap_pending(self):
        return self._bootstrap_state == 'pending'

    @property
    def pending_count(self):
        return len(self._pending)

    @property
    def output_pending(self):
        return bool(self._outputs or self._backend_outputs)

    def _live(self):
        return not (self._closed or self.call.closed or self.call.closing or self.call.input_lost or self.call.failed)

    def _update_speech_cursor(self):
        state = self._speech
        if state is not None and not state['interrupted']:
            playback = self.call.playback
            state['accepted_samples'] = max(0, playback.accepted_samples - state['accepted_start'])
            state['emitted_samples'] = min(state['accepted_samples'],
                max(0, playback.emitted_samples - state['emitted_start']))
            snapshot = getattr(state.get('output'), 'fallback_snapshot', None)
            if (snapshot is not None and state['emitted_samples'] > 0
                    and snapshot not in self._help_failure_seen):
                self._help_failure_seen.append(snapshot)
            lease = state.get('lease')
            pending = (state['accepted_samples'] > state['emitted_samples']
                       or self._active_output is state.get('output') and self.call.synthesis_active)
            if lease is not None and pending and not self._active_speech_current(lease.output, lease.generation, lease):
                state['interrupted'] = True
                self._interrupt_backend_speech(state)
                playback.interrupt()
                if self._synthesis_task is not None:
                    self._synthesis_task.cancel()
                LOG.info('Voice independent output call=%s stage=hard_lease_revoked', self.call.call_id)
                return
            if (state.get('complete') and state['accepted_samples'] > 0
                    and state['emitted_samples'] == state['accepted_samples']
                    and not state.get('history_recorded')):
                if state.get('control_binding') is not None and not state['interrupted']:
                    self._control_gate.mark_emitted(state['control_binding'])
                event = state.get('backend_event')
                if event is not None:
                    record = self._backend_receipts.get(self._backend_key(event))
                    if record is not None:
                        record['state'] = 'fully_host_emitted'
                state['history_recorded'] = True
                if 0 < len(state['text']) <= 2000:
                    self._spoken_sequence += 1
                    self._spoken_history.append(dict(text=state['text'], sequence=self._spoken_sequence,
                                                     observed_at=self.clock()))
                    while sum(len(item['text']) for item in self._spoken_history) > 4000:
                        self._spoken_history.popleft()

    def _question_current(self, state):
        if state is not None and state.get('control_binding') is not None:
            return (self._live() and state['control_binding'] == self._control_gate.binding
                    and self._native_control_current(state['control_binding'])
                    and not self._control_gate.dispatched)
        if (state is None or not self._live() or self._pending
                or state['task_revision'] != self.task_revision):
            return False
        if state['source'] == 'greeting':
            return self._request == 0
        if self._bootstrap_state != 'ready':
            return False
        boundary = getattr(self.call.dialog, 'input_boundary', None)
        return (state['source'] in ('servicenow_input_control', 'local_clarification')
            and type(boundary) is dict
            and boundary.get('source') == 'servicenow_input_control'
            and boundary.get('businessRequestId') == state['binding']
            and boundary.get('label') == state.get('control_label', state['question']))

    def question_context(self):
        self._update_speech_cursor()
        state = self._spoken_question
        if not self._question_current(state) or not state['emitted_samples']:
            return '', '', False
        complete = (state['complete'] and not state['interrupted']
                    and state['emitted_samples'] == state['accepted_samples'])
        return state['question'], state['source'], complete

    def _input_question_snapshot(self):
        question, source, complete = self.question_context()
        state = self._spoken_question
        control = self._control_gate.binding
        if control is not None:
            heard = bool(complete and self._control_gate.heard and not self._control_gate.dispatched
                and state is not None and state.get('control_binding') == control and self._speech is state)
            return (control.label, 'servicenow_input_control', heard, control.business_request_id, control)
        return (question, source, complete, state['binding'] if question else '',
                state['task_revision'] if question else None)

    def _begin_speech(self, item):
        self._update_speech_cursor()
        inherited = getattr(item, 'question_binding', None)
        question = source = binding = ''
        control = getattr(item, 'control_binding', None)
        if control is not None and control == self._control_gate.binding:
            question, source, binding = control.label, 'servicenow_input_control', control.business_request_id
        elif self._question_current(inherited):
            question, source, binding = (inherited[key] for key in ('question', 'source', 'binding'))
        elif item.kind == 'greeting':
            match = re.search(r'(?:^|[.!])\s*([^.!?]+\?)\s*$', item.text)
            question, source = (match.group(1).strip() if match else ''), 'greeting'
        else:
            boundary = getattr(self.call.dialog, 'input_boundary', None)
            if (type(boundary) is dict and boundary.get('source') == 'servicenow_input_control'
                    and boundary.get('label') == item.text):
                question, source, binding = item.text, boundary['source'], boundary.get('businessRequestId', '')
        state = dict(text=item.text, kind=item.kind, question=question, source=source,
            binding=binding, task_revision=self.task_revision,
            control_binding=control,
            backend_event=getattr(item, 'backend_event', None),
            output=item, generation=self.call.playback.generation, lease=None,
            accepted_start=self.call.playback.accepted_samples,
            emitted_start=self.call.playback.emitted_samples, accepted_samples=0,
            emitted_samples=0, complete=False, interrupted=False)
        if inherited is not None and self._question_current(inherited):
            state['control_label'] = inherited.get('control_label', inherited['question'])
        if item.kind == 'confirmation_ack':
            state.update(output=item, generation=self.call.playback.generation, pcm_bytes=0)
        self._speech = state
        if question:
            self._spoken_question = state
        return state

    def _finish_speech(self, state, *, complete):
        self._update_speech_cursor()
        state['complete'] = complete and not state['interrupted']
        self._update_speech_cursor()

    def _buffered_confirmation_ack(self):
        state = self._speech
        playback = self.call.playback
        if (state is None or state['kind'] != 'confirmation_ack' or not state['complete']
                or state['interrupted'] or state.get('generation') != playback.generation
                or not self._valid(state['output'])):
            return None
        size = state['pcm_bytes']
        remaining = size - 2 * (playback.emitted_samples - state['emitted_start'])
        # Other accepted PCM, even in this generation, is not ours to discard.
        if (size <= 0 or remaining <= 0 or remaining != len(playback.data)
                or playback.accepted_samples != state['accepted_start'] + size // 2):
            return None
        return state

    def begin_greeting(self, text):
        return self._begin_speech(SimpleNamespace(text=text, kind='greeting', question_binding=None))

    def finish_greeting(self, state, *, complete):
        self._finish_speech(state, complete=complete)

    def speech_onset(self):
        # Observe only. The exact audio/ASR envelope carries this binding, so
        # two onsets in the same output generation cannot overwrite each other.
        return (self._input_question_snapshot(),
                bool(self.call.synthesis_active or self.call.playback.data))

    def interrupt(self, *, onset=None):
        onset = self._input_question_snapshot() if onset is None else onset
        self._update_speech_cursor()
        if self._speech is not None:
            state = self._speech
            if not state['complete'] or state['emitted_samples'] < state['accepted_samples']:
                state['interrupted'] = True
                self._interrupt_backend_speech(state)
                self._interrupted_speech = state
                LOG.info('Voice independent output call=%s stage=interrupted_pcm '
                         'emitted_samples=%d accepted_samples=%d device_playback_known=false',
                         self.call.call_id, state['emitted_samples'], state['accepted_samples'])
        self.epoch += 1
        self._outputs.clear()
        self.call.playback.interrupt()
        self._input_questions[self.call.playback.generation] = onset
        while len(self._input_questions) > 16:
            self._input_questions.pop(next(iter(self._input_questions)))
        if self._synthesis_task is not None:
            self._synthesis_task.cancel()
        if self.conversation is not None and not self._closed:
            try:
                self.epoch = max(self.epoch, self.conversation.output_epoch + 1)
                task = asyncio.create_task(self.conversation.invalidate(self.epoch, 'caller input'))
                self._invalidations.add(task)
                task.add_done_callback(self._invalidation_done)
            except Exception:
                self._model_failed = True

    def _invalidation_done(self, task):
        self._invalidations.discard(task)
        if not task.cancelled():
            task.exception()

    def _observe_raw(self, text):
        self._raw.append(text)
        # The full original remains in Native's caller transcript. The model
        # gets a bounded recent window without rewriting spellings into facts.
        while len(self._raw) > 8 or sum(len(item) for item in self._raw) > 4000:
            self._raw.popleft()

    def _enqueue(self, text, turn=None, *, kind='local', observation=None, request=None, identity=None,
                 expires_at=None, question_binding=None, control_binding=None, fallback_snapshot=None):
        if not text or not self._live():
            return
        if kind == 'backend' and _generic_processing_reply(text):
            # Actual callbacks remain in the transcript; only unsolicited filler
            # speech is held to the same rule as the timed processing notices.
            LOG.info('Voice independent output call=%s stage=generic_processing_suppressed request=%s',
                     self.call.call_id, self._request)
            return
        if len(self._outputs) >= 32:
            # Complete backend output takes precedence over optional updates.
            if kind != 'backend':
                return
            self._outputs = deque(item for item in self._outputs if item.kind == 'backend')
            if len(self._outputs) >= 32:
                raise RuntimeError('Public backend output queue full')
        self._outputs.append(_Output(text, turn, self.epoch, self.task_revision,
            observation, kind, request, identity, expires_at, question_binding, control_binding,
            fallback_snapshot=fallback_snapshot))
        self._output_ready.set()
        return True

    def _bootstrap_native_question(self):
        state = self._spoken_question
        if state is None or state['kind'] == 'conversation':
            return None
        return tuple(state.get(key) for key in
                     ('question', 'source', 'binding', 'control_label', 'task_revision'))

    def _bootstrap_context_fingerprint(self, exposed_question, native_question):
        question = self.question_context()[:2]
        spoken_question = self._bootstrap_native_question()
        # This response's own question/history may grow as its sentences drain.
        # Native public replies and control bindings below remain independent.
        if self._spoken_question is not None and self._spoken_question['kind'] == 'conversation':
            question = exposed_question
            spoken_question = native_question
        dialog = self.call.dialog
        context = dict(public_replies=tuple(getattr(dialog, 'public_replies', ())),
            current_question=getattr(dialog, 'current_question', ''), exposed_question=question,
            native_question=spoken_question,
            input_boundary=getattr(dialog, 'input_boundary', None),
            conversation_ended=bool(getattr(dialog, 'conversation_ended', False)),
            bootstrap_state=self._bootstrap_state, backend_unavailable=self._backend_unavailable,
            epoch=self.epoch, task_revision=self.task_revision, context_revision=self.context_revision,
            raw_inputs=tuple(self._raw), pending_count=len(self._pending),
            supplement_count=len(self._supplements), context_snapshot=self._context_snapshot)
        encoded = json.dumps(context, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        return hashlib.sha256(encoded.encode('utf-8')).hexdigest()

    def _observation_current(self, observation):
        if isinstance(observation, _PendingObservation):
            if self.bootstrap_pending or not self._pending or observation.epoch != self.epoch:
                return False
            try:
                key, snapshot, _ = self._dialogue_snapshot(observation.turn, observation.epoch,
                                                          bind_observation=False)
                return observation.fingerprint == self._dialogue_signature(snapshot, key)
            except (TypeError, ValueError):
                return False
        if isinstance(observation, _BootstrapObservation):
            # Progress is absent from a bootstrap prompt. Do not invalidate that
            # answer for loader-only revisions while every guarded fact is stable.
            try:
                return (self.bootstrap_pending and observation.fingerprint ==
                        self._bootstrap_context_fingerprint(observation.exposed_question,
                                                            observation.native_question))
            except (TypeError, ValueError):
                return False
        return observation is None or observation == getattr(self.call.dialog, 'observation_revision', 0)

    def _log_dialogue_discard(self, reason, boundary):
        if self._dialogue_discard_count < 8:
            self._dialogue_discard_count += 1
            LOG.info('Voice independent dialogue call=%s stage=discarded reason=%s at=%s',
                     self.call.call_id, reason, boundary)

    def _discard_output(self, item, boundary):
        if item.kind == 'conversation':
            reason = 'context_changed' if not self._observation_current(item.observation_revision) else 'output_superseded'
            self._log_dialogue_discard(reason, boundary)

    def _valid(self, item):
        if item.fallback_snapshot is not None and item.fallback_snapshot != self._help_failure_snapshot():
            return False
        if item.backend_event is not None:
            return self._backend_event_current(item.backend_event)
        if item.control_binding is not None:
            return (self._live() and item.epoch == self.epoch
                and self._native_control_current(item.control_binding)
                and item.control_binding == self._control_gate.binding and not self._control_gate.dispatched)
        return (self._live() and item.epoch == self.epoch and item.task_revision == self.task_revision
                and (item.question_binding is None or self._question_current(item.question_binding))
                and self._observation_current(item.observation_revision)
                and (item.request is None or item.request == self._request and self.busy)
                and (item.expires_at is None or self.clock() < item.expires_at and not self._pending)
                and (item.identity is None or self.conversation is not None and
                     self.conversation.is_current(item.identity)))

    def _active_speech_current(self, item, generation, lease):
        if lease is None:
            return self._valid(item) and generation == self.call.playback.generation
        if (not self._live() or lease.output is not item or lease.generation != generation
                or generation != self.call.playback.generation or lease.epoch != self.epoch):
            return False
        if item.backend_event is not None and not self._backend_event_current(item.backend_event):
            return False
        if item.control_binding is not None and (not self._native_control_current(item.control_binding)
                or item.control_binding != self._control_gate.binding or self._control_gate.dispatched):
            return False
        if lease.identity is not None:
            if self.conversation is not lease.source_owner:
                return False
            check = getattr(lease.source_owner, 'is_source_current', None)
            if not callable(check):
                check = getattr(lease.source_owner, 'is_current', None)
            return callable(check) and check(lease.identity) is True
        return True

    def _current_public_findings(self):
        receipts = tuple(record['finding'] for record in self._backend_receipts.values()
            if record['state'] != 'suppressed_processing' and self._backend_event_current(record['event']))
        if receipts:
            return receipts[-8:]
        if self._pending or self._bootstrap_state != 'ready':
            return ()
        if self._request:
            return tuple(item for item in self._public_findings
                if item.request == self._request and item.task_revision == self.task_revision)
        # Preserve greeting/help compatibility only before any business input.
        replies = getattr(self.call.dialog, 'public_replies', ())
        if replies and self._reply_revision == self.task_revision and not _generic_processing_reply(replies[-1]):
            return (_PublicFinding(0, self.task_revision,
                getattr(self.call.dialog, 'observation_revision', 0), self.clock(), replies[-1]),)
        return ()

    def _current_question(self):
        if (self._pending or self._reply_revision != self.task_revision
                or self._bootstrap_state != 'ready'):
            return ''
        if self._request:
            boundary = getattr(self.call.dialog, 'input_boundary', None)
            return (boundary.get('label', '') if type(boundary) is dict
                and boundary.get('source') == 'servicenow_input_control' else '')
        return getattr(self.call.dialog, 'current_question', '')

    def _status(self):
        dialog = self.call.dialog
        received = self._current_public_findings() if self._backend_receipts else ()
        if received:
            quote, complete = self._excerpt(received[-1].text)
            if quote:
                return ('Die letzte vollständige Rückmeldung von ServiceNow lautet: „' if complete else
                        'Ein Auszug aus der letzten ServiceNow-Rückmeldung lautet: „') + quote + '“' + (
                        '' if complete else ' Die Rückmeldung ist länger. Welchen Teil möchten Sie besprechen?')
        if self.bootstrap_pending:
            return ('Die Verbindung zu ServiceNow wird noch vorbereitet. Wir können Ihr Anliegen schon besprechen. '
                    'Ihre Angaben bleiben bis zur Bereitschaft lokal vorgemerkt.' if self._pending or self._supplements else
                    'Die Verbindung zu ServiceNow wird noch vorbereitet. Wir können Ihr Anliegen schon besprechen.')
        if self._bootstrap_state == 'failed':
            notice = caller_create_failure_notice(self._bootstrap_failure_reason)
            if notice:
                return notice
            return ('Die Verbindung zu ServiceNow konnte nicht vorbereitet werden. Wir können Ihr Anliegen '
                    'weiter besprechen. Ihre Angaben werden nicht automatisch erneut gesendet.')
        if getattr(dialog, 'conversation_ended', False):
            return ('ServiceNow hat den Dialog beendet. Ich kann die letzte Rückmeldung mit Ihnen klären. '
                    'Es wird nichts erneut gesendet. '
                    + ('Ihre Ergänzungen bleiben nur hier vorgemerkt und werden nicht in diesen '
                       'beendeten Dialog geschickt.' if self._pending else ''))
        if self._backend_unavailable:
            return ('ServiceNow hat keine abschließende Antwort geliefert. Die Anfrage wird nicht erneut gesendet. '
                    + ('Ihre Ergänzungen bleiben lokal vorgemerkt; eine Übernahme durch ServiceNow ist nicht bestätigt. '
                       if self._pending else '')
                    + 'Sie können nach dem Status fragen oder die letzte Rückmeldung wiederholen lassen.')
        if self._pending:
            return ('Der aktuelle Schritt läuft noch. Ihre Ergänzung ist vorgemerkt '
                    'und wird als Nächstes weitergegeben.')
        replies = self._current_public_findings()
        if replies:
            quote, complete = self._excerpt(replies[-1].text)
            if complete:
                return 'Die letzte vollständige Rückmeldung von ServiceNow lautet: „' + quote + '“'
            if quote:
                return ('Ein Auszug aus der letzten ServiceNow-Rückmeldung lautet: „' + quote +
                        '“ Die Rückmeldung ist länger. Welchen Teil möchten Sie besprechen?')
            return ('Eine ausführlichere ServiceNow-Rückmeldung liegt vor. '
                    'Welchen Teil möchten Sie genauer besprechen?')
        processing = getattr(dialog, 'processing', None)
        if isinstance(processing, dict) and processing.get('messages'):
            label = processing['messages'][-1]
            quote, complete = self._excerpt(label)
            if not complete:
                return ('ServiceNow zeigt einen ausführlicheren Verarbeitungshinweis. '
                        'Ein bestätigtes Ergebnis liegt damit noch nicht vor.')
            age = processing.get('ageSeconds', 0)
            prefix = 'Zuletzt wurde angezeigt' if age > 30 else 'ServiceNow zeigt gerade an'
            return f'{prefix}: „{quote}“. Das ist ein Verarbeitungshinweis, noch kein bestätigtes Ergebnis.'
        if self.busy:
            return ('Die Anfrage läuft noch in ServiceNow. Eine vollständige Rückmeldung liegt mir '
                    'noch nicht vor; den Grund oder die verbleibende Dauer kenne ich nicht.')
        question = self._current_question()
        return ('Die aktuelle Rückfrage lautet: „' + question + '“' if question and len(question) <= 350 else
                'Mir liegt noch kein bestätigtes Ergebnis vor. Wobei möchten Sie als Nächstes Hilfe?')

    @staticmethod
    def _excerpt(text, limit=330):
        if len(text) <= limit:
            return text, True
        ends = [match.end() for match in re.finditer(r'[.!?](?:\s|$)', text[:limit])]
        return (text[:ends[-1]].strip() if ends else ''), False

    def _help_failure_snapshot(self):
        current = getattr(self.call.dialog, 'input_control', None)
        current_key = (current.business_request_id, current.event_id) if isinstance(current, BackendEvent) else None
        return (self._bootstrap_state, self._backend_unavailable, self._backend_input_closed,
                current_key, next(reversed(self._backend_receipts), None))

    def _enqueue_help_fallback(self, turn, *, reason='unavailable'):
        if turn is not None and turn[3] in self._turn_speech_started:
            return
        if self._backend_outputs or any(item.kind in ('backend', 'backend_control') and self._valid(item)
                                        for item in self._outputs):
            return
        if self._control_gate.binding is not None and not self._control_gate.dispatched:
            self._reask_control(turn)
            return
        snapshot = self._help_failure_snapshot()
        active = self._active_output
        if (snapshot in self._help_failure_seen
                or any(item.fallback_snapshot == snapshot and self._valid(item) for item in self._outputs)
                or active is not None and active.fallback_snapshot == snapshot and self._valid(active)):
            return
        LOG.info('Voice independent help call=%s stage=fallback reason=%s', self.call.call_id, reason)
        self._enqueue('Ich kann Ihre Frage gerade nicht zuverlässig beantworten.', turn, kind='local',
                      fallback_snapshot=snapshot)

    def _repeat_last_reply(self):
        replies = self._current_public_findings()
        if not replies:
            return 'Es liegt keine Rückmeldung zum Wiederholen vor. ' + self._status()
        quote, complete = self._excerpt(replies[-1].text)
        return (('Die letzte Rückmeldung von ServiceNow war: „' if complete else
                 'Ein Auszug aus der letzten Rückmeldung von ServiceNow war: „') + quote
                + '“'
                if quote else self._status())

    async def _accept(self, turn):
        self._sync_native_control()
        _, text, number, _, _ = turn
        if (number not in self.call.turn_controls and
                re.fullmatch(r'\s*(?:äh|ähm)[.!?,…]*\s*', text, re.IGNORECASE)):
            self.call.turn_contexts.pop(number, None)
            self._observe_raw(text)
            return
        if number not in self.call.turn_controls and _non_speech_annotation(text):
            self.call.turn_contexts.pop(number, None)
            return
        observed = getattr(turn, 'duplex_onset', None)
        if observed is not None:
            onset, overlapped = observed
        else:
            onset = self._input_questions.get(turn[0], self._input_question_snapshot())
            overlapped = bool(self.call.synthesis_active or self.call.playback.data)
        # An overlapping listening signal is not a fresh business approval.
        native_polar = onset[1] == 'servicenow_input_control' and onset[2] and _polar(onset[0])
        if (overlapped or self.busy) and _passive_signal(text) and not native_polar and self._control_gate.binding is None:
            self.call.turn_contexts.pop(number, None)
            self._observe_raw(text)
            return
        if observed is not None or turn[0] == self._last_input_generation:
            self.interrupt(onset=onset)
        self._last_input_generation = self.call.playback.generation
        self.context_revision += 1
        self._observe_raw(text)
        control = self.call.turn_controls.pop(number, None)
        if control is not None:
            self.call.turn_contexts.pop(number, None)
            await self.call.speak_language_control(control[1], self.call.playback.generation,
                'LANGUAGE_SELECTED' if control[0] == 'selected' else 'LANGUAGE_SELECTION_RETRY')
            return
        boundary = getattr(self.call.dialog, 'input_boundary', None)
        label = boundary.get('label', '') if type(boundary) is dict else ''
        self._submission_onsets[turn[3]] = dict(onset=onset,
            current_complete=bool(label and onset == (label, 'servicenow_input_control', True,
                boundary.get('businessRequestId', ''), self.task_revision)
            and self._question_current(self._spoken_question)
            and self._speech is self._spoken_question))
        if self._backend_input_closed:
            self._control_gate.hold(turn, onset, self.call.turn_contexts.pop(number, None), 'backend_ended')
            self._submission_onsets.pop(turn[3], None)
            if not self._local_questions.full():
                self._local_questions.put_nowait((turn, 'help', self.epoch))
            return
        if self._control_gate.binding is not None:
            bound = onset[4] if len(onset) > 4 and onset[2] and isinstance(onset[4], ControlBinding) else None
            self._submission_onsets[turn[3]]['control'] = bound
            if not self._native_control_current(self._control_gate.binding):
                self._control_gate.hold(turn, bound, self.call.turn_contexts.pop(number, None), 'control_owner_changed')
                self._submission_onsets.pop(turn[3], None)
                return
            if (not self._control_gate.heard or bound != self._control_gate.binding
                    or self._control_gate.dispatched):
                self._control_gate.admit(turn, bound, self.call.turn_contexts.pop(number, None))
                self._submission_onsets.pop(turn[3], None)
                self._reask_control(turn)
                return
        self._queue_business_input(turn)
        # Local speech is optional. It never consumes or replaces the raw FIFO.
        if not self._local_questions.full():
            self._local_questions.put_nowait((turn, 'help', self.epoch))

    def _queue_business_input(self, turn):
        self._spoken_question = self._interrupted_speech = None
        if self._request:
            self.task_revision += 1
            self._outputs.clear()
        was_busy = self.busy
        self._pending.append(turn)
        if was_busy:
            # Optional prompt context can describe an input, never retire its send.
            self._queue_context_update(turn)


    def _reask_control(self, turn):
        control = self._control_gate.binding
        if control is not None:
            if not self._native_control_current(control):
                return
            if (control.label and not self._control_gate.dispatched
                    and not any(item.control_binding == control and self._valid(item) for item in self._outputs)
                    and not (self._active_output is not None and self._active_output.control_binding == control
                             and self._valid(self._active_output))):
                self._outputs = deque(item for item in self._outputs if item.kind == 'backend')
                self._enqueue(control.label, turn, kind='backend_control', control_binding=control)
            return
        boundary = getattr(self.call.dialog, 'input_boundary', None)
        if (self._bootstrap_state == 'ready' and type(boundary) is dict
                and boundary.get('source') == 'servicenow_input_control' and boundary.get('label')):
            self._enqueue(boundary['label'], turn, kind='backend')

    def _native_control_current(self, binding):
        event = getattr(self.call.dialog, 'input_control', None)
        return (isinstance(event, BackendEvent) and event.owner is getattr(self.call.dialog, 'backend_owner', None)
                and binding == ControlBinding.from_event(event))

    @staticmethod
    def _backend_key(event):
        return (id(event.owner), event.business_request_id, event.event_id)

    def _backend_event_current(self, event):
        record = self._backend_receipts.get(self._backend_key(event))
        return (self._live() and event.owner is not None and event.owner is getattr(self.call.dialog, 'backend_owner', None)
                and record is not None and record['event'] is event)

    def _admit_backend_event(self, event, turn):
        if (not isinstance(event, BackendEvent) or event.ui_type != 'OutputText'
                or event.owner is None
                or event.owner is not getattr(self.call.dialog, 'backend_owner', None)
                or event.business_request_id != getattr(self.call.dialog, 'business_request_id', None)):
            return False
        key = self._backend_key(event)
        if key in self._backend_receipts:
            return False
        text = spoken_text(event.text)
        if not text:
            return False
        if len(self._backend_receipts) >= 200:
            retired = next((old for old, record in self._backend_receipts.items()
                if record['state'] not in ('pending', 'active')), None)
            if retired is None:
                raise RuntimeError('Owned backend receipt queue full')
            del self._backend_receipts[retired]
        current = getattr(self.call.dialog, 'input_control', None)
        coalesced = (isinstance(current, BackendEvent) and current.ui_type == 'Boolean'
            and current.owner is event.owner and current.business_request_id == event.business_request_id
            and current.text == text and self._control_gate.binding == ControlBinding.from_event(current))
        state = ('coalesced_control' if coalesced else
                 'suppressed_processing' if _generic_processing_reply(text) else 'pending')
        finding = _PublicFinding(self._request, self.task_revision, event.event_id, self.clock(), text)
        self._backend_receipts[key] = dict(event=event, state=state, finding=finding)
        if state == 'pending':
            self._backend_outputs.append(_Output(text, turn, self.epoch, self.task_revision,
                None, 'backend', backend_event=event))
            self._output_ready.set()
        LOG.info('Voice independent backend call=%s stage=receipt_%s event=%s request=%s',
                 self.call.call_id, state, event.event_id, event.business_request_id)
        return True

    def _interrupt_backend_speech(self, state):
        event = state.get('backend_event') if state is not None else None
        record = self._backend_receipts.get(self._backend_key(event)) if event is not None else None
        if record is not None and record['state'] in ('pending', 'active'):
            record['state'] = 'interrupted'

    def _settle_backend_state(self):
        state = getattr(self.call.dialog, 'backend_state', None)
        if (not isinstance(state, BackendState) or state.owner is None
                or state.owner is not getattr(self.call.dialog, 'backend_owner', None)
                or state.request_id != getattr(self.call.dialog, 'business_request_id', None) or not state.ended):
            return
        self._backend_input_closed = True
        self._backend_unavailable = True
        self._control_gate.retire()
        while self._pending:
            turn = self._pending.popleft()
            self._control_gate.hold(turn, self._submission_onsets.pop(turn[3], None),
                self.call.turn_contexts.pop(turn[2], None), 'backend_ended')

    def _sync_native_control(self):
        event = getattr(self.call.dialog, 'input_control', None)
        if event is not None and (not isinstance(event, BackendEvent)
                or event.owner is not getattr(self.call.dialog, 'backend_owner', None)):
            return
        binding = ControlBinding.from_event(event)
        changed = binding != self._control_gate.binding
        self._control_gate.observe(binding)
        if binding is not None:
            if changed:
                # Supplemental cumulative context must not carry held originals
                # into a later business request after this control retires.
                self._context_snapshot = ''
                self._context_covered.clear()
                self._context_full = False
                LOG.info('Voice independent control call=%s stage=observed ui_type=Boolean event=%s request=%s',
                    self.call.call_id, binding.event_id, binding.business_request_id)
            while self._pending and (changed or not self._control_gate.heard):
                turn = self._pending.popleft()
                submitted = self._submission_onsets.pop(turn[3], None)
                bound = submitted.get('control') if submitted else None
                self._control_gate.hold(turn, bound, self.call.turn_contexts.pop(turn[2], None), 'control_prequestion')
            self._context_pending = self._context_candidate = None
            if changed:
                self._outputs = deque(item for item in self._outputs if item.control_binding is None)
            if not self._control_gate.heard:
                self._reask_control(None)

    def _queue_context_update(self, turn):
        if (self._context_publisher is None or not self._live() or self._context_full
                or self._backend is None or self._backend.done()):
            return
        text = turn[1]
        snapshot = self._context_snapshot + ('\n' if self._context_snapshot else '') + text
        if len(snapshot) > 8000 or len(snapshot.encode('utf-8')) > 12000:
            # Keep the original FIFO. Never truncate a spelling or skip an
            # overflowing item and then publish a misleading later snapshot.
            self._context_full = True
            LOG.warning('Voice independent context stage=held reason=snapshot_full')
            return
        self._context_snapshot = snapshot
        self._context_publish_revision += 1
        self._context_covered.add(id(turn))
        prefix = tuple(self._pending)
        supplements = tuple(self._supplements)
        # Coalesce unsent revisions; the newest snapshot still contains every
        # raw update in order. Only one context request may be in flight.
        self._context_candidate = {'request': self._request,
            'revision': self._context_publish_revision, 'snapshot': snapshot,
            'task_revision': self.task_revision, 'prefix': prefix, 'supplements': supplements,
            'retirable': False,
            'done': asyncio.Event(), 'ack': None}
        self._context_pending = self._context_candidate
        self._context_ready.set()

    async def _context_loop(self):
        while self._live():
            await self._context_ready.wait()
            self._context_ready.clear()
            item, self._context_pending = self._context_pending, None
            if item is None:
                continue
            request, revision, snapshot = item['request'], item['revision'], item['snapshot']
            if (not self._live() or request != self._request
                    or self._backend is None or self._backend.done()):
                item['done'].set()
                continue
            try:
                item['ack'] = await self._context_publisher(revision, snapshot)
                # An ActionMsg acknowledgement proves neither agent uptake
                # nor a valid input boundary. Original FIFO stays untouched.
            except asyncio.CancelledError:
                raise
            except Exception as error:
                # Delivery may be uncertain. Do not retry or fail the call.
                LOG.warning('Voice independent context stage=uncertain type=%s', type(error).__name__)
            finally:
                item['done'].set()

    async def _reconcile_context(self, turn, replies):
        """Prompt-context uptake never replaces delivery of original input."""
        return False

    async def _business(self, turn):
        _, text, number, _, _ = turn
        if self._backend_input_closed:
            self._control_gate.hold(turn, None, self.call.turn_contexts.pop(number, None), 'backend_ended')
            return
        submitted = self._submission_onsets.pop(turn[3], None)
        self._sync_native_control()
        native_binding = self._control_gate.binding
        if native_binding is not None:
            bound = submitted.get('control') if submitted else None
            if not self._native_control_current(native_binding):
                self._control_gate.hold(turn, bound, self.call.turn_contexts.pop(number, None), 'control_owner_changed')
                return
            if not self._control_gate.admit(turn, bound, self.call.turn_contexts.get(number)):
                self.call.turn_contexts.pop(number, None)
                self._reask_control(turn)
                return
        boundary = getattr(self.call.dialog, 'input_boundary', None)
        if (native_binding is None and _polar_answer(text) and type(boundary) is dict
                and boundary.get('source') == 'servicenow_input_control'
                and _polar(boundary.get('label', ''))):
            expected = (boundary['label'], 'servicenow_input_control', True,
                        boundary.get('businessRequestId', ''))
            if (submitted is None or not submitted['current_complete']
                    or tuple(submitted['onset'][:4]) != expected):
                # A bare old yes/no cannot become the answer to a new native
                # confirmation. The native agent owns the confirmation itself.
                self.call.turn_contexts.pop(number, None)
                self._reask_control(turn)
                LOG.info('Voice independent input call=%s stage=stale_confirmation_held', self.call.call_id)
                return
        revision = self.task_revision
        self._request += 1
        request = self._request
        self._public_findings.clear()
        self._public_sequence = 0
        self._context_pending = None
        self._context_candidate = None
        self._context_covered.discard(id(turn))
        # The greeting (and earlier replies) belongs to the previous input
        # boundary. Only current callbacks or a genuine input label become current.
        self._reply_revision = None
        self.updates.start(self.clock())
        replies, deferred = [], []
        published, admitted_replies = set(), set()

        def input_label():
            boundary = getattr(self.call.dialog, 'input_boundary', None)
            label = boundary.get('label') if type(boundary) is dict else None
            return (label if type(boundary) is dict
                and boundary.get('source') == 'servicenow_input_control'
                and type(label) is str and label else '')

        def publish(reply, sequence):
            if reply and not _generic_processing_reply(reply):
                self._reply_revision = revision
                self._public_findings.append(_PublicFinding(request, revision,
                    sequence, self.clock(), reply))
                published.add(reply)

        def admit(reply):
            if self._control_gate.binding is not None and reply == self._control_gate.binding.label:
                self._reask_control(turn)
                return
            if revision == self.task_revision and not self._pending:
                admitted = self._enqueue(reply, turn, kind='backend')
                if admitted:
                    admitted_replies.add(reply)
                # Only an admitted audible replacement owns playback. Stale
                # or suppressed callbacks must leave current local speech intact.
                if admitted:
                    buffered_ack = self._buffered_confirmation_ack()
                    if self._active_kind in ('conversation', 'confirmation_ack') or buffered_ack is not None:
                        lease = self._speech.get('lease') if self._speech is not None else None
                        if (self._active_kind == 'conversation' and lease is not None
                                and self._active_speech_current(lease.output, lease.generation, lease)):
                            return
                        if buffered_ack is not None:
                            buffered_ack['interrupted'] = True
                        self.call.playback.interrupt()
                        if self._synthesis_task is not None:
                            self._synthesis_task.cancel()

        async def on_reply(reply):
            replies.append(reply)
            self._public_sequence += 1
            # Dialog/ServiceNow retain the actual callbacks as source evidence.
            # Native assistant text is published only with admitted nonempty PCM.
            # The whole final poll has already updated input_boundary before its
            # callbacks run. Resolve question speech at settlement, not per event.
            if reply and (re.search(r"""[?][\s"'»“”’)\]}]*$""", reply)
                          or _forward_solicitation(reply)
                          or reply == input_label()):
                deferred.append((reply, self._public_sequence))
                return
            publish(reply, self._public_sequence)
            admit(reply)
            self._queue_dialogue_observation()
        async def on_event(event):
            self._sync_native_control()
            self._settle_backend_state()
            if event.ui_type == 'OutputText':
                self._admit_backend_event(event, turn)
                self._queue_dialogue_observation()
            elif (event.ui_type != 'Boolean'
                    and isinstance(getattr(self.call.dialog, 'input_control', None), BackendEvent)
                    and self._backend_key(event) == self._backend_key(self.call.dialog.input_control)):
                await on_reply(event.text)
        context = self.call.turn_contexts.pop(number, None)
        try:
            await self.call.dialog.turn(text, on_event=on_event, voice_context=context,
                                        native_control_binding=native_binding)
        except BackendControlChanged as conflict:
            if conflict.owner is not getattr(self.call.dialog, 'backend_owner', None):
                raise BackendTurnUnavailable('Unowned input conflict') from None
            self.call.dialog.input_control = conflict.input_control
            event = conflict.input_control
            self.call.dialog.input_boundary = (dict(source='servicenow_input_control',
                controlType=event.ui_type, businessRequestId=event.business_request_id, label=event.text)
                if event is not None else None)
            self._sync_native_control()
            self._control_gate.hold(turn, submitted, context, 'control_changed_before_dispatch')
            self._reask_control(turn)
            return
        self._settle_backend_state()
        label = input_label()
        if label:
            # This label is an observed ServiceNow input control, not a locally
            # inferred question or approval. A callback is not guaranteed.
            if label not in replies:
                self.call.dialog.record_public_reply(label)
            if label not in published:
                sequence = next((seq for text, seq in reversed(deferred) if text == label), None)
                if sequence is None:
                    self._public_sequence += 1
                    sequence = self._public_sequence
                publish(label, sequence)
            release = (label,)
        elif (type(boundary := getattr(self.call.dialog, 'input_boundary', None)) is dict
                and boundary.get('source') == 'servicenow_input_control'):
            # A genuine control with no public label authorizes no guessed question.
            release = ()
        else:
            # A non-input informational question is delayed, never discarded.
            for reply, sequence in deferred:
                if _forward_solicitation(reply):
                    continue
                publish(reply, sequence)
            if deferred:
                self._public_findings = deque(sorted(self._public_findings,
                    key=lambda item: item.sequence), maxlen=8)
            release = tuple(reply for reply, _ in deferred if not _forward_solicitation(reply))
        reconciled = await self._reconcile_context(turn, replies)
        if not reconciled:
            for reply in release:
                if reply not in admitted_replies:
                    admit(reply)
        self._queue_dialogue_observation()

    def _start_worker(self, name, coroutine):
        task = asyncio.create_task(coroutine, name=name)
        self._workers.add(task)
        task.add_done_callback(self._worker_done)

    def _worker_done(self, task):
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            # Observe failures without cancelling an already submitted VA turn.
            LOG.warning('Voice independent worker call=%s stage=failed worker=%s type=%s',
                        self.call.call_id, task.get_name(), type(error).__name__)
        elif self._live():
            LOG.warning('Voice independent worker call=%s stage=ended worker=%s',
                        self.call.call_id, task.get_name())

    def _settle_bootstrap(self, opening):
        """Settle the same owned bootstrap without consuming any caller FIFO item."""
        try:
            replies = opening.result()
            if type(replies) is not list or any(type(reply) is not str for reply in replies):
                raise ValueError('Invalid owned startup result')
        except (asyncio.CancelledError, Exception) as error:
            self._bootstrap_state = 'failed'
            self._bootstrap_failure_reason = startup_reason(error)
            LOG.warning('Voice independent startup call=%s stage=failed type=%s reason=%s',
                        self.call.call_id, type(error).__name__, self._bootstrap_failure_reason)
            self._backend_unavailable = True
            self._reply_revision = None
            self.interrupt()
            self._enqueue(self._status(), kind='recovery')
            return
        self._bootstrap_state = 'ready'
        publish_metadata = getattr(self.call, 'publish_dialog_metadata', None)
        if callable(publish_metadata):
            publish_metadata()
        self._bootstrap_onset = None
        LOG.info('Voice independent startup call=%s stage=ready pending=%d', self.call.call_id, len(self._pending))
        if not self._pending:
            introduction = getattr(self.call.config, 'greeting', '')
            selection = getattr(self.call.call_settings, 'selection_prompt', '')
            seen = {value for value in (introduction, ' '.join(p for p in (introduction, selection) if p)) if value}
            for reply in replies:
                if reply and reply not in seen:
                    seen.add(reply)
                    self._enqueue(reply, kind='backend')
        self._queue_dialogue_observation()

    async def run(self, *, bootstrap_task=None):
        if bootstrap_task is not None and not isinstance(bootstrap_task, asyncio.Future):
            raise ValueError('Startup must be an existing call-owned task')
        opening = bootstrap_task
        self._bootstrap_state = 'pending' if opening is not None else 'ready'
        for name, coroutine in (('speaker', self._speak_loop()), ('dialogue', self._local_loop()),
                                ('updates', self._update_loop())):
            self._start_worker(name, coroutine)
        if self._context_publisher is not None:
            self._start_worker('context', self._context_loop())
        incoming = None
        try:
            while self._live():
                if opening is not None and opening.done():
                    self._settle_bootstrap(opening)
                    opening = None
                if (not self.bootstrap_pending and not self._backend_unavailable
                        and self._backend is None and self._pending):
                    self._backend = asyncio.create_task(self._business(self._pending.popleft()))
                if incoming is None:
                    incoming = asyncio.create_task(self.call.wait_for_user_turn())
                    self._incoming_turn = incoming
                waiting = {incoming}
                if self._backend is not None:
                    waiting.add(self._backend)
                if opening is not None:
                    waiting.add(opening)
                ready, _ = await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
                if opening is not None and opening in ready:
                    self._settle_bootstrap(opening)
                    opening = None
                if self._backend is not None and self._backend in ready:
                    try:
                        self._backend.result()
                        self._settle_backend_state()
                    except BackendTurnUnavailable:
                        self._backend_unavailable = True
                        self._context_pending = None
                        self._reply_revision = None
                        self.interrupt()
                        self._enqueue(self._status(), kind='recovery')
                        LOG.warning('Voice independent backend stage=%s local_dialogue=retained',
                            'closed' if getattr(self.call.dialog, 'conversation_ended', False) else 'unavailable')
                    self._backend = None
                if incoming in ready:
                    turn = incoming.result()
                    incoming = None
                    self._incoming_turn = None
                    try:
                        if turn is None or not self._live():
                            break
                        await self._accept(turn)
                    finally:
                        self.call.recognized_turns.task_done()
            # Input-loss observation must settle the already submitted VA turn.
            if self.call.input_lost and self._backend is not None:
                await asyncio.shield(self._backend)
        finally:
            if incoming is not None:
                incoming.cancel()
                await asyncio.gather(incoming, return_exceptions=True)
            await self.close()

    async def _local_loop(self):
        while self._live():
            turn, kind, epoch = await self._local_questions.get()
            try:
                if epoch != self.epoch:
                    continue
                self._local_busy = True
                await self._general_help(turn, epoch, kind)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                LOG.warning('Voice independent dialogue stage=optional_failed type=%s', type(error).__name__)
                if epoch == self.epoch:
                    if kind == 'status':
                        self._enqueue(self._status(), turn, kind='status',
                            observation=getattr(self.call.dialog, 'observation_revision', 0))
                    else:
                        self._enqueue_help_fallback(turn)
            finally:
                self._local_busy = False
                self._local_questions.task_done()

    def _dialogue_signature(self, snapshot, key):
        def normalize(value):
            if isinstance(value, dict):
                return {name: normalize(item) for name, item in value.items()
                        if name != 'observation_revision'}
            if isinstance(value, (tuple, list)):
                return [normalize(item) for item in value]
            return value
        exposed = dict(snapshot, public_findings=tuple(fact for fact in snapshot['public_findings']
            if fact['source_event'] != 'complete_emitted_assistant_speech'))
        context = dict(snapshot=exposed, key=key,
            pending_ids=tuple(turn[3] for turn in self._pending),
            input_boundary=getattr(self.call.dialog, 'input_boundary', None),
            bootstrap_state=self._bootstrap_state, backend_unavailable=self._backend_unavailable,
            conversation_ended=bool(getattr(self.call.dialog, 'conversation_ended', False)))
        encoded = json.dumps(normalize(context), sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        return hashlib.sha256(encoded.encode('utf-8')).hexdigest()

    def _dialogue_snapshot(self, turn, epoch, *, bind_observation=True):
        observation = getattr(self.call.dialog, 'observation_revision', 0)
        key = dict(call_id=self.call.call_id, task_id=self.call.call_id + '-va',
                   task_revision=self.task_revision, context_revision=self.context_revision,
                   observation_revision=observation, output_epoch=epoch, request_id=turn[3])
        snapshot = {name: key[name] for name in ('call_id', 'task_id', 'task_revision',
                     'context_revision', 'observation_revision')}
        snapshot.update(raw_inputs=tuple(self._raw), public_findings=())
        actual_question, question_source, _ = self.question_context()
        backend_closed = bool(getattr(self.call.dialog, 'conversation_ended', False))
        snapshot = conversational_snapshot(snapshot, question=actual_question,
            question_source=question_source,
            busy=self.busy and not self.bootstrap_pending and not backend_closed and not self._backend_unavailable)
        if self._interrupted_speech is not None:
            snapshot['capability_limits'] += (
                'Die vorige Sprachausgabe wurde unterbrochen. Behandle deren ungesprochenen '
                'Rest nicht als gehört. Der Audiozeiger belegt nur vom Server ausgegebenes PCM, '
                'keine bestätigte Wiedergabe am Telefon. Antworte auf die neue Eingabe im '
                'aktuellen Zusammenhang; setze alten Text nicht blind fort.',)
        snapshot['capability_limits'] += (
            'Die ServiceNow-Verbindung wird vorbereitet. Noch keine fachliche Eingabe wurde übermittelt; '
            'besprich das Anliegen, ohne eine laufende Bearbeitung oder Kontextübernahme zu behaupten.'
            if self.bootstrap_pending else
            'ServiceNow hat diesen Dialog beendet. Behaupte keine laufende Bearbeitung und keine '
            'weitere Übermittlung in diesen Dialog; erkläre nur die vorhandene Rückmeldung.' if backend_closed else
            'Die Anfrage ist derzeit nicht verfügbar; eine weitere Bearbeitung ist nicht belegt.'
            if self._backend_unavailable else
            'Die Anfrage wartet noch auf vollständige Rückmeldung.' if self.busy else
            'Kein selbständiger Geschäftsabschluss; nur die vorhandene Rückmeldung ist belegt.',)
        snapshot['capability_limits'] += (
            'Neuere Rückmeldungen gehen älteren vor; ausdrücklich zurückgezogene Angaben gelten nicht weiter.',)
        if self._pending or self._supplements:
            snapshot['capability_limits'] += (
                'Neue Caller-Ergänzungen bleiben für die reguläre Eingabe vorgemerkt. '
                'Eine Übernahme als Kontext durch laufende ServiceNow-Agenten ist NICHT bestätigt.'
                if self._context_publisher is not None else
                'Neue Caller-Ergänzungen sind lokal vorgemerkt '
                'und noch NICHT an die laufenden ServiceNow-Agenten weitergegeben.',)
        selected, remaining = [], 2000
        for reply in reversed(self._current_public_findings()):
            if len(selected) >= 3 or len(reply.text) > remaining:
                break
            selected.append(reply)
            remaining -= len(reply.text)
        for reply in reversed(selected):
            fact = {name: key[name] for name in ('call_id', 'task_id', 'task_revision',
                    'context_revision', 'observation_revision')}
            fact.update(evidence_id=f'public-reply-{reply.request}-{reply.sequence}',
                source_event='complete_public_va_reply', sequence=reply.sequence,
                observed_at=reply.observed_at, text=reply.text, superseded=False)
            snapshot['public_findings'] += (fact,)
        processing = getattr(self.call.dialog, 'processing', None)
        if (self._bootstrap_state == 'ready' and isinstance(processing, dict)
                and processing.get('messages') and not self._pending
                and not backend_closed and not self._backend_unavailable):
            fact = {name: key[name] for name in ('call_id', 'task_id', 'task_revision',
                    'context_revision', 'observation_revision')}
            fact.update(evidence_id='processing-label-' + str(processing['revision']),
                source_event='servicenow_processing_presentation', sequence=processing['revision'],
                observed_at=max(0, self.clock() - processing.get('ageSeconds', 0)),
                text=processing['messages'][-1], superseded=False)
            snapshot['public_findings'] += (fact,)
        snapshot = append_servicenow_context(snapshot, build_servicenow_voice_context(
            self.call.call_settings, dict(business_available=not self._backend_unavailable and not self.bootstrap_pending,
                business_busy=self.busy and not self.bootstrap_pending, backend_closed=backend_closed,
                context_updates_enabled=self._context_publisher is not None and not self.bootstrap_pending,
                pending_count=len(self._pending), supplement_count=len(self._supplements),
                question_source=question_source)))
        # Optional history is admitted last, after current processing and
        # capability limits, so it cannot overflow the final wire snapshot.
        # Complete emitted PCM is conversation context, not proof of a
        # business result or physical-device playback.
        for spoken in tuple(self._spoken_history)[-3:]:
            fact = {name: key[name] for name in ('call_id', 'task_id', 'task_revision',
                                               'context_revision', 'observation_revision')}
            fact.update(evidence_id='spoken-assistant-' + str(spoken['sequence']),
                source_event='complete_emitted_assistant_speech', sequence=spoken['sequence'],
                observed_at=spoken['observed_at'], text=spoken['text'], superseded=False)
            candidate = dict(snapshot, public_findings=snapshot['public_findings'] + (fact,))
            encoded = json.dumps(candidate, ensure_ascii=False, separators=(',', ':'))
            if len(encoded) <= 10000 and len(encoded.encode('utf-8')) <= 32768:
                snapshot = candidate
        if bind_observation and self.bootstrap_pending:
            question = (actual_question, question_source)
            native_question = self._bootstrap_native_question()
            observation = _BootstrapObservation(observation,
                self._bootstrap_context_fingerprint(question, native_question), question, native_question)
        elif bind_observation and self._pending:
            observation = _PendingObservation(tuple(turn), epoch, self._dialogue_signature(snapshot, key))
        return key, snapshot, observation

    def _admit_conversation(self, candidate, turn, epoch, observation, snapshot):
        return self._release_conversation_sentence(candidate, turn, epoch, observation, snapshot) == 'enqueued'

    def _release_conversation_sentence(self, candidate, turn, epoch, observation, snapshot, *,
                                       skip_unsupported_claim=False):
        """Report actual queue admission separately from a safe streaming skip."""
        if epoch != self.epoch:
            self._log_dialogue_discard('caller_epoch_changed', 'sentence')
            return 'rejected'
        if not self._observation_current(observation):
            self._log_dialogue_discard('context_changed', 'sentence')
            return 'rejected'
        # Read-only wording uses bound public observations; it supplies no
        # business evidence or completion authority. These guards hold
        # obvious success/control/identifier leakage, not prove semantics.
        text = candidate.text.strip()
        forbidden_matches = re.finditer(r'(?i)(?:<|https?://|\b(?:public-reply|processing-label)-|'
            r'\b[0-9a-f]{16,}\b|\b(?:analysis|reasoning|tool_call|'
            r'bestellt|abgeschlossen|genehmigt|freigegeben|erledigt|bestätigt)\b)', text)
        forbidden = next((match for match in forbidden_matches
            if match.group(0).casefold() != 'bestellt' or not _noncompletion_ordering(text, match)), None)
        source = ' '.join(fact['text'] for fact in snapshot['public_findings']
                          if fact['source_event'] != 'complete_emitted_assistant_speech')
        source += ' ' + ' '.join(snapshot['raw_inputs']) + ' ' + snapshot.get('question', '')
        unbound_numbers = any(number not in re.findall(r'\d+', source)
                              for number in re.findall(r'\d+', text))
        identifiers = (self.call.call_id, self.call.call_id + '-va', turn[3],
                       getattr(candidate.identity, 'server_session_id', ''),
                       getattr(candidate.identity, 'socket_instance', ''))
        reason = None
        if not text:
            reason = 'empty_text'
        elif len(text) > 1200:
            reason = 'text_too_long'
        elif forbidden:
            match = forbidden.group(0).casefold()
            reason = {'bestellt': 'completion_ordered', 'abgeschlossen': 'completion_closed',
                'genehmigt': 'completion_approved', 'freigegeben': 'completion_released',
                'erledigt': 'completion_done', 'bestätigt': 'completion_confirmed',
                'analysis': 'internal_control_word', 'reasoning': 'internal_control_word',
                'tool_call': 'internal_control_word', '<': 'markup'}.get(match)
            if reason is None:
                reason = ('external_url' if match.startswith(('http://', 'https://')) else
                          'internal_evidence_id' if match.startswith(('public-reply-', 'processing-label-'))
                          else 'opaque_identifier')
        elif unbound_numbers:
            reason = 'unbound_number'
        elif any(value and value in text for value in identifiers):
            reason = 'identifier_in_text'
        elif not self.conversation.is_current(candidate.identity):
            reason = 'identity_not_current'
        elif unproven_storage_or_check_claim(text):
            reason = 'unproven_storage_or_check_claim'
        if reason is not None:
            self._log_dialogue_discard(reason, 'sentence')
            if skip_unsupported_claim and reason == 'unproven_storage_or_check_claim':
                return 'skipped_claim'
            return 'rejected'
        admitted = self._enqueue(text, turn, kind='conversation', observation=observation,
                                 identity=candidate.identity)
        if not admitted:
            self._log_dialogue_discard('output_queue_rejected', 'sentence')
        return 'enqueued' if admitted else 'rejected'

    def _queue_dialogue_observation(self):
        observe = getattr(self.conversation, 'observe', None)
        if (not callable(observe) or self._dialogue_turn is None or self._closed
                or len(self._observations) >= 8):
            return
        try:
            key, snapshot, _ = self._dialogue_snapshot(self._dialogue_turn, self.epoch)
            conversation = self.conversation
            signature = self._dialogue_signature(snapshot, key)
            current = self._dialogue_observation_state
            if current is not None and current[0] is conversation and current[1] == signature:
                return
            scheduled = (conversation, signature, object())
            self._dialogue_observation_state = scheduled
        except Exception:
            return
        async def apply():
            try:
                if (self._dialogue_observation_state is not scheduled
                        or self.conversation is not conversation or self.epoch != key['output_epoch']):
                    return
                if await observe(snapshot, key) is not True and self._dialogue_observation_state is scheduled:
                    self._dialogue_observation_state = None
            except asyncio.CancelledError:
                if self._dialogue_observation_state is scheduled:
                    self._dialogue_observation_state = None
                raise
            except Exception as error:
                if self._dialogue_observation_state is scheduled:
                    self._dialogue_observation_state = None
                LOG.warning('Voice dialogue observation unavailable type=%s', type(error).__name__)
        task = asyncio.create_task(apply())
        self._observations.add(task)
        def finished(operation):
            self._observations.discard(operation)
            if operation.cancelled() and self._dialogue_observation_state is scheduled:
                self._dialogue_observation_state = None
        task.add_done_callback(finished)

    def _revoke_dialogue_output(self, turn):
        self._outputs = deque(item for item in self._outputs
            if not (item.kind == 'conversation' and item.turn is not None and item.turn[3] == turn[3]))
        active = self._active_output
        if active is not None and active.kind == 'conversation' and active.turn[3] == turn[3]:
            lease = self._speech.get('lease') if self._speech is not None else None
            if lease is not None and self._active_speech_current(active, lease.generation, lease):
                return
            self.call.playback.interrupt()
            if self._synthesis_task is not None:
                self._synthesis_task.cancel()

    async def _general_help(self, turn, epoch, kind='help'):
        if self._control_gate.binding is not None and not self._control_gate.dispatched:
            self._reask_control(turn)
            return
        if kind == 'status':
            # An explicit progress question needs observed state, not a model's
            # guess about hidden agent work or the meaning of silence.
            self._enqueue(self._status(), turn, kind='status',
                observation=getattr(self.call.dialog, 'observation_revision', 0))
            return
        def emit_fallback(reason='unavailable'):
            self._enqueue_help_fallback(turn, reason=reason)
        if self._model_failed:
            emit_fallback('model_failed')
            return
        try:
            if self._invalidations:
                await asyncio.gather(*tuple(self._invalidations), return_exceptions=True)
            if self.conversation is None:
                self._dialogue_observation_state = None
                self.conversation = await self._factory(self.call.config.conversation_ws_url,
                                                        self.call.call_id, self.epoch)
            if epoch != self.epoch:
                self._log_dialogue_discard('caller_epoch_changed', 'connection')
                return
            if self.conversation.output_epoch < self.epoch:
                await self.conversation.invalidate(self.epoch, 'input during connection')
            self._dialogue_turn = turn
            key, snapshot, observation = self._dialogue_snapshot(turn, epoch)
            self._dialogue_observation_state = (self.conversation,
                self._dialogue_signature(snapshot, key), object())
            admitted = 0
            async def sentence(candidate):
                nonlocal admitted
                disposition = self._release_conversation_sentence(candidate, turn, epoch, observation, snapshot,
                                                                    skip_unsupported_claim=True)
                if disposition == 'skipped_claim':
                    return
                if disposition != 'enqueued':
                    raise ValueError('Conversation sentence release rejected')
                admitted += 1
            streaming = getattr(self.conversation, 'sentence_streaming', False)
            if streaming:
                candidate = await self.conversation.respond(turn[1], snapshot, key, on_sentence=sentence)
            else:
                candidate = await self.conversation.respond(turn[1], snapshot, key)
            if self._control_gate.binding is not None and not self._control_gate.dispatched:
                self._revoke_dialogue_output(turn)
                self._reask_control(turn)
                return
            if epoch != self.epoch:
                self._log_dialogue_discard('caller_epoch_changed', 'completion')
                return
            if not self._observation_current(observation):
                self._log_dialogue_discard('context_changed', 'completion')
                self._revoke_dialogue_output(turn)
                return
            if candidate.failure is not None:
                self._revoke_dialogue_output(turn)
                if candidate.failure == 'superseded':
                    self._log_dialogue_discard('output_superseded', 'completion')
                    return
                reasons = {'output_callback_failed': 'candidate_callback_failed',
                    'unavailable': 'candidate_protocol_unavailable', 'busy': 'candidate_busy',
                    'invalid_input': 'candidate_invalid_input'}
                reason = reasons.get(candidate.failure, 'candidate_failure_unknown') if type(candidate.failure) is str else 'candidate_failure_unknown'
                self._log_dialogue_discard(reason, 'completion')
                busy = getattr(getattr(self.conversation, 'controller_transport', None), 'transient_busy', False)
                if busy:
                    # Admission429 ends only this optional model attempt. A new
                    # user question may use a fresh session; never retry input.
                    await self.conversation.close()
                    self.conversation = None
                    self._dialogue_observation_state = None
                elif candidate.failure == 'output_callback_failed':
                    # A rejected sentence is this reply's release failure, not
                    # evidence that every later model turn is unavailable. Close
                    # only its owned session; a NEW input may start another one.
                    owned = self.conversation
                    self.conversation = None
                    self._dialogue_observation_state = None
                    await owned.close()
                else:
                    self._model_failed = True
                if epoch == self.epoch:
                    emit_fallback('controller_busy' if busy else 'unavailable')
                else:
                    self._log_dialogue_discard('caller_epoch_changed', 'failure_cleanup')
                return
            if not streaming and not self._admit_conversation(candidate, turn, epoch, observation, snapshot):
                emit_fallback()
            elif streaming and not admitted:
                emit_fallback()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._revoke_dialogue_output(turn)
            busy = getattr(getattr(self.conversation, 'controller_transport', None), 'transient_busy', False)
            if busy:
                await self.conversation.close()
                self.conversation = None
                self._dialogue_observation_state = None
            else:
                self._model_failed = True
            LOG.warning('Voice independent dialogue stage=unavailable type=%s', type(error).__name__)
            if epoch == self.epoch:
                emit_fallback('controller_busy' if busy else 'unavailable')

    async def _speak_loop(self):
        while self._live():
            if not self._outputs and not self._backend_outputs:
                self._output_ready.clear()
                await self._output_ready.wait()
                continue
            queue = self._backend_outputs if self._backend_outputs else self._outputs
            item = queue[0]
            if not self._valid(item):
                self._discard_output(item, 'queue')
                queue.popleft()
                continue
            if item.kind == 'confirmation_ack' and any(
                    queued.kind == 'backend' and self._valid(queued) for queued in self._outputs):
                queue.popleft()
                continue
            if (self.call.playback.data or self.call.synthesis_active or self.call.vad_active
                    or self.call.recognition_active or not self.call.turns.empty()):
                await asyncio.sleep(.02)
                continue
            queue.popleft()
            if item.backend_event is not None:
                self._backend_receipts[self._backend_key(item.backend_event)]['state'] = 'active'
            generation = self.call.playback.generation
            self._active_kind = item.kind
            self._active_output = item
            self.call.synthesis_active = True
            speech_state = self._begin_speech(item)
            speech_complete = False
            try:
                LOG.info('Voice independent output call=%s stage=tts_start kind=%s request=%s generation=%s',
                         self.call.call_id, item.kind, self._request, generation)
                self._synthesis_task = asyncio.create_task(self._synthesize(item, generation))
                await self._synthesis_task
                speech_complete = self._active_speech_current(item, generation, speech_state.get('lease'))
            except asyncio.CancelledError:
                LOG.info('Voice independent output call=%s stage=tts_cancelled kind=%s',
                         self.call.call_id, item.kind)
                if asyncio.current_task().cancelling():
                    raise
            except Exception as error:
                LOG.warning('Voice independent output stage=tts_failed type=%s', type(error).__name__)
                self.call.playback.interrupt()
            finally:
                self._finish_speech(speech_state, complete=speech_complete)
                if item.backend_event is not None and not speech_complete:
                    self._interrupt_backend_speech(speech_state)
                self.call.synthesis_active = False
                self._active_kind = None
                self._active_output = None
                self._synthesis_task = None

    async def _synthesize(self, item, generation):
        started = self.clock()
        queued = 0
        first = True
        state = self._speech
        lease = None
        async for chunk in self.call.speech.synthesize(item.text):
            if not self._active_speech_current(item, generation, lease):
                self._discard_output(item, 'pcm')
                break
            while len(self.call.playback.data) > 48000 and self._active_speech_current(item, generation, lease):
                await asyncio.sleep(.02)
            if not self._active_speech_current(item, generation, lease):
                self._discard_output(item, 'pcm')
                break
            if self._active_speech_current(item, generation, lease):
                if chunk and self.call.playback.put(chunk, generation):
                    if lease is None:
                        lease = _SpeechLease(item, generation, self.epoch,
                            self.conversation if item.identity is not None else None, item.identity)
                        if state is not None and state.get('output') is item:
                            state['lease'] = lease
                    queued += len(chunk)
                    if item.kind == 'confirmation_ack' and state is not None and state.get('output') is item:
                        state['pcm_bytes'] += len(chunk)
                    if first:
                        first = False
                        if item.turn is not None:
                            self._turn_speech_started.append(item.turn[3])
                        LOG.info('Voice independent output call=%s stage=first_pcm kind=%s seconds=%.3f',
                                 self.call.call_id, item.kind, self.clock() - started)
                        try:
                            if item.turn is not None:
                                self.call.transcript(item.turn, 'assistant', item.text)
                            else:
                                self.call.notice('PROCESSING_UPDATE', item.text)
                        except Exception as error:
                            # Transport failure must not suppress admitted speech.
                            LOG.warning('Voice independent output call=%s stage=transcript_failed kind=%s type=%s',
                                        self.call.call_id, item.kind, type(error).__name__)
        LOG.info('Voice independent output call=%s stage=tts_finished kind=%s queued_bytes=%d seconds=%.3f current=%s',
                 self.call.call_id, item.kind, queued, self.clock() - started,
                 self._active_speech_current(item, generation, lease))

    def _automatic_update(self):
        if self._bootstrap_state != 'ready':
            return None, None
        processing = getattr(self.call.dialog, 'processing', None)
        observed_at = getattr(self.call.dialog, 'processing_observed_at', None)
        if (not self._pending and type(processing) is dict
                and processing.get('source') == 'servicenow_processing'
                and processing.get('agentCompletionKnown') is False
                and type(observed_at) in (int, float) and math.isfinite(observed_at)
                and observed_at >= self.updates.started
                and 0 <= self.clock() - observed_at < 30
                and processing.get('messages')):
            label = processing['messages'][-1]
            prefix = 'ServiceNow meldet: '
            # Keep the complete source label; add only missing end punctuation.
            if type(label) is str and re.fullmatch(r'[^.!?\r\n]+[.!?]?', label):
                sentence = label if label.endswith(('.', '!', '?')) else label + '.'
                key = _progress_key(label)
                if (len(prefix + sentence) <= 120 and key
                        and key not in self._automatic_progress_seen and not _generic_processing_label(key)):
                    self._automatic_progress_seen.add(key)
                    return prefix + sentence, observed_at + 30
        return None, None

    async def _update_loop(self):
        while self._live():
            await asyncio.sleep(.2)
            self._update_speech_cursor()
            if (self._active_kind == 'processing' and self._active_output is not None
                    and not self._valid(self._active_output)):
                self.call.playback.interrupt()
                if self._synthesis_task is not None:
                    self._synthesis_task.cancel()
            if self._backend is None:
                continue
            if self.updates.due(self.clock(), queued_bytes=len(self.call.playback.data),
                    synthesizing=self.call.synthesis_active,
                    user_busy=(self.call.vad_active or self.call.recognition_active or not self.call.turns.empty()
                               or not self.call.recognized_turns.empty()),
                    output_pending=self.output_pending, local_busy=self._local_busy or not self._local_questions.empty()):
                # Keep unsolicited speech brief: a complete backend reply can
                # arrive while this audio is playing. Detailed status remains
                # available when the caller asks for it.
                text, expires_at = self._automatic_update()
                if text is None:
                    self.updates.quiet_since = self.clock()
                    continue
                self.updates.sent(self.clock())
                self._enqueue(text, kind='processing' if expires_at is not None else 'automatic',
                              request=self._request, expires_at=expires_at,
                              observation=getattr(self.call.dialog, 'observation_revision', 0))

    async def close(self):
        if self._closed:
            return
        self._closed = True
        self._dialogue_observation_state = None
        self._outputs.clear()
        self._backend_outputs.clear()
        for record in self._backend_receipts.values():
            if record['state'] in ('pending', 'active'):
                record['state'] = 'retired_by_call_close'
        self.call.playback.interrupt()
        self._context_pending = None
        self._context_snapshot = ''
        self._context_candidate = None
        self._context_covered.clear()
        self._supplements.clear()
        self._input_questions.clear()
        self._submission_onsets.clear()
        self._spoken_history.clear()
        self._incoming_turn = None
        current = asyncio.current_task()
        tasks = set(self._workers) | self._invalidations | self._observations
        if self._backend is not None:
            tasks.add(self._backend)
        tasks.discard(current)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self.conversation is not None:
            await self.conversation.close()
