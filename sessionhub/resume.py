"""Build resume commands and launch them in a new terminal window."""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

# (binary, args-prefix before the bash command)
TERMINALS = [
    ("gnome-terminal", ["--"]),
    ("x-terminal-emulator", ["-e"]),
    ("konsole", ["-e"]),
    ("xfce4-terminal", ["-e"]),
    ("kitty", []),
    ("xterm", ["-e"]),
]


class ResumeError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def build_command(row) -> str:
    """row: sessions table row. Returns the shell command a human would run."""
    if not UUID_RE.match(row["id"]):
        raise ResumeError(400, "invalid session id")
    project = row["project_path"]
    if not project:
        raise ResumeError(409, "session has no known project directory")
    if row["tool"] == "claude":
        return f"cd {shlex.quote(project)} && claude --resume {row['id']}"
    return f"cd {shlex.quote(project)} && agy --conversation {row['id']}"


def launch_terminal(row) -> str:
    """Open a terminal running the resume command. Returns terminal used."""
    command = build_command(row)
    if not os.path.isdir(row["project_path"]):
        raise ResumeError(409, "project directory no longer exists")
    inner = f"{command}; exec bash"
    for binary, prefix in TERMINALS:
        if shutil.which(binary):
            argv = [binary, *prefix, "bash", "-c", inner]
            subprocess.Popen(
                argv,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return binary
    raise ResumeError(500, "no supported terminal emulator found")
