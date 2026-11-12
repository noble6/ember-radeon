import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ember.core import games as GM

SAMPLE = '''"UserLocalConfigStore"
{
	"Software"
	{
		"Valve"
		{
			"Steam"
			{
				"apps"
				{
					"7"
					{
						"LastPlayed"		"1"
					}
					"1850570"
					{
						"LastPlayed"		"1785060893"
						"LaunchOptions"		"PROTON_LOG=1 %command% -skip"
					}
				}
			}
		}
	}
	"x"		"a \\\\ \\"quoted\\""
}
'''

class GamesTests(unittest.TestCase):
    def test_parse(self):
        d = GM.vdf_parse(SAMPLE)
        apps = d["UserLocalConfigStore"]["Software"]["Valve"]["Steam"]["apps"]
        self.assertEqual(apps["1850570"]["LaunchOptions"], "PROTON_LOG=1 %command% -skip")
        self.assertEqual(d["UserLocalConfigStore"]["x"], 'a \\ "quoted"')

    def test_set_existing_preserves_rest(self):
        path = ["UserLocalConfigStore", "Software", "Valve", "Steam", "apps", "1850570"]
        out = GM.vdf_set(SAMPLE, path, "LaunchOptions", "ember-run %command%")
        self.assertEqual(out, SAMPLE.replace('"PROTON_LOG=1 %command% -skip"', '"ember-run %command%"'))

    def test_insert_new_key_and_block(self):
        path = ["UserLocalConfigStore", "Software", "Valve", "Steam", "apps"]
        out = GM.vdf_set(SAMPLE, path + ["7"], "LaunchOptions", 'a "b"')
        self.assertEqual(GM.vdf_parse(out)["UserLocalConfigStore"]["Software"]["Valve"]["Steam"]["apps"]["7"]
                         ["LaunchOptions"], 'a "b"')
        self.assertTrue(GM._only_launch_option_changed(SAMPLE, out, path, "7", 'a "b"'))
        out2 = GM.vdf_set(SAMPLE, path + ["999"], "LaunchOptions", "x")
        self.assertTrue(GM._only_launch_option_changed(SAMPLE, out2, path, "999", "x"))
        self.assertIn('\t\t\t\t\t"999"\n\t\t\t\t\t{\n\t\t\t\t\t\t"LaunchOptions"\t\t"x"\n\t\t\t\t\t}', out2)

    def test_wire(self):
        w = GM.wire_launch_options
        self.assertEqual(w("", True), "ember-run %command%")
        self.assertEqual(w("PROTON_LOG=1 %command% -x", True), "PROTON_LOG=1 ember-run %command% -x")
        self.assertEqual(w("-novid", True), "ember-run %command% -novid")
        self.assertEqual(w("ember-run %command%", False), "")
        self.assertEqual(w("PROTON_LOG=1 ember-run %command% -x", False), "PROTON_LOG=1 %command% -x")
        self.assertEqual(w(w("A=1 %command%", True), True), "A=1 ember-run %command%")

    def test_build_launch(self):
        GM.CACHE_DIR = Path(tempfile.mkdtemp())
        env, cmd = GM.build_launch({"antilag": True, "sharpen": 60, "fps_cap": 72, "overlay": "off",
                                    "present_mode": "mailbox", "fsr": True, "fsr_strength": 9, "hdr": False},
                                   ["game.exe"], tag="steam:1", have=lambda n: "/usr/bin/" + n)
        self.assertEqual(env["ENABLE_LAYER_MESA_ANTI_LAG"], "1")
        hud = Path(env["MANGOHUD_CONFIGFILE"])
        self.assertEqual(hud.read_text().split(), ["fps_limit=72", "fps_limit_method=late", "no_display"])
        self.assertEqual(env["WINE_FULLSCREEN_FSR_STRENGTH"], "5")
        self.assertEqual(env["MESA_VK_WSI_PRESENT_MODE"], "mailbox")
        self.assertIn("casSharpness = 0.60", Path(env["VKBASALT_CONFIG_FILE"]).read_text())
        self.assertEqual(cmd, ["mangohud", "game.exe"])
        env, cmd = GM.build_launch(dict(GM.GRAPHICS_DEFAULTS), ["g"], have=lambda n: None)
        self.assertEqual(env, {}); self.assertEqual(cmd, ["g"])

    def test_new_features(self):
        GM.CACHE_DIR = Path(tempfile.mkdtemp())
        g = dict(GM.GRAPHICS_DEFAULTS, fsr4=True, fsr4_indicator=True, mlfg=True, aa="smaa", sharpen=30, aniso=16,
                 gamescope=True, gs_scale=67, gs_filter="fsr", gs_out_w=1920, gs_out_h=1080, gs_refresh=165)
        env, cmd = GM.build_launch(g, ["game"], tag="t", have=lambda n: n == "gamescope", arch="rdna3")
        self.assertEqual(env["PROTON_FSR4_UPGRADE"], "1")
        self.assertEqual(env["MLFG_UPGRADE"], "1")
        self.assertEqual(env["DXIL_SPIRV_CONFIG"], "wmma_rdna3_workaround")
        self.assertEqual(env["RADV_TEX_ANISO"], "16")
        conf = Path(env["VKBASALT_CONFIG_FILE"]).read_text()
        self.assertIn("effects = smaa:cas", conf)
        self.assertEqual(cmd, ["gamescope", "-W", "1920", "-H", "1080", "-w", "1286", "-h", "724", "-f",
                               "-r", "165", "-F", "fsr", "--sharpness", "2", "--", "game"])
        env, cmd = GM.build_launch(dict(g, gs_filter="integer", gs_scale=50, mlfg=True), ["g"], have=lambda n: n == "gamescope",
                                   arch="rdna2")
        self.assertNotIn("DXIL_SPIRV_CONFIG", env)
        self.assertIn("integer", cmd)
        self.assertEqual(cmd[cmd.index("-w") + 1], "960")
        # gamescope missing: no wrapper, game still launches
        env, cmd = GM.build_launch(g, ["g"], have=lambda n: False)
        self.assertEqual(cmd, ["g"])

    def test_banner_then_final_overlay(self):
        GM.CACHE_DIR = Path(tempfile.mkdtemp())
        g = dict(GM.GRAPHICS_DEFAULTS, fsr4=True, antilag=True, overlay="minimal")
        banner = GM.banner_lines("Death Stranding", g, "Performance")
        self.assertEqual(banner[1], "Performance profile  ·  FSR 4  ·  Anti-Lag")
        env, cmd = GM.build_launch(g, ["game"], tag="steam:1", have=lambda n: n == "mangohud", banner=banner)
        hud = env["MANGOHUD_CONFIGFILE"]
        text = Path(hud).read_text()
        self.assertIn("custom_text_center=EMBER RADEON  ·  Death Stranding", text)
        self.assertIn("legacy_layout=0", text)
        self.assertEqual(cmd, ["mangohud", "game"])
        ino = os.stat(hud).st_ino
        GM.finalize_hud(hud)
        self.assertEqual(Path(hud).read_text().split(), ["fps_only", "position=top-left"])
        self.assertEqual(os.stat(hud).st_ino, ino)   # same inode: MangoHud's inotify watch sees it
        # banner off and nothing else needs MangoHud: no MangoHud at all
        env, cmd = GM.build_launch(dict(GM.GRAPHICS_DEFAULTS, banner=False), ["g"], have=lambda n: True, banner=banner)
        self.assertNotIn("MANGOHUD", env)

    def test_hud_text_cannot_inject_config(self):
        lines = GM.mangohud_lines(dict(GM.GRAPHICS_DEFAULTS), ["EMBER RADEON  ·  Evil\nexec=rm -rf ~", "ok\x00\x07"])
        self.assertFalse(any(l.startswith("exec") for l in lines))
        self.assertTrue(all("\n" not in l and "\x00" not in l for l in lines))
        self.assertIn("custom_text_center=EMBER RADEON  ·  Evil exec=rm -rf ~", lines)

    def test_one_click_presets(self):
        base = dict(GM.GRAPHICS_DEFAULTS)
        self.assertEqual(GM.preset_of(base), "default")
        for p in GM.GRAPHICS_PRESETS:
            self.assertTrue(set(p["set"]) <= set(GM.GRAPHICS_DEFAULTS), p["key"])   # only known options
            self.assertEqual(GM.preset_of({**base, **p["set"]}), p["key"])
        mine = {**base, "hdr": True, "overlay": "standard", "fsr4": True}           # a preset leaves these alone
        perf = next(p for p in GM.GRAPHICS_PRESETS if p["key"] == "performance")
        after = {**mine, **perf["set"]}
        self.assertTrue(after["hdr"] and after["fsr4"] and after["overlay"] == "standard" and after["antilag"])
        self.assertEqual(GM.preset_of({**base, "sharpen": 55}), "")                 # a custom mix matches none

    def _timeline(self, frames):
        """Fake process tables, one per poll; returns (procs, sleep, clock)."""
        state = {"i": 0}

        def procs():
            return frames[min(state["i"], len(frames) - 1)]

        def sleep(_s):
            state["i"] += 1
        return procs, sleep, lambda: float(state["i"])

    def test_banner_waits_for_the_game_not_the_launcher(self):
        S = int(1e9)
        # War Thunder: ember-run becomes the launcher (pid 100), which draws its own window
        # for a while; the game (aces, pid 300) appears later, detached from the launcher.
        frames = [
            {1: ("systemd", 0, 0), 100: ("launcher", 1, 0)},
            {1: ("systemd", 0, 0), 100: ("launcher", 1, 2 * S)},
            {1: ("systemd", 0, 0), 100: ("launcher", 1, 4 * S)},
            {1: ("systemd", 0, 0), 100: ("launcher", 1, 6 * S), 300: ("aces", 1, 0)},
            {1: ("systemd", 0, 0), 300: ("aces", 1, 0)},                      # still loading: nothing drawn
            {1: ("systemd", 0, 0), 300: ("aces", 1, int(0.016 * S))},         # first frames (a light scene)
            {1: ("systemd", 0, 0), 300: ("aces", 1, int(0.032 * S))},
        ]
        procs, sleep, clock = self._timeline(frames)
        self.assertTrue(GM.wait_until_rendering(100, "aces", timeout=60, procs=procs, sleep=sleep, clock=clock))
        self.assertEqual(clock(), 6.0)             # not at launch, not at the launcher: two seconds into the game drawing

    def test_banner_follows_the_process_tree_for_steam_games(self):
        S = int(1e9)
        frames = [
            {50: ("proton", 1, 0), 60: ("firefox", 1, 9 * S)},
            {50: ("proton", 1, 0), 51: ("wine-preloader", 50, 0), 60: ("firefox", 1, 12 * S)},   # unrelated app drawing
            {50: ("proton", 1, 0), 51: ("wine-preloader", 50, 0), 52: ("ds.exe", 51, 0), 60: ("firefox", 1, 15 * S)},
            {50: ("proton", 1, 0), 51: ("wine-preloader", 50, 0), 52: ("ds.exe", 51, S), 60: ("firefox", 1, 18 * S)},
            {50: ("proton", 1, 0), 51: ("wine-preloader", 50, 0), 52: ("ds.exe", 51, 2 * S), 60: ("firefox", 1, 21 * S)},
        ]
        procs, sleep, clock = self._timeline(frames)
        self.assertTrue(GM.wait_until_rendering(50, None, timeout=60, procs=procs, sleep=sleep, clock=clock))
        self.assertEqual(clock(), 4.0)             # the grandchild drew; the browser never counted
        procs, sleep, clock = self._timeline([{50: ("proton", 1, 0)}])
        self.assertFalse(GM.wait_until_rendering(50, None, timeout=5, procs=procs, sleep=sleep, clock=clock))   # gives up

    def test_banner_helper_gives_up_when_the_game_is_gone(self):
        # the command exited and no game ever appeared: stop after the grace period, not after minutes
        procs, sleep, clock = self._timeline([{1: ("systemd", 0, 0)}])
        self.assertFalse(GM.wait_until_rendering(100, "aces", timeout=300, grace=5, procs=procs, sleep=sleep, clock=clock))
        self.assertLessEqual(clock(), 6.0)
        # a launcher that exits while the game is still loading does not end the wait
        frames = [{100: ("launcher", 1, 0)}, {1: ("systemd", 0, 0)}, {300: ("aces", 1, 0)},
                  {300: ("aces", 1, 20_000_000)}, {300: ("aces", 1, 40_000_000)}]
        procs, sleep, clock = self._timeline(frames)
        self.assertTrue(GM.wait_until_rendering(100, "aces", timeout=300, grace=5, procs=procs, sleep=sleep, clock=clock))

    def test_launch_process_table_reads_this_process(self):
        table = GM._launch_procs()
        self.assertIn(os.getpid(), table)
        name, ppid, ns = table[os.getpid()]
        self.assertEqual(ppid, os.getppid())
        self.assertIn("python", name)

    def test_online_safe_mode_loads_nothing_into_the_game(self):
        gfx = {**GM.GRAPHICS_DEFAULTS, "sharpen": 23, "aa": "fxaa", "aniso": 8, "antilag": True, "fps_cap": 60,
               "overlay": "standard", "present_mode": "mailbox", "optiscaler": True, "fsr4": True}
        env, cmd = GM.build_launch(gfx, ["game"], tag="t", have=lambda n: True, banner=["EMBER RADEON", "x"],
                                   write_files=False, safe=True)
        self.assertEqual(env, {"RADV_TEX_ANISO": "8", "MESA_VK_WSI_PRESENT_MODE": "mailbox"})   # driver options only
        self.assertEqual(cmd, ["game"])                                 # no mangohud wrapper either
        for k in env:
            self.assertFalse(k.startswith(("ENABLE_", "MANGOHUD", "VKBASALT", "PROTON_")), k)
        # the same settings without safe mode do inject
        env2, cmd2 = GM.build_launch(gfx, ["game"], tag="t", have=lambda n: True, write_files=False)
        self.assertIn("ENABLE_VKBASALT", env2)
        self.assertEqual(cmd2[0], "mangohud")
        # Roblox (Sober) is safe by default; a choice made by the user always wins
        self.assertTrue(GM.safe_mode_for({"games": {}}, "exe:sober"))
        self.assertFalse(GM.safe_mode_for({"games": {}}, "exe:aces"))
        self.assertFalse(GM.safe_mode_for({"games": {"exe:sober": {"safe_mode": False}}}, "exe:sober"))
        self.assertTrue(GM.safe_mode_for({"games": {"steam:1": {"safe_mode": True}}}, "steam:1"))

    def test_flatpak_games_get_settings_handed_into_the_sandbox(self):
        sober = ["/usr/bin/flatpak", "run", "--branch=stable", "--command=sober", "org.vinegarhq.Sober", "--"]
        gfx = {**GM.GRAPHICS_DEFAULTS, "sharpen": 23, "aniso": 8, "banner": False}
        with tempfile.TemporaryDirectory() as d:
            old = GM.CACHE_DIR
            GM.CACHE_DIR = Path(d)
            try:
                env, cmd = GM.build_launch(gfx, sober, tag="exe:sober", have=lambda n: True)
            finally:
                GM.CACHE_DIR = old
        i = cmd.index("run")
        opts = cmd[i + 1:cmd.index("--branch=stable")]
        self.assertIn("--env=RADV_TEX_ANISO=8", opts)
        self.assertIn("--env=ENABLE_VKBASALT=1", opts)
        self.assertIn(f"--filesystem={d}:ro", opts)                     # so the sandbox can read the vkBasalt config
        self.assertEqual(cmd[0], "/usr/bin/flatpak")                    # the host mangohud wrapper is not used
        self.assertEqual(cmd[cmd.index("--branch=stable"):], sober[2:]) # the rest of the command is untouched
        # safe mode: only the driver option goes in, and no folder is shared
        env, cmd = GM.build_launch(gfx, sober, tag="exe:sober", have=lambda n: True, write_files=False, safe=True)
        self.assertEqual([c for c in cmd if c.startswith("--env=") or c.startswith("--filesystem=")],
                         ["--env=RADV_TEX_ANISO=8"])
        # a non-Flatpak command is never rewritten
        self.assertEqual(GM.into_flatpak(["game", "run"], {"A": "1"}), ["game", "run"])

    def test_optiscaler_fsr3(self):
        env, _ = GM.build_launch(dict(GM.GRAPHICS_DEFAULTS, optiscaler=True, opti_fg=True, banner=False), ["g"],
                                 have=lambda n: False)
        self.assertEqual(env["PROTON_USE_OPTISCALER"], "1")
        self.assertIn("Upscalers.Dx12Upscaler=ffx", env["PROTON_OPTISCALER_CONFIG"])
        self.assertIn("FrameGen.FGOutput=fsrfg", env["PROTON_OPTISCALER_CONFIG"])

    def test_real_steam_roundtrip_readonly(self):
        root = GM.steam_root()
        if not root:
            self.skipTest("no steam")
        for lc in GM.local_config_paths(root):
            text = lc.read_text(errors="surrogateescape")
            path = ["UserLocalConfigStore", "Software", "Valve", "Steam", "apps"]
            for appid in ("1850570", "424242"):
                out = GM.vdf_set(text, path + [appid], "LaunchOptions", "ember-run %command%")
                self.assertTrue(GM._only_launch_option_changed(text, out, path, appid, "ember-run %command%"))
        self.assertTrue(any(g["appid"] == "1850570" for g in GM.scan_steam()))

if __name__ == "__main__":
    unittest.main()
