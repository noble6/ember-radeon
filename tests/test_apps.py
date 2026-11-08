import os, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ember.core import apps as A


class ParseExec(unittest.TestCase):
    def test_flatpak_command_flag(self):
        r = A.parse_exec("/usr/bin/flatpak run --branch=stable --arch=x86_64 --command=sober "
                         "--file-forwarding org.vinegarhq.Sober -- @@u %u @@", "org.vinegarhq.Sober")
        self.assertEqual(r["process"], "sober")
        self.assertEqual(r["flatpak"], "org.vinegarhq.Sober")

    def test_flatpak_metadata_command(self):
        with tempfile.TemporaryDirectory() as d:
            meta = Path(d) / "flatpak/app/org.example.Game/current/active"
            meta.mkdir(parents=True)
            (meta / "metadata").write_text("[Application]\nname=org.example.Game\ncommand=game-bin\n")
            with mock.patch.object(A, "_DATA_HOME", Path(d)):
                r = A.parse_exec("flatpak run org.example.Game")
        self.assertEqual(r["process"], "game-bin")

    def test_wrappers_and_env(self):
        self.assertEqual(A.parse_exec("env DXVK_HUD=1 gamemoderun /opt/game/bin/game.x86_64 %U")["process"],
                         "game.x86_64")
        self.assertEqual(A.parse_exec("gamescope -w 1920 -h 1080 -- supertuxkart")["process"], "supertuxkart")

    def test_steam_and_ember_run(self):
        self.assertEqual(A.parse_exec("steam steam://rungameid/1850570")["steam"], "1850570")
        r = A.parse_exec("/usr/local/bin/ember-run --id exe:aces -- /games/launcher")
        self.assertEqual((r["ember_id"], r["process"]), ("exe:aces", "aces"))


class DesktopApps(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.home = root / "home"
        self.sys = root / "sys"
        for d in (self.home / "applications", self.sys / "applications", self.sys / "icons/hicolor/256x256/apps"):
            d.mkdir(parents=True)
        (self.sys / "icons/hicolor/256x256/apps/tux.png").write_bytes(b"png")

        def entry(base, name, body):
            (base / "applications" / name).write_text("[Desktop Entry]\nType=Application\n" + body)
        entry(self.sys, "tux.desktop", "Name=Tux Racer\nExec=tuxracer %f\nIcon=tux\nCategories=Game;ArcadeGame;\n")
        entry(self.sys, "editor.desktop", "Name=Editor\nExec=editor\nCategories=Utility;\n")
        entry(self.sys, "hidden.desktop", "Name=Hidden\nExec=x\nNoDisplay=true\nCategories=Game;\n")
        entry(self.sys, "steam.desktop", "Name=Steam\nExec=steam %U\nCategories=Game;\n")
        entry(self.sys, "bottle.desktop", "Name=ds\nExec=flatpak run --command=bottles-cli com.usebottles.bottles "
                                          "run -p ds -b 'RE$' -- '%u'\nCategories=Game;\n")
        # the user's own copy wins over the system one
        entry(self.home, "editor.desktop", "Name=My Editor\nExec=editor2\n")
        self.env = mock.patch.dict(os.environ, {"XDG_DATA_DIRS": str(self.sys)})
        self.env.start()
        self.dh = mock.patch.object(A, "_DATA_HOME", self.home)
        self.dh.start()

    def tearDown(self):
        self.dh.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_scan(self):
        found = {a["desktop"]: a for a in A.desktop_apps()}
        self.assertNotIn("hidden.desktop", found)
        self.assertEqual(found["editor.desktop"]["name"], "My Editor")
        tux = found["tux.desktop"]
        self.assertTrue(tux["game"])
        self.assertEqual(tux["process"], "tuxracer")
        self.assertTrue(tux["icon"].endswith("256x256/apps/tux.png"))
        self.assertTrue(found["steam.desktop"]["launcher"])
        self.assertFalse(found["steam.desktop"]["game"])
        self.assertEqual(found["bottle.desktop"]["process"], "")   # launched indirectly: user must say
        self.assertEqual(A.desktop_apps()[0]["game"], True)         # games sort first

    def test_launcher(self):
        with mock.patch.object(A, "LAUNCHER_DIR", self.home / "applications"):
            p = A.write_launcher("Sober", "sober", ["flatpak", "run", "org.vinegarhq.Sober"], "/i/s.svg",
                                 "/usr/local/bin/ember-run")
            self.assertEqual(p, A.launcher_path("sober"))
            text = p.read_text()
        self.assertIn("Exec=/usr/local/bin/ember-run --id exe:sober -- flatpak run org.vinegarhq.Sober\n", text)
        self.assertIn("Name=Sober (Ember)\n", text)

    def test_exec_quoting(self):
        self.assertEqual(A.desktop_exec(["/a b/c", "50%", "$x"]), '"/a b/c" 50%% "\\\\$x"')
        self.assertEqual(A.launch_argv("game --x %U @@u %u @@"), ["game", "--x"])


if __name__ == "__main__":
    unittest.main()
