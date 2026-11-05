"""Bounded literal equivalence for numeric local speech, never business validation.

Explicit German cardinals can support their digit spelling. Ordinal days and
calendar padding require an explicit day/month pair. No fuzzy ASR repair,
implicit year, arithmetic, identifier normalization or semantic field inference.
"""
import re

_SMALL = {'null': 0, 'eins': 1, 'zwei': 2, 'drei': 3, 'vier': 4, 'fünf': 5,
          'fuenf': 5, 'sechs': 6, 'sieben': 7, 'acht': 8, 'neun': 9, 'zehn': 10,
          'elf': 11, 'zwölf': 12, 'zwoelf': 12, 'dreizehn': 13, 'vierzehn': 14,
          'fünfzehn': 15, 'fuenfzehn': 15, 'sechzehn': 16, 'siebzehn': 17,
          'achtzehn': 18, 'neunzehn': 19}
_TENS = {'zwanzig': 20, 'dreißig': 30, 'dreissig': 30, 'vierzig': 40,
         'fünfzig': 50, 'fuenfzig': 50, 'sechzig': 60, 'siebzig': 70,
         'achtzig': 80, 'neunzig': 90}
_UNITS = {word: number for word, number in _SMALL.items() if 1 <= number <= 9}
_UNITS['ein'] = 1
_ORDINAL = {'erst': 1, 'zweit': 2, 'dritt': 3, 'viert': 4, 'fünft': 5,
            'fuenft': 5, 'sechst': 6, 'siebt': 7, 'acht': 8, 'neunt': 9,
            'zehnt': 10, 'elft': 11, 'zwölft': 12, 'zwoelft': 12}
_MONTH = {'januar': 1, 'februar': 2, 'märz': 3, 'maerz': 3, 'april': 4,
          'mai': 5, 'juni': 6, 'juli': 7, 'august': 8, 'september': 9,
          'oktober': 10, 'november': 11, 'dezember': 12}
_WORD = re.compile(r'(?<!\w)[a-zäöüß]{1,64}(?!\w)', re.I)
_DATE = re.compile(r'(?<!\w)([a-zäöüß]{1,64}|\d{1,2})\.?\s+('
                   + '|'.join(_MONTH) + r')(?!\w)', re.I)


def _under_hundred(word):
    if word in _SMALL:
        return _SMALL[word]
    if word in _TENS:
        return _TENS[word]
    for tens, value in _TENS.items():
        suffix = 'und' + tens
        if word.endswith(suffix) and word[:-len(suffix)] in _UNITS:
            return value + _UNITS[word[:-len(suffix)]]
    return None


def _under_thousand(word):
    if word.count('hundert') == 1:
        prefix, suffix = word.split('hundert')
        hundreds = 1 if not prefix else _UNITS.get(prefix)
        if hundreds is None:
            return None
        if suffix.startswith('und'):
            suffix = suffix[3:]
            if not suffix:
                return None
        remainder = 0 if not suffix else 1 if suffix == 'ein' else _under_hundred(suffix)
        return None if remainder is None else hundreds * 100 + remainder
    return _under_hundred(word)


def _cardinal(word):
    if not 1 <= len(word) <= 64:
        return None
    if word.count('tausend') == 1:
        prefix, suffix = word.split('tausend')
        thousands = 1 if not prefix else _UNITS.get(prefix)
        if thousands is None:
            return None
        if suffix.startswith('und'):
            suffix = suffix[3:]
            if not suffix:
                return None
        remainder = 0 if not suffix else 1 if suffix == 'ein' else _under_thousand(suffix)
        return None if remainder is None else thousands * 1000 + remainder
    return _under_thousand(word)


def _ordinal(word):
    for ending in ('en', 'er', 'es', 'em', 'e'):
        if not word.endswith(ending):
            continue
        stem = word[:-len(ending)]
        if stem in _ORDINAL:
            return _ORDINAL[stem]
        if stem.endswith('st'):
            value = _cardinal(stem[:-2])
            if value is not None and value >= 20:
                return value
        if stem.endswith('t'):
            value = _cardinal(stem[:-1])
            if value is not None and 13 <= value <= 19:
                return value
    return None


def has_unbound_numbers(text, source):
    """Keep exact digit matching and add only explicit lexical equivalents."""
    requested = set(re.findall(r'\d+', text))
    if not requested:
        return False
    # Existing conversation protocol bounds are tighter; refuse malformed callers.
    if len(text) > 16384 or len(source) > 65536:
        return True
    available = set(re.findall(r'\d+', source))
    if requested <= available:
        return False
    for match in _WORD.finditer(source):
        word = match.group().casefold()
        value = _cardinal(word)
        if value is not None:
            available.add(str(value))
    # A month name alone does not license a new number. Calendar zero-padding
    # comes only from an explicit day/month pair, never general identifiers.
    for match in _DATE.finditer(source):
        day_word = match.group(1).casefold()
        day = int(day_word) if day_word.isdecimal() else _ordinal(day_word)
        if day is None:
            day = _cardinal(day_word)
        if day is not None and 1 <= day <= 31:
            month = _MONTH[match.group(2).casefold()]
            available.update((str(day), f'{day:02d}', str(month), f'{month:02d}'))
    return not requested <= available
