# self-test for local-llm-gateway
# Exercises: config loading, alias resolution, request forwarding,
# non-stream response, SSE streaming passthrough, error handling.

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

import gateway


class FakeUpstream(BaseHTTPRequestHandler):
    """Simulates a local model server: /health, /v1/models, /v1/chat/completions."""

    def log_message(self, fmt, *args):
        pass

    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        elif self.path == "/v1/models":
            self._json(200, {"data": [{"id": "deepseek-v4.1-flash", "object": "model"}]})
        else:
            self._json(404, {"error": {"message": "nope"}})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length).decode())
        if self.path != "/v1/chat/completions":
            self._json(404, {"error": {"message": "nope"}})
            return
        if payload.get("model") != "deepseek-v4.1-flash":
            self._json(400, {"error": {"message": "unknown model"}})
            return
        if payload.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b'data: {"delta":"ok"}\n\n')
            self.wfile.write(b'data: [DONE]\n\n')
            self.wfile.flush()
        else:
            self._json(200, {"choices": [{"message": {"content": "ok"}}],
                             "effort": payload.get("reasoning_effort")})


def free_port():
    s = ThreadingHTTPServer(("127.0.0.1", 0), FakeUpstream)
    return s


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.up = free_port()
        cls.up_port = cls.up.server_address[1]
        threading.Thread(target=cls.up.serve_forever, daemon=True).start()

        cfg = dict(gateway.DEFAULT_CONFIG)
        cfg["listen_port"] = 0
        cfg["upstream_base_url"] = "http://127.0.0.1:%d" % cls.up_port
        cfg["default_reasoning_effort"] = "low"
        cfg["model_aliases"] = {"qwen3.8-flash-next-iq3_s": "deepseek-v4.1-flash"}
        cls.cfg = cfg
        cls.gw = gateway.make_server(cfg)
        cls.gw_port = cls.gw.server_address[1]
        threading.Thread(target=cls.gw.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.gw.shutdown()
        cls.up.shutdown()

    def base(self):
        return "http://127.0.0.1:%d" % self.gw_port

    def test_health(self):
        with urlopen(self.base() + "/health", timeout=10) as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(json.loads(r.read())["status"], "ok")

    def test_model_alias_listed(self):
        with urlopen(self.base() + "/v1/models", timeout=10) as r:
            data = json.loads(r.read())
        ids = [m["id"] for m in data["data"]]
        self.assertIn("deepseek-v4.1-flash", ids)
        self.assertIn("qwen3.8-flash-next-iq3_s", ids)

    def test_alias_resolution_and_effort(self):
        body = json.dumps({"model": "qwen3.8-flash-next-iq3_s",
                           "messages": [{"role": "user", "content": "hi"}],
                           "max_tokens": 4}).encode()
        req = Request(self.base() + "/v1/chat/completions", data=body,
                      headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        self.assertEqual(data["choices"][0]["message"]["content"], "ok")
        self.assertEqual(data["effort"], "low")

    def test_stream_passthrough(self):
        body = json.dumps({"model": "deepseek-v4.1-flash",
                           "messages": [{"role": "user", "content": "hi"}],
                           "stream": True}).encode()
        req = Request(self.base() + "/v1/chat/completions", data=body,
                      headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=20) as r:
            raw = r.read().decode()
        self.assertIn('"delta":"ok"', raw)
        self.assertIn("[DONE]", raw)

    def test_bad_model(self):
        body = json.dumps({"model": "not-a-model",
                           "messages": [{"role": "user", "content": "hi"}]}).encode()
        req = Request(self.base() + "/v1/chat/completions", data=body,
                      headers={"Content-Type": "application/json"}, method="POST")
        try:
            urlopen(req, timeout=20)
            self.fail("expected 400")
        except Exception as exc:
            self.assertEqual(getattr(exc, "code", None), 400)

    def test_config_validation(self):
        try:
            gateway.load_config(None)
        except Exception:
            self.fail("None config should not fail")
        self.assertEqual(gateway.DEFAULT_CONFIG["listen_port"], 3065)


if __name__ == "__main__":
    unittest.main(verbosity=2)
