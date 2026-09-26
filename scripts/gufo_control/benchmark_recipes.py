"""Fixed research recipes and offline validators; never execute generated code.

Fixture text and public sampler fields: gufo-benchmark-recipes-20260926.md.
Halogen filler: c8270bb31cd824a0bf53fe9ecf80059c13e7a5bf/tools/halogen-bench.py.
"""
import ast
from copy import deepcopy
import json
import operator

from . import smoke_http, smoke_guard

PROFILE_4K = 'ar4k-iq4xs-correctness-pp1-v2'
PROFILE_16K = 'ar16k-iq4xs-pp1-cache-v1'
FILLER = 'The unified memory architecture changes how inference engines schedule work across the accelerator and the host processor. '
CACHE_INSTRUCTION = '\nGive a concise summary of the passage above.'
FIXTURES = {
    'EN': {'max_tokens':128, 'prompt':'A service returns HTTP 200 but its JSON body is missing the required "id" field. In exactly two sentences, explain whether the request succeeded at the transport layer and whether it passed schema validation. State one safe next diagnostic step.'},
    'DE': {'max_tokens':128, 'prompt':'Antworte ausschließlich mit einem JSON-Objekt ohne Markdown. Aus diesen Meldungen: "Ticket A: Drucker offline, eine Person betroffen" und "Ticket B: Datenbank nicht erreichbar, alle Nutzer betroffen". Verwende genau die Schlüssel "sprache", "hoechste_prioritaet" und "begruendung". Setze sprache auf "de", hoechste_prioritaet auf "B" und begruendung auf einen kurzen deutschen Satz, der die Auswirkung auf alle Nutzer erklärt.'},
    'CODE': {'max_tokens':256, 'prompt':'Write only Python code defining clamp(x, lo, hi). If lo > hi, raise ValueError. Otherwise return x limited to the inclusive interval [lo, hi]. Do not import anything or include a test runner.'},
    'TOOL': {'max_tokens':128, 'prompt':'Use the available function to look up the status of ticket INC-2047. Do not guess its status or answer in prose before the lookup.'},
    'LONG': {'max_tokens':256, 'prompt':'Write a numbered, practical runbook for diagnosing a slow local HTTP inference endpoint. Cover request timing, prompt token count and cache state, decode timing, and memory pressure. Give at least eight steps, each with a specific observation and a next action. Continue until you reach the response budget.'},
}
TOOL = {'type':'function','function':{'name':'lookup_ticket','description':'Look up one incident ticket by ID.','parameters':{'type':'object','properties':{'ticket_id':{'type':'string'}},'required':['ticket_id'],'additionalProperties':False}}}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def _profile(profile_id):
    if profile_id not in (PROFILE_4K, PROFILE_16K):
        raise ValueError('unknown_profile')
    return profile_id == PROFILE_4K


def recipe_definition(profile_id: str) -> dict:
    four = _profile(profile_id)
    schedule = []

    def add(case, kind='measurement', mode='greedy', repetition=0, target=None, cache=False, budget=1):
        schedule.append(dict(ordinal=len(schedule), kind=kind, case=case, mode=mode,
            repetition=repetition, target_prompt_tokens=target, cache_prompt=cache,
            output_budget=budget))

    add('WARMUP', kind='warmup', budget=64)
    if four:
        cases = list(FIXTURES)
        for rep in range(3):
            modes = ('greedy','sampled') if rep % 2 == 0 else ('sampled','greedy')
            for case in cases[rep:]+cases[:rep]:
                for mode in modes:
                    add(case, mode=mode, repetition=rep, budget=FIXTURES[case]['max_tokens'])
    for rep in range(2):
        add('CALIBRATION', kind='calibration', repetition=rep)
    targets = [2048]*3 if four else [2048,8192,8192,2048,2048,8192]
    counts = {}
    for target in targets:
        rep = counts.get(target, 0)
        add('PP1', repetition=rep, target=target)
        counts[target] = rep+1
    if not four:
        add('CACHE',kind='warmup',target=2048,budget=64)
        for rep in range(3):
            add('CACHE',repetition=rep,target=2048,cache=True,budget=64)
    return dict(profile_id=profile_id, context_tokens=4096 if four else 16384,
        max_prompt_tokens=3072 if four else 16383, max_requests=36 if four else 13,
        fixtures=deepcopy(FIXTURES), tool=deepcopy(TOOL), warmup_prompt=smoke_http.PROMPT,
        request_base=deepcopy(smoke_http.REQUEST), sampled=dict(temperature=1,top_p=.95,top_k=20,seeds=[1001,1002,1003]),
        schedule=schedule, calibration=dict(first_prompt='x',second_prompt='x'+FILLER*20,
            filler=FILLER, formula='units=max(1,round(max(0,target-first)/((second-first)/20)))',
            rounding='Python round', tolerance_tokens=32, endpoint='/v1/chat/completions',stream=False,
            source_commit='c8270bb31cd824a0bf53fe9ecf80059c13e7a5bf',
            source_file='tools/halogen-bench.py',source_sha256='0587690C50CFA6769B54D67C7553BA8AA3EC861E677082590D322B0B2F0F846F'),
        cache_instruction=CACHE_INSTRUCTION, validator_version=2,
        fixture_source='gufo-benchmark-recipes-20260926.md',
        gufo_source_commit='cff564964e8506c0abb3e530cecb55332187ac6c',
        request_seconds=60,startup_seconds=480,lifetime_seconds=600,
        max_request_bytes=262144,max_response_bytes=1048576,thinking=False,
        semantic_approval='independent_review_required')


def recipe_json(profile_id: str) -> str:
    return canonical(recipe_definition(profile_id))


def build_argv(profile_id: str, secret: str) -> list[str]:
    four = _profile(profile_id)
    argv = smoke_guard.fixed_argv(secret)
    for flag, value in (('--context','4096' if four else '16384'),('--max-tokens','256'),
                        ('--max-request-bytes','262144'),('--max-connections','16')):
        argv[argv.index(flag)+1] = value
    return argv


def calibrated_prompt(target: int, first_tokens: int, second_tokens: int) -> str:
    if (any(type(x) is not int or x < 0 for x in (target,first_tokens,second_tokens))
            or not 1 <= target <= 16383 or second_tokens <= first_tokens):
        raise ValueError('invalid_calibration_counts')
    units = max(1,round(max(0,target-first_tokens)/((second_tokens-first_tokens)/20)))
    if 1 + len(FILLER.encode('utf-8'))*units > 260000:
        raise ValueError('calibration_body_limit')
    return 'x'+FILLER*units


def request_for(row, calibration=None):
    request = deepcopy(smoke_http.REQUEST)
    case = row['case']
    if case in FIXTURES:
        prompt = FIXTURES[case]['prompt']
    elif case == 'WARMUP':
        prompt = smoke_http.PROMPT
    elif case == 'CALIBRATION':
        prompt = 'x'+FILLER*(20 if row['repetition'] else 0)
    elif case in ('PP1','CACHE'):
        prompt = calibrated_prompt(row['target_prompt_tokens'], *calibration)
        if case == 'CACHE': prompt += CACHE_INSTRUCTION
    else:
        raise ValueError('unknown_case')
    request.update(messages=[dict(role='user',content=prompt)], max_tokens=row['output_budget'],cache_prompt=row['cache_prompt'])
    if row['mode'] == 'sampled':
        request.update(temperature=1,top_p=.95,top_k=20,seed=1001+row['repetition'])
    if case in ('PP1','CALIBRATION'):
        request['stream'] = False
        request.pop('stream_options')
    if case == 'TOOL':
        request.update(tools=[deepcopy(TOOL)],tool_choice='required')
    return request


class _Unsupported(Exception): pass
class _Invalid(Exception): pass
class _Returned(Exception):
    def __init__(self, value): self.value = value
class _RaisedValueError(Exception): pass


def _check_code(text):
    """Bounded syntax inspection and interpretation over four tiny scalar inputs."""
    if len(text) > 32768: return 'failed'
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return 'failed'
    nodes = list(ast.walk(tree))
    if len(nodes) > 512: return 'needs_review'
    forbidden = (ast.Import,ast.ImportFrom,ast.Attribute,ast.For,ast.While,ast.AsyncFor,
                 ast.With,ast.AsyncWith,ast.Lambda,ast.ListComp,ast.SetComp,ast.DictComp,
                 ast.GeneratorExp,ast.Global,ast.Nonlocal,ast.Await,ast.Yield,ast.YieldFrom)
    if any(isinstance(n,forbidden) for n in nodes): return 'failed'
    if len(tree.body)!=1 or not isinstance(tree.body[0],ast.FunctionDef): return 'failed'
    fn = tree.body[0]
    args=fn.args
    if (fn.name!='clamp' or fn.decorator_list or [a.arg for a in args.args]!=['x','lo','hi']
            or args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg or args.defaults
            or args.kw_defaults or fn.returns or any(a.annotation for a in args.args)
            or fn.type_params):
        return 'failed'
    for node in nodes:
        if isinstance(node,ast.Call) and (not isinstance(node.func,ast.Name)
                or node.func.id not in ('min','max','ValueError') or node.keywords):
            return 'failed'
        if isinstance(node,ast.FunctionDef) and node is not fn: return 'failed'
    allowed = (ast.Module,ast.FunctionDef,ast.arguments,ast.arg,ast.If,ast.Return,ast.Raise,
               ast.Compare,ast.IfExp,ast.Name,ast.Load,ast.Constant,ast.Call,ast.Gt,ast.Lt,
               ast.GtE,ast.LtE,ast.Eq,ast.NotEq,ast.UnaryOp,ast.USub,ast.UAdd)
    if any(not isinstance(node,allowed) for node in nodes): return 'needs_review'
    compare = {ast.Gt:operator.gt,ast.Lt:operator.lt,ast.GtE:operator.ge,ast.LtE:operator.le,ast.Eq:operator.eq,ast.NotEq:operator.ne}

    def expression(node, env, depth=0):
        if depth > 32: raise _Unsupported()
        sub = lambda n: expression(n,env,depth+1)
        if isinstance(node,ast.Name) and node.id in env: return env[node.id]
        if isinstance(node,ast.Constant) and type(node.value) in (int,float,bool,str,type(None)):
            if isinstance(node.value,(int,float)) and abs(node.value)>1000000: raise _Unsupported()
            return node.value
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
            return -sub(node.operand) if isinstance(node.op,ast.USub) else +sub(node.operand)
        if isinstance(node,ast.IfExp): return sub(node.body if sub(node.test) else node.orelse)
        if isinstance(node,ast.Compare):
            values = [sub(node.left)]+[sub(v) for v in node.comparators]
            return all(compare[type(op)](a,b) for op,a,b in zip(node.ops,values,values[1:]))
        if isinstance(node,ast.Call) and node.func.id in ('min','max') and 2 <= len(node.args) <= 3:
            return (min if node.func.id=='min' else max)(sub(a) for a in node.args)
        raise _Unsupported()

    def statements(body,env,depth=0):
        if depth>32: raise _Unsupported()
        for node in body:
            if isinstance(node,ast.Return): raise _Returned(expression(node.value,env))
            if isinstance(node,ast.If): statements(node.body if expression(node.test,env) else node.orelse,env,depth+1)
            elif isinstance(node,ast.Raise):
                exc=node.exc
                valid = isinstance(exc,ast.Name) and exc.id=='ValueError'
                valid |= (isinstance(exc,ast.Call) and isinstance(exc.func,ast.Name) and exc.func.id=='ValueError'
                          and len(exc.args)<=1 and all(isinstance(a,ast.Constant) and isinstance(a.value,str) for a in exc.args))
                if not valid or node.cause is not None: raise _Invalid()
                raise _RaisedValueError()
            elif not isinstance(node,ast.If): raise _Unsupported()

    try:
        for values, expected in [((5,0,3),3),((-2,0,3),0),((2,0,3),2),((0,3,1),'ValueError')]:
            actual=None
            try: statements(fn.body,dict(zip(('x','lo','hi'),values)))
            except _Returned as returned: actual=returned.value
            except _RaisedValueError: actual='ValueError'
            if type(actual) is not type(expected) or actual!=expected: return 'failed'
    except _Unsupported:
        return 'needs_review'
    except (TypeError,ValueError,KeyError,RecursionError,_Invalid,OverflowError):
        return 'failed'
    return 'passed'


def _code_assessment(text):
    lines = text.strip().splitlines()
    fenced = (len(lines) >= 3 and lines[0] == '```python'
              and lines[-1] == '```'
              and all('```' not in line for line in lines[1:-1]))
    source = '\n'.join(lines[1:-1]) if fenced else text
    functional = _check_code(source)
    assessment = dict(
        state='needs_review' if fenced and functional == 'passed' else functional,
        format_compliant=not fenced and functional != 'failed',
        functional_state=functional,
        evaluation_source='single_python_fence' if fenced else 'raw_python')
    if fenced:
        assessment['format_violation'] = 'markdown_fence'
    return assessment


def validate_answer(case_id: str, result: dict) -> dict:
    text = result.get('visible_answer','')
    reason = result.get('finish_reason')
    outcome = dict(state='passed',budget_exhausted=reason=='length')
    if case_id!='TOOL' and (result.get('tool_calls') or reason not in ('stop','length')):
        outcome['state']='failed'
        return outcome
    if case_id=='WARMUP':
        outcome['state']='passed' if text.strip()=='4' and reason=='stop' else 'failed'
    elif case_id in ('EN','LONG','CACHE'):
        outcome['state']='semantic_review_pending' if text.strip() and reason in ('stop','length') else 'failed'
        if case_id=='LONG':
            count=result.get('metrics',{}).get('completion_tokens')
            outcome.update(early_eos=type(count) is int and count<256,
                sustained_256_sample=count==256 and reason=='length')
    elif case_id=='DE':
        try:
            value=smoke_http._strict_json(text)
            valid=(isinstance(value,dict) and set(value)=={'sprache','hoechste_prioritaet','begruendung'}
                and value['sprache']=='de' and value['hoechste_prioritaet']=='B'
                and isinstance(value['begruendung'],str) and bool(value['begruendung'].strip()))
        except (ValueError,TypeError,RecursionError): valid=False
        outcome['state']='semantic_review_pending' if valid else 'failed'
    elif case_id=='CODE':
        outcome.update(_code_assessment(text))
    elif case_id=='TOOL':
        try:
            calls=result['tool_calls']; call=calls[0]
            valid=(len(calls)==1 and isinstance(call.get('id'),str) and bool(call['id'].strip())
                and call.get('type')=='function' and call['function']['name']=='lookup_ticket'
                and isinstance(call['function']['arguments'],str)
                and smoke_http._strict_json(call['function']['arguments'])=={'ticket_id':'INC-2047'}
                and not text.strip() and reason in ('stop','tool_calls'))
        except (ValueError,TypeError,KeyError,IndexError,RecursionError): valid=False
        outcome['state']=('needs_review' if reason=='stop' else 'passed') if valid else 'failed'
        outcome['protocol_edge_case']=valid and reason=='stop'
    elif case_id not in ('PP1','CALIBRATION'):
        raise ValueError('unknown_case')
    return outcome
