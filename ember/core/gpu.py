"""amdgpu sysfs access: discovery, telemetry, and (for the daemon) tuning writes.

Pure stdlib so the root daemon can import it without Qt. Every path goes through
`SYSFS_ROOT` so the whole stack can be exercised against a fake tree in tests.
"""
from __future__ import annotations

import os
import re
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path

SYSFS_ROOT = Path(os.environ.get("EMBER_SYSFS_ROOT", "/"))
AMD_VENDOR = "0x1002"
PP_OVERDRIVE_MASK = 0x4000  # PP_OVERDRIVE_MASK in amd_shared.h


def _p(path: str) -> Path:
    return SYSFS_ROOT / path.lstrip("/")


def read(path: Path, default: str | None = None) -> str | None:
    try:
        return path.read_text().strip()
    except (OSError, UnicodeDecodeError):
        return default


def read_int(path: Path, default: int | None = None) -> int | None:
    s = read(path)
    if s is None:
        return default
    try:
        return int(s, 0)
    except ValueError:
        return default


# ---------------------------------------------------------------- parsing helpers

_DPM_RE = re.compile(r"^\s*(\d+):\s*([0-9.]+)\s*(\w+)?(.*?)(\*)?\s*$")


def parse_dpm(text: str | None) -> list[dict]:
    """pp_dpm_sclk & friends -> [{index, mhz, label, active}]"""
    out = []
    for line in (text or "").splitlines():
        m = _DPM_RE.match(line)
        if not m:
            continue
        idx, val, unit, rest, star = m.groups()
        label = (val + (unit or "") + rest).strip()
        mhz = None
        mm = re.search(r"(\d+)\s*Mhz", line, re.I)
        if mm:
            mhz = int(mm.group(1))
        out.append({"index": int(idx), "mhz": mhz, "label": label, "active": bool(star)})
    return out


def parse_power_profiles(text: str | None) -> tuple[list[dict], int | None]:
    """pp_power_profile_mode -> ([{index, name}], active_index). Handles the
    tabular (SMU11/13) layout and the simple one-line-per-profile layout."""
    profiles: list[dict] = []
    active = None
    for line in (text or "").splitlines():
        m = re.match(r"^\s*(\d+)\s+([A-Z0-9_]+)\s*(\*)?\s*:?", line)
        if not m:
            continue
        idx, name, star = int(m.group(1)), m.group(2), m.group(3)
        if any(p["index"] == idx for p in profiles):
            continue
        profiles.append({"index": idx, "name": name})
        if star:
            active = idx
    return profiles, active


def parse_od(text: str | None) -> dict:
    """pp_od_clk_voltage -> {family, sections: {name: [[idx, value, mV|None]...]}, ranges: {name: [lo, hi]}}

    Every amdgpu generation formats this file differently:

    states  (Polaris/Vega10, SMU7/9)   OD_SCLK: "7: 1366MHz 1150mV"  write "s 7 1400 1100"
    curve   (Vega20/Navi1x, SMU11)     OD_SCLK 0/1 + OD_VDDC_CURVE   write "s 1 2100", "vc 2 2100 1150"
    minmax  (RDNA2/RDNA3, SMU11/13)    OD_SCLK 0/1 + OD_VDDGFX_OFFSET write "s 1 2700", "vo -50"
    offset  (RDNA4, SMU14)             OD_SCLK_OFFSET "0Mhz"          write "s 200", "vo -50"
    apu                                OD_SCLK 0/1 only               write "s 1 2200"
    """
    sections: dict[str, list] = {}
    ranges: dict[str, list] = {}
    cur = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.endswith(":") and line.startswith("OD_"):
            cur = line[:-1]
            sections.setdefault(cur, [])
            continue
        if cur == "OD_RANGE":
            m = re.match(r"^([\w\[\]]+):\s*(-?\d+)\s*[A-Za-z]*\s+(-?\d+)", line)
            if m:
                ranges[m.group(1)] = [int(m.group(2)), int(m.group(3))]
            continue
        if cur is None:
            continue
        m = re.match(r"^(\d+):\s*(-?\d+)\s*[A-Za-z]*(?:\s+(-?\d+)\s*m[Vv])?", line)
        if m:
            mv = int(m.group(3)) if m.group(3) else None
            sections[cur].append([int(m.group(1)), int(m.group(2)), mv])
            continue
        m = re.match(r"^(-?\d+)\s*[A-Za-z]*$", line)
        if m:
            sections[cur].append([0, int(m.group(1)), None])
    return {"family": od_family(sections), "sections": sections, "ranges": ranges}


def od_family(sections: dict) -> str:
    if "OD_SCLK_OFFSET" in sections:
        return "offset"
    sclk = sections.get("OD_SCLK") or []
    if any(e[2] is not None for e in sclk) or len(sclk) > 2:
        return "states"
    if "OD_VDDC_CURVE" in sections:
        return "curve"
    if "OD_MCLK" not in sections and "OD_VDDGFX_OFFSET" not in sections:
        return "apu"
    return "minmax"


def _entry(sections, name, idx=None):
    rows = sections.get(name) or []
    if not rows:
        return None
    if idx is None:
        return rows[-1]
    for r in rows:
        if r[0] == idx:
            return r
    return None


def od_controls(od: dict | None, stock: dict | None = None) -> list[dict]:
    """The clock/voltage sliders this GPU supports, with limits and stock values.

    `stock` is the table as read before Ember changed anything; voltage controls
    are capped at the stock value (undervolt only).
    """
    if not od:
        return []
    S, R, fam = od["sections"], od["ranges"], od["family"]
    St = (stock or od)["sections"]
    out = []

    def add(key, label, rng, stock_val, unit, hint="", step=5):
        if rng is None or stock_val is None:
            return
        lo, hi = rng
        out.append({"key": key, "label": label, "from": lo, "to": hi, "stock": stock_val,
                    "unit": unit, "hint": hint, "step": step})

    if fam == "offset":
        add("sclk_offset", "GPU clock offset", R.get("SCLK_OFFSET"), (_entry(St, "OD_SCLK_OFFSET") or [0, 0])[1], "MHz",
            "Shifts the whole boost curve. RDNA4 boosts on its own; offsets mostly matter together with an undervolt.")
    elif fam == "states":
        top = _entry(St, "OD_SCLK")
        add("sclk_max", "Max GPU clock", R.get("SCLK"), top and top[1], "MHz", "Clock of the highest power state.")
        if top and top[2] is not None and R.get("VDDC"):
            add("voltage_max_mv", "Max GPU voltage", [R["VDDC"][0], min(R["VDDC"][1], top[2])], top[2], "mV",
                "Voltage of the highest power state. Lowering it is the classic Polaris/Vega undervolt.")
    else:
        add("sclk_max", "Max GPU clock", R.get("SCLK"), (_entry(St, "OD_SCLK", 1) or [0, None])[1], "MHz")
        if fam != "apu":
            add("sclk_min", "Min GPU clock", R.get("SCLK"), (_entry(St, "OD_SCLK", 0) or [0, None])[1], "MHz",
                "Raising it keeps clocks up between frames; usually leave it alone.")
    mtop = _entry(St, "OD_MCLK", None if fam == "states" else 1)
    if mtop:
        add("mclk_max", "Max memory clock", R.get("MCLK"), mtop[1], "MHz",
            "Reported as the memory controller clock; GDDR6 effective speed is 8x this.")
    if fam == "curve":
        p2 = _entry(St, "OD_VDDC_CURVE", 2)
        vr = R.get("VDDC_CURVE_VOLT[2]")
        if p2 and p2[2] is not None and vr:
            add("voltage_max_mv", "Voltage at max clock", [vr[0], min(vr[1], p2[2])], p2[2], "mV",
                "Top point of the voltage/frequency curve. Lower it to undervolt.")
    if "OD_VDDGFX_OFFSET" in S:
        vr = R.get("VDDGFX_OFFSET") or [-200, 0]
        add("vddgfx_offset", "Voltage offset", [max(vr[0], -300), 0], 0, "mV",
            "Undervolt only. Too far = crashes under load; the boot guard reverts to stock if a boot doesn't survive.")
    return out


def od_commands(od: dict, settings: dict, stock: dict | None = None) -> list[str]:
    """Translate validated OD settings into pp_od_clk_voltage writes (without r/c)."""
    S, fam = od["sections"], od["family"]
    St = (stock or od)["sections"]
    cmds = []
    g = settings.get
    if fam == "offset":
        if g("sclk_offset") is not None:
            cmds.append(f"s {g('sclk_offset')}")
    elif fam == "states":
        top = _entry(St, "OD_SCLK")
        if top and (g("sclk_max") is not None or g("voltage_max_mv") is not None):
            mhz = g("sclk_max") if g("sclk_max") is not None else top[1]
            mv = g("voltage_max_mv") if g("voltage_max_mv") is not None else top[2]
            cmds.append(f"s {top[0]} {mhz} {mv}")
        mtop = _entry(St, "OD_MCLK")
        if mtop and g("mclk_max") is not None:
            cmds.append(f"m {mtop[0]} {g('mclk_max')} {mtop[2]}")
        return cmds
    else:
        if g("sclk_min") is not None:
            cmds.append(f"s 0 {g('sclk_min')}")
        if g("sclk_max") is not None:
            cmds.append(f"s 1 {g('sclk_max')}")
    if g("mclk_max") is not None:
        cmds.append(f"m 1 {g('mclk_max')}")
    if fam == "curve" and (g("voltage_max_mv") is not None or g("sclk_max") is not None):
        p2 = _entry(St, "OD_VDDC_CURVE", 2)
        if p2:
            mhz = g("sclk_max") if g("sclk_max") is not None else p2[1]
            mv = g("voltage_max_mv") if g("voltage_max_mv") is not None else p2[2]
            cmds.append(f"vc 2 {mhz} {mv}")
    if g("vddgfx_offset") is not None and "OD_VDDGFX_OFFSET" in S:
        cmds.append(f"vo {g('vddgfx_offset')}")
    return cmds


# RDNA3+ firmware fan options (gpu_od/fan_ctrl/*). key -> (file, label)
FAN_CTRL = {
    "zero_rpm": ("fan_zero_rpm_enable", "Zero RPM"),
    "zero_rpm_stop_temp": ("fan_zero_rpm_stop_temperature", "Zero RPM stop temperature"),
    "target_temp": ("fan_target_temperature", "Target temperature"),
    "acoustic_limit": ("acoustic_limit_rpm_threshold", "Max fan speed (RPM)"),
    "acoustic_target": ("acoustic_target_rpm_threshold", "Target fan speed (RPM)"),
    "min_pwm": ("fan_minimum_pwm", "Minimum fan speed (%)"),
}


def parse_fan_ctrl(text: str | None) -> dict | None:
    """'FAN_TARGET_TEMPERATURE:\n95\nOD_RANGE:\nTARGET_TEMPERATURE: 25 110' -> {value, range}"""
    if not text:
        return None
    value, rng, in_range = None, None, False
    for line in text.splitlines():
        line = line.strip()
        if line == "OD_RANGE:":
            in_range = True
            continue
        nums = re.findall(r"-?\d+", line)
        if in_range and len(nums) >= 2:
            rng = [int(nums[-2]), int(nums[-1])]
        elif not in_range and value is None and re.fullmatch(r"-?\d+\s*\w*", line):
            value = int(nums[0])
    if value is None:
        return None
    return {"value": value, "range": rng}


def decode_gpu_metrics(blob: bytes | None) -> dict:
    """Decode the parts of gpu_metrics that hwmon doesn't expose.

    Only formats 1.x (discrete dGPUs) are decoded; 0xFFFF means "not reported".
    Offsets follow kgd_pp_interface.h (gpu_metrics_v1_0 .. v1_3 share a prefix).
    """
    if not blob or len(blob) < 4:
        return {}
    size, fmt, content = struct.unpack_from("<HBB", blob, 0)
    if fmt != 1 or len(blob) < 78:
        return {"format": f"{fmt}.{content}"}

    def u16(off):
        v = struct.unpack_from("<H", blob, off)[0]
        return None if v == 0xFFFF else v

    out = {"format": f"{fmt}.{content}"}
    names = ["temp_edge", "temp_hotspot", "temp_mem", "temp_vrgfx", "temp_vrsoc", "temp_vrmem"]
    for i, n in enumerate(names):
        out[n] = u16(4 + 2 * i)
    out["gfx_activity"] = u16(16)
    out["umc_activity"] = u16(18)
    out["mm_activity"] = u16(20)
    out["socket_power"] = u16(22)
    out["avg_gfxclk"] = u16(40)
    out["avg_socclk"] = u16(42)
    out["avg_uclk"] = u16(44)
    out["cur_gfxclk"] = u16(54)
    out["cur_uclk"] = u16(58)
    out["throttle_status"] = struct.unpack_from("<I", blob, 68)[0]
    out["fan_rpm"] = u16(72)
    out["pcie_width"] = u16(74)
    out["pcie_speed"] = u16(76)
    if content >= 3 and len(blob) >= 110:
        out["voltage_soc"] = u16(104)
        out["voltage_gfx"] = u16(106)
        out["voltage_mem"] = u16(108)
    # Temperatures on SMU11 are whole degrees; SMU13 reports centi-degrees.
    for n in names:
        v = out.get(n)
        if v is not None and v > 300:
            out[n] = v / 100.0
    return out


# Navi1x/2x throttler bits (smu11_driver_if_sienna_cichlid.h THROTTLER_*_BIT).
THROTTLE_BITS = {
    0: "Edge temp", 1: "Hotspot temp", 2: "Hotspot temp (G)", 3: "Hotspot temp (M)",
    4: "Memory temp", 5: "VR GFX temp", 6: "VR Mem temp", 7: "VR Mem temp",
    8: "VR SOC temp", 9: "Liquid temp", 10: "Liquid temp", 11: "Plx temp",
    12: "Thermal (TEDC)", 13: "Current (TDC GFX)", 14: "Current (TDC SOC)",
    15: "Power (PPT0)", 16: "Power (PPT1)", 17: "Power (PPT2)", 18: "Power (PPT3)",
    19: "Fit", 20: "PPM", 21: "APCC",
}


def throttle_reasons(status: int | None) -> list[str]:
    if not status:
        return []
    seen = []
    for bit, name in THROTTLE_BITS.items():
        if status & (1 << bit) and name not in seen:
            seen.append(name)
    return seen


# ---------------------------------------------------------------- name lookup

def marketing_name(device_id: str, revision: str) -> str | None:
    """libdrm's amdgpu.ids maps (device, revision) to the retail name."""
    did = device_id.lower().replace("0x", "")
    rev = revision.lower().replace("0x", "")
    for ids in ("/usr/share/libdrm/amdgpu.ids", "/usr/local/share/libdrm/amdgpu.ids"):
        try:
            with open(ids) as fh:
                for line in fh:
                    parts = [p.strip() for p in line.split(",", 2)]
                    if len(parts) == 3 and parts[0].lower() == did and parts[1].lower() == rev:
                        return parts[2]
        except OSError:
            continue
    return None


def pci_names(vendor: str, device: str, sub_vendor: str, sub_device: str) -> tuple[str | None, str | None]:
    """(chip name, board partner name) from pci.ids."""
    v, d = vendor[2:].lower(), device[2:].lower()
    sv, sd = sub_vendor[2:].lower(), sub_device[2:].lower()
    chip = board = vendor_name = None
    for ids in ("/usr/share/hwdata/pci.ids", "/usr/share/misc/pci.ids"):
        try:
            fh = open(ids, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            in_v = in_d = False
            for line in fh:
                if not line.strip() or line.startswith("#"):
                    continue
                if not line.startswith("\t"):
                    in_v = line[:4].lower() == v
                    in_d = False
                    if line[:4].lower() == sv:
                        vendor_name = line[4:].strip()
                    continue
                if not in_v:
                    continue
                if line.startswith("\t\t"):
                    if in_d and line[2:11].lower() == f"{sv} {sd}":
                        board = line[11:].strip()
                elif line[1:5].lower() == d:
                    in_d = True
                    chip = line[5:].strip()
                else:
                    in_d = False
        # second pass for subsystem vendor name (may appear before the AMD block)
        if vendor_name is None:
            try:
                with open(ids, encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if line[:4].lower() == sv and not line.startswith("\t"):
                            vendor_name = line[4:].strip()
                            break
            except OSError:
                pass
        break
    if board and vendor_name and not board.lower().startswith(vendor_name.split()[0].lower()):
        board = f"{vendor_name.split()[0]} {board}"
    elif not board and vendor_name:
        board = vendor_name
    return chip, board


# ---------------------------------------------------------------- architecture

_ARCH_BY_NAME = [
    (r"Navi 4\d|RX 9\d{3}", "RDNA 4"), (r"Navi 3\d|RX 7\d{3}|7[0-9]0M", "RDNA 3"),
    (r"Navi 2\d|RX 6\d{3}|Rembrandt|Van Gogh|Mendocino|680M|660M", "RDNA 2"), (r"Navi 1\d|RX 5\d{3}", "RDNA 1"),
    (r"Vega|Radeon VII|Renoir|Cezanne|Lucienne|Picasso|Raven|Barcelo", "GCN 5 (Vega)"),
    (r"Polaris|Ellesmere|Baffin|Lexa|RX [45][5-9]0|RX 5[45]0", "GCN 4 (Polaris)"),
    (r"Fiji|Tonga|Antigua|R9 (Fury|Nano|3[89]0|285)", "GCN 3"), (r"Hawaii|Bonaire|Kaveri|Kabini", "GCN 2"),
    (r"Tahiti|Pitcairn|Cape Verde|Oland|Hainan", "GCN 1"),
]


def architecture(dev: Path, names: list[str | None]) -> str:
    """Graphics IP version from IP discovery (Navi and newer), else a name match."""
    gc = dev / "ip_discovery" / "die" / "0" / "GC" / "0"
    major, minor = read_int(gc / "major"), read_int(gc / "minor")
    if major is not None:
        if major >= 12:
            return "RDNA 4"
        if major == 11:
            return "RDNA 3.5" if (minor or 0) >= 5 else "RDNA 3"
        if major == 10:
            return "RDNA 2" if (minor or 0) >= 3 else "RDNA 1"
        if major == 9:
            return "GCN 5 (Vega)"
    hay = " ".join(n for n in names if n)
    for pat, arch in _ARCH_BY_NAME:
        if re.search(pat, hay):
            return arch
    return "GCN"


def arch_key(arch: str) -> str:
    """'RDNA 3.5' -> 'rdna3', 'GCN 4 (Polaris)' -> 'gcn4'"""
    m = re.match(r"(RDNA|GCN) (\d)", arch)
    return f"{m.group(1).lower()}{m.group(2)}" if m else "gcn"


def legacy_radeon_cards() -> list[dict]:
    """AMD GPUs bound to the old `radeon` driver (GCN 1/2 can usually move to amdgpu)."""
    out = []
    try:
        cards = sorted(p for p in _p("/sys/class/drm").iterdir() if re.fullmatch(r"card\d+", p.name))
    except OSError:
        return out
    for card in cards:
        dev = card / "device"
        if read(dev / "vendor") != AMD_VENDOR or not (dev / "driver").exists():
            continue
        drv = os.path.basename(os.path.realpath(dev / "driver"))
        if drv == "radeon":
            chip, _ = pci_names(AMD_VENDOR, read(dev / "device", "0x0"), read(dev / "subsystem_vendor", "0x0"),
                                read(dev / "subsystem_device", "0x0"))
            out.append({"card": card.name, "chip": chip or read(dev / "device")})
    return out


_INTERPRETERS = {"python", "python3", "java", "node", "electron", "wine", "wine64", "wine-preloader",
                 "wine64-preloader", "bash", "sh"}


def _proc_name(p: Path) -> str | None:
    """A human name: the script/app behind interpreters, the full .exe name for Wine games."""
    try:
        argv = [a for a in (p / "cmdline").read_bytes().split(b"\0") if a]
        comm = (p / "comm").read_text().strip()
    except OSError:
        return None
    args = [a.decode(errors="replace").replace("\\", "/") for a in argv]
    if not args:
        return comm
    base = os.path.basename(args[0])
    if re.sub(r"[\d.]+$", "", base) in _INTERPRETERS or comm in _INTERPRETERS:
        for a in args[1:]:
            if a.startswith("-"):
                continue
            b = os.path.basename(a)
            if b in ("main.py", "__main__.py", "app.py"):
                return os.path.basename(os.path.dirname(a)) or b
            return b
    if base.lower().endswith(".exe"):
        return base
    return comm if len(comm) < 15 else base


def gpu_processes(pci_slot: str, proc: Path | None = None) -> list[dict]:
    """Per-app VRAM and GPU time from DRM fdinfo (the data `amdgpu_top` and Task Manager show).

    Only processes we may read are listed: as a normal user that is your own apps.
    """
    proc = proc or _p("/proc")
    seen: dict[int, dict] = {}
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError:
        return []
    for pid in pids:
        fdinfo = proc / pid / "fdinfo"
        try:
            fds = os.listdir(fdinfo)
        except OSError:
            continue
        clients: dict[str, dict] = {}
        fd_dir = proc / pid / "fd"
        for fd in fds:
            # Only DRM device fds can carry GPU stats; checking the link first skips
            # opening the fdinfo of every socket, pipe and file a process holds.
            try:
                if not os.readlink(fd_dir / fd).startswith("/dev/dri/"):
                    continue
            except OSError:
                pass
            try:
                with open(fdinfo / fd) as fh:
                    text = fh.read(4096)
            except OSError:
                continue
            if "drm-driver:\tamdgpu" not in text or f"drm-pdev:\t{pci_slot}" not in text:
                continue
            kv = dict(line.split(":", 1) for line in text.splitlines() if ":" in line)
            cid = kv.get("drm-client-id", fd).strip()
            if cid in clients:
                continue   # several fds can share one DRM client
            def kib(k):
                v = kv.get(k, "0").strip().split()
                return int(v[0]) if v and v[0].isdigit() else 0
            def ns(k):
                v = kv.get(k, "0").strip().split()
                return int(v[0]) if v and v[0].isdigit() else 0
            clients[cid] = {"vram": kib("drm-memory-vram") or kib("drm-total-vram"),
                            "gtt": kib("drm-memory-gtt") or kib("drm-total-gtt"),
                            "gfx_ns": ns("drm-engine-gfx"), "compute_ns": ns("drm-engine-compute"),
                            "enc_ns": ns("drm-engine-enc") + ns("drm-engine-enc_1"),
                            "dec_ns": ns("drm-engine-dec")}
        if not clients:
            continue
        name = _proc_name(proc / pid) or pid
        agg = {"pid": int(pid), "name": name, "vram": 0, "gtt": 0, "gfx_ns": 0, "compute_ns": 0, "enc_ns": 0, "dec_ns": 0}
        for c in clients.values():
            for k in ("vram", "gtt", "gfx_ns", "compute_ns", "enc_ns", "dec_ns"):
                agg[k] += c[k]
        seen[int(pid)] = agg
    return sorted(seen.values(), key=lambda x: -x["vram"])


# ---------------------------------------------------------------- the GPU

DEFAULT_CRIT_C = {"edge": 100.0, "junction": 110.0, "mem": 105.0}   # used when hwmon has no temp*_crit

@dataclass
class Gpu:
    card: str               # "card1"
    dev: Path               # .../device
    hwmon: Path | None
    pci_slot: str
    info: dict = field(default_factory=dict)
    _crits: dict | None = field(default=None, repr=False, compare=False)

    # ---- static info
    def describe(self) -> dict:
        if self.info:
            return self.info
        d = self.dev
        vendor = read(d / "vendor", "0x0000")
        device = read(d / "device", "0x0000")
        rev = read(d / "revision", "0x00")
        sv = read(d / "subsystem_vendor", "0x0000")
        sd = read(d / "subsystem_device", "0x0000")
        chip, board = pci_names(vendor, device, sv, sd)
        name = marketing_name(device, rev) or chip or f"AMD GPU {device}"
        arch = architecture(d, [chip, name])
        vram = read_int(d / "mem_info_vram_total", 0) or 0
        vis = read_int(d / "mem_info_vis_vram_total", 0) or 0
        codename = None
        if chip:
            m = re.match(r"^([A-Za-z]+ \d+\w*)", chip)
            codename = m.group(1) if m else None
        self.info = {
            "card": self.card, "pci": self.pci_slot,
            "name": name, "chip": chip, "board": board, "codename": codename,
            "device_id": device, "revision": rev, "subsystem": f"{sv}:{sd}",
            "vbios": read(d / "vbios_version"),
            "vram_total": read_int(d / "mem_info_vram_total", 0),
            "vram_vendor": (read(d / "mem_info_vram_vendor") or "").capitalize() or None,
            "gtt_total": read_int(d / "mem_info_gtt_total", 0),
            "pcie_max": f"{read(d / 'max_link_speed', '?')} x{read(d / 'max_link_width', '?')}",
            "unique_id": read(d / "unique_id"),
            "arch": arch, "arch_key": arch_key(arch),
            "apu": name.endswith("Graphics") or (vram and vram <= 4 * 2**30 and not (self.hwmon and (self.hwmon / "fan1_input").exists())),
            # Resizable BAR ("Smart Access Memory"): the CPU can see all of VRAM.
            "rebar": bool(vram and vis and vis >= vram * 0.98),
            "vis_vram": vis,
        }
        return self.info

    # ---- capabilities
    @property
    def od_path(self) -> Path:
        return self.dev / "pp_od_clk_voltage"

    def fan_ctrl(self) -> dict:
        base = self.dev / "gpu_od" / "fan_ctrl"
        out = {}
        for key, (fname, _label) in FAN_CTRL.items():
            v = parse_fan_ctrl(read(base / fname))
            if v is not None:
                out[key] = v
        return out

    def capabilities(self) -> dict:
        h = self.hwmon
        caps = {
            "perf_level": (self.dev / "power_dpm_force_performance_level").exists(),
            "power_profile": (self.dev / "pp_power_profile_mode").exists(),
            "power_cap": bool(h and (h / "power1_cap").exists()),
            "fan_pwm": bool(h and (h / "pwm1_enable").exists()),
            "fan_curve_fw": (self.dev / "gpu_od" / "fan_ctrl" / "fan_curve").exists(),
            "overdrive": self.od_path.exists(),
            "overdrive_kernel": overdrive_enabled_in_kernel(),
            "gpu_metrics": (self.dev / "gpu_metrics").exists(),
        }
        return caps

    # ---- live data
    def hw(self, name: str, scale: float = 1.0):
        if not self.hwmon:
            return None
        v = read_int(self.hwmon / name)
        return None if v is None else v / scale

    def power_cap_range(self) -> dict:
        return {
            "cap": self.hw("power1_cap", 1e6), "min": self.hw("power1_cap_min", 1e6),
            "max": self.hw("power1_cap_max", 1e6), "default": self.hw("power1_cap_default", 1e6),
        }

    def asleep(self) -> bool:
        """True while a laptop's discrete GPU is powered down (runtime suspend).
        Reading its sensors would wake it up, so callers skip polling."""
        return read(self.dev / "power" / "runtime_status") == "suspended"

    def temps(self) -> dict:
        out = {}
        if not self.hwmon:
            return out
        for i in range(1, 6):
            label = read(self.hwmon / f"temp{i}_label")
            val = self.hw(f"temp{i}_input", 1000)
            if label and val is not None:
                out[label] = val
        return out

    def crit_temps(self) -> dict:
        """Critical temperature per sensor label (static, so read once)."""
        if self._crits is None:
            crits = {}
            if self.hwmon:
                for i in range(1, 6):
                    label = read(self.hwmon / f"temp{i}_label")
                    crit = self.hw(f"temp{i}_crit", 1000)
                    if label and crit and 60 <= crit <= 130:
                        crits[label] = crit
            self._crits = crits
        return self._crits

    def thermal_margin(self, temps: dict | None = None) -> float | None:
        """Degrees left before the closest sensor reaches its critical temperature."""
        temps = self.temps() if temps is None else temps
        crits = self.crit_temps()
        margins = [crits.get(label, DEFAULT_CRIT_C.get(label, 100.0)) - t for label, t in temps.items()]
        return min(margins) if margins else None

    def snapshot(self) -> dict:
        """One telemetry sample. Cheap enough to call at 2-4 Hz."""
        d = self.dev
        if self.asleep():
            return {"t": time.time(), "asleep": True, "sclk_levels": [], "mclk_levels": [], "throttle": [],
                    "fan_mode": "auto", "pcie": "asleep", "busy": 0, "power_w": 0.0, "fan_rpm": 0,
                    "vram_used": 0, "vram_total": (self.info or {}).get("vram_total") or 0}
        temps = self.temps()
        metrics = {}
        try:
            metrics = decode_gpu_metrics((d / "gpu_metrics").read_bytes())
        except OSError:
            pass
        sclk = parse_dpm(read(d / "pp_dpm_sclk"))
        mclk = parse_dpm(read(d / "pp_dpm_mclk"))
        power = self.hw("power1_average", 1e6)
        if power is None:
            power = self.hw("power1_input", 1e6)
        gfx_mhz = self.hw("freq1_input", 1e6)
        mem_mhz = self.hw("freq2_input", 1e6)
        # The firmware's running average is far steadier than an instantaneous read,
        # which flips between 0 (GFXOFF) and full boost hundreds of times a second.
        if metrics.get("avg_gfxclk") is not None:
            gfx_mhz = metrics["avg_gfxclk"]
        fan_rpm = self.hw("fan1_input")
        pwm = self.hw("pwm1")
        pwm_max = self.hw("pwm1_max") or 255
        throttle = metrics.get("throttle_status")
        return {
            "t": time.time(),
            "busy": read_int(d / "gpu_busy_percent"),
            "mem_busy": read_int(d / "mem_busy_percent", metrics.get("umc_activity")),
            "gfx_mhz": gfx_mhz,
            "mem_mhz": mem_mhz,
            "sclk_levels": sclk, "mclk_levels": mclk,
            "power_w": power,
            "power_cap_w": self.hw("power1_cap", 1e6),
            "temp_edge": temps.get("edge"),
            "temp_junction": temps.get("junction", metrics.get("temp_hotspot")),
            "temp_mem": temps.get("mem", metrics.get("temp_mem")),
            "temp_vrgfx": metrics.get("temp_vrgfx"),
            "fan_rpm": fan_rpm,
            "fan_max_rpm": self.hw("fan1_max"),
            "fan_pct": None if pwm is None else round(100 * pwm / pwm_max),
            "fan_mode": {0: "full", 1: "manual", 2: "auto"}.get(int(self.hw("pwm1_enable") or 2), "auto"),
            "vddgfx_mv": self.hw("in0_input"),
            "vram_used": read_int(d / "mem_info_vram_used", 0),
            "vram_total": read_int(d / "mem_info_vram_total", 0),
            "gtt_used": read_int(d / "mem_info_gtt_used", 0),
            "perf_level": read(d / "power_dpm_force_performance_level"),
            "pcie": f"{read(d / 'current_link_speed', '?')} x{read(d / 'current_link_width', '?')}",
            "throttle": throttle_reasons(throttle),
        }

    def tuning_state(self) -> dict:
        """Current tunables, in the same shape the daemon accepts."""
        d = self.dev
        profiles, active = parse_power_profiles(read(d / "pp_power_profile_mode"))
        od = parse_od(read(self.od_path)) if self.od_path.exists() else None
        return {
            "perf_level": read(d / "power_dpm_force_performance_level"),
            "power_profiles": profiles,
            "power_profile": active,
            "power_cap": self.power_cap_range(),
            "fan": {
                "enable": self.hw("pwm1_enable"),
                "pwm_min": self.hw("pwm1_min") or 0, "pwm_max": self.hw("pwm1_max") or 255,
                "rpm_max": self.hw("fan1_max"),
            },
            "od": od,
            "fan_ctrl": self.fan_ctrl(),
            "sclk_levels": parse_dpm(read(d / "pp_dpm_sclk")),
            "mclk_levels": parse_dpm(read(d / "pp_dpm_mclk")),
        }


def overdrive_enabled_in_kernel() -> bool:
    mask = read_int(_p("/sys/module/amdgpu/parameters/ppfeaturemask"))
    return bool(mask is not None and mask & PP_OVERDRIVE_MASK)


def ppfeaturemask() -> int | None:
    return read_int(_p("/sys/module/amdgpu/parameters/ppfeaturemask"))


def find_gpus() -> list[Gpu]:
    gpus = []
    drm = _p("/sys/class/drm")
    try:
        cards = sorted(p for p in drm.iterdir() if re.fullmatch(r"card\d+", p.name))
    except OSError:
        return gpus
    for card in cards:
        dev = card / "device"
        if read(dev / "vendor") != AMD_VENDOR:
            continue
        drv = dev / "driver"
        if drv.exists() and os.path.basename(os.path.realpath(drv)) != "amdgpu":
            continue
        hw = None
        try:
            for h in sorted((dev / "hwmon").iterdir()):
                if read(h / "name") == "amdgpu":
                    hw = h
                    break
        except OSError:
            pass
        slot = os.path.basename(os.path.realpath(dev))
        if not re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.\d", slot):
            slot = (read(dev / "uevent") or "").partition("PCI_SLOT_NAME=")[2].split("\n")[0] or card.name
        gpus.append(Gpu(card=card.name, dev=dev, hwmon=hw, pci_slot=slot))
    # Discrete first: the board with the most VRAM is almost always the one people tune.
    gpus.sort(key=lambda g: -(read_int(g.dev / "mem_info_vram_total", 0) or 0))
    return gpus
