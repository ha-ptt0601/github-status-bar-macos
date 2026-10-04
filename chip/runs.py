"""Background reviews started by chip (`claude "<prompt>" --bg`), recorded in runs.json."""
from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from chip import config, model

BG_ID_RE = re.compile(r"backgrounded · ([0-9a-f]{6,})")
KINDS = {"working": "running", "blocked": "needs_you", "done": "done"}
ROUND_NOTE = (" — round {n}: re-review this PR. First check whether each finding from round {prev} was addressed "
              "(fixed, answered, or still open), then review only what changed since round {prev}.")


class RunError(RuntimeError):
    pass


def run_key(label: str, skill_name: str) -> str:
    return f"{label}::{skill_name}"


def load(path) -> Dict[str, dict]:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


def save(path, records: Dict[str, dict]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(records, ensure_ascii=False, indent=1))


def build_command(prompt: str, label: str, skill_name: str, cfg: dict) -> List[str]:
    # The prompt must come first: --disallowedTools is variadic and would swallow a trailing prompt.
    cmd = ["claude", prompt, "--bg", "--name", f"chip · {label} · {skill_name}",
           "--permission-mode", cfg["permission_mode"]]
    if cfg["disallowed_tools"]:
        cmd += ["--disallowedTools", ",".join(cfg["disallowed_tools"])]
    return cmd


def parse_bg_id(stdout: str) -> Optional[str]:
    match = BG_ID_RE.search(stdout or "")
    return match.group(1) if match else None


def start(row: dict, skill: dict, cfg: dict, cwd: str, path, runner=None,
          now: Callable[[], float] = time.time) -> dict:
    """Round 1 starts a new background session; later rounds continue the same session."""
    runner = runner or subprocess.run
    key = run_key(row["label"], skill["name"])
    records = load(path)
    previous = records.get(key)
    prompt = config.fill_prompt(skill, row)
    if previous and previous.get("session_id"):
        number = previous.get("round", 1) + 1
        runner(["claude", "stop", previous["id"]], capture_output=True, text=True)
        # No other flags: a background session keeps its saved name, permission mode and disallowed tools;
        # passing flags would fork a copy instead of continuing it.
        cmd = ["claude", prompt + ROUND_NOTE.format(n=number, prev=number - 1),
               "--resume", previous["session_id"], "--bg"]
        history = previous.get("history", []) + [{
            "round": previous.get("round", 1), "started_at": previous["started_at"],
            "done_at": previous.get("done_at"), "resolved_at": previous.get("resolved_at"),
            "resolved_by": previous.get("resolved_by"),
        }]
    else:
        number, history = 1, []
        cmd = build_command(prompt, row["label"], skill["name"], cfg)
    proc = runner(cmd, cwd=cwd, capture_output=True, text=True)
    run_id = parse_bg_id(proc.stdout)
    if proc.returncode != 0 or not run_id:
        raise RunError((proc.stderr or proc.stdout or "claude --bg failed").strip())
    record = {"id": run_id, "session_id": previous.get("session_id") if number > 1 else None,
              "label": row["label"], "title": row["title"], "url": row["url"], "repo": row["repo"],
              "skill": skill["name"], "cwd": cwd, "round": number, "history": history, "started_at": now()}
    records[key] = record
    save(path, records)
    return record


def fetch_agents(runner=None) -> Dict[str, dict]:
    runner = runner or subprocess.run
    try:
        proc = runner(["claude", "agents", "--json", "--all"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if proc.returncode != 0:
        return {}
    try:
        return {agent["id"]: agent for agent in json.loads(proc.stdout) if agent.get("id")}
    except (ValueError, TypeError, AttributeError):
        return {}


def format_elapsed(seconds: float) -> str:
    minutes = max(1, int(seconds) // 60)
    return f"{minutes}m" if minutes < 60 else f"{minutes // 60}h{minutes % 60:02d}m"


def view(record: dict, agent: Optional[dict], now: float) -> dict:
    if agent is None:
        return {"kind": "gone", "text": "session gone"}
    state = agent.get("state") or ""
    kind = KINDS.get(state, "other")
    if kind == "running":
        text = f"running {format_elapsed(now - record['started_at'])}"
    elif kind == "needs_you":
        text = "needs you"
    elif kind == "done":
        text = "done " + datetime.fromtimestamp(record.get("done_at", now)).strftime("%H:%M")
    else:
        text = state or agent.get("status", "?")
    return {"kind": kind, "text": text}


def observe(records: Dict[str, dict], agents: Dict[str, dict], now: float) -> bool:
    """Stamp `done_at` the first time a run is seen done (cleared if it resumes); True if changed."""
    changed = False
    for record in records.values():
        agent = agents.get(record["id"])
        if not agent:
            continue
        if agent.get("sessionId") and record.get("session_id") != agent["sessionId"]:
            record["session_id"] = agent["sessionId"]
            changed = True
        if agent.get("state") == "done" and "done_at" not in record:
            record["done_at"] = now
            changed = True
        elif agent.get("state") != "done" and "done_at" in record:
            del record["done_at"]
            changed = True
    return changed


def _after(iso: Optional[str], epoch: float) -> bool:
    return bool(iso) and model.parse_ts(iso).timestamp() > epoch


def resolve(records: Dict[str, dict], rows_by_label: Dict[str, dict], now: float) -> bool:
    """Mark finished rounds resolved once GitHub shows the user's review or newer commits; True if changed."""
    changed = False
    for record in records.values():
        row = rows_by_label.get(record["label"])
        if row is None or "done_at" not in record or record.get("resolved_at"):
            continue
        if _after(row.get("my_review_at"), record["started_at"]):
            record.update(resolved_at=now, resolved_by="you reviewed on GitHub")
        elif _after(row.get("last_commit_at"), record["started_at"]):
            record.update(resolved_at=now, resolved_by="new commits")
        else:
            continue
        changed = True
    return changed


def find_by_id(records: Dict[str, dict], run_id: str) -> Optional[Tuple[str, dict]]:
    return next(((key, rec) for key, rec in records.items() if rec.get("id") == run_id), None)
