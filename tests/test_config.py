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
        self.assertEqual(cfg["skills"], [])  # each user adds their own; empty means "project or built-in review"
        self.assertEqual(config.review_skills(cfg), [config.DEFAULT_SKILL])
        self.assertEqual(cfg["errors"], [])
        self.assertEqual((cfg["work_roots"], cfg["clone_root"]), ([], ""))  # detected / ~/.cache/chip/repos
        self.assertEqual(cfg["permission_mode"], "auto")
        self.assertEqual(cfg["disallowed_tools"], ["Edit", "Write", "NotebookEdit"])
        self.assertEqual(cfg["terminal"], "Terminal")

    def test_merges_user_values(self):
        self.write({"skills": [{"name": "A", "prompt": "/a {url}"}, {"name": "B", "prompt": "/b {repo} {number}"}],
                    "work_root": "~/src"})
        cfg = config.load(self.path)
        self.assertEqual([s["name"] for s in cfg["skills"]], ["A", "B"])
        self.assertEqual(cfg["work_roots"], [os.path.expanduser("~/src")])  # the old single key still works
        self.assertEqual(cfg["permission_mode"], "auto")

    def test_work_roots_list_and_clone_root(self):
        self.write({"work_roots": ["~/code", "~/Projects"], "work_root": "~/code", "clone_root": "~/clones"})
        cfg = config.load(self.path)
        self.assertEqual(cfg["work_roots"], [os.path.expanduser("~/code"), os.path.expanduser("~/Projects")])
        self.assertEqual(cfg["clone_root"], os.path.expanduser("~/clones"))
        self.write({"work_roots": "~/code"})
        self.assertIn("work_roots", config.load(self.path)["errors"][0])

    def test_bad_json_falls_back_to_defaults(self):
        self.write("{nope")
        cfg = config.load(self.path)
        self.assertEqual(cfg["skills"], [])
        self.assertIn("invalid JSON", cfg["errors"][0])

    def test_unknown_placeholder(self):
        self.write({"skills": [{"name": "A", "prompt": "/a {pr}"}]})
        cfg = config.load(self.path)
        self.assertIn("unknown placeholder", cfg["errors"][0])
        self.assertEqual(cfg["skills"], [])

    def test_duplicate_and_empty_skills(self):
        self.write({"skills": [{"name": "A", "prompt": "x"}, {"name": "A", "prompt": "y"}]})
        self.assertIn("unique", config.load(self.path)["errors"][0])
        self.write({"skills": []})
        self.assertEqual(config.load(self.path)["errors"], [])  # empty skills are allowed
        self.write({"address_skills": []})
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
        written = json.loads(self.path.read_text())
        self.assertEqual(written["skills"], [])
        self.assertEqual(written["address_skills"][0]["name"], "Address review")

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


class HiddenProjectsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_and_validation(self):
        self.assertEqual(config.load(self.path)["hidden_projects"], [])
        self.path.write_text(json.dumps({"hidden_projects": "loyalty"}))
        self.assertIn("hidden_projects", config.load(self.path)["errors"][0])

    def test_toggle_and_show_all(self):
        self.path.write_text(json.dumps({"work_root": "~/src"}))
        config.toggle_project("loyalty-partners", self.path)
        config.toggle_project("api", self.path)
        self.assertEqual(config.load(self.path)["hidden_projects"], ["loyalty-partners", "api"])
        config.toggle_project("loyalty-partners", self.path)
        self.assertEqual(config.load(self.path)["hidden_projects"], ["api"])
        config.show_all_projects(self.path)
        data = json.loads(self.path.read_text())
        self.assertEqual((data["hidden_projects"], data["work_root"]), ([], "~/src"))


class AppliesTest(unittest.TestCase):
    PHP = {"repo": "acme/api", "language": "PHP"}
    SWIFT = {"repo": "globex/shop-ios", "language": "Swift"}

    def test_no_scope_applies_everywhere(self):
        self.assertTrue(config.applies({"name": "A", "prompt": "x"}, self.SWIFT))

    def test_repos_patterns(self):
        skill = {"name": "A", "prompt": "x", "repos": ["acme/*", "*-ios"]}
        self.assertTrue(config.applies(skill, self.PHP))
        self.assertTrue(config.applies(skill, self.SWIFT))
        self.assertFalse(config.applies(skill, {"repo": "globex/web", "language": "TypeScript"}))
        self.assertTrue(config.applies({"name": "A", "prompt": "x", "repos": ["API"]}, self.PHP))  # bare repo name

    def test_languages_and_both_must_match(self):
        php = {"name": "A", "prompt": "x", "languages": ["php"]}
        self.assertTrue(config.applies(php, self.PHP))
        self.assertFalse(config.applies(php, self.SWIFT))
        both = dict(php, repos=["globex/*"])
        self.assertFalse(config.applies(both, self.PHP))

    def test_skills_for_falls_back_to_builtin(self):
        cfg = {"skills": [{"name": "Laravel", "prompt": "/laravel {url}", "languages": ["PHP"]}]}
        self.assertEqual([s["name"] for s in config.skills_for(cfg, self.PHP)], ["Laravel"])
        self.assertEqual(config.skills_for(cfg, self.SWIFT), [config.DEFAULT_SKILL])

    def test_scope_validation(self):
        self.assertIn("repos must be a list", config.validate({"skills": [{"name": "A", "prompt": "x", "repos": "api"}]})[0])
        self.assertEqual(config.validate({"skills": [{"name": "A", "prompt": "x", "languages": ["Swift"]}]}), [])


class TemplateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_config_has_help_and_examples_and_loads_clean(self):
        config.init(self.path)
        data = json.loads(self.path.read_text())
        self.assertEqual(list(data)[:5], ["_help", "work_roots", "clone_root", "skills", "_skill_examples"])
        self.assertEqual(data["skills"], [])
        self.assertEqual(data["_skill_examples"], config.EXAMPLE_SKILLS)
        cfg = config.load(self.path)
        self.assertEqual((cfg["errors"], cfg["skills"]), ([], []))
        self.assertNotIn("_help", cfg)

    def test_examples_survive_menu_settings(self):
        config.init(self.path)
        config.set_value("status_style", "emoji", self.path)
        self.assertIn("_skill_examples", json.loads(self.path.read_text()))

    def test_example_file_in_repo_matches(self):
        example = Path(__file__).resolve().parents[1] / "config.example.json"
        self.assertEqual(json.loads(example.read_text()), config.example())
        self.assertEqual(config.validate(config.example()), [])
