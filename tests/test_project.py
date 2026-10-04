import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from chip import config, project

ROW = {"repo": "acme/api", "number": 2079, "base": "dev", "url": "https://github.com/acme/api/pull/2079",
       "label": "api#2079", "title": "t"}


class FindSkillTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def skill(self, name):
        (self.repo / ".claude" / "skills" / name).mkdir(parents=True)
        (self.repo / ".claude" / "skills" / name / "SKILL.md").write_text("---\nname: x\n---\n")

    def test_none(self):
        self.skill("commit")
        self.assertIsNone(project.find_review_skill(self.repo))

    def test_exact_review_wins(self):
        self.skill("code-review")
        self.skill("review")
        self.assertEqual(project.find_review_skill(self.repo), "review")

    def test_review_in_name_and_commands(self):
        self.skill("pr-review")
        self.assertEqual(project.find_review_skill(self.repo), "pr-review")
        other = Path(self.tmp.name) / "other"
        (other / ".claude" / "commands").mkdir(parents=True)
        (other / ".claude" / "commands" / "review-pr.md").write_text("x")
        self.assertEqual(project.find_review_skill(other), "review-pr")

    def test_known_skills_uses_clone_cache_only(self):
        self.skill("review")
        cache = Path(self.tmp.name) / "repos.json"
        cache.write_text(json.dumps({"acme/api": str(self.repo)}))
        self.assertEqual(project.known_skills({"acme/api", "acme/mailer-api"}, cache), {"acme/api": "review"})

    def test_prompt_is_filled_per_pr(self):
        skill = project.in_worktree({"name": project.skill_label("review"), "prompt": project.prompt_template("review")})
        self.assertEqual(skill["name"], "/review (project)")
        text = config.fill_prompt(skill, ROW)
        self.assertTrue(text.startswith("/review https://github.com/acme/api/pull/2079\n"))
        self.assertIn("pull request #2079", text)
        self.assertIn("git diff origin/dev...HEAD", text)
        self.assertEqual(config.validate({"skills": [skill]}), [])


class WorktreeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def runner(self, cmd, **kw):
        self.calls.append(cmd)
        if cmd[3:5] == ["worktree", "add"]:
            (Path(cmd[-2]) / ".git").parent.mkdir(parents=True, exist_ok=True)
            (Path(cmd[-2]) / ".git").write_text("gitdir: x")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def test_first_checkout_adds_a_worktree_then_updates_it(self):
        path = project.checkout("/src/api", ROW, self.root, self.runner)
        self.assertEqual(path, str(self.root / "api-2079"))
        self.assertEqual(self.calls[0], ["git", "-C", "/src/api", "fetch", "--quiet", "origin",
                                         "+refs/pull/2079/head:refs/chip/pr-2079",
                                         "+refs/heads/dev:refs/remotes/origin/dev"])
        self.assertEqual(self.calls[1], ["git", "-C", "/src/api", "worktree", "add", "--quiet", "--detach",
                                         path, "refs/chip/pr-2079"])
        self.calls.clear()
        project.checkout("/src/api", ROW, self.root, self.runner)  # round 2: new commits
        self.assertEqual(self.calls[1], ["git", "-C", path, "checkout", "--quiet", "--detach", "--force",
                                         "refs/chip/pr-2079"])

    def test_git_failure_raises(self):
        def failing(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 128, "", "fatal: couldn't find remote ref")
        with self.assertRaises(project.WorktreeError):
            project.checkout("/src/api", ROW, self.root, failing)


class CleanupTest(unittest.TestCase):
    def test_merged_pr_worktree_is_removed_once(self):
        from chip import runs
        calls = []
        records = {"k": {"label": "api#2079", "clone": "/src/api", "worktree": "/w/api-2079",
                         "resolved_by": "PR merged or closed"},
                   "j": {"label": "api#1", "clone": "/src/api", "worktree": "/w/api-1", "resolved_by": "new commits"}}
        runner = lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", "")
        self.assertTrue(runs.clean_worktrees(records, runner))
        self.assertEqual(calls, [["git", "-C", "/src/api", "worktree", "remove", "--force", "/w/api-2079"],
                                 ["git", "-C", "/src/api", "update-ref", "-d", "refs/chip/pr-2079"]])
        self.assertNotIn("worktree", records["k"])
        self.assertIn("worktree", records["j"])
        self.assertFalse(runs.clean_worktrees(records, runner))


class PrepareTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clone, self.worktree = Path(self.tmp.name) / "clone", Path(self.tmp.name) / "wt"
        (self.clone / ".claude").mkdir(parents=True)
        (self.clone / ".claude" / "settings.local.json").write_text('{"enableAllProjectMcpServers": true}')
        (self.clone / ".env").write_text("DB=x")
        (self.clone / "vendor").mkdir()
        self.worktree.mkdir()
        (self.worktree / "node_modules").mkdir()  # already there: left alone

    def tearDown(self):
        self.tmp.cleanup()

    def test_copies_local_settings_and_links_the_rest(self):
        project.prepare(self.clone, self.worktree, [".env", "vendor", "node_modules", "missing"])
        settings = self.worktree / ".claude" / "settings.local.json"
        self.assertFalse(settings.is_symlink())
        self.assertIn("enableAllProjectMcpServers", settings.read_text())
        self.assertEqual(os.readlink(self.worktree / ".env"), str(self.clone / ".env"))
        self.assertEqual(os.readlink(self.worktree / "vendor"), str(self.clone / "vendor"))
        self.assertFalse((self.worktree / "node_modules").is_symlink())
        self.assertFalse((self.worktree / "missing").exists())
        project.prepare(self.clone, self.worktree, [".env"])  # round 2: no error, still linked
        self.assertTrue((self.worktree / ".env").is_symlink())

    def test_links_validation(self):
        self.assertEqual(config.validate({"worktree_links": [".env", "storage/app"]}), [])
        self.assertIn("worktree_links", config.validate({"worktree_links": ["../secret"]})[0])
        self.assertIn("worktree_links", config.validate({"worktree_links": "vendor"})[0])
