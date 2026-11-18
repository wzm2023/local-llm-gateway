# Contributing

Small project, few rules.

## What counts as a real contribution

- Fix a bug (with a test that fails before and passes after).
- Add a feature that the README does **not** already claim (e.g. a new alias
  resolution rule, a retry policy, a different error mapping).
- Improve robustness (timeouts, partial reads, proxy handling).

## What does not count

- Whitespace-only diffs.
- Renaming files.
- Rewriting the README with no code change.

## How to run things

```bash
python3 gateway.py --config config.example.json --self-check
python3 test_gateway.py
```

## Style

- Standard library only. No new runtime dependencies.
- Keep `DEFAULT_CONFIG` authoritative; unknown keys are rejected.
- Add a test for every behaviour you add.

## Pull requests

Describe the behaviour change, not the diff. Say what failed before and what
now passes.
