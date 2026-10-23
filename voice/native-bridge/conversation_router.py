"""Scope-bound, bounded dialogue proposals; no business execution authority."""

import asyncio
import http.client
import ipaddress
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from business_tasks import Agent, StoreInvalid, bounded_identifier
from route_proposal import ProposalContract, RouteProposal, PRODUCTION_SYSTEM_PROMPT


INTENTS = frozenset({"status_query", "clarification", "amend_task", "new_task",
                     "stop_speaking", "cancel_task", "uncertain", "continue_task"})
_SAFE_REPLY = "Bitte präzisiere, welche Aufgabe oder welchen Agenten du meinst."
_MAX_CONTEXT_BYTES = 12000
_MAX_REQUEST_BYTES = 16384
_MAX_RESPONSE_BYTES = 8192
_MAX_ROUTE_BYTES = 2048
_TERMINAL = frozenset(('cancel_requested', 'cancelled', 'succeeded', 'failed', 'outcome_unknown'))


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
        # Callers may mutate the supplied lists after construction; recheck scope at use.
        self.__post_init__()
        contract = ProposalContract(self.tasks, self.agents)
        references = {v: k for k, v in contract.task_refs.items()}
        tasks = []
        for task in self.tasks:
            item = {"task_ref": references[task["task_id"]]}
            for key, limit in (("state", 32), ("objective", 500), ("open_question", 4000), ("agent_alias", 128)):
                value = task.get(key)
                if isinstance(value, str):
                    item[key] = value[:limit]
                    if len(value) > limit:
                        item[key + '_truncated'] = True
            item['pending_delivery'] = task.get('pending_delivery') is True
            item['context_version'] = task.get('context_version')
            for key in ('previous_question', 'previous_question_version', 'previous_question_id',
                        'previous_question_source', 'previous_operation_id', 'previous_operation_version',
                        'previous_operation_state', 'latest_operation_id', 'latest_operation_version',
                        'latest_operation_state'):
                if key in task:
                    item[key] = task[key]
            item['question_kind_local'] = ConversationRouter._answer_kind(task.get('open_question') or '')
            tasks.append(item)
        data = {
            "scope": "current_call",
            "tasks": tasks,
            "focus_task_ref": references.get(self.focus_task_id, ""),
            "last_question": self.last_question,
            "question_task_ref": references.get(self.question_task_id, ""),
            "question_id": self.question_id, "question_source": self.question_source,
            "question_version": self.question_version,
            "workflow_task_ref": references.get(self.workflow_task_id, ""),
            "agents": [{"alias": a.alias, "name": a.name, "description": a.description,
                        "supported_intents": list(a.supported_intents),
                        "routing_aliases": list(a.routing_aliases),
                        "allowed_intents": [k for k, v in a.capabilities.items() if v]} for a in self.agents],
        }
        if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > _MAX_CONTEXT_BYTES:
            raise StoreInvalid("routing context too large")
        return data


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
        data = context.model_data()
        request = {"model": self.model, "messages": [
            {"role": "system", "content": PRODUCTION_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"utterance": text, "context": data}, ensure_ascii=False)}],
            "temperature": 0, "max_tokens": 128,
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "route", "strict": True,
                "schema": ProposalContract(context.tasks, context.agents).schema()}}}
        payload = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(payload) > _MAX_REQUEST_BYTES:
            raise ValueError("conversation request too large")
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

    @staticmethod
    def _mentions(text, label):
        return bool(label and re.search(r'(?<![\w-])' + re.escape(label) + r'(?![\w-])', text, re.I))

    @classmethod
    def _agents(cls, context, text):
        return [a for a in context.agents if any(cls._mentions(text, label)
                for label in (a.alias, a.name, *a.routing_aliases))]

    @classmethod
    def _reference(cls, context, text):
        """Return (unique explicit task, conflicting/unknown reference). Never use focus."""
        known = {t['task_id'] for t in context.tasks}
        matches = {key for key in known if cls._mentions(text, key)}
        # ID-shaped references, not ordinary dates/room numbers, plus explicit ID markers.
        referenced = set(re.findall(r'(?<![\w-])(?:[a-z][a-z0-9_-]*\d+[a-z0-9_-]*|[0-9a-f]{8}-[0-9a-f-]{27,})(?![\w-])', text, re.I))
        for pattern in (
            r'\b(?:aufgabe|auftrag|task|ticket)\s+(?:id|nummer|nr\.?|#|:)\s*([a-z0-9][a-z0-9_-]{1,127})\b',
            r'\b(?:id|nummer|nr\.?)\s+([a-z0-9][a-z0-9_-]{1,127})\b',
            r'(?<!\w)#([a-z0-9][a-z0-9_-]{1,127})\b',
        ):
            referenced.update(re.findall(pattern, text, re.I))
        if any(v.casefold() not in {k.casefold() for k in known} for v in referenced):
            return '', True
        agents = cls._agents(context, text)
        if agents:
            targets = {t['task_id'] for t in context.tasks if t.get('agent_alias') in {a.alias for a in agents}}
            if len(agents) != 1 or len(targets) != 1 or (matches and matches != targets):
                return '', True
            matches = targets
        # A complete persisted task name/objective is a reference; partial word overlap is not.
        named = {t['task_id'] for t in context.tasks if cls._mentions(text, t.get('objective', ''))}
        if named:
            if matches and named != matches:
                return '', True
            matches = named
        return (next(iter(matches)), False) if len(matches) == 1 else ('', bool(matches))

    @classmethod
    def _target(cls, context, text, *, allow_focus=False):
        target, conflict = cls._reference(context, text)
        if conflict or target:
            return target
        if allow_focus and context.focus_task_id:
            return context.focus_task_id
        return context.tasks[0]['task_id'] if len(context.tasks) == 1 else ''

    @staticmethod
    def _clarify(context=None):
        labels = ', '.join((a.name or a.alias) for a in context.agents) if context else ''
        if context and not labels:
            labels = ', '.join(t['task_id'] for t in context.tasks)
        return Route('clarification', reply=_SAFE_REPLY + (' Verfügbar: ' + labels + '.' if labels else ''))

    @staticmethod
    def _question(context):
        task = next((t for t in context.tasks if t['task_id'] == context.question_task_id), None)
        plausible = [t for t in context.tasks if t.get('open_question') and
                     not t.get('pending_delivery') and t.get('state') not in _TERMINAL]
        if (not task or task.get('state') in _TERMINAL or task.get('pending_delivery')
                or not context.last_question or context.question_version is None
                or task.get('context_version') != context.question_version
                or task.get('open_question') != context.last_question
                or len(plausible) != 1):
            return None
        return task

    @staticmethod
    def _answer_kind(question):
        question = question.strip().casefold()
        # German polar questions put a finite verb before the subject. Detect
        # that form independently of the field being confirmed, including each
        # clause in a compound prompt. Wh words request a value instead; mixing
        # those requests with a polar clause cannot establish one answer type.
        wh = bool(re.search(r'\b(?:wer|wen|wem|wessen|was|wann|wo|wohin|woher|wie|welch\w*|who|what|which|where|when|how)\b', question))
        requested = bool(re.search(r'\b(?:nenn\w*|angeb\w*|geben sie|gib|mitteil\w*|teilen sie|sag\w*|schreib\w*|buchstab\w*)\b', question))
        finite = (r'ist|sind|bin|bist|seid|war|waren|wäre|wären|'
                  r'kann|kannst|können|könnt|könnte|könnten|'
                  r'darf|darfst|dürfen|dürft|muss|musst|müssen|müsst|'
                  r'hat|hast|haben|habt|wird|wirst|werden|werdet|wurde|wurden|'
                  r'möchte|möchtest|möchten|möchtet|will|willst|wollen|wollt|'
                  r'soll|sollst|sollen|sollt|stimmt|stimmen|passt|passen|'
                  r'lautet|lauten|entspricht|entsprechen|gilt|gelten|trifft|treffen')
        polar = bool(re.search(r'(?:^|[,?.!;]\s*)(?:bitte[, ]+)?(?:' + finite + r')\b', question))
        confirmation = bool(re.search(r'ja.{0,12}nein|bestätigen sie|bestätigst du|einverstanden|fortfahren|\b(?:do|would|are) you\b', question))
        tag = bool(re.search(r',\s*(?:oder|richtig|korrekt|stimmt das|nicht wahr)\s*\?$', question))
        first_clause = re.split(r'[,;?.!]', question, maxsplit=1)[0]
        clause_wh = bool(re.search(r'\b(?:wer|wen|wem|wessen|was|wann|wo|wohin|woher|wie|welch\w*)\b', first_clause))
        correctness = not clause_wh and bool(re.search(
            r'\b(?:stimmt|stimmen|passt|passen|entspricht|entsprechen)\b|'
            r'\b(?:ist|sind)\b.*\b(?:korrekt|richtig|zutreffend|bestätigt|in ordnung)\b', first_clause))
        if polar or confirmation or tag or correctness:
            return 'ambiguous' if wh or requested else 'yes_no'
        value_groups = (r'\bnamen?\b|vorname|nachname', r'datum|termin|welchem tag|wann|\bdate\b',
                        r'liefer(?:ort|adresse|anschrift)|wohin', r'vorgesetzt|manager|führungskraft')
        if sum(bool(re.search(pattern, question)) for pattern in value_groups) > 1:
            return 'ambiguous'
        if re.search(r'buchstab|spell', question):
            return 'spelling'
        # A noun alone inside an unfamiliar sentence is insufficient evidence of
        # a value request. Preserve explicit wh questions, imperative requests and
        # short field prompts; other noun-bearing forms remain conservative.
        short_field = bool(re.fullmatch(r'(?:(?:ihr\w*|dein\w*|your|der|die|das)\s+)?(?:vollständige\w*\s+)?(?:namen?|vorname|nachname|datum|termin|lieferort|lieferadresse|manager|führungskraft|address|date)\s*[?.:]?', question))
        if not (wh or requested or short_field):
            field = re.search(r'\bnamen?\b|vorname|nachname|datum|termin|liefer(?:ort|adresse|anschrift)|manager|führungskraft|vorgesetzt|\bdate\b', question)
            return 'ambiguous' if field else ''
        if re.search(r'liefer(?:ort|adresse|anschrift)|lieferung.*(?:wo|adresse)|delivery.*(?:location|address)|wohin', question):
            return 'location'
        if re.search(r'vorgesetzt|manager|führungskraft', question):
            return 'manager'
        if re.search(r'\bnamen?\b|heißen|heissen|vorname|nachname', question):
            return 'name'
        if re.search(r'datum|termin|welchem tag|wann|\bdate\b', question):
            return 'date'
        return ''

    @staticmethod
    def _matches_answer(text, kind):
        value = text.strip().rstrip('.!')
        if kind != 'yes_no' and re.fullmatch(r'ja|nein|nee|j[aä]', value, re.I):
            return False
        if kind == 'yes_no':
            return bool(re.fullmatch(r'ja|nein|nee|j[aä]', value, re.I))
        if kind == 'spelling':
            return bool(re.fullmatch(r'[A-Za-zÄÖÜäöü](?:[ -][A-Za-zÄÖÜäöü]){1,39}', value))
        if kind in ('name', 'manager'):
            value = re.sub(r'^(?:mein name ist|ich heiße|ich heisse|der name ist)\s+', '', value, flags=re.I)
            return bool(re.fullmatch(r"[A-ZÄÖÜ][a-zäöüß]+(?:[-'’ ][A-ZÄÖÜ][a-zäöüß]+){0,5}", value)) and value.casefold() not in ('ja', 'nein', 'hallo', 'danke', 'bitte', 'status')
        if kind == 'date':
            return bool(re.fullmatch(r'(?:am\s+)?(?:\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?\.?|\d{4}-\d{2}-\d{2}|\d{1,2}\.?(?:\s+)(?:januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)(?:\s+\d{4})?)', value, re.I))
        if kind == 'location':
            return len(value) <= 300 and bool(re.fullmatch(r'[\wÄÖÜäöüß .,/()\-]+', value)) and len(value.split()) <= 20
        return False

    @classmethod
    def _unsafe_control(cls, text):
        return bool(cls._quoted_ranges(text) or re.search(r'\b(?:nicht|kein\w*|niemals|wenn|falls|würde|würdest|könnte|hypothetisch|zitiert|sagte|bedeutet|heißt|heisst|alle|beide|irgendein\w*)\b|einen der|eine der', text, re.I))

    @classmethod
    def _affirmative_cancel(cls, context, text):
        """Validate one whole affirmative clause, not merely a cancellation prefix."""
        labels = {t['task_id'] for t in context.tasks}
        labels.update(t.get('objective', '') for t in context.tasks)
        labels.update(label for a in context.agents for label in (a.alias, a.name, *a.routing_aliases))
        # Replace complete registered references before checking grammar, preserving
        # legitimate multiword task names without allowing extra unresolved objects.
        labels.discard('')
        if labels:
            pattern = r'(?<![\w-])(?:' + '|'.join(re.escape(v) for v in sorted(labels, key=len, reverse=True)) + r')(?![\w-])'
            text = re.sub(pattern, '<target>', text, flags=re.I)
        text = re.sub(r'\s+', ' ', text.strip()).casefold()
        article = r'(?:(?:die|den|das|meine[nrs]?|diese[nrs]?) )?'
        noun = r'(?:aufgabe|auftrag|bestellung|ticket)'
        target = article + r'(?:' + noun + r' (?:(?:id|nummer|nr\.?) )?)?<target>'
        target = r'(?:' + target + '|' + article + noun + ')'
        polite = r'(?:bitte )?'
        commands = (
            polite + r'stornier(?:e|en)? ' + polite + target + r'(?: bitte)?',
            polite + r'brich ' + polite + target + r'(?: bitte)? ab(?: bitte)?',
            polite + target + ' ' + polite + r'(?:stoppen|abbrechen|stornieren)',
            r'(?:kannst du|können sie|würdest du) ' + polite + target + ' ' + polite + r'(?:stornieren|abbrechen|stoppen)',
            r'ich (?:möchte|will) ' + polite + target + r' stornieren',
        )
        return any(re.fullmatch(command + r'[.!?]?', text) for command in commands)

    @staticmethod
    def _new_intent(text):
        return bool(re.search(r'\b(?:bestell\w*|buch\w*|beantrag\w*|beauftrag\w*|kauf\w*|reservier\w*|neue[nrs]? (?:aufgabe|auftrag|anliegen|ticket)|außerdem|zusätzlich|stattdessen|ich (?:brauche|möchte|will))\b', text, re.I))

    @staticmethod
    def _quoted_ranges(text):
        """Quote spans, including single quotes; intraword apostrophes are text.

        An unmatched opener remains quoted to end-of-input. A quoted outer span
        already covers nested quotations, so nested punctuation cannot close it.
        """
        pairs = {'"': '"', '„': '“', '“': '”', '«': '»', '`': '`',
                 "'": "'", '‘': '’', '‚': '‘', '‹': '›'}
        spans, opening, closing = [], 0, ''
        for index, char in enumerate(text):
            if char in "'’" and 0 < index < len(text) - 1 and text[index - 1].isalnum() and text[index + 1].isalnum():
                continue
            if closing:
                if char == closing:
                    spans.append((opening, index + 1))
                    closing = ''
            elif char in pairs:
                opening, closing = index, pairs[char]
            elif char in '”»’›':
                # A standalone closing mark has no reliable unquoted boundary.
                opening, closing = index, char
        if closing:
            spans.append((opening, len(text)))
        return spans

    @classmethod
    def _evidence_clause(cls, text, evidence, *, action=False, _start=None):
        """Locate a single literal, unquoted nonhypothetical evidence occurrence.

        Negation is prohibited for a control/request, not for describing a problem.
        Sentence boundaries keep a harmless follow-up independent of earlier quotes.
        """
        if not evidence or (_start is None and text.count(evidence) != 1):
            return ''
        start = text.index(evidence) if _start is None else _start
        end = start + len(evidence)
        if text[start:end] != evidence:
            return ''
        # Quotes can span sentence boundaries; never authorize from inside one.
        if any(left < end and start < right for left, right in cls._quoted_ranges(text)):
            return ''
        left = max(text.rfind(mark, 0, start) for mark in '.!?;') + 1
        right = min((pos for mark in '.!?;' if (pos := text.find(mark, start + len(evidence))) >= 0), default=len(text))
        clause = text[left:right].strip()
        if re.search(r'\b(?:wenn|falls|würde|würdest|hypothetisch|beispiel|zitiert|sagte)\b', clause, re.I):
            return ''
        if action and re.search(r'\b(?:nicht|nichts|kein\w*|niemals)\b', clause, re.I):
            return ''
        return clause

    @classmethod
    def _has_separate_action(cls, text):
        # A rejected control is not a field value. Check each occurrence so a
        # repeated command cannot evade the unique model-evidence requirement.
        for match in re.finditer(r'\b(?:stornier\w*|abbrech\w*|abbruch|brich|stoppen|beend\w*|bestell\w*|buch\w*)\b', text, re.I):
            if cls._evidence_clause(text, match.group(), action=True, _start=match.start()):
                return True
        return False

    @classmethod
    def _valid_answer(cls, text, evidence, kind):
        """Same scoped authority checks for local and model-backed values."""
        return (cls._matches_answer(evidence, kind) and not cls._has_separate_action(text)
                and bool(cls._evidence_clause(text, evidence, action=True)))

    @staticmethod
    def _topic_relation(text, question):
        """Require content-bearing question vocabulary for open dialogue.

        This is a local lower bound on the model's semantic relation, not a list
        of permitted requests. Unknown question form alone confers no authority.
        """
        stop = {'welche', 'welcher', 'welches', 'welchen', 'ihren', 'ihrem', 'ihres', 'ihnen',
                'deinen', 'deinem', 'dieser', 'diese', 'dieses', 'bitte', 'können', 'möchten',
                'lautet', 'haben', 'werden', 'sollen', 'sagen', 'frage', 'schritt', 'unbekannter'}
        words = lambda value: {w.casefold().rstrip('nes') for w in re.findall(r'[^\W\d_]{5,}', value)
                               if w.casefold() not in stop}
        return bool(words(text) & words(question))

    def _semantic(self, proposal, task_id, text, context, question):
        intent, relation, evidence = proposal.intent, proposal.relation, proposal.evidence
        reject = lambda: self._clarify(context)
        if intent == 'clarification':
            return reject()
        # A separate affirmative cancellation/new request may not hitch a ride
        # in the unchanged text delivered as a benign answer.
        if intent in ('continue_task', 'amend_task') and self._has_separate_action(text):
            return reject()
        clause = self._evidence_clause(text, evidence, action=intent in ('new_task', 'stop_speaking'))
        if not clause:
            return reject()
        explicit, conflict = self._reference(context, text)
        if intent == 'status_query':
            # Focus is not independent evidence for a model-selected status target.
            bound = self._target(context, text)
            if conflict or not bound or bound != task_id:
                return reject()
            return Route(intent, bound)
        if intent == 'stop_speaking':
            direct = re.search(r'\b(?:schweig\w*|verstumm\w*|ruhe|still|leise|stumm|ton aus|audio aus|pause)\b', clause, re.I)
            business = re.search(r'\b(?:auftrag|aufgabe|bestellung|ticket|stornier\w*)\b', clause, re.I)
            return Route(intent) if direct and not business else reject()
        if intent == 'new_task':
            agents = self._agents(context, text)
            if len(agents) != 1 or agents[0].alias != proposal.agent_alias:
                return reject()
            agent = agents[0]
            labels = sorted((agent.alias, agent.name, *agent.routing_aliases), key=len, reverse=True)
            labels = '|'.join(re.escape(label) for label in labels if label)
            # Vocative/address and explicit handoff select the agent; a bare mention does not.
            selected = re.match(r'^(?:bitte\s+)?(?:' + labels + r')\s*[:,]\s*(\S.*)$', text, re.I)
            if not selected:
                selected = re.match(r'^(?:bitte\s+)?(?:an|für)\s+(?:' + labels + r')\s*[:,]\s*(\S.*)$', text, re.I)
            if not selected:
                selected = re.match(r'^(?:' + labels + r')\s+bitte\s*[:,]?\s+(\S.*)$', text, re.I)
            if not selected or len(selected.group(1).split()) < 2 or evidence not in selected.group(1):
                return reject()
            referenced, bad = self._reference(context, selected.group(1))
            if referenced or bad or any(self._mentions(text, t['task_id']) for t in context.tasks):
                return reject()
            return Route(intent, agent_alias=agent.alias)
        if conflict or explicit and explicit != task_id:
            return reject()
        if intent == 'continue_task':
            if not question or question['task_id'] != task_id:
                return reject()
            kind = self._answer_kind(context.last_question)
            if kind == 'ambiguous':
                return reject()
            if relation == 'answer':
                # Literal values alone do not authorize a separate business request.
                if self._valid_answer(text, evidence, kind) and not self._new_intent(text):
                    return Route(intent, task_id)
            elif relation == 'dialogue':
                # The model may recognize a service-process question alongside a
                # typed checkpoint; the kind/shape excludes bare mismatched values.
                # Domain suitability remains a model semantic judgment against the
                # actual catalogue, not an invented authoritative word list.
                typed_followup = kind in ('name', 'manager', 'date', 'location', 'spelling') and bool(
                    re.match(r'^(?:wie|was|warum|wieso|wo|wann|wer|welche\w*|kann|können)\b', text, re.I))
                if (kind != 'yes_no' and not self._new_intent(text)
                        and (typed_followup or self._topic_relation(text, context.last_question))):
                    return Route(intent, task_id)
            elif relation == 'explain' and re.search(r'frage|gemeint|bedeut|versteh|erklär|wiederhol', clause, re.I):
                return Route('clarification', reply=('Die aktuelle Frage lautet: ' + context.last_question)[:4000])
        if intent == 'amend_task':
            task = next((t for t in context.tasks if t['task_id'] == task_id), None)
            if (not task or task.get('state') in _TERMINAL or not task.get('previous_question_id')
                    or not task.get('previous_operation_id')
                    or task.get('previous_operation_version') != task.get('context_version')
                    or task.get('previous_question_version') != task.get('context_version', -2) - 1
                    or question or context.question_task_id):
                return reject()
            candidates = [t for t in context.tasks if t.get('previous_question_id')
                          and t.get('previous_operation_version') == t.get('context_version')]
            if not explicit and len(candidates) != 1:
                return reject()
            if (re.search(r'\b(?:korrigier\w*|korrektur|ersetzen|statt|berichtigen|meinte|ändern)\b', clause, re.I)
                    and self._valid_answer(text, evidence, self._answer_kind(task['previous_question']))):
                return Route(intent, task_id)
        return reject()

    def _local_help(self, text, context, question):
        if re.search(r'(?:andere|weitere|noch eine|mehrere|parallel).*frag|was kannst du|was kann ich.*frag', text, re.I):
            return Route('clarification', reply='Du kannst weitere Fragen stellen. Fachliche Anfragen werden nacheinander übermittelt; zusätzliche Aufgaben bleiben im bestehenden Legacy-Kontext in der Warteschlange. Ich kann die aktuelle Frage erklären und den gespeicherten Stand nennen.')
        if re.search(r'was.*(?:verstanden|behalten|gespeichert|gemerkt)|welche.*(?:angaben|daten).*gespeichert', text, re.I):
            target = self._target(context, text, allow_focus=True)
            task = next((t for t in context.tasks if t['task_id'] == target), None)
            if task and task.get('retained_text'):
                reply = 'Zuletzt für diese Aufgabe gespeichert (Originalwortlaut): ' + task['retained_text']
                return Route('clarification', reply=reply if len(reply) <= 4000 else task['retained_text'])
            return self._clarify(context)
        if re.search(r'(?:wiederhol|noch ?mal|erneut).*(?:frage)|(?:was|welche).*(?:brauchst|benötigst|information|angaben)|(?:was|wie).*(?:bedeutet|heißt|heisst|gemeint|frage.*versteh)|erklär.*(?:frage|name|datum|liefer|manager)', text, re.I):
            explicit, conflict = self._reference(context, text)
            if not question or conflict or (explicit and explicit != question['task_id']):
                return self._clarify(context)
            definitions = {
                'name': 'Mit Name ist der Vor- und Nachname der erfragten Person gemeint.',
                'manager': 'Mit Führungskraft oder Manager ist die zuständige vorgesetzte Person gemeint.',
                'date': 'Ein Datum bezeichnet den erfragten Kalendertag, gegebenenfalls mit Monat und Jahr.',
                'location': 'Der Lieferort ist der Ort beziehungsweise die Adresse, an die geliefert werden soll.',
                'yes_no': 'Diese Frage erwartet eine Zustimmung oder Ablehnung mit Ja oder Nein.',
                'spelling': 'Buchstabieren bedeutet, die Buchstaben des erfragten Namens einzeln anzugeben.',
            }
            explanation = definitions.get(self._answer_kind(context.last_question), '') if re.search(r'bedeutet|heißt|heisst|gemeint|erklär|versteh', text, re.I) else ''
            reply = (explanation + ' ' if explanation else '') + 'Die aktuelle Frage lautet: ' + context.last_question
            return Route('clarification', reply=reply if len(reply) <= 4000 else context.last_question)
        return None

    async def route(self, text: str, context: RoutingContext) -> Route:
        if not isinstance(context, RoutingContext) or not isinstance(text, str) or len(text) > 4000 or not text.strip():
            return self._clarify()
        try:
            # Scope/type/size invariants apply to every route. The optional model's
            # serialized byte budget must not disable local controls or exact repeats.
            context.__post_init__()
        except (StoreInvalid, ValueError):
            return self._clarify()
        text = text.strip()  # Matching only: coordinator persists the original utterance.
        folded = text.casefold()
        question = self._question(context)
        local = self._local_help(text, context, question)
        if local:
            return local
        unsafe = self._unsafe_control(text)
        cancellation = bool(re.search(r'\b(?:stornier\w*|abbrech\w*|abbruch|brich|stoppen|beend\w*)\b', folded))
        audio = bool(re.search(r'\b(?:ansage|sprachausgabe|stimme|vorlesen|sprechen)\b', folded))
        stop = bool(re.search(r'\b(?:h[oö]r(?:e)?(?: bitte)? auf|sei still|stop[p]?|nicht weiter sprechen)\b', folded))
        if (audio and (cancellation or stop)) or (stop and not re.search(r'auftrag|aufgabe|bestellung|ticket', folded)):
            # The negative idiom requests silence, but quotation/hypothesis still
            # removes authority. Normalization is for this guard only, never data.
            control = re.sub('nicht weiter sprechen', 'aufhören zu sprechen', text, flags=re.I)
            return self._clarify(context) if self._unsafe_control(control) else Route('stop_speaking')
        target = self._target(context, text)
        if cancellation:
            direct = self._affirmative_cancel(context, text)
            explicit, conflict = self._reference(context, text)
            generic = bool(re.fullmatch(r'(?:bitte )?(?:stornier\w* (?:bitte )?(?:(?:die|den|meine[nr]?|diese[nr]?) )?(?:aufgabe|auftrag|bestellung|ticket)|(?:die |den )?(?:aufgabe|auftrag|ticket) stoppen)[.!?]?', folded))
            target = target or (question['task_id'] if question and generic else '')
            live = any(t['task_id'] == target and t.get('state') not in _TERMINAL for t in context.tasks)
            if direct and live and not unsafe and not conflict and "'" not in text and (explicit or generic):
                return Route('cancel_task', target)
            # A quoted/negated old control is not a veto on a separate benign
            # response. Any proposed continuation still checks its own evidence.
        if re.search(r'\b(?:status|stand|wie weit|schon fertig|erledigt|was macht|läuft.*noch)\b', folded):
            target = self._target(context, text, allow_focus=True)
            return Route('status_query', target) if target else self._clarify(context)
        # Text trying to change routing policy cannot acquire business authority.
        if re.search(r'ignorier|systemprompt|system prompt|regeln.*(?:umgeh|vergiss)|verwende.*(?:alias|agent)', folded):
            return self._clarify(context)
        explicit, conflict = self._reference(context, text)
        agents = self._agents(context, text)
        new_intent = self._new_intent(text)
        correction = re.match(r'^(?:korrektur|ich korrigiere|nein[, ]+ich meinte|ich meinte)(?:\s*[:,]\s*|\s+)(.+)$', text, re.I)
        if correction and not conflict and not new_intent:
            candidates = [t for t in context.tasks if t.get('state') not in _TERMINAL
                and t.get('previous_question') and t.get('previous_question_version') == t.get('context_version', -2) - 1
                and (not explicit or explicit == t['task_id'])
                and self._valid_answer(text, correction.group(1), self._answer_kind(t['previous_question']))]
            if len(candidates) == 1:
                if (question and not explicit
                        and (question['task_id'], context.question_version) !=
                            (candidates[0]['task_id'], candidates[0]['previous_question_version'])
                        and self._matches_answer(correction.group(1), self._answer_kind(context.last_question))):
                    return self._clarify(context)
                return Route('amend_task', candidates[0]['task_id'])
            return self._clarify(context)
        if question and not conflict and (not explicit or explicit == question['task_id']) and not new_intent:
            if self._valid_answer(text, text, self._answer_kind(context.last_question)):
                return Route('continue_task', question['task_id'])
        if self.model is None:
            return self._clarify(context)
        try:
            context.model_data()
            contract = ProposalContract(context.tasks, context.agents)
            raw = await asyncio.wait_for(self.model.classify(text, context), timeout=2.0)
            proposal = contract.decode(raw)
            task_id = contract.task_refs.get(proposal.task_ref, '')
            return self._semantic(proposal, task_id, text, context, question)
        except (TimeoutError, ValueError, OSError, StoreInvalid, KeyError, TypeError):
            return self._clarify(context)
