import json
import os
import tempfile
import unittest
from pathlib import Path

from chip import config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        self.path.write_text(data if isinstance(data, str) else json.dumps(data))

    def test_defaults_when_missing(self):
        cfg = config.load(self.path)
        self.assertEqual(cfg["skills"], [{"name": "Full review", "prompt": "/my-review-skill {url}"}])
        self.assertEqual(cfg["errors"], [])
        self.assertEqual(cfg["work_root"], os.path.expanduser("~/work"))
        self.assertEqual(cfg["permission_mode"], "auto")
        self.assertEqual(cfg["disallowed_tools"], ["Edit", "Write", "NotebookEdit"])
        self.assertEqual(cfg["terminal"], "Terminal")

    def test_merges_user_values(self):
        self.write({"skills": [{"name": "A", "prompt": "/a {url}"}, {"name": "B", "prompt": "/b {repo} {number}"}],
                    "work_root": "~/src"})
        cfg = config.load(self.path)
        self.assertEqual([s["name"] for s in cfg["skills"]], ["A", "B"])
        self.assertEqual(cfg["work_root"], os.path.expanduser("~/src"))
        self.assertEqual(cfg["permission_mode"], "auto")

    def test_bad_json_falls_back_to_defaults(self):
        self.write("{nope")
        cfg = config.load(self.path)
        self.assertEqual(cfg["skills"][0]["name"], "Full review")
        self.assertIn("invalid JSON", cfg["errors"][0])

    def test_unknown_placeholder(self):
        self.write({"skills": [{"name": "A", "prompt": "/a {pr}"}]})
        cfg = config.load(self.path)
        self.assertIn("unknown placeholder", cfg["errors"][0])
        self.assertEqual(cfg["skills"][0]["name"], "Full review")

    def test_duplicate_and_empty_skills(self):
        self.write({"skills": [{"name": "A", "prompt": "x"}, {"name": "A", "prompt": "y"}]})
        self.assertIn("unique", config.load(self.path)["errors"][0])
        self.write({"skills": []})
        self.assertIn("non-empty", config.load(self.path)["errors"][0])

    def test_bad_terminal(self):
        self.write({"terminal": "Warp"})
        self.assertIn("terminal", config.load(self.path)["errors"][0])

    def test_fill_prompt(self):
        row = {"url": "https://github.com/o/r/pull/7", "repo": "o/r", "number": 7, "label": "r#7", "title": "Fix it"}
        skill = {"name": "A", "prompt": "/x {url} {repo} {number} {label} {title}"}
        self.assertEqual(config.fill_prompt(skill, row), "/x https://github.com/o/r/pull/7 o/r 7 r#7 Fix it")

    def test_init_writes_once(self):
        self.assertTrue(config.init(self.path))
        self.assertFalse(config.init(self.path))
        self.assertEqual(json.loads(self.path.read_text())["skills"][0]["name"], "Full review")

    def test_env_path(self):
        self.assertTrue(str(config.config_path()).endswith("no-such-config.json"))


class StatusStyleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_is_dots(self):
        self.assertEqual(config.load(self.path)["status_style"], "dots")

    def test_bad_style(self):
        self.path.write_text(json.dumps({"status_style": "stars"}))
        self.assertIn("status_style", config.load(self.path)["errors"][0])

    def test_set_value_writes_and_keeps_other_keys(self):
        self.path.write_text(json.dumps({"work_root": "~/src"}))
        self.assertEqual(config.set_value("status_style", "emoji", self.path), [])
        data = json.loads(self.path.read_text())
        self.assertEqual((data["status_style"], data["work_root"]), ("emoji", "~/src"))

    def test_set_value_creates_file(self):
        self.assertEqual(config.set_value("status_style", "symbols", self.path), [])
        self.assertEqual(config.load(self.path)["status_style"], "symbols")

    def test_set_value_rejects_bad_value_and_unknown_key(self):
        self.assertTrue(config.set_value("status_style", "stars", self.path))
        self.assertTrue(config.set_value("skills", "x", self.path))
        self.assertFalse(self.path.exists())


class AddressSkillsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_address_skill_only_proposes(self):
        skill = config.load(self.path)["address_skills"][0]
        self.assertEqual(skill["name"], "Address review")
        self.assertIn("{url}", skill["prompt"])
        self.assertIn("Do not edit files, commit, push, or post anything", skill["prompt"])

    def test_address_skills_validated_like_skills(self):
        self.path.write_text(json.dumps({"address_skills": [{"name": "A", "prompt": "/a {nope}"}]}))
        self.assertIn("address_skills[1] unknown placeholder", config.load(self.path)["errors"][0])
        self.path.write_text(json.dumps({"address_skills": []}))
        self.assertIn("address_skills must be a non-empty list", config.load(self.path)["errors"][0])

    def test_custom_address_skill(self):
        self.path.write_text(json.dumps({"address_skills": [{"name": "Fix plan", "prompt": "/my-fix {url}"}]}))
        self.assertEqual(config.load(self.path)["address_skills"], [{"name": "Fix plan", "prompt": "/my-fix {url}"}])
