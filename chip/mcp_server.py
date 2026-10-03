"""`chip mcp`: a stdio MCP server exposing each waiting PR as a resource.

Claude Code lists MCP resources in the `@` autocomplete of the prompt bar (fuzzy-searchable), so
typing `/chip @` + a few letters picks PRs without leaving the input line.
"""
from __future__ import annotations

import json
import re
import sys
import threading
from typing import Callable, List, Optional

from chip import config
from chip.render import STATUS_LABEL
from chip.tui import preview_text

DEFAULT_PROTOCOL = "2025-06-18"
REFRESH_SECONDS = 300
URI_RE = re.compile(r"pr://([A-Za-z0-9._-]+?)/(\d+)")


def _slug(text: str, width: int = 48) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:width].strip("-")


def resource_uri(r: dict) -> str:
    """`pr://<repo>/<number>-<title-slug>`; `owner/repo` labels become `owner--repo`."""
    repo_part = r["label"].split("#")[0].replace("/", "--")
    return f"pr://{repo_part}/{r['number']}-{_slug(r['title'])}"


def labels_in(text: str) -> List[str]:
    """Row labels (`repo#N`) for every `pr://` resource mentioned in text, in order."""
    return [f"{repo.replace('--', '/')}#{number}" for repo, number in URI_RE.findall(text)]


def _resource(r: dict) -> dict:
    description = " · ".join(x for x in (r["wait"], STATUS_LABEL[r["status"]], r["author"], r["jira"]) if x)
    return {
        "uri": resource_uri(r),
        "name": f"{r['label']} {r['title']}",
        "description": description,
        "mimeType": "text/plain",
    }


def handle(msg: dict, inbox: dict) -> Optional[dict]:
    """Answer one JSON-RPC message; None for notifications."""
    if "id" not in msg:
        return None
    method, params = msg.get("method"), msg.get("params") or {}

    def ok(result):
        return {"jsonrpc": "2.0", "id": msg["id"], "result": result}

    def err(code, message):
        return {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": code, "message": message}}

    if method == "initialize":
        return ok({
            "protocolVersion": params.get("protocolVersion", DEFAULT_PROTOCOL),
            "capabilities": {"resources": {"listChanged": True}},
            "serverInfo": {"name": "chip", "version": "1.0.0"},
            "instructions": "PRs waiting for the user's review. Mention them with @chip:pr://… and review with /chip.",
        })
    if method == "ping":
        return ok({})
    if method == "resources/list":
        return ok({"resources": [_resource(r) for r in inbox["rows"]]})
    if method == "resources/templates/list":
        return ok({"resourceTemplates": []})
    if method == "tools/list":
        return ok({"tools": []})
    if method == "prompts/list":
        return ok({"prompts": []})
    if method == "resources/read":
        uri = params.get("uri", "")
        wanted = labels_in(uri)
        for r in inbox["rows"]:
            if wanted and r["label"] == wanted[0]:
                prompt = config.fill_prompt(config.load()["skills"][0], r)
                text = preview_text(r) + f"\n\nReview: {prompt}"
                return ok({"contents": [{"uri": uri, "mimeType": "text/plain", "text": text}]})
        return err(-32002, f"PR {uri} is not in the review inbox")
    return err(-32601, f"method not found: {method}")


def serve(initial: dict, refresh: Callable[[], Optional[dict]]) -> None:
    """Run the stdio loop; a background thread refreshes the inbox and announces list changes."""
    state = {"inbox": initial}
    write_lock = threading.Lock()

    def send(payload: dict) -> None:
        with write_lock:
            sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
            sys.stdout.flush()

    def refresher() -> None:
        stop = threading.Event()
        while True:
            inbox = refresh()
            if inbox is not None:
                state["inbox"] = inbox
                send({"jsonrpc": "2.0", "method": "notifications/resources/list_changed"})
            if stop.wait(REFRESH_SECONDS):
                return

    threading.Thread(target=refresher, daemon=True).start()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        reply = handle(msg, state["inbox"])
        if reply is not None:
            send(reply)
