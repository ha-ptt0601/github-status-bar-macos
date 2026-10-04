import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from chip import repos


def make_repo(path: Path, remote: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "remote", "add", "origin", remote], check=True)
    return path


class NormalizeRemoteTest(unittest.TestCase):
    def test_forms(self):
        for url in (
            "git@github.com:Acme/Shopbox-API.git",
            "https://github.com/acme/shopbox-api",
            "https://github.com/acme/shopbox-api.git\n",
            "ssh://git@github.com/acme/shopbox-api.git",
            "https://github.com/acme/shopbox-api/",
        ):
            with self.subTest(url=url):
                self.assertEqual(repos.normalize_remote(url), "acme/shopbox-api")

    def test_non_github(self):
        self.assertIsNone(repos.normalize_remote("git@gitlab.com:a/b.git"))


class ScanResolveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "work"
        self.cache = Path(self.tmp.name) / "cache" / "repos.json"
        make_repo(self.root / "shopbox" / "shopbox-api", "git@github.com:acme/shopbox-api.git")
        make_repo(self.root / "a" / "b" / "c" / "too-deep", "git@github.com:acme/deep.git")
        make_repo(self.root / "x" / "node_modules" / "pkg", "git@github.com:acme/pkg.git")

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_respects_depth_and_skips(self):
        found = repos.scan(self.root)
        self.assertEqual(set(found), {"acme/shopbox-api"})

    def test_resolve_scans_and_caches(self):
        path = repos.resolve("acme/shopbox-api", self.root, self.cache)
        self.assertEqual(path, str(self.root / "shopbox" / "shopbox-api"))
        self.assertEqual(json.loads(self.cache.read_text())["acme/shopbox-api"], path)

    def test_resolve_drops_stale_cache(self):
        self.cache.parent.mkdir(parents=True)
        self.cache.write_text(json.dumps({"acme/shopbox-api": str(self.root / "gone")}))
        path = repos.resolve("acme/shopbox-api", self.root, self.cache)
        self.assertEqual(path, str(self.root / "shopbox" / "shopbox-api"))

    def test_resolve_finds_chip_clone_dir(self):
        make_repo(self.root / ".chip-repos" / "loyalty-api", "git@github.com:acme/loyalty-api.git")
        self.assertEqual(
            repos.resolve("acme/loyalty-api", self.root, self.cache),
            str(self.root / ".chip-repos" / "loyalty-api"),
        )

    def test_resolve_missing(self):
        self.assertIsNone(repos.resolve("acme/nope", self.root, self.cache))

    def test_clone(self):
        calls = []

        def runner(cmd, **kwargs):
            calls.append(cmd)
            make_repo(Path(cmd[-1]), "https://github.com/acme/loyalty-api.git")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        path = repos.clone("acme/loyalty-api", self.root, self.cache, runner=runner)
        self.assertEqual(path, str(self.root / ".chip-repos" / "loyalty-api"))
        self.assertEqual(calls[0][:4], ["gh", "repo", "clone", "acme/loyalty-api"])
        self.assertEqual(json.loads(self.cache.read_text())["acme/loyalty-api"], path)

    def test_clone_failure(self):
        def runner(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, "", "repository not found")

        with self.assertRaisesRegex(repos.CloneError, "not found"):
            repos.clone("acme/loyalty-api", self.root, self.cache, runner=runner)

    def test_clone_target_taken_by_other_repo(self):
        make_repo(self.root / ".chip-repos" / "api", "git@github.com:other/api.git")
        with self.assertRaisesRegex(repos.CloneError, "is not acme/api"):
            repos.clone("acme/api", self.root, self.cache, runner=None)
