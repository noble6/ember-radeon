"""ember-update: installs new Ember releases. Run as root by ember-update.service.

    ember-update.py --auto      timer run: only acts if automatic updates are on
    ember-update.py             "Update now" from the app: always checks
    ember-update.py --dry-run   download, verify and unpack, but don't install
"""
from __future__ import annotations

import compileall
import json
import os
import shutil
import socket
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


ROLLED_BACK = 3      # install.sh: the service did not start, the previous version was restored


def service_version(timeout: float = 2.0) -> str | None:
    """Version the running service reports, or None if it does not answer."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(os.environ.get("EMBER_SOCKET", "/run/ember/emberd.sock"))
        s.sendall(b'{"cmd":"hello"}\n')
        buf = b""
        while not buf.endswith(b"\n") and len(buf) < 65536:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf).get("version")
    except (OSError, ValueError, AttributeError):
        return None
    finally:
        s.close()


def wait_for_service(version: str, seconds: float = 20.0) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if service_version() == version:
            return True
        time.sleep(1.0)
    return False


def preflight(root: Path) -> None:
    """Refuse a release that cannot even load, before anything on the system changes."""
    if not compileall.compile_dir(str(root / "ember"), quiet=2, workers=1) or \
            not all(compileall.compile_file(str(root / f), quiet=2) for f in ("main.py", "emberd.py", "ember-update.py")):
        raise U.UpdateError("release does not compile on this Python")
    try:
        r = subprocess.run([sys.executable, "-I", str(root / "emberd.py"), "--self-test"],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        raise U.UpdateError(f"release self-test did not run: {e}") from None
    if r.returncode != 0:
        tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or ["no output"]
        raise U.UpdateError("release failed its self-test: " + tail[0][:200])


def remember_failed(version: str) -> None:
    try:
        U.SKIP.write_text(json.dumps({"version": version}))
        os.chmod(U.SKIP, 0o644)
    except OSError:
        pass


def roll_back(reason: str, failed: str, previous: str | None) -> bool:
    """Put the previous version back by running *its* installer. True on success."""
    script = U.PREVIOUS_LIB / "install.sh"
    if not script.exists():
        return False
    r = subprocess.run(["/bin/bash", str(script), "--rollback"], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        return False
    remember_failed(failed)
    status("rolled-back", current=previous or U.installed_version(), failed=failed, error=reason)
    return True


def run(auto: bool, dry_run: bool) -> int:
    if auto and not U.auto_enabled():
        print("ember-update: automatic updates are off")
        return 0
    if auto and not U.check_due(U.read_json(U.STATUS, {}).get("time")):
        print(f"ember-update: next {U.interval()} check is not due yet")
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
    if rel["version"] == U.skipped_version():
        if auto:
            # This release was installed before, did not work here and was rolled back.
            status("skipped", current=current, latest=rel["version"],
                   error=f"version {rel['version']} was rolled back on this machine; waiting for the next release")
            return 0
        U.SKIP.unlink(missing_ok=True)     # "Update now": the user asks to try it again
    if not rel["tarball"] or not rel["checksum"]:
        status("error", current=current, latest=rel["version"], error="release has no verified download")
        return 1
    if not rel.get("signature"):
        status("error", current=current, latest=rel["version"], error="release is not signed")
        return 1

    status("downloading", current=current, latest=rel["version"])
    CACHE.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="update-", dir=CACHE))
    try:
        blob = U.download(rel["tarball"], timeout=120)
        U.verify(blob, U.download(rel["checksum"], timeout=30).decode(errors="replace"),
                 f"ember-radeon-{rel['version']}.tar.gz")
        U.verify_signature(blob, U.download(rel["signature"], timeout=30))   # nothing is unpacked before this
        archive = work / "release.tar.gz"
        archive.write_bytes(blob)
        root = U.safe_extract(archive, work / "src")
        if U.installed_version(root) != rel["version"]:
            raise U.UpdateError("archive version does not match the release")
        preflight(root)
        if dry_run:
            status("verified", current=current, latest=rel["version"], path=str(root))
            return 0
        status("installing", current=current, latest=rel["version"])
        was_running = service_version() is not None
        r = subprocess.run(["/bin/bash", str(root / "install.sh"), "--unattended"],
                           capture_output=True, text=True, timeout=600)
        if r.returncode == ROLLED_BACK:
            remember_failed(rel["version"])
            status("rolled-back", current=current, failed=rel["version"],
                   error="the service did not start after the update")
            return 1
        if r.returncode != 0:
            tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
            raise U.UpdateError("install failed: " + " / ".join(tail))
        # The service ran before: it must now answer as the new version, or we go back.
        if was_running and not wait_for_service(rel["version"]):
            why = "the service did not answer after the update"
            if roll_back(why, rel["version"], current):
                return 1
            raise U.UpdateError(why + ", and the previous version could not be restored")
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
