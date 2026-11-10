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
        f.close(); s.close()
        srv.shutdown(); srv.server_close()

    # ---- safety behaviour added in 1.5

    def _fan_setup(self, fan):
        G, T, D, log = load(self.tmp)
        d = D.Daemon()
        key = "0000:03:00.0"
        hw = self.tmp / "sys/devices/pci0000:00/0000:00:01.1/0000:03:00.0/hwmon/hwmon2"
        d.handle({"cmd": "save_profile", "gpu": key, "name": "F", "activate": True, "settings": {"fan": fan}}, uid=0)
        return D, d, key, hw

    def test_fan_safety_floor_overrides_a_silent_profile(self):
        D, d, key, hw = self._fan_setup({"mode": "fixed", "fixed_pct": 0})
        self.assertEqual(int((hw / "pwm1").read_text()), 0)          # 60 C: the user's 0% stands
        (hw / "temp2_input").write_text("95000")                      # 15 C below critical
        d.ctl[key].fan_tick()
        self.assertEqual(int((hw / "pwm1").read_text()), round(255 * 0.60))
        (hw / "temp2_input").write_text("60000")
        (hw / "temp3_input").write_text("101000")                     # memory sensor near its own limit
        d.ctl[key].fan_tick()
        self.assertEqual(int((hw / "pwm1").read_text()), 255)
        d.shutdown()

    def test_fan_returns_to_auto_when_sensors_fail(self):
        D, d, key, hw = self._fan_setup({"mode": "curve", "curve": [[40, 20], [80, 100]]})
        self.assertEqual((hw / "pwm1_enable").read_text().strip(), "1")
        for n in (1, 2, 3):
            (hw / f"temp{n}_input").unlink()
        for _ in range(D.SENSOR_FAILS_MAX):
            d._tick()
        self.assertEqual((hw / "pwm1_enable").read_text().strip(), "2")
        self.assertIn("sensor", d.runtime[key]["fan_fault"])
        self.assertIn("fan", d.runtime[key]["error"])

    def test_control_loop_survives_errors_and_fails_safe(self):
        D, d, key, hw = self._fan_setup({"mode": "fixed", "fixed_pct": 30})
        d.ctl[key].fan_tick = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        waits = iter([False] * 4 + [True])
        d.stop.wait = lambda _t: next(waits)
        import logging
        logging.disable(logging.CRITICAL)
        try:
            d.loop()                                                  # must not raise
        finally:
            logging.disable(logging.NOTSET)
        self.assertEqual((hw / "pwm1_enable").read_text().strip(), "2")

    def test_fan_left_manual_by_a_crash_is_recovered(self):
        D, d, key, hw = self._fan_setup({"mode": "fixed", "fixed_pct": 30})
        marker = d.ctl[key]._fan_marker
        self.assertTrue(marker.exists())
        self.assertEqual((hw / "pwm1_enable").read_text().strip(), "1")
        # no shutdown(): the process "died". A new instance (or --release-fans) cleans up.
        D.Daemon()
        self.assertEqual((hw / "pwm1_enable").read_text().strip(), "2")
        self.assertFalse(marker.exists())

    def test_service_restart_keeps_the_active_profile_but_a_reboot_does_not(self):
        G, T, D, log = load(self.tmp)
        bid = self.tmp / "proc/sys/kernel/random/boot_id"
        bid.parent.mkdir(parents=True)
        bid.write_text("boot-one\n")
        key = "0000:03:00.0"
        d = D.Daemon()
        d.boot()
        d.handle({"cmd": "activate", "gpu": key, "name": "Quiet"}, uid=0)
        d.shutdown()
        log.clear()
        d2 = D.Daemon()                       # restarted by an update, same boot
        d2.boot()
        self.assertEqual(d2.runtime[key]["applied"], "Quiet")
        self.assertIn(("pp_power_profile_mode", "2"), log)      # Quiet = POWER_SAVING, put back
        self.assertIn(("pwm1_enable", "1"), log)                # and its fan curve is running again
        d2.shutdown()
        bid.write_text("boot-two\n")
        d3 = D.Daemon()                       # real reboot, "apply at boot" is off
        d3.boot()
        self.assertIsNone(d3.state["gpus"][key]["active"])
        self.assertIsNone(d3.runtime[key]["applied"])

    def test_sleeping_laptop_gpu_is_left_alone(self):
        D, d, key, hw = self._fan_setup({"mode": "fixed", "fixed_pct": 30})
        dev = hw.parent.parent
        (dev / "power").mkdir()
        (dev / "power/runtime_status").write_text("suspended\n")
        (hw / "pwm1").write_text("7")
        (hw / "temp2_input").write_text("106000")
        d._tick()
        self.assertEqual(int((hw / "pwm1").read_text()), 7)           # nothing read, nothing written
        self.assertTrue(d.ctl[key].gpu.snapshot()["asleep"])
        d.shutdown()

    def test_bad_requests_are_rejected_cleanly(self):
        G, T, D, log = load(self.tmp)
        d = D.Daemon()
        key = "0000:03:00.0"
        st = d.ctl[key].state()
        for bad in (float("inf"), float("-inf"), float("nan")):
            with self.assertRaises(T.InvalidSettings):
                T.validate({"fan": {"fixed_pct": bad}}, st)
        for req in ({"cmd": "save_profile", "name": ["x"], "settings": {}},
                    {"cmd": "save_profile", "name": "a\nb", "settings": {}},
                    {"cmd": "delete_profile", "name": {"a": 1}},
                    {"cmd": "activate", "name": ["Quiet"]}):
            with self.assertRaises(ValueError):
                d.handle({**req, "gpu": key}, uid=0)
        d.handle({"cmd": "set_rules", "gpu": key, "rules": ["junk", 5, {"match": "exe:ok", "profile": "Quiet"}]}, uid=0)
        self.assertEqual([r["match"] for r in d.state["gpus"][key]["rules"]], ["exe:ok"])
        for i in range(D.MAX_PROFILES):
            try:
                d.handle({"cmd": "save_profile", "gpu": key, "name": f"p{i}", "settings": {}}, uid=0)
            except ValueError:
                break
        self.assertEqual(len(d.state["gpus"][key]["profiles"]), D.MAX_PROFILES)

    def test_update_settings_keep_each_other(self):
        G, T, D, log = load(self.tmp)
        d = D.Daemon()
        key = "0000:03:00.0"
        f = self.tmp / "state" / "update.json"
        d.handle({"cmd": "set_update", "gpu": key, "interval": "weekly"}, uid=0)
        self.assertEqual(json.loads(f.read_text()), {"auto": True, "interval": "weekly"})
        d.handle({"cmd": "set_update", "gpu": key, "auto": False}, uid=0)
        self.assertEqual(json.loads(f.read_text()), {"auto": False, "interval": "weekly"})
        with self.assertRaises(ValueError):
            d.handle({"cmd": "set_update", "gpu": key, "interval": "hourly"}, uid=0)

    def test_profile_files_are_revalidated_for_this_gpu(self):
        G, T, D, log = load(self.tmp, overdrive=False)
        st = D.Daemon().ctl["0000:03:00.0"].state()
        other_card = T.export_profile("OC\n", {"perf_level": "high", "power_profile": 9, "power_cap_w": 250,
                                                "od": {"sclk_max": 2900},
                                                "fan": {"mode": "curve", "curve": [[40, 10], [90, 100]]}}, "RX 7900")
        name, s = T.parse_profile_file(json.dumps(other_card), st)
        self.assertEqual(name, "OC")
        self.assertEqual(s["power_cap_w"], 100.0)            # clamped to this board's limit
        self.assertIsNone(s["power_profile"])                # index does not exist on this GPU
        self.assertIsNone(s["od"])                           # overdrive is off here
        self.assertEqual(s["fan"]["curve"], [[40, 10], [90, 100]])
        for bad in ("nope", json.dumps({"kind": "x"}), "x" * 70000, json.dumps([1, 2]),
                    json.dumps({"kind": "ember-profile", "settings": {"perf_level": "rm -rf"}})):
            with self.assertRaises(T.InvalidSettings):
                T.parse_profile_file(bad, st)

    def test_socket_limits(self):
        G, T, D, log = load(self.tmp)
        d = D.Daemon()
        D.Handler.daemon_ref = d
        srv = D.Server(os.environ["EMBER_SOCKET"], D.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        def conn():
            s = socket.socket(socket.AF_UNIX)
            s.settimeout(5)
            s.connect(os.environ["EMBER_SOCKET"])
            return s
        try:
            big = conn()
            big.sendall(b"x" * (D.MAX_REQUEST + 10))                  # no newline, far too long
            self.assertIn(b"too large", big.makefile("rb").readline())
            big.close()
            time.sleep(0.2)
            held = [conn() for _ in range(D.MAX_CLIENTS_PER_UID)]
            for h in held:                                            # make sure each one is being served
                h.sendall(b'{"cmd":"hello"}\n')
                self.assertTrue(json.loads(h.makefile("rb").readline())["ok"])
            extra = conn()
            self.assertIn(b"too many connections", extra.makefile("rb").readline())
            extra.close()
            for h in held:
                h.close()
            time.sleep(0.3)
            again = conn()                                            # slots are released
            again.sendall(b'{"cmd":"hello"}\n')
            self.assertTrue(json.loads(again.makefile("rb").readline())["ok"])
            again.close()
        finally:
            srv.shutdown(); srv.server_close()


if __name__ == "__main__":
    unittest.main()
