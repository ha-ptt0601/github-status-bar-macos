"""`chip install` / `chip uninstall`: wire this clone into ~/.local/bin, Claude Code and SwiftBar."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional, Tuple

from chip import config

REPO_DIR = Path(__file__).resolve().parents[1]
MARKER = "installed by chip"
SWIFTBAR_DOMAIN = "com.ameba.SwiftBar"
PLUGIN_NAME = "chip.1m.sh"  # menu refresh every minute; GitHub is still fetched at most every 3 minutes
LEGACY_PLUGIN_NAMES = ("chip.3m.sh",)
SWIFTBAR_APP = Path("/Applications/SwiftBar.app")
REQUIRED = (("gh", "brew install gh"), ("claude", "see https://claude.com/claude-code"),
            ("git", "xcode-select --install"))


def plugin_script(chip_bin: Path, path_dirs: Iterable[str]) -> str:
    path = ":".join(dict.fromkeys(path_dirs))
    return f"""#!/bin/bash
# <swiftbar.title>chip</swiftbar.title>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideLastUpdated>true</swiftbar.hideLastUpdated>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>
# <swiftbar.hideSwiftBar>true</swiftbar.hideSwiftBar>
# {MARKER} — regenerate with `chip install`
export PATH="{path}:$PATH"
export CHIP_PLUGIN="$0"
if [ $# -eq 0 ]; then exec "{chip_bin}" swiftbar; fi
exec "{chip_bin}" "$@"
"""


def render_skill(template: str, chip_bin: Path) -> str:
    return template.replace("{{CHIP}}", str(chip_bin)) + f"\n<!-- {MARKER} -->\n"


def _swiftbar_data_dir(home: Path) -> Path:
    """Where SwiftBar keeps per-plugin data folders; never use it as the plugin folder."""
    return home / "Library" / "Application Support" / "SwiftBar" / "Plugins"


def _read_plugin_dir(runner) -> Optional[Path]:
    proc = runner(["defaults", "read", SWIFTBAR_DOMAIN, "PluginDirectory"], capture_output=True, text=True)
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(os.path.expanduser(proc.stdout.strip()))
    return None


def swiftbar_plugin_dir(runner, home: Path) -> Tuple[Path, Optional[Path]]:
    """(plugin folder to use, previous folder if we moved off SwiftBar's own data folder)."""
    current = _read_plugin_dir(runner)
    if current is not None and current != _swiftbar_data_dir(home):
        return current, None
    target = home / ".swiftbar"
    runner(["defaults", "write", SWIFTBAR_DOMAIN, "PluginDirectory", str(target)], capture_output=True, text=True)
    return target, current


def _link(dst: Path, target: Path, out) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink():
        if dst.resolve() == target.resolve():
            out(f"ok    {dst}")
        else:
            out(f"skip  {dst} already points to {os.readlink(dst)}")
        return
    if dst.exists():
        out(f"skip  {dst} exists and is not a chip link")
        return
    dst.symlink_to(target)
    out(f"link  {dst} -> {target}")


def _install_skill(repo: Path, home: Path, chip_bin: Path, out) -> None:
    dst_dir = home / ".claude" / "skills" / "chip"
    if dst_dir.is_symlink():
        if str(dst_dir.resolve()).startswith(str(repo.resolve())):
            dst_dir.unlink()
        else:
            out(f"skip  {dst_dir} is a symlink to {os.readlink(dst_dir)}")
            return
    skill = dst_dir / "SKILL.md"
    if skill.exists() and MARKER not in skill.read_text():
        out(f"skip  {skill} was not installed by chip")
        return
    dst_dir.mkdir(parents=True, exist_ok=True)
    skill.write_text(render_skill((repo / "skill" / "SKILL.md").read_text(), chip_bin))
    out(f"skill {skill}")


def _install_mcp(chip_bin: Path, runner, out) -> None:
    got = runner(["claude", "mcp", "get", "chip"], capture_output=True, text=True)
    if got.returncode == 0:
        if str(chip_bin) in got.stdout:
            out("ok    MCP server chip")
        else:
            out("skip  MCP server chip points to another chip; `claude mcp remove chip` to replace it")
        return
    runner(["claude", "mcp", "add", "--scope", "user", "chip", "--", str(chip_bin), "mcp"],
           capture_output=True, text=True)
    out("mcp   chip (user scope)")


def _install_plugin(chip_bin: Path, runner, which, out, swiftbar_app: Path, home: Path) -> None:
    plugin_dir, moved_from = swiftbar_plugin_dir(runner, home)
    plugin_dir.mkdir(parents=True, exist_ok=True)
    if moved_from:
        out(f"note  SwiftBar plugin folder moved to {plugin_dir} (was SwiftBar's own data folder)")
    stale = [plugin_dir / name for name in LEGACY_PLUGIN_NAMES]
    if moved_from:
        stale += [moved_from / name for name in (PLUGIN_NAME,) + LEGACY_PLUGIN_NAMES]
    for old in stale:
        if old.is_file() and MARKER in old.read_text():
            old.unlink()
            out(f"rm    {old} (replaced by {plugin_dir / PLUGIN_NAME})")
    plugin = plugin_dir / PLUGIN_NAME
    if plugin.exists() and MARKER not in plugin.read_text():
        out(f"skip  {plugin} was not installed by chip")
        return
    path_dirs = [str(Path(p).parent) for p in (which(t) for t in ("gh", "claude", "git", "python3")) if p]
    plugin.write_text(plugin_script(chip_bin, path_dirs))
    plugin.chmod(0o755)
    out(f"menu  {plugin}")
    if swiftbar_app.exists():
        if moved_from is not None:  # SwiftBar reads PluginDirectory at launch
            runner(["killall", "SwiftBar"], capture_output=True, text=True)
        runner(["open", "-a", "SwiftBar"], capture_output=True, text=True)
    else:
        out("note  SwiftBar is not installed: brew install swiftbar")


def install(repo: Path = REPO_DIR, home: Optional[Path] = None, runner=None,
            which: Optional[Callable[[str], Optional[str]]] = None, out=print,
            env: Optional[Mapping[str, str]] = None, swiftbar_app: Path = SWIFTBAR_APP,
            config_file: Optional[Path] = None) -> int:
    runner = runner or subprocess.run
    which = which or shutil.which
    home = home or Path.home()
    env = os.environ if env is None else env
    chip_bin = Path(repo) / "bin" / "chip"

    problems = []
    if sys.version_info < (3, 9):
        problems.append("python3 >= 3.9 is required")
    for tool, hint in REQUIRED:
        if not which(tool):
            problems.append(f"missing {tool}: {hint}")
    if which("gh") and runner(["gh", "auth", "status"], capture_output=True, text=True).returncode != 0:
        problems.append("gh is not logged in: gh auth login")
    if problems:
        for problem in problems:
            out(f"error {problem}")
        return 1
    if not which("fzf"):
        out("note  optional: brew install fzf (for the `chip` picker)")

    link = home / ".local" / "bin" / "chip"
    _link(link, chip_bin, out)
    if str(link.parent) not in env.get("PATH", "").split(":"):
        out(f"note  add {link.parent} to PATH to use `chip` in a shell")
    _install_skill(Path(repo), home, chip_bin, out)
    _install_mcp(chip_bin, runner, out)
    _install_plugin(chip_bin, runner, which, out, swiftbar_app, home)
    if config.init(config_file):
        out(f"conf  {config_file or config.config_path()}")
    out("done  chip is installed")
    return 0


def uninstall(repo: Path = REPO_DIR, home: Optional[Path] = None, runner=None, out=print) -> int:
    runner = runner or subprocess.run
    home = home or Path.home()
    chip_bin = Path(repo) / "bin" / "chip"
    link = home / ".local" / "bin" / "chip"
    if link.is_symlink() and link.resolve() == chip_bin.resolve():
        link.unlink()
        out(f"rm    {link}")
    skill_dir = home / ".claude" / "skills" / "chip"
    skill = skill_dir / "SKILL.md"
    if not skill_dir.is_symlink() and skill.exists() and MARKER in skill.read_text():
        shutil.rmtree(skill_dir)
        out(f"rm    {skill_dir}")
    got = runner(["claude", "mcp", "get", "chip"], capture_output=True, text=True)
    if got.returncode == 0 and str(chip_bin) in got.stdout:
        runner(["claude", "mcp", "remove", "chip", "--scope", "user"], capture_output=True, text=True)
        out("rm    MCP server chip")
    folders = {_read_plugin_dir(runner), home / ".swiftbar", _swiftbar_data_dir(home)}
    for plugin in (folder / name for folder in folders if folder for name in (PLUGIN_NAME,) + LEGACY_PLUGIN_NAMES):
        if plugin.is_file() and MARKER in plugin.read_text():
            plugin.unlink()
            out(f"rm    {plugin}")
    out("done  config and cache are kept (~/.config/chip, ~/.cache/chip)")
    return 0
