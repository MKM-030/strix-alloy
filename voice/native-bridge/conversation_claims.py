"""Narrow wording guard for local conversation, never business-result authority.

Balanced quotations and questions are not direct assertions. This recognizes
clear German storage/check claims, not arbitrary intent or full semantics.
"""
import re


def unproven_storage_or_check_claim(text):
    unquoted = re.sub(r'\u201e[^\u201c\u201d]*[\u201c\u201d]|\u201c[^\u201d]*\u201d|'
                      r'\u00ab[^\u00bb]*\u00bb|"[^"]*"|'
                      r'\u201a[^\u2018]*\u2018|\u2018[^\u2019]*\u2019|'
                      r"(?<!\w)'[^']*'(?!\w)", ' ', text)
    direct = (r'\b(?P<aux>ich\s+(?:habe|hatte)|(?:habe|hatte)\s+ich|'
              r'wir\s+(?:haben|hatten)|(?:haben|hatten)\s+wir|'
              r'ist|sind|wird|werden|wurde|wurden|war|waren)\b'
              r'(?P<between>[^,.!?;\n]*?)\b(?:notiert|gespeichert|gepr\u00fcft)\b')
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
                following = value[claim.end():]
                if (re.match(r'\s+werden\b', following, re.I)
                        or re.search(r'\b(?:sobald|wenn|falls|sofern)\b', following, re.I)):
                    continue
            return True
    return False
