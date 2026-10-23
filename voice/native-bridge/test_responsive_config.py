"""Responsive profile safety gates."""

import json
import tempfile
import unittest
from pathlib import Path

from business_tasks import Agent, StoreInvalid
from responsive_config import load_responsive_config


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


if __name__ == "__main__":
    unittest.main()
