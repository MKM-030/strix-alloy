"""Publish human text from the one known tool-postprocessor envelope.

Unknown formats remain unchanged. This is not a general JSON-to-speech
transformer and makes no claim about any unlogged live call payload.
"""
import json

MAX_ENVELOPE_BYTES = 32768


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate JSON key')
        value[key] = item
    return value


def _reject_constant(value):
    raise ValueError('non-JSON constant')


def spoken_text(value):
    """Unwrap exactly one complete, bounded processed_output string object.

    Preserve empty/whitespace-only content as its original envelope rather
    than silently deleting a reply. Do not stringify nonstrings or change
    ordinary prose, other JSON shapes, natural brackets or record numbers.
    """
    if not isinstance(value,str) or len(value) > MAX_ENVELOPE_BYTES:
        return value
    try:
        if len(value.encode('utf-8')) > MAX_ENVELOPE_BYTES:
            return value
    except UnicodeError:
        return value
    if not value.lstrip().startswith('{'):
        return value
    try:
        data = json.loads(value,object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
    except (ValueError,RecursionError):
        return value
    if (type(data) is not dict or set(data) != {'processed_output'}
            or type(data['processed_output']) is not str
            or not data['processed_output'].strip()):
        return value
    text = data['processed_output']
    try:
        text.encode('utf-8')  # A surrogate escape must not introduce invalid speech text.
    except UnicodeError:
        return value
    return text
