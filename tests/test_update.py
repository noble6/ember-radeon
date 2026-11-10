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


from ember.core import ed25519 as E  # noqa: E402


def ed_keypair(seed: bytes):
    """(public key, signer) for tests, built from the verifier's own curve arithmetic (RFC 8032)."""
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254

    def compress(pt):
        zi = E._inv(pt[2])
        x, y = pt[0] * zi % E._P, pt[1] * zi % E._P
        return (y | ((x & 1) << 255)).to_bytes(32, "little")
    pub = compress(E._mul(a, E._G))

    def sign(msg: bytes) -> bytes:
        r = int.from_bytes(hashlib.sha512(h[32:] + msg).digest(), "little") % E._L
        rs = compress(E._mul(r, E._G))
        k = int.from_bytes(hashlib.sha512(rs + pub + msg).digest(), "little") % E._L
        return rs + ((r + k * a) % E._L).to_bytes(32, "little")
    return pub, sign


TEST_PUB, test_sign = ed_keypair(b"\x01" * 32)
OTHER_PUB, other_sign = ed_keypair(b"\x02" * 32)


class UpdateTests(unittest.TestCase):
    def test_ed25519_rfc8032_vectors(self):
        h = bytes.fromhex
        pub = h("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        sig = h("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46b"
                "d25bf5f0595bbe24655141438e7a100b")
        self.assertTrue(E.verify(pub, b"", sig))
        self.assertFalse(E.verify(pub, b"x", sig))
        pub2 = h("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c")
        sig2 = h("92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c"
                 "387b2eaeb4302aeeb00d291612bb0c00")
        self.assertTrue(E.verify(pub2, h("72"), sig2))
        self.assertFalse(E.verify(pub, h("72"), sig2))                 # right signature, wrong key
        self.assertFalse(E.verify(pub2, h("72"), sig2[:63] + bytes([sig2[63] ^ 1])))
        for junk in (b"", b"\x00" * 64, b"\xff" * 64, sig2[:10]):     # malformed input never raises
            self.assertFalse(E.verify(pub2, h("72"), junk))
        self.assertFalse(E.verify(b"short", b"", sig))
        # the test signer agrees with the RFC key derivation
        rfc_pub, rfc_sign = ed_keypair(h("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"))
        self.assertEqual(rfc_pub, pub)
        self.assertEqual(rfc_sign(b""), sig)

    def test_release_signature(self):
        import base64
        keys = (base64.b64encode(TEST_PUB).decode(),)
        blob = b"release bytes"
        U.verify_signature(blob, test_sign(blob), keys)                              # raw
        U.verify_signature(blob, base64.b64encode(test_sign(blob)) + b"\n", keys)    # base64 text
        for bad in (other_sign(blob), test_sign(b"other bytes"), b"", b"not a signature"):
            with self.assertRaises(U.UpdateError):
                U.verify_signature(blob, bad, keys)
        with self.assertRaises(U.UpdateError):
            U.verify_signature(blob, test_sign(blob), ())                            # no trusted keys
        # the key shipped in the code is a well-formed Ed25519 public key
        for k in U.RELEASE_KEYS:
            self.assertIsNotNone(E._decompress(base64.b64decode(k)))

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

    def test_oversized_download_is_refused(self):
        import urllib.request

        class Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        orig, cap = urllib.request.urlopen, U.MAX_DOWNLOAD
        U.MAX_DOWNLOAD = 1000
        urllib.request.urlopen = lambda req, timeout=None: Resp(b"x" * 5000)
        try:
            with self.assertRaises(U.UpdateError):
                U._get("https://example.com/huge")
            urllib.request.urlopen = lambda req, timeout=None: Resp(b"x" * 900)
            self.assertEqual(len(U._get("https://example.com/ok")), 900)
        finally:
            urllib.request.urlopen, U.MAX_DOWNLOAD = orig, cap

    def test_install_kind(self):
        self.assertEqual(U.install_kind(Path("/usr/local/lib/ember")), "local")
        self.assertEqual(U.install_kind(Path("/usr/lib/ember")), "package")
        self.assertEqual(U.install_kind(Path(tempfile.mkdtemp())), "source")

    def _run_updater(self, blob, checksum, current="1.0.0", args=(), auto_setting=None, sig="good"):
        from ember import updater
        d = Path(tempfile.mkdtemp())
        U.STATE_DIR, U.STATUS, U.SETTINGS = d, d / "update-status.json", d / "update.json"
        if auto_setting is not None:
            U.SETTINGS.write_text(json.dumps({"auto": auto_setting}))
        updater.CACHE = d / "cache"
        os.environ["EMBER_CURRENT_VERSION"] = current
        os.environ["MARKER"] = str(d / "marker")
        rel = {"version": "9.9.9", "tag": "v9.9.9", "url": "https://x", "notes": "", "prerelease": False,
               "draft": False, "tarball": "https://x/ember-radeon-9.9.9.tar.gz", "checksum": "https://x/sum",
               "signature": None if sig is None else "https://x/sig"}
        import base64
        sig_bytes = {"good": test_sign(blob), "other-key": other_sign(blob), None: b""}.get(sig, sig)
        orig = (U.latest_release, U._get, U.RELEASE_KEYS)
        U.latest_release = lambda: rel
        U.RELEASE_KEYS = (base64.b64encode(TEST_PUB).decode(),)
        U._get = lambda url, timeout=20, accept=None: (blob if url.endswith(".tar.gz") else
                                                       sig_bytes if url.endswith("/sig") else checksum.encode())
        try:
            rc = updater.run(auto="--auto" in args, dry_run="--dry-run" in args)
        finally:
            U.latest_release, U._get, U.RELEASE_KEYS = orig
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

    def test_unsigned_or_wrongly_signed_release_is_not_installed(self):
        blob = make_tar(GOOD)
        good_sum = hashlib.sha256(blob).hexdigest() + "  x\n"
        # An attacker who controls the release page can publish any tarball with a matching checksum.
        for sig, expect in ((None, "not signed"), ("other-key", "trusted key"), (b"garbage", "malformed"),
                            (test_sign(b"an older release"), "trusted key")):
            rc, st, d = self._run_updater(blob, good_sum, sig=sig)
            self.assertEqual((rc, st["state"]), (1, "error"), sig)
            self.assertIn(expect, st["error"])
            self.assertFalse((d / "marker").exists(), sig)          # install.sh never ran

    def test_up_to_date_and_auto_off(self):
        blob = make_tar(GOOD)
        rc, st, d = self._run_updater(blob, "", current="9.9.9")
        self.assertEqual(st["state"], "up-to-date")
        rc, st, d = self._run_updater(blob, "", args=("--auto",), auto_setting=False)
        self.assertEqual(st, {})                       # timer run with auto off does nothing
        self.assertFalse((d / "marker").exists())


if __name__ == "__main__":
    unittest.main()
