"""Tuning settings: schema, defaults, validation and the built-in presets.

A *settings* dict is what a profile stores and what the daemon applies:

    {
      "perf_level":    "auto" | "low" | "high" | "manual",
      "power_profile": int | None,          # pp_power_profile_mode index, None = leave
      "power_cap_w":   float | None,        # None = board default
      "fan": {"mode": "auto" | "fixed" | "curve",
              "fixed_pct": 0-100,
              "curve": [[temp_c, pct], ...],  # 2-8 points, increasing temp
              "sensor": "junction" | "edge" | "mem",
              "hysteresis": 0-10},
      "od": None | {"sclk_min": int|None, "sclk_max": int|None,
                    "mclk_max": int|None, "vddgfx_offset": int|None}
    }
"""
from __future__ import annotations

import copy

from ember.core.gpu import od_controls

PERF_LEVELS = ("auto", "low", "high", "manual")
FAN_MODES = ("auto", "fixed", "curve")
FAN_SENSORS = ("junction", "edge", "mem")

DEFAULT_CURVE = [[40, 0], [55, 30], [65, 42], [75, 60], [85, 85], [95, 100]]

DEFAULTS = {
    "perf_level": "auto",
    "power_profile": None,
    "power_cap_w": None,
    "fan": {"mode": "auto", "fixed_pct": 50, "curve": DEFAULT_CURVE, "sensor": "junction", "hysteresis": 3},
    "od": None,
}


def _profile_index(profiles: list[dict], name: str) -> int | None:
    for p in profiles:
        if p["name"] == name:
            return p["index"]
    return None


def builtin_presets(tuning_state: dict) -> dict[str, dict]:
    """Quiet / Balanced / Performance, derived from what this board allows."""
    profiles = tuning_state.get("power_profiles") or []
    cap = tuning_state.get("power_cap") or {}
    cmin, cmax, cdef = cap.get("min"), cap.get("max"), cap.get("default")

    def s(**kw):
        d = copy.deepcopy(DEFAULTS)
        for k, v in kw.items():
            if k == "fan":
                d["fan"].update(v)
            else:
                d[k] = v
        return d

    quiet_cap = None
    if cmin is not None and cdef is not None:
        quiet_cap = round(max(cmin, cdef * 0.85), 1)
    return {
        "Quiet": s(power_profile=_profile_index(profiles, "POWER_SAVING"), power_cap_w=quiet_cap,
                   fan={"mode": "curve", "curve": [[45, 0], [60, 25], [72, 38], [82, 55], [90, 80], [98, 100]]}),
        "Balanced": s(power_profile=_profile_index(profiles, "BOOTUP_DEFAULT")),
        "Performance": s(power_profile=_profile_index(profiles, "3D_FULL_SCREEN"),
                         power_cap_w=cmax,
                         fan={"mode": "curve", "curve": [[35, 25], [50, 38], [62, 52], [72, 70], [82, 90], [90, 100]]}),
    }


class InvalidSettings(ValueError):
    pass


def _num(v, lo, hi, name, integer=False):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise InvalidSettings(f"{name}: not a number")
    if f != f or f in (float("inf"), float("-inf")):
        raise InvalidSettings(f"{name}: not a number")
    if lo is not None:
        f = max(lo, f)
    if hi is not None:
        f = min(hi, f)
    return int(round(f)) if integer else round(f, 1)


def validate(settings: dict, tuning_state: dict) -> dict:
    """Return a clean copy of settings clamped to what the hardware reports.

    This is the security boundary: the daemon runs as root and only ever writes
    values that came out of this function.
    """
    if not isinstance(settings, dict):
        raise InvalidSettings("settings must be an object")
    out = copy.deepcopy(DEFAULTS)

    pl = settings.get("perf_level", "auto")
    if pl not in PERF_LEVELS:
        raise InvalidSettings(f"perf_level: {pl!r}")
    out["perf_level"] = pl

    pp = settings.get("power_profile")
    if pp is not None:
        valid = {p["index"] for p in tuning_state.get("power_profiles") or []}
        try:
            pp = int(pp)
        except (TypeError, ValueError):
            raise InvalidSettings("power_profile: not an index")
        if pp not in valid:
            raise InvalidSettings(f"power_profile: {pp} not offered by this GPU")
        out["power_profile"] = pp

    cap = tuning_state.get("power_cap") or {}
    if settings.get("power_cap_w") is not None:
        if cap.get("min") is None or cap.get("max") is None:
            raise InvalidSettings("power cap not supported")
        out["power_cap_w"] = _num(settings["power_cap_w"], cap["min"], cap["max"], "power_cap_w")

    fan = settings.get("fan") or {}
    if not isinstance(fan, dict):
        raise InvalidSettings("fan must be an object")
    mode = fan.get("mode", "auto")
    if mode not in FAN_MODES:
        raise InvalidSettings(f"fan.mode: {mode!r}")
    out["fan"]["mode"] = mode
    out["fan"]["fixed_pct"] = _num(fan.get("fixed_pct", 50), 0, 100, "fan.fixed_pct", True)
    sensor = fan.get("sensor", "junction")
    out["fan"]["sensor"] = sensor if sensor in FAN_SENSORS else "junction"
    out["fan"]["hysteresis"] = _num(fan.get("hysteresis", 3), 0, 10, "fan.hysteresis", True)
    curve = fan.get("curve", DEFAULT_CURVE)
    if not isinstance(curve, list) or not 2 <= len(curve) <= 8:
        raise InvalidSettings("fan.curve: need 2-8 points")
    pts = []
    for p in curve:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise InvalidSettings("fan.curve: points are [temp, pct]")
        pts.append([_num(p[0], 0, 115, "curve temp", True), _num(p[1], 0, 100, "curve pct", True)])
    pts.sort(key=lambda p: p[0])
    # A curve must never *decrease* fan speed as temperature rises.
    for i in range(1, len(pts)):
        pts[i][1] = max(pts[i][1], pts[i - 1][1])
    out["fan"]["curve"] = pts

    fw = fan.get("fw") or {}
    avail = tuning_state.get("fan_ctrl") or {}
    if isinstance(fw, dict) and fw:
        clean_fw = {}
        for k, v in fw.items():
            if k in avail and v is not None:
                rng = avail[k].get("range")
                if not rng or rng[0] is None or rng[1] is None:
                    continue   # the driver did not report limits: don't guess
                clean_fw[k] = _num(v, rng[0], rng[1], f"fan.fw.{k}", True)
        out["fan"]["fw"] = clean_fw

    od = settings.get("od")
    if od:
        if not isinstance(od, dict):
            raise InvalidSettings("od must be an object")
        od_state = tuning_state.get("od")
        if not od_state:
            raise InvalidSettings("overdrive is not enabled (amdgpu.ppfeaturemask)")
        controls = {c["key"]: c for c in od_controls(od_state, tuning_state.get("od_stock"))}
        clean = {}
        for k, v in od.items():
            if v is None:
                continue
            c = controls.get(k)
            if c is None:
                continue  # control not offered by this generation: ignore rather than fail
            clean[k] = _num(v, c["from"], c["to"], k, True)
        if "sclk_min" in clean and "sclk_max" in clean and clean["sclk_min"] > clean["sclk_max"]:
            raise InvalidSettings("sclk_min above sclk_max")
        out["od"] = clean or None
    return out


def fan_target(curve: list, temp: float) -> float:
    """Linear interpolation over the curve (flat beyond its ends)."""
    if not curve:
        return 100.0
    if temp <= curve[0][0]:
        return float(curve[0][1])
    for (t0, p0), (t1, p1) in zip(curve, curve[1:]):
        if temp <= t1:
            if t1 == t0:
                return float(p1)
            return p0 + (p1 - p0) * (temp - t0) / (t1 - t0)
    return float(curve[-1][1])


def safety_floor(margin: float | None, start: float = 20.0, emergency: float = 5.0) -> float:
    """Minimum fan speed (%) given how many degrees are left before a critical temperature.

    0 while there is plenty of headroom, 40% once `start` degrees remain, rising to
    100% at `emergency` degrees. Applied on top of any fixed speed or curve.
    """
    if margin is None or margin >= start:
        return 0.0
    if margin <= emergency:
        return 100.0
    return 40.0 + (start - margin) / (start - emergency) * 60.0


def resample_curve(curve: list, n: int, lo: int = 25, hi: int = 100) -> list:
    """Firmware fan tables (RDNA3) take a fixed number of points."""
    if n <= 1:
        return [[hi, 100]]
    step = (hi - lo) / (n - 1)
    return [[int(lo + i * step), int(round(fan_target(curve, lo + i * step)))] for i in range(n)]
