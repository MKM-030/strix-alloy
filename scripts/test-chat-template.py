"""Regression checks for Flash Next client instructions and tool history.

Requires Jinja2. Use --props <llama-server /props capture> to reproduce the
compatibility failures against the original model template before the fix.
"""

import argparse
import hashlib
import json
from pathlib import Path
import unittest

from jinja2 import Environment


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--props", type=Path)
parser.add_argument(
    "--template",
    type=Path,
    default=Path(__file__).resolve().parents[1] / "app" / "flash-next-clients.jinja",
)
args = parser.parse_args()
MARKER = "{# Original Qwen3.8-Flash-Next template below; keep unchanged. #}\n"
if args.props:
    ORIGINAL = TEMPLATE = json.loads(args.props.read_text(encoding="utf-8-sig"))["chat_template"]
else:
    TEMPLATE = args.template.read_text(encoding="utf-8")
    ORIGINAL = TEMPLATE.split(MARKER, 1)[1]


def reject(message):
    raise ValueError(message)


ENV = Environment()
ENV.globals["raise_exception"] = reject


def render(template, messages, **options):
    return ENV.from_string(template).render(
        messages=messages, tools=options.pop("tools", []),
        add_generation_prompt=True, **options,
    )


TOOLS = [{"type": "function", "function": {
    "name": "read_file", "description": "Read a workspace file.",
    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
}}]
HISTORY = [
    {"role": "user", "content": "Read README.md."},
    {"role": "assistant", "content": "", "reasoning_content": "I should read it.",
     "tool_calls": [{"id": "call_1", "type": "function", "function": {
         "name": "read_file", "arguments": {"path": "README.md"},
     }}]},
    {"role": "tool", "tool_call_id": "call_1", "content": "File contents."},
    {"role": "user", "content": "Summarize it."},
]


class ClientTemplateTests(unittest.TestCase):
    def test_original_template_is_unchanged(self):
        self.assertEqual(hashlib.sha256(ORIGINAL.encode()).hexdigest(),
                         "c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041")

    def test_original_reproduces_late_system_failure(self):
        with self.assertRaisesRegex(ValueError, "System message must be at the beginning"):
            render(ORIGINAL, [HISTORY[0], {"role": "system", "content": "Later instructions."}])

    def test_merges_all_instructions_in_order_and_preserves_tool_history(self):
        messages = [
            {"role": "system", "content": "First instructions."},
            *HISTORY[:2],
            {"role": "developer", "content": [{"type": "text", "text": "Second instructions."}]},
            HISTORY[2],
            {"role": "system", "content": "Third instructions."},
            HISTORY[3],
        ]
        expected = [{"role": "system", "content":
                     "First instructions.\n\nSecond instructions.\n\nThird instructions."}, *HISTORY]
        before = json.dumps(messages)
        self.assertEqual(render(TEMPLATE, messages, tools=TOOLS), render(ORIGINAL, expected, tools=TOOLS))
        self.assertEqual(json.dumps(messages), before, "Rendering must not mutate input messages")

    def test_developer_only_instructions_are_retained(self):
        actual = [{"role": "developer", "content": "Use this directory."}, *HISTORY]
        expected = [{"role": "system", "content": "Use this directory."}, *HISTORY]
        self.assertEqual(render(TEMPLATE, actual, tools=TOOLS), render(ORIGINAL, expected, tools=TOOLS))

    def test_existing_chat_and_tool_rendering_are_unchanged(self):
        for head in ([], [{"role": "system", "content": "Be concise."}],
                     [{"role": "system", "content": [{"type": "text", "text": "Be concise."}]}],
                     [{"role": "system", "content": None}]):
            for tools in ([], TOOLS):
                for options in ({}, {"enable_thinking": False},
                                {"reasoning_effort": "low", "preserve_thinking": False},
                                {"reasoning_effort": "medium"}):
                    with self.subTest(head=head, tools=bool(tools), options=options):
                        self.assertEqual(render(TEMPLATE, head + HISTORY, tools=tools, **options),
                                         render(ORIGINAL, head + HISTORY, tools=tools, **options))

    def test_system_images_remain_rejected(self):
        messages = [{"role": "developer", "content": [{"type": "image"}]}, *HISTORY]
        with self.assertRaisesRegex(ValueError, "System message cannot contain images"):
            render(TEMPLATE, messages)

    def test_invalid_instruction_content_remains_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unexpected content type"):
            render(TEMPLATE, [{"role": "system", "content": 42}, *HISTORY])

    def test_missing_user_query_remains_rejected(self):
        with self.assertRaisesRegex(ValueError, "No user query"):
            render(TEMPLATE, [{"role": "system", "content": "Instructions only."}])


if __name__ == "__main__":
    print("Original template SHA256:", hashlib.sha256(ORIGINAL.encode()).hexdigest())
    unittest.main(argv=[__file__], verbosity=2)
