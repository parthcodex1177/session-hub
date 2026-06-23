import argparse
import json
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .active import active_sessions
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


def _connect():
    return db.connect()


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["models"] = json.loads(d["models"]) if d["models"] else []
    d["total_tokens"] = d["input_tokens"] + d["output_tokens"]
    return d


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
        where.append(
            "(title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' OR EXISTS "
            "(SELECT 1 FROM prompts p WHERE p.session_id = sessions.id "
            "AND p.text LIKE ? ESCAPE '\\'))"
        )
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        params += [like, like, like]
    if date_from:
        where.append("started_at >= ?")
        params.append(date_from)
    if date_to:
        where.append("started_at < ?")
        params.append(date_to + "~")  # '~' > any time suffix → inclusive day
    if not include_empty:
        where.append("user_prompt_count > 0")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    order_col = SORT_COLUMNS.get(sort, "ended_at")
    order_sql = f"ORDER BY {order_col} {'ASC' if dir == 'asc' else 'DESC'}"

    con = _connect()
    try:
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
