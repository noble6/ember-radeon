"""Record & Instant Replay, built on gpu-screen-recorder.

gpu-screen-recorder captures the screen through the GPU's own video encoder
(VCN, via VA-API on AMD), so recording costs only a few FPS. Ember starts it,
talks to it over its JSON IPC socket, and files the clips per game.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

BIN = "gpu-screen-recorder"
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "ember"
SOCK = RUNTIME / "recorder.sock"
STATE = RUNTIME / "recorder.json"
LOG = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "ember" / "recorder.log"
VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov")
IMAGE_EXT = (".png", ".jpg")

# Constant bitrate (kbps) keeps the replay buffer's RAM use predictable.
REPLAY_BITRATE = {"medium": 12000, "high": 20000, "very_high": 35000, "ultra": 60000}

DEFAULTS = {
    "output_dir": str(Path(os.environ.get("XDG_VIDEOS_DIR", Path.home() / "Videos")) / "Ember"),
    "capture": "",             # monitor name (e.g. DP-1) or "portal"; "" = first monitor
    "fps": 60,
    "codec": "auto",           # auto | h264 | hevc | av1
    "quality": "very_high",    # medium | high | very_high | ultra
    "container": "mp4",        # mp4 | mkv
    "desktop_audio": True,
    "mic": False,
    "mic_separate": True,      # microphone on its own audio track
    "cursor": True,
    "replay_seconds": 60,
    "auto_replay": False,      # start the replay buffer when a game starts
    "per_game_folders": True,
}


REPLAY_RAM_LIMIT_MB = 1024   # bigger replay buffers go to disk instead of memory


class RecorderError(RuntimeError):
    pass


def _is_recorder(pid: int | None) -> bool:
    """True if `pid` is a gpu-screen-recorder process. Guards against a recycled PID:
    we must never signal some unrelated program that inherited the number."""
    if not pid:
        return False
    try:
        return Path(f"/proc/{int(pid)}/comm").read_text().strip().startswith("gpu-screen-rec")
    except (OSError, ValueError):
        return False


def replay_storage(seconds: int, kbps: int) -> str:
    """'ram' for short buffers, 'disk' once the buffer would hold more than about 1 GB."""
    return "disk" if seconds * kbps / 8 / 1024 > REPLAY_RAM_LIMIT_MB else "ram"


def available() -> bool:
    return bool(shutil.which(BIN))


def capabilities() -> dict:
    """Codecs and capture sources this machine supports (from `gpu-screen-recorder --info`)."""
    if not available():
        return {"available": False, "codecs": [], "captures": [], "version": None}
    try:
        out = subprocess.run([BIN, "--info"], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    section, codecs, captures, info = None, [], [], {}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("section="):
            section = line.split("=", 1)[1]
            continue
        if not line:
            continue
        if section == "video_codecs":
            codecs.append(line)
        elif section == "capture_options":
            name, _, res = line.partition("|")
            captures.append({"name": name, "resolution": res})
        elif "|" in line:
            k, _, v = line.partition("|")
            info[k] = v
    plain = [c for c in ("h264", "hevc", "av1") if c in codecs]
    return {"available": True, "codecs": plain, "captures": captures, "version": info.get("gsr_version"),
            "app_audio": info.get("supports_app_audio") == "yes"}


def pick_codec(cfg: dict, caps: dict) -> str:
    codecs = caps.get("codecs") or ["h264"]
    want = cfg.get("codec", "auto")
    if want in codecs:
        return want
    for c in ("hevc", "h264", "av1"):
        if c in codecs:
            return c
    return "h264"


def pick_capture(cfg: dict, caps: dict) -> str:
    names = [c["name"] for c in caps.get("captures") or []]
    want = cfg.get("capture") or ""
    if want and (want in names or want == "portal"):
        return want
    monitors = [n for n in names if n not in ("region", "portal", "screen", "focused")]
    if monitors:
        return monitors[0]
    return "portal" if "portal" in names else "screen"


def build_args(cfg: dict, caps: dict, mode: str, out: str) -> list[str]:
    """mode: 'record' (out = file), 'replay' (out = directory), 'screenshot' (out = file)."""
    args = [BIN, "-w", pick_capture(cfg, caps)]
    if args[2] == "portal":
        args += ["-restore-portal-session", "yes"]
    if mode == "screenshot":
        return args + ["-cursor", "yes" if cfg.get("cursor", True) else "no", "-o", out]
    container = cfg.get("container", "mp4") if cfg.get("container") in ("mp4", "mkv") else "mp4"
    args += ["-c", container, "-f", str(int(cfg.get("fps") or 60)), "-k", pick_codec(cfg, caps),
             "-ac", "aac" if container == "mp4" else "opus",
             "-cursor", "yes" if cfg.get("cursor", True) else "no"]
    if cfg.get("desktop_audio", True) and cfg.get("mic") and not cfg.get("mic_separate", True):
        args += ["-a", "default_output|default_input"]
    else:
        if cfg.get("desktop_audio", True):
            args += ["-a", "default_output"]
        if cfg.get("mic"):
            args += ["-a", "default_input"]
    quality = cfg.get("quality", "very_high")
    if mode == "replay":
        secs = max(5, min(1200, int(cfg.get("replay_seconds") or 60)))
        kbps = REPLAY_BITRATE.get(quality, 35000)
        args += ["-r", str(secs), "-bm", "cbr", "-q", str(kbps),
                 "-replay-storage", replay_storage(secs, kbps), "-o", out, "-ro", out]
    else:
        args += ["-q", quality if quality in REPLAY_BITRATE else "very_high", "-o", out]
    return args + ["-ipc", str(SOCK)]


def clip_name(game: str | None, kind: str, ext: str, when: float | None = None) -> str:
    """'DEATH STRANDING 2026-11-08 14-02-11 Replay.mp4' (safe for every filesystem)."""
    stamp = time.strftime("%Y-%m-%d %H-%M-%S", time.localtime(when or time.time()))
    base = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", game or "Desktop").strip()[:80] or "Desktop"
    label = {"replay": " Replay", "screenshot": " Screenshot"}.get(kind, "")
    return f"{base} {stamp}{label}{ext}"


def file_clip(path: str, cfg: dict, game: str | None, kind: str) -> str:
    """Move a freshly saved file into <output>/<Game>/ with a readable name."""
    src = Path(path)
    if not src.exists():
        return path
    root = Path(cfg.get("output_dir") or DEFAULTS["output_dir"]).expanduser()
    folder = root / re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", game or "Desktop").strip()[:80] if cfg.get(
        "per_game_folders", True) else root
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / clip_name(game, kind, src.suffix)
    n = 2
    while dest.exists():
        dest = folder / clip_name(game, kind, f" ({n}){src.suffix}")
        n += 1
    try:
        shutil.move(str(src), dest)
    except OSError:
        return str(src)
    return str(dest)


def list_clips(output_dir: str, limit: int = 40) -> list[dict]:
    root = Path(output_dir).expanduser()
    files = []
    if root.is_dir():
        for p in list(root.glob("*")) + list(root.glob("*/*")):
            if p.is_file() and p.suffix.lower() in VIDEO_EXT + IMAGE_EXT and not p.name.startswith("."):
                try:
                    st = p.stat()
                except OSError:
                    continue
                files.append({"path": str(p), "name": p.stem, "game": p.parent.name if p.parent != root else "",
                              "bytes": st.st_size, "time": st.st_mtime,
                              "kind": "screenshot" if p.suffix.lower() in IMAGE_EXT else
                                      ("replay" if p.stem.endswith("Replay") or p.name.startswith("Replay_") else "video")})
    files.sort(key=lambda f: -f["time"])
    return files[:limit]


class Recorder:
    """One gpu-screen-recorder process: a plain recording or a replay buffer."""

    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.mode: str | None = None          # None | "record" | "replay"
        self.started = 0.0
        self.replay_recording_since = 0.0     # a regular recording running inside the replay session
        self.out_file: str | None = None
        self._id = 0
        self._reattach()

    # -- process lifecycle
    def _reattach(self):
        """Pick up a recorder left running by a previous Ember session."""
        try:
            st = json.loads(STATE.read_text())
            if _is_recorder(st["pid"]) and SOCK.exists():
                self.mode, self.started = st["mode"], st["started"]
                self.out_file = st.get("out_file")
                self._pid = int(st["pid"])
                return
        except (OSError, ValueError, KeyError):
            pass
        STATE.unlink(missing_ok=True)
        self._pid = None

    def _save_state(self):
        RUNTIME.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"pid": self.pid, "mode": self.mode, "started": self.started,
                                     "out_file": self.out_file}))

    @property
    def pid(self) -> int | None:
        if self.proc is not None:
            return self.proc.pid
        return getattr(self, "_pid", None)

    def alive(self) -> bool:
        if self.proc is not None:
            return self.proc.poll() is None
        return _is_recorder(self.pid)

    def status(self) -> dict:
        if self.mode and not self.alive():
            err = self._last_error()
            self._reset()
            return {"mode": None, "error": err}
        return {"mode": self.mode, "since": self.started,
                "recording": self.mode == "record" or bool(self.replay_recording_since),
                "recording_since": self.started if self.mode == "record" else self.replay_recording_since,
                "replay": self.mode == "replay"}

    def _reset(self):
        self.proc, self.mode, self.started, self.replay_recording_since, self.out_file = None, None, 0.0, 0.0, None
        self._pid = None
        STATE.unlink(missing_ok=True)

    def _last_error(self) -> str | None:
        try:
            lines = [l for l in LOG.read_text(errors="replace").splitlines() if "error" in l.lower()]
            return lines[-1][:200] if lines else None
        except OSError:
            return None

    def _spawn(self, args: list[str], mode: str, out_file: str | None = None):
        if self.alive():
            raise RecorderError("already running")
        RUNTIME.mkdir(parents=True, exist_ok=True)
        SOCK.unlink(missing_ok=True)
        LOG.parent.mkdir(parents=True, exist_ok=True)
        log = open(LOG, "w")
        self.proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     start_new_session=True)
        log.close()
        for _ in range(60):  # wait for the IPC socket (≈3 s max)
            if SOCK.exists() or self.proc.poll() is not None:
                break
            time.sleep(0.05)
        if self.proc.poll() is not None:
            err = self._last_error() or "gpu-screen-recorder exited"
            self.proc = None
            raise RecorderError(err)
        self.mode, self.started, self.out_file = mode, time.time(), out_file
        self.replay_recording_since = 0.0
        self._save_state()

    # -- IPC
    def _ipc(self, name: str, data=None, timeout: float = 30.0) -> dict:
        self._id += 1
        req = {"id": self._id, "name": name}
        if data is not None:
            req["data"] = data
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect(str(SOCK))
            s.sendall(json.dumps(req).encode() + b"\n")
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
        except OSError as e:
            raise RecorderError(f"recorder not responding ({e})") from None
        finally:
            s.close()
        try:
            resp = json.loads(buf)
        except ValueError:
            raise RecorderError("bad reply from recorder") from None
        if resp.get("result") != "ok":
            raise RecorderError(str(resp.get("data") or "request failed"))
        return resp

    # -- actions (blocking; run them off the GUI thread)
    def start_recording(self, cfg: dict, caps: dict) -> None:
        if self.mode == "replay":
            self._ipc("start-replay-recording")
            self.replay_recording_since = time.time()
            return
        tmp = Path(cfg["output_dir"]).expanduser()
        tmp.mkdir(parents=True, exist_ok=True)
        out = str(tmp / f".recording-{int(time.time())}.{cfg.get('container', 'mp4')}")
        self._spawn(build_args(cfg, caps, "record", out), "record", out)

    def stop_recording(self) -> str | None:
        if self.mode == "replay" and self.replay_recording_since:
            path = self._ipc("stop-replay-recording", timeout=120).get("data")
            self.replay_recording_since = 0.0
            return path
        if self.mode == "record":
            path = None
            try:
                path = self._ipc("stop", timeout=120).get("data") or self.out_file
            except RecorderError:
                self._signal_stop()
                path = self.out_file
            self._wait_exit()
            self._reset()
            return path
        return None

    def start_replay(self, cfg: dict, caps: dict) -> None:
        out = Path(cfg["output_dir"]).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        self._spawn(build_args(cfg, caps, "replay", str(out)), "replay")

    def save_replay(self, seconds: int | None = None) -> str:
        if self.mode != "replay":
            raise RecorderError("Instant Replay is off")
        data = {"seconds": int(seconds)} if seconds else None
        path = self._ipc("save-replay", data, timeout=120).get("data")
        if not path:
            raise RecorderError("replay was not saved")
        return path

    def stop_replay(self) -> str | None:
        """Stop the buffer (a recording running inside it is saved first)."""
        if self.mode != "replay":
            return None
        saved = None
        if self.replay_recording_since:
            try:
                saved = self.stop_recording()
            except RecorderError:
                pass
        try:
            self._ipc("stop", timeout=10)
        except RecorderError:
            self._signal_stop()
        self._wait_exit()
        self._reset()
        return saved

    def screenshot(self, cfg: dict, caps: dict) -> str:
        out = Path(cfg["output_dir"]).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        path = out / f".shot-{int(time.time() * 1000)}.png"
        r = subprocess.run(build_args(cfg, caps, "screenshot", str(path)), capture_output=True, text=True, timeout=15)
        if r.returncode != 0 or not path.exists():
            raise RecorderError((r.stderr or "screenshot failed").strip().splitlines()[-1])
        return str(path)

    def _signal_stop(self):
        if self.proc is not None or _is_recorder(self.pid):
            try:
                os.kill(self.pid, signal.SIGINT)
            except OSError:
                pass

    def _wait_exit(self, timeout: float = 15.0):
        end = time.time() + timeout
        while time.time() < end and self.alive():
            time.sleep(0.1)
        if self.proc is not None:
            self.proc.poll()
