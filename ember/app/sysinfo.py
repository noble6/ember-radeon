"""System report: driver stack, display session, and the optional gaming layers."""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from ember.core import gpu as G


def _run(cmd: list[str], timeout: float = 4.0) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _os_release() -> str:
    try:
        kv = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
        return kv.get("PRETTY_NAME", "Linux").strip('"')
    except OSError:
        return "Linux"


def _cpu() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return re.sub(r"\s+", " ", line.split(":", 1)[1]).strip()
    except OSError:
        pass
    return platform.processor() or "Unknown"


def _ram() -> int:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def _layer(name: str) -> bool:
    for d in ("/usr/share/vulkan/implicit_layer.d", "/etc/vulkan/implicit_layer.d",
              str(Path.home() / ".local/share/vulkan/implicit_layer.d")):
        p = Path(d)
        if p.is_dir() and any(name.lower() in f.name.lower() for f in p.iterdir()):
            return True
    return False


def _proton_variants() -> list[str]:
    out = []
    for d in (Path.home() / ".local/share/Steam/compatibilitytools.d", Path.home() / ".steam/root/compatibilitytools.d",
              Path("/usr/share/steam/compatibilitytools.d"), Path("/usr/local/share/steam/compatibilitytools.d")):
        if d.is_dir():
            out += sorted(p.name for p in d.iterdir() if p.is_dir())
    return sorted(set(out))


def collect() -> dict:
    vk = _run(["vulkaninfo", "--summary"])
    gl = _run(["glxinfo", "-B"]) if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") else ""

    def grab(text, pat):
        m = re.search(pat, text)
        return m.group(1).strip() if m else None

    mesa = grab(gl, r"OpenGL core profile version string:.*Mesa ([^\s]+)") or grab(vk, r"driverInfo\s*=\s*Mesa ([^\s]+)")
    mask = G.ppfeaturemask()
    protons = _proton_variants()
    fsr_capable = [p for p in protons if re.search(r"GE|cachyos|tkg|EM", p)]
    return {
        "os": _os_release(),
        "kernel": platform.release(),
        "session": f"{os.environ.get('XDG_SESSION_TYPE', '?').capitalize()} · {os.environ.get('XDG_CURRENT_DESKTOP', '?')}",
        "cpu": _cpu(),
        "ram": _ram(),
        "mesa": mesa,
        "gl_renderer": grab(gl, r"OpenGL renderer string:\s*(.+)"),
        "gl_version": grab(gl, r"OpenGL core profile version string:\s*([0-9.]+)"),
        "vk_api": grab(vk, r"apiVersion\s*=\s*([0-9.]+)"),
        "vk_driver": grab(vk, r"driverName\s*=\s*(\S+)"),
        "vk_device": grab(vk, r"deviceName\s*=\s*(.+)"),
        "drm": grab(gl, r"DRM ([0-9.]+)"),
        "ppfeaturemask": f"0x{mask:08x}" if mask is not None else None,
        "overdrive_kernel": G.overdrive_enabled_in_kernel(),
        "layers": {
            "antilag": _layer("anti_lag"),
            "vkbasalt": _layer("vkbasalt"),
            "mangohud": _layer("mangohud") or bool(shutil.which("mangohud")),
            "gamescope": bool(shutil.which("gamescope")),
            "proton_fsr": bool(fsr_capable),
            "proton_cachyos": any("cachyos" in p.lower() for p in protons),
            "gpu_screen_recorder": bool(shutil.which("gpu-screen-recorder")),
            "lsfg": _layer("lsfg"),
        },
        "legacy_radeon": G.legacy_radeon_cards(),
        "protons": protons,
    }
