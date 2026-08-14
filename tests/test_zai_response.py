import json
import unittest
from unittest.mock import patch

from mariner_core import (
    AppError,
    ProviderConfig,
    _call_zai,
    _extract_zai_text,
    parse_model_json,
)


class ZaiResponseTests(unittest.TestCase):
    def test_extracts_plain_content(self):
        text, reason = _extract_zai_text(
            {"choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}]}
        )
        self.assertEqual(text, '{"ok":true}')
        self.assertEqual(reason, "stop")

    def test_serializes_object_content_as_json(self):
        text, _ = _extract_zai_text(
            {"choices": [{"message": {"content": {"ok": True}}}]}
        )
        self.assertEqual(json.loads(text), {"ok": True})

    def test_joins_segmented_content(self):
        text, _ = _extract_zai_text(
            {
                "choices": [
                    {"message": {"content": [{"type": "text", "text": '{"ok":'}, {"text": "true}"}]}}
                ]
            }
        )
        self.assertEqual(json.loads(text), {"ok": True})

    def test_does_not_treat_reasoning_content_as_the_final_answer(self):
        text, _ = _extract_zai_text(
            {"choices": [{"message": {"content": "", "reasoning_content": '{"ok":true}'}}]}
        )
        self.assertEqual(text, "")

    def test_parser_handles_thinking_prefix_and_json_fence(self):
        result = parse_model_json(
            '<think>internal text</think>\n```json\n{"ok": true}\n```', "Z.AI"
        )
        self.assertEqual(result, {"ok": True})

    def test_parser_handles_double_encoded_json(self):
        result = parse_model_json('"{\\"ok\\": true}"', "Z.AI")
        self.assertEqual(result, {"ok": True})

    def test_parser_rejects_nested_object_inside_truncated_outer_json(self):
        with self.assertRaises(AppError):
            parse_model_json(
                '{"summary":"unfinished","issues":[{"issue":"nested complete"}]',
                "Z.AI",
            )

    @patch("mariner_core._provider_post")
    def test_requests_json_mode(self, provider_post):
        provider_post.return_value = {
            "choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}]
        }
        result = _call_zai("prompt", ProviderConfig(zai_key="secret"))
        self.assertEqual(result, {"ok": True})
        body = provider_post.call_args.kwargs["body"]
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertFalse(body["stream"])
        self.assertEqual(body["max_tokens"], 24_000)

    @patch("mariner_core._provider_post")
    def test_retries_truncated_json_without_thinking(self, provider_post):
        provider_post.side_effect = [
            {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": '{"summary":"unfinished'},
                    }
                ]
            },
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"summary":"complete"}'},
                    }
                ]
            },
        ]

        result = _call_zai("prompt", ProviderConfig(zai_key="secret"))

        self.assertEqual(result, {"summary": "complete"})
        self.assertEqual(provider_post.call_count, 2)
        retry_body = provider_post.call_args_list[1].kwargs["body"]
        self.assertEqual(retry_body["thinking"], {"type": "disabled"})
        self.assertEqual(retry_body["temperature"], 0.0)
        self.assertIn("RESPONSE CORRECTION", retry_body["messages"][0]["content"])

    @patch("mariner_core._provider_post")
    def test_reports_invalid_json_only_after_retry(self, provider_post):
        provider_post.side_effect = [
            {
                "choices": [
                    {"finish_reason": "stop", "message": {"content": "plain prose"}}
                ]
            },
            {
                "choices": [
                    {"finish_reason": "stop", "message": {"content": "still prose"}}
                ]
            },
        ]

        with self.assertRaisesRegex(AppError, "automatic retry"):
            _call_zai("prompt", ProviderConfig(zai_key="secret"))

        self.assertEqual(provider_post.call_count, 2)

    @patch("mariner_core._provider_post")
    def test_reasoning_content_is_ignored_and_final_content_is_retried(self, provider_post):
        provider_post.side_effect = [
            {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {
                            "content": "",
                            "reasoning_content": '{"summary":"hidden reasoning"}',
                        },
                    }
                ]
            },
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"summary":"final answer"}'},
                    }
                ]
            },
        ]

        result = _call_zai("prompt", ProviderConfig(zai_key="secret"))

        self.assertEqual(result, {"summary": "final answer"})
        self.assertEqual(provider_post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
