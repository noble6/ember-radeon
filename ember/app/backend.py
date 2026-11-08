"""QML-facing backend: telemetry, daemon state, games and app settings."""
from __future__ import annotations

import copy
import getpass
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication

from ember.app import caches
from ember.app import hotkeys as HK
from ember.app import recorder as REC
from ember.app import daemon_client as dc
from ember.app import display
from ember.app import sysinfo
from ember import __version__
from ember.core import games as GM
from ember.core import update as UPD
from ember.core import gpu as G
from ember.core import tuning as T

HISTORY = 120  # samples kept per series
SERIES = ("gfx_mhz", "mem_mhz", "temp_edge", "temp_junction", "temp_mem", "power_w", "power_cap_w", "fan_rpm",
          "busy", "mem_busy", "vram_pct")
SETTINGS_FILE = GM.CONFIG_DIR / "settings.json"
ACCENTS = {"Crimson": "#E0243C", "Ember": "#FF5A1F", "Magenta": "#D61F69", "Violet": "#7C4DFF",
           "Cyan": "#00B8D4", "Lime": "#7CB342"}
HERE = Path(__file__).resolve().parents[2]


def _install_root() -> Path:
    return HERE


class Backend(QObject):
    tick = Signal()
    daemonChanged = Signal()
    tuningChanged = Signal()
    gamesChanged = Signal()
    sysChanged = Signal()
    settingsChanged = Signal()
    busyChanged = Signal()
    gpuChanged = Signal()
    procsChanged = Signal()
    displaysChanged = Signal()
    cachesChanged = Signal()
    loggingChanged = Signal()
    playingChanged = Signal()
    gameStarted = Signal(str, str)      # (title, body) for the tray notification
    recChanged = Signal()
    clipsChanged = Signal()
    recEvent = Signal(str, str)         # (title, body): clip saved, errors
    updateChanged = Signal()
    restartRequested = Signal()
    toast = Signal(str)
    _done = Signal(object, object, object)   # (callback, result, error) marshalled to the GUI thread

    def __init__(self):
        super().__init__()
        self._gpus = G.find_gpus()
        self._gpu = self._gpus[0] if self._gpus else None
        self._snap: dict = {}
        self._hist = {k: [] for k in SERIES}
        self._daemon = {"connected": False, "authorized": False, "version": None}
        self._dstate: dict = {}
        self._tuning: dict = self._gpu.tuning_state() if self._gpu else {}
        self._games: list = []
        self._gcfg = GM.load_games_config()
        self._sys: dict = {}
        self._busy = 0
        self._pool = ThreadPoolExecutor(max_workers=2)
        self._settings = self._load_settings()
        self._done.connect(self._on_done)
        self._procs: list = []
        self._proc_prev: dict = {}
        self._displays: list = []
        self._caches: dict = {}
        self._log_fh = None
        self._log_path = ""
        self._playing: list = []
        self._seen_ids: set = set()
        self._rec = REC.Recorder()
        self._rec_caps: dict = {"available": REC.available(), "codecs": [], "captures": []}
        self._rec_state: dict = self._rec.status()
        self._rec_busy = False
        self._auto_replay = False
        self._clips: list = []
        self._upd = {"latest": None, "checking": False, "error": None, "url": UPD.RELEASES_PAGE, "notes": ""}
        self._upd_status: dict = {}
        self._upd_kind = UPD.install_kind(HERE)
        self._hotkeys = HK.Hotkeys()
        self._hotkeys.triggered.connect(self.recAction)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._sample)
        self._timer.start(int(self._settings["interval_ms"]))
        self._dtimer = QTimer(self)
        self._dtimer.timeout.connect(self.refreshDaemon)
        self._dtimer.start(2000)
        self._sample()
        self.refreshDaemon()
        QTimer.singleShot(0, self.refreshGames)
        self._run(sysinfo.collect, self._set_sys)
        self._ptimer = QTimer(self)
        self._ptimer.timeout.connect(self.refreshProcesses)
        self._ptimer.start(2000)
        self._gtimer = QTimer(self)
        self._gtimer.timeout.connect(self._scan_games)
        self._gtimer.start(2000)
        self._utimer = QTimer(self)
        self._utimer.timeout.connect(self._poll_update)
        self._utimer.start(5000)
        QTimer.singleShot(20000, self.checkUpdates)
        self._uctimer = QTimer(self)
        self._uctimer.timeout.connect(self.checkUpdates)
        self._uctimer.start(6 * 3600 * 1000)
        self._rtimer = QTimer(self)
        self._rtimer.timeout.connect(self._poll_rec)
        self._rtimer.start(1000)
        QTimer.singleShot(200, lambda: self._run(REC.capabilities, self._set_rec_caps))
        QTimer.singleShot(400, self.refreshClips)
        if not os.environ.get("EMBER_SCREENSHOT"):
            QTimer.singleShot(900, self._register_hotkeys)
        QTimer.singleShot(300, self.refreshDisplays)
        QTimer.singleShot(600, self.refreshCaches)

    # ---------------------------------------------------------------- plumbing
    def _run(self, fn, cb=None, err=None, busy=False):
        if busy:
            self._busy += 1
            self.busyChanged.emit()

        def job():
            try:
                res = fn()
                self._done.emit((cb, busy), res, None)
            except Exception as e:  # noqa: BLE001 - surfaced to the UI
                self._done.emit((err, busy), None, e)
        self._pool.submit(job)

    def _on_done(self, cbinfo, res, e):
        cb, busy = cbinfo
        if busy:
            self._busy -= 1
            self.busyChanged.emit()
        if e is not None:
            if cb:
                cb(e)
            else:
                self.toast.emit(str(e))
        elif cb:
            cb(res)

    # ---------------------------------------------------------------- settings
    def _load_settings(self) -> dict:
        s = {"theme": "dark", "accent": "Crimson", "interval_ms": 500, "close_to_tray": True,
             "temp_unit": "C", "start_hidden": False}
        try:
            s.update(json.loads(SETTINGS_FILE.read_text()))
        except (OSError, ValueError):
            pass
        s["interval_ms"] = max(250, min(2000, int(s.get("interval_ms", 500))))
        s["rec"] = {**REC.DEFAULTS, **(s.get("rec") or {})}
        return s

    def _save_settings(self):
        GM.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(self._settings, indent=1))

    @Property("QVariant", notify=settingsChanged)
    def settings(self):
        return self._settings

    @Property("QVariant", constant=True)
    def accents(self):
        return [{"name": k, "color": v} for k, v in ACCENTS.items()]

    @Property(str, notify=settingsChanged)
    def accent(self):
        return ACCENTS.get(self._settings["accent"], ACCENTS["Crimson"])

    @Property(bool, notify=settingsChanged)
    def dark(self):
        return self._settings["theme"] != "light"

    @Slot(str, "QVariant")
    def setSetting(self, key, value):
        if hasattr(value, "toVariant"):
            value = value.toVariant()
        self._settings[key] = value
        if key == "autostart":
            self._set_autostart(bool(value))
        if key == "interval_ms":
            self._settings[key] = max(250, min(2000, int(value)))
            self._timer.setInterval(self._settings[key])
        self._save_settings()
        self.settingsChanged.emit()

    def _set_autostart(self, on: bool):
        path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / "ember.desktop"
        if on:
            path.parent.mkdir(parents=True, exist_ok=True)
            exe = shutil.which("ember") or f"{sys.executable} {HERE / 'main.py'}"
            path.write_text("[Desktop Entry]\nType=Application\nName=Ember\nIcon=ember\n"
                            f"Exec={exe} --hidden\nX-GNOME-Autostart-enabled=true\n")
        else:
            path.unlink(missing_ok=True)

    # ---------------------------------------------------------------- telemetry
    def _sample(self):
        if not self._gpu:
            return
        s = self._gpu.snapshot()
        s["vram_pct"] = 100 * s["vram_used"] / s["vram_total"] if s.get("vram_total") else None
        self._snap = s
        if self._log_fh:
            self._log_row(s)
        for k in SERIES:
            h = self._hist[k]
            v = s.get(k)
            h.append(float(v) if v is not None else float("nan"))
            if len(h) > HISTORY:
                del h[0]
        self.tick.emit()

    @Property("QVariant", notify=tick)
    def snap(self):
        s = dict(self._snap)
        s.pop("sclk_levels", None)
        s.pop("mclk_levels", None)
        return s

    @Property("QVariant", notify=tick)
    def history(self):
        return self._hist

    @Property(bool, constant=True)
    def hasGpu(self):
        return self._gpu is not None

    @Property("QVariant", notify=gpuChanged)
    def gpu(self):
        if not self._gpu:
            return {}
        return {**self._gpu.describe(), "caps": self._gpu.capabilities()}

    @Property("QVariant", constant=True)
    def gpus(self):
        return [{"index": i, "name": g.describe()["name"], "pci": g.pci_slot, "apu": g.describe()["apu"]}
                for i, g in enumerate(self._gpus)]

    @Property(int, notify=gpuChanged)
    def gpuIndex(self):
        return self._gpus.index(self._gpu) if self._gpu in self._gpus else 0

    @Slot(int)
    def selectGpu(self, i):
        if not 0 <= i < len(self._gpus) or self._gpus[i] is self._gpu:
            return
        self._gpu = self._gpus[i]
        self._hist = {k: [] for k in SERIES}
        self._proc_prev = {}
        self._tuning = self._gpu.tuning_state()
        self.gpuChanged.emit()
        self.tuningChanged.emit()
        self.daemonChanged.emit()
        self._sample()
        self.refreshProcesses()

    # ---------------------------------------------------------------- game detection
    @Property("QVariant", notify=playingChanged)
    def playing(self):
        return self._playing

    def _scan_games(self):
        from ember.daemon import running_games

        def ok(found):
            appids, exes = found
            known = {g["id"]: g for g in self.games}
            now = []
            for gid, g in known.items():
                kind, _, val = gid.partition(":")
                if (kind == "steam" and val in appids) or (kind == "exe" and val.lower() in exes):
                    now.append(g)
            # Steam games we have no manifest for (e.g. still updating) still count.
            for a in appids:
                if f"steam:{a}" not in known:
                    now.append({"id": f"steam:{a}", "name": f"Steam app {a}", "source": "Steam", "graphics": {},
                                "profile": "", "wired": False})
            ids = {g["id"] for g in now}
            for g in now:
                if g["id"] not in self._seen_ids:
                    self._announce(g)
            if now and not self._seen_ids and self._settings["rec"].get("auto_replay") \
                    and self._rec_caps.get("available") and not self._rec_state.get("mode"):
                self._auto_replay = True
                self._rec_job("replay-on", quiet=True)
            if not now and self._seen_ids and self._auto_replay and self._rec_state.get("mode") == "replay":
                self._auto_replay = False
                self._rec_job("replay-off", quiet=True)
            self._seen_ids = ids
            if [g["id"] for g in now] != [g["id"] for g in self._playing]:
                self._playing = now
                self.playingChanged.emit()
        self._run(running_games, ok, lambda e: None)

    def _announce(self, g):
        rt = self.runtime
        prof = g.get("profile") or (rt.get("applied") if rt else None) or "Stock"
        feats = GM.banner_lines(None, g.get("graphics") or {}, None)[1] if g.get("wired") else ""
        body = f"{prof} profile" + (f" · {feats}" if feats and feats != "Radeon tuning ready" else "")
        if not g.get("wired") and g.get("source") == "Steam":
            body += " · add ember-run to unlock graphics features"
        self.gameStarted.emit(f"Ember active · {g['name']}", body)

    # ---------------------------------------------------------------- updates
    @Property("QVariant", notify=updateChanged)
    def updateInfo(self):
        installed = UPD.installed_version() if self._upd_kind == "local" else None
        latest = self._upd.get("latest")
        st = self._upd_status
        busy = st.get("state") in ("checking", "downloading", "installing") and time.time() - st.get("time", 0) < 900
        return {
            "current": __version__,
            "installed": installed,
            "kind": self._upd_kind,
            "latest": latest,
            "available": bool(latest and UPD.is_newer(latest, installed or __version__)),
            "restart_needed": bool(installed and UPD.is_newer(installed, __version__)),
            "checking": self._upd["checking"],
            "error": self._upd["error"],
            "url": self._upd["url"],
            "notes": self._upd["notes"],
            "auto": UPD.auto_enabled(),
            "status": st.get("state"),
            "status_error": st.get("error") if st.get("state") == "error" else None,
            "busy": busy,
            "last_checked": st.get("time"),
        }

    @Slot()
    def checkUpdates(self):
        if self._upd["checking"]:
            return
        self._upd["checking"] = True
        self.updateChanged.emit()

        def ok(rel):
            self._upd.update(checking=False, error=None, latest=rel["version"], url=rel["url"], notes=rel["notes"])
            self.updateChanged.emit()

        def fail(e):
            self._upd.update(checking=False, error=str(e))
            self.updateChanged.emit()
        self._run(UPD.latest_release, ok, fail)

    @Slot()
    def installUpdate(self):
        if self._upd_kind != "local":
            self.toast.emit("This copy of Ember is managed by your package manager or a git checkout")
            return

        def job():
            r = subprocess.run(["systemctl", "start", "--no-block", "ember-update-now.service"],
                               capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                raise RuntimeError((r.stderr or "could not start the updater").strip().splitlines()[-1])
        self._run(job, lambda _: self.toast.emit("Updating Ember in the background"),
                  lambda e: self.toast.emit(f"Update: {e}"))

    @Slot(bool)
    def setAutoUpdate(self, on):
        self._cmd({"cmd": "set_update", "auto": bool(on)},
                  "Ember will update itself" if on else "Automatic updates off")
        QTimer.singleShot(600, self.updateChanged.emit)

    def _poll_update(self):
        st = UPD.read_json(UPD.STATUS, {})
        if st != self._upd_status:
            prev = self._upd_status.get("state")
            self._upd_status = st
            if st.get("state") == "updated" and prev and prev != "updated":
                self.recEvent.emit("Ember updated", f"Version {st.get('current')} is installed")
            self.updateChanged.emit()
        if self.updateInfo["restart_needed"]:
            self.updateChanged.emit()

    @Slot()
    def restartNow(self):
        if self._rec_state.get("mode"):
            self.toast.emit("Stop recording or Instant Replay first")
            return
        self.restartRequested.emit()

    @Property(bool, notify=updateChanged)
    def restartPending(self):
        return self.updateInfo["restart_needed"]

    # ---------------------------------------------------------------- record & instant replay
    def _set_rec_caps(self, caps):
        self._rec_caps = caps
        self.recChanged.emit()

    def _register_hotkeys(self):
        def ok(registered):
            if registered:
                self._hotkeys.listen()
            self.recChanged.emit()
        self._run(self._hotkeys.register_keys, ok, lambda e: None)

    @Property("QVariant", notify=recChanged)
    def recCaps(self):
        return self._rec_caps

    @Property("QVariant", notify=recChanged)
    def recState(self):
        return {**self._rec_state, "busy": self._rec_busy}

    @Property("QVariant", notify=recChanged)
    def recConfig(self):
        return self._settings["rec"]

    @Property("QVariant", notify=recChanged)
    def hotkeys(self):
        return {"kde": self._hotkeys.enabled, "list": self._hotkeys.describe()}

    @Property("QVariant", notify=clipsChanged)
    def clips(self):
        return self._clips

    def _poll_rec(self):
        st = self._rec.status()
        if st != self._rec_state:
            if st.get("error") and self._rec_state.get("mode"):
                self.recEvent.emit("Recording stopped", st["error"])
                self.toast.emit(f"Recorder stopped: {st['error']}")
            self._rec_state = st
            self.recChanged.emit()

    @Slot(str, "QVariant")
    def setRecSetting(self, key, value):
        if hasattr(value, "toVariant"):
            value = value.toVariant()
        if key not in REC.DEFAULTS:
            return
        self._settings["rec"][key] = value
        self._save_settings()
        self.recChanged.emit()
        if key not in ("auto_replay", "output_dir", "per_game_folders") and self._rec_state.get("mode") == "replay":
            self.toast.emit("Turn Instant Replay off and on again to use the new settings")

    def _game_now(self):
        return self._playing[0] if self._playing else None

    def _hud_flash(self, lines, seconds=3.0, keep=False):
        g = self._game_now()
        if not g:
            return
        gfx = GM.graphics_for(self._gcfg, g["id"])
        if GM.show_hud(g["id"], gfx, lines) and not keep:
            QTimer.singleShot(int(seconds * 1000), self._hud_restore)

    def _hud_restore(self):
        g = self._game_now()
        if not g:
            return
        if self._rec_state.get("recording"):
            self._hud_flash(["● REC"], keep=True)
        else:
            GM.finalize_hud(str(GM.hud_path(g["id"])))

    @Slot(str)
    def recAction(self, action):
        """Entry point for buttons, the tray, hotkeys and `ember --rec`."""
        if not self._rec_caps.get("available"):
            self.toast.emit("Install gpu-screen-recorder to record")
            return
        st = self._rec_state
        if action == "toggle-recording":
            self._rec_job("record-off" if st.get("recording") else "record-on")
        elif action == "save-replay":
            if st.get("mode") == "replay":
                self._rec_job("save-replay")
            else:
                self.toast.emit("Instant Replay is off. Turn it on first (Alt+Shift+F10)")
                self._hud_flash(["INSTANT REPLAY IS OFF"])
        elif action == "toggle-replay":
            self._rec_job("replay-off" if st.get("mode") == "replay" else "replay-on")
        elif action == "screenshot":
            self._rec_job("screenshot")

    @Slot(int)
    def saveReplaySeconds(self, seconds):
        self._rec_job("save-replay", seconds=seconds)

    def _rec_job(self, job, seconds=None, quiet=False):
        if self._rec_busy:
            return
        cfg = dict(self._settings["rec"])
        caps = self._rec_caps
        g = self._game_now()
        game = g["name"] if g else None
        rec = self._rec

        def work():
            if job == "record-on":
                rec.start_recording(cfg, caps)
                return ("started", None)
            if job == "record-off":
                path = rec.stop_recording()
                return ("saved", REC.file_clip(path, cfg, game, "video") if path else None)
            if job == "replay-on":
                rec.start_replay(cfg, caps)
                return ("replay-on", None)
            if job == "replay-off":
                path = rec.stop_replay()
                return ("replay-off", REC.file_clip(path, cfg, game, "video") if path else None)
            if job == "save-replay":
                return ("replay-saved", REC.file_clip(rec.save_replay(seconds), cfg, game, "replay"))
            if job == "screenshot":
                return ("shot", REC.file_clip(rec.screenshot(cfg, caps), cfg, game, "screenshot"))
            return (None, None)

        def done(res):
            self._rec_busy = False
            what, path = res
            self._rec_state = rec.status()
            self.recChanged.emit()
            name = os.path.basename(path) if path else ""
            secs = seconds or cfg.get("replay_seconds")
            if what == "started":
                self._hud_flash(["● REC"], keep=True)
                if not quiet:
                    self.toast.emit("Recording")
            elif what == "replay-on":
                self._hud_flash(["INSTANT REPLAY ON", f"Alt+F10 saves the last {secs} s"])
                if not quiet:
                    self.toast.emit(f"Instant Replay on: keeping the last {secs} s")
            elif what == "replay-off":
                self._hud_flash(["INSTANT REPLAY OFF"])
                if not quiet:
                    self.toast.emit("Instant Replay off")
            elif what in ("saved", "replay-saved", "shot"):
                title = {"saved": "Recording saved", "replay-saved": f"Replay saved ({secs} s)",
                         "shot": "Screenshot saved"}[what]
                stem = os.path.splitext(name)[0]
                hud_title = {"saved": "RECORDING SAVED", "replay-saved": f"REPLAY SAVED  ·  last {secs} s",
                             "shot": "SCREENSHOT SAVED"}[what]
                self._hud_flash([hud_title, stem if len(stem) <= 60 else stem[:57] + "..."])
                self.recEvent.emit(title, path or "")
                self.toast.emit(f"{title}: {name}")
                self.refreshClips()

        def fail(e):
            self._rec_busy = False
            self._rec_state = rec.status()
            self.recChanged.emit()
            self.toast.emit(f"Recorder: {e}")
            self._hud_flash(["RECORDER ERROR", str(e)[:60]])

        self._rec_busy = True
        self.recChanged.emit()
        self._run(work, done, fail)

    @Slot()
    def refreshClips(self):
        out = self._settings["rec"]["output_dir"]
        self._run(lambda: REC.list_clips(out), lambda c: (setattr(self, "_clips", c), self.clipsChanged.emit()),
                  lambda e: None)

    @Slot(str)
    def openPath(self, path):
        subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)

    @Slot(str)
    def showInFolder(self, path):
        if shutil.which("dolphin"):
            subprocess.Popen(["dolphin", "--select", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        else:
            self.openPath(os.path.dirname(path))

    @Slot(str)
    def deleteClip(self, path):
        root = Path(self._settings["rec"]["output_dir"]).expanduser().resolve()
        p = Path(path).resolve()
        if root in p.parents and p.suffix.lower() in REC.VIDEO_EXT + REC.IMAGE_EXT:
            p.unlink(missing_ok=True)
            self.toast.emit(f"Deleted {p.name}")
            self.refreshClips()

    @Slot()
    def openShortcutSettings(self):
        HK.open_shortcut_settings()

    def stopRecorderOnQuit(self):
        """Never lose a recording when Ember quits: save it first."""
        if self._rec_state.get("recording") or self._rec_state.get("mode"):
            try:
                cfg = self._settings["rec"]
                g = self._game_now()
                path = self._rec.stop_recording() if self._rec_state.get("recording") else None
                if path:
                    REC.file_clip(path, cfg, g["name"] if g else None, "video")
                if self._rec.mode == "replay":
                    self._rec.stop_replay()
            except REC.RecorderError:
                pass

    # ---------------------------------------------------------------- per-app usage
    @Property("QVariant", notify=procsChanged)
    def processes(self):
        return self._procs

    @Slot()
    def refreshProcesses(self):
        if not self._gpu:
            return
        slot = self._gpu.pci_slot

        def ok(rows):
            now = __import__("time").monotonic()
            prev, self._proc_prev = self._proc_prev, {}
            out = []
            for r in rows:
                busy_ns = r["gfx_ns"] + r["compute_ns"]
                p = prev.get(r["pid"])
                pct = None
                if p:
                    dt = now - p[0]
                    if dt > 0:
                        pct = max(0.0, min(100.0, (busy_ns - p[1]) / (dt * 1e9) * 100))
                self._proc_prev[r["pid"]] = (now, busy_ns)
                out.append({"pid": r["pid"], "name": r["name"], "vram_mb": r["vram"] / 1024,
                            "gtt_mb": r["gtt"] / 1024, "gpu_pct": pct,
                            "media": bool(r["enc_ns"] or r["dec_ns"])})
            out.sort(key=lambda x: (-(x["gpu_pct"] or 0), -x["vram_mb"]))
            self._procs = out[:12]
            self.procsChanged.emit()
        self._run(lambda: G.gpu_processes(slot), ok, lambda e: None)

    # ---------------------------------------------------------------- metric logging (CSV)
    @Property(str, notify=loggingChanged)
    def logPath(self):
        return self._log_path if self._log_fh else ""

    @Slot()
    def toggleLogging(self):
        import csv
        import time as _t
        if self._log_fh:
            self._log_fh.close()
            self._log_fh = None
            self.toast.emit(f"Saved {self._log_path}")
            self.loggingChanged.emit()
            return
        d = Path(os.environ.get("XDG_DOCUMENTS_DIR", Path.home() / "Documents")) / "Ember logs"
        d.mkdir(parents=True, exist_ok=True)
        self._log_path = str(d / _t.strftime("ember-%Y%m%d-%H%M%S.csv"))
        self._log_fh = open(self._log_path, "w", newline="")
        self._log_csv = csv.writer(self._log_fh)
        self._log_csv.writerow(["time", "gpu_mhz", "mem_mhz", "busy_pct", "power_w", "power_cap_w",
                                "edge_c", "hotspot_c", "mem_c", "fan_rpm", "vram_used_mb", "vddgfx_mv", "throttle"])
        self.toast.emit("Recording metrics to CSV")
        self.loggingChanged.emit()

    def _log_row(self, s):
        import time as _t
        try:
            self._log_csv.writerow([_t.strftime("%H:%M:%S"), s.get("gfx_mhz"), s.get("mem_mhz"), s.get("busy"),
                                    s.get("power_w"), s.get("power_cap_w"), s.get("temp_edge"), s.get("temp_junction"),
                                    s.get("temp_mem"), s.get("fan_rpm"), round((s.get("vram_used") or 0) / 2**20),
                                    s.get("vddgfx_mv"), "|".join(s.get("throttle") or [])])
        except (OSError, ValueError):
            self._log_fh = None
            self.loggingChanged.emit()

    # ---------------------------------------------------------------- displays
    @Property("QVariant", notify=displaysChanged)
    def displays(self):
        return self._displays

    @Property(bool, constant=True)
    def displayControl(self):
        return display.available()

    @Slot()
    def refreshDisplays(self):
        def ok(outs):
            self._displays = outs
            self.displaysChanged.emit()
        self._run(display.outputs, ok, lambda e: None)

    @Slot(str, str, str)
    def setDisplay(self, output, key, value):
        def ok(_):
            self.refreshDisplays()
        self._run(lambda: display.set_option(output, key, value), ok,
                  lambda e: (self.toast.emit(f"Display: {e}"), self.refreshDisplays()), busy=True)

    # ---------------------------------------------------------------- shader caches
    @Property("QVariant", notify=cachesChanged)
    def caches(self):
        return self._caches

    @Slot()
    def refreshCaches(self):
        self._run(caches.scan, lambda c: (setattr(self, "_caches", c), self.cachesChanged.emit()), lambda e: None)

    @Slot(str)
    def clearCache(self, which):
        def ok(freed):
            self.toast.emit(f"Cleared {freed / 2**20:.0f} MB - shaders rebuild on next launch")
            self.refreshCaches()
        self._run(lambda: caches.clear(which), ok, lambda e: self.toast.emit(str(e)), busy=True)

    @Property("QVariant", notify=tuningChanged)
    def tuning(self):
        t = copy.deepcopy(self._tuning)
        if t.get("od") and t["od"].get("ranges"):
            t["od"]["ranges"] = {k: list(v) for k, v in t["od"]["ranges"].items()}
            t["od"]["sections"] = {k: [list(x) for x in v] for k, v in t["od"]["sections"].items()}
        stock = self.gpuState.get("od_stock") if self._gpu else None
        t["od_controls"] = G.od_controls(self._tuning.get("od"), stock)
        t["fan_ctrl_info"] = [{"key": k, "label": G.FAN_CTRL[k][1], **v} for k, v in (t.get("fan_ctrl") or {}).items()]
        # CUSTOM needs a full coefficient table; we don't offer it.
        t["power_profiles"] = [p for p in t.get("power_profiles", []) if p["name"] != "CUSTOM"]
        return t

    # ---------------------------------------------------------------- daemon
    @Property("QVariant", notify=daemonChanged)
    def daemon(self):
        return self._daemon

    @Property("QVariant", notify=daemonChanged)
    def gpuState(self):
        """{profiles, active, apply_on_boot, rules} for the selected GPU."""
        if not self._gpu:
            return {}
        return ((self._dstate.get("state") or {}).get("gpus") or {}).get(self._gpu.pci_slot) or {}

    @Property("QVariant", notify=daemonChanged)
    def profileNames(self):
        """Profile names in a stable order (QVariantMap would sort them)."""
        names = list((self.gpuState.get("profiles") or {}).keys())
        builtin = [n for n in ("Quiet", "Balanced", "Performance") if n in names]
        return builtin + [n for n in names if n not in builtin]

    @Property("QVariant", notify=daemonChanged)
    def runtime(self):
        if not self._gpu:
            return {}
        return (self._dstate.get("runtime") or {}).get(self._gpu.pci_slot) or {}

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy > 0

    @Slot()
    def refreshDaemon(self):
        def fetch():
            return dc.request({"cmd": "state"}, timeout=2)

        def ok(resp):
            changed = (not self._daemon["connected"] or resp.get("authorized") != self._daemon["authorized"]
                       or json.dumps(resp, sort_keys=True) != json.dumps(self._dstate, sort_keys=True))
            self._daemon = {"connected": True, "authorized": bool(resp.get("authorized")),
                            "boot_skipped": bool(resp.get("boot_skipped"))}
            self._dstate = resp
            if changed:
                self._tuning = self._gpu.tuning_state() if self._gpu else {}
                self.tuningChanged.emit()
                self.daemonChanged.emit()

        def fail(_e):
            if self._daemon["connected"] or self._dstate:
                self._daemon = {"connected": False, "authorized": False}
                self._dstate = {}
                self.daemonChanged.emit()
        self._run(fetch, ok, fail)

    def _cmd(self, req: dict, msg: str | None = None):
        if not self._gpu:
            return
        req = {**req, "gpu": self._gpu.pci_slot}

        def ok(resp):
            rt = resp.get("runtime") or {}
            if rt.get("error"):
                self.toast.emit(f"Applied with problems: {rt['error']}")
            elif msg:
                self.toast.emit(msg)
            self.refreshDaemon()
        self._run(lambda: dc.request(req), ok, lambda e: self.toast.emit(str(e)), busy=True)

    @Slot(str)
    def activateProfile(self, name):
        self._cmd({"cmd": "activate", "name": name or None},
                  f"{name} profile applied" if name else "Back to stock settings")

    @Slot(str, "QVariant", bool)
    def saveProfile(self, name, settings, activate):
        if hasattr(settings, "toVariant"):
            settings = settings.toVariant()
        try:
            T.validate(settings, self._tuning)
        except T.InvalidSettings as e:
            self.toast.emit(str(e))
            return
        self._cmd({"cmd": "save_profile", "name": name, "settings": settings, "activate": activate},
                  f"Saved “{name}”" + (" and applied" if activate else ""))

    @Slot(str)
    def deleteProfile(self, name):
        self._cmd({"cmd": "delete_profile", "name": name}, f"Deleted “{name}”")

    @Slot()
    def resetStock(self):
        self._cmd({"cmd": "reset"}, "Restored stock settings")

    @Slot()
    def resetPresets(self):
        self._cmd({"cmd": "reset_presets"}, "Built-in profiles restored")

    @Slot(bool)
    def setApplyOnBoot(self, on):
        self._cmd({"cmd": "set_boot", "apply_on_boot": on},
                  "Profile will be applied at boot" if on else "Stock settings at boot")

    @Slot(result="QVariant")
    def defaultSettings(self):
        return copy.deepcopy(T.DEFAULTS)

    @Slot("QVariant", float, result=float)
    def fanAt(self, curve, temp):
        if hasattr(curve, "toVariant"):
            curve = curve.toVariant()
        return T.fan_target(curve, temp)

    # ---------------------------------------------------------------- install helpers
    def _pkexec(self, args: list[str], ok_msg: str, then=None):
        if not shutil.which("pkexec"):
            self.toast.emit("pkexec not found - run the command in a terminal with sudo")
            return

        def job():
            r = subprocess.run(["pkexec", *args], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip()
                                   else "cancelled")
            return r.stdout

        def ok(_):
            self.toast.emit(ok_msg)
            if then:
                then()
        self._run(job, ok, lambda e: self.toast.emit(f"Failed: {e}"), busy=True)

    @Slot()
    def installService(self):
        script = _install_root() / "install.sh"
        if not script.exists():
            self.toast.emit("install.sh not found next to the app")
            return
        self._pkexec(["/bin/bash", str(script), "--system", f"--user={getpass.getuser()}"],
                     "Ember service installed", lambda: QTimer.singleShot(800, self.refreshDaemon))

    @Slot()
    def enableOverdrive(self):
        helper = None
        for p in ("/usr/local/lib/ember/ember-overdrive", "/usr/lib/ember/ember-overdrive", str(_install_root() / "packaging/ember-overdrive")):
            if os.path.exists(p):
                helper = p
                break
        if not helper:
            self.toast.emit("overdrive helper missing")
            return
        self._pkexec(["/bin/bash", helper, "enable"], "Overdrive enabled - reboot to unlock clock & voltage tuning",
                     lambda: self.sysChanged.emit())

    # ---------------------------------------------------------------- games
    @Property("QVariant", notify=gamesChanged)
    def games(self):
        out = []
        rules = {r["match"]: r for r in (self.gpuState.get("rules") or [])}
        for g in self._games + [self._custom_entry(c) for c in self._gcfg.get("custom", [])]:
            cfg = (self._gcfg.get("games") or {}).get(g["id"]) or {}
            out.append({**g, "profile": (rules.get(g["id"]) or {}).get("profile", ""),
                        "use_defaults": cfg.get("use_defaults", True),
                        "graphics": GM.graphics_for(self._gcfg, g["id"])})
        return out

    def _custom_entry(self, c: dict) -> dict:
        return {"id": f"exe:{c['exe']}", "name": c.get("name") or c["exe"], "source": "Other",
                "exe": c["exe"], "wired": True, "launch_options": ""}

    @Property("QVariant", notify=gamesChanged)
    def globalGraphics(self):
        return GM.graphics_for(self._gcfg, None)

    @Slot()
    def refreshGames(self):
        def ok(games):
            self._games = games
            self.gamesChanged.emit()
        self._run(GM.scan_steam, ok)

    @Slot(str, "QVariant")
    def setGraphics(self, game_id, gfx):
        if hasattr(gfx, "toVariant"):
            gfx = gfx.toVariant()
        clean = {k: gfx[k] for k in GM.GRAPHICS_DEFAULTS if k in gfx}
        if clean.get("gamescope"):
            mon = next((d for d in self._displays if d.get("enabled") and d.get("current")), None)
            if mon:
                clean.update(gs_out_w=mon["current"]["w"], gs_out_h=mon["current"]["h"],
                             gs_refresh=int(round(mon["current"]["hz"])))
        if game_id:
            g = self._gcfg["games"].setdefault(game_id, {})
            g.update(clean)
            if "use_defaults" in gfx:
                g["use_defaults"] = bool(gfx["use_defaults"])
        else:
            self._gcfg["defaults"].update(clean)
        GM.save_games_config(self._gcfg)
        self.gamesChanged.emit()

    @Slot(str, str, str)
    def setGameProfile(self, game_id, label, profile):
        rules = [r for r in (self.gpuState.get("rules") or []) if r["match"] != game_id]
        if profile:
            rules.insert(0, {"match": game_id, "label": label, "profile": profile})
        self._cmd({"cmd": "set_rules", "rules": rules},
                  f"{label} → {profile}" if profile else f"{label} uses your active profile")
        QTimer.singleShot(400, self.gamesChanged.emit)

    @Slot(str, bool)
    def wireSteam(self, appid, enable):
        def ok(lo):
            self.toast.emit("Launch options: " + (lo or "(none)"))
            self.refreshGames()
        self._run(lambda: GM.set_steam_launch_option(appid, enable), ok,
                  lambda e: self.toast.emit(str(e)), busy=True)

    @Slot(str, str)
    def addCustomGame(self, name, exe):
        exe = os.path.basename(exe.strip())
        if not exe:
            return
        self._gcfg["custom"] = [c for c in self._gcfg.get("custom", []) if c["exe"] != exe]
        self._gcfg["custom"].append({"name": name.strip() or exe, "exe": exe})
        GM.save_games_config(self._gcfg)
        self.gamesChanged.emit()

    @Slot(str)
    def removeCustomGame(self, exe):
        self._gcfg["custom"] = [c for c in self._gcfg.get("custom", []) if c["exe"] != exe]
        GM.save_games_config(self._gcfg)
        self.setGameProfile(f"exe:{exe}", exe, "")

    @Slot("QVariant", result=str)
    def launchPreview(self, gfx):
        if hasattr(gfx, "toVariant"):
            gfx = gfx.toVariant()
        return GM.env_preview(gfx, self.gpu.get("arch_key"))

    # ---------------------------------------------------------------- system
    def _set_sys(self, info):
        self._sys = info
        self.sysChanged.emit()

    @Property("QVariant", notify=sysChanged)
    def system(self):
        return self._sys

    @Slot(result=str)
    def report(self):
        g = self.gpu
        s = self._sys
        lines = [
            f"GPU: {g.get('name')} ({g.get('chip')})", f"Board: {g.get('board')}  Subsystem: {g.get('subsystem')}",
            f"VBIOS: {g.get('vbios')}  VRAM: {g.get('vram_total', 0) / 2**30:.0f} GiB {g.get('vram_vendor') or ''}",
            f"PCIe: {self._snap.get('pcie')} (max {g.get('pcie_max')})",
            f"OS: {s.get('os')}  Kernel: {s.get('kernel')}  Session: {s.get('session')}",
            f"Mesa: {s.get('mesa')}  Vulkan: {s.get('vk_api')} ({s.get('vk_driver')})  GL: {s.get('gl_version')}",
            f"ppfeaturemask: {s.get('ppfeaturemask')}  Overdrive: {'on' if s.get('overdrive_kernel') else 'off'}",
            f"CPU: {s.get('cpu')}  RAM: {s.get('ram', 0) / 2**30:.1f} GiB",
        ]
        return "\n".join(lines)

    @Slot(str)
    def copy(self, text):
        QGuiApplication.clipboard().setText(text)
        self.toast.emit("Copied to clipboard")

    @Slot(str)
    def openUrl(self, url):
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def shutdown(self):
        self.stopRecorderOnQuit()
        self._timer.stop()
        self._dtimer.stop()
        self._pool.shutdown(wait=False, cancel_futures=True)
