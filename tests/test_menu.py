import unittest

from chip import model
from chip.menu import PER_PAGE, assign_labels, build_page


def row(i, repo="acme/shopbox-api", **overrides):
    base = {
        "index": i, "repo": repo, "number": 100 + i, "title": f"feat: thing {i}",
        "url": f"https://github.com/{repo}/pull/{100 + i}", "author": "alice", "wait": "2d",
        "status": model.NEW, "decision": "-", "size": "+1/-0 1f", "ci": "-", "conflict": False,
        "base": "dev", "stacked": False, "jira": "", "draft": False,
    }
    base.update(overrides)
    return base


def rows(n):
    return assign_labels([row(i) for i in range(1, n + 1)])


def pr_questions(page):
    return [q for q in page["questions"] if q["multiSelect"]]


class LabelTest(unittest.TestCase):
    def test_short_repo_name(self):
        self.assertEqual(rows(1)[0]["label"], "shopbox-api#101")

    def test_full_name_when_short_names_collide(self):
        labelled = assign_labels([row(1, repo="acme/api"), row(2, repo="globex/api"), row(3)])
        self.assertEqual([r["label"] for r in labelled], ["acme/api#101", "globex/api#102", "shopbox-api#103"])


class BuildPageTest(unittest.TestCase):
    def test_first_page_has_three_pr_questions_and_nav(self):
        page = build_page(rows(39), 1)
        self.assertEqual((page["page"], page["pages"], page["total"]), (1, 4, 39))
        self.assertEqual([len(q["options"]) for q in pr_questions(page)], [4, 4, 4])
        nav = page["questions"][-1]
        self.assertFalse(nav["multiSelect"])
        self.assertEqual([o["label"] for o in nav["options"]], ["Review các PR đã chọn", "Xem trang tiếp"])
        self.assertEqual(nav["header"], "Trang 1/4")

    def test_last_page_has_no_nav(self):
        page = build_page(rows(39), 4)
        self.assertEqual([len(q["options"]) for q in page["questions"]], [3])
        self.assertTrue(page["questions"][0]["multiSelect"])

    def test_option_content(self):
        r = row(1, title="fix(orders): only require a customer", status=model.REREVIEW,
                stacked=True, base="feature/a", conflict=True, jira="MYS-1", decision="CHANGES_REQ 1✗")
        option = build_page(assign_labels([r, row(2)]), 1)["questions"][0]["options"][0]
        self.assertEqual(option["label"], "shopbox-api#101")
        self.assertEqual(
            option["description"],
            "fix(orders): only require a customer · alice · 2d · cần re-review · CHANGES_REQ 1✗"
            " · +1/-0 1f · feature/a (stacked) · conflict · MYS-1",
        )

    def test_question_text_and_header(self):
        q = pr_questions(build_page(rows(39), 2))[0]
        self.assertEqual(q["question"], "Chọn PR để review (13–16 / 39)")
        self.assertEqual(q["header"], "PR 13-16")

    def test_no_single_option_question(self):
        for n in (5, 9, 13):
            page = build_page(rows(n), (n - 1) // PER_PAGE + 1)
            with self.subTest(n=n):
                self.assertTrue(all(len(q["options"]) >= 2 for q in page["questions"]))

    def test_single_pr_gets_skip_option(self):
        options = build_page(rows(1), 1)["questions"][0]["options"]
        self.assertEqual([o["label"] for o in options], ["shopbox-api#101", "Không chọn"])

    def test_page_out_of_range(self):
        with self.assertRaises(ValueError):
            build_page(rows(3), 2)
