"""Restore the historical conditional SCC voice locale rules.

Call before the single-system-prompt compatibility dispatch, while the original
public model alias and flattened provider message are still present.
"""

SCC_LOCALE_MARKER = '<scc_voice_locale_override_20261013>'
SCC_LOCALE_SUFFIX = '''

<scc_voice_locale_override_20261013>
Diese abschliessenden Regeln haben fuer Sprache und Laenge Vorrang vor den englischen Beispielen oben. Wenn Benutzeranfrage oder Benutzerbeitraege in conversation_history Deutsch sind oder persona Deutsch verlangt, schreibe ALLE benutzersichtbaren Ausgaben, insbesondere transition_message und reply, vollstaendig auf Deutsch. Dies gilt auch nach einer Namensangabe oder Bestaetigung. Eine ausdrueckliche andere Sprachwahl des Benutzers hat Vorrang. Englische Beispiele zeigen nur Schema und Ablauf; uebernimm ihre englische Sprache nicht.
Fuer die SCC-Laptop-Onboarding-Demo oder eine deutsche Laptopbestellung fuer einen neuen Mitarbeiter besteht reasoning aus maximal einem kurzen Satz mit hoechstens 25 Woertern als knapper Entscheidungsbegruendung. Alle JSON-Felder, Aktions-IDs, Aktionstitel und Eingabeschluessel bleiben unveraendert. Alle bestehenden Regeln zur Aktionsauswahl, ausdruecklichen Bestellbestaetigung und Vermeidung automatischer Wiederholungen bleiben verbindlich. Fuer andere Sprachen bleiben die bisherigen Regeln unveraendert.
</scc_voice_locale_override_20261013>'''


def restore_scc_voice_locale(body, *, route, demo_model):
    """Append the historical conditional locale rules to only the SCC demo.

    Returns the original object for other contracts. A matching request gets
    new outer/message containers, retaining all original fields and text.
    """
    if (route != '/v1/chat/completions' or demo_model != 'halogen-v2'
            or not isinstance(body, dict) or body.get('model') != 'halogen-v2'):
        return body
    messages = body.get('messages')
    tools = body.get('tools')
    if (not isinstance(messages, list) or len(messages) != 1
            or not isinstance(messages[0], dict)
            or messages[0].get('role') not in ('system', 'user')
            or not (tools is None or tools == [])):
        return body
    content = messages[0].get('content')
    if (not isinstance(content, str) or 'SCC Laptop Onboarding' not in content
            or SCC_LOCALE_MARKER in content):
        return body
    return dict(body, messages=[dict(messages[0], content=content + SCC_LOCALE_SUFFIX)])
