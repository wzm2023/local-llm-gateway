#!/usr/bin/env python3
"""
local-llm-gateway
-----------------
A tiny, dependency-free OpenAI-compatible gateway for a LOCAL model server.

Why it exists:
  Many desktop AI clients (Claude-3p, Cherry Studio, Trae, YuE2 Studio,
  Codex-style CLIs) only speak the OpenAI HTTP protocol. A local runtime
  (e.g. a self-hosted Strata / llama.cpp / vLLM server) usually exposes the
  same shape but with slightly different details:

  * model names differ from the names a client expects (aliases)
  * the upstream requires an API key that the client does not have
  * reasoning-effort knobs are accepted only at the top level or inside
  chat_template_kwargs
  * streaming responses must not be buffered

This gateway normalises those details, so one base_url serves every client
while the inference stays local (zero cloud billing).

Run:
    python3 gateway.py --config config.example.json
Check:
    python3 gateway.py --config config.example.json --self-check
"""

import argparse
import json
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

VERSION = "1.0.0"

DEFAULT_CONFIG = {
    "listen_host": "127.0.0.1",
    "listen_port": 3065,
    "upstream_base_url": "http://127.0.0.1:8080",
    "upstream_api_key": "",
    "request_timeout": 600,
    "default_reasoning_effort": None,
    "model_aliases": {},
    "health_path": "/health",
    "models_path": "/v1/models",
    "chat_path": "/v1/chat/completions",
    "cors_origin": "*",
}


def load_config(path):
    cfg = dict(DEFAULT_CONFIG)
    if path:
        with open(path, "r", encoding="utf-8") as fh:
            user = json.load(fh)
        if not isinstance(user, dict):
            raise ValueError("config must be a JSON object")
        unknown = set(user) - set(DEFAULT_CONFIG)
        if unknown:
            raise ValueError("unknown config keys: %s" % ", ".join(sorted(unknown)))
        cfg.update(user)
    return cfg


def resolve_alias(cfg, model):
    aliases = cfg.get("model_aliases") or {}
    return aliases.get(model, model)


def upstream_url(cfg, path):
    base = cfg["upstream_base_url"].rstrip("/")
    return base + path


def build_headers(cfg):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "local-llm-gateway/" + VERSION,
    }
    key = cfg.get("upstream_api_key") or ""
    if key:
        headers["Authorization"] = "Bearer " + key
    return headers


class GatewayHandler(BaseHTTPRequestHandler):
    cfg = DEFAULT_CONFIG
    server_version = "local-llm-gateway/" + VERSION

    # ---------- helpers ----------
    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", self.cfg["cors_origin"])
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", self.cfg["cors_origin"])
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _proxy(self, method, path, body, stream=False):
        url = upstream_url(self.cfg, path)
        req = Request(url, data=body if method == "POST" else None, method=method)
        for k, v in build_headers(self.cfg).items():
            req.add_header(k, v)
        try:
            resp = urlopen(req, timeout=self.cfg["request_timeout"])
        except HTTPError as exc:
            raw = exc.read()
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception:
                payload = {"error": {"message": raw.decode("utf-8", "replace")}}
            return exc.code, payload, None
        except URLError as exc:
            return 502, {"error": {"message": "upstream unreachable: %s" % exc.reason}}, None
        except socket.timeout:
            return 504, {"error": {"message": "upstream timeout"}}, None

        if stream:
            return resp.status, resp, resp.headers.get("Content-Type", "text/event-stream")
        return resp.status, resp.read(), resp.headers.get("Content-Type", "application/json")


    # ---------- routes ----------
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.cfg["cors_origin"])
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/health", self.cfg["health_path"]):
            self._send_json(200, {"status": "ok", "gateway": VERSION,
                                  "upstream": self.cfg["upstream_base_url"]})
            return
        if self.path == self.cfg["models_path"] or self.path == "/models":
            status, payload, _ = self._proxy("GET", self.cfg["models_path"], b"")
            if status != 200:
                self._send_json(status, payload if isinstance(payload, dict) else {"error": payload})
                return
            try:
                data = json.loads(payload.decode("utf-8"))
            except Exception:
                self._send_json(502, {"error": {"message": "upstream returned invalid JSON"}})
                return
            items = data.get("data") or []
            alias_set = set((self.cfg.get("model_aliases") or {}).values())
            out = []
            for it in items:
                out.append(it)
                if it.get("id") in alias_set:
                    for alias, target in (self.cfg.get("model_aliases") or {}).items():
                        if target == it.get("id"):
                            out.append({"id": alias, "object": "model", "upstream": target})
            data["data"] = out
            self._send_json(200, data)
            return
        self._send_json(404, {"error": {"message": "not found: " + self.path}})

    def do_POST(self):
        if self.path != self.cfg["chat_path"]:
            self._send_json(404, {"error": {"message": "not found: " + self.path}})
            return

        body = self._read_body()
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            self._send_json(400, {"error": {"message": "request body must be JSON"}})
            return
        if not isinstance(payload, dict):
            self._send_json(400, {"error": {"message": "request body must be an object"}})
            return

        model = payload.get("model")
        if not isinstance(model, str) or not model:
            self._send_json(400, {"error": {"message": "model is required"}})
            return
        payload["model"] = resolve_alias(self.cfg, model)

        effort = payload.pop("reasoning_effort", None)
        if effort is None:
            effort = self.cfg.get("default_reasoning_effort")
        if effort not in (None, "", "none", "low", "medium", "high"):
            self._send_json(400, {"error": {"message": "reasoning_effort must be none/low/medium/high"}})
            return
        if effort:
            payload["reasoning_effort"] = effort
            ctk = payload.get("chat_template_kwargs")
            if isinstance(ctk, dict):
                ctk.setdefault("reasoning_effort", effort)
            else:
                payload["chat_template_kwargs"] = {"reasoning_effort": effort}

        stream = bool(payload.get("stream"))
        out = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        status, resp, ctype = self._proxy("POST", self.cfg["chat_path"], out, stream=stream)

        if status != 200:
            if isinstance(resp, dict):
                self._send_json(status, resp)
            else:
                self._send_json(status, {"error": {"message": resp.decode("utf-8", "replace")}})
            return

        if stream:
            self.send_response(200)
            self.send_header("Content-Type", ctype or "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", self.cfg["cors_origin"])
            self.end_headers()
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        else:
            self._send_bytes(200, resp, ctype or "application/json")


def make_server(cfg):
    handler = type("BoundGatewayHandler", (GatewayHandler,), {"cfg": cfg})
    httpd = ThreadingHTTPServer((cfg["listen_host"], cfg["listen_port"]), handler)
    return httpd


def self_check(cfg):
    """Start the gateway on a free port, hit /health and /v1/models."""
    probe = dict(cfg)
    probe["listen_port"] = 0
    httpd = make_server(probe)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % port
    try:
        from urllib.request import urlopen as _open
        status = _open(base + "/health", timeout=10).status
        models_status = _open(base + "/v1/models", timeout=10).status
    except Exception as exc:
        print("self-check failed: %s" % exc)
        return 1
    finally:
        httpd.shutdown()
    ok = status == 200 and models_status == 200
    print("self-check: health=%d models=%d -> %s" % (status, models_status, "PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="OpenAI-compatible gateway for a local model server")
    parser.add_argument("--config", default=None, help="path to JSON config")
    parser.add_argument("--self-check", action="store_true", help="probe health and models endpoints")
    parser.add_argument("--version", action="store_true", help="print version")
    args = parser.parse_args(argv)

    if args.version:
        print(VERSION)
        return 0

    cfg = load_config(args.config)
    if args.self_check:
        return self_check(cfg)

    httpd = make_server(cfg)
    print("local-llm-gateway %s listening on http://%s:%d (upstream %s)"
          % (VERSION, cfg["listen_host"], cfg["listen_port"], cfg["upstream_base_url"]))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
