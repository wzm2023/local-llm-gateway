# Codex for Open Source — application draft

Official form: https://openai.com/form/codex-for-oss
Also listed as https://developers.openai.com/community/codex-for-oss

Fields the form asks for:
- name + email associated with the ChatGPT account
- GitHub username
- repository URL (profile public, repo public)
- role: primary maintainer / core maintainer
- why the repo qualifies (max 500 chars)
- interest: Codex Security / API credits
- OpenAI Organization ID (org-... prefix, from platform.openai.com/settings/organization/general)
- how you will use API credits on the project (max 500 chars)
- anything else (max 500 chars)

No card, no payment, no Session token — the form itself only asks about the project.

## Draft: why this repository qualifies (<=500 chars)

```
local-llm-gateway is a public, MIT-licensed Python service that turns any local
model server (Strata/llama.cpp/vLLM/Ollama) into a single OpenAI-compatible
base_url for desktop clients. It resolves model aliases, forwards reasoning
effort at top level and inside chat_template_kwargs, relays SSE unbuffered,
and maps upstream failures to 502/504. Standard library only, no dependencies.
Users are people running self-hosted inference who need one endpoint for many
clients without cloud billing. I maintain it: I write the code, review diffs,
ship releases, and keep tests green (python3 test_gateway.py, 6 tests).
```

## Draft: how API credits will be used (<=500 chars)

```
Codex would review every pull request before merge: check the alias map, the
effort injection path, the SSE relay (no buffered Content-Length), and the
error mapping. It would also generate regression tests for streaming and
timeout paths, and check release notes against the README. That replaces the
manual first pass I do now on each diff and lets my review time go to the
protocol-level judgement only a maintainer can make.
```

## Draft: anything else (optional, <=500 chars)

```
The repo is small but real: 5 files, 6 passing tests, MIT license, one commit
per change. It exists because Claude-style gateways and Cherry Studio/Trae-style
clients speak OpenAI while local runtimes speak a slightly different shape.
```

## Honest caveat

- Approval is discretionary; OpenAI reviews applications on a rolling basis
  and picks projects itself. Filling the form guarantees nothing.
- No fixed star threshold is published, but an empty repo with no releases and
  no users is weak evidence. Keep the repo public, add a release tag, and let
  the commit history show real maintenance.
- Benefits are personal, non-transferable, not sellable.
