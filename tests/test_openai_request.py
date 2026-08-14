import json
import unittest
from unittest.mock import Mock, patch

import requests

from mariner_core import AppError, ProviderConfig, _call_openai


def sse(*events: dict) -> list[bytes]:
    lines: list[bytes] = []
    for event in events:
        lines.append(b"event: " + str(event.get("type", "")).encode("utf-8"))
        lines.append(b"data: " + json.dumps(event).encode("utf-8"))
        lines.append(b"")
    return lines


def response_object(text: str, *, status: str = "completed", reason: str = "") -> dict:
    payload: dict = {
        "id": "resp_1",
        "status": status,
        "output": [
            {"type": "reasoning", "summary": []},
            {
                "type": "message",
                "content": [{"type": "output_text", "text": text}],
            },
        ],
    }
    if reason:
        payload["incomplete_details"] = {"reason": reason}
    return payload


def text_stream(text: str, *, status: str = "completed", reason: str = "") -> list[bytes]:
    terminal = {
        "completed": "response.completed",
        "incomplete": "response.incomplete",
        "failed": "response.failed",
    }[status]
    return sse(
        {"type": "response.created", "response": {"id": "resp_1", "status": "in_progress"}},
        {"type": "response.output_text.delta", "delta": text},
        {"type": terminal, "response": response_object(text, status=status, reason=reason)},
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


CONFIG = ProviderConfig(openai_key="secret", openai_model="gpt-5.6-sol")


class OpenAiRequestTests(unittest.TestCase):
    @patch("mariner_core.requests.post")
    def test_senior_arbitration_streams_at_pro_effort(self, post):
        post.return_value = fake_response(lines=text_stream('{"executiveSummary":"ok"}'))

        result = _call_openai("prompt", CONFIG, senior=True)

        self.assertEqual(result, {"executiveSummary": "ok"})
        body = post.call_args.kwargs["json"]
        # Arbitration reasons for minutes; a stream keeps the timeout between
        # chunks instead of bounding the whole turn.
        self.assertTrue(body["stream"])
        self.assertTrue(post.call_args.kwargs["stream"])
        self.assertEqual(body["reasoning"], {"effort": "high", "mode": "pro"})
        self.assertEqual(body["max_output_tokens"], CONFIG.openai_max_output_tokens)

    @patch("mariner_core.requests.post")
    def test_non_senior_calls_do_not_request_pro_mode(self, post):
        post.return_value = fake_response(lines=text_stream('{"ok":true}'))

        _call_openai("prompt", CONFIG, senior=False)

        self.assertEqual(post.call_args.kwargs["json"]["reasoning"], {"effort": "medium"})

    @patch("mariner_core.requests.post")
    def test_unsupported_pro_mode_degrades_instead_of_losing_arbitration(self, post):
        post.side_effect = [
            fake_response(
                ok=False,
                status=400,
                payload={
                    "error": {
                        "type": "invalid_request_error",
                        "message": "Unsupported parameter: 'reasoning.mode'",
                    }
                },
            ),
            fake_response(lines=text_stream('{"executiveSummary":"ok"}')),
        ]

        result = _call_openai("prompt", CONFIG, senior=True)

        self.assertEqual(result, {"executiveSummary": "ok"})
        self.assertEqual(post.call_count, 2)
        self.assertNotIn("mode", post.call_args_list[1].kwargs["json"]["reasoning"])

    @patch("mariner_core.requests.post")
    def test_blocked_streaming_falls_back_to_a_single_request(self, post):
        post.side_effect = [
            fake_response(
                ok=False,
                status=400,
                payload={
                    "error": {
                        "type": "invalid_request_error",
                        "message": "Unsupported parameter: 'stream' is not supported",
                    }
                },
            ),
            fake_response(payload=response_object('{"executiveSummary":"ok"}')),
        ]

        result = _call_openai("prompt", CONFIG, senior=True)

        self.assertEqual(result, {"executiveSummary": "ok"})
        self.assertEqual(post.call_count, 2)
        # Same variant retried, this time without streaming.
        retry = post.call_args_list[1].kwargs["json"]
        self.assertNotIn("stream", retry)
        self.assertEqual(retry["reasoning"], {"effort": "high", "mode": "pro"})

    @patch("mariner_core.requests.post")
    def test_authentication_failure_is_not_retried(self, post):
        post.return_value = fake_response(
            ok=False,
            status=401,
            payload={"error": {"type": "invalid_api_key", "message": "Incorrect API key"}},
        )

        with self.assertRaisesRegex(AppError, "request failed"):
            _call_openai("prompt", CONFIG, senior=True)

        self.assertEqual(post.call_count, 1)

    @patch("mariner_core.requests.post")
    def test_truncated_arbitration_is_recovered_and_flagged(self, post):
        post.return_value = fake_response(
            lines=text_stream(
                '{"executiveSummary":"Partial","resolvedDisputes":[{"topic":"Costs"}],"unres',
                status="incomplete",
                reason="max_output_tokens",
            )
        )

        result = _call_openai("prompt", CONFIG, senior=True)

        self.assertEqual(result["executiveSummary"], "Partial")
        self.assertTrue(result["responseTruncated"])

    @patch("mariner_core.requests.post")
    def test_exhausted_output_budget_names_the_setting_to_raise(self, post):
        post.return_value = fake_response(
            lines=text_stream("", status="incomplete", reason="max_output_tokens")
        )

        with self.assertRaisesRegex(AppError, "OPENAI_MAX_OUTPUT_TOKENS"):
            _call_openai("prompt", CONFIG, senior=True)

    @patch("mariner_core.requests.post")
    def test_refusal_is_reported_as_a_declined_request(self, post):
        refusal = {
            "id": "resp_1",
            "status": "completed",
            "output": [
                {"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}
            ],
        }
        post.return_value = fake_response(
            lines=sse({"type": "response.completed", "response": refusal})
        )

        with self.assertRaisesRegex(AppError, "declined"):
            _call_openai("prompt", CONFIG, senior=True)

    @patch("mariner_core.requests.post")
    def test_stream_error_event_is_surfaced(self, post):
        post.return_value = fake_response(
            lines=sse(
                {"type": "response.output_text.delta", "delta": "{"},
                {"type": "error", "error": {"type": "server_error", "message": "boom"}},
            )
        )

        with self.assertRaisesRegex(AppError, "request failed"):
            _call_openai("prompt", CONFIG, senior=True)

    @patch("mariner_core.requests.post")
    def test_timeout_is_reported_without_leaking_internals(self, post):
        post.side_effect = requests.Timeout("read timed out")

        with self.assertRaisesRegex(AppError, "timed out"):
            _call_openai("prompt", CONFIG, senior=True)

    @patch("mariner_core.requests.post")
    def test_non_ascii_output_survives_the_stream_decoder(self, post):
        post.return_value = fake_response(
            lines=text_stream('{"executiveSummary":"Marinarul român are dreptul la îngrijire."}')
        )

        result = _call_openai("prompt", CONFIG, senior=True)

        self.assertEqual(
            result["executiveSummary"], "Marinarul român are dreptul la îngrijire."
        )


if __name__ == "__main__":
    unittest.main()
