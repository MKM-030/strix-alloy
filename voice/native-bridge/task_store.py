"""Private SQLite journal for call-scoped tasks and durable operation claims."""

import hashlib
import json
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from business_tasks import Agent, Scope, StoreCapacity, StoreConflict, StoreDenied, StoreInvalid, bounded_identifier


_BUSINESS_KINDS = frozenset({"continue_task", "amend_task", "new_task", "cancel_task"})
_VOICE_KEYS = frozenset({"language", "assistant_id", "profile"})
_CREDENTIAL_KEY_PARTS = frozenset({
    "apikey", "bearer", "cookie", "credential", "csrf", "password", "passwd",
    "secret", "sessionid", "token", "authorization", "authentication",
    "privatekey", "accesskey", "authheader", "authkey",
})
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 2048
_TERMINAL_STATES = frozenset({"awaiting_input", "succeeded", "failed", "cancelled", "outcome_unknown"})


def _now():
    return datetime.now(timezone.utc).isoformat()


def _new_id():
    return str(uuid.uuid4())


def _validate_json(value, *, limit=16384):
    """Accept bounded JSON; reject credential-shaped field names at every level.

    Field names are nonempty printable ASCII. Matching ignores case and all
    separators, including punctuation and spaces, so prefixed/header variants
    cannot enter the durable callback, evidence, or event records.
    """
    stack = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            raise StoreInvalid("payload too complex")
        if type(item) is dict:
            if len(item) > _MAX_JSON_NODES - nodes - len(stack):
                raise StoreInvalid("payload too complex")
            for key, nested in item.items():
                if not isinstance(key, str) or not key or len(key) > 128 or not key.isascii() or any(ord(char) < 32 or ord(char) == 127 for char in key):
                    raise StoreInvalid("invalid payload")
                normalized = "".join(char for char in key.casefold() if char.isalnum())
                if any(part in normalized for part in _CREDENTIAL_KEY_PARTS) or normalized.endswith("auth"):
                    raise StoreInvalid("invalid payload")
                stack.append((nested, depth + 1))
        elif type(item) is list:
            if len(item) > _MAX_JSON_NODES - nodes - len(stack):
                raise StoreInvalid("payload too complex")
            stack.extend((nested, depth + 1) for nested in item)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise StoreInvalid("invalid payload")
        elif type(item) is str and len(item) > limit:
            raise StoreInvalid("payload too large")
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise StoreInvalid("invalid payload") from None
    if len(encoded) > limit:
        raise StoreInvalid("payload too large")
    return encoded


def _decode(value):
    return json.loads(value) if value is not None else None


def _receipt_ref(value, *, optional=False):
    if optional and value == '':
        return value
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value):
        raise StoreInvalid('invalid receipt reference')
    return value


class TaskStore:
    """Synchronous journal. Call recover once at process startup, not on open."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.path), timeout=5.0, isolation_level=None, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS scopes (
                scope_id TEXT PRIMARY KEY, call_id TEXT NOT NULL, call_generation INTEGER NOT NULL,
                instance_id TEXT NOT NULL, assistant_id TEXT NOT NULL, principal_id TEXT NOT NULL,
                attached INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY, parent_task_id TEXT, scope_id TEXT NOT NULL REFERENCES scopes(scope_id),
                agent_alias TEXT NOT NULL, agent_id TEXT NOT NULL, registry_revision TEXT NOT NULL,
                capabilities TEXT NOT NULL, objective TEXT NOT NULL, context_version INTEGER NOT NULL DEFAULT 0,
                state TEXT NOT NULL, open_question TEXT, result_version INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS tasks_scope ON tasks(scope_id, created_at);
            CREATE TABLE IF NOT EXISTS operations (
                operation_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(task_id),
                utterance_id TEXT NOT NULL UNIQUE, context_version INTEGER NOT NULL,
                kind TEXT NOT NULL, text TEXT NOT NULL, voice_context TEXT NOT NULL,
                immutable_payload TEXT NOT NULL, dispatch_state TEXT NOT NULL,
                request_ref TEXT, execution_ref TEXT, receipt TEXT,
                replies TEXT, evidence TEXT, outcome TEXT, reason_code TEXT,
                created_at TEXT NOT NULL, submitted_at TEXT, settled_at TEXT
            );
            CREATE INDEX IF NOT EXISTS operations_task ON operations(task_id, created_at);
            CREATE TABLE IF NOT EXISTS inbox (
                event_id TEXT PRIMARY KEY, operation_id TEXT NOT NULL REFERENCES operations(operation_id),
                event_type TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL REFERENCES tasks(task_id), operation_id TEXT REFERENCES operations(operation_id),
                type TEXT NOT NULL, context_version INTEGER NOT NULL,
                payload TEXT NOT NULL, source TEXT NOT NULL, fingerprint TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_task_seq ON events(task_id, sequence);
            CREATE TABLE IF NOT EXISTS commands (
                command_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(task_id),
                scope_id TEXT NOT NULL, text TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scope_questions (
                scope_id TEXT PRIMARY KEY REFERENCES scopes(scope_id),
                task_id TEXT NOT NULL REFERENCES tasks(task_id), text TEXT NOT NULL,
                source TEXT NOT NULL, context_version INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS owned_dispatches (
                operation_id TEXT PRIMARY KEY REFERENCES operations(operation_id),
                task_ref TEXT NOT NULL, command TEXT NOT NULL,
                event_sequence INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS owned_events (
                operation_id TEXT NOT NULL REFERENCES operations(operation_id),
                sequence INTEGER NOT NULL, event_id TEXT NOT NULL UNIQUE,
                PRIMARY KEY(operation_id, sequence)
            );
        """)
        # Additive migration: existing journals and uncertain reservations survive.
        columns = {row['name'] for row in self._db.execute('PRAGMA table_info(scope_questions)')}
        if 'question_id' not in columns:
            self._db.execute("ALTER TABLE scope_questions ADD COLUMN question_id TEXT NOT NULL DEFAULT ''")
        for row in self._db.execute("SELECT scope_id FROM scope_questions WHERE question_id='' ").fetchall():
            self._db.execute('UPDATE scope_questions SET question_id=? WHERE scope_id=?', (_new_id(), row['scope_id']))

    def close(self):
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None

    @contextmanager
    def _transaction(self):
        with self._lock:
            nested = self._db.in_transaction
            savepoint = 'nested_' + uuid.uuid4().hex
            self._db.execute('SAVEPOINT ' + savepoint if nested else "BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._db.execute('ROLLBACK TO ' + savepoint if nested else "ROLLBACK")
                if nested:
                    self._db.execute('RELEASE ' + savepoint)
                raise
            else:
                self._db.execute('RELEASE ' + savepoint if nested else "COMMIT")

    def _event(self, task_id, operation_id, event_type, context_version, payload, source="store", event_id=None):
        encoded = _validate_json(payload)
        fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        self._db.execute(
            "INSERT INTO events(event_id,task_id,operation_id,type,context_version,payload,source,fingerprint) VALUES(?,?,?,?,?,?,?,?)",
            (event_id or _new_id(), task_id, operation_id, event_type, context_version, encoded, source, fingerprint),
        )

    def _task_row(self, task_id, scope_id):
        row = self._db.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None or row["scope_id"] != scope_id:
            raise StoreDenied("task unavailable")
        return row

    def _task_snapshot(self, row):
        scope = self._db.execute("SELECT * FROM scopes WHERE scope_id=?", (row["scope_id"],)).fetchone()
        return {
            "task_id": row["task_id"], "parent_task_id": row["parent_task_id"],
            "scope_id": row["scope_id"], "call_id": scope["call_id"],
            "call_generation": scope["call_generation"], "instance_id": scope["instance_id"],
            "assistant_id": scope["assistant_id"], "principal_id": scope["principal_id"],
            "agent_alias": row["agent_alias"], "agent_id": row["agent_id"],
            "registry_revision": row["registry_revision"], "capabilities": _decode(row["capabilities"]),
            "objective": row["objective"], "context_version": row["context_version"],
            "state": row["state"], "open_question": row["open_question"],
            "result_version": row["result_version"], "created_at": row["created_at"],
            "updated_at": row["updated_at"], "attached": bool(scope["attached"]),
        }

    def _operation_snapshot(self, row):
        return {
            "operation_id": row["operation_id"], "task_id": row["task_id"],
            "utterance_id": row["utterance_id"], "context_version": row["context_version"],
            "kind": row["kind"], "text": row["text"], "voice_context": _decode(row["voice_context"]),
            "immutable_payload": _decode(row["immutable_payload"]), "dispatch_state": row["dispatch_state"],
            "request_ref": row["request_ref"], "execution_ref": row["execution_ref"], "receipt": _decode(row["receipt"]),
            "replies": _decode(row["replies"]), "evidence": _decode(row["evidence"]),
            "outcome": row["outcome"], "reason_code": row["reason_code"],
            "created_at": row["created_at"], "submitted_at": row["submitted_at"], "settled_at": row["settled_at"],
        }

    def create_task(self, scope: Scope, agent: Agent, objective: str, *, task_id: str | None = None) -> dict:
        if not isinstance(scope, Scope) or not isinstance(agent, Agent):
            raise StoreInvalid("invalid binding")
        if not isinstance(objective, str) or not objective or len(objective) > 4000:
            raise StoreInvalid("invalid objective")
        identifier = bounded_identifier(task_id) if task_id is not None else _new_id()
        capabilities = _validate_json(dict(agent.capabilities), limit=4096)
        with self._transaction():
            existing = self._db.execute("SELECT * FROM scopes WHERE scope_id=?", (scope.scope_id,)).fetchone()
            binding = (scope.call_id, scope.call_generation, scope.instance_id, scope.assistant_id, scope.principal_id)
            if existing is None:
                self._db.execute(
                    "INSERT INTO scopes(scope_id,call_id,call_generation,instance_id,assistant_id,principal_id) VALUES(?,?,?,?,?,?)",
                    (scope.scope_id, *binding),
                )
            elif tuple(existing[key] for key in ("call_id", "call_generation", "instance_id", "assistant_id", "principal_id")) != binding:
                raise StoreConflict("scope binding conflict")
            elif not existing["attached"]:
                raise StoreDenied("scope detached")
            if self._db.execute("SELECT COUNT(*) FROM tasks WHERE scope_id=?", (scope.scope_id,)).fetchone()[0] >= 8:
                raise StoreCapacity("task capacity reached")
            if self._db.execute("SELECT 1 FROM tasks WHERE task_id=?", (identifier,)).fetchone():
                raise StoreConflict("task identity conflict")
            now = _now()
            self._db.execute(
                "INSERT INTO tasks(task_id,scope_id,agent_alias,agent_id,registry_revision,capabilities,objective,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (identifier, scope.scope_id, agent.alias, agent.agent_id, agent.revision, capabilities, objective, "queued", now, now),
            )
            self._event(identifier, None, "task_created", 0, {"objective": objective})
            return self._task_snapshot(self._task_row(identifier, scope.scope_id))

    def get_task(self, task_id: str, scope_id: str) -> dict:
        with self._lock:
            return self._task_snapshot(self._task_row(task_id, scope_id))

    def list_tasks(self, scope_id: str) -> list[dict]:
        bounded_identifier(scope_id)
        with self._lock:
            rows = self._db.execute("SELECT * FROM tasks WHERE scope_id=? ORDER BY created_at,task_id", (scope_id,)).fetchall()
            return [self._task_snapshot(row) for row in rows]

    def routing_checkpoint(self, scope_id):
        """Immutable authority snapshot; unrelated progress events do not fence input.

        Scope-wide task identities/versions and latest accepted operations prevent
        a changed set of plausible question targets from acquiring stale authority.
        No callback text, timestamp or result counter is part of this fence.
        """
        bounded_identifier(scope_id)
        with self._lock:
            scope = self._db.execute('SELECT * FROM scopes WHERE scope_id=?', (scope_id,)).fetchone()
            tasks = self.list_tasks(scope_id)
            latest = {}
            for op in self.operations(scope_id):
                latest[op['task_id']] = (op['operation_id'], op['context_version'])
            question = self.question(scope_id)
            return (scope_id, tuple(scope) if scope else None,
                tuple((t['task_id'], t['context_version'], t['state'] in
                       ('succeeded', 'failed', 'cancelled', 'cancel_requested', 'outcome_unknown'),
                       t['agent_alias'], t['agent_id'], t['registry_revision'],
                       tuple(sorted(t['capabilities'].items())), t['open_question'], latest.get(t['task_id'])) for t in tasks),
                tuple(question.items()) if question else None)

    def _check_preconditions(self, scope_id, preconditions, authority):
        if preconditions is not None and preconditions != self.routing_checkpoint(scope_id):
            raise StoreConflict('routing checkpoint changed')
        # Coordinator supplies the current in-process registry/attachment guard.
        # Invoked only within the same SQLite write transaction as acceptance.
        if authority is not None and not authority():
            raise StoreConflict('routing authority changed')

    def routing_snapshot(self, scope_id):
        """Capture question and operation provenance under one journal read lock."""
        with self._transaction():
            return self.question(scope_id), self.list_tasks(scope_id), self.operations(scope_id), self.routing_checkpoint(scope_id)

    def grounded_snapshot(self, scope_id, task_id):
        return self._grounded_read(scope_id, task_id, messages=True)

    def grounded_revision(self, scope_id, task_id):
        return self._grounded_read(scope_id, task_id, messages=False)

    def _grounded_read(self, scope_id, task_id, *, messages):
        """Bounded projections in one SQLite snapshot; never extract private payloads."""
        from grounded_conversation import EvidenceRevision, GroundedSnapshot, freeze
        bounded_identifier(scope_id)
        bounded_identifier(task_id)
        with self._transaction():
            scope = self._db.execute('SELECT scope_id,call_id,call_generation,instance_id,assistant_id,principal_id,attached FROM scopes WHERE scope_id=?', (scope_id,)).fetchone()
            if not scope or not scope['attached']:
                raise StoreDenied('scope unavailable')
            headers = self._db.execute('''SELECT t.task_id,t.scope_id,t.agent_alias,t.agent_id,t.registry_revision,
                t.capabilities,t.objective,t.context_version,t.state,
                latest.operation_id latest_id,latest.context_version latest_version,latest.dispatch_state latest_dispatch
                FROM tasks t LEFT JOIN operations latest ON latest.operation_id=(
                    SELECT operation_id FROM operations o WHERE o.task_id=t.task_id ORDER BY o.rowid DESC LIMIT 1)
                WHERE t.scope_id=? ORDER BY t.created_at,t.task_id LIMIT 9''', (scope_id,)).fetchall()
            if len(headers) > 8:
                raise StoreCapacity('grounded task capacity')
            task = next((h for h in headers if h['task_id'] == task_id), None)
            if task is None:
                raise StoreDenied('task unavailable')
            columns = 'operation_id,context_version,dispatch_state,outcome,kind' + (',text' if messages else '')
            operations = list(reversed(self._db.execute('SELECT ' + columns + ' FROM operations WHERE task_id=? ORDER BY rowid DESC LIMIT 2', (task_id,)).fetchall()))
            pending = bool(self._db.execute("SELECT 1 FROM operations WHERE task_id=? AND dispatch_state='unsubmitted' LIMIT 1", (task_id,)).fetchone())
            question = self._db.execute('SELECT task_id,question_id,context_version,text,source FROM scope_questions WHERE scope_id=?', (scope_id,)).fetchone()
            head = self._db.execute('SELECT sequence FROM events WHERE task_id=? ORDER BY sequence DESC LIMIT 1', (task_id,)).fetchone()
            revision = EvidenceRevision(tuple(scope), tuple(tuple(h) for h in headers),
                tuple(question) if question else None, head[0] if head else 0,
                tuple(tuple(o[k] for k in ('operation_id', 'context_version', 'dispatch_state', 'outcome', 'kind')) for o in operations), pending)
            if not messages:
                return revision
            # Question text belongs only to the selected task; revision reads do
            # not fetch operation bodies or competitors' substantive history.
            task = dict(task)
            task['open_question'] = self._db.execute('SELECT open_question FROM tasks WHERE task_id=? AND scope_id=?', (task_id, scope_id)).fetchone()[0]
            def event(operation_id, kind):
                row = self._db.execute('''SELECT operation_id,event_id,sequence,context_version,fingerprint,payload
                    FROM events WHERE task_id=? AND operation_id=? AND type=? ORDER BY sequence DESC LIMIT 1''',
                    (task_id, operation_id, kind)).fetchone()
                if not row or len(row['payload']) > 16384: return None
                try: payload = _decode(row['payload'])
                except (ValueError, RecursionError): return None
                if not isinstance(payload, dict): return None
                return dict(row), payload
            provenance = []
            for op in operations:
                accepted = event(op['operation_id'], 'utterance_accepted')
                source = None
                if accepted:
                    row, payload = accepted
                    if (row['context_version'] == op['context_version'] and payload.get('kind') == op['kind']
                            and payload.get('text') == op['text']):
                        source = {k: row[k] for k in ('event_id', 'sequence', 'context_version', 'fingerprint')}
                        answered = payload.get('answered_question')
                        if (isinstance(answered, dict) and set(answered) <= {'scope_id','task_id','question_id','context_version','text','source'}
                                and answered.get('task_id') == task_id and answered.get('context_version') == op['context_version']-1
                                and isinstance(answered.get('text'), str) and len(answered['text']) <= 4000):
                            source['answered_question'] = answered
                provenance.append(freeze(source) if source else None)
            backend = None
            if operations:
                latest = operations[-1]
                observation = event(latest['operation_id'], 'backend_observed')
                settlement = event(latest['operation_id'], 'operation_settled')
                candidates = []
                if latest['dispatch_state'] == 'settled' and settlement:
                    row, payload = settlement
                    replies = payload.get('replies')
                    if (isinstance(replies, list) and len(replies) <= 32
                            and all(isinstance(r, str) and len(r) <= 4000 for r in replies)):
                        candidates.append((row, replies[-1] if replies else ''))
                if observation:
                    candidates.append((observation[0], observation[1].get('text')))
                for row, text in candidates:
                    if (row['context_version'] == latest['context_version'] and isinstance(text, str)
                            and 0 < len(text) <= 4000):
                        backend = freeze({k: row[k] for k in ('operation_id','event_id','sequence','fingerprint')} | {'text': text})
                        break
            eligible_question = (question and question['task_id'] == task_id
                and question['context_version'] == task['context_version'] and not pending
                and task['state'] not in ('cancelled','cancel_requested','succeeded','failed','outcome_unknown')
                and question['text'] == task['open_question'])
            return GroundedSnapshot(tuple(scope), tuple(freeze(dict(h)) for h in headers), freeze(dict(task)),
                tuple(freeze(dict(o)) for o in operations), tuple(provenance),
                freeze(dict(question)) if eligible_question else None, backend, pending, revision)

    def accept(self, task_id: str, scope_id: str, utterance_id: str, text: str, *, kind="continue_task", voice_context=None, preconditions=None, authority=None) -> dict:
        bounded_identifier(utterance_id)
        if kind not in _BUSINESS_KINDS or not isinstance(text, str) or not text or len(text) > 4000:
            raise StoreInvalid("invalid utterance")
        context = {} if voice_context is None else voice_context
        if not isinstance(context, dict) or set(context) - _VOICE_KEYS:
            raise StoreInvalid("invalid voice context")
        if any(not isinstance(value, str) or not value or len(value) > 128 for value in context.values()):
            raise StoreInvalid("invalid voice context")
        encoded_context = _validate_json(context, limit=512)
        with self._transaction():
            task = self._task_row(task_id, scope_id)
            if self._db.execute('SELECT 1 FROM commands WHERE command_id=?', (utterance_id,)).fetchone():
                raise StoreConflict('utterance identity conflict')
            if "assistant_id" in context:
                bound_assistant = self._db.execute("SELECT assistant_id FROM scopes WHERE scope_id=?", (scope_id,)).fetchone()[0]
                if context["assistant_id"] != bound_assistant:
                    raise StoreInvalid("invalid voice context")
            existing = self._db.execute("SELECT * FROM operations WHERE utterance_id=?", (utterance_id,)).fetchone()
            if existing:
                if existing["task_id"] == task_id and existing["kind"] == kind and existing["text"] == text and existing["voice_context"] == encoded_context:
                    return self._operation_snapshot(existing)
                raise StoreConflict("utterance identity conflict")
            self._check_preconditions(scope_id, preconditions, authority)
            if not _decode(task["capabilities"]).get(kind, False):
                raise StoreDenied("agent capability unavailable")
            attached = self._db.execute("SELECT attached FROM scopes WHERE scope_id=?", (scope_id,)).fetchone()[0]
            if not attached:
                raise StoreDenied("scope detached")
            if task["state"] in ("succeeded", "failed", "cancelled", "cancel_requested", "outcome_unknown"):
                raise StoreConflict("task is terminal")
            if self._db.execute("SELECT COUNT(*) FROM operations o JOIN tasks t ON t.task_id=o.task_id WHERE t.scope_id=? AND o.dispatch_state IN ('unsubmitted','submitted','suspended','unknown')", (scope_id,)).fetchone()[0] >= 32:
                raise StoreCapacity("pending capacity reached")
            version = task["context_version"] + 1
            operation_id = _new_id()
            payload = _validate_json({"kind": kind, "text": text, "voice_context": context, "context_version": version})
            now = _now()
            self._db.execute("UPDATE tasks SET context_version=?,updated_at=? WHERE task_id=?", (version, now, task_id))
            self._db.execute(
                "INSERT INTO operations(operation_id,task_id,utterance_id,context_version,kind,text,voice_context,immutable_payload,dispatch_state,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (operation_id, task_id, utterance_id, version, kind, text, encoded_context, payload, "unsubmitted", now),
            )
            answered = self.question(scope_id)
            if answered and (answered['task_id'] != task_id or answered['context_version'] != version - 1):
                answered = None
            self._event(task_id, operation_id, "utterance_accepted", version,
                        {"kind": kind, "text": text, "answered_question": answered})
            self._db.execute('DELETE FROM scope_questions WHERE scope_id=? AND task_id=?', (scope_id, task_id))
            self._db.execute('UPDATE tasks SET open_question=NULL WHERE task_id=?', (task_id,))
            return self._operation_snapshot(self._db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone())

    def accept_new_task(self, scope, agent, utterance_id, text, *, voice_context=None, preconditions=None, authority=None):
        """Create workflow and its first durable utterance in one transaction."""
        with self._transaction():
            prior = self._db.execute('SELECT * FROM operations WHERE utterance_id=?', (utterance_id,)).fetchone()
            if prior:
                task = self._task_row(prior['task_id'], scope.scope_id)
                if (task['agent_alias'], task['agent_id'], task['registry_revision']) != (agent.alias, agent.agent_id, agent.revision):
                    raise StoreConflict('agent binding conflict')
            else:
                self._check_preconditions(scope.scope_id, preconditions, authority)
                task = self.create_task(scope, agent, text)
            return self.accept(task['task_id'], scope.scope_id, utterance_id, text, kind='new_task', voice_context=voice_context)

    def note_question(self, task_id, scope_id, text, *, source, context_version=None):
        if not isinstance(text, str) or not text or len(text) > 4000 or source not in ('backend', 'greeting'):
            raise StoreInvalid('invalid question')
        with self._transaction():
            task = self._task_row(task_id, scope_id)
            if not self._task_snapshot(task)['attached']:
                raise StoreDenied('scope detached')
            if task['state'] in ('cancel_requested', 'cancelled', 'succeeded', 'failed', 'outcome_unknown'):
                raise StoreConflict('task cannot accept a question')
            if context_version is not None and task['context_version'] != context_version:
                return False
            question_id = _new_id()
            self._db.execute('INSERT OR REPLACE INTO scope_questions VALUES(?,?,?,?,?,?)',
                             (scope_id, task_id, text, source, task['context_version'], question_id))
            self._db.execute('UPDATE tasks SET open_question=? WHERE task_id=?', (text, task_id))
            self._event(task_id, None, 'question_noted', task['context_version'], {'text': text, 'source': source}, event_id=question_id)
            return True

    def question(self, scope_id):
        bounded_identifier(scope_id)
        with self._lock:
            row = self._db.execute('SELECT q.* FROM scope_questions q JOIN scopes s ON s.scope_id=q.scope_id WHERE q.scope_id=? AND s.attached=1', (scope_id,)).fetchone()
            return dict(row) if row else None

    def operations(self, scope_id: str) -> list[dict]:
        """Operator/coordinator-private scope-filtered history, including suspended work."""
        bounded_identifier(scope_id)
        with self._lock:
            rows = self._db.execute("SELECT o.* FROM operations o JOIN tasks t ON t.task_id=o.task_id WHERE t.scope_id=? ORDER BY o.rowid", (scope_id,)).fetchall()
            return [self._operation_snapshot(row) for row in rows]

    def cancel_pending(self, task_id, scope_id, command_id, *, text, preconditions=None, authority=None):
        bounded_identifier(command_id)
        if not isinstance(text, str) or not text or len(text) > 4000:
            raise StoreInvalid("invalid command")
        with self._transaction():
            task = self._task_row(task_id, scope_id)
            prior = self._db.execute("SELECT * FROM commands WHERE command_id=?", (command_id,)).fetchone()
            if prior:
                if (prior['task_id'], prior['scope_id'], prior['text']) != (task_id, scope_id, text):
                    raise StoreConflict("command identity conflict")
                return self._task_snapshot(task)
            self._check_preconditions(scope_id, preconditions, authority)
            if self._db.execute("SELECT 1 FROM operations WHERE utterance_id=?", (command_id,)).fetchone():
                raise StoreConflict("command identity conflict")
            if not self._db.execute("SELECT attached FROM scopes WHERE scope_id=?", (scope_id,)).fetchone()[0]:
                raise StoreDenied("scope detached")
            if task['state'] in ('succeeded', 'failed', 'cancelled', 'outcome_unknown'):
                raise StoreConflict("task is terminal")
            dispatched = self._db.execute("SELECT 1 FROM operations WHERE task_id=? AND submitted_at IS NOT NULL", (task_id,)).fetchone()
            state = 'cancel_requested' if dispatched else 'cancelled'
            operation_state = 'suspended' if dispatched else 'cancelled'
            version = task['context_version'] + 1
            self._db.execute("INSERT INTO commands VALUES(?,?,?,?)", (command_id, task_id, scope_id, text))
            self._db.execute("UPDATE operations SET dispatch_state=? WHERE task_id=? AND dispatch_state='unsubmitted'", (operation_state, task_id))
            self._db.execute("UPDATE tasks SET state=?,context_version=?,open_question=NULL,updated_at=? WHERE task_id=?", (state, version, _now(), task_id))
            self._db.execute('DELETE FROM scope_questions WHERE scope_id=? AND task_id=?', (scope_id, task_id))
            self._event(task_id, None, 'cancel_pending', version, {'command_id': command_id, 'text': text, 'state': state})
            return self._task_snapshot(self._task_row(task_id, scope_id))

    def pending(self, scope_id: str) -> list[dict]:
        bounded_identifier(scope_id)
        with self._lock:
            rows = self._db.execute("""SELECT o.* FROM operations o JOIN tasks t ON t.task_id=o.task_id
                JOIN scopes s ON s.scope_id=t.scope_id WHERE t.scope_id=? AND s.attached=1 AND o.dispatch_state='unsubmitted'
                ORDER BY o.rowid""", (scope_id,)).fetchall()
            return [self._operation_snapshot(row) for row in rows]

    def dispatch(self, operation_id: str) -> dict:
        bounded_identifier(operation_id)
        with self._transaction():
            row = self._db.execute("SELECT o.*,t.scope_id,t.state FROM operations o JOIN tasks t ON t.task_id=o.task_id WHERE o.operation_id=?", (operation_id,)).fetchone()
            if row is None:
                raise StoreDenied("operation unavailable")
            if not self._db.execute("SELECT attached FROM scopes WHERE scope_id=?", (row["scope_id"],)).fetchone()[0]:
                raise StoreDenied("scope detached")
            if row["dispatch_state"] != "unsubmitted":
                raise StoreConflict("operation already claimed")
            if row["state"] in ("succeeded", "failed", "cancelled", "cancel_requested", "outcome_unknown"):
                raise StoreConflict("task is terminal")
            if self._db.execute("SELECT 1 FROM operations WHERE dispatch_state IN ('submitted','unknown') LIMIT 1").fetchone():
                raise StoreConflict("execution unresolved")
            now = _now()
            self._db.execute("UPDATE operations SET dispatch_state='submitted',submitted_at=? WHERE operation_id=?", (now, operation_id))
            self._db.execute("UPDATE tasks SET state='running',updated_at=? WHERE task_id=?", (now, row["task_id"]))
            self._event(row["task_id"], operation_id, "operation_submitted", row["context_version"], {"dispatch_state": "submitted"})
            return self._operation_snapshot(self._db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone())

    def observe(self, operation_id: str, event_id: str, event_type: str, payload) -> bool:
        bounded_identifier(operation_id)
        bounded_identifier(event_id)
        bounded_identifier(event_type)
        if event_type in ("task_created", "utterance_accepted", "operation_submitted", "operation_settled", "outcome_unknown", "receipt_recorded", "operation_reconciled"):
            raise StoreInvalid("reserved event type")
        encoded = _validate_json(payload)
        with self._transaction():
            operation = self._db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
            if operation is None:
                raise StoreDenied("operation unavailable")
            prior = self._db.execute("SELECT * FROM inbox WHERE event_id=?", (event_id,)).fetchone()
            if prior:
                if (prior["operation_id"], prior["event_type"], prior["payload"]) == (operation_id, event_type, encoded):
                    return False
                raise StoreConflict("callback identity conflict")
            self._db.execute("INSERT INTO inbox(event_id,operation_id,event_type,payload) VALUES(?,?,?,?)", (event_id, operation_id, event_type, encoded))
            self._event(operation["task_id"], operation_id, event_type, operation["context_version"], payload, source="executor", event_id=event_id)
            return True

    def settle(self, operation_id: str, *, replies: list[str], outcome="awaiting_input", evidence=None) -> dict:
        bounded_identifier(operation_id)
        if outcome not in _TERMINAL_STATES or outcome == "outcome_unknown":
            raise StoreInvalid("invalid outcome")
        if outcome == 'cancelled':
            # No owned authoritative cancellation adapter exists in legacy mode.
            # A payload Boolean must not manufacture that authority.
            raise StoreDenied('authoritative cancellation unavailable')
        if not isinstance(replies, list) or len(replies) > 32 or any(not isinstance(reply, str) or len(reply) > 4000 for reply in replies):
            raise StoreInvalid("invalid replies")
        encoded_replies = _validate_json(replies)
        encoded_evidence = _validate_json({} if evidence is None else evidence)
        with self._transaction():
            row = self._db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
            if row is None:
                raise StoreDenied("operation unavailable")
            if row["dispatch_state"] == "settled":
                if (row["replies"], row["evidence"], row["outcome"]) == (encoded_replies, encoded_evidence, outcome):
                    return self._task_snapshot(self._db.execute("SELECT * FROM tasks WHERE task_id=?", (row["task_id"],)).fetchone())
                raise StoreConflict("settlement conflict")
            if row["dispatch_state"] != "submitted":
                raise StoreConflict("operation not submitted")
            task = self._db.execute("SELECT * FROM tasks WHERE task_id=?", (row["task_id"],)).fetchone()
            if task["state"] in ("succeeded", "failed", "cancelled", "outcome_unknown"):
                raise StoreConflict("task is terminal")
            now = _now()
            self._db.execute("UPDATE operations SET dispatch_state='settled',replies=?,evidence=?,outcome=?,settled_at=? WHERE operation_id=?", (encoded_replies, encoded_evidence, outcome, now, operation_id))
            state = 'cancel_requested' if task['state'] == 'cancel_requested' and outcome == 'awaiting_input' else outcome
            question = replies[-1] if outcome == 'awaiting_input' and replies else None
            settlement_id = _new_id()
            binding = self._db.execute('SELECT * FROM scope_questions WHERE scope_id=?', (task['scope_id'],)).fetchone()
            if (outcome == 'awaiting_input' and binding is not None
                    and binding['task_id'] == row['task_id']
                    and (binding['context_version'] > row['context_version']
                         or (not replies and binding['context_version'] == row['context_version']
                             and row['context_version'] == task['context_version']))):
                # Empty return lists do not retract a current callback-only question.
                # A newer explicit question also remains consistent in both views.
                question = binding['text']
            self._db.execute("UPDATE tasks SET state=?,open_question=?,result_version=result_version+1,updated_at=? WHERE task_id=?", (state, question, now, row["task_id"]))
            if outcome != 'awaiting_input':
                self._db.execute('DELETE FROM scope_questions WHERE task_id=?', (row['task_id'],))
            elif (state == 'awaiting_input' and row['context_version'] == task['context_version']
                    and self._task_snapshot(task)['attached']
                    and (binding is None or binding['task_id'] == row['task_id'])):
                if question:
                    question_id = binding['question_id'] if binding and question == binding['text'] else settlement_id
                    self._db.execute('INSERT OR REPLACE INTO scope_questions VALUES(?,?,?,?,?,?)',
                        (task['scope_id'], row['task_id'], question, 'backend', row['context_version'], question_id))
                else:
                    self._db.execute('DELETE FROM scope_questions WHERE task_id=?', (row['task_id'],))
            self._event(row["task_id"], operation_id, "operation_settled", row["context_version"], {"outcome": outcome, "replies": replies, "evidence": _decode(encoded_evidence)}, event_id=settlement_id)
            return self._task_snapshot(self._db.execute("SELECT * FROM tasks WHERE task_id=?", (row["task_id"],)).fetchone())

    def record_receipt(self, operation_id, *, request_ref='', execution_ref='', receipt=None):
        """Private executor/operator seam. An ACK/reference never settles a write.

        Bind once; only missing references/receipt fields may be added. No model
        or public route may call this method. Credentials and free text are absent
        from the receipt schema; retain source documents outside this journal.
        """
        bounded_identifier(operation_id)
        _receipt_ref(request_ref, optional=True)
        _receipt_ref(execution_ref, optional=True)
        receipt = {} if receipt is None else receipt
        allowed = {'status', 'task_ref', 'operation_ref', 'request_ref', 'execution_ref'}
        if type(receipt) is not dict or set(receipt) - allowed:
            raise StoreInvalid('invalid receipt')
        for key, value in receipt.items():
            if key == 'status':
                if value not in ('accepted', 'queued', 'submitted', 'succeeded', 'failed', 'cancelled', 'outcome_unknown'):
                    raise StoreInvalid('invalid receipt status')
            else:
                _receipt_ref(value)
        request_ref = request_ref or receipt.get('request_ref', '')
        execution_ref = execution_ref or receipt.get('execution_ref', '')
        for key, value in (('request_ref', request_ref), ('execution_ref', execution_ref)):
            if key in receipt and receipt[key] != value:
                raise StoreConflict('receipt reference conflict')
        with self._transaction():
            row = self._db.execute('SELECT * FROM operations WHERE operation_id=?', (operation_id,)).fetchone()
            if row is None:
                raise StoreDenied('operation unavailable')
            if row['dispatch_state'] not in ('submitted', 'unknown', 'settled'):
                raise StoreConflict('operation not submitted')
            for key, value in (('request_ref', request_ref), ('execution_ref', execution_ref)):
                if row[key] and value and row[key] != value:
                    raise StoreConflict('receipt reference conflict')
            previous = _decode(row['receipt']) or {}
            if any(key in previous and previous[key] != value for key, value in receipt.items()):
                raise StoreConflict('receipt binding conflict')
            merged = {**previous, **receipt}
            request_ref = row['request_ref'] or request_ref
            execution_ref = row['execution_ref'] or execution_ref
            encoded = _validate_json(merged, limit=2048)
            if (row['request_ref'] or '', row['execution_ref'] or '', previous) == (request_ref, execution_ref, merged):
                return self._operation_snapshot(row)
            self._db.execute('UPDATE operations SET request_ref=?,execution_ref=?,receipt=? WHERE operation_id=?',
                             (request_ref, execution_ref, encoded, operation_id))
            self._event(row['task_id'], operation_id, 'receipt_recorded', row['context_version'],
                        {'request_ref': request_ref, 'execution_ref': execution_ref, 'receipt': merged})
            return self._operation_snapshot(self._db.execute('SELECT * FROM operations WHERE operation_id=?', (operation_id,)).fetchone())

    def executor_binding(self, operation_id):
        """Private executor lookup; never a public task discovery interface."""
        bounded_identifier(operation_id)
        with self._lock:
            row = self._db.execute('SELECT * FROM operations WHERE operation_id=?', (operation_id,)).fetchone()
            if row is None:
                raise StoreDenied('operation unavailable')
            task = self._db.execute('SELECT * FROM tasks WHERE task_id=?', (row['task_id'],)).fetchone()
            binding = self._db.execute('SELECT * FROM owned_dispatches WHERE operation_id=?', (operation_id,)).fetchone()
            return {'operation': self._operation_snapshot(row), 'task': self._task_snapshot(task),
                    'task_ref': binding['task_ref'] if binding else None,
                    'command': _decode(binding['command']) if binding else None}

    def record_owned_dispatch(self, operation_id, task_ref, command):
        """Persist exact owned command before transport; it cannot be rebound."""
        _receipt_ref(task_ref)
        encoded = _validate_json(command, limit=8192)
        with self._transaction():
            row = self.executor_binding(operation_id)
            prior = self._db.execute('SELECT * FROM owned_dispatches WHERE operation_id=?', (operation_id,)).fetchone()
            if prior:
                if (prior['task_ref'], prior['command']) != (task_ref, encoded):
                    raise StoreConflict('owned dispatch binding conflict')
                return row
            if row['operation']['dispatch_state'] != 'unsubmitted':
                raise StoreConflict('operation already claimed')
            self._db.execute('INSERT INTO owned_dispatches(operation_id,task_ref,command) VALUES(?,?,?)', (operation_id, task_ref, encoded))
            return self.executor_binding(operation_id)

    def observe_owned(self, operation_id, event):
        """Trusted adapter only: persist original correlation and monotone cursor."""
        allowed = {'event_id', 'sequence', 'task_id', 'operation_id', 'context_version', 'status', 'text'}
        if (type(event) is not dict or set(event) != allowed or type(event['sequence']) is not int
                or event['sequence'] < 1 or type(event['context_version']) is not int
                or event['status'] not in ('queued', 'submitted', 'awaiting_input', 'succeeded', 'failed', 'cancelled', 'outcome_unknown')
                or type(event['text']) is not str or len(event['text']) > 4000):
            raise StoreInvalid('invalid owned event')
        for key in ('event_id', 'task_id', 'operation_id'):
            _receipt_ref(event[key])
        with self._transaction():
            binding = self.executor_binding(operation_id)
            op, task = binding['operation'], binding['task']
            if (event['task_id'], event['operation_id'], event['context_version']) != (binding['task_ref'], operation_id, op['context_version']):
                raise StoreConflict('owned event correlation mismatch')
            prior = self._db.execute('SELECT * FROM owned_dispatches WHERE operation_id=?', (operation_id,)).fetchone()
            same_sequence = self._db.execute('SELECT event_id FROM owned_events WHERE operation_id=? AND sequence=?',
                                             (operation_id, event['sequence'])).fetchone()
            if same_sequence and same_sequence['event_id'] != event['event_id']:
                raise StoreConflict('owned event sequence conflict')
            if not self.observe(operation_id, event['event_id'], 'owned_observation', event):
                return False
            self._db.execute('INSERT INTO owned_events VALUES(?,?,?)', (operation_id, event['sequence'], event['event_id']))
            if event['sequence'] <= prior['event_sequence']:
                return False  # retain late historical observation without moving the cursor
            self._db.execute('UPDATE owned_dispatches SET event_sequence=? WHERE operation_id=?', (event['sequence'], operation_id))
            # Gaps do not imply complete delivery. Historical text never binds a question.
            return task['attached'] and task['context_version'] == op['context_version']

    def reconcile_unknown(self, operation_id, *, outcome, evidence, replies=None):
        """Private evidence workflow, never timeout-based retry or model output.

        Trusted caller must verify the actual authoritative record or explicit
        operator observation, bind its reference via record_receipt, and retain
        the observation source externally. Correlation/schema checks here cannot
        authenticate the human or platform on their own.
        """
        bounded_identifier(operation_id)
        required = {'source', 'observer_ref', 'observation_ref', 'task_id', 'operation_id', 'context_version', 'outcome'}
        if (outcome not in ('succeeded', 'failed', 'cancelled') or type(evidence) is not dict
                or not required <= set(evidence) or set(evidence) - required - {'request_ref', 'execution_ref'}
                or evidence['source'] not in ('operator', 'authority') or evidence['outcome'] != outcome
                or type(evidence['context_version']) is not int):
            raise StoreInvalid('invalid reconciliation evidence')
        for key in ('observer_ref', 'observation_ref', 'task_id', 'operation_id'):
            _receipt_ref(evidence[key])
        for key in ('request_ref', 'execution_ref'):
            if key in evidence:
                _receipt_ref(evidence[key])
        replies = [] if replies is None else replies
        if type(replies) is not list or len(replies) > 32 or any(type(v) is not str or len(v) > 4000 for v in replies):
            raise StoreInvalid('invalid replies')
        encoded_replies, encoded_evidence = _validate_json(replies), _validate_json(evidence, limit=4096)
        with self._transaction():
            row = self._db.execute('SELECT * FROM operations WHERE operation_id=?', (operation_id,)).fetchone()
            if row is None:
                raise StoreDenied('operation unavailable')
            if (evidence['operation_id'], evidence['task_id'], evidence['context_version']) != (operation_id, row['task_id'], row['context_version']):
                raise StoreConflict('reconciliation correlation mismatch')
            refs = [key for key in ('request_ref', 'execution_ref') if key in evidence]
            if not refs or any(not row[key] or row[key] != evidence[key] for key in refs):
                raise StoreConflict('reconciliation reference mismatch')
            if row['dispatch_state'] == 'settled':
                if (row['outcome'], row['evidence'], row['replies']) != (outcome, encoded_evidence, encoded_replies):
                    raise StoreConflict('reconciliation conflict')
                return self._operation_snapshot(row)
            if row['dispatch_state'] != 'unknown':
                raise StoreConflict('operation is not unknown')
            now = _now()
            self._db.execute("UPDATE operations SET dispatch_state='settled',outcome=?,evidence=?,replies=?,settled_at=? WHERE operation_id=?",
                             (outcome, encoded_evidence, encoded_replies, now, operation_id))
            self._db.execute('UPDATE tasks SET state=?,open_question=NULL,result_version=result_version+1,updated_at=? WHERE task_id=?',
                             (outcome, now, row['task_id']))
            self._db.execute('DELETE FROM scope_questions WHERE task_id=?', (row['task_id'],))
            # Pending follow-ups are not consent to resubmit a resolved business write.
            self._db.execute("UPDATE operations SET dispatch_state='suspended' WHERE task_id=? AND dispatch_state='unsubmitted'", (row['task_id'],))
            self._event(row['task_id'], operation_id, 'operation_reconciled', row['context_version'],
                        {'outcome': outcome, 'evidence': evidence, 'replies': replies}, source='reconciliation')
            return self._operation_snapshot(self._db.execute('SELECT * FROM operations WHERE operation_id=?', (operation_id,)).fetchone())

    def mark_unknown(self, operation_id: str, reason_code: str) -> None:
        bounded_identifier(operation_id)
        bounded_identifier(reason_code)
        with self._transaction():
            row = self._db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
            if row is None:
                raise StoreDenied("operation unavailable")
            if row["dispatch_state"] == "unknown" and row["reason_code"] == reason_code:
                return
            if row["dispatch_state"] != "submitted":
                raise StoreConflict("operation not submitted")
            now = _now()
            self._db.execute("UPDATE operations SET dispatch_state='unknown',reason_code=? WHERE operation_id=?", (reason_code, operation_id))
            self._db.execute("UPDATE tasks SET state='outcome_unknown',open_question=NULL,updated_at=? WHERE task_id=?", (now, row["task_id"]))
            self._db.execute('DELETE FROM scope_questions WHERE task_id=?', (row['task_id'],))
            self._event(row["task_id"], operation_id, "outcome_unknown", row["context_version"], {"reason_code": reason_code})

    def detach_scope(self, scope_id: str) -> None:
        bounded_identifier(scope_id)
        with self._transaction():
            self._db.execute("UPDATE scopes SET attached=0 WHERE scope_id=?", (scope_id,))
            self._db.execute('DELETE FROM scope_questions WHERE scope_id=?', (scope_id,))
            self._db.execute("UPDATE operations SET dispatch_state='suspended' WHERE dispatch_state='unsubmitted' AND task_id IN (SELECT task_id FROM tasks WHERE scope_id=?)", (scope_id,))

    def recover(self) -> dict:
        with self._transaction():
            rows = self._db.execute("SELECT * FROM operations WHERE dispatch_state='submitted' ORDER BY rowid").fetchall()
            for row in rows:
                now = _now()
                self._db.execute("UPDATE operations SET dispatch_state='unknown',reason_code='process_restart' WHERE operation_id=?", (row["operation_id"],))
                self._db.execute("UPDATE tasks SET state='outcome_unknown',open_question=NULL,updated_at=? WHERE task_id=?", (now, row["task_id"]))
                self._db.execute('DELETE FROM scope_questions WHERE task_id=?', (row['task_id'],))
                self._event(row["task_id"], row["operation_id"], "outcome_unknown", row["context_version"], {"reason_code": "process_restart"})
            return {"unknown": len(rows)}

    def has_unresolved(self) -> bool:
        with self._lock:
            return self._db.execute("SELECT 1 FROM operations WHERE dispatch_state IN ('submitted','unknown') LIMIT 1").fetchone() is not None

    def events(self, task_id: str, scope_id: str, after: int = 0) -> list[dict]:
        if isinstance(after, bool) or not isinstance(after, int) or after < 0:
            raise StoreInvalid("invalid event cursor")
        with self._lock:
            self._task_row(task_id, scope_id)
            rows = self._db.execute("SELECT * FROM events WHERE task_id=? AND sequence>? ORDER BY sequence", (task_id, after)).fetchall()
            return [{"event_id": row["event_id"], "sequence": row["sequence"], "task_id": row["task_id"],
                     "operation_id": row["operation_id"], "type": row["type"], "context_version": row["context_version"],
                     "payload": _decode(row["payload"]), "source": row["source"], "fingerprint": row["fingerprint"]} for row in rows]
