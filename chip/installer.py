"""`chip install` / `chip uninstall`: wire this clone into ~/.local/bin, Claude Code and the GitHubBar app."""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Mapping, Optional

from chip import __version__, config

REPO_DIR = Path(__file__).resolve().parents[1]
MARKER = "installed by chip"
APP_NAME = "GitHubBar"
BUNDLE_ID = "com.ha-ptt0601.githubbar"
SWIFTBAR_DOMAIN = "com.ameba.SwiftBar"
# SwiftBar plugins earlier chip versions installed; GitHubBar replaces them.
OLD_PLUGIN_NAMES = ("chip.1m.sh", "chip.3m.sh", "chip-mine.1m.sh")
REQUIRED = (("gh", "brew install gh"), ("claude", "see https://claude.com/claude-code"),
            ("git", "xcode-select --install"))
LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework"
              "/Support/lsregister")
ICON_SIZES = (16, 32, 128, 256, 512)


def render_skill(template: str, chip_bin: Path) -> str:
    return template.replace("{{CHIP}}", str(chip_bin)) + f"\n<!-- {MARKER} -->\n"


def app_path(home: Path) -> Path:
    return home / "Applications" / f"{APP_NAME}.app"


def info_plist(chip_bin: Path, path_dirs: List[str]) -> dict:
    """The bundle's Info.plist: name, menu-bar-only, and the environment GitHubBar passes to chip."""
    path = ":".join(dict.fromkeys(path_dirs + ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]))
    return {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": APP_NAME,
        "CFBundlePackageType": "APPL",
        "CFBundleIconFile": APP_NAME,
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "LSMinimumSystemVersion": "13.0",
        "LSUIElement": True,
        "LSEnvironment": {"PATH": path, "CHIP_PLUGIN": str(chip_bin)},
    }


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


def _swiftbar_folders(runner, home: Path) -> List[Path]:
    folders = [home / ".swiftbar", home / "Library" / "Application Support" / "SwiftBar" / "Plugins"]
    proc = runner(["defaults", "read", SWIFTBAR_DOMAIN, "PluginDirectory"], capture_output=True, text=True)
    if proc.returncode == 0 and proc.stdout.strip():
        folders.insert(0, Path(os.path.expanduser(proc.stdout.strip())))
    return list(dict.fromkeys(folders))


def _remove_old_plugins(runner, home: Path, out) -> None:
    """Remove the SwiftBar plugins earlier chip versions wrote (only files carrying chip's marker)."""
    for folder in _swiftbar_folders(runner, home):
        for name in OLD_PLUGIN_NAMES:
            plugin = folder / name
            if plugin.is_file() and MARKER in plugin.read_text():
                plugin.unlink()
                out(f"rm    {plugin} (GitHubBar replaces the SwiftBar plugin)")


def _make_icon(repo: Path, resources: Path, runner) -> None:
    svg = repo / "chip" / "assets" / "github-mark.svg"
    iconset = resources / f"{APP_NAME}.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    for size in ICON_SIZES:
        for scale in (1, 2):
            name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
            runner(["sips", "-s", "format", "png", "-z", str(size * scale), str(size * scale), str(svg),
                    "--out", str(iconset / name)], capture_output=True, text=True)
    runner(["iconutil", "-c", "icns", str(iconset), "-o", str(resources / f"{APP_NAME}.icns")],
           capture_output=True, text=True)
    shutil.rmtree(iconset, ignore_errors=True)


def _install_app(repo: Path, home: Path, chip_bin: Path, runner, which, out) -> bool:
    """Build GitHubBar, assemble the .app, sign it ad hoc and launch it (it adds itself to Login Items). False on failure."""
    if not which("swift"):
        out("note  GitHubBar needs Swift from the Command Line Tools: xcode-select --install")
        return True
    build = runner(["swift", "build", "-c", "release", "--package-path", str(repo / "app")],
                   capture_output=True, text=True)
    binary = repo / "app" / ".build" / "release" / APP_NAME
    if build.returncode != 0 or not binary.exists():
        out(f"error GitHubBar build failed: {(build.stderr or build.stdout).strip()[-400:]}")
        return False
    app = app_path(home)
    runner(["osascript", "-e", f'quit app "{APP_NAME}"'], capture_output=True, text=True)
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, contents / "MacOS" / APP_NAME)
    (contents / "MacOS" / APP_NAME).chmod(0o755)
    path_dirs = [str(Path(p).parent) for p in (which(t) for t in ("gh", "claude", "git", "python3")) if p]
    (contents / "Info.plist").write_bytes(plistlib.dumps(info_plist(chip_bin, path_dirs)))
    _make_icon(repo, contents / "Resources", runner)
    for cmd in (["codesign", "--force", "--sign", "-", str(app)],
                ["xattr", "-dr", "com.apple.quarantine", str(app)],
                [LSREGISTER, "-f", str(app)]):
        runner(cmd, capture_output=True, text=True)
    # The app registers itself as a login item (SMAppService) on first launch: no Apple-events permission needed.
    runner(["open", str(app)], capture_output=True, text=True)
    out(f"app   {app} (opens at login; toggle in its menu)")
    return True


def install(repo: Path = REPO_DIR, home: Optional[Path] = None, runner=None,
            which: Optional[Callable[[str], Optional[str]]] = None, out=print,
            env: Optional[Mapping[str, str]] = None, config_file: Optional[Path] = None) -> int:
    runner = runner or subprocess.run
    which = which or shutil.which
    home = home or Path.home()
    env = os.environ if env is None else env
    repo = Path(repo)
    chip_bin = repo / "bin" / "chip"

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
    _install_skill(repo, home, chip_bin, out)
    _install_mcp(chip_bin, runner, out)
    _remove_old_plugins(runner, home, out)
    app_ok = _install_app(repo, home, chip_bin, runner, which, out)
    if config.init(config_file):
        out(f"conf  {config_file or config.config_path()}")
    out("done  chip is installed" if app_ok else "done  chip is installed, but GitHubBar is not")
    return 0 if app_ok else 1


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
    _remove_old_plugins(runner, home, out)
    app = app_path(home)
    info = app / "Contents" / "Info.plist"
    if info.exists() and plistlib.loads(info.read_bytes()).get("CFBundleIdentifier") == BUNDLE_ID:
        runner(["osascript", "-e", f'quit app "{APP_NAME}"'], capture_output=True, text=True)
        # Removing the bundle drops its SMAppService login item; clear a legacy System Events item too.
        runner(["osascript", "-e", f'tell application "System Events" to delete login item "{APP_NAME}"'],
               capture_output=True, text=True)
        shutil.rmtree(app)
        out(f"rm    {app}")
    out("done  config and cache are kept (~/.config/chip, ~/.cache/chip)")
    return 0
