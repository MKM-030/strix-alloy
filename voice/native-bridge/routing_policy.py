"""One immutable request policy for local and semantic routing proposals.

Candidates are possibilities, never durable authorization. Store preconditions are
still checked atomically at acceptance. No model prose is rendered as help.
"""
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from business_tasks import StoreInvalid
if TYPE_CHECKING:
    from conversation_router import Route

_TERMINAL = frozenset(('cancel_requested', 'cancelled', 'succeeded', 'failed', 'outcome_unknown'))
REASONS = frozenset(('accepted_local', 'accepted_model', 'unclear', 'schema', 'evidence_role',
    'target_ambiguity', 'type_contradiction', 'operation_ineligible', 'competing_request',
    'authority_changed', 'timeout', 'context_budget', 'grounded_help', 'domain_unsuitable',
    'domain_unclear', 'selection_required', 'unavailable', 'legacy_route', 'duplicate_accepted', 'semantic_reference', 'audio_context'))
DEFINITIONS = MappingProxyType({
    'name': 'Mit Name ist der Vor- und Nachname der erfragten Person gemeint.',
    'manager': 'Mit Führungskraft oder Manager ist die zuständige vorgesetzte Person gemeint.',
    'date': 'Ein Datum bezeichnet den erfragten Kalendertag, gegebenenfalls mit Monat und Jahr.',
    'location': 'Der Lieferort ist der Ort beziehungsweise die Adresse, an die geliefert werden soll.',
    'yes_no': 'Diese Frage erwartet eine Zustimmung oder Ablehnung mit Ja oder Nein.',
    'spelling': 'Buchstabieren bedeutet, die Buchstaben des erfragten Namens einzeln anzugeben.',
})

class ContextBudgetExceeded(StoreInvalid):
    """Complete request cannot fit the bounded transport; no competitor is dropped."""


@dataclass(frozen=True)
class HelpSource:
    task_id: str
    question_id: str
    context_version: int
    source: str
    question: str
    definition_key: str = ''

@dataclass(frozen=True)
class ProposalObservation:
    """Bounded semantic-stage facts; never caller evidence, model prose or IDs."""
    status: str
    intent: str = 'none'
    meaning: str = 'none'
    domain: str = 'na'
    json_syntax_valid: bool | None = None
    schema_shape_valid: bool | None = None
    bounds_valid: bool | None = None
    choice_bound: bool | None = None

    @property
    def offered_intent(self): return self.intent if self.choice_bound else None

    @property
    def offered_meaning(self): return self.meaning if self.choice_bound else None

    @property
    def offered_domain(self): return self.domain if self.choice_bound else None

    @property
    def domain_judgment(self): return self.offered_domain

    def __post_init__(self):
        from route_proposal import MEANINGS, DOMAINS
        if (self.status not in ('decoded', 'schema_rejected', 'syntax_rejected', 'shape_rejected', 'bounds_rejected', 'binding_rejected', 'timeout', 'context_budget', 'unavailable')
                or self.intent not in ('none', 'clarification', 'status_query', 'stop_speaking', 'continue_task', 'amend_task', 'new_task')
                or self.meaning not in MEANINGS | {'none'} or self.domain not in DOMAINS):
            raise ValueError('invalid proposal observation')


@dataclass(frozen=True)
class RoutingDecision:
    route: 'Route'
    disposition: str
    reason: str
    help_source: HelpSource | None = None
    proposal: ProposalObservation | None = None
    model_elapsed_ms: float | None = None
    route_elapsed_ms: float | None = None
    durable_acceptance: bool | None = None

    @property
    def policy_accepted(self):
        return self.disposition == 'decision' or self.help_source is not None

    @property
    def policy_reason(self):
        return self.reason

    @property
    def stale_rejected(self):
        return self.reason == 'authority_changed'

    @property
    def origin(self):
        return 'model' if self.proposal is not None else 'local'

    def __post_init__(self):
        if self.disposition not in ('decision', 'clarification', 'grounded_repeat', 'grounded_explanation'):
            raise ValueError('invalid decision disposition')
        if self.reason not in REASONS:
            raise ValueError('invalid decision reason')

@dataclass(frozen=True)
class Candidate:
    ref: str
    intent: str
    task_id: str = ''
    agent_alias: str = ''
    meanings: tuple[str, ...] = ()
    origin: str = 'either'
    question: str = ''
    question_id: str = ''
    question_version: int | None = None
    question_source: str = ''
    operation_id: str = ''
    operation_version: int | None = None

@dataclass(frozen=True)
class PolicySnapshot:
    scope_id: str
    tasks: tuple
    agents: tuple
    focus_task_id: str
    last_question: str
    question_task_id: str
    question_version: int | None
    workflow_task_id: str
    question_id: str
    question_source: str
    candidates: tuple[Candidate, ...] = ()

    def model_data(self):
        from route_proposal import ProposalContract
        return ProposalContract(self).model_data()



def policy_snapshot(context):
    """Public factory used by router and direct LoopbackConversationModel.classify."""
    if isinstance(context, PolicySnapshot):
        return context
    from conversation_router import RoutingContext
    if not isinstance(context, RoutingContext):
        raise StoreInvalid('invalid routing context')
    context.__post_init__()
    def freeze(value):
        if isinstance(value, dict): return MappingProxyType({k: freeze(v) for k, v in value.items()})
        if isinstance(value, (tuple, list)): return tuple(freeze(v) for v in value)
        return value
    snapshot = PolicySnapshot(context.scope_id, tuple(freeze(t) for t in context.tasks),
        tuple(context.agents), context.focus_task_id, context.last_question, context.question_task_id,
        context.question_version, context.workflow_task_id, context.question_id, context.question_source)
    candidates = [Candidate('c0', 'clarification', meanings=('unclear',)),
                  Candidate('c1', 'stop_speaking', meanings=('audio',))]
    def add(intent, **kwargs):
        candidates.append(Candidate(f'c{len(candidates)}', intent, **kwargs))
    for task in snapshot.tasks:
        add('status_query', task_id=task['task_id'], meanings=('reference',))
        if task.get('state') not in _TERMINAL:
            add('cancel_task', task_id=task['task_id'], meanings=('request',), origin='local')
        if (task.get('state') not in _TERMINAL and task.get('previous_question')
                and task.get('previous_question_id') and task.get('previous_operation_id')
                and task.get('previous_operation_version') == task.get('context_version')
                and task.get('previous_question_version') == task.get('context_version', -2) - 1
                and task.get('latest_operation_id') == task.get('previous_operation_id')
                and task.get('latest_operation_version') == task.get('previous_operation_version')):
            add('amend_task', task_id=task['task_id'], meanings=('correction',),
                question=task['previous_question'], question_id=task['previous_question_id'],
                question_version=task['previous_question_version'], question_source=task.get('previous_question_source', ''),
                operation_id=task['previous_operation_id'], operation_version=task['previous_operation_version'])
    question = PolicyRules._question(snapshot)
    if question:
        binding = dict(task_id=question['task_id'], question=snapshot.last_question,
            question_id=snapshot.question_id, question_version=snapshot.question_version,
            question_source=snapshot.question_source)
        add('continue_task', meanings=('answer', 'dialogue'), **binding)
        # A Route can repeat for old route-only callers without inventing provenance.
        add('clarification', meanings=('repeat', 'explain'), **binding)
    for agent in snapshot.agents:
        if agent.capabilities.get('new_task') and 'new_task' in agent.supported_intents:
            add('new_task', agent_alias=agent.alias, meanings=('request',))
    from dataclasses import replace
    return replace(snapshot, candidates=tuple(candidates))


def clarify(snapshot=None, reason='unclear'):
    from conversation_router import Route
    labels = ', '.join((a.name or a.alias) for a in snapshot.agents) if snapshot else ''
    if snapshot and not labels: labels = ', '.join(t['task_id'] for t in snapshot.tasks)
    reply = 'Bitte präzisiere, welche Aufgabe oder welchen Agenten du meinst.'
    return RoutingDecision(Route('clarification', reply=reply + (' Verfügbar: ' + labels + '.' if labels else '')),
                           'clarification', reason)


class PolicyRules:
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

    @classmethod
    def status_target(cls, context, text, *, semantic_task_id=''):
        target, conflict = cls._reference(context, text)
        if cls.control_context_veto(text): return ''
        if conflict or re.search(r'\bfremd\w* (?:aufgabe|auftrag|ticket|anfrage)|\b(?:eines|einem|einer|der) anderen (?:kunden?|anrufers?|nutzers?)\b|\bnicht mein\w* (?:aufgabe|auftrag|ticket)', text, re.I):
            return ''
        # A named unknown object cannot be substituted with the only own task.
        # Generic status grammar is independent of focus. Complete registered
        # references are removed before checking for unresolved target material.
        remaining = text
        labels = [t['task_id'] for t in context.tasks]
        labels += [t.get('objective', '') for t in context.tasks]
        labels += [v for a in context.agents for v in (a.alias, a.name, *a.routing_aliases)]
        for label in sorted(filter(None, labels), key=len, reverse=True):
            remaining = re.sub(r'(?<![\w-])' + re.escape(label) + r'(?![\w-])', ' ', remaining, flags=re.I)
        grammar = {'status', 'stand', 'fortschritt', 'wie', 'weit', 'schon', 'fertig', 'erledigt',
            'was', 'macht', 'läuft', 'noch', 'ist', 'sind', 'es', 'sie', 'er', 'der', 'die', 'das',
            'den', 'des', 'dem', 'mein', 'meine', 'meiner', 'meinen', 'meinem', 'meines',
            'dieser', 'diese', 'dieses', 'diesem', 'diesen', 'von', 'vom', 'für', 'zu', 'zum', 'zur',
            'mit', 'bei', 'beim', 'bitte', 'mir', 'zeig', 'zeige', 'zeigen', 'sag', 'sage', 'sagen',
            'du', 'kannst', 'können', 'auftrag', 'aufgabe', 'ticket', 'bestellung', 'anfrage',
            'gibt', 'einen', 'ein', 'einem', 'eine', 'einer', 'aktuell', 'aktuelle', 'aktuellen', 'aktuellem', 'heute', 'jetzt', 'id', 'nummer', 'nr'}
        if any(word.casefold() not in grammar for word in re.findall(r'[\w-]+', remaining)):
            # A semantic reference may match an objective paraphrase. It is a
            # model judgment, not a locally proved match. Generic action words
            # alone cannot select among competing tasks, even with a focus.
            if semantic_task_id:
                selected = next((t for t in context.tasks if t['task_id'] == semantic_task_id), None)
                objective = (selected.get('objective') or '').strip().casefold() if selected else ''
                if not target and objective and sum((t.get('objective') or '').strip().casefold() == objective for t in context.tasks) > 1:
                    return ''
                return target or semantic_task_id
            return ''
        return target or (context.tasks[0]['task_id'] if len(context.tasks) == 1 else '')

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
            if re.search(r'\b(?:ich|möchte|brauche|will|bitte|kann|können|wie|warum)\b', value, re.I):
                return False
            return len(value) <= 300 and bool(re.fullmatch(r'[\wÄÖÜäöüß .,/()\-]+', value)) and len(value.split()) <= 20
        return False

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
            r'(?:kannst du|können sie|würdest du|würden sie) ' + polite + target + ' ' + polite + r'(?:stornieren|abbrechen|stoppen)',
            r'ich (?:möchte|will) ' + polite + target + r' stornieren',
        )
        return any(re.fullmatch(command + r'[.!?]?', text) for command in commands)

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
    def control_context_veto(cls, text):
        """Incomplete negative context recognizers for controls, never a positive grammar.

        Polite modal questions alone are allowed; reported/conditional modals are
        excluded. This is deliberately not applied to ordinary answer values.
        """
        return bool(cls._quoted_ranges(text) or re.search(
            r'\b(?:nicht|nichts|kein\w*|niemals|nie|wenn|falls|hypothetisch|beispiel|zitiert|sagte|sagt|berichtete)\b', text, re.I)
            or (re.search(r'\b(?:würde|würdest|würden)\b', text, re.I)
                and not re.match(r'^(?:würdest du|würden sie)\b', text.strip(), re.I)))

    @classmethod
    def audio_context_veto(cls, text):
        # v1 abstains on compound controls even when one clause is a real stop.
        return bool(cls.control_context_veto(text) or re.search(r'[;,:\n]|[.!?]\s*\S|\b(?:und|oder|außerdem|zusätzlich|danach)\b', text, re.I))

    @classmethod
    def request_context_veto(cls, text):
        # Quoted/reported requests never authorize a new task; negation is scoped
        # to recognized actions below, so "kein Papier" can describe a fault.
        return bool(cls._quoted_ranges(text) or re.search(r'\b(?:wenn|falls|hypothetisch|beispiel|zitiert|sagte)\b', text, re.I)
            or (re.search(r'\b(?:würde|würdest|würden)\b', text, re.I)
                and not re.match(r'^(?:würdest du|würden sie)\b', text.strip(), re.I)))

    @classmethod
    def evidence_clauses(cls, text, evidence, *, action=False):
        """Literal evidence has roles, not a unique-occurrence or value-shape rule."""
        if not evidence:
            return ()
        clauses = []
        quotes = cls._quoted_ranges(text)
        for match in re.finditer(re.escape(evidence), text):
            start, end = match.span()
            if any(left < end and start < right for left, right in quotes):
                continue
            left = max(text.rfind(mark, 0, start) for mark in '.!?;') + 1
            right = min((pos for mark in '.!?;' if (pos := text.find(mark, end)) >= 0), default=len(text))
            clause = text[left:right].strip()
            if re.search(r'\b(?:wenn|falls|hypothetisch|beispiel|zitiert|sagte)\b', clause, re.I):
                continue
            if re.search(r'\b(?:würde|würdest|würden)\b', clause, re.I) and not re.match(r'^(?:würdest du|würden sie)\b', clause, re.I):
                continue
            if action and re.search(r'\b(?:nicht|nichts|kein\w*|niemals)\b', clause, re.I):
                continue
            if clause not in clauses: clauses.append(clause)
        return tuple(clauses)

    @classmethod
    def action_clauses(cls, text, *, include_negative=False):
        """Positive request witnesses; intake also examines negative action relations."""
        imperative = r'(?:stornier(?:e)?|bestell(?:e)?|buche|kaufe|reservier(?:e)?|beantrag(?:e)?|beauftrag(?:e)?|beend(?:e)?|brich|stoppe)'
        infinitive = r'(?:stornieren|bestellen|buchen|kaufen|reservieren|beantragen|beauftragen|beenden|abbrechen|stoppen|anlegen|erstellen)'
        # Short forms that are also nouns need an accusative object relationship.
        # A coordinated noun subject or a genitive complement cannot prove it.
        object_phrase = r'(?:(?:mir|uns)\s+)?(?:ein(?:en|e)?|den|die|das|mein(?:en|e)?|dies(?:en|e|es))\s+\S.*'
        result = []
        for match in re.finditer(r'[^.!?;]+', text):
            clause = match.group().strip()
            if not cls.evidence_clauses(text, clause):
                continue
            command = re.sub(r'^[^:]+:\s*', '', clause)
            command = re.sub(r'^(?:außerdem|zusätzlich)\s+', '', command, flags=re.I)
            patterns = (
                r'(?:bitte\s+)?' + imperative + r'\s+.+',
                r'(?:bitte\s+)?(?:kauf|buch|stopp)\s+(?:bitte\s+)?' + object_phrase,
                infinitive + r'\s+Sie\s+.+',
                r'(?:kannst du|können sie|würdest du|würden sie)\s+(?:bitte\s+)?.+\s+' + infinitive,
                r'(?:ich (?:möchte|will)|(?:möchte|will) ich)\s+.+\s+' + infinitive,
                r'bitte\s+.+\s+' + infinitive,
                object_phrase + r'\s+bitte\s+' + infinitive,
            )
            # Subject + finite ability verb describes the caller's situation,
            # including object-fronted statements. It is not an infinitive
            # directive; its relevance remains the semantic proposal's job.
            ability_statement = re.fullmatch(
                r'(?:ich (?:kann|konnte)|wir (?:können|konnten)|'
                r'.+ (?:kann|konnte) ich|.+ (?:können|konnten) wir)\s+.+\s+' + infinitive,
                command, re.I)
            # Check reordered negative directives without turning a reported
            # inability into a command or applying negation across clauses.
            negative_action = (include_negative and not ability_statement and cls.action_negated(command)
                and re.search(r'\b' + infinitive + r'(?:\s+bitte)?$', command, re.I))
            if negative_action or any(re.fullmatch(pattern, command, re.I) for pattern in patterns):
                result.append(clause)
        return tuple(result)

    @staticmethod
    def action_negated(clause):
        return bool(re.search(r'\b(?:nicht|nichts|kein\w*|niemals)\b', clause, re.I))

    @classmethod
    def separate_action(cls, text):
        return any(not cls.action_negated(clause) for clause in cls.action_clauses(text))

    @classmethod
    def audio_witness(cls, text):
        if cls._quoted_ranges(text):
            return False
        value = re.sub(r'\s+', ' ', text.strip()).casefold().rstrip('.!?')
        polite = r'(?:bitte )?'
        obj = r'(?:(?:die |das )?(?:ansage|sprachausgabe|stimme|audio|vorlesen|sprechen))'
        forms = (
            polite + r'h[oö]r(?:e)? ' + polite + r'auf(?: zu sprechen| mit (?:der )?(?:ansage|sprachausgabe|vorlesen))?',
            polite + r'(?:sei still|schweig(?:e)?|verstumm(?:e)?|ruhe|still|leise|stumm|ton aus|audio aus|pause|stopp?)(?: jetzt| bitte)?',
            polite + r'nicht weiter sprechen',
            polite + r'brich ' + polite + obj + r' ab(?: bitte)?',
            polite + r'(?:stoppe|beende|unterbrich) ' + polite + obj + r'(?: bitte)?',
            polite + obj + r' (?:stoppen|abbrechen|beenden)',
            r'(?:kannst du|können sie|würdest du|würden sie) ' + polite + obj + r' (?:abbrechen|stoppen|beenden)',
        )
        return any(re.fullmatch(pattern, value) for pattern in forms)

    @classmethod
    def cancel_witness(cls, snapshot, text):
        return not cls._quoted_ranges(text) and cls._affirmative_cancel(snapshot, text)

    @classmethod
    def selected_agent(cls, snapshot, text):
        agents = cls._agents(snapshot, text)
        if len(agents) != 1:
            return '', ''
        agent = agents[0]
        labels = '|'.join(re.escape(v) for v in sorted((agent.alias, agent.name, *agent.routing_aliases), key=len, reverse=True) if v)
        for pattern in (r'^(?:bitte\s+)?(?:' + labels + r')\s*[:,]\s*(\S.*)$',
                        r'^(?:bitte\s+)?(?:an|für)\s+(?:' + labels + r')\s*[:,]\s*(\S.*)$',
                        r'^(?:' + labels + r')\s+bitte\s*[:,]?\s+(\S.*)$'):
            selected = re.match(pattern, text, re.I)
            if selected:
                return agent.alias, selected.group(1)
        return '', ''

    @classmethod
    def ambiguous_question(cls, question):
        # Positive proof of two requested values/confirmation alternatives. A polite
        # modal field request is not such proof merely because the heuristic is unsure.
        kind = cls._answer_kind(question)
        if kind != 'ambiguous': return False
        return bool(re.search(r'\b(?:und|oder)\b|\?.+\?|[,;].*(?:möchten|ist|sind|soll)', question, re.I))

    @classmethod
    def contradiction(cls, text, question):
        """Only demonstrated conflict, never failure of a positive heuristic."""
        if cls.ambiguous_question(question): return True
        value = text.strip().rstrip('.!?').strip()
        value = re.sub(r'^(?:korrektur|ich korrigiere)\s*:\s*', '', value, flags=re.I)
        supplied = re.fullmatch(r'(?:sie (?:können|dürfen)|du (?:kannst|darfst)) (.+?) (?:eintragen|verwenden|nehmen)', value, re.I)
        if supplied: value = supplied.group(1)
        kind = cls._answer_kind(question)
        polar = bool(re.fullmatch(r'(?:ja|nein|nee)(?:,? (?:bitte|danke|das passt))?', value, re.I))
        if kind in ('name', 'manager', 'date', 'location', 'spelling') and polar: return True
        if kind == 'yes_no' and not polar:
            return any(cls._matches_answer(value, k) for k in ('name', 'date', 'spelling'))
        if kind in ('name', 'manager') and cls._matches_answer(value, 'date'): return True
        return False

    @classmethod
    def correction_competes(cls, snapshot, candidate, text, value):
        explicit, _ = cls._reference(snapshot, text)
        if explicit and explicit == candidate.task_id:
            others = [c for c in snapshot.candidates if c.intent == 'continue_task' and c.task_id == explicit]
        else:
            others = [c for c in snapshot.candidates if c.intent == 'continue_task']
        for current in others:
            prior_kind = cls._answer_kind(candidate.question)
            current_kind = cls._answer_kind(current.question)
            # Distinct established fields do not compete; unknown/matching fields do.
            if (current.question != candidate.question and current_kind and prior_kind
                    and current_kind != 'ambiguous' and prior_kind != 'ambiguous'
                    and current_kind != prior_kind):
                continue
            # Distinct questions can be resolved by an explicit previous-answer relation;
            # unknown field heuristics alone do not establish competing values.
            if candidate.question != current.question:
                if (candidate.question in text and current.question not in text
                        or re.search(r'\b(?:vorige|vorherige|frühere|vorige[nrms]?|vorherige[nrms]?|frühere[nrms]?)\s+(?:angabe|antwort|frage)\b', text, re.I)):
                    continue
                if not prior_kind or not current_kind or 'ambiguous' in (prior_kind, current_kind):
                    continue
            return True
        return False


def _candidate(snapshot, intent, task_id='', meaning=''):
    return next((c for c in snapshot.candidates if c.intent == intent
        and (not task_id or c.task_id == task_id) and (not meaning or meaning in c.meanings)), None)


@dataclass(frozen=True)
class LocalWitness:
    """Private deterministic path; never decoded from model output."""
    candidate: Candidate
    meaning: str
    evidence: str
    value: str = ''
    domain: str = 'na'


def evaluate_choice(snapshot, text, option):
    return _evaluate(snapshot, text, option, local=False)


def _evaluate(snapshot, text, proposal, *, local):
    """Shared structural exclusions; model choice carries no literal proof."""
    from conversation_router import Route
    candidate = proposal.candidate
    reject = lambda reason: clarify(snapshot, reason)
    if candidate not in snapshot.candidates or proposal.meaning not in candidate.meanings:
        return reject('schema')
    if candidate.origin == 'local' and not local:
        return reject('operation_ineligible')
    if candidate.ref == 'c0': return reject('unclear')
    intent, meaning = candidate.intent, proposal.meaning
    if intent == 'cancel_task':
        if not local or not PolicyRules.cancel_witness(snapshot, text):
            return reject('evidence_role')
    elif intent == 'stop_speaking':
        if local:
            if not PolicyRules.audio_witness(text): return reject('evidence_role')
        elif PolicyRules.audio_context_veto(text):
            return reject('audio_context')
    if local and intent not in ('cancel_task', 'stop_speaking'):
        clauses = PolicyRules.evidence_clauses(text, proposal.evidence)
        if not clauses: return reject('evidence_role')
        if proposal.value and not PolicyRules.evidence_clauses(text, proposal.value):
            return reject('evidence_role')
    else:
        # Real utterance clauses are inspected for contradictions only. They are
        # not manufactured generated evidence and do not prove semantic relevance.
        clauses = tuple(c.strip() for c in re.split(r'(?<!\d)[.!?;]', text) if c.strip())
    explicit, conflict = PolicyRules._reference(snapshot, text)
    if intent in ('status_query', 'cancel_task'):
        bound = PolicyRules.status_target(snapshot, text, semantic_task_id=candidate.task_id if not local else '') if intent == 'status_query' else PolicyRules._target(snapshot, text)
        if conflict or not bound or bound != candidate.task_id: return reject('target_ambiguity')
    elif intent == 'new_task':
        selected, payload = PolicyRules.selected_agent(snapshot, text)
        if selected != candidate.agent_alias or len(payload.split()) < 2:
            return reject('selection_required')
        if PolicyRules.request_context_veto(payload): return reject('evidence_role')
        actions = PolicyRules.action_clauses(payload, include_negative=True)
        if actions and all(PolicyRules.action_negated(clause) for clause in actions):
            return reject('evidence_role')
        target, bad = PolicyRules._reference(snapshot, payload)
        if target or bad: return reject('target_ambiguity')
        if proposal.domain != 'suitable':
            return reject('domain_unsuitable' if proposal.domain == 'unsuitable' else 'domain_unclear')
    elif intent in ('continue_task', 'amend_task', 'clarification'):
        if conflict or explicit and explicit != candidate.task_id:
            return reject('target_ambiguity')
        if intent == 'clarification':
            if PolicyRules.control_context_veto(text): return reject('evidence_role')
            definition_key = PolicyRules._answer_kind(candidate.question) if meaning == 'explain' else ''
            definition = DEFINITIONS.get(definition_key, '')
            reply = (definition + ' ' if definition else '') + 'Die aktuelle Frage lautet: ' + candidate.question
            if len(reply) > 4000:
                reply, definition = candidate.question, ''
            source = HelpSource(candidate.task_id, candidate.question_id, candidate.question_version,
                candidate.question_source, candidate.question, definition_key if definition else '') if candidate.question_id else None
            disposition = ('grounded_explanation' if definition else 'grounded_repeat') if source else 'clarification'
            return RoutingDecision(Route('clarification', reply=reply), disposition,
                'grounded_help' if source else 'unclear', source)
        if PolicyRules.separate_action(text): return reject('competing_request')
        if meaning == 'answer' or intent == 'amend_task':
            for clause in clauses:
                if PolicyRules.contradiction(clause, candidate.question): return reject('type_contradiction')
                # Only local positive witnesses require an affirmative scalar.
                if local and re.search(r'(?:^|:\s*)(?:nicht|kein\w*|niemals)\b', clause, re.I):
                    return reject('evidence_role')
        elif PolicyRules.ambiguous_question(candidate.question):
            return reject('type_contradiction')
        if intent == 'amend_task':
            candidates = [c for c in snapshot.candidates if c.intent == 'amend_task']
            if not explicit and len(candidates) != 1 or PolicyRules.correction_competes(snapshot, candidate, text, ''):
                return reject('target_ambiguity')
    return RoutingDecision(Route(intent, candidate.task_id, candidate.agent_alias), 'decision',
                           'accepted_local' if local else 'semantic_reference' if intent == 'status_query' else 'accepted_model')


def deterministic(snapshot, text):
    """Produce finite, positive local witnesses; semantic uncertainty goes to model."""
    from conversation_router import Route
    def run(candidate, meaning, evidence, value=''):
        if not candidate: return clarify(snapshot, 'operation_ineligible')
        proposal = LocalWitness(candidate, meaning, evidence, value)
        return _evaluate(snapshot, text, proposal, local=True)
    if PolicyRules.audio_witness(text):
        return run(_candidate(snapshot, 'stop_speaking'), 'audio', text)
    if PolicyRules.cancel_witness(snapshot, text):
        target = PolicyRules._target(snapshot, text)
        return run(_candidate(snapshot, 'cancel_task', target) if target else None, 'request', text)
    if re.search(r'\b(?:status|stand|wie weit|schon fertig|erledigt|was macht|läuft.*noch)\b', text, re.I):
        target = PolicyRules.status_target(snapshot, text)
        if target:
            return run(_candidate(snapshot, 'status_query', target), 'reference', text)
        return None
    if re.search(r'(?:andere|weitere|noch eine|mehrere|parallel).*frag|was kannst du|was kann ich.*frag', text, re.I):
        return RoutingDecision(Route('clarification', reply='Du kannst weitere Fragen stellen. Fachliche Anfragen werden nacheinander übermittelt; zusätzliche Aufgaben bleiben im bestehenden Legacy-Kontext in der Warteschlange. Ich kann die aktuelle Frage erklären und den gespeicherten Stand nennen.'), 'clarification', 'unclear')
    if re.search(r'was.*(?:verstanden|behalten|gespeichert|gemerkt)|welche.*(?:angaben|daten).*gespeichert', text, re.I):
        target = PolicyRules._target(snapshot, text, allow_focus=True)
        task = next((t for t in snapshot.tasks if t['task_id'] == target), None)
        if task and task.get('retained_text'):
            reply = 'Zuletzt für diese Aufgabe gespeichert (Originalwortlaut): ' + task['retained_text']
            return RoutingDecision(Route('clarification', reply=reply if len(reply) <= 4000 else task['retained_text']), 'clarification', 'unclear')
        return clarify(snapshot)
    if re.search(r'(?:wiederhol|noch ?mal|erneut).*(?:frage)|(?:was|welche).*(?:brauchst|benötigst|information|angaben)|(?:was|wie).*(?:bedeutet|heißt|heisst|gemeint|frage.*versteh)|erklär.*(?:frage|name|datum|liefer|manager)', text, re.I):
        meaning = 'explain' if re.search(r'bedeutet|heißt|heisst|gemeint|erklär|versteh', text, re.I) else 'repeat'
        return run(_candidate(snapshot, 'clarification', meaning=meaning), meaning, text)
    if re.search(r'ignorier|systemprompt|system prompt|regeln.*(?:umgeh|vergiss)|verwende.*(?:alias|agent)', text, re.I):
        return clarify(snapshot)
    correction = re.match(r'^(?:korrektur|ich korrigiere|nein[, ]+ich meinte|ich meinte)(?:\s*[:,]\s*|\s+)(.+)$', text, re.I)
    if correction:
        explicit, conflict = PolicyRules._reference(snapshot, text)
        candidates = [c for c in snapshot.candidates if c.intent == 'amend_task'
            and (not explicit or c.task_id == explicit)
            and PolicyRules._matches_answer(correction.group(1), PolicyRules._answer_kind(c.question))]
        if len(candidates) == 1 and not conflict:
            return run(candidates[0], 'correction', text, correction.group(1))
        # A positive semantic correction can still resolve an unrecognized spoken value.
        return None
    current = _candidate(snapshot, 'continue_task')
    if current and PolicyRules._matches_answer(text, PolicyRules._answer_kind(current.question)):
        return run(current, 'answer', text)
    return None
