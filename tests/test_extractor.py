import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from builders import mip, pkg_bytes, tex_bytes
from src import tex_parser as tp
from src.extractor import extract_package, parse_package, wallpaper_output_name
from src.steam_finder import wallpaper_from_folder

ROOT = Path(__file__).resolve().parent.parent
MP4_BYTES = b"\0\0\0\x18ftypisom" + b"\0" * 20
RGBA_TEX = tex_bytes(size=(2, 2), images=[[mip(2, 2, b"\x10\x20\x30\xff" * 4)]])
PNG_TEX = tex_bytes(size=(2, 2), images=[[mip(2, 2, b"\x89PNG\r\n\x1a\nfake")]], fif=13)
VIDEO_TEX = tex_bytes(size=(2, 2), images=[[mip(2, 2, MP4_BYTES)]], container="TEXB0004", mp4=True)
ENTRIES = {
    "scene.json": b"{}",
    "materials/back.tex": RGBA_TEX,
    "materials/logo.tex": PNG_TEX,
    "materials/clip.tex": VIDEO_TEX,
    "materials/broken.tex": b"TEXV0005\0garbage",
    "shaders/effect.frag": b"void main() {}",
    "models/model.json": b"{}",
}


class PackageTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.pkg = self.tmp / "scene.pkg"
        self.pkg.write_bytes(pkg_bytes(ENTRIES))
        self.out = self.tmp / "out"
        self.logs = []
        patcher = mock.patch.object(tp, "HAS_PILLOW", False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def files(self):
        return sorted(p.relative_to(self.out).as_posix() for p in self.out.rglob("*") if p.is_file())

    def test_no_cleanup_keeps_everything(self):
        extract_package(self.pkg, self.out, log_callback=self.logs.append)
        expected = sorted(list(ENTRIES) + ["materials/back.bmp", "materials/logo.png", "materials/clip.mp4"])
        self.assertEqual(self.files(), expected)
        self.assertEqual((self.out / "materials/back.bmp").read_bytes()[54:58], b"\x30\x20\x10\xff")
        self.assertIn("1 of 4 texture(s) couldn't be converted", self.logs)
        self.assertTrue(any(line.startswith("Saved 10 file(s) to") for line in self.logs))

    def test_cleanup_keeps_images_and_failed_textures(self):
        paths = extract_package(self.pkg, self.out, cleanup_non_images=True, log_callback=self.logs.append)
        expected = ["materials/back.bmp", "materials/broken.tex", "materials/clip.mp4", "materials/logo.png"]
        self.assertEqual(self.files(), expected)
        self.assertEqual(sorted(p.relative_to(self.out.resolve()).as_posix() for p in paths), expected)
        self.assertFalse((self.out / "shaders").exists())
        self.assertFalse((self.out / "models").exists())

    def test_cleanup_without_conversion_keeps_textures(self):
        extract_package(self.pkg, self.out, extract_tex=False, cleanup_non_images=True, log_callback=self.logs.append)
        self.assertEqual(self.files(), sorted(name for name in ENTRIES if name.endswith(".tex")))

    def test_cleanup_never_touches_existing_files(self):
        (self.out / "My Empty Folder").mkdir(parents=True)
        (self.out / "notes.txt").write_text("mine")
        (self.out / "models").mkdir()
        (self.out / "models/own.json").write_text("{}")
        extract_package(self.pkg, self.out, cleanup_non_images=True, log_callback=self.logs.append)
        self.assertTrue((self.out / "My Empty Folder").is_dir())
        self.assertEqual((self.out / "notes.txt").read_text(), "mine")
        self.assertTrue((self.out / "models/own.json").is_file())

    def test_all_textures_failing_raises(self):
        self.pkg.write_bytes(pkg_bytes({"a.tex": b"junk", "b.json": b"{}"}))
        with self.assertRaisesRegex(ValueError, "Couldn't decode any image"):
            extract_package(self.pkg, self.out, cleanup_non_images=True, log_callback=self.logs.append)
        self.assertTrue((self.out / "a.tex").is_file())  # nothing lost

    def test_unsafe_entry_names_are_skipped(self):
        self.pkg.write_bytes(pkg_bytes({"../evil.txt": b"x", "ok.json": b"{}"}))
        extract_package(self.pkg, self.out, log_callback=self.logs.append)
        self.assertFalse((self.tmp / "evil.txt").exists())
        self.assertEqual(self.files(), ["ok.json"])

    def test_damaged_packages(self):
        good = pkg_bytes(ENTRIES)
        for name, data in {"empty": b"", "huge name": b"\xff\xff\xff\x7f", "cut table": good[:40],
                           "cut data": good[:-5]}.items():
            with self.subTest(name):
                self.pkg.write_bytes(data)
                with self.assertRaisesRegex(ValueError, "Not a Wallpaper Engine package, or the file is damaged"):
                    extract_package(self.pkg, self.out, log_callback=self.logs.append)
                if name != "cut data":  # header failures must not leave an empty folder behind
                    self.assertFalse(self.out.exists())

    def test_parse_package(self):
        info = parse_package(self.pkg)
        self.assertEqual(info.root, "PKGV0024")
        self.assertEqual([f.name for f in info.files], list(ENTRIES))


class FolderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # Resolved like the CLI resolves its input (Windows temp dirs can be 8.3 short names)
        self.tmp = Path(self._tmp.name).resolve()

    def tearDown(self):
        self._tmp.cleanup()

    def wallpaper(self, folder_name, title=None, files=None):
        folder = self.tmp / "library" / folder_name
        folder.mkdir(parents=True)
        if title is not None:
            (folder / "project.json").write_text(json.dumps({"title": title, "type": "scene"}))
        for name, data in (files or {}).items():
            (folder / name).write_bytes(data)
        return folder

    def test_wallpaper_output_name(self):
        folder = self.wallpaper("123", 'Cool: "Night" City?. ', {"scene.pkg": b""})
        self.assertEqual(wallpaper_output_name(folder), "Cool_ _Night_ City_")
        self.assertEqual(wallpaper_output_name(folder / "scene.pkg"), "Cool_ _Night_ City_")
        self.assertEqual(wallpaper_output_name(self.wallpaper("456", None, {"scene.pkg": b""}) / "scene.pkg"), "456")
        self.assertEqual(wallpaper_output_name(self.wallpaper("loose", None, {"x.pkg": b""}) / "x.pkg"), "x")
        self.assertEqual(wallpaper_output_name(self.wallpaper("789", "con")), "con_")
        self.assertEqual(len(wallpaper_output_name(self.wallpaper("999", "a" * 300))), 60)

    def test_wallpaper_from_folder(self):
        folder = self.wallpaper("123", "Title", {"scene.pkg": b""})
        info = wallpaper_from_folder(folder)
        self.assertEqual((info.title, info.asset_path, info.wp_type), ("Title", folder / "scene.pkg", "scene"))
        self.assertIsNone(wallpaper_from_folder(folder / "scene.pkg"))

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "main.py"), *map(str, args)],
                              capture_output=True, text=True, cwd=ROOT)

    def test_cli_directory_batch(self):
        self.wallpaper("111", "Scene One", {"scene.pkg": pkg_bytes(ENTRIES)})
        self.wallpaper("222", "Video Two", {"clip.mp4": MP4_BYTES})
        self.wallpaper("333", "Scene One", {"scene.pkg": pkg_bytes({"a.tex": RGBA_TEX})})
        self.wallpaper("444", None)  # nothing to extract
        out = self.tmp / "out"
        result = self.run_cli(self.tmp / "library", "-o", out)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((out / "Scene One/materials/back.png").is_file()
                        or (out / "Scene One/materials/back.bmp").is_file())
        self.assertFalse((out / "Scene One/scene.json").exists())  # cleanup on by default
        self.assertTrue((out / "Scene One (333)").is_dir())
        self.assertEqual((out / "Video Two/clip.mp4").read_bytes(), MP4_BYTES)
        self.assertIn(f"Extracted 3 of 3 wallpaper(s) to: {out}", result.stdout)

    def test_cli_loose_packages_and_case_collisions(self):
        self.wallpaper("loose", None, {"a.pkg": pkg_bytes(ENTRIES), "b.pkg": pkg_bytes(ENTRIES)})
        self.wallpaper("777", "Rain", {"scene.pkg": pkg_bytes(ENTRIES)})
        self.wallpaper("888", "rain", {"scene.pkg": pkg_bytes(ENTRIES)})
        out = self.tmp / "out"
        result = self.run_cli(self.tmp / "library", "-o", out)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Extracted 4 of 4 wallpaper(s)", result.stdout)
        # NTFS is case-insensitive, so "rain" must not share "Rain"'s folder
        self.assertEqual(sorted(d.name for d in out.iterdir()), ["Rain", "a", "b", "rain (888)"])

    def test_cli_single_folder_and_flags(self):
        folder = self.wallpaper("555", "Solo", {"scene.pkg": pkg_bytes(ENTRIES)})
        out = self.tmp / "out"
        result = self.run_cli(folder, "-o", out, "--no-cleanup", "--no-tex-convert")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((out / "Solo/scene.json").is_file())
        self.assertFalse(any((out / "Solo/materials").glob("*.png")))

    def test_cli_single_pkg_still_works(self):
        folder = self.wallpaper("666", "Solo", {"scene.pkg": pkg_bytes(ENTRIES)})
        result = self.run_cli(folder / "scene.pkg", "--all-mipmaps")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"Output: {folder / 'scene_extracted'}", result.stdout)
        self.assertTrue(list((folder / "scene_extracted/materials").glob("back_2x2.*")))

    def test_cli_missing_input(self):
        result = self.run_cli(self.tmp / "nope")
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not exist", result.stdout)


if __name__ == "__main__":
    unittest.main()
