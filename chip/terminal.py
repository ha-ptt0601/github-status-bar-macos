"""Open a shell command in a new Terminal.app or iTerm window via osascript."""
from __future__ import annotations

import os
import shlex
import subprocess
from typing import Mapping, Optional, Tuple

SCRIPTS = {
    "Terminal": ('tell application "Terminal"\n activate\n do script "{cmd}"\n'
                 ' set bounds of front window to {{80, 60, 1580, 960}}\nend tell'),
    "iTerm": 'tell application "iTerm"\n activate\n create window with default profile command "{cmd}"\nend tell',
}
TERM_PROGRAM_APP = {"Apple_Terminal": "Terminal", "iTerm.app": "iTerm"}


def _applescript(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def pick_app(configured: str, env: Optional[Mapping[str, str]] = None) -> str:
    """The terminal chip is running in (when known), else the configured one."""
    env = os.environ if env is None else env
    return TERM_PROGRAM_APP.get(env.get("TERM_PROGRAM", ""), configured)


def open_command(command: str, app: str, runner=None) -> Tuple[bool, str]:
    runner = runner or subprocess.run
    script = SCRIPTS.get(app)
    if script is None:
        return False, f"unsupported terminal app: {app}"
    if app == "iTerm":  # iTerm runs `command` without a shell
        command = "/bin/zsh -lc " + shlex.quote(command)
    proc = runner(["osascript", "-e", script.format(cmd=_applescript(command))], capture_output=True, text=True)
    return proc.returncode == 0, (proc.stderr or "").strip()
