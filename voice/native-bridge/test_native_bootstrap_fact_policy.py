"""V10 bootstrap policy delivery through real Pipecat/Omni/local wire, fake HTTP.

This reproduces omitted role policy, not model semantics. Caller facts remain
unverified data, and the canned transport response is not a semantic test.
"""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'optional-omni')]

from conversation_repair import NATURAL_CONVERSATION_PROMPT
from local_llm_socket import LocalTextSocket
from native_duplex import NativeDuplex
from omni_conversation import OmniConversation
from pipecat_dialogue import PipecatDialogue
from servicenow_voice_context import build_servicenow_voice_context
from test_local_llm_fixed_routes import HTTP, DIRECT_CHAT, DIRECT_MODELS
from test_native_duplex import FakeCall


V10_RAW = ('Ich brauche ein Laptop für Marcel Käfge. Eintrittsdatum ist der 16. November 2026. '
           'Die Führungskraft ist Softwaremanager. Benutzername Sam. Lieferung nach Hamburg.')


class BootstrapFactPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def wire(self, phase, raw=V10_RAW):
        call = FakeCall()
        configured = 'Greifen Sie zusammen genannte Angaben auf. Antworten Sie natürlich.'
        call.call_settings = SimpleNamespace(language='de', session_parameters=lambda:
            dict(prompt=dict(systemMessage=configured)))
        lane = NativeDuplex(call)
        lane._bootstrap_state = 'pending' if phase == 'bootstrap' else 'ready'
        lane._backend_unavailable = phase == 'unavailable'
        call.dialog.conversation_ended = phase == 'closed'
        if phase in ('bootstrap', 'processing'):
            lane._backend = asyncio.get_running_loop().create_future()
        turn = (0, raw, 2, 'b' * 32, 0)
        lane._observe_raw(raw)
        if phase == 'bootstrap':
            lane._pending.append(turn)
        key, snapshot, _ = lane._dialogue_snapshot(turn, lane.epoch)
        http = HTTP(DIRECT_CHAT, DIRECT_MODELS)
        socket = LocalTextSocket(DIRECT_CHAT, 'C:/synthetic-unused-token', http=http)
        dialogue = PipecatDialogue(OmniConversation(lambda: socket))
        with patch('local_llm_socket._token', return_value='synthetic-only-token'), \
                patch('aiohttp.ClientSession', side_effect=AssertionError('Real HTTP forbidden')):
            try:
                async with asyncio.timeout(3):
                    await dialogue.start(call.call_id, lane.epoch, NATURAL_CONVERSATION_PROMPT + '\n' +
                        build_servicenow_voice_context(call.call_settings).system_prompt_fragment)
                    result = await dialogue.respond(raw, snapshot, key)
                self.assertIsNone(result.failure)
                self.assertEqual(call.dialog.calls, [])
                self.assertEqual(http.requests, [('GET', DIRECT_MODELS), ('POST', DIRECT_CHAT)])
                messages = http.bodies[0]['messages']
                self.assertEqual([m['role'] for m in messages], ['system', 'system', 'user', 'user'])
                self.assertIn(configured, messages[0]['content'])
                self.assertEqual(messages[-1]['content'], raw)
                data = json.loads(messages[2]['content'])
                self.assertEqual(data['raw_inputs'], [raw])
                self.assertEqual(data['public_findings'], [])
                self.assertNotIn(raw, messages[0]['content'] + messages[1]['content'])
                return messages[1]['content']
            finally:
                await dialogue.close()
                call.closed = True
                await lane.close()

    async def test_bootstrap_cannot_omit_caller_identifier_and_requirement_policy(self):
        policy = await self.wire('bootstrap')
        self.assertIn('Identifikatoren', policy)
        self.assertIn('Stelle keine zusätzliche Pflichtangabe auf.', policy)
        self.assertIn('noch nicht bereit', policy)
        self.assertIn('Noch keine fachliche Eingabe wurde übermittelt', policy)

    async def test_policy_survives_every_lifecycle_phase_without_granting_fact_authority(self):
        for phase in ('bootstrap', 'idle', 'processing', 'unavailable', 'closed'):
            with self.subTest(phase=phase):
                policy = await self.wire(phase)
                self.assertIn('Identifikatoren', policy)
                self.assertIn('Stelle keine zusätzliche Pflichtangabe auf.', policy)
                self.assertIn('unbestätigte Nutzerangaben', policy)
                self.assertIn('keine Übernahme, Speicherung, Prüfung oder Ausführung', policy)

    async def test_generic_identifier_and_correction_are_preserved_as_data(self):
        raw = 'Die Kontaktperson ist die Projektleitung, Kennung ZX-17. Korrektur: ZX-18. Welche Hilfe bieten Sie?'
        policy = await self.wire('bootstrap', raw)
        self.assertIn('Identifikatoren', policy)
        self.assertIn('sprachliche Unklarheit', policy)
        self.assertNotIn('Sam', policy)
        self.assertNotIn('Führungskraft', policy)


if __name__ == '__main__':
    unittest.main()
