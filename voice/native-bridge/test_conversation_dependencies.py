"""No-inference dependency preparation and call-local construction checks."""
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

import native_bridge as bridge
import native_duplex as duplex


class ForbiddenConstruction:
    def __init__(self, *args, **kwargs):
        raise AssertionError('dependency preparation constructed a runtime owner')


def dependency_modules():
    optional = Path(duplex.__file__).resolve().parent.parent / 'optional-omni'
    protocol = ModuleType('omni_protocol')
    protocol.__file__ = str(optional / 'omni_protocol.py')
    conversation = ModuleType('omni_conversation')
    conversation.__file__ = str(optional / 'omni_conversation.py')
    conversation.OmniConversation = type('Adapter', (ForbiddenConstruction,), {})
    socket = ModuleType('local_llm_socket')
    socket.LocalTextSocket = type('Socket', (ForbiddenConstruction,), {})
    pipeline = ModuleType('pipecat_dialogue')
    pipeline.PipecatDialogue = type('Dialogue', (ForbiddenConstruction,), {})
    return {'omni_protocol': protocol, 'omni_conversation': conversation,
            'local_llm_socket': socket, 'pipecat_dialogue': pipeline}


class PreparationTests(unittest.TestCase):
    def helper(self):
        helper = getattr(duplex, 'prepare_conversation_dependencies', None)
        self.assertTrue(callable(helper), 'selected conversation dependencies must be prepared before calls')
        return helper

    def test_preparation_only_returns_classes_and_is_reusable(self):
        helper = self.helper()
        modules = dependency_modules()
        with patch.dict(sys.modules, modules):
            first = helper()
            second = helper()
        expected = (modules['omni_conversation'].OmniConversation,
                    modules['local_llm_socket'].LocalTextSocket,
                    modules['pipecat_dialogue'].PipecatDialogue)
        self.assertEqual(first, expected)
        self.assertEqual(second, expected)

    def test_preparation_retains_optional_module_origin_validation(self):
        helper = self.helper()
        modules = dependency_modules()
        modules['omni_conversation'].__file__ = str(Path(duplex.__file__).with_name('foreign.py'))
        with patch.dict(sys.modules, modules), self.assertRaisesRegex(RuntimeError, 'Unexpected optional'):
            helper()

    def test_missing_selected_dependency_propagates(self):
        helper = self.helper()
        modules = dependency_modules()
        modules['pipecat_dialogue'] = None
        with patch.dict(sys.modules, modules), self.assertRaises(ImportError):
            helper()


class StartupPreparationTests(unittest.IsolatedAsyncioTestCase):
    async def start(self, config, *, failure=False):
        events = []

        def prepare():
            events.append('dependencies')
            if failure:
                raise ImportError('selected dependency unavailable')

        class Session:
            def __init__(self, **kwargs):
                events.append('http_session')

            async def close(self):
                events.append('http_closed')

        async def asr_ready(*args):
            events.append('asr_readiness')

        with patch.object(bridge, 'prepare_conversation_dependencies', prepare, create=True), \
                patch.object(bridge, 'ClientSession', Session), \
                patch.object(bridge, 'require_asr_ready', asr_ready):
            app = bridge.create_app(config, dialog_factory=lambda: self.fail('startup created a caller dialog'),
                speech_factory=lambda _: self.fail('startup created caller speech'))
            lifecycle = app.cleanup_ctx[0](app)
            try:
                if failure:
                    with self.assertRaises(ImportError):
                        await anext(lifecycle)
                    self.assertEqual(events, ['dependencies'])
                else:
                    await anext(lifecycle)
                    return events
            finally:
                try:
                    await anext(lifecycle)
                except StopAsyncIteration:
                    pass

    async def test_controller_dependencies_finish_before_http_or_startup_ready(self):
        config = bridge.Config(instance_name='fixture', voice_service_id='assistant',
            conversation_transport='controller-text',
            conversation_http_url='http://127.0.0.1:8840/v1/chat/completions',
            conversation_token_file='C:/fixture/token.txt')
        events = await self.start(config)
        self.assertEqual(events, ['dependencies', 'http_session', 'http_session',
                                  'asr_readiness', 'http_closed', 'http_closed'])

    async def test_websocket_dependencies_are_also_prepared_before_startup_ready(self):
        config = bridge.Config(instance_name='fixture', voice_service_id='assistant',
            conversation_ws_url='ws://127.0.0.1:9999')
        events = await self.start(config)
        self.assertEqual(events, ['dependencies', 'http_session', 'http_session',
                                  'asr_readiness', 'http_closed', 'http_closed'])

    async def test_legacy_startup_does_not_require_optional_conversation_dependencies(self):
        config = bridge.Config(instance_name='fixture', voice_service_id='assistant')
        events = await self.start(config)
        self.assertEqual(events, ['http_session', 'http_session', 'asr_readiness',
                                  'http_closed', 'http_closed'])

    async def test_selected_dependency_failure_prevents_startup_and_resource_creation(self):
        config = bridge.Config(instance_name='fixture', voice_service_id='assistant',
            conversation_ws_url='ws://127.0.0.1:9999')
        await self.start(config, failure=True)


class CallConstructionTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepared_classes_still_create_distinct_call_owners_and_report_timings(self):
        self.assertTrue(callable(getattr(duplex, 'prepare_conversation_dependencies', None)),
                        'dependency preparation missing')

        class Socket:
            def __init__(self, url, token_file):
                self.url, self.token_file = url, token_file

        class Adapter:
            def __init__(self, factory, *, deadlines):
                self.factory, self.deadlines = factory, deadlines

        class Dialogue:
            def __init__(self, conversation):
                self.conversation = conversation

            async def start(self, call_id, epoch, seed):
                self.call_id, self.epoch, self.seed = call_id, epoch, seed

        with patch.object(duplex, 'prepare_conversation_dependencies', return_value=(Adapter, Socket, Dialogue)), \
                self.assertLogs(duplex.LOG, level='INFO') as logs:
            first = await duplex.open_conversation('', 'first-call', 3,
                controller_url='http://127.0.0.1:8840/v1/chat/completions', controller_token_file='C:/fixture/token')
            second = await duplex.open_conversation('', 'second-call', 7,
                controller_url='http://127.0.0.1:8840/v1/chat/completions', controller_token_file='C:/fixture/token')
        self.assertIsNot(first, second)
        self.assertIsNot(first.conversation, second.conversation)
        self.assertIsNot(first.controller_transport, second.controller_transport)
        self.assertIs(first.conversation.factory(), first.controller_transport)
        self.assertEqual((first.call_id, first.epoch), ('first-call', 3))
        self.assertEqual((second.call_id, second.epoch), ('second-call', 7))
        self.assertEqual(len(logs.output), 2)
        for line in logs.output:
            self.assertRegex(line, r'dependencies_ms=\d+ initialization_ms=\d+')


if __name__ == '__main__':
    unittest.main()
