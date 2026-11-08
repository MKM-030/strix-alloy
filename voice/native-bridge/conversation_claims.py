"""Narrow wording guard for local conversation, never business-result authority.

Balanced quotations and questions are not direct assertions. This recognizes
clear German storage/check claims, not arbitrary intent or full semantics.
"""
import re


def _unquoted(text):
    return re.sub(r'\u201e[^\u201c\u201d]*[\u201c\u201d]|\u201c[^\u201d]*\u201d|'
                      r'\u00ab[^\u00bb]*\u00bb|"[^"]*"|'
                      r'\u201a[^\u2018]*\u2018|\u2018[^\u2019]*\u2019|'
                      r"(?<!\w)'[^']*'(?!\w)", ' ', text)


def unproven_pending_data_claim(text, native_question=''):
    """Direct invented intake/withholding claims; owned question equivalence remains."""
    def normal(value):
        return re.sub(r'[^\w]+', ' ', value.casefold()).strip()
    if native_question and normal(text) == normal(native_question):
        return False
    for sentence in re.finditer(r'[^.!?;\n]+(?:[.!?;\n]|$)', _unquoted(text)):
        value = sentence.group().strip()
        if value.endswith('?'):
            continue
        value = normal(value)
        # A local queue/transport wait cannot prove that delivery was withheld
        # for missing business fields. Keep this actor/causal form general;
        # quotations, questions and conditional wording are not direct claims.
        if (re.fullmatch(r'ich habe .+ (?:noch )?nicht .*(?:übergeben|übermittelt|weitergegeben|gesendet) '
                         r'(?:da|weil) ich .+ (?:benötige|brauche)', value)
                and not re.search(r'\b(?:wenn|falls|sofern|würde|könnte|müsste|kein\w*|nichts)\b', value)):
            return True
        if (re.fullmatch(r'(?:der|die|das) .+ (?:ist|sind) für den prozess nicht relevant '
                         r'da wir nur .+ benötigen', value)
                or re.fullmatch(r'bitte nennen sie mir noch den vollständigen '
                                r'(?:vor|nach)?namen(?: .+)?', value)):
            return True
    return False


def unproven_current_action_claim(text, current_outputs=()):
    """Bounded German direct system-action category, not general entailment."""
    def normal(value):
        return re.sub(r'[^\w]+', ' ', value.casefold()).strip()
    if any(normal(text) == normal(output) for output in current_outputs):
        return False
    negative = r'\b(?:nichts|kein\w*|nie|niemals|weder)\b'
    conditional = r'\b(?:wenn|falls|sofern|sobald|würde|könnte|müsste)\b'
    general = r'\b(?:grundsätzlich|allgemein|üblicherweise|normalerweise|typischerweise|beispielsweise)\b'
    temporal = r'(?:(?:jetzt|nun|gerade|bereits|derzeit|aktuell)\s+)*'
    present = r'(?:prüft|speichert|bearbeitet|verarbeitet|validiert|bestellt|genehmigt|bestätigt)\b'
    future = r'\b(?:prüfen|speichern|bearbeiten|verarbeiten|validieren|bestellen|genehmigen|bestätigen|durchführen|abschließen|freigeben)\b'
    predicate_not = r'\bnicht(?:\s+mehr)?(?:\s+(?:durch|ab|frei|' + future + r'))?[.!]?\s*$'
    for sentence in re.finditer(r'[^.!?;\n]+(?:[.!?;\n]|$)', _unquoted(text)):
        value = sentence.group().strip().casefold()
        actor = re.match(r'^(?:servicenow|das system)\s+(.+)', value)
        if actor is None or value.endswith('?'):
            continue
        # Conditions qualify their coordinated clause, not earlier actions.
        # Keep a trailing comma-condition attached to a single future clause.
        for clause in re.split(r'\s+(?:und|aber)\s+', actor[1]):
            clause = re.sub(r'^(?:servicenow|das system)\s+', '', clause)
            predicate = clause.split(',', 1)[0]
            if (re.search(r'\blaut ihrer aussage\b', predicate)
                    or re.search(r',\s*(?:sagen|sagten) sie[.!]?\s*$', clause)):
                continue
            # A purpose/complement's negation does not negate the main action.
            # "nicht manuell" qualifies its manner; terminal/predicate negation
            # such as "nicht", "nicht durch" or "nicht prüfen" denies the action.
            if (re.search(negative, predicate) or re.search(predicate_not, predicate)
                    or re.search(conditional, clause)
                    or re.search(general, predicate) and not re.search(
                        r'\b(?:jetzt|nun|gerade|bereits|derzeit|aktuell)\b', predicate)):
                continue
            clause = re.sub('^' + temporal, '', clause)
            if (re.match(present, clause)
                    or re.match(r'führt\b', clause) and re.search(r'\bdurch\b', clause)
                    or re.match(r'schließt\b', clause) and re.search(r'\bab\b', clause)
                    or re.match(r'gibt\b', clause) and re.search(r'\bfrei\b', clause)
                    or re.match(r'wird\b', clause) and re.search(future, clause)):
                return True
    return False


def unproven_storage_or_check_claim(text):
    unquoted = _unquoted(text)
    auxiliary = (r'ich\s+(?:habe|hatte)|(?:habe|hatte)\s+ich|'
                 r'wir\s+(?:haben|hatten)|(?:haben|hatten)\s+wir|'
                 r'ist|sind|wird|werden|wurde|wurden|war|waren')
    # Commas may enumerate fields; another auxiliary or complement clause
    # cannot connect an earlier "habe" to a later reported participle.
    direct = (r'\b(?P<aux>' + auxiliary + r')\b(?P<between>(?:(?!\b(?:'
              + auxiliary + r')\b|,\s*(?:dass|ob|wie)\b)[^.!?;\n])*?)'
              r'\b(?:notiert|gespeichert|gepr\u00fcft)\b')
    negative = r'\b(?:nicht(?!\s+nur\b)|nichts|keinerlei|kein(?:e[rmns]?)?|nie(?:mals)?|weder)\b'
    planned = (r'\b(?:muss|müssen|müsste|müssten|musste|mussten|kann|können|könnte|könnten|'
               r'soll|sollen|sollte|sollten|darf|dürfen|dürfte|dürften|würde|würden|'
               r'bevor|wenn|falls|sofern|damit|vielleicht|möglicherweise|eventuell)\b')
    for sentence in re.finditer(r'[^.!?;\n]+(?:[.!?;\n]|$)', unquoted):
        value = sentence.group()
        if value.rstrip().endswith('?'):
            continue
        for claim in re.finditer(direct, value, re.I):
            between = claim.group('between')
            if re.search(negative, between, re.I) or re.search(planned, between, re.I):
                continue
            # A future/conditional passive is not a report that work happened.
            if claim.group('aux').casefold() in ('wird', 'werden'):
                preceding = value[:claim.start()]
                following = value[claim.end():]
                if (re.search(r'\b(?:wenn|falls|sofern)\b[^,]*,\s*(?:dann\s+)?$', preceding, re.I)
                        or re.match(r'\s+werden\b', following, re.I)
                        or re.search(r'\b(?:sobald|wenn|falls|sofern)\b', following, re.I)):
                    continue
            return True
    return False


def unproven_technical_destination_claim(text, current_outputs=()):
    """Hold direct destination/function assertions without owned native evidence.

    This is a narrow German wording class, not name validation or intent
    recognition. Exact current OutputText equivalence is the sole exception.
    """
    def normal(value):
        return re.sub(r'[^\w]+', ' ', value.casefold()).strip()
    if any(normal(text) == normal(output) for output in current_outputs):
        return False
    destination = r'(?:gegenstelle|zielname|verbindungsziel|verbindungsadresse|verbindungspartner)'
    invalid = r'(?:kein(?:e[rmns]?)?\s+gültig\w*|(?:nicht\s+gültig|ungültig))'
    # Remove quoted speech, but do not let a quoted target hide the surrounding
    # independent assertion ("dies ist kein gültiger Zielname").
    # Keep a quoted sentence boundary so a report cannot qualify a later
    # independent assertion after that quotation.
    masked = _unquoted(re.sub(r'([.!?])([“”»\"’‘])', r'\2\1', text))
    for sentence in re.finditer(r'[^.!?;\n]+(?:[.!?;\n]|$)', masked):
        value = sentence.group().strip().casefold()
        if value.endswith('?'):
            continue
        for clause in re.split(r'\s+(?:und|aber|sondern)\s+', value):
            if (re.search(r'\b(?:wenn|falls|sofern|sobald|würde|wäre|könnte|möglicherweise|vielleicht)\b', clause)
                    or re.search(r'\b(?:allgemein|grundsätzlich|üblicherweise|normalerweise|typischerweise|beispielsweise)\b', clause)
                    or re.search(r'\b(?:laut|sagte[n]?|sagen|meinte[n]?|behauptet|berichtete)\b', clause)):
                continue
            # Absence of configured connection functions is an architectural
            # claim, unlike a current connection failure. Recognize only direct
            # first-person possession and its causal subordinate form; quoted,
            # conditional and reported clauses remain nonassertions above.
            functions = r'keine\s+(?:technischen\s+)?verbindungsfunktionen?\b'
            if (re.match(r'ich\s+(?:habe|besitze)\s+' + functions, clause)
                    or re.search(r'\b(?:da|weil)\s+ich\s+' + functions
                                 + r'\s+(?:habe|besitze)\b', clause)):
                return True
            # Complement causes and target-validity predicates cover the
            # observed class, regardless of the target's actual spelling.
            if (re.search(r'\b(?:ist|sind)\s+' + invalid + r'\s+' + destination + r'\b', clause)
                    or re.search(r'\b' + invalid + r'\s+' + destination + r'\s+(?:ist|sind)\b', clause)
                    or re.search(r'\b' + destination + r'\b[^,]*\b(?:ist|sind)\s+(?:nicht\s+gültig|ungültig)\b', clause)):
                return True
    return False
