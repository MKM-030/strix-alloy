"""Default-off private timing metadata for the exact 0.20.3 image API."""
import hashlib
import types

UPSTREAM = '/halogen/tools/serve_api.py'
UPSTREAM_SHA256 = '7f529cd224e973265237d70e8b9157350302a19faffdc70c05eee3a884e2f4f4'
PRIVATE_KEY = '_hgn0203_native_request_id'
PUBLIC_KEY = 'raw_native_request_id'
MARKER = '_hgn0203_native_identity_observer'


def code_named(parent, name):
    matches = [value for value in parent.co_consts
               if isinstance(value, types.CodeType) and value.co_name == name]
    if len(matches) != 1:
        raise ValueError('Exact upstream function binding is ambiguous')
    return matches[0]


def verify_function(function, expected, namespace):
    if (not isinstance(function, types.FunctionType) or function.__globals__ is not namespace
            or function.__code__.co_filename != UPSTREAM):
        raise ValueError('Exact upstream function ownership changed')
    fields = ('co_code', 'co_consts', 'co_names', 'co_varnames', 'co_argcount',
              'co_kwonlyargcount', 'co_flags', 'co_freevars', 'co_cellvars')
    if any(getattr(function.__code__, key) != getattr(expected, key) for key in fields):
        raise ValueError('Exact upstream function code changed')


def install(namespace, source, *, enabled=False):
    if enabled is not True:
        return False
    if (type(source) is not bytes or hashlib.sha256(source).hexdigest() != UPSTREAM_SHA256
            or MARKER in namespace):
        raise ValueError('Private observer requires the fresh exact upstream API')
    engine = namespace.get('Engine')
    parser = getattr(engine, '_done_dict', None)
    timings = namespace.get('timings_of')
    compiled = compile(source, UPSTREAM, 'exec', dont_inherit=True)
    verify_function(parser, code_named(code_named(compiled, 'Engine'), '_done_dict'), namespace)
    verify_function(timings, code_named(compiled, 'timings_of'), namespace)

    def observed_done(parts):
        result = parser(parts)
        if (type(parts) is not list or len(parts) < 7 or parts[0] != 'D'
                or type(parts[1]) is not str or not parts[1].isascii()
                or not parts[1].isdigit()):
            raise ValueError('Private observer received an invalid native D identity')
        request_id = int(parts[1])
        if (not 1 <= request_id <= 0x7fffffffffffffff or str(request_id) != parts[1]
                or PRIVATE_KEY in result):
            raise ValueError('Private observer received an invalid native request ID')
        return {**result, PRIVATE_KEY: request_id}

    def observed_timings(done, info=None):
        result = timings(done, info)
        if PRIVATE_KEY in done:
            if PUBLIC_KEY in result:
                raise ValueError('Private identity timing field already exists')
            result[PUBLIC_KEY] = done[PRIVATE_KEY]
        return result

    engine._done_dict = staticmethod(observed_done)
    namespace['timings_of'] = observed_timings
    namespace[MARKER] = dict(api_sha256=UPSTREAM_SHA256, default_off=True,
        native_identity_source='Exact D record parts[1] from the matching GEN stream')
    return True
