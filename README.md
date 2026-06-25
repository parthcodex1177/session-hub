# Session Hub

[![CI](https://github.com/parthcodex1177/session-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/parthcodex1177/session-hub/actions/workflows/ci.yml)

A local dashboard for **Claude Code** and **Antigravity CLI** session history.

Browse every past session, search your full prompt history with FTS, see token
usage and estimated API cost, tag important sessions, and resume old work —
all from a native desktop window or browser tab.

![Sessions view](assets/screenshot-sessions.png)

> _Activity tab — usage and cost analytics:_
>
> ![Activity view](assets/screenshot-activity.png)
>
> _(Screenshots use sample data.)_

---

## Features

| Feature | Detail |
|---|---|
| Unified history | Claude Code + Antigravity indexed into one SQLite DB |
| Full-text search | FTS5 on every prompt — find "where did I fix that N+1 query" |
| Token → cost | Estimated API cost per session (Claude Opus/Sonnet/Haiku, Gemini families) |
| Session tagging | Tag sessions "important", "reference", etc. — filterable |
| Inline detail | Click a row to expand prompts, metadata, git commits — no navigation |
| Git diff view | Commits that landed during a session (lazy-loaded from `git log`) |
| Live badge | Green pulsing dot for sessions running right now; auto-refreshes every 30s |
| Resume | ▶ opens a terminal with `claude --resume <id>` or `agy --conversation <id>` |
| Export | Download filtered results as JSON or CSV |
| Activity charts | Sessions/day, per project, per model, tokens/day, estimated cost/day |
| Light / dark | Theme toggle, persisted in localStorage |
| Incremental scan | Only re-parses changed files (~80 ms warm) |

---

## Requirements

| | Linux | macOS | Windows |
|---|---|---|---|
| Python | 3.8+ | 3.8+ | 3.8+ |
| Native window | GTK3 + WebKit2GTK (`gir1.2-webkit2-4.0`/`4.1`) — **auto-installed** | built-in WKWebView | Edge WebView2 (Win 10/11) |
| Browser mode | ✅ any browser | ✅ any browser | ✅ any browser |
| Claude Code | optional | optional | optional |
| Antigravity CLI | optional | optional | optional |

---

## Install

### Recommended: one command (installs, adds menu icon, and updates)

This installs pipx if needed, installs Session Hub from GitHub, and registers
**Session Hub** in your application / start menu — all at once. **Run the exact
same command again any time to update** to the latest version:

```bash
curl -fsSL https://raw.githubusercontent.com/parthcodex1177/session-hub/main/install-pipx.sh | bash
```

Then launch **Session Hub** from your app menu (on GNOME, if it doesn't appear
immediately, press **Alt+F2 → `r` → Enter** once, or log out/in), or run
`session-hub` in a terminal. It runs on **any Python 3.8+** — including the
Python already on Ubuntu 20.04+, Debian 11+, and macOS.

Remove it with `pipx uninstall session-hub` and `session-hub --uninstall-desktop`.

### Manual pipx (same thing, step by step)

```bash
python3 -m pip install --user pipx && python3 -m pipx ensurepath
pipx install "git+https://github.com/parthcodex1177/session-hub.git"
session-hub --install-desktop      # add the app-menu icon (Linux)
session-hub                        # or just run it in your browser
```

Update with `pipx install --force "git+https://github.com/parthcodex1177/session-hub.git"`.

> The menu icon launches **browser mode** (the dashboard opens in your default
> browser). A true native desktop window needs the system GTK/WebKit libraries,
> which an isolated pipx environment can't use — for that, use the Linux native
> app install below (git clone + `install-app.sh`).

### Alternative: prebuilt binary (no Python at all)

If you'd rather not install Python or pipx, grab the self-contained binary —
it bundles its own Python and runs on any Linux with glibc 2.28+ (Ubuntu 20.04
and newer):

```bash
curl -fsSL https://raw.githubusercontent.com/parthcodex1177/session-hub/main/install.sh | bash
```

Or download a single file from the
[**Releases**](https://github.com/parthcodex1177/session-hub/releases) page:

| OS | Asset |
|---|---|
| Linux (x86_64) | `session-hub-linux-x86_64` |
| macOS (Apple Silicon) | `session-hub-macos-arm64` |
| Windows (x86_64) | `session-hub-windows-x86_64.exe` |

```bash
chmod +x session-hub-linux-x86_64 && ./session-hub-linux-x86_64
```

### Linux (Ubuntu / Debian) — native app

```bash
git clone https://github.com/parthcodex1177/session-hub.git ~/tools/session-hub
~/tools/session-hub/install-app.sh
```

Adds **Session Hub** to the GNOME app grid and a `session-hub` command on PATH.
Search it in Activities or pin it to the dock.

The installer **auto-detects and installs** the native-window libraries
(PyGObject + GTK3 + WebKit2GTK — the right `gir1.2-webkit2-4.0`/`4.1` for your
release), prompting for your password if needed. Re-running `install-app.sh`
after `git pull` re-checks them, so updates stay self-healing. If you launch
from the GNOME icon on a fresh machine and the libs are missing, run
`session-hub` once in a terminal so it can install them.

Uninstall: `~/tools/session-hub/install-app.sh --uninstall`

### macOS — native app

```bash
git clone https://github.com/parthcodex1177/session-hub.git ~/tools/session-hub
~/tools/session-hub/run.sh --app
```

The first run creates a venv and installs pywebview (which uses the system
WKWebView — no extra installs needed). For a permanent launcher, create an
Automator app or alias: `alias session-hub='~/tools/session-hub/run.sh --app'`.

### Windows — native app

```
git clone https://github.com/parthcodex1177/session-hub.git %USERPROFILE%\tools\session-hub
%USERPROFILE%\tools\session-hub\install.bat
```

Creates a Desktop shortcut. Requires Edge WebView2 Runtime, which ships with
Windows 10 (1803+) and Windows 11.

### Any platform — browser mode

```bash
~/tools/session-hub/run.sh           # http://127.0.0.1:8788/
~/tools/session-hub/run.sh --port 9000
~/tools/session-hub/run.sh --scan-only   # index only, print summary
SESSION_HUB_PORT=9000 session-hub    # via installed command
```

---

## Data sources (read-only)

Session Hub **never writes** to your Claude or Antigravity data.

| Tool | Files read |
|---|---|
| Claude Code | `~/.claude/projects/*/*.jsonl`<br>`~/.claude/history.jsonl`<br>`~/.claude/sessions/*.json` (live status) |
| Antigravity | `~/.gemini/antigravity-cli/history.jsonl`<br>`~/.gemini/antigravity-cli/conversations/*.db` (model + step count) |

Index: `~/.local/share/session-hub/index.db` (Linux/macOS) or
`%LOCALAPPDATA%\session-hub\index.db` (Windows, if configured).

---

## Cost estimates

The **~$x.xx** figures use public API list prices and exclude cached tokens.
They are a ballpark, not a billing figure.

---

## Development

```bash
git clone https://github.com/parthcodex1177/session-hub.git
cd session-hub
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest tests/ -v
.venv/bin/session-hub          # start server at http://127.0.0.1:8788/
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for architecture notes.

---

## Documentation

- **[USAGE.md](USAGE.md)** — how to use every feature, keyboard shortcuts, troubleshooting
- **[FEATURES.md](FEATURES.md)** — complete feature reference
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — architecture and how to add a new tool

---

## License

MIT — see [LICENSE](LICENSE).
