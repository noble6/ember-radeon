import os, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ember.app import caches as C
from ember.core import gpu as G


class CacheTests(unittest.TestCase):
    def test_custom_mesa_dir_is_never_cleared_itself(self):
        with tempfile.TemporaryDirectory() as d:
            shared = Path(d) / "shared"                     # MESA_SHADER_CACHE_DIR pointing at a shared folder
            (shared / "mesa_shader_cache").mkdir(parents=True)
            (shared / "mesa_shader_cache" / "ab").write_bytes(b"x" * 100)
            (shared / "my-documents.txt").write_text("keep me")
            (shared / "other").mkdir()
            (shared / "other" / "file").write_text("keep me too")
            env = {"MESA_SHADER_CACHE_DIR": str(shared), "XDG_CACHE_HOME": str(Path(d) / "cache")}
            with mock.patch.dict(os.environ, env), mock.patch.object(C.GM, "steam_root", lambda: None):
                self.assertEqual(C.mesa_dirs(), [shared / "mesa_shader_cache"])
                self.assertEqual(C.clear("mesa"), 100)
            self.assertTrue((shared / "my-documents.txt").exists())
            self.assertTrue((shared / "other" / "file").exists())
            self.assertEqual(list((shared / "mesa_shader_cache").iterdir()), [])


class ProcessScanTests(unittest.TestCase):
    def test_only_drm_fds_are_inspected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "100"
            (p / "fdinfo").mkdir(parents=True)
            (p / "fd").mkdir()
            (p / "cmdline").write_bytes(b"game\0")
            (p / "comm").write_text("game\n")
            drm = "drm-driver:\tamdgpu\ndrm-pdev:\t0000:03:00.0\ndrm-client-id:\t7\ndrm-memory-vram:\t2048 KiB\n"
            (p / "fdinfo" / "3").write_text(drm)
            os.symlink("/dev/dri/renderD128", p / "fd" / "3")
            # looks like a DRM client, but the fd is a plain file: must be skipped without reading it
            (p / "fdinfo" / "4").write_text(drm.replace("\t7", "\t8").replace("2048", "999999"))
            os.symlink("/home/user/notes.txt", p / "fd" / "4")
            rows = G.gpu_processes("0000:03:00.0", proc=Path(d))
        self.assertEqual([(r["pid"], r["vram"]) for r in rows], [(100, 2048)])


if __name__ == "__main__":
    unittest.main()
