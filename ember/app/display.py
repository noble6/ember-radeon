"""Display settings (FreeSync/VRR, refresh, HDR, colour) via KDE's kscreen-doctor, plus EDID facts.

Wayland compositors own display configuration, so there is no driver-level API
to call like on Windows; KDE exposes everything through kscreen-doctor.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from ember.core import gpu as G

VRR = {0: "never", 1: "always", 2: "automatic"}
RGB = {0: "automatic", 1: "full", 2: "limited"}
KEYS = {"vrrpolicy": set(VRR.values()), "rgbrange": set(RGB.values()), "hdr": {"enable", "disable"},
        "wcg": {"enable", "disable"}}


def _env() -> dict:
    # kscreen-doctor is a Qt app: it must talk to the real compositor, never inherit an offscreen platform.
    env = dict(os.environ)
    env.pop("QT_QPA_PLATFORM", None)
    return env


def available() -> bool:
    return bool(shutil.which("kscreen-doctor")) and "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "")


def parse_edid(blob: bytes) -> dict:
    out = {}
    if len(blob) < 128 or blob[:8] != b"\x00\xff\xff\xff\xff\xff\xff\x00":
        return out
    m = ((blob[8] << 8) | blob[9])
    out["vendor"] = "".join(chr(64 + ((m >> s) & 0x1F)) for s in (10, 5, 0))
    for off in (54, 72, 90, 108):
        d = blob[off:off + 18]
        if d[0] or d[1]:
            continue
        tag = d[3]
        if tag == 0xFC:
            out["model"] = d[5:18].split(b"\n")[0].decode("ascii", "replace").strip()
        elif tag == 0xFD:
            flags = d[4]
            vmin = d[5] + (255 if flags & 0x01 else 0)
            vmax = d[6] + (255 if flags & 0x02 else 0)
            out["vrange"] = [vmin, vmax]
    # AMD FreeSync VSDB (OUI 00-00-1A) in the CTA-861 extension carries the real VRR range.
    for ext in range(1, len(blob) // 128):
        e = blob[ext * 128:(ext + 1) * 128]
        if e[0] != 0x02:
            continue
        dtd = e[2]
        i = 4
        while i < dtd and i < 127:
            tag, ln = e[i] >> 5, e[i] & 0x1F
            body = e[i + 1:i + 1 + ln]
            if tag == 3 and len(body) >= 8 and body[0:3] == b"\x1a\x00\x00":
                out["freesync"] = [body[5], body[6]]
            i += 1 + ln
    return out


def _edid_for(name: str) -> dict:
    for p in G._p("/sys/class/drm").glob(f"card*-{name}"):
        try:
            return parse_edid((p / "edid").read_bytes())
        except OSError:
            pass
    # kscreen names HDMI as HDMI-A-1 in DRM
    alt = name.replace("HDMI-", "HDMI-A-") if "HDMI-A" not in name else name
    for p in G._p("/sys/class/drm").glob(f"card*-{alt}"):
        try:
            return parse_edid((p / "edid").read_bytes())
        except OSError:
            pass
    return {}


def outputs() -> list[dict]:
    if not available():
        return []
    try:
        data = json.loads(subprocess.run(["kscreen-doctor", "-j"], capture_output=True, text=True, timeout=5, env=_env()).stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    res = []
    for o in data.get("outputs", []):
        if not o.get("connected"):
            continue
        modes = []
        for m in o.get("modes", []):
            sz = m.get("size", {})
            modes.append({"id": str(m["id"]), "w": sz.get("width"), "h": sz.get("height"),
                          "hz": round(m.get("refreshRate", 0), 2)})
        modes.sort(key=lambda m: (-(m["w"] or 0) * (m["h"] or 0), -m["hz"]))
        cur = next((m for m in modes if m["id"] == str(o.get("currentModeId"))), None)
        edid = _edid_for(o["name"])
        res.append({
            "name": o["name"], "enabled": o.get("enabled", False),
            "model": " ".join(x for x in (edid.get("vendor"), edid.get("model")) if x) or o["name"],
            "vrange": edid.get("freesync") or edid.get("vrange"),
            "modes": modes, "current": cur,
            "vrr": VRR.get(o.get("vrrPolicy", 0), "never"),
            "rgb": RGB.get(o.get("rgbRange", 0), "automatic"),
            "max_bpc": o.get("maxBpc", 0), "hdr": bool(o.get("hdr")), "wcg": bool(o.get("wcg")),
            "brightness": round(100 * float(o.get("brightness", 1.0))),
            "ddc": bool(o.get("ddcCiAllowed")),
            "scale": o.get("scale", 1),
        })
    return res


def set_option(output: str, key: str, value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", output):
        raise ValueError("bad output name")
    value = str(value)
    if key in KEYS:
        if value not in KEYS[key]:
            raise ValueError(f"{key}: {value!r}")
    elif key == "mode":
        if not re.fullmatch(r"\d{1,4}", value):
            raise ValueError("bad mode")
    elif key in ("brightness", "maxbpc"):
        if not re.fullmatch(r"\d{1,3}", value):
            raise ValueError(f"bad {key}")
    else:
        raise ValueError(f"unsupported setting {key}")
    r = subprocess.run(["kscreen-doctor", f"output.{output}.{key}.{value}"], capture_output=True, text=True, timeout=10, env=_env())
    err = (r.stderr or "").strip()
    if r.returncode != 0 or "Unable" in err or "error" in err.lower():
        raise RuntimeError(err or "kscreen-doctor failed")
