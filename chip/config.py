"""User config at ~/.config/chip/config.json: review skills, work root, permissions, terminal."""
from __future__ import annotations

import json
import os
import string
from pathlib import Path
from typing import List, Optional

PLACEHOLDERS = {"url", "repo", "number", "label", "title"}
TERMINALS = ("Terminal", "iTerm")
STATUS_STYLES = ("dots", "emoji", "symbols")
SETTABLE = {"status_style": STATUS_STYLES, "terminal": TERMINALS}
DEFAULT = {
    "work_root": "~/work",
    "skills": [{"name": "Full review", "prompt": "/my-review-skill {url}"}],
    "permission_mode": "auto",
    "disallowed_tools": ["Edit", "Write", "NotebookEdit"],
    "terminal": "Terminal",
    "status_style": "dots",
}


def config_path() -> Path:
    return Path(os.environ.get("CHIP_CONFIG") or Path.home() / ".config" / "chip" / "config.json")


def _fields(prompt: str) -> set:
    return {field for _, field, _, _ in string.Formatter().parse(prompt) if field is not None}


def validate(data) -> List[str]:
    if not isinstance(data, dict):
        return ["config must be a JSON object"]
    errors = []
    skills = data.get("skills", DEFAULT["skills"])
    if not isinstance(skills, list) or not skills:
        errors.append("skills must be a non-empty list")
    else:
        for i, skill in enumerate(skills, 1):
            ok = isinstance(skill, dict) and all(
                isinstance(skill.get(k), str) and skill[k].strip() for k in ("name", "prompt"))
            if not ok:
                errors.append(f"skills[{i}] needs a non-empty name and prompt")
                continue
            try:
                unknown = _fields(skill["prompt"]) - PLACEHOLDERS
            except ValueError as exc:
                errors.append(f"skills[{i}] prompt: {exc}")
                continue
            if unknown:
                errors.append(f"skills[{i}] unknown placeholder(s): {', '.join(sorted(unknown))}")
        names = [s.get("name") for s in skills if isinstance(s, dict)]
        if len(names) != len(set(names)):
            errors.append("skill names must be unique")
    for key in ("work_root", "permission_mode"):
        if not isinstance(data.get(key, DEFAULT[key]), str):
            errors.append(f"{key} must be a string")
    tools = data.get("disallowed_tools", DEFAULT["disallowed_tools"])
    if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
        errors.append("disallowed_tools must be a list of strings")
    if data.get("terminal", DEFAULT["terminal"]) not in TERMINALS:
        errors.append(f"terminal must be one of {', '.join(TERMINALS)}")
    if data.get("status_style", DEFAULT["status_style"]) not in STATUS_STYLES:
        errors.append(f"status_style must be one of {', '.join(STATUS_STYLES)}")
    return errors


def _resolved(data: dict, errors: List[str]) -> dict:
    out = {key: data[key] for key in DEFAULT}
    out["work_root"] = str(Path(os.path.expanduser(out["work_root"])))
    out["errors"] = errors
    return out


def load(path: Optional[Path] = None) -> dict:
    """The merged config plus `errors`. Any error means the defaults are used (errors kept for display)."""
    path = Path(path) if path else config_path()
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except ValueError as exc:
            return _resolved(DEFAULT, [f"{path}: invalid JSON ({exc})"])
    errors = validate(data)
    if errors:
        return _resolved(DEFAULT, errors)
    merged = dict(DEFAULT)
    merged.update({k: v for k, v in data.items() if k in DEFAULT})
    return _resolved(merged, [])


def fill_prompt(skill: dict, row: dict) -> str:
    return skill["prompt"].format(url=row["url"], repo=row["repo"], number=row["number"],
                                  label=row["label"], title=row["title"])


def init(path: Optional[Path] = None) -> bool:
    """Write the default config if missing; True when a file was written."""
    path = Path(path) if path else config_path()
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEFAULT, ensure_ascii=False, indent=2) + "\n")
    return True


def set_value(key: str, value: str, path: Optional[Path] = None) -> List[str]:
    """Set one menu-settable key in the config file; returns errors (nothing is written on error)."""
    path = Path(path) if path else config_path()
    if key not in SETTABLE:
        return [f"{key} cannot be set from the menu (settable: {', '.join(sorted(SETTABLE))})"]
    if value not in SETTABLE[key]:
        return [f"{key} must be one of {', '.join(SETTABLE[key])}"]
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except ValueError as exc:
            return [f"{path}: invalid JSON ({exc})"]
    data[key] = value
    errors = validate(data)
    if errors:
        return errors
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return []
