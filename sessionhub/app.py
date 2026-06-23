import argparse
import csv
import io
import json
import re
import subprocess
import threading
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .active import active_sessions
from .pricing import estimate_cost
from .resume import ResumeError, build_command, launch_terminal
from .scanner import scan

app = FastAPI(title="Session Hub")
_scan_lock = threading.Lock()

SORT_COLUMNS = {
    "started_at": "started_at",
    "ended_at": "ended_at",
    "title": "title",
    "project_name": "project_name",
    "message_count": "message_count",
    "total_tokens": "(input_tokens + output_tokens)",
}

_TAG_RE = re.compile(r'^[\w\s\-]{1,30}$')


def _connect():
    return db.connect()


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["models"] = json.loads(d["models"]) if d["models"] else []
    d["total_tokens"] = d["input_tokens"] + d["output_tokens"]
    return d


def _build_where(
    tool=None,
    project=None,
    model=None,
    q=None,
    date_from=None,
    date_to=None,
    include_empty=False,
    fts_ids: set | None = None,
):
    """Build (where_clauses, params) applying all standard session filters."""
    where = []
    params: list = []
    if tool:
        where.append("tool = ?")
        params.append(tool)
    if project:
        where.append("project_path = ?")
        params.append(project)
    if model:
        where.append(
            "EXISTS (SELECT 1 FROM json_each(sessions.models) WHERE value = ?)"
        )
        params.append(model)
    if q:
        like_q = f"%{q}%"
        if fts_ids:
            placeholders = ",".join("?" * len(fts_ids))
            where.append(
                f"(id IN ({placeholders}) OR title LIKE ? OR description LIKE ?)"
            )
            params += list(fts_ids) + [like_q, like_q]
        else:
            escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like = f"%{escaped}%"
            where.append(
                "(title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' OR EXISTS "
                "(SELECT 1 FROM prompts p WHERE p.session_id = sessions.id "
                "AND p.text LIKE ? ESCAPE '\\'))"
            )
            params += [like, like, like]
    if date_from:
        where.append("started_at >= ?")
        params.append(date_from)
    if date_to:
        where.append("started_at < ?")
        params.append(date_to + "~")
    if not include_empty:
        where.append("user_prompt_count > 0")
    return where, params


def _fts_lookup(con, q: str) -> set[str] | None:
    """Run FTS5 match, return set of session_ids or None on parse error."""
    if not q:
        return None
    try:
        rows = con.execute(
            "SELECT session_id FROM prompts_fts WHERE text MATCH ?", (q,)
        ).fetchall()
        return {row[0] for row in rows}
    except Exception:
        return None


@app.get("/api/sessions/export")
def export_sessions(
    format: str = Query("json", pattern="^(json|csv)$"),
    tool: str | None = None,
    project: str | None = None,
    model: str | None = None,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_empty: bool = False,
):
    con = _connect()
    try:
        fts_ids = _fts_lookup(con, q) if q else None
        where, params = _build_where(
            tool=tool,
            project=project,
            model=model,
            q=q,
            date_from=date_from,
            date_to=date_to,
            include_empty=include_empty,
            fts_ids=fts_ids,
        )
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        rows = con.execute(
            f"SELECT * FROM sessions {where_sql} ORDER BY ended_at DESC LIMIT 10000",
            params,
        ).fetchall()
    finally:
        con.close()

    items = [_row_to_dict(r) for r in rows]

    if format == "csv":
        output = io.StringIO()
        if items:
            writer = csv.DictWriter(output, fieldnames=list(items[0].keys()))
            writer.writeheader()
            writer.writerows(items)
        else:
            output.write("")
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="sessions.csv"'},
        )

    return Response(
        content=json.dumps(items, default=str),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="sessions.json"'},
    )


@app.get("/api/sessions")
def list_sessions(
    tool: str | None = None,
    project: str | None = None,
    model: str | None = None,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_empty: bool = False,
    sort: str = "ended_at",
    dir: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    con = _connect()
    try:
        fts_ids = _fts_lookup(con, q) if q else None
        where, params = _build_where(
            tool=tool,
            project=project,
            model=model,
            q=q,
            date_from=date_from,
            date_to=date_to,
            include_empty=include_empty,
            fts_ids=fts_ids,
        )
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        order_col = SORT_COLUMNS.get(sort, "ended_at")
        order_sql = f"ORDER BY {order_col} {'ASC' if dir == 'asc' else 'DESC'}"

        total = con.execute(
            f"SELECT count(*) AS c FROM sessions {where_sql}", params
        ).fetchone()["c"]
        rows = con.execute(
            f"SELECT * FROM sessions {where_sql} {order_sql} LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    finally:
        con.close()

    live = active_sessions()
    items = []
    for row in rows:
        d = _row_to_dict(row)
        d["is_active"] = d["id"] in live
        d["active_status"] = live.get(d["id"])
        items.append(d)
    return {"total": total, "items": items}


@app.get("/api/sessions/{session_id}/diff")
def session_diff(session_id: str):
    con = _connect()
    try:
        row = con.execute(
            "SELECT project_path, started_at, ended_at, git_branch "
            "FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    finally:
        con.close()

    if not row:
        raise HTTPException(404, "session not found")

    project_path = row["project_path"]
    started_at = row["started_at"]
    ended_at = row["ended_at"]

    if not project_path or not Path(project_path).is_dir():
        raise HTTPException(409, f"project_path not found or not a directory: {project_path!r}")

    cmd = ["git", "log", "--oneline"]
    if started_at:
        cmd += [f"--after={started_at}"]
    if ended_at:
        cmd += [f"--before={ended_at}"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
            cwd=project_path,
        )
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        if result.returncode != 0:
            return {"commits": [], "command": " ".join(cmd), "error": result.stderr.strip()}
        return {"commits": lines, "command": " ".join(cmd)}
    except FileNotFoundError:
        return {"commits": [], "command": " ".join(cmd), "error": "git not found"}
    except subprocess.TimeoutExpired:
        return {"commits": [], "command": " ".join(cmd), "error": "git command timed out"}
    except Exception as exc:
        return {"commits": [], "command": " ".join(cmd), "error": str(exc)}


@app.get("/api/sessions/{session_id}/tags")
def get_tags(session_id: str):
    con = _connect()
    try:
        if not con.execute(
            "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
        ).fetchone():
            raise HTTPException(404, "session not found")
        tags = [
            row["tag"]
            for row in con.execute(
                "SELECT tag FROM tags WHERE session_id = ? ORDER BY tag",
                (session_id,),
            )
        ]
    finally:
        con.close()
    return {"tags": tags}


@app.post("/api/sessions/{session_id}/tags")
def add_tag(session_id: str, body: dict):
    tag = (body.get("tag") or "").strip()
    if not tag:
        raise HTTPException(400, "tag must not be empty")
    if not _TAG_RE.match(tag):
        raise HTTPException(
            400,
            "tag must be 1-30 chars, alphanumeric, hyphen, or space only",
        )

    con = _connect()
    try:
        if not con.execute(
            "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
        ).fetchone():
            raise HTTPException(404, "session not found")
        con.execute(
            "INSERT OR IGNORE INTO tags(session_id, tag) VALUES (?,?)",
            (session_id, tag),
        )
        con.commit()
        tags = [
            row["tag"]
            for row in con.execute(
                "SELECT tag FROM tags WHERE session_id = ? ORDER BY tag",
                (session_id,),
            )
        ]
    finally:
        con.close()
    return {"tags": tags}


@app.delete("/api/sessions/{session_id}/tags/{tag}")
def delete_tag(session_id: str, tag: str):
    con = _connect()
    try:
        if not con.execute(
            "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
        ).fetchone():
            raise HTTPException(404, "session not found")
        con.execute(
            "DELETE FROM tags WHERE session_id = ? AND tag = ?",
            (session_id, tag),
        )
        con.commit()
        tags = [
            row["tag"]
            for row in con.execute(
                "SELECT tag FROM tags WHERE session_id = ? ORDER BY tag",
                (session_id,),
            )
        ]
    finally:
        con.close()
    return {"tags": tags}


@app.get("/api/sessions/{session_id}")
def session_detail(session_id: str):
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "session not found")
        prompts = [
            dict(p)
            for p in con.execute(
                "SELECT seq, ts, text FROM prompts WHERE session_id = ? ORDER BY seq",
                (session_id,),
            )
        ]
    finally:
        con.close()
    d = _row_to_dict(row)
    d["prompts"] = prompts
    live = active_sessions()
    d["is_active"] = session_id in live
    d["active_status"] = live.get(session_id)
    try:
        d["resume_command"] = build_command(row)
    except ResumeError as exc:
        d["resume_command"] = None
        d["resume_blocked_reason"] = exc.detail
    return d


@app.get("/api/stats")
def stats(date_from: str | None = None, date_to: str | None = None):
    where = ["user_prompt_count > 0"]
    params: list = []
    if date_from:
        where.append("started_at >= ?")
        params.append(date_from)
    if date_to:
        where.append("started_at < ?")
        params.append(date_to + "~")
    where_sql = "WHERE " + " AND ".join(where)

    con = _connect()
    try:
        per_day: dict[str, dict] = {}
        for row in con.execute(
            f"SELECT date(started_at, 'localtime') AS d, tool, count(*) AS c "
            f"FROM sessions {where_sql} GROUP BY d, tool ORDER BY d",
            params,
        ):
            entry = per_day.setdefault(
                row["d"], {"date": row["d"], "claude": 0, "antigravity": 0}
            )
            entry[row["tool"]] = row["c"]

        per_project = [
            dict(r)
            for r in con.execute(
                f"SELECT coalesce(project_name, '(unknown)') AS name, count(*) AS count, "
                f"sum(input_tokens + output_tokens) AS tokens "
                f"FROM sessions {where_sql} GROUP BY name ORDER BY count DESC",
                params,
            )
        ]
        per_model = [
            dict(r)
            for r in con.execute(
                f"SELECT je.value AS model, count(*) AS count, "
                f"sum(input_tokens + output_tokens) AS tokens "
                f"FROM sessions, json_each(sessions.models) je {where_sql} "
                f"GROUP BY je.value ORDER BY count DESC",
                params,
            )
        ]
        tokens_per_day = [
            dict(r)
            for r in con.execute(
                f"SELECT date(started_at, 'localtime') AS date, sum(input_tokens) AS input, "
                f"sum(output_tokens) AS output FROM sessions {where_sql} "
                f"GROUP BY date ORDER BY date",
                params,
            )
        ]
        totals = dict(
            con.execute(
                f"SELECT count(*) AS sessions, sum(user_prompt_count) AS prompts, "
                f"sum(input_tokens) AS input_tokens, sum(output_tokens) AS output_tokens, "
                f"count(DISTINCT project_path) AS projects FROM sessions {where_sql}",
                params,
            ).fetchone()
        )
        projects = [
            r["project_path"]
            for r in con.execute(
                "SELECT DISTINCT project_path FROM sessions "
                "WHERE project_path IS NOT NULL ORDER BY project_path"
            )
        ]
        last_scan = db.get_meta(con, "last_scan_at")

        # Tags: distinct tags with counts
        tag_rows = con.execute(
            "SELECT tag, count(*) AS count FROM tags GROUP BY tag ORDER BY count DESC"
        ).fetchall()
        tags_list = [{"tag": r["tag"], "count": r["count"]} for r in tag_rows]

        # Cost per day and total cost
        cost_rows = con.execute(
            f"SELECT date(started_at, 'localtime') AS d, "
            f"models, input_tokens, output_tokens "
            f"FROM sessions {where_sql} ORDER BY d",
            params,
        ).fetchall()

        cost_per_day_map: dict[str, float] = {}
        total_cost = 0.0
        for r in cost_rows:
            models = json.loads(r["models"]) if r["models"] else []
            cost = estimate_cost(r["input_tokens"] or 0, r["output_tokens"] or 0, models)
            if cost is None:
                continue
            d = r["d"] or "unknown"
            cost_per_day_map[d] = cost_per_day_map.get(d, 0.0) + cost
            total_cost += cost

        cost_per_day = [
            {"date": d, "cost": round(c, 6)}
            for d, c in sorted(cost_per_day_map.items())
        ]
    finally:
        con.close()

    return {
        "per_day": list(per_day.values()),
        "per_project": per_project,
        "per_model": per_model,
        "tokens_per_day": tokens_per_day,
        "totals": totals,
        "projects": projects,
        "last_scan_at": last_scan,
        "tags": tags_list,
        "cost_per_day": cost_per_day,
        "total_cost": round(total_cost, 6),
    }


@app.post("/api/scan")
def trigger_scan():
    if not _scan_lock.acquire(blocking=False):
        return JSONResponse({"detail": "scan already in progress"}, status_code=409)
    try:
        con = _connect()
        try:
            summary = scan(con)
        finally:
            con.close()
        return summary.as_dict()
    finally:
        _scan_lock.release()


def _get_session_row(session_id: str):
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    finally:
        con.close()
    if not row:
        raise HTTPException(404, "session not found")
    return row


@app.get("/api/resume/{session_id}/command")
def resume_command(session_id: str):
    row = _get_session_row(session_id)
    try:
        return {"command": build_command(row)}
    except ResumeError as exc:
        raise HTTPException(exc.status, exc.detail)


@app.post("/api/resume/{session_id}")
def resume_session(session_id: str):
    row = _get_session_row(session_id)
    try:
        terminal = launch_terminal(row)
    except ResumeError as exc:
        raise HTTPException(exc.status, exc.detail)
    return {"ok": True, "terminal_used": terminal}


app.mount(
    "/",
    StaticFiles(directory=Path(__file__).parent / "static", html=True),
    name="static",
)


def main():
    parser = argparse.ArgumentParser(description="Session Hub dashboard")
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument(
        "--scan-only", action="store_true", help="run a scan, print summary, exit"
    )
    args = parser.parse_args()

    if args.scan_only:
        con = db.connect()
        try:
            summary = scan(con)
        finally:
            con.close()
        print(json.dumps(summary.as_dict(), indent=2))
        return

    con = db.connect()
    try:
        scan(con)  # initial index so the first page load is populated
    finally:
        con.close()

    import uvicorn

    print(f"Session Hub: http://{config.HOST}:{args.port}/")
    uvicorn.run(app, host=config.HOST, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
