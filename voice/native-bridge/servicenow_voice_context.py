"""Small, model-neutral ServiceNow context; no network, tools or business authority.

Use the stable system fragment once when opening the conversation. Rebuild the
optional capability limits from current owner state for each turn. Documentation
and source receipts describe knowledge, never a tool registry or live availability.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import json
import re


@dataclass(frozen=True)
class DocumentationSource:
    key: str
    url: str
    version: str
    checked_on: str


@dataclass(frozen=True)
class RetrievalSnippet:
    key: str
    text: str
    source: str
    observed_on: str


@dataclass(frozen=True)
class VoicePlatformContext:
    system_prompt_fragment: str
    capability_limits: tuple[str, ...]
    documentation: tuple[DocumentationSource, ...]
    retrieval_snippets: tuple[RetrievalSnippet, ...]


SYSTEM_PROMPT_FRAGMENT = (
    'Du führst das Gespräch zum ServiceNow-Sprachassistenten, unabhängig vom verwendeten Modell. '
    'Sprich natürlich und knapp in der Sprache des Anrufs. Erkläre bekannte Sachverhalte und '
    'Rückfragen. NativeDuplex bleibt alleiniger Übermittler fachlicher Eingaben an den bestehenden '
    'ServiceNow-Dialog; dessen Agenten können andere Modelle nutzen. Du hast keine eigenen '
    'Bestell-, Bestätigungs-, SDK-, Shell- oder Verwaltungswerkzeuge. '
    'Gesprächssignale sind keine Aufträge. Fachliche Antworten gehören zur tatsächlich gestellten '
    'ServiceNow-Frage. Fortschritt und Erfolg nur aus aktuellen gebundenen Belegen nennen; '
    'Empfang, Speicherung, Promptaufnahme und Anwendung einer Korrektur unterscheiden. '
    'Dokumentationswissen erteilt keine Ausführungsrechte. Fluent SDK erstellt Anwendungsmetadaten; '
    'es ist nicht das Voice-SDK. Versionsgerechtes SDK-Wissen: '
    'https://servicenow.github.io/sdk/4.12.2 . '
    'A2A-Dokumentation: https://www.servicenow.com/docs/r/intelligent-experiences/secondary-agent.html . '
    'A2A-Verfügbarkeit in diesem Anruf ist nicht belegt. Lies keine technischen Kennungen oder Quellenmarkierungen vor.'
)

DOCUMENTATION = (
    DocumentationSource('fluent_sdk_reference', 'https://servicenow.github.io/sdk/4.12.2',
                        'reference=4.12.2; installed=unknown', '2026-10-25'),
    DocumentationSource('fluent_sdk_release', 'https://github.com/ServiceNow/sdk/releases/tag/v4.14.0',
                        'release=4.14.0; published=2026-10-22; installed=unknown', '2026-10-25'),
    DocumentationSource('sdk_skill', 'https://github.com/ServiceNow/sdk',
                        'explain>=4.6.0; query>=4.8.0; no local Fluent project verified', '2026-10-25'),
    DocumentationSource('secondary_agents',
                        'https://www.servicenow.com/docs/r/intelligent-experiences/secondary-agent.html',
                        'documentation_release=Brazil; updated=2026-09-10; instance_release=unknown',
                        '2026-10-25'),
)

RETRIEVAL_SNIPPETS = (
    RetrievalSnippet('owned_onboarding_flow',
        'Bekannter Demo-Onboarding-Ablauf (Quellstand 23.10.): benötigt Namen, Eintrittsdatum, '
        'Lieferort und ausdrückliche Zusammenfassungsbestätigung. Er ist Backend-Wissen, '
        'kein direkt aufrufbares Gesprächswerkzeug.',
        'live-scc-order-tool.js; live-scc-order-tool-metadata.json', '2026-10-23'),
    RetrievalSnippet('owned_voice_boundary',
        'Dialog.turn übermittelt genau die akzeptierte Eingabe; öffentliche Antworten, aktueller '
        'Input-Control und Verarbeitungsanzeige sind getrennt. context_status belegt höchstens '
        'die exakte Promptaufnahme, weder Geschäftserfolg noch Zustimmung.',
        'voice/native-bridge/native_bridge.py:Dialog; voice/native-bridge/native_duplex.py:_business',
        '2026-10-25'),
    RetrievalSnippet('sdk_skill_scope',
        'Die installierte now-sdk-Skill beschreibt versionsgebundene Dokumentationssuche und '
        'getrennte Instanzabfragen. Diese Entwicklungs-Skill ist im Sprachmodell kein Werkzeug. '
        'SDK-CLI und Credential-Zugriff werden nicht bereitgestellt.',
        'servicenow-sdk/1.2.0/skills/now-sdk/SKILL.md; official ServiceNow/sdk README',
        '2026-10-25'),
)

_LANGUAGE = re.compile(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,3}\Z')
def _boolean(state, key):
    value = state.get(key)
    return value if type(value) is bool else None


def _count(state, key):
    value = state.get(key)
    return value if type(value) is int and 0 <= value <= 256 else None


def _language(settings):
    # Never serialize prompt, native_projection, credentials, service/profile IDs,
    # requested tool names, or provider strings from the settings/state objects.
    if isinstance(settings, Mapping):
        value = settings.get('language')
    else:
        value = getattr(settings, 'language', None)
    return value if type(value) is str and _LANGUAGE.fullmatch(value) else 'unbekannt'


def build_servicenow_voice_context(settings=None, known_state=None):
    """Select facts from CallSettings or its detached session_parameters dict.

    known_state is supplied by the NativeDuplex owner, not by model/user text:
    business_available, business_busy, backend_closed, context_updates_enabled
    are exact bools; pending_count/supplement_count are bounded ints;
    question_source accepts only the two existing owned source labels.
    Absent/invalid values stay unknown. No caller text is promoted into policy.
    """
    state = known_state if isinstance(known_state, Mapping) else {}
    available, busy = (_boolean(state, key) for key in ('business_available', 'business_busy'))
    closed = _boolean(state, 'backend_closed')
    if closed is True:
        status = 'Dialog beendet; keine weitere Übermittlung in diesen Dialog.'
    elif available is False:
        status = 'Backend derzeit nicht verfügbar; keine weitere Bearbeitung belegt.'
    elif busy is True:
        status = 'Eine übermittelte Eingabe läuft noch; Ergebnis nicht bestätigt.'
    elif available is True and busy is False:
        status = 'Regulärer Dialogpfad verfügbar; kein fachlicher Abschluss belegt.'
    else:
        status = 'Backendstatus unbekannt; keine laufende Bearbeitung behaupten.'
    pending, supplements = (_count(state, key) for key in ('pending_count', 'supplement_count'))
    retained = (f'{pending} lokale Eingaben, {supplements} Ergänzungen vorgemerkt.'
                if pending is not None and supplements is not None else 'Vormerkungsstand unbekannt.')
    updates = ('Kontextkanal vorhanden; Übernahme nur mit exaktem Beleg.'
               if closed is not True and _boolean(state, 'context_updates_enabled') is True
               else 'Keine bestätigte Kontextübernahme.')
    question = ('Aktuelle Frage stammt aus ServiceNow-Eingabesteuerung.'
                if closed is not True and state.get('question_source') == 'servicenow_input_control'
                else 'Keine aktuelle ServiceNow-Eingabesteuerung hier belegt.')
    limits = (
        f'Plattform: ServiceNow; Sprache {_language(settings)}. NativeDuplex ist einziger '
        'fachlicher Übermittler. SDK/Fluent-Skill und Dokumentation sind Wissen, keine '
        'ausführbaren Modellwerkzeuge. Keine automatische Wiederholung unklarer Geschäftsaufrufe.',
        'Anrufstatus: ' + status + ' ' + retained + ' ' + updates + ' ' + question,
        RETRIEVAL_SNIPPETS[0].text,
    )
    return VoicePlatformContext(SYSTEM_PROMPT_FRAGMENT, limits, DOCUMENTATION, RETRIEVAL_SNIPPETS)


def append_servicenow_context(snapshot, context):
    """Append only optional limits that fit the existing strict wire envelope.

    Existing scope, caller text, question, findings and control fields are never
    removed, replaced or truncated. Full/oversized snapshots keep their content.
    Do not put documentation receipts/snippet schemas into the snapshot.
    """
    result = dict(snapshot)
    limits = result.get('capability_limits', ())
    if type(limits) is not tuple:
        return result
    for line in context.capability_limits:
        if line in limits or len(limits) >= 32 or type(line) is not str or not 0 < len(line) <= 1000:
            continue
        candidate = dict(result, capability_limits=limits + (line,))
        try:
            encoded = json.dumps(candidate, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
        except (TypeError, ValueError):
            return result
        if len(encoded) <= 10000 and len(encoded.encode('utf-8')) <= 32768:
            result, limits = candidate, candidate['capability_limits']
    return result
