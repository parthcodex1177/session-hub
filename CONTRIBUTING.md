# Contributing to Session Hub

## Running locally

```bash
git clone https://github.com/parthcodex1177/session-hub.git
cd session-hub
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/session-hub          # start the server
```

## Tests

```bash
.venv/bin/python -m pytest tests/ -v
```

Tests use only `tmp_path` fixtures and never touch your real `~/.claude` or
`~/.gemini` data.

## Adding a new AI tool

1. Add paths to `sessionhub/config.py`.
2. Write a `parse_<tool>.py` that returns `list[SessionRecord]`.
3. Call it from `sessionhub/scanner.py` alongside the existing parsers.
4. Add tests in `tests/`.

## Code style

- Python 3.8+, no external type-checking deps required. Keep it 3.8-compatible:
  every module starts with `from __future__ import annotations`, and FastAPI
  route signatures use `typing.Optional[...]` (not `X | None`) because FastAPI
  resolves those annotations at runtime.
- Keep the frontend in vanilla JS + CSS (no build step).
- All dynamic HTML must pass through `esc()` (XSS guard).
- Security boundary: `resume.py` validates session IDs against strict UUID
  regex + DB existence before building any shell command. Never use
  `shell=True` or interpolate user input into shell strings.

## Reporting issues

Please include:
- OS and Python version.
- Which AI tool(s) you have installed.
- The relevant section of `~/.local/state/session-hub/app.log`.
