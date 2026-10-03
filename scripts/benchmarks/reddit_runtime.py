"""One-at-a-time managed benchmark requests; never starts or changes an engine."""
import hashlib
import json
import pathlib
import sys
import threading
import time
import urllib.error
import urllib.request

from reddit_suite import check_identity, digest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'server'))
from host_frames import frame

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / 'server/.local/current.json'


def cold_cache_reused(usage, timings):
    details = usage.get('prompt_tokens_details') or {}
    native = usage.get('gufo') or {}
    return bool(timings.get('cache_n', 0) or usage.get('cached_tokens', 0) or
                details.get('cached_tokens', 0) or native.get('cache_hit') or
                native.get('cache_disk_hit'))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ValueError('Redirect refused')


class ManagedClient:
    def __init__(self, profile_path, expected_run_id, *, state_path=STATE):
        self.profile_path = pathlib.Path(profile_path).resolve(strict=True)
        self.profile_bytes = self.profile_path.read_bytes()
        self.profile = json.loads(self.profile_bytes.decode('utf-8-sig'))
        self.profile_sha256 = digest(self.profile_bytes)
        self.state_path = pathlib.Path(state_path)
        self.expected_run_id = expected_run_id
        state = self.assert_identity()
        self.origin = 'http://127.0.0.1:' + str(state['port'])
        self.model = self.profile['backend']['identifier']
        token_file = pathlib.Path(self.profile['token_file'])
        if not token_file.is_absolute():
            token_file = self.profile_path.parent / token_file
        self.secret = token_file.read_text(encoding='ascii').strip()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.health()

    def assert_identity(self):
        state = json.loads(self.state_path.read_text(encoding='utf-8-sig'))
        check_identity(self.profile, state, self.expected_run_id, self.profile_sha256)
        return state

    def request(self, path, body=None, timeout=1800):
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
        request = urllib.request.Request(self.origin + path, data=data,
            headers={'Authorization': 'Bearer ' + self.secret, 'Content-Type': 'application/json'})
        with self.opener.open(request, timeout=timeout) as response:
            return json.load(response)

    def health(self):
        observed = self.request('/health')
        if (observed.get('backend') != self.model or observed.get('active_requests', 0) or
                observed.get('busy') or observed.get('in_flight', 0) or observed.get('queued', 0)):
            raise ValueError('Active backend is busy or does not match selected profile')
        return observed

    def call(self, messages, max_tokens, mode, label, *, top_logprobs=False,
             cold=False, response_format=None):
        if response_format is not None and (
                self.profile['engine']['kind'] != 'halogen' or
                response_format != {'type': 'json_object'}):
            raise ValueError('Only Halogen json_object response format is supported')
        self.assert_identity()
        self.health()
        before = frame()
        minimum = {key: before[key] for key in ('available_bytes', 'commit_headroom_bytes')}
        if min(minimum.values()) < 18 * 1024**3:
            raise ValueError('Memory headroom is below 18 GiB; request refused')
        stop = threading.Event()
        failures = []

        def sample_memory():
            while not stop.wait(0.2):
                try:
                    measured = frame()
                    for key in minimum:
                        minimum[key] = min(minimum[key], measured[key])
                except OSError as exc:
                    failures.append(str(exc))
                    break

        body = {'model': self.profile['backend']['model'], 'messages': messages,
                'max_tokens': max_tokens, 'temperature': 0, 'seed': 20261002,
                'stream': False, 'enable_thinking': False, 'reasoning_effort': 'none'}
        if self.profile['engine']['kind'] == 'halogen':
            body['drafter'] = 'mtp' if mode == 'speculative' else 'serial'
        if top_logprobs:
            body.update(logprobs=True, top_logprobs=5)
        if cold:
            body['cache_prompt'] = False
        if response_format is not None:
            body['response_format'] = dict(response_format)
        started = time.perf_counter()
        worker = threading.Thread(target=sample_memory, daemon=True)
        worker.start()
        try:
            response = self.request('/v1/chat/completions', body)
        finally:
            wall = time.perf_counter() - started
            stop.set()
            worker.join(timeout=2)
            final = frame()
            for key in minimum:
                minimum[key] = min(minimum[key], final[key])
        self.assert_identity()
        if failures:
            raise OSError('Memory sampling failed: ' + '; '.join(failures))
        if min(minimum.values()) < 18 * 1024**3:
            raise ValueError('Memory reserve crossed during request')
        choice = response['choices'][0]
        message = choice['message']
        text = (message.get('reasoning_content') or '') + (message.get('content') or '')
        if not text:
            text = json.dumps(message.get('tool_calls', []), sort_keys=True, ensure_ascii=False)
        logprobs = choice.get('logprobs')
        top = logprobs.get('content') if isinstance(logprobs, dict) else None
        prompt = json.dumps(messages, ensure_ascii=False, separators=(',', ':'))
        usage = response.get('usage', {})
        timings = response.get('timings', {})
        if (type(usage.get('prompt_tokens', timings.get('prompt_n'))) is not int or
                type(usage.get('completion_tokens', timings.get('predicted_n'))) is not int):
            raise ValueError('Engine did not report comparable token counts')
        if cold and cold_cache_reused(usage, timings):
            raise ValueError('Cold probe reused prompt tokens')
        phase = usage.get('gufo', {}) if isinstance(usage.get('gufo'), dict) else timings
        draft = {key: value for key, value in (timings | phase).items()
                 if 'draft' in key or 'accept' in key or 'spec' in key}
        drafted = timings.get('draft_n', usage.get('draft_tokens'))
        accepted = timings.get('draft_n_accepted', timings.get('draft_accepted',
                       usage.get('draft_tokens_accepted')))
        return {'name': label, 'mode': mode, 'prompt_sha256': digest(prompt.encode('utf-8')),
                'text': text, 'sha256': digest(text.encode('utf-8')),
                'requested_output': max_tokens, 'wall_seconds': wall,
                'cold_prompt': cold,
                'response_format': response_format,
                'usage': usage, 'timings': timings, 'engine_phases': phase,
                'draft_accounting': draft or None, 'finish_reason': choice.get('finish_reason'),
                'drafted': drafted, 'accepted': accepted,
                'draft_acceptance': accepted / drafted if isinstance(drafted, int) and
                                    isinstance(accepted, int) and drafted > 0 else None,
                'minimum_memory': minimum, 'top_logprobs': top,
                'reported_model': response.get('model')}


def save_json(path, value):
    pathlib.Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n',
                                  encoding='utf-8')
