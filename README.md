# local-llm-gateway

A dependency-free, OpenAI-compatible HTTP gateway for a **local** model server.

Desktop AI clients (Claude-style gateways, Cherry Studio, Trae, YuE2 Studio,
Codex-style CLIs) all speak the OpenAI protocol. A self-hosted runtime
(Strata / llama.cpp / vLLM / Ollama) usually exposes the same shape but with
different model names, an API key requirement, or reasoning knobs that must be
passed at the top level. This gateway normalises those details so that a single
`base_url` serves every client while inference stays on your own machine.

## Why

- **One base_url for all clients** — no per-client engine adaptation.
- **Aliases** — map the name a client expects onto the real local model.
- **Effort passthrough** — `reasoning_effort` is forwarded at the top level and
  inside `chat_template_kwargs`, so the upstream runtime honours it.
- **Streaming** — SSE chunks are relayed unbuffered; no fake `Content-Length`.
- **Zero cloud billing** — the upstream is your own server.

## Requirements

- Python 3.8+
- Standard library only (no pip install)

## Quick start

```bash
python3 gateway.py --config config.example.json
# listening on http://127.0.0.1:3065
```

Then point any OpenAI-compatible client at:

```
base_url = http://127.0.0.1:3065/v1
```

## Self-check

```bash
python3 gateway.py --config config.example.json --self-check
```

Prints `self-check: health=200 models=200 -> PASS`.

## Configuration

| key | default | meaning |
|---|---|---|
| `listen_host` | `127.0.0.1` | bind address |
| `listen_port` | `3065` | bind port |
| `upstream_base_url` | `http://127.0.0.1:8080` | local model server |
| `upstream_api_key` | `""` | key injected for the upstream |
| `request_timeout` | `600` | upstream timeout in seconds |
| `default_reasoning_effort` | `null` | `none` / `low` / `medium` / `high` |
| `model_aliases` | `{}` | alias -> real model id |
| `health_path` | `/health` | upstream health endpoint |
| `models_path` | `/v1/models` | upstream model list |
| `chat_path` | `/v1/chat/completions` | upstream chat endpoint |
| `cors_origin` | `*` | CORS header value |

## Endpoints

| method | path | behaviour |
|---|---|---|
| GET | `/health` | gateway liveness + upstream URL |
| GET | `/v1/models` | upstream models, plus alias entries |
| POST | `/v1/chat/completions` | alias + effort normalisation, forwarded |

Errors from the upstream (400/404/500) are relayed with their JSON body;
an unreachable upstream becomes `502`, a timeout becomes `504`.

## Tests

```bash
python3 test_gateway.py
```

Six tests: health, alias listing, alias resolution + effort injection,
SSE passthrough, bad-model error, config validation. All pass with a fake
upstream server, so no real model is required.

## License

MIT — see `LICENSE`.
