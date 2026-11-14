"""OpenAI 兼容客户端的本地回环测试(不访问外网)。"""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from solver.llm import LLMConfig, LLMError, complete_chat


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length))
        self.server.payloads.append(payload)
        self.server.auth_headers.append(self.headers.get("Authorization"))

        if "/fail" in self.path:
            body = b'{"error":"invalid key"}'
            status = 401
        else:
            content = json.dumps(
                {"type": "arithmetic", "expression": "1+1"}
            )
            body = json.dumps(
                {"choices": [{"message": {"content": content}}]}
            ).encode("utf-8")
            status = 200

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class LLMClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.server.payloads = []
        cls.server.auth_headers = []
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True
        )
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}/v1"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_complete_chat(self) -> None:
        messages = [{"role": "user", "content": "题目: 1+1"}]
        content = complete_chat(
            messages,
            LLMConfig(
                base_url=self.base,
                api_key="test-key",
                model="fake-model",
                timeout=5,
            ),
        )
        self.assertIn("arithmetic", content)
        self.assertEqual(self.server.payloads[-1]["model"], "fake-model")
        self.assertEqual(self.server.payloads[-1]["messages"], messages)
        self.assertEqual(
            self.server.auth_headers[-1], "Bearer test-key"
        )

    def test_http_error(self) -> None:
        with self.assertRaises(LLMError) as context:
            complete_chat(
                [{"role": "user", "content": "hi"}],
                LLMConfig(
                    base_url=f"{self.base}/fail",
                    api_key="bad",
                    model="fake-model",
                    timeout=5,
                ),
            )
        self.assertIn("401", str(context.exception))

    def test_missing_api_key(self) -> None:
        with self.assertRaises(LLMError):
            complete_chat(
                [{"role": "user", "content": "hi"}],
                LLMConfig(
                    base_url=self.base,
                    api_key="",
                    model="fake-model",
                    timeout=5,
                ),
            )


if __name__ == "__main__":
    unittest.main()
