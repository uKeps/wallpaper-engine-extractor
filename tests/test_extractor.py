import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from builders import mip, pkg_bytes, scene_pkg_entries, tex_bytes
from wallpaper_engine_extractor import tex_parser as tp
from wallpaper_engine_extractor.extractor import extract_package, parse_package, wallpaper_output_name
from wallpaper_engine_extractor import steam_finder
from wallpaper_engine_extractor.steam_finder import wallpaper_from_folder

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

    def extract_scene(self, entries, cleanup=True):
        self.pkg.write_bytes(pkg_bytes(entries))
        (self.tmp / "project.json").write_text(json.dumps({"title": "Night Sky"}))
        return extract_package(self.pkg, self.out, cleanup_non_images=cleanup, log_callback=self.logs.append)

    def test_main_image_from_scene(self):
        paths = self.extract_scene(scene_pkg_entries())
        # The layer covering the screen, not the bigger character or mask textures
        self.assertEqual((self.out / "Night Sky.bmp").read_bytes(), (self.out / "materials/sky.bmp").read_bytes())
        self.assertIn("Main image: Night Sky.bmp", self.logs)
        self.assertIn(self.out.resolve() / "Night Sky.bmp", paths)
        self.assertFalse((self.out / "scene.json").exists())  # cleanup still ran

    def test_main_image_fallback_is_largest_non_mask(self):
        entries = scene_pkg_entries()
        del entries["scene.json"]
        self.extract_scene(entries, cleanup=False)
        self.assertEqual((self.out / "Night Sky.bmp").read_bytes(),
                         (self.out / "materials/character.bmp").read_bytes())

    def test_broken_scene_never_fails_extraction(self):
        self.extract_scene(scene_pkg_entries(scene=b"{not json"))
        self.assertTrue((self.out / "Night Sky.bmp").is_file())  # fell back to the textures
        shutil.rmtree(self.out)
        with mock.patch("wallpaper_engine_extractor.extractor.find_main_image", side_effect=RuntimeError("boom")):
            paths = self.extract_scene(scene_pkg_entries())
        self.assertIn("Couldn't pick the main image: boom", self.logs)
        self.assertEqual(len(paths), 4)  # the four converted textures, nothing at the top
        self.assertFalse((self.out / "Night Sky.bmp").exists())

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

    def wallpaper(self, folder_name, title=None, files=None, wp_type="scene"):
        folder = self.tmp / "library" / folder_name
        folder.mkdir(parents=True)
        if title is not None:
            (folder / "project.json").write_text(json.dumps({"title": title, "type": wp_type}))
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

    def test_cli_skips_web_and_application_wallpapers(self):
        self.wallpaper("111", "Scene", {"scene.pkg": pkg_bytes(ENTRIES)})
        web = self.wallpaper("222", "Clock", {"index.html": b"<html></html>"}, wp_type="web")
        self.wallpaper("333", "Visualizer", {"app.exe": b"MZ"}, wp_type="application")
        out = self.tmp / "out"
        result = self.run_cli(self.tmp / "library", "-o", out)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Skipped "Clock": web wallpaper, nothing to extract', result.stdout)
        self.assertIn('Skipped "Visualizer": application wallpaper, nothing to extract', result.stdout)
        self.assertIn("[1/1] Scene", result.stdout)
        self.assertIn(f"Extracted 1 of 1 wallpaper(s) to: {out} (2 skipped, nothing to extract)", result.stdout)

        result = self.run_cli(web, "-o", out)
        self.assertEqual(result.returncode, 1)
        self.assertIn('"Clock" can\'t be extracted: web wallpaper', result.stdout)

    def test_cli_loose_textures(self):
        folder = self.tmp / "textures"
        (folder / "sub").mkdir(parents=True)
        (folder / "a.tex").write_bytes(RGBA_TEX)
        (folder / "sub/b.tex").write_bytes(RGBA_TEX)
        result = self.run_cli(folder, "-o", self.tmp / "out")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Extracted 2 of 2 texture(s)", result.stdout)
        self.assertTrue(list((self.tmp / "out").glob("a.*")) and list((self.tmp / "out/sub").glob("b.*")))
        result = self.run_cli(folder)  # no -o: next to each .tex
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(list(folder.glob("a.[bp][mn][pg]")) and list((folder / "sub").glob("b.[bp][mn][pg]")))

    def test_cli_version(self):
        result = self.run_cli("--version")
        self.assertRegex(result.stdout, r"^wallpaper-engine-extractor \d+\.\d+\.\d+")

    def test_cli_missing_input(self):
        result = self.run_cli(self.tmp / "nope")
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not exist", result.stdout)


class SteamFinderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name).resolve()
        for patcher in (mock.patch.object(Path, "home", return_value=self.home),
                        mock.patch.object(steam_finder.platform, "system", return_value="Linux"),
                        mock.patch.object(steam_finder, "_registry_steam_paths", return_value=[]),
                        mock.patch.dict(os.environ)):
            patcher.start()
            self.addCleanup(patcher.stop)
        os.environ.pop("XDG_DATA_HOME", None)

    def steam(self, root: Path, workshop_id: str):
        item = root / "steamapps/workshop/content/431960" / workshop_id
        item.mkdir(parents=True)
        (item / "project.json").write_text(json.dumps({"title": workshop_id}))
        # Steam lists its own folder as the first library, by its real path
        (root / "steamapps/libraryfolders.vdf").write_text(f'"libraryfolders" {{ "0" {{ "path" "{root}" }} }}')

    def ids(self):
        return sorted(wp.workshop_id for wp in steam_finder.find_installed_wallpapers())

    def test_symlinked_steam_root_is_listed_once(self):
        real = self.home / ".local/share/Steam"
        self.steam(real, "111")
        (self.home / ".steam").mkdir()
        try:
            (self.home / ".steam/steam").symlink_to(real, target_is_directory=True)
        except OSError:
            self.skipTest("symlinks not permitted")
        self.assertEqual(self.ids(), ["111"])

    def test_xdg_data_home_snap_and_flatpak(self):
        os.environ["XDG_DATA_HOME"] = str(self.home / "xdg")
        self.steam(self.home / "xdg/Steam", "111")
        self.steam(self.home / "snap/steam/common/.local/share/Steam", "222")
        self.steam(self.home / ".var/app/com.valvesoftware.Steam/data/Steam", "333")
        self.assertEqual(self.ids(), ["111", "222", "333"])


if __name__ == "__main__":
    unittest.main()
