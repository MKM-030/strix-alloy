"""Pure conversational repairs; business utterances are returned untouched to the owner.

The caller supplies the current question binding from actual started output. This
module neither creates a task nor supplies a name, date, approval or backend call.
"""
from dataclasses import dataclass
import re


NATURAL_CONVERSATION_PROMPT = (
    'Sprich natürlich, hilfreich und knapp auf Deutsch, in höchstens drei kurzen Sätzen. '
    'Beantworte die Frage der Person im Zusammenhang mit dem bisher Gesagten. '
    'Wenn du dich unklar ausgedrückt hast, korrigiere das und erkläre konkret, was du meintest. '
    'Die Person spricht mit dir: Sage ich, meine Frage oder Ihre Angabe. '
    'Technische Feldnamen und Herkunftsmarkierungen sind keine Formulierungen fürs Gespräch. '
    'Erfinde keinen Auftrag aus einer Begrüßung oder einem kurzen Gesprächssignal. '
    'ServiceNow führt die Bestellung und erforderliche Bestätigungen durch. '
    'Du erklärst nur; du selbst bestellst und bestätigst nichts. '
    'Erfinde keine Angaben, Bearbeitungsschritte, Ursachen, Ergebnisse oder Wartezeiten. '
    'Namen, Daten und Bestellungen erfordern die jeweils gestellte Frage und eine passende Antwort.'
)


@dataclass(frozen=True)
class RepairDecision:
    kind: str
    reply: str
    resume_question: bool = False


def _normal(text):
    return re.sub(r'[^\wäöüß]+', ' ', text.casefold()).strip()


_ACK = re.compile(r'(?:ja(?: genau(?: so)?| bitte)?|genau(?: so)?|ok(?:ay)?|mhm|hm|aha|'
                  r'verstanden|alles klar|gut|in ordnung|richtig|korrekt)')
_SOCIAL = re.compile(r'(?:hallo(?: noch mal| nochmal)?|hi|hey|guten (?:morgen|tag|abend)|'
                     r'hörst du mich(?: noch)?|hören sie mich(?: noch)?|bist du noch da|'
                     r'sind sie noch da|kannst du mich hören|können sie mich hören|'
                     r'danke|vielen dank|dankeschön|bitte)')
_LEAD = r'(?:(?:ja|aber|also|bitte|äh|ähm) )*'
_FEEDBACK = (r'(?:(?:öffentliche[nrms]?|oeffentliche[nrms]?|konkrete[nrms]?) )?'
             r'(?:rückmeldung(?:en)?|rueckmeldung(?:en)?|rücklegung(?:en)?|ruecklegung(?:en)?)')
_FEEDBACK_QUESTION = (r'(?:(?:was für)(?: eine| ein| welche)?|welche) ' + _FEEDBACK +
                      r'(?: (?:meinst du|meinen sie))?(?: von (?:welcher anfrage|welchem anliegen|'
                      r'welchem auftrag|welchem vorgang))?')
_META = re.compile(_LEAD + r'(?:' + _FEEDBACK_QUESTION +
    r'|(?:wovon|worüber) (?:redest|sprichst) du(?: ' + _FEEDBACK_QUESTION + r')?'
    r'|(?:welche anfrage|welches anliegen|welcher auftrag|welchen vorgang) (?:meinst du|meinen sie)'
    r'|von (?:welcher anfrage|welchem anliegen|welchem auftrag|welchem vorgang) (?:redest|sprichst) du'
    r'|ich verstehe nicht (?:was du meinst|wovon du sprichst)'
    r'|(?:das verstehe ich nicht|was redest du da)'
    r'|(?:welche anfrage|welches anliegen|welcher auftrag|welchen vorgang)'
    r'|von welcher ' + _FEEDBACK + r' (?:redest|sprichst) du'
    r'|was ist mit (?:der |dieser |einer |den |diesen )?' + _FEEDBACK + r' gemeint'
    r'|was meinst du (?:damit|mit (?:der |dieser |einer )?' + _FEEDBACK + r')'
    r'|was soll das mit (?:der |dieser |einer )?' + _FEEDBACK +
    r')(?: denn| eigentlich| überhaupt| bitte| jetzt)?')


def _pure_kind(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 500:
        return None
    value = _normal(text)
    if _SOCIAL.fullmatch(value):
        return 'social'
    if _ACK.fullmatch(value):
        return 'backchannel'
    if _META.fullmatch(value):
        return 'repair'
    return None


def _passive_signal(text):
    """Whole acknowledgments/courtesies only; a real hearing question stays active."""
    return (_pure_kind(text) == 'backchannel' or _normal(text) in {
        'hallo', 'hallo noch mal', 'hallo nochmal', 'hi', 'hey',
        'guten morgen', 'guten tag', 'guten abend',
        'danke', 'vielen dank', 'dankeschön'})


def _bound_question(question, source):
    return (question.strip() if isinstance(question, str) and 0 < len(question.strip()) <= 800
            and source in ('greeting', 'servicenow_input_control') else '')


def _polar(question):
    value = _normal(question)
    if re.search(r'\b(?:wer|wen|wem|wessen|was|wann|wo|wohin|woher|wie|welch\w*)\b', value):
        return False
    return bool(re.search(r'^(?:ist|sind|stimmt|soll|sollen|darf|kann|können|möchten|möchtest|'
                          r'willst|wollen|bestätigen|bestätigst|passt)\b', value)
                or re.search(r'\b(?:richtig|korrekt|stimmt das|einverstanden)$', value))


def classify_repair(text, *, question='', question_source='', question_complete=False,
                    business_started=False, busy=False, raw_history=()):
    """Return only whole-turn social/meta repairs; None leaves the exact text to FIFO.

    A yes/genau answer is business input only at a complete, genuine polar input
    control. An unfinished question is re-asked before any approval is accepted.
    """
    kind = _pure_kind(text)
    if kind is None:
        return None
    current = _bound_question(question, question_source)
    if kind == 'backchannel':
        if current and question_source == 'servicenow_input_control' and question_complete and _polar(current):
            return None
    if _passive_signal(text):
        # Listening signals do not need another listening signal in reply.
        # An idle open question may be repeated by the owner, once per binding.
        if busy or not current:
            return RepairDecision(kind, '')
        if current:
            return RepairDecision(kind, ('Bitte hören Sie die Frage erst vollständig: ' if not question_complete
                                         and _polar(current) else '') + current)
    if kind == 'social':
        if _normal(text) == 'bitte':
            return RepairDecision(kind, current or 'Was möchten Sie genauer wissen?')
        return RepairDecision(kind, 'Ja, ich höre Sie.', bool(current) and not question_complete)
    # Own previous awkward wording. Do not echo the misunderstood technical term.
    if current:
        return RepairDecision(kind, 'Ich habe mich unklar ausgedrückt. Meine Frage war: ' + current)
    previous = next((item for item in reversed(tuple(raw_history))
                     if isinstance(item, str) and _pure_kind(item) is None and item.strip()), '')
    if business_started and previous and len(previous) <= 220:
        return RepairDecision(kind, 'Ich habe mich unklar ausgedrückt. Es geht um Ihre Eingabe: „' +
                              previous + '“ Was möchten Sie dazu klären?')
    if business_started:
        return RepairDecision(kind, 'Ich habe mich unklar ausgedrückt. Ich meinte eine Antwort auf Ihre '
                              'bisherige Eingabe. Was möchten Sie dazu klären?')
    return RepairDecision(kind, 'Ich habe mich unklar ausgedrückt. Sie haben noch keinen Auftrag genannt. '
                          'Wobei möchten Sie Hilfe?')


def conversational_snapshot(snapshot, *, question='', question_source='', busy=False):
    """Keep wire/provenance binding; put the actual question in question, not instructions.

    Caller history and backend findings retain their original text. Technical
    processing provenance belongs in source_event, never prepended to spoken text.
    """
    result = dict(snapshot)
    result['question'] = _bound_question(question, question_source)
    result['capability_limits'] = (
        'Antworte auf die aktuelle Rückfrage im Zusammenhang mit den unveränderten bisherigen Eingaben.',
        'Wenn eine aktuelle Frage angegeben ist, erkläre diese konkrete Frage statt einen neuen Auftrag anzunehmen.',
        'Korrigiere unklare eigene Worte in Alltagssprache. Erfinde keine Bedeutung für ein Gesprächssignal.',
        'Du kannst erklären und Angaben klären. ServiceNow allein führt Bestellungen und Bestätigungen durch.',
        'Eine Bearbeitungsanzeige belegt weder ein Ergebnis noch einen abgeschlossenen Schritt.',
        'Erfinde keine Ursachen, Prüfungen, Dauer, Mitarbeiterangaben oder Zusagen.',
        'Neue Ergänzungen gelten erst mit Beleg als übernommen; bloßer Empfang belegt keine Verarbeitung oder Zustimmung.',
        'Beachte spätere Korrekturen, ohne frühere zurückgenommene Angaben als weiterhin gültig auszugeben.',
        'Eine Eingabe wartet noch auf eine Antwort.' if busy else 'Behaupte nur den aus den vorhandenen Angaben belegten Stand.',
    )
    return result
