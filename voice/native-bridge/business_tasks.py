"""Validated identities for call-scoped responsive business tasks."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


class StoreConflict(Exception):
    """An identity or state already has a different binding."""


class StoreCapacity(Exception):
    """A per-scope capacity limit was reached."""


class StoreDenied(Exception):
    """The caller has no access to this call-scoped task."""


class StoreInvalid(Exception):
    """An input does not satisfy the store contract."""


def bounded_identifier(value: str, *, optional: bool = False) -> str:
    if not isinstance(value, str) or len(value) > 128 or (not optional and not value):
        raise StoreInvalid("invalid identifier")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise StoreInvalid("invalid identifier")
    return value


@dataclass(frozen=True)
class Scope:
    scope_id: str
    call_id: str
    call_generation: int
    instance_id: str
    assistant_id: str
    principal_id: str = ""

    def __post_init__(self):
        for name in ("scope_id", "call_id", "instance_id", "assistant_id"):
            bounded_identifier(getattr(self, name))
        bounded_identifier(self.principal_id, optional=True)
        if isinstance(self.call_generation, bool) or not isinstance(self.call_generation, int) or self.call_generation < 0:
            raise StoreInvalid("invalid call generation")


@dataclass(frozen=True)
class Agent:
    alias: str
    agent_id: str
    revision: str
    capabilities: Mapping[str, bool]
    name: str = ""
    description: str = ""
    supported_intents: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ("alias", "agent_id", "revision"):
            bounded_identifier(getattr(self, name))
        if not isinstance(self.capabilities, Mapping) or not self.capabilities:
            raise StoreInvalid("invalid capabilities")
        capabilities = {}
        for key, enabled in self.capabilities.items():
            bounded_identifier(key)
            if type(enabled) is not bool:
                raise StoreInvalid("invalid capabilities")
            capabilities[key] = enabled
        for value, limit in ((self.name, 80), (self.description, 400)):
            if not isinstance(value, str) or len(value) > limit or any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise StoreInvalid("invalid agent description")
        if not isinstance(self.supported_intents, tuple) or len(self.supported_intents) > 16:
            raise StoreInvalid("invalid agent intents")
        if any(not isinstance(value, str) or not value or len(value) > 64 or
               any(ord(char) < 32 or ord(char) == 127 for char in value)
               for value in self.supported_intents):
            raise StoreInvalid("invalid agent intents")
        object.__setattr__(self, "capabilities", MappingProxyType(capabilities))
