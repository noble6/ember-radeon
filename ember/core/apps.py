"""Installed desktop apps (.desktop entries), for adding non-Steam games.

Covers native packages, Flatpaks (system and user), and the shortcuts that
Lutris, Heroic, Bottles and Steam create. For each app Ember works out the
process name to watch for, so game detection and profile switching work
without typing anything.
"""
from __future__ import annotations

import configparser
import os
import re
import shlex
from pathlib import Path

HOME = Path.home()
_DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local/share")


def data_dirs() -> list[Path]:
    dirs = [_DATA_HOME, _DATA_HOME / "flatpak/exports/share", Path("/var/lib/flatpak/exports/share")]
    for d in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":"):
        if d:
            dirs.append(Path(d))
    out, seen = [], set()
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


# Launchers and game tools: listed, but never mistaken for a game themselves.
LAUNCHERS = {"steam", "com.valvesoftware.steam", "net.lutris.lutris", "lutris", "com.heroicgameslauncher.hgl",
             "heroic", "com.usebottles.bottles", "bottles", "net.davidotek.pupgui2", "protonup-qt",
             "io.github.ilya_zlobintsev.lactrl", "lact", "org.prismlauncher.prismlauncher", "itch",
             "io.itch.itch", "com.github.mtkennerly.ludusavi", "net.davidotek.pupgui2"}
_WRAPPERS = {"env", "nice", "ionice", "gamemoderun", "mangohud", "prime-run", "taskset", "gamescope",
             "obs-gamecapture", "pw-jack", "firejail", "systemd-run", "sh", "bash"}
# Commands that start something else: the real game process can't be known from Exec=.
_INDIRECT = {"bottles-cli", "bottles", "xdg-open", "gio", "lutris", "heroic", "heroic-run", "wine", "wine64",
             "proton", "umu-run", "steam", "legendary", "itch", "minigalaxy", "kioclient", "kde-open"}
_ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_STEAM_RE = re.compile(r"steam://(?:rungameid|run)/(\d+)")


def _flatpak_command(app_id: str) -> str | None:
    """The `command=` a Flatpak runs, from its metadata."""
    for base in (_DATA_HOME / "flatpak", Path("/var/lib/flatpak")):
        meta = base / "app" / app_id / "current/active/metadata"
        try:
            for line in meta.read_text(errors="replace").splitlines():
                if line.startswith("command="):
                    return line.split("=", 1)[1].strip() or None
        except OSError:
            continue
    return None


def _split(exec_line: str) -> list[str]:
    try:
        return shlex.split(exec_line)
    except ValueError:
        return exec_line.split()


def parse_exec(exec_line: str, x_flatpak: str = "") -> dict:
    """What launching this entry runs: {'process': name, 'steam': appid, 'ember_id': id}.
    'process' is the basename Ember matches against /proc/*/cmdline (lowercased)."""
    out = {"process": "", "steam": "", "ember_id": ""}
    m = _STEAM_RE.search(exec_line or "")
    if m:
        out["steam"] = m.group(1)
        return out
    args = [a for a in _split(exec_line or "") if not (a.startswith("%") and len(a) == 2) and a not in ("@@", "@@u")]
    # ember-run --id ID -- cmd...
    for i, a in enumerate(args):
        if os.path.basename(a) == "ember-run" and i + 2 < len(args) and args[i + 1] == "--id":
            out["ember_id"] = args[i + 2]
            if args[i + 2].startswith("exe:"):
                out["process"] = args[i + 2][4:]
            return out
    while args and (os.path.basename(args[0]) in _WRAPPERS or _ENV_RE.match(args[0])):
        head = os.path.basename(args.pop(0))
        if head in ("sh", "bash"):        # sh -c "real command"
            if args[:1] == ["-c"] and len(args) > 1:
                return parse_exec(args[1], x_flatpak)
            break
        if head == "gamescope" and "--" in args:
            args = args[args.index("--") + 1:]
        while args and args[0].startswith("-") and head != "env":
            args.pop(0)
    if not args:
        return out
    head = os.path.basename(args[0])
    if head == "flatpak" and "run" in args:
        rest = args[args.index("run") + 1:]
        cmd = next((a.split("=", 1)[1] for a in rest if a.startswith("--command=")), None)
        app = next((a for a in rest if not a.startswith("-")), x_flatpak)
        cmd = cmd or (_flatpak_command(app) if app else None)
        out["process"] = os.path.basename(cmd) if cmd else ""
        out["flatpak"] = app or ""
        return out
    if x_flatpak and not out["process"]:
        out["flatpak"] = x_flatpak
    out["process"] = head
    return out


def _icon_dirs() -> list[Path]:
    dirs = []
    for d in data_dirs():
        dirs.append(d / "icons")
    dirs += [HOME / ".icons", Path("/usr/share/pixmaps")]
    return dirs


_SIZES = ["512x512", "256x256", "scalable", "192x192", "128x128", "96x96", "64x64", "48x48"]


def icon_path(icon: str) -> str:
    """Resolve an Icon= value to a file Qt can load (largest hicolor size wins)."""
    if not icon:
        return ""
    if icon.startswith("/"):
        return icon if os.path.isfile(icon) else ""
    for base in _icon_dirs():
        if base.name == "pixmaps":
            for ext in (".png", ".svg", ".xpm"):
                if (base / (icon + ext)).is_file():
                    return str(base / (icon + ext))
            continue
        for theme in ("hicolor", "breeze", "Adwaita"):
            for size in _SIZES:
                for ext in (".png", ".svg"):
                    p = base / theme / size / "apps" / (icon + ext)
                    if p.is_file():
                        return str(p)
    return ""


def _read_entry(path: Path) -> dict | None:
    cp = configparser.RawConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    try:
        cp.read_string(path.read_text(errors="replace"))
    except (OSError, configparser.Error, UnicodeDecodeError):
        return None
    if not cp.has_section("Desktop Entry"):
        return None
    e = dict(cp.items("Desktop Entry"))
    if e.get("Type", "Application") != "Application":
        return None
    if e.get("NoDisplay", "").lower() == "true" or e.get("Hidden", "").lower() == "true":
        return None
    if not e.get("Name") or not e.get("Exec"):
        return None
    return e


def desktop_apps() -> list[dict]:
    """Every visible app, games first. Earlier XDG dirs win (user entries override system ones)."""
    seen: dict[str, dict] = {}
    for d in data_dirs():
        apps = d / "applications"
        if not apps.is_dir():
            continue
        for path in sorted(apps.rglob("*.desktop")):
            desk_id = str(path.relative_to(apps)).replace("/", "-")
            if desk_id in seen:
                continue
            e = _read_entry(path)
            if not e:
                seen[desk_id] = {}
                continue
            run = parse_exec(e["Exec"], e.get("X-Flatpak", ""))
            cats = [c for c in e.get("Categories", "").split(";") if c]
            stem = desk_id[:-8]
            launcher = stem.lower() in LAUNCHERS or run["process"].lower() in LAUNCHERS
            process = "" if (run["process"].lower() in _INDIRECT and not launcher) else run["process"]
            seen[desk_id] = {
                "desktop": desk_id,
                "name": e["Name"],
                "comment": e.get("Comment", ""),
                "icon": icon_path(e.get("Icon", "")),
                "exec": e["Exec"],
                "process": process,
                "steam": run["steam"],
                "ember_id": run["ember_id"],
                "flatpak": run.get("flatpak", ""),
                "game": "Game" in cats and not launcher,
                "launcher": launcher,
            }
    out = [a for a in seen.values() if a]
    out.sort(key=lambda a: (not a["game"], a["name"].lower()))
    return out


def launch_argv(exec_line: str) -> list[str]:
    """The entry's Exec= as argv, without field codes, ready to put after `ember-run --id ... --`."""
    return [a for a in _split(exec_line) if not (a.startswith("%") and len(a) == 2) and a not in ("@@", "@@u")]


_RESERVED = set(' \t\n"\'\\><~|&;$*?#()`')


def desktop_exec(argv: list[str]) -> str:
    """Quote argv for an Exec= line (Desktop Entry spec: double quotes, then string escaping)."""
    parts = []
    for a in argv:
        a = a.replace("%", "%%")
        if a and not (set(a) & _RESERVED):
            parts.append(a)
            continue
        q = "".join("\\" + c if c in '"`$\\' else c for c in a)
        parts.append('"' + q + '"')
    return " ".join(parts).replace("\\", "\\\\")


def _desktop_value(s: str) -> str:
    return s.replace("\\", "\\\\").replace("\n", " ").replace("\r", " ")


LAUNCHER_DIR = _DATA_HOME / "applications"


def launcher_path(exe: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", exe)[:80] or "game"
    return LAUNCHER_DIR / f"ember-game-{safe}.desktop"


def write_launcher(name: str, exe: str, argv: list[str], icon: str, ember_run: str) -> Path:
    """A menu entry that starts the game through ember-run (graphics features + banner)."""
    path = launcher_path(exe)
    LAUNCHER_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["[Desktop Entry]", "Type=Application", f"Name={_desktop_value(name)} (Ember)",
             f"Comment={_desktop_value('Start ' + name + ' with Ember graphics settings')}",
             "Exec=" + desktop_exec([ember_run, "--id", f"exe:{exe}", "--"] + list(argv)),
             "Categories=Game;", "X-Ember-Launcher=true"]
    if icon:
        lines.insert(4, f"Icon={_desktop_value(icon)}")
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n")
    os.chmod(tmp, 0o755)
    os.replace(tmp, path)
    return path
