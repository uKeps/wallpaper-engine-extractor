"""Tkinter GUI for Wallpaper Engine Extractor: pick a wallpaper, extract it, open the folder."""

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from pathlib import Path

from wallpaper_engine_extractor.extractor import extract_package, wallpaper_output_name
from wallpaper_engine_extractor.steam_finder import wallpaper_from_folder
from wallpaper_engine_extractor.tex_parser import extract_tex_file, HAS_PILLOW
from wallpaper_engine_extractor.video_extractor import extract_video_file, SUPPORTED_VIDEO_EXTENSIONS
from wallpaper_engine_extractor.theme import (
    ACCENT_COLOR, BG_COLOR, BORDER_COLOR, ERROR_COLOR, LOG_BG, MONO_FONT, PRIMARY_COLOR, PRIMARY_TEXT,
    STRONG_BORDER, SURFACE_COLOR, TEXT_COLOR, TEXT_MUTED, WARNING_COLOR, Card, ModernButton,
    enable_dpi_awareness, font, init_scale, px, rounded, rounded_photo, style_title_bar, upload_icon,
)
from wallpaper_engine_extractor.wallpaper_browser import WallpaperBrowserDialog, _load_thumbnail

# Try to import tkinterdnd2 for drag-and-drop support (optional)
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

SUPPORTED_INPUT_EXTENSIONS = (".pkg", ".tex", *SUPPORTED_VIDEO_EXTENSIONS)
CONTENT_WIDTH = 440  # every block is this wide, so the drawn shapes have a known size
THUMB_SIZE = (80, 45)


def resource_path(relative: str) -> Path:
    """Locate a bundled asset: package data when installed or run from source, sys._MEIPASS in a PyInstaller build."""
    base = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent
    return Path(base) / relative


def get_default_output_dir() -> Path:
    """Best-effort discovery of the user's Desktop folder as the default output location."""
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "Desktop")
            desktop = Path(os.path.expandvars(value))
            if desktop.is_dir():
                return desktop / "Wallpaper Extracted"
    except (ImportError, OSError):
        pass

    desktop = Path.home() / "Desktop"
    base = desktop if desktop.is_dir() else Path.home()
    return base / "Wallpaper Extracted"


def open_folder(path: Path | None):
    if not path or not path.exists():
        messagebox.showerror("Error", "Output folder no longer exists.")
        return
    try:
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])
    except OSError as e:
        messagebox.showerror("Error", f"Could not open folder:\n{e}")


def _fit(text: str, font_spec, width: int) -> str:
    """text cut with an ellipsis to fit width pixels."""
    f = tkfont.Font(font=font_spec)
    if f.measure(text) <= width:
        return text
    while text and f.measure(text + "\u2026") > width:
        text = text[:-1]
    return text.rstrip() + "\u2026"


class App(TkinterDnD.Tk if HAS_DND else tk.Tk):
    def __init__(self):
        enable_dpi_awareness()
        super().__init__()
        init_scale(self)

        self.title("Wallpaper Engine Extractor")
        self.configure(bg=BG_COLOR)
        self.resizable(False, False)

        # Set Window Icon if possible (fallback gracefully).
        # `default=` also applies it to child Toplevels such as the wallpaper browser.
        try:
            self.iconbitmap(default=str(resource_path("assets/icon.ico")))
        except Exception:
            pass

        # Variables
        self.input_path_var = tk.StringVar()
        self.output_path_var = tk.StringVar(value=str(get_default_output_dir()))
        self.cleanup_non_images_var = tk.BooleanVar(value=True)
        self.is_running = False
        self.extracting = None  # the input of the current or last run
        self.result_dir = None

        self.create_widgets()
        style_title_bar(self)
        self.input_path_var.trace_add("write", lambda *_: self.show_input())

        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self.on_drop)
            self.dnd_bind("<<DropEnter>>", lambda e: self.highlight_drop_zone(True) or e.action)
            self.dnd_bind("<<DropLeave>>", lambda e: self.highlight_drop_zone(False))
        self.bind("<Return>", lambda e: self.start_extraction())

    def create_widgets(self):
        self._style_checkbox()
        main = self.main_frame = tk.Frame(self, bg=BG_COLOR, padx=px(28), pady=px(24))
        main.pack(fill="both", expand=True)

        tk.Label(
            main, text="Wallpaper Engine Extractor", font=font(14, "semibold"), bg=BG_COLOR, fg=TEXT_COLOR
        ).pack(anchor="w")
        tk.Label(
            main, text="Get the image or video out of any wallpaper.", font=font(10), bg=BG_COLOR, fg=TEXT_MUTED
        ).pack(anchor="w", pady=(px(2), px(16)))

        # Drop zone: the whole dashed area opens the file picker, the buttons pick from Steam or disk
        self.drop_zone = Card(main, CONTENT_WIDTH, 184, BG_COLOR, STRONG_BORDER, dash=True)
        self.drop_zone.pack()
        zone = self.drop_zone.inner
        self.upload_image = upload_icon(px(40), TEXT_MUTED, BG_COLOR, BORDER_COLOR)
        if self.upload_image:
            tk.Label(zone, image=self.upload_image, bg=BG_COLOR).pack(pady=(0, px(10)))
        tk.Label(
            zone, text="Drop a wallpaper here" if HAS_DND else "Choose a wallpaper",
            font=font(11, "semibold"), bg=BG_COLOR, fg=TEXT_COLOR
        ).pack()
        tk.Label(
            zone, text="or pick one from your Steam library", font=font(9), bg=BG_COLOR, fg=TEXT_MUTED
        ).pack(pady=(px(2), px(12)))
        buttons = tk.Frame(zone, bg=BG_COLOR)
        buttons.pack()
        self.btn_steam = ModernButton(buttons, "Find in Steam", self.open_wallpaper_browser, size=10, pady=6)
        self.btn_steam.pack(side="left", padx=px(4))
        ModernButton(buttons, "Browse files", self.browse_input, "secondary", size=10, pady=6).pack(
            side="left", padx=px(4))
        for widget in (self.drop_zone, zone, *zone.pack_slaves()[:-1]):
            widget.bind("<Button-1>", lambda e: self.browse_input())
            widget.configure(cursor="hand2")
        self.hint = tk.Label(
            main, text="Steam Workshop wallpapers, or .pkg, .tex, .mp4 and .webm files",
            font=font(9), bg=BG_COLOR, fg=TEXT_MUTED
        )
        self.hint.pack(anchor="w", pady=(px(8), 0))

        # The picked wallpaper, shown once there is one
        self.file_card = Card(main, CONTENT_WIDTH, 73, SURFACE_COLOR, anchor="w")
        card = self.file_card.inner
        self.preview_label = tk.Label(card, bg=SURFACE_COLOR, bd=0)
        self.preview_photo = None  # keeps the Tk image alive
        info = tk.Frame(card, bg=SURFACE_COLOR)
        info.pack(side="left", fill="x", expand=True)
        self.input_title = tk.Label(info, font=font(10, "semibold"), bg=SURFACE_COLOR, fg=TEXT_COLOR, anchor="w")
        self.input_title.pack(anchor="w")
        meta = tk.Frame(info, bg=SURFACE_COLOR)
        meta.pack(anchor="w", pady=(px(1), 0))
        self.input_detail = tk.Label(meta, font=font(9), bg=SURFACE_COLOR, fg=TEXT_MUTED)
        self.input_detail.pack(side="left")
        self.status_label = tk.Label(meta, font=font(9), bg=SURFACE_COLOR, fg=TEXT_MUTED)
        self.status_label.pack(side="left", padx=(px(6), 0))
        ModernButton(card, "\u00d7", lambda: self.input_path_var.set(""), "ghost", size=12, padx=8, pady=0).pack(
            side="right")

        # Settings
        self.settings = settings = tk.Frame(main, bg=BG_COLOR)
        settings.pack(fill="x", pady=(px(18), 0))
        output_row = tk.Frame(settings, bg=BG_COLOR)
        output_row.pack(fill="x")
        tk.Label(output_row, text="Save to", font=font(9), bg=BG_COLOR, fg=TEXT_MUTED).pack(side="left")
        ModernButton(output_row, "Change", self.browse_output, "ghost", size=9, padx=8, pady=3).pack(side="right")
        # Read-only so long paths clip instead of stretching the window
        tk.Entry(
            output_row, textvariable=self.output_path_var, state="readonly", font=font(9),
            readonlybackground=BG_COLOR, fg=TEXT_COLOR, relief="flat", bd=0, highlightthickness=0
        ).pack(side="left", fill="x", expand=True, padx=(px(8), 0))
        ttk.Checkbutton(
            settings, text="Only keep images and videos", variable=self.cleanup_non_images_var,
            style="Flat.TCheckbutton" if self.check_images[0] else "TCheckbutton", takefocus=True,
        ).pack(anchor="w", pady=(px(6), 0))
        if not HAS_PILLOW:
            tk.Label(
                settings, text="Pillow not installed: RAW textures will be saved as BMP",
                font=font(9), bg=BG_COLOR, fg=TEXT_MUTED
            ).pack(anchor="w", pady=(px(4), 0))

        # Log: hidden until asked for, or until something goes wrong
        self.log_visible = False
        self.log_text = tk.Text(
            main, width=1, height=7, bg=LOG_BG, fg=TEXT_MUTED, relief="flat", bd=0, padx=px(10), pady=px(8),
            highlightthickness=1, highlightbackground=BORDER_COLOR, font=(MONO_FONT, 9), state="disabled",
            wrap="word"
        )

        # Footer: the actions, right-aligned, the primary one last
        tk.Frame(main, bg=BORDER_COLOR, height=1).pack(fill="x", pady=(px(18), px(14)))
        footer = tk.Frame(main, bg=BG_COLOR)
        footer.pack(fill="x")
        self.btn_details = ModernButton(footer, "Show log", self.toggle_log, "ghost", size=9, padx=8, pady=5)
        self.btn_run = ModernButton(footer, "Extract", self.start_extraction, "disabled")
        self.btn_run.pack(side="right")
        self.btn_open = ModernButton(footer, "Open folder", lambda: open_folder(self.result_dir), "primary")
        self.show_input()

    def _style_checkbox(self):
        style = ttk.Style()
        style.theme_use("clam")
        # clam draws its check as an X: draw a rounded box with a real check mark instead
        self.check_images = (
            rounded(px(16), px(16), px(4), BG_COLOR, STRONG_BORDER),
            rounded(px(16), px(16), px(4), PRIMARY_COLOR, check=PRIMARY_TEXT),
        )
        if self.check_images[0]:
            style.element_create(
                "Flat.indicator", "image", self.check_images[0], ("selected", self.check_images[1]),
                width=px(24), sticky="w",  # wider than the box: the gap before the label
            )
            style.layout("Flat.TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
                ("Flat.indicator", {"side": "left", "sticky": "w"}),
                ("Checkbutton.label", {"side": "left", "sticky": "nswe"}),
            ]})])
        for name in ("Flat.TCheckbutton", "TCheckbutton"):
            style.configure(name, background=BG_COLOR, foreground=TEXT_MUTED, font=font(9), padding=(0, px(2)),
                            focuscolor=BG_COLOR)
            style.map(name, background=[("active", BG_COLOR)], foreground=[("active", TEXT_COLOR)])

    def show_input(self):
        value = self.input_path_var.get().strip()
        path = Path(value) if value else None
        wallpaper = wallpaper_from_folder(path.parent) if path and (path.parent / "project.json").is_file() else None

        if path:
            if wallpaper and path == wallpaper.asset_path:
                title, detail = wallpaper.title, f"{wallpaper.wp_type.capitalize()} \u00b7 {path.name}"
            else:
                title, detail = path.name, f"in {path.parent.name}"
            thumbnail = _load_thumbnail(wallpaper, (px(THUMB_SIZE[0]), px(THUMB_SIZE[1]))) if wallpaper else None
            self.preview_photo = rounded_photo(thumbnail, px(6), SURFACE_COLOR) if thumbnail else None
            if self.preview_photo:
                self.preview_label.configure(image=self.preview_photo)
                self.preview_label.pack(side="left", padx=(0, px(12)), before=self.input_title.master)
            else:
                self.preview_label.pack_forget()
            text_width = px(CONTENT_WIDTH - 90 - (THUMB_SIZE[0] + 12 if self.preview_photo else 0))
            self.input_title.configure(text=_fit(title, self.input_title["font"], text_width))
            self.input_detail.configure(text=_fit(detail, self.input_detail["font"], text_width - px(60)))
            self.status_label.configure(text="\u00b7 Ready", fg=TEXT_MUTED)
            self.file_card.pack(pady=(px(14), 0), after=self.hint)
        else:
            self.file_card.pack_forget()

        # Highlight only the next step: pick a wallpaper, then extract it
        self.btn_steam.restyle(variant="secondary" if path else "primary")
        if not self.is_running:
            self.btn_run.restyle("Extract", "primary" if path else "disabled")
        self.btn_open.pack_forget()  # the last result belongs to the previous wallpaper
        self.btn_details.pack_forget()
        self.toggle_log(False)

    def highlight_drop_zone(self, active: bool):
        self.drop_zone.paint(BG_COLOR, TEXT_MUTED if active else STRONG_BORDER)

    def toggle_log(self, show: bool | None = None):
        self.log_visible = not self.log_visible if show is None else show
        if self.log_visible:
            self.log_text.pack(fill="x", pady=(px(14), 0), after=self.settings)
        else:
            self.log_text.pack_forget()
        self.btn_details.restyle("Hide log" if self.log_visible else "Show log")

    def set_input(self, path: Path):
        """Accept a wallpaper file, or the wallpaper's folder, preview or project.json."""
        folder = path if path.is_dir() else path.parent
        wallpaper = wallpaper_from_folder(folder) if path.is_dir() or (folder / "project.json").is_file() else None
        if path.is_dir() or path.suffix.lower() not in SUPPORTED_INPUT_EXTENSIONS:
            if not (wallpaper and wallpaper.asset_path):
                if wallpaper and wallpaper.wp_type in ("web", "application"):
                    messagebox.showerror(
                        "Cannot Extract Wallpaper",
                        f'"{wallpaper.title}" is a {wallpaper.wp_type} wallpaper and has no image or video to extract.'
                    )
                else:
                    messagebox.showerror(
                        "Unsupported File",
                        f"'{path.name}' is not a supported wallpaper file.\n"
                        "Drop a wallpaper folder, or a .pkg, .tex, .mp4 or .webm file."
                    )
                return
            path = wallpaper.asset_path
        self.input_path_var.set(str(path))

    def browse_input(self):
        file_path = filedialog.askopenfilename(
            title="Select scene.pkg, .tex, or video wallpaper file",
            filetypes=[
                ("Wallpaper Engine Files", "*.pkg;*.tex;*.mp4;*.webm"),
                ("Wallpaper Package (scene.pkg)", "*.pkg"),
                ("Wallpaper Texture (.tex)", "*.tex"),
                ("Video Wallpaper (.mp4/.webm)", "*.mp4;*.webm"),
                ("All files", "*.*")
            ]
        )
        if file_path:
            self.set_input(Path(file_path))

    def browse_output(self):
        folder_path = filedialog.askdirectory(title="Select Output Directory")
        if folder_path:
            self.output_path_var.set(folder_path)

    def open_wallpaper_browser(self):
        dialog = WallpaperBrowserDialog(self)
        self.wait_window(dialog)
        if dialog.selected:
            self.input_path_var.set(str(dialog.selected.asset_path))

    def on_drop(self, event):
        self.highlight_drop_zone(False)
        paths = self.tk.splitlist(event.data)
        if not paths:
            return

        self.set_input(Path(paths[0]))

    def _post(self, callback, *args):
        try:
            if self.winfo_exists():
                self.after(0, lambda: self.winfo_exists() and callback(*args))
        except (tk.TclError, RuntimeError):
            pass

    def log_message(self, message: str):
        # Called from the extraction thread: hand the widget update to the Tk main loop
        self._post(self._append_log, message)

    def _append_log(self, message: str):
        if not self.winfo_exists():
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        
    def start_extraction(self):
        if self.is_running:
            return
            
        input_file = self.input_path_var.get().strip()
        output_folder = self.output_path_var.get().strip()
        
        if not input_file:
            messagebox.showinfo(
                "No wallpaper selected",
                "Pick a wallpaper first: Find in Steam, Browse files, or drop one on the window."
            )
            return
            
        input_path = Path(input_file)
        if not input_path.is_file():
            messagebox.showerror("Error", "That file is gone. It may have been moved or unsubscribed in Steam.")
            return
            
        if not output_folder:
            messagebox.showerror("Error", "Please select an output folder.")
            return
            
        output_path = Path(output_folder) / wallpaper_output_name(input_path)
        
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.btn_open.pack_forget()
        self.status_label.configure(text="\u00b7 Extracting\u2026", fg=TEXT_MUTED)

        # Lock UI
        self.is_running = True
        self.extracting = input_file
        self.btn_run.restyle("Extracting\u2026", "disabled")
        
        # Spawn background thread to prevent UI freezing
        thread = threading.Thread(
            target=self.run_extraction,
            args=(input_path, output_path, self.cleanup_non_images_var.get()),
            daemon=True
        )
        thread.start()
        
    def run_extraction(self, input_path: Path, output_path: Path, cleanup: bool):
        try:
            self.log_message("Starting extraction process...\n")
            suffix = input_path.suffix.lower()

            if suffix == ".pkg":
                paths = extract_package(
                    pkg_path=input_path,
                    output_dir=output_path,
                    cleanup_non_images=cleanup,
                    log_callback=self.log_message
                )
            elif suffix == ".tex":
                self.log_message(f"Reading texture {input_path.name}...")
                paths = extract_tex_file(input_path, output_path, log_callback=self.log_message)
            elif suffix in SUPPORTED_VIDEO_EXTENSIONS:
                self.log_message(f"Processing video wallpaper {input_path.name}...")
                paths = [extract_video_file(input_path, output_path, log_callback=self.log_message)]
            else:
                raise ValueError("Unsupported file format")
            if suffix != ".pkg":
                self.log_message(f"Saved {len(paths)} file(s) to {output_path}")

            self._post(self.show_result, paths)

        except Exception as e:
            self.log_message(f"\nFailed: {e}")
            self._post(self.show_result, None)

        finally:
            self.is_running = False

    def show_result(self, paths: list[Path] | None):
        """Unlock the UI after a run: paths extracted, or None when it failed."""
        if not self.winfo_exists():
            return
        if self.input_path_var.get().strip() != self.extracting:
            self.show_input()  # another wallpaper was picked meanwhile: this result isn't about it
            return
        self.btn_details.pack(side="left")
        if not paths:
            failed = paths is None
            self.btn_run.restyle("Extract", "primary")
            self.status_label.configure(
                text="\u00b7 Failed" if failed else "\u00b7 Nothing extracted",
                fg=ERROR_COLOR if failed else WARNING_COLOR,
            )
            self.toggle_log(True)
            return
        self.result_dir = Path(os.path.commonpath([p.parent for p in paths]))
        count = len(paths)
        self.status_label.configure(text=f"\u00b7 Saved {count} file{'s' if count != 1 else ''}", fg=ACCENT_COLOR)
        # The folder is the next step now
        self.btn_run.restyle("Extract", "secondary")
        self.btn_open.pack(side="right", padx=(px(8), 0), before=self.btn_run)

def main(path: Path | None = None):
    app = App()
    if path:
        app.after_idle(app.set_input, path)
    app.mainloop()


if __name__ == "__main__":
    main()
