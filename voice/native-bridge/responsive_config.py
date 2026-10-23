"""Opt-in responsive voice configuration with explicit evidence gates."""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from business_tasks import Agent
from conversation_router import LoopbackConversationModel


_PROFILE_KEYS = frozenset({"enabled", "mode", "store_file", "model_url", "model_name",
                           "model_token_file", "model_timeout_seconds", "agents",
                           "capability_evidence"})
_AGENT_KEYS = frozenset({"alias", "agent_id", "revision", "capabilities", "name",
                         "description", "supported_intents"})
_AUTHORITY = frozenset({"verified_principal", "agent_tool_binding", "revision_fence",
                        "durable_operation_claim", "reconciliation"})


@dataclass(frozen=True)
class ResponsiveConfig:
    enabled: bool = False
    mode: str = "legacy"
    store_file: str = ""
    model_url: str = ""
    model_name: str = ""
    model_token_file: str = ""
    model_timeout_seconds: float = 2.0
    agents: tuple[Agent, ...] = ()
    capability_evidence: dict = field(default_factory=dict)
    omni_qualified: bool = False
    vision_qualified: bool = False


def _duplicate_pairs(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("duplicate profile key")
        output[key] = value
    return output


def _private_path(profile, value):
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise ValueError("invalid private path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = profile.parent / path
    return str(path.resolve())


def _qualified_manifest(path, required):
    """Require content-addressed evidence files, not feature flags."""
    try:
        raw = Path(path).read_bytes()
        if len(raw) > 16384:
            return False
        manifest = json.loads(raw, object_pairs_hook=_duplicate_pairs)
        proofs = manifest["capabilities"]
        if not isinstance(proofs, dict) or not required.issubset(proofs):
            return False
        for capability in required:
            proof = proofs[capability]
            if not isinstance(proof, dict) or set(proof) != {"artifact", "sha256", "status"}:
                return False
            if proof["status"] != "verified" or not isinstance(proof["sha256"], str) or len(proof["sha256"]) != 64:
                return False
            artifact = Path(_private_path(Path(path), proof["artifact"]))
            if not artifact.is_file() or artifact.stat().st_size > 1024 * 1024:
                return False
            if hashlib.sha256(artifact.read_bytes()).hexdigest() != proof["sha256"]:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        return False


def load_responsive_config(path) -> ResponsiveConfig:
    profile = Path(path).expanduser().resolve()
    if not profile.is_file():
        return ResponsiveConfig()
    raw = profile.read_bytes()
    if len(raw) > 65536:
        raise ValueError("responsive profile too large")
    try:
        data = json.loads(raw, object_pairs_hook=_duplicate_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite profile value")))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid responsive profile") from error
    if not isinstance(data, dict) or set(data) - _PROFILE_KEYS:
        raise ValueError("unknown responsive setting")
    enabled = data.get("enabled", False)
    mode = data.get("mode", "legacy")
    if type(enabled) is not bool or mode not in ("legacy", "assist", "full") or not isinstance(mode, str):
        raise ValueError("invalid responsive mode")
    if enabled and mode == "legacy":
        raise ValueError("enabled legacy profile is ambiguous")
    store_file = _private_path(profile, data["store_file"]) if data.get("store_file") else ""
    if enabled and not store_file:
        raise ValueError("enabled responsive mode requires a private store")
    token_file = _private_path(profile, data["model_token_file"]) if data.get("model_token_file") else ""
    model_url = data.get("model_url", "")
    model_name = data.get("model_name", "")
    model_timeout = data.get("model_timeout_seconds", 2.0)
    if model_url or model_name or token_file:
        if not model_url or not model_name:
            raise ValueError("incomplete conversation model")
        LoopbackConversationModel(None, model_url, model_name, token_file, model_timeout)
    elif type(model_timeout) not in (int, float) or not 0 < model_timeout <= 2:
        raise ValueError("invalid conversation timeout")
    entries = data.get("agents", [])
    if not isinstance(entries, list) or len(entries) > 16:
        raise ValueError("invalid agents")
    agents = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - _AGENT_KEYS:
            raise ValueError("invalid agent settings")
        intents = entry.get("supported_intents", [])
        if not isinstance(intents, list):
            raise ValueError("invalid agent intents")
        agents.append(Agent(entry["alias"], entry["agent_id"], entry["revision"],
                            entry["capabilities"], entry.get("name", ""),
                            entry.get("description", ""), tuple(intents)))
    if len({agent.alias for agent in agents}) != len(agents):
        raise ValueError("duplicate agent alias")
    evidence = data.get("capability_evidence", {})
    if not isinstance(evidence, dict) or set(evidence) - {"authority", "omni", "vision"}:
        raise ValueError("invalid capability evidence")
    evidence = {key: _private_path(profile, value) for key, value in evidence.items()}
    if mode == "full" and ("authority" not in evidence or
                           not _qualified_manifest(evidence["authority"], _AUTHORITY)):
        raise ValueError("full mode lacks verified authority evidence")
    # Omni and vision paths are recorded for later qualification; this profile grants no capability from their presence.
    return ResponsiveConfig(enabled, mode, store_file, model_url, model_name, token_file,
                            float(model_timeout), tuple(agents), MappingProxyType(evidence))
