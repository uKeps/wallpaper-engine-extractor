"""Smoke test of the main window's flow: pick, extract, result. Skipped where Tk can't open a window."""

import json
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wallpaper_engine_extractor import gui  # noqa: E402


class MainWindowTests(unittest.TestCase):
    def setUp(self):
        try:
            self.app = gui.App()
        except tk.TclError as e:
            self.skipTest(f"no display: {e}")
        self.app.withdraw()
        self.addCleanup(self.app.destroy)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name) / "123"
        self.folder.mkdir()
        (self.folder / "scene.pkg").write_bytes(b"")
        (self.folder / "project.json").write_text(json.dumps({"title": "Night Sky", "type": "scene"}))

    def test_extract_is_enabled_only_once_a_wallpaper_is_picked(self):
        self.assertEqual(str(self.app.btn_run["state"]), "disabled")
        self.app.set_input(self.folder)
        self.assertEqual(self.app.input_path_var.get(), str(self.folder / "scene.pkg"))
        self.assertEqual(self.app.input_title["text"], "Night Sky")
        self.assertEqual(str(self.app.btn_run["state"]), "normal")

    def test_failure_opens_the_log_and_success_offers_the_folder(self):
        self.app.set_input(self.folder)
        self.app.show_result(None)
        self.assertTrue(self.app.log_visible)
        self.app.toggle_log(False)
        self.app.show_result([self.folder / "a.png"])
        self.assertFalse(self.app.log_visible)
        self.assertEqual(self.app.result_dir, self.folder)
        self.assertIn("Saved 1 file", self.app.status_label["text"])


if __name__ == "__main__":
    unittest.main()
