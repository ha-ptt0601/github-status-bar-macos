"""Background reviews started by chip (`claude "<prompt>" --bg`), recorded in runs.json."""
from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from chip import config, files, model

BG_ID_RE = re.compile(r"backgrounded · ([0-9a-f]{6,})")
KINDS = {"working": "running", "blocked": "needs_you", "done": "done"}
# Address runs only propose fixes and draft replies: never commit, push or post to GitHub.
ADDRESS_DENY = ["Bash(git commit:*)", "Bash(git push:*)", "Bash(gh pr comment:*)", "Bash(gh pr review:*)"]
# User messages that Claude Code writes itself (not typed): task results, sub-agent hand-backs, command output.
AUTOMATIC = ("<task-notification>", "Another Claude session sent a message", "<local-command", "<system-reminder>",
             "Caveat:")
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
    files.write_atomic(Path(path), json.dumps(records, ensure_ascii=False, indent=1))


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
          now: Callable[[], float] = time.time, address: bool = False, extra: Optional[dict] = None,
          resume: Optional[str] = None) -> dict:
    """Round 1 starts a new background session, or continues the session `resume` (e.g. the one where the
    feature was built); later rounds continue the same session."""
    runner = runner or subprocess.run
    key = run_key(row["label"], skill["name"])
    records = load(path)
    previous = records.get(key)
    prompt = config.fill_prompt(skill, row)
    if (previous and previous.get("session_id")) or resume:
        previous = previous if previous and previous.get("session_id") else None
        number = previous.get("round", 1) + 1 if previous else 1
        if previous is None:
            previous = {"session_id": resume, "id": "", "round": 0, "started_at": now()}
        if previous["id"]:
            runner(["claude", "stop", previous["id"]], capture_output=True, text=True)
        # No other flags: a background session keeps its saved name, permission mode and disallowed tools;
        # passing flags would fork a copy instead of continuing it.
        note = ROUND_NOTE.format(n=number, prev=number - 1) if number > 1 else ""
        cmd = ["claude", prompt + note, "--resume", previous["session_id"], "--bg"]
        history = previous.get("history", []) + ([{
            "round": previous.get("round", 1), "started_at": previous["started_at"],
            "done_at": previous.get("done_at"), "resolved_at": previous.get("resolved_at"),
            "resolved_by": previous.get("resolved_by"),
        }] if number > 1 else [])
    else:
        number, history = 1, []
        if address:
            cfg = dict(cfg, disallowed_tools=list(cfg["disallowed_tools"]) + ADDRESS_DENY)
        cmd = build_command(prompt, row["label"], skill["name"], cfg)
    proc = runner(cmd, cwd=cwd, capture_output=True, text=True)
    run_id = parse_bg_id(proc.stdout)
    if proc.returncode != 0 or not run_id:
        raise RunError((proc.stderr or proc.stdout or "claude --bg failed").strip())
    record = {"id": run_id, "session_id": previous.get("session_id") if previous else None,
              "label": row["label"], "title": row["title"], "url": row["url"], "repo": row["repo"],
              "skill": skill["name"], "kind": "address" if address else "review", "cwd": cwd,
              "round": number, "history": history, "started_at": now(), **(extra or {})}
    records[key] = record
    save(path, records)
    return record


def relabel(records: Dict[str, dict], rows_by_label: Dict[str, dict]) -> bool:
    """A PR's label can change (e.g. `api#7` → `acme/api#7` when another owner's `api` shows up): follow it
    by URL, so the review is not taken for a closed PR. True if any record moved."""
    by_url = {r["url"]: r for r in rows_by_label.values() if r.get("url")}
    changed = False
    for key, record in list(records.items()):
        row = by_url.get(record.get("url"))
        if row and record["label"] != row["label"]:
            record["label"] = row["label"]
            del records[key]
            records[run_key(row["label"], record["skill"])] = record
            changed = True
    return changed


def clean_worktrees(records: Dict[str, dict], runner=None) -> bool:
    """Remove the PR worktree of project-skill runs whose PR was merged or closed; True if any changed."""
    from chip import project
    changed = False
    for record in records.values():
        if record.get("worktree") and record.get("resolved_by") == "PR merged or closed":
            number = record["label"].rsplit("#", 1)[-1]
            project.remove(record["clone"], record["worktree"], number, runner)
            record.pop("worktree")
            changed = True
    return changed


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
    kind = "done" if "done_at" in record else KINDS.get(state, "other")  # chatting in it later is not a review
    if kind == "running":
        text = f"running {format_elapsed(now - record['started_at'])}"
    elif kind == "needs_you":
        text = "needs you"
    elif kind == "done":
        text = "done " + datetime.fromtimestamp(record.get("done_at", now)).strftime("%H:%M")
    else:
        text = state or agent.get("status", "?")
    return {"kind": kind, "text": text}


def transcript(session_id: str) -> Optional[Path]:
    from chip import sessions
    return next(sessions.projects_dir().glob(f"*/{session_id}.jsonl"), None)


def _typed(entry: dict) -> bool:
    """A prompt someone typed (chip's review prompt or the user's own), not one Claude Code wrote."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return False
    content = entry.get("message", {}).get("content")
    return isinstance(content, str) and not content.startswith(AUTOMATIC)


def finished_before_follow_up(path: Optional[Path], started_at: float) -> Optional[float]:
    """When the user typed in a review's session after chip's prompt, the review had finished: the end of the
    last turn before that message (or the message's time). None while nobody has typed after chip."""
    if not path:
        return None
    prompts: List[float] = []
    ends: List[float] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if '"user"' not in line and '"turn_duration"' not in line:  # skip parsing the rest
                    continue
                try:
                    entry = json.loads(line)
                    stamp = model.parse_ts(entry["timestamp"]).timestamp()
                except (ValueError, KeyError, TypeError):
                    continue
                if stamp < started_at - 5:
                    continue  # an earlier round in the same session
                if _typed(entry):
                    prompts.append(stamp)
                    if len(prompts) == 2:
                        break
                elif entry.get("subtype") == "turn_duration":
                    ends.append(stamp)
    except OSError:
        return None
    if len(prompts) < 2:
        return None
    before = [end for end in ends if prompts[0] < end < prompts[1]]
    return max(before) if before else prompts[1]


def observe(records: Dict[str, dict], agents: Dict[str, dict], now: float,
            find_transcript: Callable[[str], Optional[Path]] = transcript) -> bool:
    """Stamp `done_at` the first time a run is seen done; True if changed. A finished round stays finished:
    when the user opens the session and asks something, that is not another review. If they asked before
    chip saw it done, the session's transcript tells when the review ended."""
    changed = False
    for record in records.values():
        agent = agents.get(record["id"])
        if not agent:
            continue
        if agent.get("sessionId") and record.get("session_id") != agent["sessionId"]:
            record["session_id"] = agent["sessionId"]
            changed = True
        if "done_at" in record:
            continue
        if agent.get("state") == "done":
            record["done_at"] = now
            changed = True
        elif record.get("session_id"):
            ended = finished_before_follow_up(find_transcript(record["session_id"]), record["started_at"])
            if ended is not None:
                record["done_at"] = ended
                changed = True
    return changed


def _after(iso: Optional[str], epoch: float) -> bool:
    return bool(iso) and model.parse_ts(iso).timestamp() > epoch


def resolve(records: Dict[str, dict], rows_by_label: Dict[str, dict], now: float, fetched: bool = False) -> bool:
    """Mark rounds resolved: finished ones once GitHub shows the user's review or newer commits, and any
    round whose PR is gone from a successful fetch (merged or closed). True if anything changed."""
    changed = False
    for record in records.values():
        if record.get("resolved_at"):
            continue
        row = rows_by_label.get(record["label"])
        if row is None:
            if fetched:
                record.update(resolved_at=now, resolved_by="PR merged or closed")
                changed = True
            continue
        if "done_at" not in record:
            continue
        if _after(row.get("my_review_at"), record["started_at"]):
            record.update(resolved_at=now, resolved_by="you reviewed on GitHub")
        elif _after(row.get("last_commit_at"), record["started_at"]):
            record.update(resolved_at=now, resolved_by="new commits")
        elif row.get("kind") == "mine" and row.get("mine_status") == model.READY:
            record.update(resolved_at=now, resolved_by="approved")
        else:
            continue
        changed = True
    return changed


def find_by_id(records: Dict[str, dict], run_id: str) -> Optional[Tuple[str, dict]]:
    return next(((key, rec) for key, rec in records.items() if rec.get("id") == run_id), None)
