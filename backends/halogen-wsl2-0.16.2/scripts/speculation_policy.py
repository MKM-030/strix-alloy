"""Bounded opt-in native speculation policies for the pinned 0.16.2 engine.

The supported upstream defaults are PLD=3,3 and SPEC_ADAPT=32,0.35,64:
https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/FLAGS.md
Only those policies and explicit off are accepted for matched ablations.
Omission leaves the image defaults intact; no measured gain is implied.
"""
import json

POLICIES = {
    'HALOGEN_PLD': ('0', '3,3'),
    'HALOGEN_SPEC_ADAPT': ('0', '32,0.35,64'),
}


def validate(controls):
    if type(controls) is not dict:
        raise ValueError('Speculation policy must be a JSON object')
    result = {}
    for key, value in controls.items():
        if key not in POLICIES:
            raise ValueError('Unsupported speculation policy: ' + str(key))
        if type(value) is not str or value not in POLICIES[key]:
            raise ValueError('Speculation policy requires an explicit off or stock string: ' + key)
        result[key] = value
    return result


def parse(text):
    if not isinstance(text, str) or len(text) > 1024:
        raise ValueError('Speculation policy JSON exceeds the 1024-character budget')

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate speculation policy: ' + key)
            result[key] = value
        return result

    return validate(json.loads(text, object_pairs_hook=unique))


def environment(controls):
    return {} if controls is None else validate(controls)
