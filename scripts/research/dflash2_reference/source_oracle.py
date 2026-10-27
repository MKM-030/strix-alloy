"""Independent AST oracle; no upstream module imports or import-time Torch work.

Source is SGLang, Apache-2.0: see sources/SGLANG_LICENSE and provenance.json.
Only compilation decorators and torch._dynamo.mark_static statements are removed.
"""
import ast
import copy
import hashlib
from functools import lru_cache
from pathlib import Path

SOURCE = Path(__file__).with_name('sources') / 'sglang_dflash.py'
SOURCE_SHA256 = 'b7b541368cbbb072a679d08ba5bf0f952f4a43f02b6c078562b2ea7a9ddfd01b'
NAMES = ('_grouped_conv', '_score_edges', '_follow_maps')
CLASSES = ('DFlashGroupedConv',)

class _AnnotationsOnly(ast.NodeTransformer):
    def visit_Expr(self, node):
        if (isinstance(node.value, ast.Call) and
                ast.unparse(node.value.func) == 'torch._dynamo.mark_static'):
            return None
        return self.generic_visit(node)

def extracted_tree():
    data = SOURCE.read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError('Pinned SGLang source bytes differ')
    module = ast.parse(data, filename=str(SOURCE))
    functions = {n.name: n for n in module.body if isinstance(n, ast.FunctionDef)}
    selected = []
    for name in NAMES:
        node = copy.deepcopy(functions[name])
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or ast.unparse(decorator.func) != 'torch.compile':
                raise ValueError('Unexpected source decorator')
        node.decorator_list = []
        selected.append(_AnnotationsOnly().visit(node))
    classes = {n.name:n for n in module.body if isinstance(n, ast.ClassDef)}
    for name in CLASSES:
        node = copy.deepcopy(classes[name])
        if node.decorator_list:
            raise ValueError('Unexpected source class decorator')
        selected.append(_AnnotationsOnly().visit(node))
    return ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))

@lru_cache(maxsize=1)
def source_functions():
    # Explicit invocation only. No SGLang, compiler, distributed or device API.
    import torch
    namespace = {'torch': torch, 'F': torch.nn.functional, 'nn': torch.nn}
    exec(compile(extracted_tree(), str(SOURCE), 'exec'), namespace)
    return {name: namespace[name] for name in NAMES + CLASSES}
