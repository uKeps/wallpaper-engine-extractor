"""Modern dark-themed Tkinter GUI for Wallpaper Engine PKG & TEX Extractor."""

import os
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
PRIMARY_COLOR = "#3b82f6"       # Premium Blue
PRIMARY_HOVER = "#2563eb"
ACCENT_COLOR = "#10b981"        # Emerald Green
BORDER_COLOR = "#2e2e38"
LOG_BG = "#0d0d0f"


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


class ModernButton(tk.Button):
    """A customized Tkinter button with hover effects and modern style."""
    def __init__(self, master, **kwargs):
        hover_bg = kwargs.pop("hover_bg", PRIMARY_HOVER)
        normal_bg = kwargs.get("bg", PRIMARY_COLOR)
        
        super().__init__(
            master,
            fg=TEXT_COLOR,
            relief="flat",
            activebackground=hover_bg,
            activeforeground=TEXT_COLOR,
            cursor="hand2",
            padx=15,
            pady=8,
            font=("Arial", 10, "bold"),
            bd=0,
            **kwargs
        )
        
        self.bind("<Enter>", lambda e: self.configure(bg=hover_bg))
        self.bind("<Leave>", lambda e: self.configure(bg=normal_bg))


class App(TkinterDnD.Tk if HAS_DND else tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Wallpaper Engine Asset Extractor")
        self.geometry("700x600")
        self.configure(bg=BG_COLOR)
        self.resizable(True, True)

        # Set Window Icon if possible (fallback gracefully)
        try:
            self.iconbitmap("")
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

        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self.on_drop)
        
    def create_widgets(self):
        # Apply style overrides
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=BG_COLOR, foreground=TEXT_COLOR)
        style.configure("TLabel", background=BG_COLOR, foreground=TEXT_COLOR, font=("Arial", 10))
        style.configure("TCheckbutton", background=BG_COLOR, foreground=TEXT_COLOR, font=("Arial", 9))
        
        # Main Container
        main_frame = tk.Frame(self, bg=BG_COLOR, padx=20, pady=20)
        main_frame.pack(fill="both", expand=True)
        
        # Header
        header_label = tk.Label(
            main_frame,
            text="Wallpaper Engine Extractor",
            font=("Arial", 18, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR
        )
        header_label.pack(anchor="w", pady=(0, 5))
        
        sub_header = tk.Label(
            main_frame,
            text="Extract scene.pkg archives and convert proprietary .tex textures into standard images.",
            font=("Arial", 10),
            bg=BG_COLOR,
            fg=TEXT_MUTED
        )
        sub_header.pack(anchor="w", pady=(0, 20))
        
        # Input Selection Frame
        input_frame = tk.LabelFrame(
            main_frame,
            text=" File Selection ",
            font=("Arial", 10, "bold"),
            bg=BG_COLOR,
            fg=PRIMARY_COLOR,
            bd=1,
            relief="solid",
            padx=15,
            pady=15
        )
        input_frame.pack(fill="x", pady=(0, 15))
        
        # Grid Configuration for Inputs
        input_frame.columnconfigure(1, weight=1)
        
        # Input File path row
        tk.Label(input_frame, text="Input File:", bg=BG_COLOR, fg=TEXT_COLOR).grid(row=0, column=0, sticky="w", pady=5)
        input_entry = tk.Entry(
            input_frame,
            textvariable=self.input_path_var,
            bg=SURFACE_COLOR,
            fg=TEXT_COLOR,
            insertbackground=TEXT_COLOR,
            relief="flat",
            bd=5,
            highlightbackground=BORDER_COLOR,
            font=("Arial", 10)
        )
        input_entry.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        browse_input_btn = ModernButton(
            input_frame,
            text="Browse",
            bg=SURFACE_COLOR,
            hover_bg=BORDER_COLOR,
            command=self.browse_input
        )
        browse_input_btn.grid(row=0, column=2, pady=5)
        
        # Output File path row
        tk.Label(input_frame, text="Output Folder:", bg=BG_COLOR, fg=TEXT_COLOR).grid(row=1, column=0, sticky="w", pady=5)
        output_entry = tk.Entry(
            input_frame,
            textvariable=self.output_path_var,
            bg=SURFACE_COLOR,
            fg=TEXT_COLOR,
            insertbackground=TEXT_COLOR,
            relief="flat",
            bd=5,
            highlightbackground=BORDER_COLOR,
            font=("Arial", 10)
        )
        output_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        browse_output_btn = ModernButton(
            input_frame,
            text="Browse",
            bg=SURFACE_COLOR,
            hover_bg=BORDER_COLOR,
            command=self.browse_output
        )
        browse_output_btn.grid(row=1, column=2, pady=5)

        # Auto-detect installed Steam Workshop wallpapers
        detect_btn = ModernButton(
            input_frame,
            text="Detect Installed Wallpapers (Steam)",
            bg=ACCENT_COLOR,
            hover_bg="#0d9668",
            command=self.open_wallpaper_browser
        )
        detect_btn.grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))

        # Drag & drop hint / availability indicator
        dnd_text = (
            "Tip: you can also drag & drop a wallpaper file anywhere in this window"
            if HAS_DND else
            "Install tkinterdnd2 (pip install tkinterdnd2) to enable drag & drop"
        )
        tk.Label(
            input_frame, text=dnd_text, bg=BG_COLOR, fg=TEXT_MUTED, font=("Arial", 9, "italic")
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))

        # Options Frame
        options_frame = tk.Frame(main_frame, bg=BG_COLOR)
        options_frame.pack(fill="x", pady=(0, 15))
        
        # Checkboxes using standard Tkinter Checkbutton but styled
        cb_style = {"bg": BG_COLOR, "fg": TEXT_COLOR, "selectcolor": SURFACE_COLOR, "activebackground": BG_COLOR, "activeforeground": TEXT_COLOR, "font": ("Arial", 10)}
        
        self.cb_convert = tk.Checkbutton(
            options_frame,
            text="Convert .tex textures to PNG/JPG",
            variable=self.convert_tex_var,
            command=self.toggle_tex_options,
            **cb_style
        )
        self.cb_convert.pack(anchor="w", side="top", pady=2)
        
        self.cb_mips = tk.Checkbutton(
            options_frame,
            text="Extract all mipmap sizes (instead of just the largest texture resolution)",
            variable=self.extract_all_mips_var,
            **cb_style
        )
        self.cb_mips.pack(anchor="w", side="top", pady=2, padx=20)
        
        self.cb_cleanup = tk.Checkbutton(
            options_frame,
            text="Keep ONLY wallpaper images (delete shaders, scripts, and temp files)",
            variable=self.cleanup_non_images_var,
            **cb_style
        )
        self.cb_cleanup.pack(anchor="w", side="top", pady=2)
        
        # Pillow status indicator
        pillow_text = "Pillow: Installed (RAW texture decompression enabled)" if HAS_PILLOW else "Pillow: Not installed (RAW textures will extract as BMP)"
        pillow_color = ACCENT_COLOR if HAS_PILLOW else TEXT_MUTED
        lbl_pillow = tk.Label(options_frame, text=pillow_text, fg=pillow_color, bg=BG_COLOR, font=("Arial", 9, "italic"))
        lbl_pillow.pack(anchor="w", side="top", pady=(5, 0))
        
        # Action Button Frame
        action_frame = tk.Frame(main_frame, bg=BG_COLOR)
        action_frame.pack(side="bottom", fill="x", pady=(10, 0))
        
        self.btn_run = ModernButton(
            action_frame,
            text="Extract & Convert Assets",
            bg=PRIMARY_COLOR,
            hover_bg=PRIMARY_HOVER,
            command=self.start_extraction
        )
        self.btn_run.pack(side="right")

        # Progress Log Frame
        log_frame = tk.LabelFrame(
            main_frame,
            text=" Log Output ",
            font=("Arial", 10, "bold"),
            bg=BG_COLOR,
            fg=PRIMARY_COLOR,
            bd=1,
            relief="solid",
            padx=10,
            pady=10
        )
        log_frame.pack(fill="both", expand=True)
        
        # Scrollbar and text log widget
        self.log_text = tk.Text(
            log_frame,
            bg=LOG_BG,
            fg=TEXT_COLOR,
            relief="flat",
            bd=0,
            font=("Consolas", 9),
            state="disabled",
            insertbackground=TEXT_COLOR
        )
        self.log_text.pack(side="left", fill="both", expand=True)
        
        scrollbar = tk.Scrollbar(log_frame, command=self.log_text.yview, bg=BG_COLOR, elementborderwidth=0)
        scrollbar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
    def toggle_tex_options(self):
        if self.convert_tex_var.get():
            self.cb_mips.configure(state="normal")
        else:
            self.cb_mips.configure(state="disabled")
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

    def on_drop(self, event):
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
        
        # Clear logs
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        
        # Lock UI
        self.is_running = True
        self.btn_run.configure(state="disabled", bg=SURFACE_COLOR, text="Processing...")
        
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
                
            self.log_message("\n--- Extraction completed successfully! ---")
            # Update UI on completion
            self.after(0, lambda: messagebox.showinfo("Success", "Assets extracted successfully!"))
            
        except Exception as e:
            self.log_message(f"\n[ERROR] An error occurred: {e}")
            self.after(0, lambda: messagebox.showerror("Extraction Error", f"An error occurred: {e}"))
            
        finally:
            self.is_running = False
            self.after(0, lambda: self.btn_run.configure(state="normal", bg=PRIMARY_COLOR, text="Extract & Convert Assets"))


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
