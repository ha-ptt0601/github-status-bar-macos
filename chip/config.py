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
ADDRESS_PROMPT = (
    "Help me address the review feedback on my pull request {url}. Use gh to read every unresolved review thread "
    "and review comment. For each one: quote it, propose the exact code change as a diff, and draft a short reply "
    "I can post. Do not edit files, commit, push, or post anything to GitHub."
)
DEFAULT = {
    "work_root": "~/work",
    "skills": [{"name": "Full review", "prompt": "/my-review-skill {url}"}],
    "address_skills": [{"name": "Address review", "prompt": ADDRESS_PROMPT}],
    "permission_mode": "auto",
    "disallowed_tools": ["Edit", "Write", "NotebookEdit"],
    "terminal": "Terminal",
    "status_style": "dots",
    "hidden_projects": [],
}


def config_path() -> Path:
    return Path(os.environ.get("CHIP_CONFIG") or Path.home() / ".config" / "chip" / "config.json")


def _fields(prompt: str) -> set:
    return {field for _, field, _, _ in string.Formatter().parse(prompt) if field is not None}


def _validate_skills(key: str, skills) -> List[str]:
    if not isinstance(skills, list) or not skills:
        return [f"{key} must be a non-empty list"]
    errors = []
    for i, skill in enumerate(skills, 1):
        ok = isinstance(skill, dict) and all(
            isinstance(skill.get(k), str) and skill[k].strip() for k in ("name", "prompt"))
        if not ok:
            errors.append(f"{key}[{i}] needs a non-empty name and prompt")
            continue
        try:
            unknown = _fields(skill["prompt"]) - PLACEHOLDERS
        except ValueError as exc:
            errors.append(f"{key}[{i}] prompt: {exc}")
            continue
        if unknown:
            errors.append(f"{key}[{i}] unknown placeholder(s): {', '.join(sorted(unknown))}")
    names = [s.get("name") for s in skills if isinstance(s, dict)]
    if len(names) != len(set(names)):
        errors.append(f"{key} names must be unique")
    return errors


def validate(data) -> List[str]:
    if not isinstance(data, dict):
        return ["config must be a JSON object"]
    errors = []
    for key in ("skills", "address_skills"):
        errors += _validate_skills(key, data.get(key, DEFAULT[key]))
    for key in ("work_root", "permission_mode"):
        if not isinstance(data.get(key, DEFAULT[key]), str):
            errors.append(f"{key} must be a string")
    tools = data.get("disallowed_tools", DEFAULT["disallowed_tools"])
    if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
        errors.append("disallowed_tools must be a list of strings")
    if data.get("terminal", DEFAULT["terminal"]) not in TERMINALS:
        errors.append(f"terminal must be one of {', '.join(TERMINALS)}")
    hidden = data.get("hidden_projects", DEFAULT["hidden_projects"])
    if not isinstance(hidden, list) or not all(isinstance(p, str) for p in hidden):
        errors.append("hidden_projects must be a list of project names")
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


def _update(path: Optional[Path], change) -> None:
    path = Path(path) if path else config_path()
    data = json.loads(path.read_text()) if path.exists() else {}
    change(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def toggle_project(name: str, path: Optional[Path] = None) -> None:
    """Hide a project in the menu, or show it again if it is hidden."""
    def change(data):
        hidden = [p for p in data.get("hidden_projects", []) if p != name]
        if len(hidden) == len(data.get("hidden_projects", [])):
            hidden.append(name)
        data["hidden_projects"] = hidden
    _update(path, change)


def show_all_projects(path: Optional[Path] = None) -> None:
    _update(path, lambda data: data.__setitem__("hidden_projects", []))
