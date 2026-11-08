"""Overdrive across amdgpu generations: parsing, controls, validation, command generation."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import od_fixtures as F  # noqa: E402
from ember.core import gpu as G  # noqa: E402
from ember.core import tuning as T  # noqa: E402


def keys(od):
    return [c["key"] for c in G.od_controls(od)]


class Generations(unittest.TestCase):
    def test_polaris_states(self):
        od = G.parse_od(F.POLARIS)
        self.assertEqual(od["family"], "states")
        self.assertEqual(od["sections"]["OD_SCLK"][7], [7, 1366, 1150])
        self.assertEqual(keys(od), ["sclk_max", "voltage_max_mv", "mclk_max"])
        v = {c["key"]: c for c in G.od_controls(od)}["voltage_max_mv"]
        self.assertEqual((v["from"], v["to"]), (750, 1150))  # capped at stock: undervolt only
        clean = T.validate({"od": {"sclk_max": 1400, "voltage_max_mv": 1300, "mclk_max": 2100}}, {"od": od})
        self.assertEqual(clean["od"]["voltage_max_mv"], 1150)
        self.assertEqual(G.od_commands(od, clean["od"]), ["s 7 1400 1150", "m 1 2100 950"])
        self.assertEqual(G.od_commands(od, {"voltage_max_mv": 1080}), ["s 7 1366 1080"])

    def test_navi10_curve(self):
        od = G.parse_od(F.NAVI10)
        self.assertEqual(od["family"], "curve")
        self.assertEqual(od["ranges"]["VDDC_CURVE_VOLT[2]"], [750, 1200])
        self.assertEqual(keys(od), ["sclk_max", "sclk_min", "mclk_max", "voltage_max_mv"])
        self.assertEqual(G.od_commands(od, {"sclk_max": 2000, "voltage_max_mv": 1100, "mclk_max": 900}),
                         ["s 1 2000", "m 1 900", "vc 2 2000 1100"])

    def test_rdna3_minmax(self):
        od = G.parse_od(F.RDNA3)
        self.assertEqual(od["family"], "minmax")
        c = {c["key"]: c for c in G.od_controls(od)}
        self.assertEqual((c["vddgfx_offset"]["from"], c["vddgfx_offset"]["to"]), (-300, 0))
        self.assertEqual(G.od_commands(od, {"sclk_max": 2700, "mclk_max": 1300, "vddgfx_offset": -70}),
                         ["s 1 2700", "m 1 1300", "vo -70"])

    def test_rdna4_offset(self):
        od = G.parse_od(F.RDNA4)
        self.assertEqual(od["family"], "offset")
        self.assertEqual(keys(od), ["sclk_offset", "mclk_max", "vddgfx_offset"])
        clean = T.validate({"od": {"sclk_offset": 5000, "sclk_max": 3000}}, {"od": od})
        self.assertEqual(clean["od"], {"sclk_offset": 1000})  # clamped; sclk_max not offered -> ignored
        self.assertEqual(G.od_commands(od, {"sclk_offset": 150, "vddgfx_offset": -40}), ["s 150", "vo -40"])

    def test_apu(self):
        od = G.parse_od(F.APU)
        self.assertEqual(od["family"], "apu")
        self.assertEqual(keys(od), ["sclk_max"])
        self.assertEqual(G.od_commands(od, {"sclk_max": 2300}), ["s 1 2300"])

    def test_stock_table_caps_voltage_after_changes(self):
        stock = G.parse_od(F.POLARIS)
        now = G.parse_od(F.POLARIS.replace("1366MHz       1150mV", "1366MHz       1000mV"))
        v = {c["key"]: c for c in G.od_controls(now, stock)}["voltage_max_mv"]
        self.assertEqual((v["stock"], v["to"]), (1150, 1150))

    def test_fan_ctrl_parse_and_validate(self):
        self.assertEqual(G.parse_fan_ctrl(F.FAN_CTRL["fan_target_temperature"]), {"value": 95, "range": [25, 110]})
        self.assertEqual(G.parse_fan_ctrl(F.FAN_CTRL["acoustic_limit_rpm_threshold"])["value"], 2450)
        st = {"fan_ctrl": {"target_temp": {"value": 95, "range": [25, 110]}, "zero_rpm": {"value": 1, "range": [0, 1]}}}
        clean = T.validate({"fan": {"fw": {"target_temp": 200, "zero_rpm": 0, "bogus": 3}}}, st)
        self.assertEqual(clean["fan"]["fw"], {"target_temp": 110, "zero_rpm": 0})


if __name__ == "__main__":
    unittest.main()
