import unittest

from chip import mcp_server, model
from chip.menu import assign_labels


def row(i, repo="acme/shopbox-api", **overrides):
    base = {
        "index": i, "repo": repo, "number": 270 + i, "title": "fix(orders): only require a customer!",
        "url": f"https://github.com/{repo}/pull/{270 + i}", "author": "alice", "wait": "1h",
        "status": model.NEW, "decision": "-", "size": "+57/-7 2f", "ci": "-", "conflict": False,
        "base": "dev", "stacked": False, "jira": "MYS-9", "draft": False, "stale": False,
    }
    base.update(overrides)
    return base


INBOX = {"viewer": "me", "rows": assign_labels([row(4), row(5, repo="acme/api", status=model.REREVIEW)]),
         "hidden": {"approved": 0, "draft": 0}}


class UriTest(unittest.TestCase):
    def test_uri_has_repo_number_and_title_slug(self):
        self.assertEqual(mcp_server.resource_uri(INBOX["rows"][0]),
                         "pr://shopbox-api/274-fix-orders-only-require-a-customer")

    def test_label_from_uri_or_mention(self):
        for text in ("pr://shopbox-api/274-fix-orders", "@chip:pr://shopbox-api/274-fix-orders"):
            self.assertEqual(mcp_server.labels_in(text), ["shopbox-api#274"])
        self.assertEqual(mcp_server.labels_in("@chip:pr://api/275-x and @chip:pr://shopbox-api/274-y"),
                         ["api#275", "shopbox-api#274"])

    def test_owner_collision_label_roundtrip(self):
        r = assign_labels([row(1, repo="acme/api"), row(2, repo="globex/api")])[1]
        uri = mcp_server.resource_uri(r)
        self.assertTrue(uri.startswith("pr://globex--api/272-"))
        self.assertEqual(mcp_server.labels_in(uri), ["globex/api#272"])


class HandleTest(unittest.TestCase):
    def call(self, method, params=None):
        return mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}, INBOX)

    def test_initialize_advertises_resources(self):
        result = self.call("initialize", {"protocolVersion": "2025-06-18"})["result"]
        self.assertEqual(result["capabilities"]["resources"], {"listChanged": True})
        self.assertEqual(result["serverInfo"]["name"], "chip")
        self.assertEqual(result["protocolVersion"], "2025-06-18")

    def test_list(self):
        resources = self.call("resources/list")["result"]["resources"]
        self.assertEqual([r["uri"] for r in resources], [
            "pr://shopbox-api/274-fix-orders-only-require-a-customer",
            "pr://api/275-fix-orders-only-require-a-customer",
        ])
        self.assertEqual(resources[1]["name"], "api#275 fix(orders): only require a customer!")
        self.assertIn("Re-review", resources[1]["description"])
        self.assertEqual(resources[0]["mimeType"], "text/plain")

    def test_read(self):
        uri = "pr://api/275-fix-orders-only-require-a-customer"
        contents = self.call("resources/read", {"uri": uri})["result"]["contents"]
        self.assertEqual(contents[0]["uri"], uri)
        self.assertIn("https://github.com/acme/api/pull/275", contents[0]["text"])
        self.assertIn("/my-review-skill", contents[0]["text"])

    def test_read_unknown(self):
        self.assertIn("error", self.call("resources/read", {"uri": "pr://nope/1-x"}))

    def test_notification_gets_no_reply(self):
        self.assertIsNone(mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, INBOX))

    def test_unknown_method(self):
        self.assertEqual(self.call("tools/call")["error"]["code"], -32601)

    def test_empty_lists_for_tools_and_prompts(self):
        self.assertEqual(self.call("tools/list")["result"], {"tools": []})
        self.assertEqual(self.call("prompts/list")["result"], {"prompts": []})
        self.assertEqual(self.call("resources/templates/list")["result"], {"resourceTemplates": []})
