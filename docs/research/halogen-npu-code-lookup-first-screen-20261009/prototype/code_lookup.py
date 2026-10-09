"""CPU-only bounded source lookup. No model/runtime/network imports or calls."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
import json
import keyword
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
import tokenize
from typing import Protocol, Sequence

APPROVED_REPOSITORY = Path(r'C:\Projects\strix-alloy-clean')
WORK_DIRECTORY = Path(__file__).resolve().parent
SCHEMA = 'code-lookup-cpu-index.v1'
ROOTS = ('server/', 'backends/halogen-wsl2-0.17.3/scripts/')
EXCLUDED_COMPONENTS = {'__pycache__', 'cache', 'caches', 'private', 'secrets',
                       'credentials', 'tokens', 'node_modules'}
WORD = re.compile(r'[A-Za-z_][A-Za-z_0-9]*|[0-9]+')
CONFIG = {'max_lines': 32, 'max_excerpt_utf8_bytes': 8192,
          'max_source_bytes': 1_000_000, 'shortlist_limit': 12,
          'result_limit': 3, 'bm25_k1': 1.2, 'bm25_b': 0.75}


class Reranker(Protocol):
    """Later same-model CPU/NPU adapters must supply complete frozen identity."""
    identity: dict[str, str]

    def rerank(self, query: str, candidates: Sequence[dict]) -> Sequence[float]: ...


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('utf-8')


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _approved_repo(repo) -> Path:
    repo = Path(repo).resolve(strict=True)
    if repo != APPROVED_REPOSITORY.resolve(strict=True):
        raise ValueError('repository is outside the frozen approved root')
    return repo


def _work_path(path) -> Path:
    path = Path(path).resolve()
    if not path.is_relative_to(WORK_DIRECTORY):
        raise ValueError('index/output must remain in the isolated work directory')
    return path


def _allowed(relative: str) -> bool:
    if '\\' in relative or ':' in relative:
        return False
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or path.suffix != '.py':
        return False
    if not any(relative.startswith(root) for root in ROOTS):
        return False
    for part in path.parts:
        lower = part.lower()
        if lower.startswith('.') or lower in EXCLUDED_COMPONENTS:
            return False
        if lower.startswith('private') or lower in {'secrets.py', 'credentials.py', 'tokens.py'}:
            return False
    return True


def _tracked_inventory(repo: Path) -> list[str]:
    # Read-only Git metadata; source files are not executed or recursively scanned.
    top = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--show-toplevel'],
                         check=True, capture_output=True, text=True).stdout.strip()
    if Path(top).resolve() != repo:
        raise ValueError('explicit repository must be the Git top level')
    data = subprocess.run(['git', '-C', str(repo), 'ls-files', '-z', '--', *ROOTS],
                          check=True, capture_output=True).stdout
    return sorted(set(p.decode('utf-8') for p in data.split(b'\0') if p))


def _selected_paths(repo: Path) -> list[str]:
    return sorted(p for p in _tracked_inventory(repo) if _allowed(p))


def _safe_source(repo: Path, relative: str) -> Path:
    if not _allowed(relative):
        raise ValueError('source reference is outside the allowlist')
    path = repo
    for component in PurePosixPath(relative).parts:
        path = path / component
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or (getattr(info, 'st_file_attributes', 0) & 0x400):
            raise ValueError('symlink or junction source is forbidden')
    if not stat.S_ISREG(info.st_mode) or not path.resolve().is_relative_to(repo):
        raise ValueError('source must be a regular file within the approved repository')
    return path


def _read_source(repo: Path, relative: str) -> tuple[bytes, list[str], str]:
    path = _safe_source(repo, relative)
    data = path.read_bytes()
    _safe_source(repo, relative)
    encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    return data, data.decode(encoding).splitlines(keepends=True), encoding


def _terms(text: str) -> list[str]:
    terms = []
    for match in WORD.finditer(text):
        word = match.group()
        terms.append(word.lower())
        pieces = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', word).split('_')
        if len(pieces) > 1:
            terms.extend(piece.lower() for piece in pieces if piece)
    return terms


def _identifier_lines(data: bytes) -> dict[str, list[int]]:
    positions = {}
    try:
        for token in tokenize.tokenize(io.BytesIO(data).readline):
            if token.type == tokenize.NAME and not keyword.iskeyword(token.string):
                positions.setdefault(token.string.lower(), set()).add(token.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # Invalid/incomplete source can still have lexical matches; not fake identifiers.
        return {}
    return {name: sorted(lines) for name, lines in positions.items()}


def _chunk_id(path: str, digest: str, start: int, end: int) -> str:
    return _hash(_canonical([SCHEMA, path, digest, start, end]))


def _chunks(relative: str, digest: str, lines: list[str], identifiers: dict):
    start = 1
    chunk_lines = []
    byte_count = 0
    omissions = []
    chunks = []

    def emit():
        if not chunk_lines:
            return
        end = start + len(chunk_lines) - 1
        counts = Counter(_terms(''.join(chunk_lines) + ' ' + relative))
        positions = {name: [line for line in places if start <= line <= end]
                     for name, places in identifiers.items()
                     if any(start <= line <= end for line in places)}
        chunks.append({'chunk_id': _chunk_id(relative, digest, start, end),
                       'path': relative, 'source_sha256': digest,
                       'start_line': start, 'end_line': end,
                       'identifier_lines': positions, 'terms': dict(sorted(counts.items())),
                       'length': sum(counts.values())})

    for number, line in enumerate(lines, 1):
        size = len(line.encode('utf-8'))
        if size > CONFIG['max_excerpt_utf8_bytes']:
            emit()
            chunk_lines = []
            byte_count = 0
            omissions.append({'path': relative, 'line': number, 'reason': 'oversized_line'})
            start = number + 1
            continue
        if chunk_lines and (len(chunk_lines) >= CONFIG['max_lines'] or
                            byte_count + size > CONFIG['max_excerpt_utf8_bytes']):
            emit()
            chunk_lines = []
            byte_count = 0
            start = number
        if not chunk_lines:
            start = number
        chunk_lines.append(line)
        byte_count += size
    emit()
    return chunks, omissions


def _atomic_json(path: Path, value):
    path = _work_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp',
                                            dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(_canonical(value) + b'\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def build_index(repo, index_path) -> dict:
    repo = _approved_repo(repo)
    index_path = _work_path(index_path)
    selected = _selected_paths(repo)
    sources, chunks, omissions = [], [], []
    for relative in selected:
        data, lines, encoding = _read_source(repo, relative)
        digest = _hash(data)
        if len(data) > CONFIG['max_source_bytes']:
            raise ValueError('source exceeds the frozen byte bound: ' + relative)
        sources.append({'path': relative, 'sha256': digest, 'bytes': len(data),
                        'lines': len(lines), 'encoding': encoding})
        pieces, skipped = _chunks(relative, digest, lines, _identifier_lines(data))
        chunks.extend(pieces)
        omissions.extend(skipped)
    if selected != _selected_paths(repo):
        raise ValueError('tracked corpus changed during build')
    for source in sources:
        if _hash(_read_source(repo, source['path'])[0]) != source['sha256']:
            raise ValueError('source changed during build: ' + source['path'])
    body = {'schema': SCHEMA, 'repository': str(repo), 'config': dict(CONFIG),
            'scope_roots': list(ROOTS), 'sources': sources, 'chunks': chunks,
            'omitted_lines': omissions, 'model_or_provider_used': False}
    index = dict(body, generation=_hash(_canonical(body)))
    _atomic_json(index_path, index)
    return index


def _validate_index(index: dict, repo: Path):
    body = {key: value for key, value in index.items() if key != 'generation'}
    if index.get('schema') != SCHEMA or index.get('config') != CONFIG:
        raise ValueError('unsupported index schema or configuration')
    if index.get('generation') != _hash(_canonical(body)):
        raise ValueError('index generation hash mismatch')
    if Path(index['repository']).resolve() != repo:
        raise ValueError('index belongs to a different repository')
    paths = [source['path'] for source in index['sources']]
    if paths != sorted(set(paths)) or not all(_allowed(p) for p in paths):
        raise ValueError('invalid source inventory')
    sources = {source['path']: source for source in index['sources']}
    for chunk in index['chunks']:
        source = sources.get(chunk['path'])
        if (not source or chunk['source_sha256'] != source['sha256'] or
                not 1 <= chunk['start_line'] <= chunk['end_line'] <= source['lines'] or
                chunk['end_line'] - chunk['start_line'] + 1 > CONFIG['max_lines'] or
                chunk['chunk_id'] != _chunk_id(chunk['path'], source['sha256'],
                                               chunk['start_line'], chunk['end_line'])):
            raise ValueError('chunk identity or span mismatch')


def load_index(index_path) -> dict:
    return json.loads(_work_path(index_path).read_text(encoding='utf-8'))


def _base_result(index: dict, status: str, reason: str) -> dict:
    return {'schema': 'code-lookup-cpu-result.v1', 'status': status, 'reason': reason,
            'index_generation': index.get('generation'), 'results': [],
            'shortlist_count': 0, 'shortlist': [],
            'rebuild_required': False, 'stale_paths': [],
            'provider': {'status': 'disabled'}, 'main_model_called': False,
            'lookup_sufficient': None, 'ranking_is_correctness_probability': False}


def _rank(index: dict, query: str) -> tuple[list[dict], str, bool]:
    chunks = index['chunks']
    query_terms = set(_terms(query))
    if not query_terms or not chunks:
        return [], 'cpu_bm25', False
    frequencies = Counter(term for chunk in chunks for term in chunk['terms'])
    average = sum(chunk['length'] for chunk in chunks) / len(chunks) or 1.0
    exact = query.strip().lower()
    identifier = bool(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', query.strip()))
    ranked = []
    for chunk in chunks:
        path_match = exact in {chunk['path'].lower(), PurePosixPath(chunk['path']).name.lower()}
        identifier_match = identifier and exact in chunk['identifier_lines']
        score = 0.0
        for term in query_terms:
            count = chunk['terms'].get(term, 0)
            if not count:
                continue
            inverse = math.log(1 + (len(chunks) - frequencies[term] + 0.5) /
                               (frequencies[term] + 0.5))
            denominator = count + CONFIG['bm25_k1'] * (
                1 - CONFIG['bm25_b'] + CONFIG['bm25_b'] * chunk['length'] / average)
            score += inverse * count * (CONFIG['bm25_k1'] + 1) / denominator
        if score > 0 or path_match or identifier_match:
            ranked.append({'chunk': chunk, 'bm25_score': score,
                           'exact_priority': 2 if path_match else int(identifier_match),
                           'identifier_match_lines': chunk['identifier_lines'].get(exact, [])
                           if identifier else []})
    ranked.sort(key=lambda row: (-row['exact_priority'], -row['bm25_score'],
                                row['chunk']['path'], row['chunk']['start_line']))
    if not ranked:
        return [], 'cpu_bm25', False
    priority = ranked[0]['exact_priority']
    exact_rows = [r for r in ranked if r['exact_priority'] == priority] if priority else []
    if priority == 2:
        ambiguous = len({r['chunk']['path'] for r in exact_rows}) > 1
        method = 'cpu_path_bm25'
    elif priority == 1:
        ambiguous = len({(r['chunk']['path'], line) for r in exact_rows
                         for line in r['identifier_match_lines']}) > 1
        method = 'cpu_identifier_bm25'
    else:
        ambiguous = (len(ranked) > 1 and math.isclose(ranked[0]['bm25_score'],
                                                    ranked[1]['bm25_score'],
                                                    rel_tol=1e-12, abs_tol=1e-12))
        method = 'cpu_bm25'
    return ranked[:CONFIG['shortlist_limit']], method, ambiguous


def _excerpt(repo: Path, index: dict, row: dict, method: str) -> dict:
    chunk = row['chunk']
    data, lines, _ = _read_source(repo, chunk['path'])
    if _hash(data) != chunk['source_sha256']:
        raise ValueError('source changed before excerpt: ' + chunk['path'])
    text = ''.join(lines[chunk['start_line'] - 1:chunk['end_line']])
    if len(text.encode('utf-8')) > CONFIG['max_excerpt_utf8_bytes']:
        raise ValueError('excerpt exceeds the frozen byte bound')
    return {'path': chunk['path'], 'start_line': chunk['start_line'],
            'end_line': chunk['end_line'], 'excerpt': text,
            'source_sha256': chunk['source_sha256'], 'chunk_id': chunk['chunk_id'],
            'index_generation': index['generation'], 'ranking_method': method,
            'bm25_score': row['bm25_score'],
            'identifier_match_lines': row['identifier_match_lines']}


def lookup(index: dict, query: str, *, repo, reranker: Reranker | None = None,
           enable_provider: bool = False, gpu_busy: bool = False) -> dict:
    result = _base_result(index, 'invalid_index', 'invalid_index')
    try:
        repo = _approved_repo(repo)
        _validate_index(index, repo)
    except (ValueError, KeyError, TypeError, OSError) as error:
        result['reason'] = type(error).__name__
        return result
    try:
        paths = [source['path'] for source in index['sources']]
        current = _selected_paths(repo)
        stale = sorted(set(paths) ^ set(current))
        for source in index['sources']:
            try:
                if _hash(_read_source(repo, source['path'])[0]) != source['sha256']:
                    stale.append(source['path'])
            except (ValueError, OSError, UnicodeError, SyntaxError):
                stale.append(source['path'])
        if stale:
            result.update(status='stale_index', reason='tracked_inventory_or_source_changed',
                          rebuild_required=True, stale_paths=sorted(set(stale)))
            return result
    except (ValueError, OSError, subprocess.SubprocessError):
        result.update(status='stale_index', reason='tracked_inventory_unavailable',
                      rebuild_required=True)
        return result
    if not isinstance(query, str) or not query.strip() or len(query) > 1000:
        result.update(status='no_match', reason='empty_or_invalid_query')
        return result
    shortlist, method, ambiguous = _rank(index, query)
    result['shortlist_count'] = len(shortlist)
    if not shortlist:
        result.update(status='no_match', reason='no_positive_lexical_match')
        return result
    if enable_provider:
        if gpu_busy:
            result['provider'] = {'status': 'gpu_busy_cpu_fallback'}
        elif reranker is None:
            result['provider'] = {'status': 'unavailable_cpu_fallback'}
        else:
            try:
                identity = dict(reranker.identity)
                required = ('model_sha256', 'tokenizer_sha256', 'preprocessing_sha256')
                if not all(re.fullmatch(r'[a-f0-9]{64}', identity.get(k, '')) for k in required):
                    raise ValueError('incomplete frozen same-model identity')
                candidates = [_excerpt(repo, index, row, method) for row in shortlist]
                scores = list(reranker.rerank(query, candidates))
                if len(scores) != len(shortlist) or not all(math.isfinite(float(s)) for s in scores):
                    raise ValueError('invalid reranker scores')
                scored = sorted(zip(shortlist, scores), key=lambda pair: -float(pair[1]))
                shortlist = [row for row, _ in scored]
                method = 'explicit_same_model_reranker'
                result['provider'] = {'status': 'enabled', 'identity': identity,
                                      'scores_are_probabilities': False}
            except Exception as error:
                result['provider'] = {'status': 'failed_cpu_fallback',
                                      'error_type': type(error).__name__}
    result['shortlist'] = [dict(path=row['chunk']['path'],
                               start_line=row['chunk']['start_line'],
                               end_line=row['chunk']['end_line'],
                               chunk_id=row['chunk']['chunk_id'],
                               source_sha256=row['chunk']['source_sha256'],
                               index_generation=index['generation'],
                               bm25_score=row['bm25_score'],
                               exact_priority=row['exact_priority']) for row in shortlist]
    try:
        result['results'] = [_excerpt(repo, index, row, method)
                             for row in shortlist[:CONFIG['result_limit']]]
    except (ValueError, OSError, UnicodeError, SyntaxError):
        result.update(status='stale_index', reason='source_changed_before_return',
                      results=[], shortlist=[], rebuild_required=True)
        return result
    result.update(status='ambiguous' if ambiguous else 'ok',
                  reason='multiple_exact_locations_or_top_score_tie' if ambiguous
                  else 'ranked_source_locations_not_answer_confidence', ranking_method=method)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    for command in ('build', 'query'):
        child = subparsers.add_parser(command)
        child.add_argument('--repo', required=True)
        child.add_argument('--index', required=True)
        child.add_argument('--output')
        if command == 'query':
            child.add_argument('--query', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'build':
            index = build_index(args.repo, args.index)
            result = {'status': 'built', 'generation': index['generation'],
                      'source_files': len(index['sources']), 'chunks': len(index['chunks']),
                      'omitted_lines': index['omitted_lines'], 'model_or_provider_used': False}
        else:
            result = lookup(load_index(args.index), args.query, repo=args.repo)
        if args.output:
            _atomic_json(Path(args.output), result)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 3 if result['status'] in {'stale_index', 'invalid_index'} else 0
    except (ValueError, OSError, UnicodeError, SyntaxError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'error', 'error_type': type(error).__name__,
                          'main_model_called': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
