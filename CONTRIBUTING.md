# Contributing to Session Hub

## Running locally

```bash
git clone https://github.com/your-username/session-hub.git
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

- Python 3.10+, no external type-checking deps required.
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
