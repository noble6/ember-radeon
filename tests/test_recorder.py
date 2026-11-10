"""Recorder logic that doesn't need a GPU: arguments, naming, filing, listing."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ember.app import recorder as R  # noqa: E402

CAPS = {"available": True, "codecs": ["h264", "hevc"],
        "captures": [{"name": "DP-1", "resolution": "1920x1080"}, {"name": "region", "resolution": ""},
                     {"name": "portal", "resolution": ""}]}


class RecorderTests(unittest.TestCase):
    def cfg(self, **kw):
        return {**R.DEFAULTS, "output_dir": tempfile.mkdtemp(), **kw}

    def test_record_args(self):
        a = R.build_args(self.cfg(mic=True), CAPS, "record", "/tmp/x.mp4")
        self.assertEqual(a[:3], ["gpu-screen-recorder", "-w", "DP-1"])
        self.assertIn("hevc", a)                                    # auto picks HEVC when available
        self.assertEqual(a[a.index("-ac") + 1], "aac")              # AAC in MP4 for compatibility
        self.assertEqual([a[i + 1] for i, x in enumerate(a) if x == "-a"], ["default_output", "default_input"])
        self.assertEqual(a[a.index("-q") + 1], "very_high")
        self.assertNotIn("-r", a)
        self.assertEqual(a[-2], "-ipc")

    def test_replay_args_and_fallbacks(self):
        a = R.build_args(self.cfg(codec="av1", capture="HDMI-A-9", replay_seconds=99999, mic=True, mic_separate=False,
                                  container="mkv"), CAPS, "replay", "/out")
        self.assertEqual(a[2], "DP-1")                              # unknown monitor -> first real monitor
        self.assertEqual(a[a.index("-k") + 1], "hevc")              # AV1 not supported here -> HEVC
        self.assertEqual(a[a.index("-r") + 1], "1200")              # clamped
        self.assertEqual(a[a.index("-bm") + 1], "cbr")
        self.assertEqual(a[a.index("-ac") + 1], "opus")
        self.assertIn("default_output|default_input", a)
        self.assertEqual(a[a.index("-ro") + 1], "/out")
        p = R.build_args(self.cfg(capture="portal"), CAPS, "screenshot", "/tmp/s.png")
        self.assertIn("-restore-portal-session", p)
        self.assertNotIn("-ipc", p)

    def test_naming_and_filing(self):
        self.assertEqual(R.clip_name('Half/Life: "2"', "replay", ".mp4", time.mktime((2026, 11, 8, 14, 2, 11, 0, 0, -1))),
                         "HalfLife 2 2026-11-08 14-02-11 Replay.mp4")
        cfg = self.cfg()
        src = Path(cfg["output_dir"]) / "Replay_2026.mp4"
        src.write_bytes(b"x")
        dest = R.file_clip(str(src), cfg, "Death Stranding", "replay")
        self.assertTrue(dest.startswith(os.path.join(cfg["output_dir"], "Death Stranding", "Death Stranding ")))
        self.assertTrue(dest.endswith(" Replay.mp4") and os.path.exists(dest) and not src.exists())
        src.write_bytes(b"y")   # same second -> no overwrite
        dest2 = R.file_clip(str(src), cfg, "Death Stranding", "replay")
        self.assertNotEqual(dest, dest2)
        flat = R.file_clip(str(Path(dest2)), {**cfg, "per_game_folders": False}, None, "video")
        self.assertEqual(os.path.dirname(flat), cfg["output_dir"])
        kinds = sorted(c["kind"] for c in R.list_clips(cfg["output_dir"]))
        self.assertEqual(kinds, ["replay", "video"])

    def test_long_replay_buffers_go_to_disk(self):
        self.assertEqual(R.replay_storage(60, 35000), "ram")        # about 250 MB
        self.assertEqual(R.replay_storage(1200, 60000), "disk")     # about 8.8 GB
        args = R.build_args({**R.DEFAULTS, "replay_seconds": 1200, "quality": "ultra"}, CAPS, "replay", "/tmp/x")
        self.assertEqual(args[args.index("-replay-storage") + 1], "disk")

    def test_recycled_pid_is_not_mistaken_for_the_recorder(self):
        self.assertFalse(R._is_recorder(os.getpid()))               # alive, but it is this test, not the recorder
        self.assertFalse(R._is_recorder(None))
        self.assertFalse(R._is_recorder(2 ** 22 + 12345))
        rec = R.Recorder()
        rec._pid, rec.mode = os.getpid(), "replay"                  # stale state pointing at an unrelated process
        self.assertFalse(rec.alive())
        rec._signal_stop()                                          # must not signal us

    def test_status_when_idle(self):
        os.environ["XDG_RUNTIME_DIR"] = tempfile.mkdtemp()
        rec = R.Recorder()
        self.assertIsNone(rec.status()["mode"])
        with self.assertRaises(R.RecorderError):
            rec.save_replay()


if __name__ == "__main__":
    unittest.main()
