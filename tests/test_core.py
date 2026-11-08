"""Core + daemon tests against a fake sysfs tree (no root, no real GPU writes)."""
import importlib
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import fakesys  # noqa: E402

SIMULATED = ("pp_od_clk_voltage", "pp_power_profile_mode", "fan_curve", "fan_zero_rpm_enable",
             "fan_target_temperature", "fan_zero_rpm_stop_temperature", "acoustic_limit_rpm_threshold",
             "acoustic_target_rpm_threshold", "fan_minimum_pwm")


def load(tmp: Path, **kw):
    """Fresh imports bound to a fake tree; writes to command-style files are recorded, not stored."""
    os.environ["EMBER_SYSFS_ROOT"] = str(tmp)
    os.environ["EMBER_STATE_DIR"] = str(tmp / "state")
    os.environ["EMBER_SOCKET"] = str(tmp / "s.sock")
    os.environ["EMBER_CONF"] = str(tmp / "conf")
    fakesys.build(tmp, **kw)
    import ember.core.gpu as G
    import ember.core.tuning as T
    import ember.daemon as D
    G = importlib.reload(G)
    T = importlib.reload(T)
    D = importlib.reload(D)
    log = []
    real = D.write

    def rec(path, value):
        log.append((Path(path).name, value))
        if Path(path).name in SIMULATED:
            return
        real(path, value)
    D.write = rec
    return G, T, D, log


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_discovery_and_snapshot(self):
        G, T, D, _ = load(self.tmp)
        gpus = G.find_gpus()
        self.assertEqual(len(gpus), 1)
        g = gpus[0]
        self.assertEqual(g.pci_slot, "0000:03:00.0")
        self.assertEqual(g.describe()["name"], "AMD Radeon RX 6600")
        s = g.snapshot()
        self.assertEqual(s["temp_junction"], 60.0)
        self.assertEqual(s["power_w"], 45.0)
        self.assertEqual(s["gfx_mhz"], 2400.0)
        caps = g.capabilities()
        self.assertTrue(caps["overdrive"] and caps["overdrive_kernel"])
        ts = g.tuning_state()
        self.assertEqual(ts["power_profile"], 0)
        self.assertEqual(ts["od"]["ranges"]["SCLK"], [500, 3150])
        self.assertEqual(ts["od"]["family"], "minmax")

    def test_validate_clamps_and_rejects(self):
        G, T, D, _ = load(self.tmp)
        st = G.find_gpus()[0].tuning_state()
        v = T.validate({"power_cap_w": 500, "fan": {"mode": "curve", "curve": [[90, 20], [30, 50]]},
                        "od": {"sclk_max": 9999, "vddgfx_offset": 80}}, st)
        self.assertEqual(v["power_cap_w"], 100.0)
        self.assertEqual(v["od"]["sclk_max"], 3150)
        self.assertEqual(v["od"]["vddgfx_offset"], 0)          # never overvolt
        self.assertEqual(v["fan"]["curve"], [[30, 50], [90, 50]])  # sorted + monotonic
        with self.assertRaises(T.InvalidSettings):
            T.validate({"perf_level": "turbo; rm -rf /"}, st)
        with self.assertRaises(T.InvalidSettings):
            T.validate({"power_profile": 42}, st)

    def test_od_rejected_without_kernel_support(self):
        G, T, D, _ = load(self.tmp, overdrive=False)
        st = G.find_gpus()[0].tuning_state()
        with self.assertRaises(T.InvalidSettings):
            T.validate({"od": {"sclk_max": 2800}}, st)

    def test_fan_curve_math(self):
        G, T, D, _ = load(self.tmp)
        c = [[40, 20], [80, 100]]
        self.assertEqual(T.fan_target(c, 30), 20)
        self.assertEqual(T.fan_target(c, 60), 60)
        self.assertEqual(T.fan_target(c, 99), 100)
        self.assertEqual(len(T.resample_curve(c, 5)), 5)

    def test_apply_profile_writes_expected_sequence(self):
        G, T, D, log = load(self.tmp)
        d = D.Daemon()
        key = "0000:03:00.0"
        resp = d.handle({"cmd": "save_profile", "gpu": key, "name": "OC", "activate": True, "settings": {
            "power_profile": 1, "power_cap_w": 97,
            "fan": {"mode": "fixed", "fixed_pct": 50},
            "od": {"sclk_max": 2800, "mclk_max": 900, "vddgfx_offset": -50}}}, uid=0)
        self.assertEqual(resp["runtime"]["applied"], "OC")
        self.assertIsNone(resp["runtime"]["error"])
        self.assertIn(("pp_power_profile_mode", "1"), log)
        self.assertIn(("power1_cap", "97000000"), log)
        od = [v for n, v in log if n == "pp_od_clk_voltage"]
        self.assertEqual(od, ["r", "s 1 2800", "m 1 900", "vo -50", "c"])
        hw = self.tmp / "sys/devices/pci0000:00/0000:00:01.1/0000:03:00.0/hwmon/hwmon2"
        self.assertEqual((hw / "pwm1_enable").read_text().strip(), "1")
        self.assertEqual((hw / "pwm1").read_text().strip(), str(round(255 * 0.5)))
        # back to stock hands the fan back to firmware and resets OD
        log.clear()
        d.handle({"cmd": "reset", "gpu": key}, uid=0)
        self.assertEqual((hw / "pwm1_enable").read_text().strip(), "2")
        self.assertIn(("pp_od_clk_voltage", "r"), log)
        self.assertIn(("power1_cap", "100000000"), log)

    def test_fan_curve_hysteresis_and_emergency(self):
        G, T, D, log = load(self.tmp)
        d = D.Daemon()
        key = "0000:03:00.0"
        hw = self.tmp / "sys/devices/pci0000:00/0000:00:01.1/0000:03:00.0/hwmon/hwmon2"
        d.handle({"cmd": "save_profile", "gpu": key, "name": "C", "activate": True, "settings": {
            "fan": {"mode": "curve", "curve": [[40, 0], [80, 100]], "hysteresis": 3}}}, uid=0)
        self.assertEqual(int((hw / "pwm1").read_text()), round(255 * 0.5))  # 60C -> 50%
        (hw / "temp2_input").write_text("58500")  # small drop: hold speed
        d.ctl[key].fan_tick()
        self.assertEqual(int((hw / "pwm1").read_text()), round(255 * 0.5))
        (hw / "temp2_input").write_text("50000")  # real drop: slow down
        d.ctl[key].fan_tick()
        self.assertEqual(int((hw / "pwm1").read_text()), round(255 * 0.25))
        (hw / "temp2_input").write_text("106000")  # near crit: full blast
        d.ctl[key].fan_tick()
        self.assertEqual(int((hw / "pwm1").read_text()), 255)
        d.shutdown()
        self.assertEqual((hw / "pwm1_enable").read_text().strip(), "2")

    def test_game_rule_switches_profiles(self):
        G, T, D, log = load(self.tmp, procs={
            4242: b"/home/u/.steam/ubuntu12_32/reaper\x00SteamLaunch\x00AppId=1493710\x00--\x00x"})
        d = D.Daemon()
        key = "0000:03:00.0"
        d.handle({"cmd": "activate", "gpu": key, "name": "Quiet"}, uid=0)
        d.handle({"cmd": "set_rules", "gpu": key, "rules": [
            {"match": "steam:1493710", "label": "Some Game", "profile": "Performance"},
            {"match": "exe:../../etc/passwd/x", "profile": "Quiet"}]}, uid=0)
        self.assertEqual(len(d.state["gpus"][key]["rules"]), 1)  # bad matcher dropped
        appids, exes = D.running_games()
        self.assertIn("1493710", appids)
        self.assertIn("reaper", exes)
        rule = D.match_rule(d.state["gpus"][key]["rules"], appids, exes)
        d.runtime[key]["game_rule"] = rule
        d.reconcile(key)
        self.assertEqual(d.runtime[key]["applied"], "Performance")
        self.assertEqual(d.runtime[key]["game"], "Some Game")
        d.runtime[key]["game_rule"] = None
        d.reconcile(key)
        self.assertEqual(d.runtime[key]["applied"], "Quiet")
        d.shutdown()

    def test_resume_drift_reapplies(self):
        G, T, D, log = load(self.tmp)
        d = D.Daemon()
        key = "0000:03:00.0"
        d.handle({"cmd": "save_profile", "gpu": key, "name": "P", "activate": True,
                  "settings": {"power_cap_w": 95, "od": {"sclk_max": 2800}}}, uid=0)
        self.assertFalse(d.ctl[key].drifted())
        hw = self.tmp / "sys/devices/pci0000:00/0000:00:01.1/0000:03:00.0/hwmon/hwmon2"
        (hw / "power1_cap").write_text("100000000")   # driver reset it
        self.assertTrue(d.ctl[key].drifted())
        log.clear()
        d.ctl[key].applied = None
        d.reconcile(key, force=True)
        self.assertIn(("power1_cap", "95000000"), log)
        self.assertIn(("pp_od_clk_voltage", "s 1 2800"), log)

    def test_rdna3_firmware_fan_curve_and_options(self):
        G, T, D, log = load(self.tmp, gen="rdna3")
        d = D.Daemon()
        key = "0000:03:00.0"
        ts = d.ctl[key].state()
        self.assertEqual(ts["fan_ctrl"]["target_temp"], {"value": 95, "range": [25, 110]})
        r = d.handle({"cmd": "save_profile", "gpu": key, "name": "F", "activate": True, "settings": {
            "fan": {"mode": "curve", "curve": [[30, 0], [60, 40], [90, 100]], "fw": {"zero_rpm": 0}},
            "od": {"sclk_max": 2700, "vddgfx_offset": -60}}}, uid=0)
        self.assertIsNone(r["runtime"]["error"])
        fc = [v for n, v in log if n == "fan_curve"]
        self.assertEqual(fc[-1], "c")
        pts = [list(map(int, v.split())) for v in fc[:-1]]
        self.assertEqual(len(pts), 5)
        self.assertEqual(pts[0][1], 25)                         # temps within the firmware range
        self.assertTrue(all(15 <= p[2] <= 100 for p in pts))     # % within the firmware range
        self.assertIn(("fan_zero_rpm_enable", "0"), log)
        od = [v for n, v in log if n == "pp_od_clk_voltage"]
        self.assertEqual(od, ["r", "s 1 2700", "vo -60", "c"])
        hw = self.tmp / "sys/devices/pci0000:00/0000:00:01.1/0000:03:00.0/hwmon/hwmon2"
        self.assertEqual((hw / "pwm1_enable").read_text().strip(), "2")  # pwm path untouched
        log.clear()
        d.handle({"cmd": "reset", "gpu": key}, uid=0)
        self.assertIn(("fan_zero_rpm_enable", "r"), log)

    def test_polaris_needs_manual_mode_for_od(self):
        G, T, D, log = load(self.tmp, gen="polaris")
        d = D.Daemon()
        key = "0000:03:00.0"
        d.handle({"cmd": "save_profile", "gpu": key, "name": "UV", "activate": True,
                  "settings": {"od": {"voltage_max_mv": 1080}}}, uid=0)
        seq = [(n, v) for n, v in log if n in ("power_dpm_force_performance_level", "pp_od_clk_voltage")]
        self.assertEqual(seq[:5], [("power_dpm_force_performance_level", "manual"), ("pp_od_clk_voltage", "r"),
                                   ("pp_od_clk_voltage", "s 7 1366 1080"), ("pp_od_clk_voltage", "c"),
                                   ("power_dpm_force_performance_level", "auto")])
        self.assertEqual(d.state["gpus"][key]["od_stock"]["sections"]["OD_SCLK"][7], [7, 1366, 1150])

    def test_authorization(self):
        G, T, D, log = load(self.tmp)
        d = D.Daemon()
        import pwd
        nobody = pwd.getpwnam("nobody").pw_uid
        self.assertTrue(d.handle({"cmd": "state"}, uid=nobody)["state"])
        with self.assertRaises(PermissionError):
            d.handle({"cmd": "reset", "gpu": "0000:03:00.0"}, uid=nobody)

    def test_boot_crash_guard_skips_od(self):
        G, T, D, log = load(self.tmp)
        d = D.Daemon()
        key = "0000:03:00.0"
        d.handle({"cmd": "save_profile", "gpu": key, "name": "OC", "activate": True,
                  "settings": {"od": {"sclk_max": 2900}}}, uid=0)
        d.handle({"cmd": "set_boot", "gpu": key, "apply_on_boot": True}, uid=0)
        (self.tmp / "state" / "applying").write_text("1")   # previous boot died
        log.clear()
        d2 = D.Daemon()
        d2.boot()
        self.assertTrue(d2.boot_skipped)
        self.assertNotIn(("pp_od_clk_voltage", "s 1 2900"), log)
        self.assertEqual(d2.runtime[key]["applied"], "OC")

    def test_socket_roundtrip(self):
        G, T, D, log = load(self.tmp)
        d = D.Daemon()
        D.Handler.daemon_ref = d
        srv = D.Server(os.environ["EMBER_SOCKET"], D.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        s = socket.socket(socket.AF_UNIX)
        s.connect(os.environ["EMBER_SOCKET"])
        f = s.makefile("rwb")
        f.write(b'{"cmd":"hello"}\nnot json\n'); f.flush()
        a = json.loads(f.readline()); b = json.loads(f.readline())
        self.assertTrue(a["ok"]); self.assertEqual(a["gpus"], ["0000:03:00.0"])
        self.assertFalse(b["ok"])
        srv.shutdown(); srv.server_close()


if __name__ == "__main__":
    unittest.main()
