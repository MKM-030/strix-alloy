"""Synthetic known-envelope regression; no claim about an unlogged Android payload."""
import asyncio
import importlib
import json
import unittest
from unittest.mock import patch

from native_bridge import Config, Dialog, NativeCall

try:
    output = importlib.import_module('spoken_output')
except ModuleNotFoundError as error:
    if error.name != 'spoken_output':
        raise
    output = None

HUMAN = 'Fertig (Referenz [A-12]): REQ0012345, RITM0012346.'
WRAPPED = json.dumps({'processed_output':HUMAN}, ensure_ascii=False)


class FixtureDialog(Dialog):
    def __init__(self, messages):
        super().__init__(Config())
        self.messages = messages

    async def open(self):
        return []

    async def close(self):
        pass

    async def request(self, method, path, **kwargs):
        if path == '/api/message':
            return {'accepted':True}
        return {'cursor':1,'busy':False,
                'events':[{'kind':'bot','text':text} for text in self.messages]}


class PublisherTests(unittest.IsolatedAsyncioTestCase):
    async def test_known_envelope_reaches_result_and_callback_as_identical_human_text(self):
        published = []
        async def publish(text):
            published.append(text)
        result = await FixtureDialog([WRAPPED]).turn('synthetic input',on_reply=publish)
        self.assertEqual(result,[HUMAN])
        self.assertEqual(published,result)

    async def test_human_text_empty_envelope_and_unknown_nonstrings_keep_existing_behavior(self):
        empty = '{"processed_output":""}'
        other = {'processed_output':'not serialized'}
        source = [HUMAN,empty,other]
        published = []
        async def publish(text):
            published.append(text)
        self.assertEqual(await FixtureDialog(source).turn('synthetic input',on_reply=publish),source)
        self.assertEqual(published,source)
        self.assertIs(published[2],other)

    async def test_native_call_transcript_and_tts_receive_same_unwrapped_text(self):
        spoken = []
        done = asyncio.Event()
        class Speech:
            async def transcribe(self,pcm):
                return 'synthetic input'
            async def synthesize(self,text):
                spoken.append(text)
                done.set()
                yield b''
        call = NativeCall(Config(),Speech(),FixtureDialog([WRAPPED]))
        call.spawn(call.process_turns())
        try:
            await call.turns.put((0,bytes(3200)))
            await asyncio.wait_for(done.wait(),1)
            transcripts = [event['data']['content'] for event in call.pending_events
                if event.get('type') == 'transcript' and event['data'].get('role') == 'assistant']
            self.assertEqual(spoken,[HUMAN])
            self.assertEqual(transcripts,spoken)
        finally:
            await call.close()


class EnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(output,'strict spoken output helper is missing')

    def test_only_exact_one_field_complete_object_is_unwrapped_once(self):
        self.assertEqual(output.spoken_text(WRAPPED),HUMAN)
        self.assertEqual(output.spoken_text(' \n'+WRAPPED+'\t '),HUMAN)
        inner = json.dumps({'processed_output':HUMAN})
        self.assertEqual(output.spoken_text(json.dumps({'processed_output':inner})),inner)

    def test_other_json_human_text_and_natural_brackets_are_preserved(self):
        sources = [HUMAN,'Output: '+WRAPPED,'```json\n'+WRAPPED+'\n```',
            json.dumps([{'processed_output':HUMAN}]),json.dumps({'output':HUMAN}),
            json.dumps({'processed_output':HUMAN,'metadata':1}),
            json.dumps({'processed_output':{'text':HUMAN}}),
            json.dumps({'processed_output':[HUMAN]}),
            json.dumps({'processed_output':True}),json.dumps({'processed_output':7}),
            json.dumps({'processed_output':None}),WRAPPED+' trailing',WRAPPED+WRAPPED]
        for source in sources:
            with self.subTest(source=source):
                self.assertIs(output.spoken_text(source),source)

    def test_duplicate_keys_nonfinite_constants_and_malformed_json_are_preserved(self):
        sources = ['{"processed_output":"first","processed_output":"second"}',
            '{"processed_output":"first","processed_\\u006futput":"second"}',
            '{"processed_output":NaN}','{"processed_output":Infinity}',
            '{"processed_output":-Infinity}','{"processed_output":1e9999}',
            '{"processed_output":"text","metadata":{"same":1,"same":2}}',
            '{"processed_output":"text",}', '{"processed_output":"unterminated}',
            '\ufeff'+WRAPPED,'[','{'*2000,'{"processed_output":"\\ud800"}']
        for source in sources:
            with self.subTest(source=source[:120]):
                self.assertIs(output.spoken_text(source),source)

    def test_empty_or_whitespace_inner_text_is_not_silently_destroyed(self):
        for text in ('',' ','\t\n'):
            source = json.dumps({'processed_output':text})
            self.assertIs(output.spoken_text(source),source)

    def test_nonstring_values_are_returned_without_stringification(self):
        for value in (None,False,0,7,[],{}, {'processed_output':'text'},b'bytes'):
            self.assertIs(output.spoken_text(value),value)

    def test_wire_byte_bound_accepts_limit_and_skips_parsing_above_it(self):
        prefix = '{"processed_output":"'
        suffix = '"}'
        limit = output.MAX_ENVELOPE_BYTES
        text = 'x'*(limit-len(prefix)-len(suffix))
        self.assertEqual(output.spoken_text(prefix+text+suffix),text)
        over = prefix+text+'x'+suffix
        multibyte = json.dumps({'processed_output':'ä'*(limit//2)},ensure_ascii=False)
        self.assertLess(len(multibyte),limit)
        for source in (over,multibyte):
            with self.subTest(length=len(source)),patch.object(output.json,'loads',
                    side_effect=AssertionError('oversized envelope must not be parsed')):
                self.assertIs(output.spoken_text(source),source)


if __name__ == '__main__':
    unittest.main()
