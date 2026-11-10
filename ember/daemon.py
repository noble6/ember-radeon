"""emberd: the privileged half of Ember.

Runs as root (systemd), owns every sysfs write, and speaks newline-delimited JSON
over a Unix socket. It also runs the software fan curve and swaps profiles when a
game with a rule starts or exits, so tuning keeps working with the UI closed.
"""
from __future__ import annotations

import copy
import grp
import json
import logging
import os
import pwd
import re
import signal
import socket
import socketserver
import struct
import sys
import threading
import time
from pathlib import Path

from ember.core import gpu as G
from ember.core import tuning as T

from ember import __version__ as VERSION  # noqa: E402
SOCKET = Path(os.environ.get("EMBER_SOCKET", "/run/ember/emberd.sock"))
STATE_DIR = Path(os.environ.get("EMBER_STATE_DIR", "/var/lib/ember"))
CONF = Path(os.environ.get("EMBER_CONF", "/etc/ember/emberd.conf"))
PROC = G.SYSFS_ROOT / "proc"
BOOT_GRACE_S = 90          # OD applied at boot must survive this long to be trusted next boot
EMERGENCY_MARGIN_C = 5     # fans to 100% this close to a sensor's critical temperature
SAFETY_MARGIN_C = 20       # from here on a minimum fan speed applies, whatever the profile says
SENSOR_FAILS_MAX = 3       # unreadable temperature this many ticks in a row: fan goes back to automatic
MAX_REQUEST = 256 * 1024   # bytes per request line
MAX_CLIENTS = 32           # concurrent connections, total
MAX_CLIENTS_PER_UID = 8
CLIENT_TIMEOUT_S = 30      # idle connections are dropped
MAX_PROFILES = 64

log = logging.getLogger("emberd")


class ApplyError(RuntimeError):
    pass


def write(path: Path, value: str) -> None:
    log.debug("write %s <- %s", path, value)
    try:
        with open(path, "w") as fh:
            fh.write(value + "\n")
    except OSError as e:
        raise ApplyError(f"{path.name} <- {value!r}: {e.strerror or e}") from None


# ---------------------------------------------------------------- per-GPU controller

class Controller:
    """Applies settings to one GPU and runs its fan loop."""

    def __init__(self, gpu: G.Gpu):
        self.gpu = gpu
        self.applied: dict | None = None      # validated settings currently on the hardware
        self.fan_owned = False                 # we switched pwm1_enable to manual
        self._last_pwm_pct: float | None = None
        self._last_temp: float | None = None
        self._fan_cfg: dict | None = None
        self._sensor_fails = 0
        self.fan_fault: str | None = None      # why the fan was handed back to the firmware
        self.od_stock: dict | None = None     # pp_od_clk_voltage as first seen (factory values)

    # A marker on disk records that we hold the fan in manual mode, so that a crashed
    # or killed daemon can still be cleaned up after (see recover_fans).
    @property
    def _fan_marker(self) -> Path:
        return STATE_DIR / f"fan-{re.sub(r'[^0-9A-Za-z._-]', '_', self.key)}.owned"

    def _own_fan(self, owned: bool) -> None:
        self.fan_owned = owned
        try:
            if owned:
                STATE_DIR.mkdir(parents=True, exist_ok=True)
                self._fan_marker.write_text("1")
            else:
                self._fan_marker.unlink(missing_ok=True)
        except OSError as e:
            log.debug("fan marker: %s", e)

    @property
    def key(self) -> str:
        return self.gpu.pci_slot

    def state(self) -> dict:
        ts = self.gpu.tuning_state()
        ts["od_stock"] = self.od_stock
        return ts

    # -- writes
    def _perf_level(self, level: str) -> None:
        write(self.gpu.dev / "power_dpm_force_performance_level", level)

    def _power_profile(self, idx: int) -> None:
        path = self.gpu.dev / "pp_power_profile_mode"
        try:
            write(path, str(idx))
        except ApplyError:
            # Some SMU generations only accept a profile switch in manual mode.
            self._perf_level("manual")
            write(path, str(idx))

    def _power_cap(self, watts: float | None) -> None:
        h = self.gpu.hwmon
        if not h or not (h / "power1_cap").exists():
            return
        if watts is None:
            dflt = G.read_int(h / "power1_cap_default")
            if dflt is None:
                return
            uw = dflt
        else:
            uw = int(watts * 1_000_000)
        if G.read_int(h / "power1_cap") != uw:
            write(h / "power1_cap", str(uw))

    def _od(self, od: dict | None, previous: dict | None) -> None:
        path = self.gpu.od_path
        if not path.exists():
            if od:
                raise ApplyError("overdrive is not available on this GPU/kernel")
            return
        if od == previous and od is not None:
            return
        if od is None and previous is None and self.applied is not None:
            return   # no overdrive before, none now: leave the table alone
        table = G.parse_od(G.read(path))
        if table["family"] == "states":
            # Polaris/Vega10 only accept table edits in manual mode; the perf-level
            # step that runs next puts the requested level back.
            self._perf_level("manual")
        write(path, "r")
        if od:
            for cmd in G.od_commands(table, od, self.od_stock):
                write(path, cmd)
        write(path, "c")

    def _fan_fw(self, fw: dict) -> None:
        """RDNA3+ firmware fan options (zero RPM, target temperature, acoustic limits)."""
        base = self.gpu.dev / "gpu_od" / "fan_ctrl"
        for key, val in (fw or {}).items():
            fname = G.FAN_CTRL[key][0]
            write(base / fname, str(int(val)))
            write(base / fname, "c")

    def _fan_firmware_curve(self, fan: dict) -> bool:
        """RDNA3+: the SMU owns the curve (gpu_od/fan_ctrl/fan_curve). True if used."""
        fc = self.gpu.dev / "gpu_od" / "fan_ctrl" / "fan_curve"
        if not fc.exists():
            return False
        text = G.read(fc) or ""
        npts = len(re.findall(r"^\s*\d+:", text, re.M)) or 5
        if fan["mode"] == "auto":
            write(fc, "r")
            return True
        # Ranges look like "FAN_CURVE(hotspot temp): 25C 100C" / "FAN_CURVE(fan speed): 15% 100%".
        trange, srange, pct = (25, 100), (0, 100), True
        for line in text.splitlines():
            nums = [int(n) for n in re.findall(r"-?\d+", line.split(":", 1)[-1])]
            if "temp" in line.lower() and len(nums) >= 2:
                trange = (nums[0], nums[1])
            elif "speed" in line.lower() and len(nums) >= 2:
                srange, pct = (nums[0], nums[1]), "%" in line
        curve = fan["curve"] if fan["mode"] == "curve" else [[trange[0], fan["fixed_pct"]], [trange[1], fan["fixed_pct"]]]
        for i, (t, p) in enumerate(T.resample_curve(curve, npts, trange[0], trange[1])):
            speed = p if pct else round(p * 255 / 100)
            speed = max(srange[0], min(srange[1], speed))
            write(fc, f"{i} {t} {speed}")
        write(fc, "c")
        return True

    def _fan(self, fan: dict) -> None:
        self.fan_fault = None
        self._sensor_fails = 0
        if self._fan_firmware_curve(fan):
            self._own_fan(False)
            return
        h = self.gpu.hwmon
        if not h or not (h / "pwm1_enable").exists():
            if fan["mode"] != "auto":
                raise ApplyError("fan control not available")
            return
        if fan["mode"] == "auto":
            if self.fan_owned or G.read_int(h / "pwm1_enable") != 2:
                write(h / "pwm1_enable", "2")
            self._own_fan(False)
            self._last_pwm_pct = None
        else:
            self._own_fan(True)            # marker first: a crash right after must still be cleaned up
            try:
                write(h / "pwm1_enable", "1")
            except ApplyError:
                self._own_fan(False)
                raise
            self._fan_cfg = fan
            self._last_pwm_pct = None
            self.fan_tick(force=True)

    def apply(self, settings: dict) -> dict:
        clean = T.validate(settings, self.state())
        prev = self.applied or {}
        errors = []
        steps = [
            ("clocks", lambda: self._od(clean["od"], prev.get("od") if prev else None)),
            ("perf level", lambda: self._perf_level(clean["perf_level"])),
            ("power profile", lambda: self._power_profile(
                clean["power_profile"] if clean["power_profile"] is not None else self._default_profile())),
            ("power limit", lambda: self._power_cap(clean["power_cap_w"])),
            ("fan options", lambda: self._fan_fw(clean["fan"].get("fw"))),
            ("fan", lambda: self._fan(clean["fan"])),
        ]
        for name, fn in steps:
            try:
                fn()
            except ApplyError as e:
                errors.append(f"{name}: {e}")
                log.warning("%s: %s failed: %s", self.key, name, e)
        self.applied = clean
        if errors:
            raise ApplyError("; ".join(errors))
        return clean

    def drifted(self) -> bool:
        """True if the hardware no longer matches what we applied (e.g. after resume)."""
        a = self.applied
        if not a or self.gpu.asleep():
            return False
        if G.read(self.gpu.dev / "power_dpm_force_performance_level") != a["perf_level"]:
            return True
        h = self.gpu.hwmon
        if a["power_cap_w"] is not None and h is not None:
            cur = G.read_int(h / "power1_cap")
            if cur is not None and abs(cur - a["power_cap_w"] * 1e6) > 1e6:
                return True
        return False

    def _default_profile(self) -> int:
        for p in self.state().get("power_profiles") or []:
            if p["name"] == "BOOTUP_DEFAULT":
                return p["index"]
        return 0

    def restore_stock(self) -> None:
        stock = copy.deepcopy(T.DEFAULTS)
        try:
            self.apply(stock)
        finally:
            # Always try to hand the fan back, even if something else failed.
            self.release_fan()
        if self.gpu.od_path.exists():
            try:
                write(self.gpu.od_path, "r")
                write(self.gpu.od_path, "c")
            except ApplyError as e:
                log.warning("od reset: %s", e)
        base = self.gpu.dev / "gpu_od" / "fan_ctrl"
        for fname, _label in G.FAN_CTRL.values():
            if (base / fname).exists():
                try:
                    write(base / fname, "r")
                    write(base / fname, "c")
                except ApplyError as e:
                    log.warning("fan option reset: %s", e)
        self.applied = None

    def release_fan(self) -> None:
        h = self.gpu.hwmon
        if self.fan_owned and h:
            try:
                write(h / "pwm1_enable", "2")
            except ApplyError as e:
                log.error("could not return fan to auto: %s", e)
        self._own_fan(False)

    def fail_safe(self, why: str) -> None:
        """Something is wrong with manual fan control: give the fan back to the firmware."""
        if self.fan_owned:
            log.error("%s: %s; returning the fan to automatic control", self.key, why)
            self.release_fan()
            self.fan_fault = why

    def fan_tick(self, force: bool = False) -> None:
        fan = self._fan_cfg
        h = self.gpu.hwmon
        if not self.fan_owned or not fan or not h:
            return
        if self.gpu.asleep():
            return   # powered-down laptop GPU: reading sensors would wake it, and its fan is off anyway
        temps = self.gpu.temps()
        temp = temps.get(fan["sensor"])
        if temp is None:
            temp = temps.get("junction", temps.get("edge"))
        if temp is None:
            self._sensor_fails += 1
            if self._sensor_fails >= SENSOR_FAILS_MAX:
                self.fail_safe("temperature sensor is not readable")
            return
        self._sensor_fails = 0
        if fan["mode"] == "fixed":
            pct = float(fan["fixed_pct"])
        else:
            pct = T.fan_target(fan["curve"], temp)
        # Safety floor: close to any sensor's critical temperature the fan speeds up no matter
        # what the profile asks for, reaching 100% just before the limit.
        margin = self.gpu.thermal_margin(temps)
        floor = T.safety_floor(margin, SAFETY_MARGIN_C, EMERGENCY_MARGIN_C)
        if floor > pct:
            pct = floor
        elif fan["mode"] == "curve":
            # Hysteresis: only slow down once the temperature has really dropped.
            if (not force and self._last_pwm_pct is not None and pct < self._last_pwm_pct
                    and self._last_temp is not None and temp > self._last_temp - fan["hysteresis"]):
                return
        if not force and self._last_pwm_pct is not None and abs(pct - self._last_pwm_pct) < 1:
            return
        pmin = G.read_int(h / "pwm1_min") or 0
        pmax = G.read_int(h / "pwm1_max") or 255
        raw = int(round(pmin + (pmax - pmin) * pct / 100))
        try:
            if G.read_int(h / "pwm1_enable") != 1:   # driver reset (e.g. after resume)
                write(h / "pwm1_enable", "1")
            write(h / "pwm1", str(raw))
            self._last_pwm_pct = pct
            self._last_temp = temp
        except ApplyError as e:
            log.warning("fan tick: %s", e)


# ---------------------------------------------------------------- game detection

_STEAM_RE = re.compile(rb"SteamLaunch\x00AppId=(\d+)")


def running_games() -> tuple[set[str], set[str]]:
    """(steam app ids, executable basenames) of everything currently running."""
    appids, exes = set(), set()
    try:
        pids = [p for p in os.listdir(PROC) if p.isdigit()]
    except OSError:
        return appids, exes
    for pid in pids:
        try:
            with open(PROC / pid / "cmdline", "rb") as fh:
                cmd = fh.read(4096)
        except OSError:
            continue
        if not cmd:
            continue
        m = _STEAM_RE.search(cmd)
        if m:
            appids.add(m.group(1).decode())
        exe = cmd.split(b"\x00", 1)[0].replace(b"\\", b"/").rsplit(b"/", 1)[-1]
        if exe:
            exes.add(exe.decode(errors="replace").lower())
    return appids, exes


def match_rule(rules: list[dict], appids: set[str], exes: set[str]) -> dict | None:
    for r in rules:
        kind, _, val = str(r.get("match", "")).partition(":")
        if kind == "steam" and val in appids:
            return r
        if kind == "exe" and val.lower() in exes:
            return r
    return None


# ---------------------------------------------------------------- the daemon

def boot_id() -> str | None:
    """Changes on every boot; lets us tell a service restart from a fresh boot."""
    return G.read(PROC / "sys" / "kernel" / "random" / "boot_id")


def recover_fans(gpus: list[G.Gpu]) -> int:
    """Hand back every fan a previous instance left in manual mode (crash, kill, power cut).
    Also what `emberd --release-fans` runs when systemd stops the service."""
    n = 0
    for g in gpus:
        c = Controller(g)
        if not c._fan_marker.exists():
            continue
        h = g.hwmon
        try:
            if h and G.read_int(h / "pwm1_enable") == 1:
                write(h / "pwm1_enable", "2")
                n += 1
                log.warning("%s: fan was left in manual mode; returned to automatic", c.key)
        except ApplyError as e:
            log.error("%s: could not return fan to automatic: %s", c.key, e)
        try:
            c._fan_marker.unlink(missing_ok=True)
        except OSError:
            pass
    return n


class Daemon:
    def __init__(self):
        self.lock = threading.RLock()
        gpus = G.find_gpus()
        recover_fans(gpus)
        self.ctl: dict[str, Controller] = {g.pci_slot: Controller(g) for g in gpus}
        self.state = self._load()
        self.runtime: dict[str, dict] = {k: {"applied": None, "reason": None, "game": None, "error": None}
                                         for k in self.ctl}
        self.boot_skipped = False
        self._last_scan = self._last_drift = 0.0
        self.stop = threading.Event()
        self.conf = self._load_conf()
        for k, c in self.ctl.items():
            g = self._gpu_state(k)  # seed presets
            if c.gpu.od_path.exists():
                if not g.get("od_stock"):
                    # First time we see this GPU nothing has been applied yet: this is the factory table.
                    g["od_stock"] = G.parse_od(G.read(c.gpu.od_path))
                c.od_stock = g["od_stock"]

    # -- persistence
    def _load(self) -> dict:
        try:
            st = json.loads((STATE_DIR / "state.json").read_text())
            if isinstance(st, dict) and isinstance(st.get("gpus"), dict):
                return st
        except (OSError, ValueError):
            pass
        return {"version": 1, "gpus": {}}

    def _save(self) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATE_DIR / "state.json.tmp"
        tmp.write_text(json.dumps(self.state, indent=1))
        os.replace(tmp, STATE_DIR / "state.json")

    def _load_conf(self) -> dict:
        conf = {"groups": ["wheel"], "users": []}
        try:
            for line in CONF.read_text().splitlines():
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if k in ("groups", "users") and v:
                    conf[k] = [x.strip() for x in v.split(",") if x.strip()]
        except OSError:
            pass
        return conf

    def _gpu_state(self, key: str) -> dict:
        g = self.state["gpus"].setdefault(key, {})
        if "profiles" not in g:
            g["profiles"] = T.builtin_presets(self.ctl[key].state())
        g.setdefault("active", None)
        g.setdefault("apply_on_boot", False)
        g.setdefault("rules", [])
        return g

    # -- authorization
    def authorized(self, uid: int) -> bool:
        if uid == 0:
            return True
        try:
            pw = pwd.getpwuid(uid)
        except KeyError:
            return False
        if pw.pw_name in self.conf["users"]:
            return True
        names = set()
        for gid in os.getgrouplist(pw.pw_name, pw.pw_gid):
            try:
                names.add(grp.getgrgid(gid).gr_name)
            except KeyError:
                pass
        return bool(names & set(self.conf["groups"]))

    # -- profile resolution
    def effective(self, key: str) -> tuple[str | None, str, str | None]:
        """(profile name, reason, game label) that should be on the hardware."""
        g = self._gpu_state(key)
        rt = self.runtime[key]
        if rt.get("game_rule"):
            r = rt["game_rule"]
            if r.get("profile") in g["profiles"]:
                return r["profile"], "game", r.get("label") or r.get("match")
        return g["active"], "manual", None

    def reconcile(self, key: str, force: bool = False, skip_od: bool = False) -> None:
        with self.lock:
            name, reason, game = self.effective(key)
            rt = self.runtime[key]
            if not force and rt["applied"] == name and rt["reason"] == reason:
                return
            g = self._gpu_state(key)
            ctl = self.ctl[key]
            try:
                if name is None:
                    if rt["applied"] is not None or force:
                        ctl.restore_stock()
                else:
                    settings = copy.deepcopy(g["profiles"][name])
                    if skip_od:
                        settings["od"] = None
                    ctl.apply(settings)
                rt["error"] = None
            except (ApplyError, T.InvalidSettings) as e:
                rt["error"] = str(e)
            rt.update(applied=name, reason=reason, game=game, fan_fault=None)
            log.info("%s: profile=%s (%s%s)%s", key, name or "stock", reason,
                     f": {game}" if game else "", f" ERROR {rt['error']}" if rt["error"] else "")

    # -- commands
    def handle(self, req: dict, uid: int) -> dict:
        cmd = req.get("cmd")
        if cmd == "hello":
            return {"version": VERSION, "gpus": list(self.ctl), "authorized": self.authorized(uid)}
        if cmd == "state":
            with self.lock:
                return {"state": self.state, "runtime": self.runtime, "boot_skipped": self.boot_skipped,
                        "authorized": self.authorized(uid)}
        if not self.authorized(uid):
            raise PermissionError("not authorized (add your user to the 'wheel' group or /etc/ember/emberd.conf)")
        key = req.get("gpu")
        if key not in self.ctl:
            raise ValueError(f"unknown gpu {key!r}")
        with self.lock:
            g = self._gpu_state(key)
            if cmd == "save_profile":
                name = req.get("name")
                if not isinstance(name, str) or not name.strip() or len(name.strip()) > 40 \
                        or any(ord(ch) < 32 for ch in name):
                    raise ValueError("profile name must be 1-40 characters")
                name = name.strip()
                if name not in g["profiles"] and len(g["profiles"]) >= MAX_PROFILES:
                    raise ValueError(f"at most {MAX_PROFILES} profiles")
                clean = T.validate(req.get("settings"), self.ctl[key].state())
                g["profiles"][name] = clean
                if req.get("activate"):
                    g["active"] = name
                self._save()
                if self.effective(key)[0] == name:
                    self.reconcile(key, force=True)
            elif cmd == "delete_profile":
                name = req.get("name")
                if not isinstance(name, str):
                    raise ValueError("profile name must be text")
                g["profiles"].pop(name, None)
                if g["active"] == name:
                    g["active"] = None
                g["rules"] = [r for r in g["rules"] if r.get("profile") != name]
                self._save()
                self.reconcile(key)
            elif cmd == "activate":
                name = req.get("name")
                if name is not None and (not isinstance(name, str) or name not in g["profiles"]):
                    raise ValueError(f"no profile {name!r}")
                g["active"] = name
                self._save()
                self.reconcile(key, force=True)
            elif cmd == "set_rules":
                rules = req.get("rules") or []
                if not isinstance(rules, list):
                    raise ValueError("rules must be a list")
                clean = []
                for r in rules[:500]:
                    if not isinstance(r, dict):
                        continue
                    m = str(r.get("match", ""))
                    if not re.fullmatch(r"(steam:\d{1,12}|exe:[^/\x00]{1,128})", m):
                        continue
                    clean.append({"match": m, "label": str(r.get("label", ""))[:120],
                                  "profile": str(r.get("profile", ""))[:40]})
                g["rules"] = clean
                self._save()
            elif cmd == "set_update":
                from ember.core import update as U
                STATE_DIR.mkdir(parents=True, exist_ok=True)
                tmp = STATE_DIR / "update.json.tmp"
                tmp.write_text(json.dumps({"auto": bool(req.get("auto"))}))
                os.chmod(tmp, 0o644)
                os.replace(tmp, STATE_DIR / U.SETTINGS.name)
            elif cmd == "set_boot":
                g["apply_on_boot"] = bool(req.get("apply_on_boot"))
                self._save()
            elif cmd == "reset":
                g["active"] = None
                self.runtime[key]["game_rule"] = None
                self._save()
                self.reconcile(key, force=True)
            elif cmd == "reset_presets":
                g["profiles"].update(T.builtin_presets(self.ctl[key].state()))
                self._save()
                self.reconcile(key, force=True)
            else:
                raise ValueError(f"unknown command {cmd!r}")
            return {"runtime": self.runtime[key], "gpu_state": g}

    # -- lifecycle
    def boot(self) -> None:
        bid = boot_id()
        restarted = bid is not None and self.state.get("boot_id") == bid
        self.state["boot_id"] = bid
        if restarted:
            # Same boot: the service was restarted (an update, a crash). Put the active
            # profile back instead of silently dropping to stock.
            log.info("service restart within the same boot: restoring active profiles")
            for key in self.ctl:
                if self._gpu_state(key)["active"] is not None:
                    self.reconcile(key, force=True)
            self._save()
            return
        marker = STATE_DIR / "applying"
        crashed = marker.exists()
        if crashed:
            self.boot_skipped = True
            log.warning("previous boot did not survive applying clocks; skipping overclock this time")
        any_od = False
        for key in self.ctl:
            g = self._gpu_state(key)
            if not g["apply_on_boot"] or g["active"] is None:
                continue
            if g["profiles"].get(g["active"], {}).get("od"):
                any_od = True
        if any_od and not crashed:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            marker.write_text(str(time.time()))
        if any_od or crashed:
            t = threading.Timer(BOOT_GRACE_S, lambda: marker.unlink(missing_ok=True))
            t.daemon = True     # never hold up a shutdown
            t.start()
        for key in self.ctl:
            g = self._gpu_state(key)
            if not g["apply_on_boot"]:
                # Don't touch the hardware, but remember that nothing is applied.
                self.state["gpus"][key]["active"] = None
                continue
            self.reconcile(key, force=True, skip_od=crashed)
        self._save()

    def loop(self) -> None:
        failures = 0
        while not self.stop.wait(1.0):
            try:
                self._tick()
                failures = 0
            except Exception:  # the control loop must outlive any single bad read
                failures += 1
                if failures in (1, 10) or failures % 300 == 0:
                    log.exception("control loop error (%d in a row)", failures)
                if failures >= 3:
                    # Don't leave a fan at a stale fixed speed while we can't regulate it.
                    with self.lock:
                        for key, c in self.ctl.items():
                            c.fail_safe("control loop keeps failing")
                            self._note_fan_fault(key, c)

    def _note_fan_fault(self, key: str, c: Controller) -> None:
        if c.fan_fault and self.runtime[key].get("fan_fault") != c.fan_fault:
            self.runtime[key]["fan_fault"] = c.fan_fault
            self.runtime[key]["error"] = f"fan: {c.fan_fault}; the firmware controls the fan now"

    def _tick(self) -> None:
        with self.lock:
            for key, c in self.ctl.items():
                c.fan_tick()
                self._note_fan_fault(key, c)
        now = time.monotonic()
        if now - self._last_drift >= 5.0:
            self._last_drift = now
            for key, c in self.ctl.items():
                with self.lock:
                    if c.drifted():
                        log.info("%s: settings were reset (resume?), re-applying", key)
                        c.applied = None  # force OD rewrite too
                        self.reconcile(key, force=True)
        if now - self._last_scan >= 2.0:
            self._last_scan = now
            with self.lock:
                rules = {k: list(self._gpu_state(k)["rules"]) for k in self.ctl}
            if any(rules.values()):
                appids, exes = running_games()
                for key in self.ctl:
                    rule = match_rule(rules[key], appids, exes)
                    with self.lock:
                        if rule != self.runtime[key].get("game_rule"):
                            self.runtime[key]["game_rule"] = rule
                            self.reconcile(key)

    def shutdown(self) -> None:
        self.stop.set()
        with self.lock:
            for c in self.ctl.values():
                c.release_fan()


def peer_uid(sock: socket.socket) -> int:
    creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", creds)[1]


class Handler(socketserver.StreamRequestHandler):
    daemon_ref: Daemon
    timeout = CLIENT_TIMEOUT_S        # applied to the socket: idle clients can't pin a thread

    def handle(self):
        uid = peer_uid(self.request)
        while True:
            try:
                line = self.rfile.readline(MAX_REQUEST + 1)   # bounded: never buffer an endless line
            except OSError:
                break                                          # timed out or went away
            if not line:
                break
            if len(line) > MAX_REQUEST or not line.endswith(b"\n"):
                try:
                    self.wfile.write(b'{"ok": false, "error": "request too large"}\n')
                except OSError:
                    pass
                break
            try:
                req = json.loads(line)
                if not isinstance(req, dict):
                    raise ValueError("request must be an object")
                resp = {"ok": True, **self.daemon_ref.handle(req, uid)}
            except (ValueError, PermissionError, T.InvalidSettings, ApplyError) as e:
                resp = {"ok": False, "error": str(e)}
            except Exception as e:  # never let one bad request kill the daemon
                log.exception("request failed")
                resp = {"ok": False, "error": f"internal error: {e}"}
            try:
                self.wfile.write(json.dumps(resp).encode() + b"\n")
                self.wfile.flush()
            except OSError:
                break


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    """One thread per client, with a ceiling on clients overall and per user so that
    nobody can exhaust the daemon by opening connections and going quiet."""
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._clients_lock = threading.Lock()
        self._clients: dict[int, int] = {}

    def process_request(self, request, client_address):
        try:
            uid = peer_uid(request)
        except OSError:
            self.shutdown_request(request)
            return
        with self._clients_lock:
            if sum(self._clients.values()) >= MAX_CLIENTS or self._clients.get(uid, 0) >= MAX_CLIENTS_PER_UID:
                busy = True
            else:
                busy = False
                self._clients[uid] = self._clients.get(uid, 0) + 1
        if busy:
            try:
                request.sendall(b'{"ok": false, "error": "too many connections"}\n')
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            threading.Thread(target=self._serve, args=(request, client_address, uid), daemon=True).start()
        except RuntimeError:      # out of threads
            self._done(uid)
            self.shutdown_request(request)

    def _serve(self, request, client_address, uid):
        try:
            self.process_request_thread(request, client_address)   # handles errors and closes the socket
        finally:
            self._done(uid)

    def _done(self, uid: int) -> None:
        with self._clients_lock:
            left = self._clients.get(uid, 0) - 1
            if left > 0:
                self._clients[uid] = left
            else:
                self._clients.pop(uid, None)


def main() -> int:
    logging.basicConfig(level=os.environ.get("EMBER_LOG", "INFO"),
                        format="%(levelname)s %(message)s", stream=sys.stderr)
    if "--release-fans" in sys.argv[1:]:
        # ExecStopPost: runs after the service stopped for any reason, including a crash or SIGKILL.
        recover_fans(G.find_gpus())
        return 0
    d = Daemon()
    if not d.ctl:
        log.error("no amdgpu devices found")
        return 1
    for c in d.ctl.values():
        log.info("found %s (%s) caps=%s", c.gpu.describe()["name"], c.key, c.gpu.capabilities())
    d.boot()

    SOCKET.parent.mkdir(parents=True, exist_ok=True)
    try:
        SOCKET.unlink()
    except FileNotFoundError:
        pass
    Handler.daemon_ref = d
    srv = Server(str(SOCKET), Handler)
    os.chmod(SOCKET, 0o666)   # anyone may *read* state; writes are checked per-request

    def stop(*_):
        threading.Thread(target=srv.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    worker = threading.Thread(target=d.loop, daemon=True)
    worker.start()
    log.info("emberd %s listening on %s", VERSION, SOCKET)
    try:
        srv.serve_forever()
    finally:
        d.shutdown()
        srv.server_close()
        try:
            SOCKET.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
