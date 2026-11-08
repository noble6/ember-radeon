"""Updater: version logic, release parsing, checksum and archive safety, and a full
offline update run against a fake release (no network, no root)."""
import hashlib
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ember.core import update as U  # noqa: E402


def make_tar(files: dict, top="ember-radeon-9.9.9", extra=None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, content in files.items():
            data = content.encode()
            ti = tarfile.TarInfo(f"{top}/{name}")
            ti.size = len(data)
            ti.mode = 0o755
            tf.addfile(ti, io.BytesIO(data))
        for ti in extra or []:
            tf.addfile(ti, io.BytesIO(b""))
    return buf.getvalue()


GOOD = {"install.sh": "#!/bin/bash\necho installed > \"$MARKER\"\n", "main.py": "",
        "ember/__init__.py": '__version__ = "9.9.9"\n', "ember/daemon.py": ""}


class UpdateTests(unittest.TestCase):
    def test_versions(self):
        self.assertTrue(U.is_newer("v1.10.0", "1.9.3"))
        self.assertTrue(U.is_newer("1.2", "1.1.9"))
        self.assertFalse(U.is_newer("1.2.0", "1.2.0"))
        self.assertFalse(U.is_newer("garbage", "1.0.0"))

    def test_parse_release(self):
        r = U.parse_release({"tag_name": "v1.2.0", "assets": [
            {"name": "ember-radeon-1.2.0.tar.gz", "url": "https://api/1", "browser_download_url": "https://x/a.tgz"},
            {"name": "ember-radeon-1.2.0.tar.gz.sha256", "browser_download_url": "https://x/a.sha"}]})
        self.assertEqual((r["version"], r["tarball"], r["checksum"]),
                         ("1.2.0", ["https://api/1", "https://x/a.tgz"], ["https://x/a.sha"]))
        self.assertIsNone(U.parse_release({"tag_name": "v2.0.0", "assets": []})["tarball"])

    def test_checksum(self):
        blob = b"hello"
        good = hashlib.sha256(blob).hexdigest() + "  f.tar.gz\n"
        U.verify(blob, good, "f")
        with self.assertRaises(U.UpdateError):
            U.verify(b"tampered", good, "f")
        with self.assertRaises(U.UpdateError):
            U.verify(blob, "not a checksum", "f")
        with self.assertRaises(U.UpdateError):
            U._get("http://example.com/plain-http")

    def test_safe_extract(self):
        d = Path(tempfile.mkdtemp())
        (d / "ok.tgz").write_bytes(make_tar(GOOD))
        root = U.safe_extract(d / "ok.tgz", d / "out")
        self.assertEqual(U.installed_version(root), "9.9.9")
        evil = tarfile.TarInfo("ember-radeon-9.9.9/../../escape")
        (d / "evil.tgz").write_bytes(make_tar(GOOD, extra=[evil]))
        with self.assertRaises(U.UpdateError):
            U.safe_extract(d / "evil.tgz", d / "out2")
        link = tarfile.TarInfo("ember-radeon-9.9.9/link")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        (d / "link.tgz").write_bytes(make_tar(GOOD, extra=[link]))
        with self.assertRaises(U.UpdateError):
            U.safe_extract(d / "link.tgz", d / "out3")
        (d / "partial.tgz").write_bytes(make_tar({"main.py": ""}))
        with self.assertRaises(U.UpdateError):
            U.safe_extract(d / "partial.tgz", d / "out4")

    def test_download_falls_back_to_mirror(self):
        calls = []
        orig = U._get

        def fake(url, timeout=20, accept=None):
            calls.append((url, accept))
            if "api" in url:
                raise U.UpdateError("504")
            return b"ok"
        U._get = fake
        try:
            self.assertEqual(U.download(["https://api/1", "https://web/1"]), b"ok")
        finally:
            U._get = orig
        self.assertEqual([c[0] for c in calls], ["https://api/1", "https://web/1"])
        self.assertEqual(calls[0][1], "application/octet-stream")

    def test_install_kind(self):
        self.assertEqual(U.install_kind(Path("/usr/local/lib/ember")), "local")
        self.assertEqual(U.install_kind(Path("/usr/lib/ember")), "package")
        self.assertEqual(U.install_kind(Path(tempfile.mkdtemp())), "source")

    def _run_updater(self, blob, checksum, current="1.0.0", args=(), auto_setting=None):
        from ember import updater
        d = Path(tempfile.mkdtemp())
        U.STATE_DIR, U.STATUS, U.SETTINGS = d, d / "update-status.json", d / "update.json"
        if auto_setting is not None:
            U.SETTINGS.write_text(json.dumps({"auto": auto_setting}))
        updater.CACHE = d / "cache"
        os.environ["EMBER_CURRENT_VERSION"] = current
        os.environ["MARKER"] = str(d / "marker")
        rel = {"version": "9.9.9", "tag": "v9.9.9", "url": "https://x", "notes": "", "prerelease": False,
               "draft": False, "tarball": "https://x/ember-radeon-9.9.9.tar.gz", "checksum": "https://x/sum"}
        orig = (U.latest_release, U._get)
        U.latest_release = lambda: rel
        U._get = lambda url, timeout=20, accept=None: blob if url.endswith(".tar.gz") else checksum.encode()
        try:
            rc = updater.run(auto="--auto" in args, dry_run="--dry-run" in args)
        finally:
            U.latest_release, U._get = orig
            del os.environ["EMBER_CURRENT_VERSION"]
        return rc, json.loads(U.STATUS.read_text()) if U.STATUS.exists() else {}, d

    def test_full_update_installs_verified_release(self):
        blob = make_tar(GOOD)
        rc, st, d = self._run_updater(blob, hashlib.sha256(blob).hexdigest() + "  x\n")
        self.assertEqual(rc, 0)
        self.assertEqual((st["state"], st["current"]), ("updated", "9.9.9"))
        self.assertEqual((d / "marker").read_text().strip(), "installed")   # install.sh ran

    def test_tampered_release_is_not_installed(self):
        blob = make_tar(GOOD)
        rc, st, d = self._run_updater(blob, hashlib.sha256(b"other").hexdigest() + "  x\n")
        self.assertEqual(rc, 1)
        self.assertEqual(st["state"], "error")
        self.assertIn("checksum", st["error"])
        self.assertFalse((d / "marker").exists())

    def test_up_to_date_and_auto_off(self):
        blob = make_tar(GOOD)
        rc, st, d = self._run_updater(blob, "", current="9.9.9")
        self.assertEqual(st["state"], "up-to-date")
        rc, st, d = self._run_updater(blob, "", args=("--auto",), auto_setting=False)
        self.assertEqual(st, {})                       # timer run with auto off does nothing
        self.assertFalse((d / "marker").exists())


if __name__ == "__main__":
    unittest.main()
