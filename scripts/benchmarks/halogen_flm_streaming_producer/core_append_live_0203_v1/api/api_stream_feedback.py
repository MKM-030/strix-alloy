"""Default-off queued streaming exact-ID feedback for the pinned Halogen0.20.3 API methods."""
import ast
import hashlib
import time
import types
import uuid

from token_feedback import TokenFeedback

UPSTREAM = '/halogen/tools/serve_api.py'
UPSTREAM_SHA256 = '7f529cd224e973265237d70e8b9157350302a19faffdc70c05eee3a884e2f4f4'
GLOBAL_NAME = '_hgn0203_stream_feedback'


def nested_code(parent, name):
    matches = [item for item in parent.co_consts if isinstance(item, types.CodeType) and item.co_name == name]
    if len(matches) != 1:
        raise ValueError('Ambiguous pinned upstream function')
    return matches[0]


def verify_method(method, code, namespace):
    if (not isinstance(method, types.FunctionType) or method.__globals__ is not namespace
            or method.__code__.co_filename != UPSTREAM):
        raise ValueError('Pinned API method ownership differs')
    fields = ('co_code', 'co_consts', 'co_names', 'co_varnames', 'co_argcount', 'co_posonlyargcount',
              'co_kwonlyargcount', 'co_flags', 'co_freevars', 'co_cellvars')
    if any(getattr(method.__code__, field) != getattr(code, field) for field in fields):
        raise ValueError('Pinned API method code differs')


class CaptureObserver:
    def __init__(self, publish, publisher, allowed_prompts):
        self.publish = publish
        self.publisher = publisher
        self.active = {}
        self.allowed_prompts = frozenset(allowed_prompts)

    @property
    def active_count(self):
        return len(self.active)

    def begin(self, engine, request_id, prompt_ids, ctl, options):
        key = (id(engine), request_id)
        if key in self.active:
            return
        epoch = uuid.uuid4().hex
        feedback = TokenFeedback(enabled=True)
        begin = feedback.begin(request_id, epoch, prompt_ids)
        # Qualification is exact-workload, scalar, greedy and plain only.
        # Ineligible requests never send BEGIN and cannot arm native injection.
        if (getattr(engine, 'n_slots', None) != 1
                or (begin['prefix_count'], begin['prefix_sha256']) not in self.allowed_prompts
                or options['max_tokens'] != 128 or options['drafter'] not in (None, 1)
                or options['sample'] is not None or options['penalty'] != ''
                or any(options[name] for name in ('snap', 'snap2', 'snap3', 'images', 'schema',
                       'escape', 'think', 'seg', 'guard', 'keep', 'agent', 'tools', 'keep_end'))
                or options['after'] is not None):
            return
        state = dict(feedback=feedback, epoch=epoch, begin=begin, ctl=ctl,
                     last=begin, token_ids=[], retired=False,
                     began_ns=time.perf_counter_ns())
        self.active[key] = state
        try:
            state['begin_enqueued'] = self.publisher.begin(dict(begin), tuple(prompt_ids)) is True
            state['retired'] = not state['begin_enqueued']
        except Exception as error:
            state['observer_error'] = type(error).__name__
            state['retired'] = True

    def _publish(self, state, packet):
        if state['retired']:
            return
        try:
            if self.publisher.feedback(dict(packet)) is not True:
                state['retired'] = True
        except Exception as error:
            state['observer_error'] = type(error).__name__
            state['retired'] = True

    def feed_line(self, engine, request_id, raw):
        state = self.active.get((id(engine), request_id))
        if state is None:
            return
        ctl = state['ctl']
        if ctl is not None and (ctl.get('stop') or ctl.get('x_sent')):
            packet = state['feedback'].cancel(state['epoch'], reason='presentation_cancelled')
            if packet is not None:
                self._publish(state, packet)
                state['last'] = packet
            return
        try:
            packet = state['feedback'].feed_line(raw, request_epoch=state['epoch'])
        except (ValueError, TypeError) as error:
            packet = state['feedback'].cancel(state['epoch'], reason='invalid_native_stream')
            state['observer_error'] = type(error).__name__
            # Old parser may already have marked a malformed D inactive. The
            # last successfully observed true prefix remains the retirement key.
            if packet is None:
                packet = dict(state['last'], kind='cancelled', token_ids=[],
                              reason='invalid_native_stream', complete_native_stream=False)
            self._publish(state, packet)
            state['last'] = packet
            return
        if packet is not None:
            state['last'] = packet
            if packet['kind'] == 'commit':
                state['token_ids'].extend(packet['token_ids'])
            self._publish(state, packet)

    def feed_parts(self, engine, request_id, parts):
        self.feed_line(engine, request_id, (' '.join(parts) + '\n').encode('ascii'))

    def finish(self, engine, request_id):
        state = self.active.pop((id(engine), request_id), None)
        if state is None:
            return
        terminal = state['last']
        if terminal['kind'] not in ('done', 'error', 'cancelled'):
            packet = state['feedback'].cancel(state['epoch'], reason='generator_closed')
            if packet is None:
                packet = dict(state['last'], kind='cancelled', token_ids=[],
                              reason='generator_closed', complete_native_stream=False)
            self._publish(state, packet)
            terminal = packet
        if self.publish is not None:
            try:
                self.publish(dict(schema='halogen0203.streaming-native-ID-observer.v1',
                                  api_sha256=UPSTREAM_SHA256, native_request_id=request_id,
                                  request_epoch=state['epoch'], begin=state['begin'],
                                  token_ids=state['token_ids'], terminal=terminal,
                                  sidecar_retired=state['retired'],
                                  observer_error=state.get('observer_error'),
                                  elapsed_observer_ns=time.perf_counter_ns()-state['began_ns'],
                                  proves_native_acceptance=False,
                                  proves_producer_time_advantage=False))
            except Exception:
                pass


def observer_call(method, arguments):
    return ast.Expr(value=ast.Call(
        func=ast.Attribute(value=ast.Name(id=GLOBAL_NAME, ctx=ast.Load()), attr=method, ctx=ast.Load()),
        args=[ast.Name(id=name, ctx=ast.Load()) for name in arguments], keywords=[]))


def begin_call():
    names = ('max_tokens', 'drafter', 'sample', 'penalty', 'snap', 'snap2', 'images',
             'schema', 'after', 'escape', 'think', 'seg', 'snap3', 'guard', 'keep',
             'agent', 'tools', 'keep_end')
    node = observer_call('begin', ('self', 'req', 'ids', 'ctl'))
    node.value.args.append(ast.Dict(keys=[ast.Constant(value=name) for name in names],
                                   values=[ast.Name(id=name, ctx=ast.Load()) for name in names]))
    return node


class FeedTransformer(ast.NodeTransformer):
    def __init__(self, batched):
        self.batched = batched
        self.insertions = 0

    def visit_Assign(self, node):
        if (not self.batched and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'parts'
                and ast.unparse(node.value) == 'raw.decode().split()'):
            self.insertions += 1
            return [ast.copy_location(observer_call('feed_line', ('self', 'req', 'raw')), node), node]
        return self.generic_visit(node)

    def visit_If(self, node):
        node = self.generic_visit(node)
        if self.batched and ast.unparse(node.test) == "parts[0] == 'P'":
            self.insertions += 1
            return [ast.copy_location(observer_call('feed_parts', ('self', 'req', 'parts')), node), node]
        return node


def instrument(source):
    tree = ast.parse(source)
    engine = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Engine')
    for name in ('generate', '_gen_batched'):
        method = next(node for node in engine.body if isinstance(node, ast.AsyncFunctionDef) and node.name == name)
        transform = FeedTransformer(batched=name == '_gen_batched')
        method = transform.visit(method)
        if transform.insertions != 1:
            raise ValueError('Pinned native parser insertion count differs')
        if name == 'generate':
            positions = [index for index, node in enumerate(method.body)
                         if isinstance(node, ast.Assign) and ast.unparse(node) == 'req = self.req']
            if len(positions) != 1:
                raise ValueError('Pinned request allocation differs')
            start = positions[0] + 1
            begin = begin_call()
            guarded = ast.Try(body=method.body[start:], handlers=[], orelse=[],
                              finalbody=[observer_call('finish', ('self', 'req'))])
            method.body = method.body[:start] + [begin, guarded]
    return compile(ast.fix_missing_locations(tree), UPSTREAM, 'exec', dont_inherit=True)


def install(namespace, source, *, enabled=False, publish=None, publisher=None, allowed_prompts=()):
    if enabled is not True:
        return False
    if (type(source) is not bytes or hashlib.sha256(source).hexdigest() != UPSTREAM_SHA256
            or GLOBAL_NAME in namespace or (publish is not None and not callable(publish))
            or not callable(getattr(publisher, 'begin', None))
            or not callable(getattr(publisher, 'feedback', None))):
        raise ValueError('Exact source and an explicit private capture sink are required')
    engine = namespace.get('Engine')
    expected = nested_code(compile(source, UPSTREAM, 'exec', dont_inherit=True), 'Engine')
    for name in ('generate', '_gen_batched'):
        verify_method(getattr(engine, name, None), nested_code(expected, name), namespace)
    compiled = instrument(source)
    allowed_prompts = frozenset(allowed_prompts)
    if (not allowed_prompts or any(type(row) is not tuple or len(row) != 2
            or type(row[0]) is not int or not 1 <= row[0] <= 262144
            or type(row[1]) is not str or len(row[1]) != 64
            or any(character not in '0123456789abcdef' for character in row[1])
            for row in allowed_prompts)):
        raise ValueError('Frozen exact actual-ID prompt count/hash whitelist required')
    observer = CaptureObserver(publish, publisher, allowed_prompts)
    patched_engine = nested_code(compiled, 'Engine')
    replacements = {name: types.FunctionType(nested_code(patched_engine, name), namespace)
                    for name in ('generate', '_gen_batched')}
    for name, replacement in replacements.items():
        original = getattr(engine, name)
        replacement.__defaults__ = original.__defaults__
        replacement.__kwdefaults__ = original.__kwdefaults__
        replacement.__annotations__ = original.__annotations__
        replacement.__qualname__ = original.__qualname__
    namespace[GLOBAL_NAME] = observer
    for name, replacement in replacements.items():
        setattr(engine, name, replacement)
    return observer
