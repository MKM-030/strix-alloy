"""Independent Native conversation while the existing VA business turn waits.

The VA remains the only business executor. Uncertain/data/confirmation input is
kept verbatim and submitted once, serially, at its next settled input boundary.
Read-only conversational questions take the independent local lane.
"""
import asyncio
from collections import deque
from dataclasses import dataclass, replace
import importlib.util
import logging
import math
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit
from types import SimpleNamespace

from conversation_repair import (classify_repair, conversational_snapshot,
                                 NATURAL_CONVERSATION_PROMPT, _polar, _pure_kind,
                                 _passive_signal)
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
    value = _progress_key(text)
    return bool(re.fullmatch(r'(?:ja(?: (?:genau(?: so)?|bitte|das stimmt|das ist richtig|'
        r'das ist korrekt))?|nein(?: danke)?|genau(?: so)?|richtig|korrekt|'
        r'ich bestätige(?: das)?|einverstanden)', value))


def _name_correction(text):
    value = _progress_key(text)
    return bool(re.search(r'\bname\b', value) and re.search(
        r'\b(?:falsch\w*|anders|nicht richtig|nicht korrekt|stimmt nicht|richtige name)\b', value))


def _name_control(boundary):
    return (type(boundary) is dict and boundary.get('source') == 'servicenow_input_control'
        and type(boundary.get('label')) is str
        and not re.search(r'\b(?:bestell\w*|abschick\w*|absend\w*)\b',
                          _progress_key(boundary['label']))
        and bool(re.search(
            r'\b(?:name\w*|vorname\w*|nachname\w*|schreibweise|buchstab\w*)\b',
            _progress_key(boundary['label']))))


def _mixed_negative(text):
    return bool(re.match(r'\s*nein\b[\s,:;]+\S+', text, re.IGNORECASE)) and not _polar_answer(text)


def _spelled_letters(text):
    # Detect letter chains only. Preserve and read back the complete raw input;
    # never join the letters into an assumed name or choose a first/last name.
    return bool(re.search(r'(?<!\w)[a-zäöüß](?:[- ,.;:/]+[a-zäöüß]){2,}(?!\w)',
                          text, re.IGNORECASE))


def _spelling_control(boundary):
    return (_name_control(boundary) and not _polar(boundary['label'])
        and bool(re.search(r'\b(?:buchstab\w*|schreibweise)\b',
                           _progress_key(boundary['label']))))


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


def _missing_name_rejection(text):
    # Recognize the rejection, never extract or approve a replacement name.
    parts = [_progress_key(part) for part in re.split(r'[.!?;]+', text) if part.strip()]
    patterns = (
        r'(?:(?:und|aber|nein) )?(?:das|dies) ist (?:der|ein) falsche[rn]? name',
        r'(?:(?:und|aber) )?(?:der|dieser|mein|sein|ihr) name ist (?:falsch|anders|nicht richtig|nicht korrekt)',
        r'(?:(?:und|aber) )?(?:der|dieser|mein|sein|ihr) name stimmt nicht',
        r'(?:das|so) ist nicht der richtige name')
    return (bool(parts) and any(re.search(r'\bname\b', part) for part in parts)
        and all(part == 'nein' or any(re.fullmatch(pattern, part) for pattern in patterns) for part in parts))


def _social_frustration(value):
    # Whole social utterances only; a supplied name, spelling or mixed request
    # containing a swear word must still reach the ordinary business FIFO.
    return bool(re.fullmatch(r'(?:fick (?:dich|deine mutter)|halt (?:die klappe|dein maul)|'
        r'das (?:ist (?:(?:doch|ja) )?(?:scheiße|scheisse|mist)|nervt(?: mich)?|regt mich auf)|'
        r'was soll (?:der|dieser) (?:scheiß|scheiss)|so funktioniert das nicht)', value))


def _question_kind(text):
    value = re.sub(r'[\s?!.,]+', ' ', text.casefold()).strip()
    if len(value) > 350 or len(value.split()) > 55 or re.search(r'\d|;', text):
        return None
    if _social_frustration(value):
        return 'frustration'
    # These complete questions contain no supplied name or approval. They can
    # be explained immediately; actual spelling/correction remains raw VA input.
    name = r'(?:(?:den|meinen|einen|ihren) )?(?:vollständigen )?(?:namen|vornamen|nachnamen)'
    if any(re.fullmatch(pattern, value) for pattern in (
            rf'(?:kann|darf|soll|muss) ich (?:(?:dir|ihnen) )?{name} (?:bitte )?buchstabieren(?: bitte)?',
            rf'wie (?:kann|soll|muss) ich {name} (?:am besten |richtig )?buchstabieren',
            rf'wie buchstabiere ich {name}(?: am besten| richtig)?')):
        return 'spelling_help'
    if re.fullmatch(rf'(?:warum|weshalb|wieso) (?:soll|muss) ich {name} '
                    r'(?:(?:noch einmal|nochmal|erneut) )?bestätigen', value):
        return 'name_help'
    # Mixed business data/actions remain verbatim VA input. Read-only German
    # paraphrases need no magic sentence and give Omni no execution authority.
    if (re.search(r'\b(?:nein|ja|korrektur|falsch|name|vorname|nachname|schreibweise|'
                r'buchstab\w*|korrigier\w*|bestell\w*|beauftrag\w*|stornier\w*|'
                r'änder\w*|aender\w*|verwende\w*|nimm|setz\w*|füge|fuege|'
                r'schick\w*|sende\w*|beantrag\w*|buche\w*|lösch\w*|loesch\w*|'
                r'bestätige|bestaetige|abschicken)\b', value)):
        return None
    status = {
        'gibt es schon etwas konkretes', 'gibt es schon etwas neues', 'wie ist der stand',
        'was ist der aktuelle stand', 'was weißt du sicher', 'was weisst du sicher',
        'was hat die prüfung ergeben', 'wie lange dauert das', 'warum dauert das so lange',
        'woran liegt die verzögerung', 'ist meine anfrage noch in bearbeitung',
        'kannst du schon abschließen', 'kannst du schon abschliessen', 'was passiert gerade',
        'gibt es einen zwischenstand', 'was bedeutet das für meine anfrage',
    }
    help_questions = {
        'was kannst du', 'was kannst du für mich tun', 'wie kannst du mir helfen',
        'wie funktioniert das', 'was brauchst du von mir', 'welche angaben brauchst du',
        'ich möchte erst verstehen welche angaben du brauchst',
        'erklär mir bitte den nächsten schritt etwas genauer',
        'was kannst du für die vorbereitung eines neuen mitarbeiters übernehmen',
    }
    if value in status:
        return 'status'
    question = re.search(r'\b(?:was|wie|woran|warum|weshalb|wieso|gibt es|liegt|'
                         r'kannst du|sag|sagen|erklär|erkläre|erklären)\b', value)
    progress = re.search(r'\b(?:stand|status|fortschritt|weit|bisher|inzwischen|ergebnis\w*|'
        r'rückmeldung\w*|rueckmeldung\w*|weißt|weisst|wei[sß]|wissen|dauert|dauer|'
        r'verzöger\w*|verzoeger\w*|warte\w*|passiert|konkretes|neues|bedeutet|'
        r'prüfung|pruefung|fertig|abschließ\w*|abschliess\w*|verfügbar|verfuegbar)\b', value)
    if question and progress or re.search(r'\bwas (?:heißt|heisst) das\b', value):
        return 'status'
    if value in help_questions or re.search(r'\b(?:was kannst du|wie kannst du|wie funktioniert|'
            r'welche angaben|was brauchst du|welche informationen|was muss ich wissen|'
            r'(?:erklär|erkläre|erklärst)\b.*\b(?:schritt|ablauf)|'
            r'(?:möchte|will)\b.*\bverstehen|wie geht\b.*\bweiter|'
            r'was\b.*\bnächste\w* schritt)\b', value):
        return 'help'
    # Open conversational questions need no fixed status/help phrase. Names,
    # dates, spellings, mixed changes and approvals have already been excluded.
    if re.match(r'^(?:warum|weshalb|wieso|was|wie|welche\w*|woher|worum|'
                r'kannst du|können sie|erklär\w*|erlaeuter\w*)\b', value):
        return 'help'
    return None


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


async def open_conversation(url, call_id, epoch, *, controller_url='', controller_token_file=''):
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
                                 build_servicenow_voice_context().system_prompt_fragment)
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
                             build_servicenow_voice_context().system_prompt_fragment)
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
class _Output:
    text: str
    turn: object
    epoch: int
    task_revision: int
    observation_revision: int | None
    kind: str
    request: int | None = None
    identity: object = None
    expires_at: float | None = None
    question_binding: object = None


class NativeDuplex:
    def __init__(self, call, *, context_publisher=None, context_reconciler=None,
                 conversation_factory=open_conversation, clock=time.monotonic):
        self.call, self.clock = call, clock
        if conversation_factory is open_conversation:
            self._factory = lambda url, call_id, epoch: open_conversation(url, call_id, epoch,
                controller_url=getattr(call.config, 'conversation_http_url', ''),
                controller_token_file=getattr(call.config, 'conversation_token_file', ''))
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
        self._model_failed = False
        self.epoch = 1
        self.task_revision = self.context_revision = 1
        self._request = 0
        self._reply_revision = 1
        self._public_findings = deque(maxlen=8)
        self._public_sequence = 0
        self._pending = deque()
        # Early data is context, never an answer to a control that arrives later.
        self._supplements = deque()
        self._correction_request = None
        self._name_correction_context = None
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
        self._incoming_turn = None
        self._backend_unavailable = False
        self._automatic_progress_seen = set()
        self._workers = set()
        self._invalidations = set()
        self._observations = set()
        self._closed = False
        self._last_input_generation = call.playback.generation
        self.updates = DurationUpdates(getattr(call.call_settings, 'filler_delay_seconds', None))

    @property
    def busy(self):
        return self._backend is not None or bool(self._pending)

    @property
    def pending_count(self):
        return len(self._pending)

    @property
    def output_pending(self):
        return bool(self._outputs)

    def _live(self):
        return not (self._closed or self.call.closed or self.call.closing or self.call.input_lost or self.call.failed)

    def _update_speech_cursor(self):
        state = self._speech
        if state is not None and not state['interrupted']:
            playback = self.call.playback
            state['accepted_samples'] = max(0, playback.accepted_samples - state['accepted_start'])
            state['emitted_samples'] = min(state['accepted_samples'],
                max(0, playback.emitted_samples - state['emitted_start']))

    def _question_current(self, state):
        if (state is None or not self._live() or self._pending
                or state['task_revision'] != self.task_revision):
            return False
        if state['source'] == 'greeting':
            return self._request == 0
        boundary = getattr(self.call.dialog, 'input_boundary', None)
        return (state['source'] in ('servicenow_input_control', 'local_clarification')
            and not (state['source'] == 'servicenow_input_control'
                     and self._correction_request == self._request)
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
        return (question, source, complete, state['binding'] if question else '',
                state['task_revision'] if question else None)

    def _begin_speech(self, item):
        self._update_speech_cursor()
        inherited = getattr(item, 'question_binding', None)
        question = source = binding = ''
        if self._question_current(inherited):
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
            accepted_start=self.call.playback.accepted_samples,
            emitted_start=self.call.playback.emitted_samples, accepted_samples=0,
            emitted_samples=0, complete=False, interrupted=False)
        if inherited is not None and self._question_current(inherited):
            state['control_label'] = inherited.get('control_label', inherited['question'])
        self._speech = state
        if question:
            self._spoken_question = state
        return state

    def _finish_speech(self, state, *, complete):
        self._update_speech_cursor()
        state['complete'] = complete and not state['interrupted']

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
                 expires_at=None, question_binding=None):
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
            observation, kind, request, identity, expires_at, question_binding))
        self._output_ready.set()
        return True

    def _valid(self, item):
        return (self._live() and item.epoch == self.epoch and item.task_revision == self.task_revision
                and (item.question_binding is None or self._question_current(item.question_binding))
                and (item.observation_revision is None or item.observation_revision ==
                     getattr(self.call.dialog, 'observation_revision', 0))
                and (item.request is None or item.request == self._request and self.busy)
                and (item.expires_at is None or self.clock() < item.expires_at and not self._pending)
                and (item.identity is None or self.conversation is not None and
                     self.conversation.is_current(item.identity)))

    def _current_public_findings(self):
        if self._pending:
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
        if self._pending or self._reply_revision != self.task_revision:
            return ''
        if self._request:
            if self._correction_request == self._request:
                return self._correction_question()
            boundary = getattr(self.call.dialog, 'input_boundary', None)
            return (boundary.get('label', '') if type(boundary) is dict
                and boundary.get('source') == 'servicenow_input_control' else '')
        return getattr(self.call.dialog, 'current_question', '')

    def _status(self):
        dialog = self.call.dialog
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

    def _help_fallback(self):
        question = self._current_question()
        base = ('Ich kann Angaben mit Ihnen klären und vorhandene Rückmeldungen verständlich erklären. '
                'ServiceNow führt den Vorgang und fragt notwendige Bestätigungen ab.')
        return base + (' Die aktuelle Rückfrage lautet: „' + question + '“' if question and len(question) <= 350 else
                       ' Welche Angabe oder welchen Schritt möchten Sie besprechen?')

    def _repeat_last_reply(self):
        replies = self._current_public_findings()
        if not replies:
            return 'Es liegt keine Rückmeldung zum Wiederholen vor. ' + self._status()
        quote, complete = self._excerpt(replies[-1].text)
        return (('Die letzte Rückmeldung von ServiceNow war: „' if complete else
                 'Ein Auszug aus der letzten Rückmeldung von ServiceNow war: „') + quote
                + '“ Eine abschließende Antwort auf die laufende Anfrage liegt weiterhin nicht vor.'
                if quote else self._status())

    async def _accept(self, turn):
        _, text, number, _, _ = turn
        if (number not in self.call.turn_controls and
                re.fullmatch(r'\s*(?:äh|ähm)[.!?,…]*\s*', text, re.IGNORECASE)):
            # A whole hesitation cannot express a topic, name or confirmation.
            # Keep single spelled Ä/M/A, em/emm and mixed name input verbatim.
            self.call.turn_contexts.pop(number, None)
            self._observe_raw(text)
            LOG.info('Voice independent input call=%s stage=hesitation_ignored', self.call.call_id)
            return
        if number not in self.call.turn_controls and _non_speech_annotation(text):
            self.call.turn_contexts.pop(number, None)
            LOG.info('Voice independent input call=%s stage=non_speech_annotation_ignored', self.call.call_id)
            return
        observed_onset = getattr(turn, 'duplex_onset', None)
        if observed_onset is not None:
            onset, overlapped = observed_onset
        else:
            onset = self._input_questions.get(turn[0], self._input_question_snapshot())
            overlapped = bool(self.call.synthesis_active or self.call.playback.data)
        # A casual overlap is not a request to erase the remaining output.
        # Real polar answers still go through the complete-control onset gate.
        bound_polar = (onset[1] == 'servicenow_input_control' and onset[2]
                       and _polar(onset[0]))
        if (overlapped or self.busy) and _passive_signal(text) and not (
                bound_polar and _pure_kind(text) == 'backchannel'):
            self.call.turn_contexts.pop(number, None)
            self._observe_raw(text)
            LOG.info('Voice independent input call=%s stage=backchannel_preserved', self.call.call_id)
            return
        if observed_onset is not None or turn[0] == self._last_input_generation:
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
        question, source, complete = self.question_context()
        boundary = getattr(self.call.dialog, 'input_boundary', None)
        label = (boundary.get('label', '') if type(boundary) is dict
                 and boundary.get('source') == 'servicenow_input_control' else '')
        bound_name_rejection = (_name_control(boundary)
            and (_mixed_negative(text) or _progress_key(text) == 'nein'))
        if self._request and _polar_answer(text) and (
                self._correction_request == self._request or label and _polar(label)):
            ready = (type(boundary) is dict and bool(label)
                     and onset == (label, 'servicenow_input_control', True,
                               boundary.get('businessRequestId', ''), self.task_revision)
                     and self._correction_request != self._request
                     and self._question_current(self._spoken_question))
            if not ready:
                self._retain_supplement(turn)
                self._reask_control(turn)
                return
            if _name_control(boundary) and not _progress_key(text).startswith('nein'):
                # Only a fresh positive answer to the fully emitted genuine
                # name control closes this local spelling-wait context.
                self._name_correction_context = None
        repair = classify_repair(text, question=question, question_source=source,
            question_complete=complete, business_started=bool(self._request),
            busy=self.busy, raw_history=tuple(self._raw))
        if repair is not None:
            self.call.turn_contexts.pop(number, None)
            if not repair.reply:
                return
            if _passive_signal(text):
                question_key = (question, source, self.task_revision,
                    boundary.get('businessRequestId') if type(boundary) is dict else None)
                if question_key == self._passive_question_reasked:
                    return
                self._passive_question_reasked = question_key
            binding = self._spoken_question if question else None
            self._enqueue(repair.reply, turn, kind='local',
                question_binding=binding if question and repair.reply.endswith(question) else None)
            if repair.resume_question and self._question_current(binding):
                self._enqueue(question, turn, kind='local', question_binding=binding)
            elif label and (not question or source == 'local_clarification'):
                # A caller can greet while the actual control is queued but
                # has not begun. Input invalidation must not lose that question.
                self._reask_control(turn)
            return
        kind = _question_kind(text)
        if kind == 'frustration':
            self.call.turn_contexts.pop(number, None)
            recent_rejection = any(_missing_name_rejection(item) for item in tuple(self._raw)[:-1])
            pending_rejection = any(_missing_name_rejection(item[1]) for item in self._pending)
            question = self._current_question()
            if recent_rejection and pending_rejection:
                response = ('Lassen Sie uns den Namen richtig aufnehmen. Wie lautet er? '
                            'Sie können ihn buchstabieren.')
            elif question and len(question) <= 350:
                response = ('Bleiben wir bei der aktuellen Rückfrage: „' + question +
                            '“ Soll ich sie näher erklären?')
            else:
                response = 'Ich höre, dass Sie verärgert sind. Was möchten Sie als Nächstes klären?'
            self._enqueue(response, turn, kind='local',
                observation=getattr(self.call.dialog, 'observation_revision', 0))
            return
        rejected_name = _missing_name_rejection(text) or bound_name_rejection
        clarification = self._correction_question()
        if self._backend_unavailable:
            self.call.turn_contexts.pop(number, None)
            repeat = re.sub(r'[\s?!.,]+', ' ', text.casefold()).strip() in {
                'wiederhole bitte die letzte rückmeldung', 'bitte wiederhole die letzte antwort',
                'wiederhole das bitte', 'kannst du das bitte wiederholen'}
            if kind is None and not repeat:
                self.task_revision += 1
                self._outputs.clear()
                self._pending.append(turn)
            self._enqueue(clarification if rejected_name else self._repeat_last_reply() if repeat else self._status(),
                          turn, kind='recovery')
            return
        if kind is not None:
            self.call.turn_contexts.pop(number, None)
            if self._local_questions.full():
                self._enqueue(self._status(), turn, kind='status')
            else:
                self._local_questions.put_nowait((turn, kind, self.epoch))
            return
        if self._backend is not None and not self._backend.done():
            if _name_correction(text) or bound_name_rejection:
                self._remember_name_correction(turn, self._request)
                self._correction_request = self._request
                self._spoken_question = None
            self._retain_supplement(turn)
            if _name_correction(text) or bound_name_rejection:
                self._enqueue(clarification, turn, kind='local')
            return
        corrective = (_name_correction(text) or bool(re.match(
            r'\s*nein\b[\s,:;]+\S+', text, re.IGNORECASE)))
        if (label and _polar(label) and self._correction_request != self._request
                and not corrective
                and onset != (label, 'servicenow_input_control', True,
                              boundary.get('businessRequestId', ''), self.task_revision)):
            self._retain_supplement(turn)
            self._reask_control(turn)
            return
        self._spoken_question = self._interrupted_speech = None
        if rejected_name:
            self._remember_name_correction(turn, self._request + 1)
        elif (self._name_correction_context is not None
              and self._name_correction_context['request'] == self._request):
            # A fresh caller answer goes raw to ServiceNow. It is not local
            # name normalization or approval, even if it contains only letters.
            self._name_correction_context.update(request=self._request + 1,
                needs_spelling=False, wait_sent=False)
        if self._request:
            self.task_revision += 1
            self._outputs.clear()
        was_busy = self.busy
        self._pending.append(turn)
        if was_busy:
            # The original is queued, never rewritten or posted as business
            # input to a busy VA; the optional context channel is separate.
            self._queue_context_update(turn)
        if rejected_name:
            self._enqueue(clarification, turn, kind='local')

    @staticmethod
    def _correction_question():
        return ('Bitte buchstabieren Sie zuerst nur den Vornamen. '
                'Den Nachnamen klären wir danach.')

    def _remember_name_correction(self, turn, request):
        self._name_correction_context = dict(request=request, original=turn,
            needs_spelling=True, spelling_turns=[], offered=set(), wait_sent=False)

    def _offer_held_spelling(self, turn):
        context = self._name_correction_context
        boundary = getattr(self.call.dialog, 'input_boundary', None)
        if (context is None or context['request'] != self._request
                or not _spelling_control(boundary)):
            return
        for original in context['spelling_turns']:
            if id(original) in context['offered'] or len(original[1]) > 600:
                continue
            text = ('Sie hatten bereits buchstabiert: „' + original[1] +
                    '“ Bitte antworten Sie jetzt mit der Schreibweise passend zur aktuellen Frage; '
                    'korrigieren Sie sie bei Bedarf.')
            if self._enqueue(text, turn, kind='local'):
                context['offered'].add(id(original))

    def _retain_supplement(self, turn):
        self._supplements.append((turn, self.call.turn_contexts.get(turn[2])))
        self._queue_context_update(turn)
        context = self._name_correction_context
        if (context is not None and context['request'] == self._request
                and _spelled_letters(turn[1]) and not _mixed_negative(turn[1])):
            context['spelling_turns'].append(turn)
            if len(turn[1]) <= 600:
                self._enqueue('Ich habe diese Buchstaben aufgenommen: „' + turn[1] +
                    '“ Ich halte sie für die nächste Namensrückfrage fest.', turn, kind='local')
        LOG.info('Voice independent input call=%s stage=held_context turn=%s request=%s',
                 self.call.call_id, turn[2], self._request)

    def _reask_control(self, turn):
        boundary = getattr(self.call.dialog, 'input_boundary', None)
        if type(boundary) is not dict or boundary.get('source') != 'servicenow_input_control':
            if self._correction_request == self._request:
                self._enqueue(self._correction_question(), turn, kind='local')
            return
        label = boundary.get('label', '')
        if not label:
            return
        correcting = self._correction_request == self._request
        question = self._correction_question() if correcting else label
        binding = dict(question=question, control_label=label,
            source='local_clarification' if correcting else 'servicenow_input_control',
            binding=boundary.get('businessRequestId', ''), task_revision=self.task_revision)
        self._enqueue(question, turn, kind='local', question_binding=binding)

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
        confirmations = {'ja', 'nein', 'ok', 'okay', 'genau', 'richtig', 'korrekt',
            'bestätigt', 'bestätigen', 'ich bestätige', 'ich bestätige das',
            'einverstanden', 'ja bitte', 'ja genau', 'nein danke'}
        retirable = all(id(item) in self._context_covered and
            re.sub(r'[\s.!?,;:]+', ' ', item[1].casefold()).strip() not in confirmations
            for item in prefix + tuple(item[0] for item in supplements))
        # Coalesce unsent revisions; the newest snapshot still contains every
        # raw update in order. Only one context request may be in flight.
        self._context_candidate = {'request': self._request,
            'revision': self._context_publish_revision, 'snapshot': snapshot,
            'task_revision': self.task_revision, 'prefix': prefix, 'supplements': supplements,
            'retirable': retirable,
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
        """Retire only exactly covered queued input after an exact prompt receipt."""
        item = self._context_candidate
        if item is None or self._context_reconciler is None or not item['retirable']:
            return False
        prefix, supplements, epoch = item['prefix'], item['supplements'], self.epoch

        def current():
            incoming = self._incoming_turn
            return (self._live() and self._context_candidate is item
                and item['request'] == self._request
                and item['revision'] == self._context_publish_revision
                and item['task_revision'] == self.task_revision and self.epoch == epoch
                and bool(prefix or supplements) and len(self._pending) == len(prefix)
                and all(left is right for left, right in zip(self._pending, prefix))
                and len(self._supplements) == len(supplements)
                and all(left is right for left, right in zip(self._supplements, supplements))
                and not (incoming is not None and incoming.done())
                and self.call.recognized_turns.empty())

        if not current():
            return False
        try:
            await asyncio.wait_for(item['done'].wait(), 12)
            if not current():
                return False
            ack = item['ack']
            boundary = getattr(self.call.dialog, 'input_boundary', None)
            keys = ('contextRequestId', 'businessRequestId', 'conversationId', 'executionPlanId')
            if (type(ack) is not dict or ack.get('contextStored') is not True
                    or ack.get('revision') != item['revision']
                    or any(type(ack.get(key)) is not str or not re.fullmatch(r'[0-9a-f]{32}', ack[key])
                           for key in keys)
                    or type(boundary) is not dict
                    or boundary.get('source') != 'servicenow_input_control'
                    or boundary.get('businessRequestId') != ack['businessRequestId']):
                return False
            status = await self._context_reconciler(item['revision'])
            if (not current() or getattr(self.call.dialog, 'input_boundary', None) is not boundary
                    or type(status) is not dict or status.get('state') != 'context_prompt_status'
                    or status.get('revision') != item['revision']
                    or status.get('contextStored') is not True
                    or status.get('inputBoundaryConfirmed') is not True
                    or status.get('promptIncluded') is not True or status.get('ingested') is not True
                    or any(status.get(key) != ack[key] for key in keys)):
                return False
        except asyncio.CancelledError:
            raise
        except Exception as error:
            LOG.warning('Voice independent context stage=status_unavailable type=%s', type(error).__name__)
            return False
        for pending in prefix:
            self._pending.popleft()
            self._context_covered.discard(id(pending))
            self.call.turn_contexts.pop(pending[2], None)
        for original, _ in supplements:
            self._supplements.popleft()
            self._context_covered.discard(id(original))
            self.call.turn_contexts.pop(original[2], None)
        self._context_candidate = None
        if self._context_pending is item:
            self._context_pending = None
        self.task_revision += 1
        self._reply_revision = self.task_revision
        self._outputs.clear()
        latest = boundary.get('label') or (replies[-1] if prefix and replies else '')
        # Exact prompt/input proof can advance this actual boundary callback;
        # unrelated earlier replies retain their old revision and stay fenced.
        self._public_findings = deque((replace(item, task_revision=self.task_revision)
            if item.request == self._request and item.text == latest else item
            for item in self._public_findings), maxlen=8)
        self._enqueue(latest, turn, kind='backend')
        LOG.info('Voice independent context stage=prompt_included revision=%d retired=%d supplements=%d; '
                 'no task success or approval inferred', item['revision'],
                 len(prefix) + len(supplements), len(supplements))
        return True

    async def _business(self, turn):
        _, text, number, _, _ = turn
        revision = self.task_revision
        self._request += 1
        name_context = self._name_correction_context
        self._correction_request = (self._request if name_context is not None
            and name_context['request'] == self._request and name_context['needs_spelling'] else None)
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
            if revision == self.task_revision and not self._pending:
                admitted = self._enqueue(reply, turn, kind='backend')
                if admitted:
                    admitted_replies.add(reply)
                # Only an admitted audible replacement owns playback. Stale
                # or suppressed callbacks must leave current local speech intact.
                if admitted and self._active_kind == 'conversation':
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
        context = self.call.turn_contexts.pop(number, None)
        if context is None:
            await self.call.dialog.turn(text, on_reply=on_reply)
        else:
            await self.call.dialog.turn(text, on_reply=on_reply, voice_context=context)
        label = input_label()
        if label:
            # This label is an observed ServiceNow input control, not a locally
            # inferred question or approval. A callback is not guaranteed.
            if label not in replies:
                self.call.dialog.record_public_reply(label)
            if self._correction_request == request and not _spelling_control(self.call.dialog.input_boundary):
                # Preserve the old callback as backend evidence; do not repeat
                # a name the caller has already explicitly rejected.
                self._reask_control(turn)
                return
            if _spelling_control(self.call.dialog.input_boundary):
                self._correction_request = None
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
        if revision == self.task_revision and not self._pending:
            self._offer_held_spelling(turn)
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

    async def run(self):
        for name, coroutine in (('speaker', self._speak_loop()), ('dialogue', self._local_loop()),
                                ('updates', self._update_loop())):
            self._start_worker(name, coroutine)
        if self._context_publisher is not None:
            self._start_worker('context', self._context_loop())
        incoming = None
        try:
            while self._live():
                if not self._backend_unavailable and self._backend is None and self._pending:
                    self._backend = asyncio.create_task(self._business(self._pending.popleft()))
                if incoming is None:
                    incoming = asyncio.create_task(self.call.wait_for_user_turn())
                    self._incoming_turn = incoming
                waiting = {incoming}
                if self._backend is not None:
                    waiting.add(self._backend)
                ready, _ = await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
                if self._backend is not None and self._backend in ready:
                    try:
                        self._backend.result()
                        if getattr(self.call.dialog, 'conversation_ended', False):
                            raise BackendConversationEnded('ServiceNow ended this conversation')
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
                    self._enqueue(self._status() if kind == 'status' else self._help_fallback(), turn)
            finally:
                self._local_busy = False
                self._local_questions.task_done()

    def _dialogue_snapshot(self, turn, epoch):
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
            busy=self.busy and not backend_closed and not self._backend_unavailable)
        if self._interrupted_speech is not None:
            snapshot['capability_limits'] += (
                'Die vorige Sprachausgabe wurde unterbrochen. Behandle deren ungesprochenen '
                'Rest nicht als gehört. Der Audiozeiger belegt nur vom Server ausgegebenes PCM, '
                'keine bestätigte Wiedergabe am Telefon. Antworte auf die neue Eingabe im '
                'aktuellen Zusammenhang; setze alten Text nicht blind fort.',)
        snapshot['capability_limits'] += (
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
        if (isinstance(processing, dict) and processing.get('messages') and not self._pending
                and not backend_closed and not self._backend_unavailable):
            fact = {name: key[name] for name in ('call_id', 'task_id', 'task_revision',
                    'context_revision', 'observation_revision')}
            fact.update(evidence_id='processing-label-' + str(processing['revision']),
                source_event='servicenow_processing_presentation', sequence=processing['revision'],
                observed_at=max(0, self.clock() - processing.get('ageSeconds', 0)),
                text=processing['messages'][-1], superseded=False)
            snapshot['public_findings'] += (fact,)
        snapshot = append_servicenow_context(snapshot, build_servicenow_voice_context(
            self.call.call_settings, dict(business_available=not self._backend_unavailable,
                business_busy=self.busy, backend_closed=backend_closed,
                context_updates_enabled=self._context_publisher is not None,
                pending_count=len(self._pending), supplement_count=len(self._supplements),
                question_source=question_source)))
        return key, snapshot, observation

    def _admit_conversation(self, candidate, turn, epoch, observation, snapshot):
        if (epoch != self.epoch or observation != getattr(self.call.dialog, 'observation_revision', 0)):
            return False
        # Read-only wording uses bound public observations; it supplies no
        # business evidence or completion authority. These guards hold
        # obvious success/control/identifier leakage, not prove semantics.
        text = candidate.text.strip()
        forbidden = re.search(r'(?i)(?:<|https?://|\b(?:public-reply|processing-label)-|'
            r'\b[0-9a-f]{16,}\b|\b(?:analysis|reasoning|tool_call|'
            r'bestellt|abgeschlossen|genehmigt|freigegeben|erledigt|bestätigt)\b)', text)
        source = ' '.join(fact['text'] for fact in snapshot['public_findings'])
        unbound_numbers = any(number not in re.findall(r'\d+', source)
                              for number in re.findall(r'\d+', text))
        identifiers = (self.call.call_id, self.call.call_id + '-va', turn[3],
                       getattr(candidate.identity, 'server_session_id', ''),
                       getattr(candidate.identity, 'socket_instance', ''))
        if (not text or len(text) > 1200 or forbidden or unbound_numbers or
                any(value and value in text for value in identifiers) or
                not self.conversation.is_current(candidate.identity)):
            return False
        return self._enqueue(text, turn, kind='conversation', observation=observation,
                      identity=candidate.identity)

    def _queue_dialogue_observation(self):
        observe = getattr(self.conversation, 'observe', None)
        if (not callable(observe) or self._dialogue_turn is None or self._closed
                or len(self._observations) >= 8):
            return
        try:
            key, snapshot, _ = self._dialogue_snapshot(self._dialogue_turn, self.epoch)
        except Exception:
            return
        async def apply():
            try:
                await observe(snapshot, key)
            except Exception as error:
                LOG.warning('Voice dialogue observation unavailable type=%s', type(error).__name__)
        task = asyncio.create_task(apply())
        self._observations.add(task)
        task.add_done_callback(self._observations.discard)

    def _revoke_dialogue_output(self, turn):
        self._outputs = deque(item for item in self._outputs
            if not (item.kind == 'conversation' and item.turn is not None and item.turn[3] == turn[3]))
        active = self._active_output
        if active is not None and active.kind == 'conversation' and active.turn[3] == turn[3]:
            self.call.playback.interrupt()
            if self._synthesis_task is not None:
                self._synthesis_task.cancel()

    async def _general_help(self, turn, epoch, kind='help'):
        if kind == 'status':
            # An explicit progress question needs observed state, not a model's
            # guess about hidden agent work or the meaning of silence.
            self._enqueue(self._status(), turn, kind='status',
                observation=getattr(self.call.dialog, 'observation_revision', 0))
            return
        if kind in ('spelling_help', 'name_help'):
            # Explain the existing readback procedure without waiting for a
            # model or changing any current ServiceNow data/approval state.
            text = ('Gern. Nennen Sie die Buchstaben bitte einzeln. Bei Bedarf können Sie '
                    'Vor- und Nachnamen getrennt buchstabieren. Danach lesen wir die '
                    'Schreibweise zur Bestätigung vor.' if kind == 'spelling_help' else
                    'Damit ein Hörfehler nicht weitergegeben wird, lesen wir den Namen '
                    'noch einmal vor. Bestätigen Sie ihn nur, wenn die vollständige '
                    'Schreibweise stimmt.')
            self._enqueue(text, turn, kind='local',
                observation=getattr(self.call.dialog, 'observation_revision', 0))
            return
        fallback = self._status if kind == 'status' else self._help_fallback
        def emit_fallback():
            self._enqueue(fallback(), turn, kind='status' if kind == 'status' else 'local',
                observation=getattr(self.call.dialog, 'observation_revision', 0))
        if self._model_failed:
            emit_fallback()
            return
        try:
            if self._invalidations:
                await asyncio.gather(*tuple(self._invalidations), return_exceptions=True)
            if self.conversation is None:
                self.conversation = await self._factory(self.call.config.conversation_ws_url,
                                                        self.call.call_id, self.epoch)
            if epoch != self.epoch:
                return
            if self.conversation.output_epoch < self.epoch:
                await self.conversation.invalidate(self.epoch, 'input during connection')
            self._dialogue_turn = turn
            key, snapshot, observation = self._dialogue_snapshot(turn, epoch)
            admitted = 0
            async def sentence(candidate):
                nonlocal admitted
                if not self._admit_conversation(candidate, turn, epoch, observation, snapshot):
                    raise ValueError('Conversation sentence release rejected')
                admitted += 1
            streaming = getattr(self.conversation, 'sentence_streaming', False)
            if streaming:
                candidate = await self.conversation.respond(turn[1], snapshot, key, on_sentence=sentence)
            else:
                candidate = await self.conversation.respond(turn[1], snapshot, key)
            if epoch != self.epoch:
                return
            if observation != getattr(self.call.dialog, 'observation_revision', 0):
                self._revoke_dialogue_output(turn)
                return
            if candidate.failure is not None:
                self._revoke_dialogue_output(turn)
                if candidate.failure == 'superseded':
                    return
                if getattr(getattr(self.conversation, 'controller_transport', None), 'transient_busy', False):
                    # Admission429 ends only this optional model attempt. A new
                    # user question may use a fresh session; never retry input.
                    await self.conversation.close()
                    self.conversation = None
                else:
                    self._model_failed = True
                emit_fallback()
                return
            if not streaming and not self._admit_conversation(candidate, turn, epoch, observation, snapshot):
                emit_fallback()
            elif streaming and not admitted:
                emit_fallback()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._revoke_dialogue_output(turn)
            if getattr(getattr(self.conversation, 'controller_transport', None), 'transient_busy', False):
                await self.conversation.close()
                self.conversation = None
            else:
                self._model_failed = True
            LOG.warning('Voice independent dialogue stage=unavailable type=%s', type(error).__name__)
            if epoch == self.epoch:
                emit_fallback()

    async def _speak_loop(self):
        while self._live():
            if not self._outputs:
                self._output_ready.clear()
                await self._output_ready.wait()
                continue
            item = self._outputs[0]
            if not self._valid(item):
                self._outputs.popleft()
                continue
            if (self.call.playback.data or self.call.synthesis_active or self.call.vad_active
                    or self.call.recognition_active or not self.call.turns.empty()):
                await asyncio.sleep(.02)
                continue
            self._outputs.popleft()
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
                speech_complete = self._valid(item) and generation == self.call.playback.generation
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
                self.call.synthesis_active = False
                self._active_kind = None
                self._active_output = None
                self._synthesis_task = None

    async def _synthesize(self, item, generation):
        started = self.clock()
        queued = 0
        first = True
        async for chunk in self.call.speech.synthesize(item.text):
            if not self._valid(item) or generation != self.call.playback.generation:
                break
            while len(self.call.playback.data) > 48000 and self._valid(item):
                await asyncio.sleep(.02)
            if self._valid(item) and generation == self.call.playback.generation:
                if chunk and self.call.playback.put(chunk, generation):
                    queued += len(chunk)
                    if first:
                        first = False
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
                 self._valid(item) and generation == self.call.playback.generation)

    def _automatic_update(self):
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
            # Use the complete source sentence; never truncate a possible result.
            if (type(label) is str and len(prefix + label) <= 120
                    and re.fullmatch(r'[^.!?\r\n]+[.!?]', label)):
                key = _progress_key(label)
                if key and key not in self._automatic_progress_seen and not _generic_processing_label(key):
                    self._automatic_progress_seen.add(key)
                    return prefix + label, observed_at + 30
        return None, None

    async def _update_loop(self):
        while self._live():
            await asyncio.sleep(.2)
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
                    output_pending=bool(self._outputs), local_busy=self._local_busy or not self._local_questions.empty()):
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
        self._outputs.clear()
        self._context_pending = None
        self._context_snapshot = ''
        self._context_candidate = None
        self._context_covered.clear()
        self._supplements.clear()
        self._input_questions.clear()
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
