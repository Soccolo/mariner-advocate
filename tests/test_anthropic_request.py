import json
import unittest
from unittest.mock import Mock, patch

import requests

from mariner_core import (
    ANALYSIS_JSON_SCHEMA,
    AppError,
    ProviderConfig,
    _call_anthropic,
)


def sse(*events: dict) -> list[bytes]:
    lines: list[bytes] = []
    for event in events:
        lines.append(f"event: {event['type']}".encode("utf-8"))
        lines.append(b"data: " + json.dumps(event).encode("utf-8"))
        lines.append(b"")
    return lines


def text_stream(text: str, *, stop_reason: str = "end_turn") -> list[bytes]:
    return sse(
        {"type": "message_start", "message": {"id": "msg_1"}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "hidden"}},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": text}},
        {"type": "message_delta", "delta": {"stop_reason": stop_reason}},
        {"type": "message_stop"},
    )


def fake_response(*, ok=True, status=200, lines=None, payload=None):
    response = Mock()
    response.ok = ok
    response.status_code = status
    response.iter_lines.return_value = iter(lines or [])
    response.json.return_value = payload if payload is not None else {}
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    return response


CONFIG = ProviderConfig(anthropic_key="secret", anthropic_model="claude-opus-5")


class AnthropicRequestTests(unittest.TestCase):
    @patch("mariner_core.requests.post")
    def test_streams_with_a_thinking_aware_output_budget(self, post):
        post.return_value = fake_response(lines=text_stream('{"summary":"ok"}'))

        result = _call_anthropic("prompt", CONFIG, schema=ANALYSIS_JSON_SCHEMA)

        self.assertEqual(result, {"summary": "ok"})
        body = post.call_args.kwargs["json"]
        # claude-opus-5 thinks by default and max_tokens covers thinking plus the
        # answer, so the budget must be large and the request must stream.
        self.assertTrue(body["stream"])
        self.assertTrue(post.call_args.kwargs["stream"])
        self.assertEqual(body["max_tokens"], CONFIG.anthropic_max_tokens)
        self.assertEqual(body["thinking"], {"type": "adaptive"})
        self.assertEqual(body["output_config"]["effort"], "high")
        self.assertEqual(
            body["output_config"]["format"],
            {"type": "json_schema", "schema": ANALYSIS_JSON_SCHEMA},
        )

    @patch("mariner_core.requests.post")
    def test_hidden_thinking_is_never_treated_as_the_answer(self, post):
        post.return_value = fake_response(
            lines=sse(
                {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}},
                {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": '{"summary":"reasoning"}'}},
                {"type": "message_delta", "delta": {"stop_reason": "end_turn"}},
            )
        )

        with self.assertRaisesRegex(AppError, "no final content"):
            _call_anthropic("prompt", CONFIG)

    @patch("mariner_core.requests.post")
    def test_unsupported_parameter_falls_back_instead_of_failing_the_stage(self, post):
        post.side_effect = [
            fake_response(
                ok=False,
                status=400,
                payload={
                    "error": {
                        "type": "invalid_request_error",
                        "message": "output_config.format: unsupported parameter",
                    }
                },
            ),
            fake_response(lines=text_stream('{"summary":"ok"}')),
        ]

        result = _call_anthropic("prompt", CONFIG, schema=ANALYSIS_JSON_SCHEMA)

        self.assertEqual(result, {"summary": "ok"})
        self.assertEqual(post.call_count, 2)
        self.assertNotIn("format", post.call_args_list[1].kwargs["json"]["output_config"])

    @patch("mariner_core.requests.post")
    def test_authentication_failure_is_not_retried(self, post):
        post.return_value = fake_response(
            ok=False,
            status=401,
            payload={"error": {"type": "authentication_error", "message": "invalid x-api-key"}},
        )

        with self.assertRaisesRegex(AppError, "request failed"):
            _call_anthropic("prompt", CONFIG, schema=ANALYSIS_JSON_SCHEMA)

        self.assertEqual(post.call_count, 1)

    @patch("mariner_core.requests.post")
    def test_truncated_json_is_recovered_and_flagged(self, post):
        post.return_value = fake_response(
            lines=text_stream(
                '{"summary":"Partial","issues":[{"issue":"Medical costs"}],"nextSt',
                stop_reason="max_tokens",
            )
        )

        result = _call_anthropic("prompt", CONFIG)

        self.assertEqual(result["summary"], "Partial")
        self.assertTrue(result["responseTruncated"])

    @patch("mariner_core.requests.post")
    def test_exhausted_output_budget_names_the_setting_to_raise(self, post):
        post.return_value = fake_response(lines=text_stream("", stop_reason="max_tokens"))

        with self.assertRaisesRegex(AppError, "ANTHROPIC_MAX_TOKENS"):
            _call_anthropic("prompt", CONFIG)

    @patch("mariner_core.requests.post")
    def test_refusal_is_reported_as_a_declined_request(self, post):
        post.return_value = fake_response(lines=text_stream("", stop_reason="refusal"))

        with self.assertRaisesRegex(AppError, "declined"):
            _call_anthropic("prompt", CONFIG)

    @patch("mariner_core.requests.post")
    def test_stream_error_event_is_surfaced(self, post):
        post.return_value = fake_response(
            lines=sse(
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}},
            )
        )

        with self.assertRaisesRegex(AppError, "request failed"):
            _call_anthropic("prompt", CONFIG)

    @patch("mariner_core.requests.post")
    def test_timeout_is_reported_without_leaking_internals(self, post):
        post.side_effect = requests.Timeout("read timed out")

        with self.assertRaisesRegex(AppError, "timed out"):
            _call_anthropic("prompt", CONFIG)

    @patch("mariner_core.requests.post")
    def test_non_ascii_output_survives_the_stream_decoder(self, post):
        post.return_value = fake_response(
            lines=text_stream('{"summary":"Marinarul român a suferit o fractură."}')
        )

        result = _call_anthropic("prompt", CONFIG)

        self.assertEqual(result["summary"], "Marinarul român a suferit o fractură.")


if __name__ == "__main__":
    unittest.main()
