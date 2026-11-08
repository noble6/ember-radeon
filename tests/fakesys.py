"""Build a fake amdgpu sysfs tree modelled on an RX 6600 (Navi 23, SMU 11)."""
from __future__ import annotations

import os
from pathlib import Path

PROFILE_MODE = """PROFILE_INDEX(NAME) CLOCK_TYPE(NAME) FPS MinFreqType MinActiveFreqType MinActiveFreq BoosterFreqType BoosterFreq PD_Data_limit_c PD_Data_error_coeff PD_Data_error_rate_coeff
 0 BOOTUP_DEFAULT*:
                    0(       GFXCLK)       0       5       1       0       4     800 4587520  -65536       0
 1 3D_FULL_SCREEN :
                    0(       GFXCLK)       0       5       1       0       4     650 4587520   -3276  -65536
 2   POWER_SAVING :
                    0(       GFXCLK)       0       5       1       0       3       0 5898240  -65536       0
 3          VIDEO :
 4             VR :
 5        COMPUTE :
 6         CUSTOM :
"""

OD = """OD_SCLK:
0: 500Mhz
1: 2750Mhz
OD_MCLK:
0: 97Mhz
1: 875MHz
OD_VDDGFX_OFFSET:
0mV
OD_RANGE:
SCLK:     500Mhz       3150Mhz
MCLK:     674Mhz       1075Mhz
"""


def build(root: Path, overdrive: bool = True, procs: dict[int, bytes] | None = None, gen: str = "rdna2") -> Path:
    dev = root / "sys/devices/pci0000:00/0000:00:01.1/0000:03:00.0"
    hw = dev / "hwmon/hwmon2"
    files = {
        dev / "vendor": "0x1002", dev / "device": "0x73ff", dev / "revision": "0xc7",
        dev / "subsystem_vendor": "0x1043", dev / "subsystem_device": "0x05d5",
        dev / "vbios_version": "115-D534P00-100",
        dev / "mem_info_vram_total": "8573157376", dev / "mem_info_vram_used": "700000000",
        dev / "mem_info_vram_vendor": "micron", dev / "gpu_busy_percent": "12",
        dev / "power_dpm_force_performance_level": "auto",
        dev / "pp_power_profile_mode": PROFILE_MODE,
        dev / "pp_dpm_sclk": "0: 500Mhz \n1: 800Mhz *\n2: 2750Mhz \n",
        dev / "pp_dpm_mclk": "0: 96Mhz *\n1: 541Mhz \n2: 675Mhz \n3: 875Mhz \n",
        dev / "current_link_speed": "16.0 GT/s PCIe", dev / "current_link_width": "16",
        hw / "name": "amdgpu",
        hw / "temp1_label": "edge", hw / "temp1_input": "50000",
        hw / "temp2_label": "junction", hw / "temp2_input": "60000", hw / "temp2_crit": "110000",
        hw / "temp3_label": "mem", hw / "temp3_input": "55000",
        hw / "power1_average": "45000000", hw / "power1_cap": "100000000",
        hw / "power1_cap_min": "94000000", hw / "power1_cap_max": "100000000",
        hw / "power1_cap_default": "100000000",
        hw / "pwm1": "80", hw / "pwm1_enable": "2", hw / "pwm1_min": "0", hw / "pwm1_max": "255",
        hw / "fan1_input": "1100", hw / "fan1_max": "3630",
        hw / "freq1_input": "2400000000", hw / "freq2_input": "875000000", hw / "in0_input": "1050",
        root / "sys/module/amdgpu/parameters/ppfeaturemask": "0xffffffff" if overdrive else "0xfff7bfff",
    }
    if overdrive:
        import od_fixtures
        files[dev / "pp_od_clk_voltage"] = {"rdna2": OD, "rdna3": od_fixtures.RDNA3, "rdna4": od_fixtures.RDNA4,
                                             "polaris": od_fixtures.POLARIS, "navi10": od_fixtures.NAVI10}[gen]
    if gen in ("rdna3", "rdna4"):
        import od_fixtures
        for name, text in od_fixtures.FAN_CTRL.items():
            files[dev / "gpu_od" / "fan_ctrl" / name] = text
    for p, v in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(v + ("" if v.endswith("\n") else "\n"))
    drv = root / "sys/bus/pci/drivers/amdgpu"
    drv.mkdir(parents=True, exist_ok=True)
    (dev / "driver").symlink_to(drv)
    card = root / "sys/class/drm/card1"
    card.mkdir(parents=True, exist_ok=True)
    (card / "device").symlink_to(dev)
    for pid, cmd in (procs or {}).items():
        (root / "proc" / str(pid)).mkdir(parents=True, exist_ok=True)
        (root / "proc" / str(pid) / "cmdline").write_bytes(cmd)
    (root / "proc").mkdir(exist_ok=True)
    return dev


def env_for(root: Path) -> dict:
    return {**os.environ, "EMBER_SYSFS_ROOT": str(root)}
