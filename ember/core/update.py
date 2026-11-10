"""Release checks and safe unpacking, shared by the app and the root updater.

Releases come from GitHub. Each release carries `ember-radeon-<version>.tar.gz`,
a `.sha256` and a `.sig`. An update is installed only when the tarball carries a
valid Ed25519 signature from a release key built into this file. The checksum
catches broken downloads; the signature is what establishes trust, because the
signing key is never stored on GitHub: taking over the repository or the account
is not enough to push code to existing installs.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from ember.core import ed25519

REPO = "noble6/ember-radeon"
# Ed25519 public keys (base64) allowed to sign releases. More than one allows key rotation:
# ship the new key in a release signed by the old one, then start signing with the new key.
RELEASE_KEYS = ("VKBEK2AP/+pXWzjdnTDD/DRf6RVIcJ454/1S+hGyVvs=",)
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
USER_AGENT = "ember-updater"
LOCAL_LIB = Path("/usr/local/lib/ember")      # where install.sh puts Ember
STATE_DIR = Path(os.environ.get("EMBER_STATE_DIR", "/var/lib/ember"))
SETTINGS = STATE_DIR / "update.json"           # {"auto": bool}, written by emberd
STATUS = STATE_DIR / "update-status.json"      # written by the updater, read by the app
RETRY_DELAY = 5.0                              # seconds; grows with each retry
MAX_DOWNLOAD = 64 * 1024 * 1024                # a release is about 1 MB; refuse anything absurd


class UpdateError(RuntimeError):
    pass


def parse_version(v: str) -> tuple:
    m = re.match(r"^v?(\d+)\.(\d+)(?:\.(\d+))?", (v or "").strip())
    if not m:
        return (0, 0, 0)
    return tuple(int(x or 0) for x in m.groups())


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def installed_version(lib: Path = LOCAL_LIB) -> str | None:
    """Version of the Ember installed by install.sh (None if not installed that way)."""
    try:
        text = (lib / "ember" / "__init__.py").read_text()
    except OSError:
        return None
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else None


def install_kind(running_from: Path) -> str:
    """'local' (install.sh: Ember updates itself), 'package' (distro/AUR: the package
    manager updates it) or 'source' (running from a git checkout)."""
    p = running_from.resolve()
    if LOCAL_LIB in p.parents or p == LOCAL_LIB:
        return "local"
    if str(p).startswith("/usr/lib/") or str(p).startswith("/usr/share/"):
        return "package"
    return "source"


def _get(url: str, timeout: float = 20.0, accept: str = "application/vnd.github+json") -> bytes:
    if not url.startswith("https://"):
        raise UpdateError("refusing a non-HTTPS URL")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:   # verifies TLS certificates
                data = r.read(MAX_DOWNLOAD + 1)
            if len(data) > MAX_DOWNLOAD:
                raise UpdateError("download is larger than any Ember release should be")
            return data
        except urllib.error.HTTPError as e:
            last = e
            if e.code < 500 and e.code != 429:   # 4xx won't fix itself; 5xx and rate limits might
                break
        except OSError as e:
            last = e
        time.sleep(RETRY_DELAY * (attempt + 1))
    raise UpdateError(f"download failed: {last}")


def parse_release(data: dict) -> dict:
    """Pick the tarball and checksum assets out of a GitHub release object."""
    tag = data.get("tag_name") or ""
    version = tag.lstrip("v")
    # Prefer the API download endpoint (api.github.com); the github.com web link is the fallback.
    assets = {a.get("name"): [u for u in (a.get("url"), a.get("browser_download_url")) if u]
              for a in data.get("assets") or []}
    tar_name = f"ember-radeon-{version}.tar.gz"
    return {
        "version": version,
        "tag": tag,
        "name": data.get("name") or tag,
        "url": data.get("html_url") or RELEASES_PAGE,
        "notes": (data.get("body") or "")[:4000],
        "published": data.get("published_at"),
        "tarball": assets.get(tar_name),
        "checksum": assets.get(tar_name + ".sha256"),
        "signature": assets.get(tar_name + ".sig"),
        "prerelease": bool(data.get("prerelease")),
        "draft": bool(data.get("draft")),
    }


def download(urls, timeout: float = 120.0) -> bytes:
    """Fetch a release asset, trying each mirror URL in turn."""
    if isinstance(urls, str):
        urls = [urls]
    last = None
    for u in urls or []:
        try:
            return _get(u, timeout=timeout, accept="application/octet-stream")
        except UpdateError as e:
            last = e
    raise last or UpdateError("no download URL")


def latest_release() -> dict:
    try:
        data = json.loads(_get(API_LATEST, timeout=15))
    except ValueError:
        raise UpdateError("bad reply from GitHub") from None
    return parse_release(data)


def verify(blob: bytes, checksum_text: str, name: str) -> None:
    """checksum_text is `sha256sum` output: '<hex>  <file name>'."""
    m = re.match(r"^\s*([0-9a-fA-F]{64})\b", checksum_text or "")
    if not m:
        raise UpdateError("checksum file is malformed")
    got = hashlib.sha256(blob).hexdigest()
    if got.lower() != m.group(1).lower():
        raise UpdateError(f"checksum mismatch for {name}")


def verify_signature(blob: bytes, sig: bytes, keys=None) -> None:
    """Raise unless `sig` is a valid signature of `blob` by one of the release keys.
    `sig` is the 64 raw bytes, or their base64 text."""
    keys = RELEASE_KEYS if keys is None else keys
    raw = sig
    if len(raw) != 64:
        try:
            raw = base64.b64decode(sig.strip(), validate=True)
        except (binascii.Error, ValueError):
            raw = b""
    if len(raw) != 64:
        raise UpdateError("release signature is malformed")
    for k in keys:
        try:
            pub = base64.b64decode(k, validate=True)
        except (binascii.Error, ValueError):
            continue
        if ed25519.verify(pub, blob, raw):
            return
    raise UpdateError("release signature does not match a trusted key")


def safe_extract(archive: Path, dest: Path) -> Path:
    """Unpack a release tarball, refusing anything that escapes `dest`.
    Returns the single top-level directory inside it."""
    dest = dest.resolve()
    with tarfile.open(archive, "r:gz") as tf:
        members = tf.getmembers()
        for m in members:
            target = (dest / m.name).resolve()
            if dest != target and dest not in target.parents:
                raise UpdateError(f"unsafe path in archive: {m.name}")
            if m.issym() or m.islnk():
                link = (target.parent / m.linkname).resolve()
                if dest != link and dest not in link.parents:
                    raise UpdateError(f"unsafe link in archive: {m.name}")
            if m.isdev():
                raise UpdateError(f"device file in archive: {m.name}")
        try:
            tf.extractall(dest, filter="data")
        except TypeError:          # Python < 3.12 has no extraction filters; we checked above
            tf.extractall(dest)
    tops = {Path(m.name).parts[0] for m in members if m.name and Path(m.name).parts}
    if len(tops) != 1:
        raise UpdateError("archive must contain one top-level folder")
    root = dest / tops.pop()
    for needed in ("install.sh", "ember/__init__.py", "ember/daemon.py", "main.py"):
        if not (root / needed).exists():
            raise UpdateError(f"archive is missing {needed}")
    return root


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def auto_enabled() -> bool:
    return bool(read_json(SETTINGS, {}).get("auto", True))
