import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from chip import runs, sessions


def line(branch, cwd, kind="assistant", text="", ts="2026-10-01T10:00:00Z"):
    entry = {"type": kind, "gitBranch": branch, "cwd": cwd, "timestamp": ts, "sessionId": "x"}
    if kind == "user":
        entry["message"] = {"content": text}
    return json.dumps(entry, separators=(",", ":"))


class SessionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "projects"
        self.index_path = Path(self.tmp.name) / "sessions.json"

    def tearDown(self):
        self.tmp.cleanup()

    def session(self, folder, sid, lines):
        path = self.root / folder / f"{sid}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n")
        return path

    def test_finds_the_busiest_session_on_the_branch_in_the_repo(self):
        api = "/Users/me/work/acme/api"
        self.session("-Users-me-work-acme-api", "feat-1", [
            line("dev", api, "user", "add the export feature"),
            *[line("feature/export", api + "/.worktrees/export") for _ in range(5)]])
        self.session("-Users-me-work-acme-api", "small", [line("feature/export", api)])
        self.session("-Users-me-work-other", "elsewhere", [line("feature/export", "/Users/me/work/other")] * 9)
        self.session("-Users-me--cache-chip-worktrees-api-7", "chip-run", [line("feature/export", api)] * 20)
        index = sessions.update_index(self.index_path, budget=5, root=self.root)
        found = sessions.find(index, "feature/export", api)
        self.assertEqual((found["id"], found["cwd"], found["prompt"]), ("feat-1", api, "add the export feature"))
        self.assertIsNone(sessions.find(index, "dev", api))  # trunk branches never match
        self.assertIsNone(sessions.find(index, "feature/none", api))

    def test_index_is_incremental(self):
        path = self.session("-p", "a", [line("feature/x", "/r")])
        sessions.update_index(self.index_path, root=self.root)
        before = json.loads(self.index_path.read_text())["files"][str(path)]["mtime"]
        sessions.update_index(self.index_path, root=self.root)
        self.assertEqual(json.loads(self.index_path.read_text())["files"][str(path)]["mtime"], before)

    def test_links_win_and_by_id(self):
        self.session("-r", "abc", [line("feature/y", "/r")])
        index = sessions.update_index(self.index_path, root=self.root)
        links_path = Path(self.tmp.name) / "links.json"
        sessions.link(links_path, "api#9", sessions.by_id(index, "abc"))
        rows = [{"label": "api#9", "repo": "acme/api", "head": "feature/other"},
                {"label": "api#10", "repo": "acme/api", "head": "feature/y"}]
        found = sessions.for_rows(rows, index, sessions.load_links(links_path), {})
        self.assertTrue(found["api#9"]["linked"])
        self.assertEqual((found["api#10"]["id"], found["api#10"]["linked"]), ("abc", False))
        sessions.unlink(links_path, "api#9")
        self.assertEqual(sessions.load_links(links_path), {})

    def test_the_session_that_opened_the_pr_beats_the_busiest_one(self):
        api = "/Users/me/work/acme/api"
        opened = json.dumps({"type": "pr-link", "sessionId": "opener", "prNumber": 9,
                             "prUrl": "https://github.com/Acme/API/pull/9", "prRepository": "Acme/API"})
        self.session("-Users-me-work-acme-api", "opener", [line("feature/export", api), opened])
        self.session("-Users-me-work-acme-api", "busy", [line("feature/export", api)] * 9)
        index = sessions.update_index(self.index_path, budget=5, root=self.root)
        row = {"label": "api#9", "repo": "acme/api", "number": 9, "head": "feature/export"}
        found = sessions.for_rows([row, dict(row, label="api#10", number=10)], index, {}, {"acme/api": api})
        self.assertEqual((found["api#9"]["id"], found["api#9"]["cwd"]), ("opener", api))
        self.assertEqual(found["api#10"]["id"], "busy")  # no session opened #10: the branch decides
        self.assertEqual(sessions.find_by_pr(index, "acme/api", 9)["id"], "opener")
        self.assertIsNone(sessions.find_by_pr(index, "acme/api", 10))

    def test_an_index_from_before_pr_links_is_read_again(self):
        path = self.session("-p", "a", [line("feature/x", "/r"), json.dumps(
            {"type": "pr-link", "prNumber": 3, "prRepository": "acme/api"})])
        stale = {"files": {str(path): {"branches": {"feature/x": 1}, "mtime": path.stat().st_mtime}}}
        self.index_path.write_text(json.dumps(stale))
        index = sessions.update_index(self.index_path, root=self.root)
        self.assertEqual(index["files"][str(path)]["prs"], ["acme/api#3"])


class ResumeTest(unittest.TestCase):
    def test_round_one_continues_the_given_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []

            def runner(cmd, **kw):
                calls.append((cmd, kw.get("cwd")))
                return subprocess.CompletedProcess(cmd, 0, "backgrounded · ab12cd34 · x\n", "")
            row = {"label": "api#9", "title": "t", "url": "https://github.com/acme/api/pull/9", "repo": "acme/api",
                   "number": 9}
            skill = {"name": "Address review (feature session)", "prompt": "Address {url}"}
            cfg = {"disallowed_tools": [], "permission_mode": "auto"}
            record = runs.start(row, skill, cfg, "/r", Path(tmp) / "runs.json", runner, address=True, resume="feat-1")
            self.assertEqual(calls[0], (["claude", "Address https://github.com/acme/api/pull/9", "--resume", "feat-1",
                                         "--bg"], "/r"))
            self.assertEqual((record["session_id"], record["round"], record["kind"]), ("feat-1", 1, "address"))
