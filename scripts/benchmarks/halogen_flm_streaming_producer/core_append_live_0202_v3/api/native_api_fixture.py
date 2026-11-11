"""Exercise the actual pinned API methods with finite native protocol I/O."""
import ast
import asyncio
import importlib.util
from pathlib import Path
import sys
import time
import types
import unittest

HERE = Path(__file__).resolve().parent
API = HERE.parents[1] / 'extracted/serve_api.py'
SOURCE = API.read_bytes()
UPSTREAM = '/halogen/tools/serve_api.py'


def load_adapter():
    path = HERE / 'api_feedback.py'
    if not path.is_file():
        return None
    sys.path.insert(0, str(HERE.parent / 'npu-token-feedback-prep'))
    spec = importlib.util.spec_from_file_location('test0201_api_feedback', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeRefusal(Exception):
    pass


def original_namespace():
    tree = ast.parse(SOURCE)
    engine = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Engine')
    names = {'generate', '_gen_batched', '_done_dict', '_note_pool'}
    methods = [node for node in engine.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    namespace = dict(asyncio=asyncio, time=time, PLD_VIEW=False,
                     LeadPoint=type('LeadPoint', (), {}), FIRST_TOKEN_S=5,
                     NEXT_TOKEN_S=5, ABORT_DRAIN_S=1, fe_mark=lambda *args: None,
                     HTTPException=NativeRefusal, engine_refusal=lambda parts: 'refused')
    compiled = compile(SOURCE, UPSTREAM, 'exec', dont_inherit=True)
    def code_named(parent, name):
        return next(value for value in parent.co_consts if isinstance(value, types.CodeType) and value.co_name == name)
    original_engine = code_named(compiled, 'Engine')
    isolated_engine = type('Engine', (), {})
    namespace['Engine'] = isolated_engine
    namespace['t_line_logprob'] = types.FunctionType(code_named(compiled, 't_line_logprob'), namespace)
    # Fresh 0.20.2 generate uses the upstream cached-ID serialization helpers.
    # Bind their real code objects rather than replacing new frontend behavior.
    for name in ('ids_text', 'ids_gen_text'):
        namespace[name] = types.FunctionType(code_named(compiled, name), namespace)
    for method in methods:
        function = types.FunctionType(code_named(original_engine, method.name), namespace)
        function.__defaults__ = tuple(ast.literal_eval(value) for value in method.args.defaults)
        setattr(isolated_engine, method.name, staticmethod(function) if method.name == '_done_dict' else function)
    return namespace


class Reader:
    def __init__(self, lines):
        self.lines = iter(lines)

    async def readline(self):
        return next(self.lines)


class Writer:
    def __init__(self):
        self.lines = []

    def write(self, line):
        self.lines.append(line)

    async def drain(self):
        return None


async def engine_for(namespace, lines, slots=1):
    engine = namespace['Engine'].__new__(namespace['Engine'])
    async def ensure():
        return None
    async def close():
        engine.r = engine.w = None
    engine._ensure, engine.close = ensure, close
    engine.req, engine.n_slots, engine.info = 40, slots, {}
    engine.w, engine.r = Writer(), Reader(lines)
    engine.streams, engine.wlock = {}, asyncio.Lock()
    return engine
