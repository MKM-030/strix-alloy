"""Pinned, immutable bytes for the finite two-lifecycle qualification."""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .build_identity import checked_path

WORKLOAD_SHA256 = '30D633A46F3F16433557CFF41E7F01C3A28D75132B875BEE63B8E39A332ACC38'
WORKLOAD_PATH = Path(__file__).resolve().parents[2] / 'config/gufo-service-lifecycle-workload.json'
MAX_MANIFEST_BYTES = 262144


@dataclass(frozen=True)
class PreparedPost:
    attempt: int
    request_id: str
    route: str
    body: bytes
    body_sha256: str
    expected_status: int
    expected_error: str | None
    step_json: str


@dataclass(frozen=True)
class Workload:
    raw: bytes

    def __post_init__(self):
        if (type(self.raw) is not bytes or len(self.raw) > MAX_MANIFEST_BYTES
                or sha256(self.raw).hexdigest().upper() != WORKLOAD_SHA256):
            raise ValueError('finite_workload_identity')

    def document(self):
        return json.loads(self.raw.decode('utf-8'))

    def limits(self):
        return self.document()['limits']

    def lifecycle(self, index):
        if type(index) is not int or index not in (1, 2):
            raise ValueError('finite_lifecycle_index')
        return self.document()['lifecycles'][index - 1]

    def post(self, index, attempt):
        life = self.lifecycle(index)
        if type(attempt) is not int or not 1 <= attempt <= life['maximum_post_attempts']:
            raise ValueError('finite_post_index')
        step = life['steps'][attempt - 1]
        row = next(row for row in self.document()['request_pool'] if row['id'] == step['request'])
        body = row['body'].encode('utf-8') if row['encoding'] == 'utf8' else bytes.fromhex(row['body'])
        digest = sha256(body).hexdigest().upper()
        if not row['scheduled'] or len(body) != row['body_bytes'] or digest != row['body_sha256']:
            raise ValueError('finite_request_identity')
        status = step.get('expected_http_status', row['expected_http_status'])
        error = row['expected_error_code']
        if 'allowed_error_codes' in step:
            error = step['allowed_error_codes'][0]
        return PreparedPost(attempt, row['id'], row['route'], body, digest,
                            status, error, json.dumps(step, sort_keys=True))


def load_workload(path=WORKLOAD_PATH):
    path = checked_path(path)
    with path.open('rb') as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    workload = Workload(raw)
    for index in (1, 2):
        for attempt in range(1, workload.lifecycle(index)['maximum_post_attempts'] + 1):
            workload.post(index, attempt)
    return workload
