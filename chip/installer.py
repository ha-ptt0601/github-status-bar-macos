"""`chip install` / `chip uninstall`: wire chip into ~/.local/bin, Claude Code and the GitHubBar app.

chip runs either from a clone (it builds GitHubBar.app into ~/Applications) or from inside GitHubBar.app,
which carries a copy of chip in Contents/Resources/chip (the .dmg from the releases; `package` builds it).
"""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, List, Mapping, Optional

from chip import __version__, config

REPO_DIR = Path(__file__).resolve().parents[1]
MARKER = "installed by chip"
APP_NAME = "GitHubBar"
BUNDLE_ID = "com.ha-ptt0601.githubbar"
REQUIRED = (("gh", "brew install gh"), ("claude", "see https://claude.com/claude-code"),
            ("git", "xcode-select --install"))
LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework"
              "/Support/lsregister")
ICON_SIZES = (16, 32, 128, 256, 512)
BUNDLED = ("bin", "chip", "skill", "LICENSE", "config.example.json")  # what GitHubBar.app carries
ARCHS = ("arm64", "x86_64")
DMG = f"{APP_NAME}.dmg"
# The window the .dmg opens with: big icons, the app on the left, Applications on the right (Finder saves it
# in the image's .DS_Store).
DMG_LAYOUT = f"""
tell application "Finder"
  tell disk "{APP_NAME}"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set the bounds of container window to {{200, 120, 740, 440}}
    set opts to the icon view options of container window
    set arrangement of opts to not arranged
    set icon size of opts to 128
    set text size of opts to 13
    set position of item "{APP_NAME}.app" of container window to {{140, 150}}
    set position of item "Applications" of container window to {{400, 150}}
    update without registering applications
    delay 1
    close
  end tell
end tell
"""


def bundled(repo: Path = REPO_DIR) -> Optional[Path]:
    """The GitHubBar.app this chip came inside (…/GitHubBar.app/Contents/Resources/chip); None for a clone."""
    repo = Path(repo).resolve()
    app = repo.parents[2] if len(repo.parents) > 2 else None
    if repo.parent.name == "Resources" and repo.parent.parent.name == "Contents" and app and app.suffix == ".app":
        return app
    return None


def render_skill(template: str, chip_bin: Path) -> str:
    return template.replace("{{CHIP}}", str(chip_bin)) + f"\n<!-- {MARKER} -->\n"


def app_path(home: Path) -> Path:
    return home / "Applications" / f"{APP_NAME}.app"


def info_plist(chip_bin: Optional[Path], path_dirs: List[str]) -> dict:
    """The bundle's Info.plist: name, menu-bar-only, and the environment GitHubBar passes to chip. Without
    `chip_bin` (the .dmg), GitHubBar runs the chip it carries and takes PATH from the login shell."""
    plist = {
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
    }
    if chip_bin:
        path = ":".join(dict.fromkeys(path_dirs + ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]))
        plist["LSEnvironment"] = {"PATH": path, "CHIP_PLUGIN": str(chip_bin)}
    return plist


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


def _build(repo: Path, runner, arch: Optional[str] = None):
    """Build the GitHubBar binary (for `arch`, else this Mac). Returns its path, or the build error."""
    cmd = ["swift", "build", "-c", "release", "--package-path", str(repo / "app"), "--product", APP_NAME]
    if arch:
        cmd += ["--triple", f"{arch}-apple-macosx13.0"]
    build = runner(cmd, capture_output=True, text=True)
    binary = repo / "app" / ".build" / (f"{arch}-apple-macosx" if arch else "") / "release" / APP_NAME
    if build.returncode != 0 or not binary.exists():
        return (build.stderr or build.stdout or "swift build failed").strip()[-400:]
    return binary


def _assemble(app: Path, binary: Path, repo: Path, info: dict, runner, carry_chip: bool) -> None:
    """Lay out GitHubBar.app (binary, Info.plist, icon and, for the .dmg, chip itself) and sign it ad hoc."""
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, contents / "MacOS" / APP_NAME)
    (contents / "MacOS" / APP_NAME).chmod(0o755)
    (contents / "Info.plist").write_bytes(plistlib.dumps(info))
    _make_icon(repo, contents / "Resources", runner)
    if carry_chip:
        dst = contents / "Resources" / "chip"
        shutil.rmtree(dst, ignore_errors=True)
        dst.mkdir(parents=True)
        for name in BUNDLED:
            src = repo / name
            if src.is_dir():
                shutil.copytree(src, dst / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            elif src.exists():
                shutil.copy2(src, dst / name)
    runner(["codesign", "--force", "--sign", "-", str(app)], capture_output=True, text=True)


def _install_app(repo: Path, home: Path, chip_bin: Path, runner, which, out) -> bool:
    """Build GitHubBar, assemble the .app, sign it ad hoc and launch it (it adds itself to Login Items). False on failure."""
    if not which("swift"):
        out("note  GitHubBar needs Swift from the Command Line Tools: xcode-select --install")
        return True
    binary = _build(repo, runner)
    if isinstance(binary, str):
        out(f"error GitHubBar build failed: {binary}")
        return False
    app = app_path(home)
    runner(["osascript", "-e", f'quit app "{APP_NAME}"'], capture_output=True, text=True)
    path_dirs = [str(Path(p).parent) for p in (which(t) for t in ("gh", "claude", "git", "python3")) if p]
    _assemble(app, binary, repo, info_plist(chip_bin, path_dirs), runner, carry_chip=False)
    for cmd in (["xattr", "-dr", "com.apple.quarantine", str(app)], [LSREGISTER, "-f", str(app)]):
        runner(cmd, capture_output=True, text=True)
    # The app registers itself as a login item (SMAppService) on first launch: no Apple-events permission needed.
    runner(["open", str(app)], capture_output=True, text=True)
    out(f"app   {app} (opens at login; toggle in its menu)")
    return True


def package(repo: Path = REPO_DIR, out_dir: Optional[Path] = None, runner=None, out=print) -> Optional[Path]:
    """Build GitHubBar.dmg: a universal GitHubBar.app carrying chip, next to a link to /Applications."""
    runner = runner or subprocess.run
    repo = Path(repo)
    out_dir = Path(out_dir or repo / "dist")
    binaries = []
    for arch in ARCHS:
        binary = _build(repo, runner, arch)
        if isinstance(binary, str):
            out(f"error GitHubBar build failed ({arch}): {binary}")
            return None
        binaries.append(binary)
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / APP_NAME
        universal = Path(tmp) / f"{APP_NAME}.bin"
        lipo = runner(["lipo", "-create", "-output", str(universal)] + [str(b) for b in binaries],
                      capture_output=True, text=True)
        if lipo.returncode != 0:
            out(f"error lipo failed: {(lipo.stderr or lipo.stdout).strip()}")
            return None
        _assemble(stage / f"{APP_NAME}.app", universal, repo, info_plist(None, []), runner, carry_chip=True)
        (stage / "Applications").symlink_to("/Applications")
        out_dir.mkdir(parents=True, exist_ok=True)
        dmg = out_dir / DMG
        writable = Path(tmp) / "rw.dmg"
        made = runner(["hdiutil", "create", "-volname", APP_NAME, "-srcfolder", str(stage), "-ov",
                       "-format", "UDRW", str(writable)], capture_output=True, text=True)
        if made.returncode != 0:
            out(f"error hdiutil failed: {(made.stderr or made.stdout).strip()}")
            return None
        _lay_out(writable, runner, out)
        made = runner(["hdiutil", "convert", str(writable), "-format", "UDZO", "-ov", "-o", str(dmg)],
                      capture_output=True, text=True)
        if made.returncode != 0:
            out(f"error hdiutil failed: {(made.stderr or made.stdout).strip()}")
            return None
    out(f"dmg   {dmg}")
    return dmg


def _lay_out(image: Path, runner, out) -> None:
    """Arrange the window the .dmg opens with. Optional: without it Finder shows the two icons as they are."""
    attach = runner(["hdiutil", "attach", "-readwrite", "-noverify", "-noautoopen", str(image)],
                    capture_output=True, text=True)
    volume = next((line.split("\t")[-1].strip() for line in (attach.stdout or "").splitlines()
                   if "/Volumes/" in line), "")
    if attach.returncode != 0 or not volume:
        out("note  could not open the .dmg to arrange its window")
        return
    try:
        if runner(["osascript", "-e", DMG_LAYOUT], capture_output=True, text=True).returncode != 0:
            out("note  Finder did not arrange the .dmg window (allow Terminal to control Finder)")
    finally:
        runner(["sync"], capture_output=True, text=True)
        runner(["hdiutil", "detach", volume], capture_output=True, text=True)


def _report_folders(config_file, out) -> None:
    """Say where chip will look for clones, and where it clones the rest."""
    from chip import store
    cfg = config.load(config_file)
    roots = cfg["work_roots"] or [str(p) for p in store.detected_roots()]
    source = "work_roots" if cfg["work_roots"] else "detected"
    if roots:
        out(f"repos looks for your clones in {', '.join(roots)} ({source}); set work_roots in the config to change")
    else:
        out("repos no code folder found; set work_roots in the config to use your own clones")
    out(f"repos clones the others into {cfg['clone_root'] or store.cache_dir() / 'repos'}")


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
    # Inside GitHubBar.app (the .dmg) the app is already there: GitHubBar runs this on its first launch.
    app_ok = bundled(repo) is not None or _install_app(repo, home, chip_bin, runner, which, out)
    if config.init(config_file):
        out(f"conf  {config_file or config.config_path()}")
    _report_folders(config_file, out)
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
    if bundled(repo):
        out(f"note  quit GitHubBar and move {bundled(repo)} to the Trash to remove the app")
        out("done  config and cache are kept (~/.config/chip, ~/.cache/chip)")
        return 0
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
