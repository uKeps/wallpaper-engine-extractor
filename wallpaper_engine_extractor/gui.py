"""Modern dark-themed Tkinter GUI for Wallpaper Engine PKG & TEX Extractor."""

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from wallpaper_engine_extractor.extractor import extract_package, wallpaper_output_name
from wallpaper_engine_extractor.steam_finder import wallpaper_from_folder
from wallpaper_engine_extractor.tex_parser import extract_tex_file, HAS_PILLOW
from wallpaper_engine_extractor.video_extractor import extract_video_file, SUPPORTED_VIDEO_EXTENSIONS
from wallpaper_engine_extractor.theme import (
    ACCENT_COLOR, BG_COLOR, BORDER_COLOR, ERROR_COLOR, FONT, LOG_BG, PRIMARY_COLOR, PRIMARY_HOVER,
    SECONDARY_HOVER, SURFACE_COLOR, TEXT_COLOR, TEXT_MUTED, ModernButton,
)
from wallpaper_engine_extractor.wallpaper_browser import WallpaperBrowserDialog, _load_thumbnail

# Try to import tkinterdnd2 for drag-and-drop support (optional)
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

SUPPORTED_INPUT_EXTENSIONS = (".pkg", ".tex", *SUPPORTED_VIDEO_EXTENSIONS)
PREVIEW_SIZE = (224, 126)
# Button colors: only the next step is blue
PRIMARY = (PRIMARY_COLOR, PRIMARY_HOVER)
SECONDARY = (BORDER_COLOR, SECONDARY_HOVER)
INACTIVE = (SURFACE_COLOR, SURFACE_COLOR)


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


def _box(fill: str, check: bool = False, size: int = 14) -> tk.PhotoImage:
    """A flat checkbox square, with a white check mark when check is set, and a gap before the label."""
    image = tk.PhotoImage(width=size + 7, height=size)  # the unpainted pixels are transparent
    image.put(fill, to=(0, 0, size, size))
    if check:
        for x, y in [(3, 7), (4, 8), (5, 9), (6, 8), (7, 7), (8, 6), (9, 5), (10, 4)]:
            image.put("#ffffff", to=(x, y, x + 1, y + 2))
    return image


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


class App(TkinterDnD.Tk if HAS_DND else tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Wallpaper Engine Extractor")
        self.configure(bg=BG_COLOR)
        self.minsize(520, 0)

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
        self.result_dir = None

        self.create_widgets()
        self.input_path_var.trace_add("write", lambda *_: self.show_input())

        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self.on_drop)
            self.dnd_bind("<<DropEnter>>", lambda e: self.highlight_drop_zone(True) or e.action)
            self.dnd_bind("<<DropLeave>>", lambda e: self.highlight_drop_zone(False))
        self.bind("<Return>", lambda e: self.start_extraction())

    def create_widgets(self):
        style = ttk.Style()
        style.theme_use("clam")
        # clam draws its check as an X: use a drawn box with a real check mark instead
        self.check_images = (_box(BORDER_COLOR), _box(PRIMARY_COLOR, check=True))
        style.element_create("Flat.indicator", "image", self.check_images[0], ("selected", self.check_images[1]))
        style.layout("Flat.TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
            ("Flat.indicator", {"side": "left", "sticky": ""}),
            ("Checkbutton.label", {"side": "left", "sticky": "nswe"}),
        ]})])
        style.configure(
            "Flat.TCheckbutton", background=BG_COLOR, foreground=TEXT_MUTED, font=(FONT, 9), padding=(0, 2),
        )
        style.map("Flat.TCheckbutton", background=[("active", BG_COLOR)], foreground=[("active", TEXT_COLOR)])

        self.main_frame = main_frame = tk.Frame(self, bg=BG_COLOR, padx=28, pady=24)
        main_frame.pack(fill="both", expand=True)

        tk.Label(
            main_frame, text="Wallpaper Engine Extractor", font=(FONT, 15, "bold"),
            bg=BG_COLOR, fg=TEXT_COLOR
        ).pack(anchor="w")
        tk.Label(
            main_frame, text="Get the image or video out of any wallpaper.",
            font=(FONT, 10), bg=BG_COLOR, fg=TEXT_MUTED
        ).pack(anchor="w", pady=(2, 18))

        # Settings sit at the bottom, out of the way of the pick → extract → open flow
        settings = tk.Frame(main_frame, bg=BG_COLOR)
        settings.pack(side="bottom", fill="x", pady=(22, 0))
        tk.Frame(settings, bg=BORDER_COLOR, height=1).pack(fill="x", pady=(0, 10))
        output_row = tk.Frame(settings, bg=BG_COLOR)
        output_row.pack(fill="x")
        tk.Label(output_row, text="Save to", font=(FONT, 9), bg=BG_COLOR, fg=TEXT_MUTED).pack(side="left")
        ModernButton(
            output_row, text="Change", bg=BG_COLOR, hover_bg=SURFACE_COLOR, fg=TEXT_MUTED,
            font=(FONT, 9), padx=8, pady=2, command=self.browse_output
        ).pack(side="right")
        # Read-only so long paths clip instead of stretching the window
        tk.Entry(
            output_row, textvariable=self.output_path_var, state="readonly", font=(FONT, 9),
            readonlybackground=BG_COLOR, fg=TEXT_COLOR, relief="flat", bd=0, highlightthickness=0
        ).pack(side="left", fill="x", expand=True, padx=(8, 0))
        ttk.Checkbutton(
            settings, text="Only keep images and videos", variable=self.cleanup_non_images_var,
            style="Flat.TCheckbutton", takefocus=True,
        ).pack(anchor="w", pady=(4, 0))
        if not HAS_PILLOW:
            tk.Label(
                settings, text="Pillow not installed: RAW textures will be saved as BMP",
                font=(FONT, 9), bg=BG_COLOR, fg=TEXT_MUTED
            ).pack(anchor="w", pady=(4, 0))

        # Drop zone: shows the current input and holds the two ways to pick one
        self.drop_zone = tk.Frame(
            main_frame, bg=SURFACE_COLOR, padx=20, pady=24,
            highlightthickness=1, highlightbackground=BORDER_COLOR
        )
        self.drop_zone.pack(fill="x")
        self.preview_label = tk.Label(self.drop_zone, bg=SURFACE_COLOR, bd=0)
        self.preview_photo = None  # keeps the Tk image alive
        self.input_title = tk.Label(
            self.drop_zone, font=(FONT, 12, "bold"), bg=SURFACE_COLOR, fg=TEXT_COLOR,
            wraplength=440, justify="center"
        )
        self.input_title.pack()
        self.input_detail = tk.Label(self.drop_zone, font=(FONT, 9), bg=SURFACE_COLOR, fg=TEXT_MUTED)
        self.input_detail.pack(pady=(2, 14))
        buttons = tk.Frame(self.drop_zone, bg=SURFACE_COLOR)
        buttons.pack()
        self.btn_steam = ModernButton(buttons, text="Find in Steam", command=self.open_wallpaper_browser)
        self.btn_steam.pack(side="left", padx=4)
        ModernButton(
            buttons, text="Browse files", bg=BORDER_COLOR, hover_bg=SECONDARY_HOVER, command=self.browse_input
        ).pack(side="left", padx=4)

        self.btn_run = ModernButton(main_frame, text="Extract", font=(FONT, 11, "bold"), pady=10,
                                    command=self.start_extraction)
        self.btn_run.pack(fill="x", pady=(16, 0))

        # Status line and log stay hidden until the first extraction; the log until asked for
        self.status_row = tk.Frame(main_frame, bg=BG_COLOR)
        self.status_label = tk.Label(self.status_row, font=(FONT, 10), bg=BG_COLOR, fg=TEXT_MUTED)
        self.status_label.pack(side="left")
        self.btn_open = ModernButton(
            self.status_row, text="Open folder", padx=12, pady=4, command=lambda: open_folder(self.result_dir)
        )
        self.btn_details = ModernButton(
            self.status_row, text="Details", bg=BG_COLOR, hover_bg=SURFACE_COLOR, fg=TEXT_MUTED,
            font=(FONT, 9), padx=8, pady=4, command=self.toggle_log
        )
        self.btn_details.pack(side="right")
        self.log_visible = False
        self.log_text = tk.Text(
            main_frame, width=1, height=8, bg=LOG_BG, fg=TEXT_MUTED, relief="flat", bd=0, padx=10, pady=8,
            highlightthickness=0, font=("Consolas", 9), state="disabled", wrap="word"
        )
        self.show_input()

    def show_input(self):
        value = self.input_path_var.get().strip()
        path = Path(value) if value else None
        wallpaper = wallpaper_from_folder(path.parent) if path and (path.parent / "project.json").is_file() else None
        if not path:
            title = "Drop a wallpaper here" if HAS_DND else "Choose a wallpaper"
            detail = "From Steam, or a scene.pkg, .tex, .mp4 or .webm file"
        elif wallpaper and path == wallpaper.asset_path:
            title, detail = wallpaper.title, f"{wallpaper.wp_type.capitalize()} wallpaper · {path.name}"
        else:
            title, detail = path.name, f"in {path.parent.name}"
        self.input_title.configure(text=title)
        self.input_detail.configure(text=detail)

        thumbnail = _load_thumbnail(wallpaper, PREVIEW_SIZE) if wallpaper else None
        if thumbnail:
            from PIL import ImageTk  # only reached when Pillow made the thumbnail
            self.preview_photo = ImageTk.PhotoImage(thumbnail)
            self.preview_label.configure(image=self.preview_photo)
            self.preview_label.pack(before=self.input_title, pady=(0, 12))
        else:
            self.preview_photo = None
            self.preview_label.pack_forget()

        # Highlight only the next step: pick a wallpaper, then extract it
        self.btn_steam.set_colors(*(SECONDARY if path else PRIMARY))
        if not self.is_running:
            self.btn_run.configure(state="normal" if path else "disabled")
            self.btn_run.set_colors(*(PRIMARY if path else INACTIVE))
        if self.status_row.winfo_manager():
            self.status_row.pack_forget()  # the last result belongs to the previous wallpaper
            self.toggle_log(False)

    def highlight_drop_zone(self, active: bool):
        self.drop_zone.configure(highlightbackground=PRIMARY_COLOR if active else BORDER_COLOR)

    def toggle_log(self, show: bool | None = None):
        self.log_visible = not self.log_visible if show is None else show
        if self.log_visible:
            self.status_row.pack(fill="x", pady=(12, 0), after=self.btn_run)
            self.log_text.pack(fill="both", expand=True, after=self.status_row, pady=(6, 0))
        else:
            self.log_text.pack_forget()
        self.btn_details.configure(text="Hide details" if self.log_visible else "Details")

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
                "Pick a wallpaper first: Find in Steam, Browse files, or drop one here."
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
        
        # Clear logs and reveal them on the first run
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.status_row.pack(fill="x", pady=(12, 0), after=self.btn_run)
        self.btn_open.pack_forget()
        self.status_label.configure(text="Extracting...", fg=TEXT_MUTED)

        # Lock UI
        self.is_running = True
        self.btn_run.configure(state="disabled", text="Extracting...")
        self.btn_run.set_colors(*INACTIVE)
        
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
        self.btn_run.configure(state="normal", text="Extract")
        if not paths:
            failed = paths is None
            self.btn_run.set_colors(*PRIMARY)
            self.status_label.configure(
                text="Extraction failed" if failed else "Nothing was extracted",
                fg=ERROR_COLOR if failed else "#f59e0b",
            )
            self.toggle_log(True)
            return
        self.result_dir = Path(os.path.commonpath([p.parent for p in paths]))
        self.status_label.configure(text=f"\u2713  Saved {len(paths)} file(s)", fg=ACCENT_COLOR)
        # The folder is the next step now
        self.btn_run.set_colors(*SECONDARY)
        self.btn_open.pack(side="right", padx=(8, 0))


def main(path: Path | None = None):
    app = App()
    if path:
        app.after_idle(app.set_input, path)
    app.mainloop()


if __name__ == "__main__":
    main()
