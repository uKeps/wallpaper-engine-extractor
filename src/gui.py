"""Modern dark-themed Tkinter GUI for Wallpaper Engine PKG & TEX Extractor."""

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from src.extractor import extract_package
from src.tex_parser import extract_tex_file, HAS_PILLOW
from src.video_extractor import extract_video_file, SUPPORTED_VIDEO_EXTENSIONS
from src.wallpaper_browser import WallpaperBrowserDialog

# Try to import tkinterdnd2 for drag-and-drop support (optional)
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

SUPPORTED_INPUT_EXTENSIONS = (".pkg", ".tex", *SUPPORTED_VIDEO_EXTENSIONS)

# Colors
BG_COLOR = "#121214"
SURFACE_COLOR = "#1e1e24"
TEXT_COLOR = "#e2e2e7"
TEXT_MUTED = "#8e8e9f"
PRIMARY_COLOR = "#3b82f6"
PRIMARY_HOVER = "#2563eb"
ACCENT_COLOR = "#10b981"
BORDER_COLOR = "#2e2e38"
LOG_BG = "#0d0d0f"

# Tk falls back to the closest system font where Segoe UI isn't installed
FONT = "Segoe UI"


def resource_path(relative: str) -> Path:
    """Locate a bundled asset, both from a source checkout and from a PyInstaller build."""
    base = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent.parent
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


def open_folder(path: Path):
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


class ModernButton(tk.Button):
    """A flat Tkinter button with a hover color."""
    def __init__(self, master, **kwargs):
        hover_bg = kwargs.pop("hover_bg", PRIMARY_HOVER)
        normal_bg = kwargs.setdefault("bg", PRIMARY_COLOR)

        options = dict(
            fg=TEXT_COLOR,
            relief="flat",
            activebackground=hover_bg,
            activeforeground=TEXT_COLOR,
            disabledforeground=TEXT_MUTED,
            cursor="hand2",
            padx=14,
            pady=7,
            font=(FONT, 10),
            bd=0,
            highlightthickness=0,
        )
        super().__init__(master, **{**options, **kwargs})

        self.bind("<Enter>", lambda e: self["state"] != "disabled" and self.configure(bg=hover_bg))
        self.bind("<Leave>", lambda e: self["state"] != "disabled" and self.configure(bg=normal_bg))


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
        self.convert_tex_var = tk.BooleanVar(value=True)
        self.extract_all_mips_var = tk.BooleanVar(value=False)
        self.cleanup_non_images_var = tk.BooleanVar(value=True)
        self.is_running = False

        self.create_widgets()
        self.input_path_var.trace_add("write", lambda *_: self.show_input())

        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self.on_drop)
            self.dnd_bind("<<DropEnter>>", lambda e: self.highlight_drop_zone(True) or e.action)
            self.dnd_bind("<<DropLeave>>", lambda e: self.highlight_drop_zone(False))

    def create_widgets(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "TCheckbutton", background=BG_COLOR, foreground=TEXT_COLOR, font=(FONT, 10),
            indicatorbackground=SURFACE_COLOR, indicatorforeground=TEXT_COLOR,
            indicatorrelief="flat", focuscolor=BG_COLOR, padding=(0, 3),
        )
        style.map(
            "TCheckbutton",
            background=[("active", BG_COLOR)],
            foreground=[("disabled", TEXT_MUTED)],
            indicatorbackground=[("selected", PRIMARY_COLOR), ("active", BORDER_COLOR)],
        )

        self.main_frame = main_frame = tk.Frame(self, bg=BG_COLOR, padx=28, pady=24)
        main_frame.pack(fill="both", expand=True)

        tk.Label(
            main_frame, text="Wallpaper Engine Extractor", font=(FONT, 16, "bold"),
            bg=BG_COLOR, fg=TEXT_COLOR
        ).pack(anchor="w")
        tk.Label(
            main_frame, text="Get the image or video out of any wallpaper.",
            font=(FONT, 10), bg=BG_COLOR, fg=TEXT_MUTED
        ).pack(anchor="w", pady=(2, 18))

        # Drop zone: shows the current input and holds the two ways to pick one
        self.drop_zone = tk.Frame(
            main_frame, bg=SURFACE_COLOR, padx=20, pady=26,
            highlightthickness=1, highlightbackground=BORDER_COLOR
        )
        self.drop_zone.pack(fill="x")
        self.input_title = tk.Label(self.drop_zone, font=(FONT, 12, "bold"), bg=SURFACE_COLOR, fg=TEXT_COLOR)
        self.input_title.pack()
        self.input_detail = tk.Label(self.drop_zone, font=(FONT, 9), bg=SURFACE_COLOR, fg=TEXT_MUTED)
        self.input_detail.pack(pady=(2, 14))
        buttons = tk.Frame(self.drop_zone, bg=SURFACE_COLOR)
        buttons.pack()
        ModernButton(
            buttons, text="Find in Steam", bg=PRIMARY_COLOR, hover_bg=PRIMARY_HOVER,
            command=self.open_wallpaper_browser
        ).pack(side="left", padx=4)
        ModernButton(
            buttons, text="Browse files", bg=BORDER_COLOR, hover_bg="#3a3a46",
            command=self.browse_input
        ).pack(side="left", padx=4)
        self.show_input()

        # Output folder: read-only so long paths clip instead of stretching the window
        output_row = tk.Frame(main_frame, bg=BG_COLOR)
        output_row.pack(fill="x", pady=(16, 10))
        tk.Label(output_row, text="Save to", font=(FONT, 10), bg=BG_COLOR, fg=TEXT_MUTED).pack(side="left")
        ModernButton(
            output_row, text="Change", bg=BG_COLOR, hover_bg=SURFACE_COLOR, padx=8, pady=2,
            command=self.browse_output
        ).pack(side="right")
        tk.Entry(
            output_row, textvariable=self.output_path_var, state="readonly", font=(FONT, 10),
            readonlybackground=BG_COLOR, fg=TEXT_COLOR, relief="flat", bd=0, highlightthickness=0
        ).pack(side="left", fill="x", expand=True, padx=(10, 0))

        ttk.Checkbutton(
            main_frame, text="Images only (skip shaders, scripts and JSON)",
            variable=self.cleanup_non_images_var
        ).pack(anchor="w")
        ttk.Checkbutton(
            main_frame, text="Convert .tex textures to PNG/JPG",
            variable=self.convert_tex_var, command=self.toggle_tex_options
        ).pack(anchor="w")
        self.cb_mips = ttk.Checkbutton(
            main_frame, text="Include every mipmap size", variable=self.extract_all_mips_var
        )
        self.cb_mips.pack(anchor="w", padx=(24, 0))

        if not HAS_PILLOW:
            tk.Label(
                main_frame, text="Pillow not installed: RAW textures will be saved as BMP",
                font=(FONT, 9), bg=BG_COLOR, fg=TEXT_MUTED
            ).pack(anchor="w", pady=(6, 0))

        self.btn_run = ModernButton(
            main_frame, text="Extract", bg=PRIMARY_COLOR, hover_bg=PRIMARY_HOVER,
            font=(FONT, 11, "bold"), pady=10, command=self.start_extraction
        )
        self.btn_run.pack(fill="x", pady=(18, 0))

        # Status line and log stay hidden until the first extraction
        self.status_row = tk.Frame(main_frame, bg=BG_COLOR)
        self.status_label = tk.Label(self.status_row, font=(FONT, 10), bg=BG_COLOR, fg=TEXT_MUTED)
        self.status_label.pack(side="left")
        self.btn_open = ModernButton(
            self.status_row, text="Open folder", bg=BG_COLOR, hover_bg=SURFACE_COLOR, padx=8, pady=2,
            command=lambda: open_folder(Path(self.output_path_var.get()))
        )
        self.log_text = tk.Text(
            main_frame, height=8, bg=LOG_BG, fg=TEXT_MUTED, relief="flat", bd=0, padx=10, pady=8,
            highlightthickness=0, font=("Consolas", 9), state="disabled", wrap="word"
        )

    def show_input(self, title: str | None = None):
        value = self.input_path_var.get().strip()
        if not value:
            self.input_title.configure(text="Drop a wallpaper here" if HAS_DND else "Choose a wallpaper")
            self.input_detail.configure(text="scene.pkg, .tex, .mp4 or .webm")
            return
        path = Path(value)
        self.input_title.configure(text=title or path.name)
        self.input_detail.configure(text=f"{path.parent.name}/{path.name}" if title else f"in {path.parent.name}")

    def highlight_drop_zone(self, active: bool):
        self.drop_zone.configure(highlightbackground=PRIMARY_COLOR if active else BORDER_COLOR)

    def toggle_tex_options(self):
        if self.convert_tex_var.get():
            self.cb_mips.state(["!disabled"])
        else:
            self.cb_mips.state(["disabled"])
            self.extract_all_mips_var.set(False)

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
            self.input_path_var.set(file_path)

    def browse_output(self):
        folder_path = filedialog.askdirectory(title="Select Output Directory")
        if folder_path:
            self.output_path_var.set(folder_path)

    def open_wallpaper_browser(self):
        dialog = WallpaperBrowserDialog(self)
        self.wait_window(dialog)
        if dialog.selected_asset_path:
            self.input_path_var.set(str(dialog.selected_asset_path))
            self.show_input(title=dialog.selected_title)

    def on_drop(self, event):
        self.highlight_drop_zone(False)
        paths = self.tk.splitlist(event.data)
        if not paths:
            return

        path = Path(paths[0])
        if path.suffix.lower() not in SUPPORTED_INPUT_EXTENSIONS:
            messagebox.showerror(
                "Unsupported File",
                f"'{path.name}' is not a supported wallpaper file.\n"
                "Drop a .pkg, .tex, .mp4, or .webm file."
            )
            return

        self.input_path_var.set(str(path))
            
    def log_message(self, message: str):
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
            messagebox.showerror("Error", "Please select an input file (.pkg or .tex).")
            return
            
        input_path = Path(input_file)
        if not input_path.is_file():
            messagebox.showerror("Error", "The selected input file does not exist.")
            return
            
        if not output_folder:
            messagebox.showerror("Error", "Please select an output folder.")
            return
            
        output_path = Path(output_folder)
        
        # Clear logs and reveal them on the first run
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.status_row.pack(fill="x", pady=(14, 6))
        self.log_text.pack(fill="both", expand=True)
        self.btn_open.pack_forget()
        self.status_label.configure(text="Extracting...", fg=TEXT_MUTED)

        # Lock UI
        self.is_running = True
        self.btn_run.configure(state="disabled", bg=SURFACE_COLOR, text="Extracting...")
        
        # Spawn background thread to prevent UI freezing
        thread = threading.Thread(
            target=self.run_extraction,
            args=(input_path, output_path),
            daemon=True
        )
        thread.start()
        
    def run_extraction(self, input_path: Path, output_path: Path):
        try:
            self.log_message("Starting extraction process...\n")
            
            if input_path.suffix.lower() == ".pkg":
                extract_package(
                    pkg_path=input_path,
                    output_dir=output_path,
                    extract_tex=self.convert_tex_var.get(),
                    extract_all_mipmaps=self.extract_all_mips_var.get(),
                    cleanup_non_images=self.cleanup_non_images_var.get(),
                    log_callback=self.log_message
                )
            elif input_path.suffix.lower() == ".tex":
                self.log_message(f"Reading texture {input_path.name}...")
                imgs = extract_tex_file(
                    tex_path=input_path,
                    output_dir=output_path,
                    extract_all_mipmaps=self.extract_all_mips_var.get()
                )
                self.log_message(f"Extracted {len(imgs)} image(s) from .tex container.")
                for img in imgs:
                    self.log_message(f"Created: {img.name}")
            elif input_path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS:
                self.log_message(f"Processing video wallpaper {input_path.name}...")
                output_video = extract_video_file(
                    video_path=input_path,
                    output_dir=output_path,
                    log_callback=self.log_message
                )
                self.log_message(f"Created: {output_video.name}")
            else:
                self.log_message("Error: Unsupported file format.")
                
            self.log_message("\nDone.")
            self.after(0, self.show_done)

        except Exception as e:
            self.log_message(f"\n[ERROR] An error occurred: {e}")
            self.after(0, lambda: self.status_label.configure(text="Extraction failed, see the log below", fg="#ef4444"))
            self.after(0, lambda: messagebox.showerror("Extraction Error", f"An error occurred: {e}"))

        finally:
            self.is_running = False
            self.after(0, lambda: self.btn_run.configure(state="normal", bg=PRIMARY_COLOR, text="Extract"))

    def show_done(self):
        self.status_label.configure(text="Done", fg=ACCENT_COLOR)
        self.btn_open.pack(side="right")


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
