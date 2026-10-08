"""Typed defaults supported by the pinned 0.17.2 upstream chat API.

Requests retain upstream precedence and forced-tool handling. Only these three
defaults enter the container; parent environment variables are not forwarded.
"""
import json

EFFORTS = ('minimal', 'low', 'medium', 'high', 'xhigh', 'max')
FIELDS = ('enable_thinking', 'reasoning_effort', 'max_thinking_tokens')


def validate(defaults):
    if type(defaults) is not dict:
        raise ValueError('API defaults must be a JSON object')
    result = {}
    for key, value in defaults.items():
        if key not in FIELDS:
            raise ValueError('Unsupported API default: ' + str(key))
        if key == 'enable_thinking' and type(value) is not bool:
            raise ValueError('enable_thinking must be a boolean')
        if key == 'reasoning_effort' and (type(value) is not str or value not in EFFORTS):
            raise ValueError('reasoning_effort must be minimal, low, medium, high, xhigh or max; use enable_thinking=false for Off')
        if key == 'max_thinking_tokens' and (type(value) is not int or not 1 <= value <= 1 << 30):
            raise ValueError('max_thinking_tokens must be an integer from 1 to 1073741824')
        result[key] = value
    return result


def parse(text):
    if type(text) is not str or len(text) > 1024:
        raise ValueError('API defaults JSON exceeds the 1024-character budget')

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate API default: ' + key)
            result[key] = value
        return result

    return validate(json.loads(text, object_pairs_hook=unique))


def environment(defaults):
    result = {}
    for key, value in ({} if defaults is None else validate(defaults)).items():
        if key == 'enable_thinking':
            result['HALOGEN_ENABLE_THINKING'] = '1' if value else '0'
        elif key == 'reasoning_effort':
            result['HALOGEN_REASONING_EFFORT'] = value
        else:
            result['HALOGEN_MAX_THINKING_TOKENS'] = str(value)
    return result
