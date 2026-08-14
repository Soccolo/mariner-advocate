import json
import unittest
from unittest.mock import patch

from mariner_core import ProviderConfig, _call_zai, _extract_zai_text


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

    def test_falls_back_to_reasoning_content_when_final_content_is_empty(self):
        text, _ = _extract_zai_text(
            {"choices": [{"message": {"content": "", "reasoning_content": '{"ok":true}'}}]}
        )
        self.assertEqual(json.loads(text), {"ok": True})

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


if __name__ == "__main__":
    unittest.main()
