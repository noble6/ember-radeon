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
        self.assertIn("custom_text_center=EMBER ACTIVE  ·  Death Stranding", text)
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
        lines = GM.mangohud_lines(dict(GM.GRAPHICS_DEFAULTS), ["EMBER ACTIVE  ·  Evil\nexec=rm -rf ~", "ok\x00\x07"])
        self.assertFalse(any(l.startswith("exec") for l in lines))
        self.assertTrue(all("\n" not in l and "\x00" not in l for l in lines))
        self.assertIn("custom_text_center=EMBER ACTIVE  ·  Evil exec=rm -rf ~", lines)

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
