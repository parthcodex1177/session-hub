# Session Hub — Features

A complete reference of everything Session Hub does.

## Session browsing
- **Unified history** — indexes both **Claude Code** (`~/.claude/`) and
  **Antigravity CLI** (`~/.gemini/antigravity-cli/`) into one view.
- **Rich table** — tool badge, title, description, project, model(s), started,
  last activity (relative), message count, tokens in/out, status, actions.
- **Sortable columns** — title, project, started, last activity, messages,
  tokens. Click a header to toggle ascending / descending.
- **Pagination** — 50 per page with Prev / Next.
- **Live "running" badge** — a green pulsing pill marks sessions active right
  now, detected from pid files plus a `/proc` liveness check.
- **Auto-refresh** — while any session is live, the list silently refreshes
  every 30 seconds.
- **Loading & empty states** — shimmer skeleton rows while loading and a
  friendly panel when nothing matches.

## Search & filtering
- **Full-text search (FTS5)** — searches the full text of every prompt, not
  just titles/descriptions. Falls back to a LIKE search if the query contains
  FTS special syntax.
- **Filters** — tool, project, model, tag, and a compact start-date range.
- **Show empty** — include sessions that recorded zero user prompts.
- **Keyboard** — `/` focuses the search box, `Esc` collapses an open row.

## Expandable detail (inline accordion)
Click a row to expand it in place (one open at a time):
- Full, untruncated **description**.
- **Metadata grid** — session ID, project path, git branch, model(s), CLI
  version, start / last-activity timestamps, message & prompt counts, tokens
  in/out, cache create/read tokens, estimated cost, source file path.
- **Prompt timeline** — every recorded prompt with timestamps (lazy-loaded).
- **Git commits during the session** — runs `git log` scoped to the session's
  time window in the project directory (lazy-loaded; shows an error inline if
  the directory is gone or git is unavailable).

## Tags
- Add / remove tags per session from the detail panel.
- Tag chips appear on each row.
- Filter the whole list by a tag.
- Tag values are validated (1–30 chars; letters, digits, hyphen, space).

## Cost & token tracking
- **Per-session cost estimate** (`~$x.xx`) shown under the token cell and in
  the detail grid.
- Pricing tiers: Claude **Opus / Sonnet / Haiku** and **Gemini 2.x / 3.x**
  families. Cache tokens are excluded — it is a ballpark, not a bill.
- Sessions whose model has no known price show `—`.

## Activity tab
- **Stat cards** — sessions, prompts, projects, input tokens, output tokens,
  estimated total cost.
- **Charts** — sessions per day (stacked by tool), sessions per project,
  sessions per model (doughnut), tokens per day, estimated cost per day.

## Resume
- **Resume session** — opens a terminal in the project directory running
  `claude --resume <id>` (Claude) or `agy --conversation <id>` (Antigravity).
- **Copy command** — copies that command to the clipboard.
- Disabled with an explanation when a session isn't resumable.

## Export
- Export the **currently filtered** result set as **JSON** or **CSV**.

## Appearance
- **Light / dark theme** toggle, persisted across restarts.
- Sticky app header and table header while scrolling.
- Status pills, gradient wordmark, hover states, and transitions.
- Tooltips on icon buttons.

## Platforms
- **Native desktop window** (no browser) via pywebview:
  - Linux — GTK + WebKit2GTK
  - macOS — WKWebView
  - Windows — Edge WebView2
- **Browser mode** on any OS.
- **Single instance** with `--restart` for clean upgrades.

## Under the hood
- **Incremental scanning** — only changed files are re-parsed (~80 ms warm).
- **SQLite index** with automatic schema migrations.
- **No-cache headers** so in-place upgrades always load fresh code.
- **Read-only** — never writes to your Claude / Antigravity data.
- **Security** — bound to 127.0.0.1 only, parameterized SQL everywhere,
  strict UUID validation before any resume command, no `shell=True`.
- **Tested** — pytest suite + GitHub Actions CI on Python 3.8 / 3.10 / 3.12.
