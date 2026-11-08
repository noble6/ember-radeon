"""ember-update: installs new Ember releases. Run as root by ember-update.service.

    ember-update.py --auto      timer run: only acts if automatic updates are on
    ember-update.py             "Update now" from the app: always checks
    ember-update.py --dry-run   download, verify and unpack, but don't install
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ember.core import update as U

CACHE = Path(os.environ.get("EMBER_UPDATE_CACHE", "/var/cache/ember"))


def status(state: str, **kw) -> None:
    data = {"state": state, "time": time.time(), **kw}
    try:
        U.STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = U.STATUS.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        os.chmod(tmp, 0o644)
        os.replace(tmp, U.STATUS)
    except OSError:
        pass
    print(f"ember-update: {state} {kw if kw else ''}".rstrip(), flush=True)


def run(auto: bool, dry_run: bool) -> int:
    if auto and not U.auto_enabled():
        print("ember-update: automatic updates are off")
        return 0
    current = os.environ.get("EMBER_CURRENT_VERSION") or U.installed_version()
    if current is None and not dry_run:
        status("error", error="Ember is not installed with install.sh; update it with your package manager")
        return 1
    status("checking", current=current)
    try:
        rel = U.latest_release()
    except U.UpdateError as e:
        status("error", current=current, error=str(e))
        return 1
    if rel["draft"] or rel["prerelease"] or not U.is_newer(rel["version"], current or "0"):
        status("up-to-date", current=current, latest=rel["version"])
        return 0
    if not rel["tarball"] or not rel["checksum"]:
        status("error", current=current, latest=rel["version"], error="release has no verified download")
        return 1

    status("downloading", current=current, latest=rel["version"])
    CACHE.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="update-", dir=CACHE))
    try:
        blob = U.download(rel["tarball"], timeout=120)
        U.verify(blob, U.download(rel["checksum"], timeout=30).decode(errors="replace"),
                 f"ember-radeon-{rel['version']}.tar.gz")
        archive = work / "release.tar.gz"
        archive.write_bytes(blob)
        root = U.safe_extract(archive, work / "src")
        if U.installed_version(root) != rel["version"]:
            raise U.UpdateError("archive version does not match the release")
        if dry_run:
            status("verified", current=current, latest=rel["version"], path=str(root))
            return 0
        status("installing", current=current, latest=rel["version"])
        r = subprocess.run(["/bin/bash", str(root / "install.sh"), "--unattended"],
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
            raise U.UpdateError("install failed: " + " / ".join(tail))
        status("updated", previous=current, current=rel["version"], latest=rel["version"], url=rel["url"])
        return 0
    except U.UpdateError as e:
        status("error", current=current, latest=rel["version"], error=str(e))
        return 1
    finally:
        if not dry_run:
            shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    args = sys.argv[1:]
    return run(auto="--auto" in args, dry_run="--dry-run" in args)


if __name__ == "__main__":
    sys.exit(main())
