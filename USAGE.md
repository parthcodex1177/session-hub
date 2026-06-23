# Session Hub — Usage Guide

## Launching

| How | Command |
|---|---|
| Installed app (Linux) | Search **Session Hub** in Activities, or run `session-hub` |
| Native window, no install | `~/tools/session-hub/run.sh --app` |
| Browser tab | `~/tools/session-hub/run.sh` → open http://127.0.0.1:8788/ |
| Clean restart after upgrade | `~/tools/session-hub/session-hub-launch.sh --restart` |

## The Sessions tab

The main table lists every indexed session, newest activity first.

- **Search** — type in the search box (or press `/`). It matches session
  titles, descriptions, and the full text of every prompt.
- **Filter** — use the dropdowns (tool / project / model / tag) and the date
  range. Filters combine (AND).
- **Sort** — click a column header (Title, Project, Started, Last activity,
  Msgs, Tokens). Click again to reverse.
- **Show empty** — tick to include sessions with no user prompts.
- **Open a session** — click the row. It expands inline to show the full
  description, metadata, prompt timeline, and git commits from that session.
  Press `Esc` or click the row again to collapse.

## Resuming a session

In a row's **Actions** column or the expanded panel:
- **▶ Resume session** — opens a terminal in the session's project directory
  and resumes it (`claude --resume` / `agy --conversation`).
- **⧉ Copy command** — copies the resume command to your clipboard.

If a session can't be resumed (e.g. its project folder was deleted) the button
is disabled and shows the reason on hover.

## Tagging

Open a session, then in the **Tags** row:
- Type a tag and click **Add** (or press Enter).
- Click the **✕** on a chip to remove it.
- Filter the whole list to a tag using the **All tags** dropdown.

## Exporting

Click **↓ Export** in the toolbar and choose **JSON** or **CSV**. The export
contains exactly the sessions matching your current filters.

## The Activity tab

Shows totals and charts across all sessions (respecting the date range):
sessions per day by tool, per project, per model, tokens per day, and
estimated cost per day, plus summary cards including estimated total cost.

## Refreshing the index

Click **⟳ Refresh** to rescan. Only files changed since the last scan are
re-parsed, so it's fast. Live sessions also auto-refresh every 30 seconds.

## Keyboard shortcuts

| Key | Action |
|---|---|
| `/` | Focus the search box |
| `Esc` | Collapse the open session row |

## Theme

Click the ☀ / ☾ button in the header to switch between dark and light. Your
choice is remembered across restarts.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Changes/fixes not showing after an upgrade | `session-hub-launch.sh --restart` (a stale instance may be holding the window) |
| "Failed to start" notification | Check `~/.local/state/session-hub/app.log` |
| Native window won't open on Linux | Install WebKit2GTK: `sudo apt install gir1.2-webkit2-4.1` |
| No data on first run | Click **⟳ Refresh**; ensure you have Claude Code or Antigravity history |
| Inspect errors | In the native window, right-click → Inspect → Console |
