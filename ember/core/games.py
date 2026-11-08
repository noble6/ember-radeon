"""Games: Steam library discovery, per-game graphics options, launch-option wiring.

The graphics options map Adrenalin-style features onto what the open Linux stack
actually provides:

    Anti-Lag            -> Mesa's VK_LAYER_MESA_anti_lag (ENABLE_LAYER_MESA_ANTI_LAG)
    Image sharpening    -> vkBasalt CAS (AMD FidelityFX Contrast Adaptive Sharpening)
    FSR 4 (ML)          -> PROTON_FSR4_UPGRADE (Proton-GE / proton-cachyos; RDNA2-4)
    FSR Redstone FG     -> MLFG_UPGRADE (custom Proton)
    RSR / integer / VSR -> gamescope -F fsr|nis|pixel / -S integer, render scale above or below output
    Morphological AA    -> vkBasalt SMAA / FXAA
    Anisotropic filter  -> RADV_TEX_ANISO
    FSR 3 anywhere      -> OptiScaler (PROTON_USE_OPTISCALER) swaps DLSS/XeSS for FSR 3.1/4 + FSR 3 FG
    "Ember active" bar  -> MangoHud custom_text banner, swapped out after a few seconds (inotify reload)
    Frame rate target   -> MangoHud fps_limit
    Performance overlay -> MangoHud
    VSync / present     -> MESA_VK_WSI_PRESENT_MODE
    FSR 1 upscaling     -> WINE_FULLSCREEN_FSR (Proton-GE / proton-cachyos)
    HDR                 -> Proton's Wayland driver + DXVK_HDR
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ember"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "ember"
GAMES_FILE = CONFIG_DIR / "games.json"
WRAPPER = "ember-run"

GRAPHICS_DEFAULTS = {
    "antilag": False,
    "sharpen": 0,           # 0 = off, else CAS strength 1-100
    "fps_cap": 0,           # 0 = off
    "overlay": "off",       # off | minimal | standard | detailed
    "present_mode": "default",  # default | fifo | mailbox | immediate
    "fsr": False,
    "fsr_strength": 2,      # 0 (sharpest) .. 5
    "hdr": False,
    "fsr4": False,          # FSR 3.1 -> FSR 4 upgrade inside Proton
    "fsr4_indicator": False,
    "mlfg": False,          # FSR "Redstone" ML frame generation
    "optiscaler": False,    # FSR 3.1/4 in games that only ship DLSS or XeSS (OptiScaler via Proton)
    "opti_fg": False,       # FSR 3 frame generation through OptiScaler
    "banner": True,         # in-game "Ember active" banner for the first seconds
    "aa": "off",            # off | fxaa | smaa  (vkBasalt)
    "aniso": 0,             # 0 = app, else 2/4/8/16 (RADV)
    "gamescope": False,     # driver-level upscaling ("RSR") via gamescope
    "gs_scale": 77,         # render resolution as % of the display (>100 = super resolution)
    "gs_filter": "fsr",     # fsr | nis | linear | nearest | integer
    "gs_sharpness": 2,      # 0 (sharpest) .. 20
    "gs_out_w": 0, "gs_out_h": 0, "gs_refresh": 0,   # filled in from the display at save time
}
GS_FILTERS = ("fsr", "nis", "linear", "nearest", "integer")
AA_MODES = ("off", "fxaa", "smaa")
OVERLAYS = {
    "minimal": "fps_only,position=top-left",
    "standard": "fps,frametime,frame_timing,gpu_stats,gpu_temp,gpu_core_clock,gpu_power,vram,cpu_stats,cpu_temp,position=top-left",
    "detailed": "full,position=top-left",
}
PRESENT_MODES = ("default", "fifo", "mailbox", "immediate")

# Not games: compatibility tools and runtimes that also have app manifests.
_TOOL_RE = re.compile(r"^(Proton|Steam Linux Runtime|Steamworks Common|SteamVR)", re.I)
_TOOL_IDS = {"228980", "1070560", "1391110", "1628350", "4183110", "1493710", "2180100", "2805730"}


def steam_root() -> Path | None:
    for p in (Path.home() / ".local/share/Steam", Path.home() / ".steam/steam",
              Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam"):
        if (p / "steamapps").is_dir():
            return p.resolve()
    return None


# ---------------------------------------------------------------- minimal VDF

def _tokens(text: str):
    """Yield (kind, value, start, end) for text VDF: kind is 's', '{' or '}'."""
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "/" and text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif c in "{}":
            yield c, c, i, i + 1
            i += 1
        elif c == '"':
            j, buf = i + 1, []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append({"n": "\n", "t": "\t", "\\": "\\", '"': '"'}.get(text[j + 1], text[j + 1]))
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            yield "s", "".join(buf), i, j + 1
            i = j + 1
        else:  # unquoted token
            j = i
            while j < n and text[j] not in " \t\r\n{}\"":
                j += 1
            yield "s", text[i:j], i, j
            i = j


def vdf_parse(text: str) -> dict:
    root: dict = {}
    stack = [root]
    key = None
    for kind, val, *_ in _tokens(text):
        if kind == "s":
            if key is None:
                key = val
            else:
                stack[-1][key] = val
                key = None
        elif kind == "{":
            d = {}
            stack[-1][key] = d
            stack.append(d)
            key = None
        else:
            if len(stack) > 1:
                stack.pop()
    return root


def vdf_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _find_block(text: str, path: list[str]):
    """Locate the {...} block at `path` (case-insensitive keys).

    Returns (open_brace_pos, close_brace_pos, {child_key_lower: (value_start, value_end)}).
    """
    toks = list(_tokens(text))
    depth = 0
    want = [p.lower() for p in path]
    matched = 0          # how many path components we are inside
    i = 0
    pending_key = None
    while i < len(toks):
        kind, val, s, e = toks[i]
        if kind == "s":
            if pending_key is None:
                pending_key = (val, s, e)
            else:
                pending_key = None
        elif kind == "{":
            k = pending_key[0].lower() if pending_key else None
            pending_key = None
            depth += 1
            if matched == depth - 1 and matched < len(want) and k == want[matched]:
                matched += 1
                if matched == len(want):
                    # collect direct string children
                    children = {}
                    j, d2, ck = i + 1, 0, None
                    while j < len(toks):
                        kk, vv, ss, ee = toks[j]
                        if kk == "{":
                            d2 += 1
                            ck = None
                        elif kk == "}":
                            if d2 == 0:
                                return s, ss, children
                            d2 -= 1
                        elif d2 == 0:
                            if ck is None:
                                ck = vv
                            else:
                                children[ck.lower()] = (ss, ee)
                                ck = None
                        j += 1
                    return None
        else:
            if matched == depth:
                matched -= 1
            depth -= 1
            pending_key = None
        i += 1
    return None


def vdf_set(text: str, path: list[str], key: str, value: str) -> str:
    """Set path/key = value by splicing text; every other byte is preserved."""
    blk = _find_block(text, path)
    if blk is None:
        # create the innermost missing block under its parent
        if len(path) < 2:
            raise KeyError("/".join(path))
        text = vdf_set_block(text, path[:-1], path[-1])
        blk = _find_block(text, path)
        if blk is None:
            raise KeyError("/".join(path))
    open_pos, close_pos, children = blk
    quoted = f'"{vdf_escape(value)}"'
    if key.lower() in children:
        s, e = children[key.lower()]
        return text[:s] + quoted + text[e:]
    indent = _indent_after(text, open_pos) + "\t"
    line = f'\n{indent}"{key}"\t\t{quoted}'
    return text[:open_pos + 1] + line + text[open_pos + 1:]


def vdf_set_block(text: str, parent: list[str], name: str) -> str:
    blk = _find_block(text, parent)
    if blk is None:
        raise KeyError("/".join(parent))
    open_pos = blk[0]
    ind = _indent_after(text, open_pos)
    inner = ind + "\t"
    ins = f'\n{inner}"{name}"\n{inner}{{\n{inner}}}'
    return text[:open_pos + 1] + ins + text[open_pos + 1:]


def _indent_after(text: str, pos: int) -> str:
    line_start = text.rfind("\n", 0, pos) + 1
    m = re.match(r"[ \t]*", text[line_start:pos])
    return m.group(0) if m else ""


# ---------------------------------------------------------------- Steam

def steam_running() -> bool:
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/comm") as fh:
                if fh.read().strip() in ("steam", "steamwebhelper"):
                    return True
        except OSError:
            pass
    return False


def steam_libraries(root: Path) -> list[Path]:
    libs = [root]
    try:
        data = vdf_parse((root / "steamapps/libraryfolders.vdf").read_text(errors="replace"))
        for v in (data.get("libraryfolders") or {}).values():
            if isinstance(v, dict) and v.get("path"):
                p = Path(v["path"])
                if p.resolve() != root and (p / "steamapps").is_dir():
                    libs.append(p)
    except OSError:
        pass
    return libs


def _art(root: Path, appid: str) -> dict:
    base = root / "appcache/librarycache" / appid
    out = {}
    for key, names in (("cover", ["library_600x900.jpg", "library_600x900_2x.jpg"]),
                       ("hero", ["library_hero.jpg"]), ("logo", ["logo.png"]), ("header", ["header.jpg"])):
        for n in names:
            hits = [base / n] + list(base.glob(f"*/{n}"))
            for h in hits:
                if h.is_file():
                    out[key] = str(h)
                    break
            if key in out:
                break
    return out


def local_config_paths(root: Path) -> list[Path]:
    return sorted((root / "userdata").glob("*/config/localconfig.vdf"))


def launch_options(root: Path) -> dict[str, str]:
    """appid -> launch options string (first user that has any)."""
    out: dict[str, str] = {}
    for lc in local_config_paths(root):
        try:
            data = vdf_parse(lc.read_text(errors="replace"))
        except OSError:
            continue
        apps = _ci(_ci(_ci(_ci(data, "UserLocalConfigStore"), "Software"), "Valve"), "Steam")
        apps = _ci(apps, "apps")
        for appid, blob in (apps or {}).items():
            if isinstance(blob, dict):
                lo = _ci(blob, "LaunchOptions")
                if isinstance(lo, str) and appid not in out:
                    out[appid] = lo
    return out


def _ci(d, key):
    if not isinstance(d, dict):
        return None
    for k, v in d.items():
        if k.lower() == key.lower():
            return v
    return None


def scan_steam() -> list[dict]:
    root = steam_root()
    if not root:
        return []
    los = launch_options(root)
    games = []
    seen = set()
    for lib in steam_libraries(root):
        for acf in sorted((lib / "steamapps").glob("appmanifest_*.acf")):
            try:
                st = vdf_parse(acf.read_text(errors="replace")).get("AppState", {})
            except OSError:
                continue
            appid, name = st.get("appid"), st.get("name") or ""
            if not appid or appid in seen or appid in _TOOL_IDS or _TOOL_RE.match(name):
                continue
            seen.add(appid)
            lo = los.get(appid, "")
            games.append({
                "id": f"steam:{appid}", "appid": appid, "name": name, "source": "Steam",
                "installdir": str(lib / "steamapps/common" / st.get("installdir", "")),
                "size": int(st.get("SizeOnDisk") or 0),
                "last_played": int(st.get("LastPlayed") or 0),
                "launch_options": lo, "wired": WRAPPER in lo,
                **_art(root, appid),
            })
    games.sort(key=lambda g: (-g["last_played"], g["name"].lower()))
    return games


def wire_launch_options(current: str, enable: bool) -> str:
    cur = (current or "").strip()
    has = re.search(rf"(^|\s){re.escape(WRAPPER)}(\s|$)", cur)
    if enable:
        if has:
            return cur
        if "%command%" in cur:
            return cur.replace("%command%", f"{WRAPPER} %command%", 1)
        return f"{WRAPPER} %command% {cur}".strip()
    if not has:
        return cur
    out = re.sub(rf"(^|\s){re.escape(WRAPPER)}(?=\s|$)", r"\1", cur)
    out = re.sub(r"\s+", " ", out).strip()
    return "" if out == "%command%" else out


def set_steam_launch_option(appid: str, enable: bool) -> str:
    """Add/remove the ember-run wrapper in every Steam user's localconfig.vdf.

    Steam rewrites localconfig.vdf on exit, so this refuses while Steam runs.
    """
    if not re.fullmatch(r"\d{1,12}", str(appid)):
        raise ValueError("bad appid")
    root = steam_root()
    if not root:
        raise RuntimeError("Steam not found")
    if steam_running():
        raise RuntimeError("Close Steam first - it overwrites launch options when it exits")
    result = ""
    paths = local_config_paths(root)
    if not paths:
        raise RuntimeError("no Steam user config found")
    for lc in paths:
        text = lc.read_text(errors="surrogateescape")
        data = vdf_parse(text)
        apps_path = ["UserLocalConfigStore", "Software", "Valve", "Steam", "apps"]
        apps = data
        for k in apps_path:
            apps = _ci(apps, k)
        cur = ""
        if isinstance(apps, dict) and isinstance(_ci(apps, appid), dict):
            cur = _ci(_ci(apps, appid), "LaunchOptions") or ""
        new = wire_launch_options(cur, enable)
        if new == cur:
            result = new
            continue
        if _find_block(text, apps_path + [appid]) is None and _find_block(text, apps_path) is None:
            continue
        patched = vdf_set(text, apps_path + [appid], "LaunchOptions", new)
        if not _only_launch_option_changed(text, patched, apps_path, appid, new):
            raise RuntimeError("refusing to write: patch verification failed")
        backup = lc.with_name(f"localconfig.vdf.ember-{int(time.time())}.bak")
        shutil.copy2(lc, backup)
        tmp = lc.with_suffix(".vdf.ember-tmp")
        tmp.write_text(patched, errors="surrogateescape")
        os.replace(tmp, lc)
        result = new
    return result


def _strip_launch_option(tree: dict, apps_path: list[str], appid: str) -> dict:
    tree = json.loads(json.dumps(tree))
    apps = tree
    for k in apps_path:
        apps = _ci(apps, k)
    if isinstance(apps, dict):
        for k in list(apps):
            if k.lower() == appid.lower() and isinstance(apps[k], dict):
                for kk in [kk for kk in apps[k] if kk.lower() == "launchoptions"]:
                    del apps[k][kk]
                if not apps[k]:
                    del apps[k]
    return tree


def _only_launch_option_changed(before: str, after: str, apps_path, appid, value) -> bool:
    """The patched file must parse to the same tree except our one value."""
    b, a = vdf_parse(before), vdf_parse(after)
    apps = a
    for k in apps_path:
        apps = _ci(apps, k)
    if _ci(_ci(apps, appid), "LaunchOptions") != value:
        return False
    return _strip_launch_option(a, apps_path, appid) == _strip_launch_option(b, apps_path, appid)


# ---------------------------------------------------------------- per-game graphics

def load_games_config() -> dict:
    try:
        cfg = json.loads(GAMES_FILE.read_text())
        if isinstance(cfg, dict):
            cfg.setdefault("defaults", dict(GRAPHICS_DEFAULTS))
            cfg.setdefault("games", {})
            cfg.setdefault("custom", [])
            return cfg
    except (OSError, ValueError):
        pass
    return {"defaults": dict(GRAPHICS_DEFAULTS), "games": {}, "custom": []}


def save_games_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = GAMES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=1))
    os.replace(tmp, GAMES_FILE)


def graphics_for(cfg: dict, game_id: str | None) -> dict:
    out = dict(GRAPHICS_DEFAULTS)
    out.update({k: v for k, v in (cfg.get("defaults") or {}).items() if k in GRAPHICS_DEFAULTS})
    if game_id:
        g = (cfg.get("games") or {}).get(game_id) or {}
        if not g.get("use_defaults", True):
            out.update({k: v for k, v in g.items() if k in GRAPHICS_DEFAULTS})
    return out


def gamescope_args(gfx: dict) -> list[str]:
    """gamescope command line for driver-level upscaling (RSR), integer scaling or super resolution."""
    ow, oh = int(gfx.get("gs_out_w") or 0), int(gfx.get("gs_out_h") or 0)
    if not ow or not oh:
        ow, oh = 1920, 1080
    scale = max(33, min(200, int(gfx.get("gs_scale") or 100))) / 100
    rw, rh = max(320, int(round(ow * scale / 2)) * 2), max(200, int(round(oh * scale / 2)) * 2)
    filt = gfx.get("gs_filter", "fsr")
    args = ["gamescope", "-W", str(ow), "-H", str(oh), "-w", str(rw), "-h", str(rh), "-f"]
    if int(gfx.get("gs_refresh") or 0):
        args += ["-r", str(int(gfx["gs_refresh"]))]
    if filt == "integer":
        args += ["-S", "integer", "-F", "nearest"]
    elif filt in ("fsr", "nis"):
        args += ["-F", filt, "--sharpness", str(max(0, min(20, int(gfx.get("gs_sharpness", 2)))))]
    elif filt in ("linear", "nearest"):
        args += ["-F", filt]
    if gfx.get("hdr"):
        args += ["--hdr-enabled"]
    if int(gfx.get("fps_cap") or 0) > 0:
        args += ["-o", str(int(gfx["fps_cap"]))]   # unfocused limit keeps alt-tab cheap
    return args + ["--"]


def mangohud_lines(gfx: dict, banner: list[str] | None = None) -> list[str] | None:
    """MangoHud config for this game. None = MangoHud not needed at all."""
    fps = int(gfx.get("fps_cap") or 0)
    overlay = gfx.get("overlay", "off")
    lines: list[str] = []
    if fps > 0:
        lines += [f"fps_limit={fps}", "fps_limit_method=late"]
    if banner:
        lines += ["legacy_layout=0", "position=top-center", "font_size=22", "round_corners=14",
                  "background_alpha=0.82", "background_color=1A0A0E", "text_color=FFFFFF",
                  "hud_no_margin", f"custom_text_center={banner[0]}"]
        lines += [f"custom_text_center={b}" for b in banner[1:]]
        return lines
    if overlay in OVERLAYS:
        lines += OVERLAYS[overlay].split(",")
    elif fps > 0:
        lines.append("no_display")
    else:
        return None
    return lines


def finalize_hud(path: str) -> None:
    """Swap the banner config for the game's real overlay config, in place.

    MangoHud watches its config with inotify, so rewriting the same inode
    (not rename) makes the banner disappear without touching the game.
    """
    p = Path(path)
    final = p.with_suffix(".final")
    try:
        data = final.read_text()
        with open(p, "r+") as fh:
            fh.seek(0)
            fh.write(data)
            fh.truncate()
    except OSError:
        pass


def hud_path(tag: str) -> Path:
    return CACHE_DIR / f"hud-{re.sub(r'[^A-Za-z0-9_.-]', '_', tag)}.conf"


def show_hud(tag: str, gfx: dict, lines: list[str]) -> bool:
    """Show a message inside a running game (launched via ember-run) by rewriting
    its MangoHud config in place. Returns False if the game has no Ember HUD."""
    p = hud_path(tag)
    if not p.exists():
        return False
    try:
        with open(p, "r+") as fh:
            fh.seek(0)
            fh.write("\n".join(mangohud_lines(gfx, lines)) + "\n")
            fh.truncate()
        return True
    except OSError:
        return False


def banner_lines(game: str | None, gfx: dict, profile: str | None) -> list[str]:
    feats = []
    if profile:
        feats.append(f"{profile} profile")
    for key, label in (("fsr4", "FSR 4"), ("optiscaler", "FSR 3.1"), ("opti_fg", "FSR 3 FG"), ("mlfg", "Redstone FG"),
                       ("antilag", "Anti-Lag"), ("gamescope", "Super Resolution")):
        if gfx.get(key):
            feats.append(label)
    if int(gfx.get("sharpen") or 0):
        feats.append("Sharpening")
    if int(gfx.get("fps_cap") or 0):
        feats.append(f"{int(gfx['fps_cap'])} FPS target")
    title = "EMBER ACTIVE" + (f"  ·  {game}" if game else "")
    return [title[:60], ("  ·  ".join(feats) or "Radeon tuning ready")[:90]]


def build_launch(gfx: dict, argv: list[str], tag: str = "default", have=shutil.which,
                 arch: str | None = None, banner: list[str] | None = None,
                 write_files: bool = True) -> tuple[dict, list[str]]:
    """Return (env additions, argv) implementing the graphics options."""
    env: dict[str, str] = {}
    cmd = list(argv)
    if gfx.get("antilag"):
        env["ENABLE_LAYER_MESA_ANTI_LAG"] = "1"
    sharpen = int(gfx.get("sharpen") or 0)
    aa = gfx.get("aa", "off") if gfx.get("aa") in AA_MODES else "off"
    if sharpen > 0 or aa != "off":
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", tag)
        conf = CACHE_DIR / f"vkbasalt-{safe}.conf"
        effects = ([aa] if aa != "off" else []) + (["cas"] if sharpen > 0 else [])
        lines = [f"effects = {':'.join(effects)}", "toggleKey = Home"]
        if sharpen > 0:
            lines.append(f"casSharpness = {min(sharpen, 100) / 100:.2f}")
        conf.write_text("\n".join(lines) + "\n")
        env["ENABLE_VKBASALT"] = "1"
        env["VKBASALT_CONFIG_FILE"] = str(conf)
    aniso = int(gfx.get("aniso") or 0)
    if aniso in (2, 4, 8, 16):
        env["RADV_TEX_ANISO"] = str(aniso)
    if gfx.get("fsr4"):
        env["PROTON_FSR4_UPGRADE"] = "1"
    if gfx.get("fsr4_indicator"):
        env["PROTON_FSR4_INDICATOR"] = "1"
        env["FSR4_WATERMARK"] = "1"
    if gfx.get("optiscaler") or gfx.get("opti_fg"):
        env["PROTON_USE_OPTISCALER"] = "1"
        opts = ["Upscalers.Dx11Upscaler=fsr31", "Upscalers.Dx12Upscaler=ffx", "Upscalers.VulkanUpscaler=ffx"]
        if gfx.get("opti_fg"):
            opts += ["FrameGen.Enabled=true", "FrameGen.FGInput=upscaler", "FrameGen.FGOutput=fsrfg"]
        env["PROTON_OPTISCALER_CONFIG"] = ";".join(opts)
    if gfx.get("mlfg"):
        env["MLFG_UPGRADE"] = "1"
        if arch == "rdna3":
            env["DXIL_SPIRV_CONFIG"] = "wmma_rdna3_workaround"
    lines = mangohud_lines(gfx)
    if lines is not None or (banner and gfx.get("banner", True)):
        final = lines if lines is not None else ["no_display"]
        active = mangohud_lines(gfx, banner) if banner and gfx.get("banner", True) else final
        if write_files:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", tag)
            hud = CACHE_DIR / f"hud-{safe}.conf"
            hud.write_text("\n".join(active) + "\n")
            hud.with_suffix(".final").write_text("\n".join(final) + "\n")
            env["MANGOHUD_CONFIGFILE"] = str(hud)
        env["MANGOHUD"] = "1"
        if have("mangohud") and cmd and os.path.basename(cmd[0]) != "mangohud":
            cmd = ["mangohud"] + cmd   # also covers OpenGL titles via LD_PRELOAD
    pm = gfx.get("present_mode", "default")
    if pm in PRESENT_MODES and pm != "default":
        env["MESA_VK_WSI_PRESENT_MODE"] = pm
    if gfx.get("fsr"):
        env["WINE_FULLSCREEN_FSR"] = "1"
        env["WINE_FULLSCREEN_FSR_STRENGTH"] = str(max(0, min(5, int(gfx.get("fsr_strength", 2)))))
    if gfx.get("gamescope") and have("gamescope"):
        cmd = gamescope_args(gfx) + cmd
    if gfx.get("hdr") and not (gfx.get("gamescope") and have("gamescope")):
        env["PROTON_ENABLE_WAYLAND"] = "1"
        env["PROTON_ENABLE_HDR"] = "1"
        env["DXVK_HDR"] = "1"
        env["ENABLE_HDR_WSI"] = "1"
    return env, cmd


def env_preview(gfx: dict, arch: str | None = None) -> str:
    env, cmd = build_launch(gfx, ["%command%"], tag="preview", have=lambda n: n in ("gamescope", "mangohud"),
                            arch=arch, write_files=False)
    if "VKBASALT_CONFIG_FILE" in env:
        env["VKBASALT_CONFIG_FILE"] = "…"
    return " ".join([f"{k}={v}" for k, v in env.items()] + cmd)
