"""Responsive profile safety gates."""

import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from business_tasks import Agent, StoreInvalid
from responsive_config import ResponsiveConfig, load_responsive_config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.path = self.folder / "profile.json"

    def tearDown(self):
        self.temp.cleanup()

    def save(self, value):
        self.path.write_text(json.dumps(value), encoding="utf-8")
        return load_responsive_config(self.path)

    def test_missing_profile_keeps_legacy(self):
        profile = load_responsive_config(self.path)
        self.assertFalse(profile.enabled)
        self.assertEqual(profile.mode, "legacy")

    def test_inline_secrets_and_unknown_keys_rejected(self):
        for value in ({"model_token": "secret"}, {"model": {"api_key": "secret"}},
                      {"unexpected": True}, {"model_url": "http://example.com"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.save(value)

    def test_full_without_authority_evidence_rejected(self):
        with self.assertRaises(ValueError):
            self.save({"enabled": True, "mode": "full", "store_file": "private/tasks.db"})

    def test_self_declared_hashed_evidence_cannot_enable_full_runtime(self):
        capabilities = {}
        for name in ("verified_principal", "agent_tool_binding", "revision_fence",
                     "durable_operation_claim", "reconciliation"):
            artifact = self.folder / f"{name}.txt"
            artifact.write_text("self declared", encoding="utf-8")
            capabilities[name] = {"artifact": artifact.name,
                                  "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                                  "status": "verified"}
        manifest = self.folder / "authority.json"
        manifest.write_text(json.dumps({"capabilities": capabilities}), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.save({"enabled": True, "mode": "full", "store_file": "private/tasks.db",
                       "capability_evidence": {"authority": manifest.name}})

    def test_full_request_remains_unverified_when_disabled(self):
        profile = self.save({"enabled": False, "mode": "full"})
        self.assertFalse(profile.enabled)
        self.assertFalse(profile.authority_verified)
        self.assertTrue(profile.requires_live_authority)
        with self.assertRaises(ValueError):
            ResponsiveConfig(enabled=True, mode="full")
        with self.assertRaises(TypeError):
            ResponsiveConfig(authority_verified=True)

    def test_unqualified_vision_cannot_be_enabled_by_boolean(self):
        with self.assertRaises(ValueError):
            self.save({"enabled": True, "mode": "assist", "store_file": "private/tasks.db", "vision_enabled": True})

    def test_private_paths_relative_to_profile_and_agent_metadata(self):
        profile = self.save({"enabled": True, "mode": "assist", "store_file": "private/tasks.db",
                             "agents": [{"alias": "helpdesk", "agent_id": "a1", "revision": "r1",
                                         "capabilities": {"continue_task": True}, "name": "Service Desk",
                                         "description": "Service requests", "supported_intents": ["continue_task"]}]})
        self.assertEqual(profile.store_file, str((self.folder / "private/tasks.db").resolve()))
        self.assertEqual(profile.agents[0].name, "Service Desk")

    def test_agent_metadata_bounded(self):
        with self.assertRaises(StoreInvalid):
            Agent("a", "id", "r", {"continue_task": True}, name="n" * 81)

    def test_registered_routing_aliases_are_bounded_and_loaded(self):
        profile = self.save({'agents': [{'alias': 'a', 'agent_id': 'id', 'revision': 'r',
            'capabilities': {'new_task': True}, 'routing_aliases': ['Beschaffung', 'Laptop']} ]})
        self.assertEqual(profile.agents[0].routing_aliases, ('Beschaffung', 'Laptop'))
        for aliases in (('x' * 81,), ('',), ('x', 'X'), ('x\n',), tuple(str(i) for i in range(17)), ['a']):
            with self.subTest(aliases=aliases), self.assertRaises(StoreInvalid):
                Agent('a', 'id', 'r', {'continue_task': True}, routing_aliases=aliases)


if __name__ == "__main__":
    unittest.main()
