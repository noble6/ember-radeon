"""Shader caches: Mesa's (all GL/Vulkan apps) and Steam's per-game pre-caches.

"Reset shader cache" is a classic driver-panel fix for stutter or corruption after
driver updates; on Linux the caches are plain directories we can measure and clear.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from ember.core import games as GM


def _size(p: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(p):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def mesa_dirs() -> list[Path]:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    custom = os.environ.get("MESA_SHADER_CACHE_DIR")
    cands = [Path(custom)] if custom else []
    cands += [base / "mesa_shader_cache", base / "mesa_shader_cache_db", base / "radv_builtin_shaders"]
    return [p for p in cands if p.is_dir()]


def steam_dirs() -> dict[str, Path]:
    root = GM.steam_root()
    out = {}
    if not root:
        return out
    for lib in GM.steam_libraries(root):
        sc = lib / "steamapps" / "shadercache"
        if sc.is_dir():
            for d in sc.iterdir():
                if d.is_dir() and d.name.isdigit():
                    out[d.name] = d
    return out


def scan() -> dict:
    names = {g["appid"]: g["name"] for g in GM.scan_steam()}
    mesa = sum(_size(p) for p in mesa_dirs())
    games = []
    for appid, d in steam_dirs().items():
        sz = _size(d)
        if sz:
            games.append({"id": f"steam:{appid}", "name": names.get(appid, f"App {appid}"), "bytes": sz})
    games.sort(key=lambda g: -g["bytes"])
    return {"mesa": mesa, "games": games}


def clear(which: str) -> int:
    """Delete one cache. Only ever touches the directories found above."""
    if which == "mesa":
        targets = mesa_dirs()
    else:
        m = re.fullmatch(r"steam:(\d+)", which)
        if not m:
            raise ValueError("unknown cache")
        d = steam_dirs().get(m.group(1))
        targets = [d] if d else []
    freed = 0
    for t in targets:
        freed += _size(t)
        for child in t.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
    return freed
