"""Private SQLite journal for call-scoped tasks and durable operation claims."""

import hashlib
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from business_tasks import Agent, Scope, StoreCapacity, StoreConflict, StoreDenied, StoreInvalid, bounded_identifier


_BUSINESS_KINDS = frozenset({"continue_task", "amend_task", "new_task", "cancel_task"})
_VOICE_KEYS = frozenset({"language", "assistant_id", "profile"})
_FORBIDDEN_KEYS = frozenset({"bearer", "cookie", "cookies", "api_key", "apikey", "secret", "token", "authorization", "csrf", "password"})
_TERMINAL_STATES = frozenset({"awaiting_input", "succeeded", "failed", "cancelled", "outcome_unknown"})


def _now():
    return datetime.now(timezone.utc).isoformat()


def _new_id():
    return str(uuid.uuid4())


def _validate_json(value, *, limit=16384):
    def scan(item):
        if isinstance(item, dict):
            for key, nested in item.items():
                if not isinstance(key, str) or key.lower() in _FORBIDDEN_KEYS:
                    raise StoreInvalid("invalid payload")
                scan(nested)
        elif isinstance(item, list):
            for nested in item:
                scan(nested)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise StoreInvalid("invalid payload")

    scan(value)
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise StoreInvalid("invalid payload") from None
    if len(encoded) > limit:
        raise StoreInvalid("payload too large")
    return encoded


def _decode(value):
    return json.loads(value) if value is not None else None


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
        """)

    def close(self):
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None

    @contextmanager
    def _transaction(self):
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            else:
                self._db.execute("COMMIT")

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

    def accept(self, task_id: str, scope_id: str, utterance_id: str, text: str, *, kind="continue_task", voice_context=None) -> dict:
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
            if "assistant_id" in context:
                bound_assistant = self._db.execute("SELECT assistant_id FROM scopes WHERE scope_id=?", (scope_id,)).fetchone()[0]
                if context["assistant_id"] != bound_assistant:
                    raise StoreInvalid("invalid voice context")
            if not _decode(task["capabilities"]).get(kind, False):
                raise StoreDenied("agent capability unavailable")
            existing = self._db.execute("SELECT * FROM operations WHERE utterance_id=?", (utterance_id,)).fetchone()
            if existing:
                if existing["task_id"] == task_id and existing["kind"] == kind and existing["text"] == text and existing["voice_context"] == encoded_context:
                    return self._operation_snapshot(existing)
                raise StoreConflict("utterance identity conflict")
            attached = self._db.execute("SELECT attached FROM scopes WHERE scope_id=?", (scope_id,)).fetchone()[0]
            if not attached:
                raise StoreDenied("scope detached")
            if task["state"] in ("succeeded", "failed", "cancelled", "outcome_unknown"):
                raise StoreConflict("task is terminal")
            if self._db.execute("SELECT COUNT(*) FROM operations o JOIN tasks t ON t.task_id=o.task_id WHERE t.scope_id=? AND o.dispatch_state IN ('unsubmitted','submitted','unknown')", (scope_id,)).fetchone()[0] >= 32:
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
            self._event(task_id, operation_id, "utterance_accepted", version, {"kind": kind, "text": text})
            return self._operation_snapshot(self._db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone())

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
            if row["dispatch_state"] != "unsubmitted":
                raise StoreConflict("operation already claimed")
            if not self._db.execute("SELECT attached FROM scopes WHERE scope_id=?", (row["scope_id"],)).fetchone()[0]:
                raise StoreDenied("scope detached")
            if row["state"] in ("succeeded", "failed", "cancelled", "outcome_unknown"):
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
        if event_type in ("task_created", "utterance_accepted", "operation_submitted", "operation_settled", "outcome_unknown"):
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
            self._db.execute("UPDATE tasks SET state=?,result_version=result_version+1,updated_at=? WHERE task_id=?", (outcome, now, row["task_id"]))
            self._event(row["task_id"], operation_id, "operation_settled", row["context_version"], {"outcome": outcome, "replies": replies, "evidence": _decode(encoded_evidence)})
            return self._task_snapshot(self._db.execute("SELECT * FROM tasks WHERE task_id=?", (row["task_id"],)).fetchone())

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
            self._db.execute("UPDATE tasks SET state='outcome_unknown',updated_at=? WHERE task_id=?", (now, row["task_id"]))
            self._event(row["task_id"], operation_id, "outcome_unknown", row["context_version"], {"reason_code": reason_code})

    def detach_scope(self, scope_id: str) -> None:
        bounded_identifier(scope_id)
        with self._transaction():
            self._db.execute("UPDATE scopes SET attached=0 WHERE scope_id=?", (scope_id,))

    def recover(self) -> dict:
        with self._transaction():
            rows = self._db.execute("SELECT * FROM operations WHERE dispatch_state='submitted' ORDER BY rowid").fetchall()
            for row in rows:
                now = _now()
                self._db.execute("UPDATE operations SET dispatch_state='unknown',reason_code='process_restart' WHERE operation_id=?", (row["operation_id"],))
                self._db.execute("UPDATE tasks SET state='outcome_unknown',updated_at=? WHERE task_id=?", (now, row["task_id"]))
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
