"""Dialog for browsing Wallpaper Engine wallpapers installed via Steam Workshop."""

import threading
import tkinter as tk

from src.steam_finder import find_installed_wallpapers

try:
    from PIL import Image, ImageTk
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

BG_COLOR = "#121214"
SURFACE_COLOR = "#1e1e24"
TEXT_COLOR = "#e2e2e7"
TEXT_MUTED = "#8e8e9f"
PRIMARY_COLOR = "#3b82f6"
PRIMARY_HOVER = "#2563eb"

THUMB_SIZE = (96, 54)


class WallpaperBrowserDialog(tk.Toplevel):
    """Modal dialog listing installed Steam Workshop wallpapers with preview thumbnails."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Detected Steam Workshop Wallpapers")
        self.geometry("560x520")
        self.configure(bg=BG_COLOR)
        self.transient(master)
        self.grab_set()

        self.selected_asset_path = None
        self._thumbnail_refs = []  # keep PhotoImage references alive

        self._build_widgets()
        self._start_scan()

    def _build_widgets(self):
        status_frame = tk.Frame(self, bg=BG_COLOR, padx=15, pady=10)
        status_frame.pack(fill="x")
        self.status_label = tk.Label(
            status_frame,
            text="Scanning Steam libraries for installed wallpapers...",
            bg=BG_COLOR, fg=TEXT_MUTED, font=("Arial", 10), wraplength=520, justify="left"
        )
        self.status_label.pack(anchor="w")

        list_container = tk.Frame(self, bg=BG_COLOR, padx=15)
        list_container.pack(fill="both", expand=True)

        canvas = tk.Canvas(list_container, bg=BG_COLOR, highlightthickness=0)
        scrollbar = tk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
        self.items_frame = tk.Frame(canvas, bg=BG_COLOR)

        self.items_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.items_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>"))

        footer = tk.Frame(self, bg=BG_COLOR, padx=15, pady=10)
        footer.pack(fill="x", side="bottom")
        tk.Button(
            footer, text="Cancel", command=self.destroy,
            bg=SURFACE_COLOR, fg=TEXT_COLOR, relief="flat", padx=12, pady=6, cursor="hand2"
        ).pack(side="right")

    def _start_scan(self):
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        try:
            wallpapers = find_installed_wallpapers()
        except Exception as e:
            self.after(0, lambda: self.status_label.configure(text=f"Error scanning Steam libraries: {e}"))
            return
        self.after(0, lambda: self._populate(wallpapers))

    def _populate(self, wallpapers):
        if not wallpapers:
            self.status_label.configure(
                text="No Wallpaper Engine workshop items found. Make sure Steam and Wallpaper "
                     "Engine are installed and you have subscribed to at least one wallpaper."
            )
            return

        extractable_count = sum(1 for w in wallpapers if w.asset_path is not None)
        self.status_label.configure(
            text=f"Found {len(wallpapers)} wallpaper(s), {extractable_count} with an extractable asset."
        )
        if not HAS_PILLOW:
            tk.Label(
                self.items_frame,
                text="Install Pillow (pip install pillow) to see preview thumbnails.",
                bg=BG_COLOR, fg=TEXT_MUTED, font=("Arial", 9, "italic")
            ).pack(anchor="w", pady=(0, 10))

        for wp in wallpapers:
            self._add_row(wp)

    def _add_row(self, wp):
        extractable = wp.asset_path is not None

        row = tk.Frame(self.items_frame, bg=SURFACE_COLOR, padx=10, pady=8)
        row.pack(fill="x", pady=4)

        thumb_label = tk.Label(row, bg=SURFACE_COLOR, width=12, height=4, fg=TEXT_MUTED, font=("Arial", 8))
        thumb_label.pack(side="left", padx=(0, 12))
        self._load_thumbnail(thumb_label, wp)

        info_frame = tk.Frame(row, bg=SURFACE_COLOR)
        info_frame.pack(side="left", fill="both", expand=True)

        tk.Label(
            info_frame, text=wp.title, bg=SURFACE_COLOR, fg=TEXT_COLOR,
            font=("Arial", 10, "bold"), anchor="w", justify="left", wraplength=300
        ).pack(anchor="w")

        subtitle = f"ID: {wp.workshop_id}  |  Type: {wp.wp_type}"
        if not extractable:
            subtitle += "  |  No extractable asset found"
        tk.Label(info_frame, text=subtitle, bg=SURFACE_COLOR, fg=TEXT_MUTED, font=("Arial", 8)).pack(anchor="w")

        tk.Button(
            row, text="Select", bg=PRIMARY_COLOR, fg=TEXT_COLOR, relief="flat", cursor="hand2",
            padx=12, pady=4, state=("normal" if extractable else "disabled"),
            command=lambda w=wp: self._select(w)
        ).pack(side="right", padx=(10, 0))

    def _load_thumbnail(self, label, wp):
        if HAS_PILLOW and wp.preview_path is not None:
            try:
                image = Image.open(wp.preview_path)
                image.thumbnail(THUMB_SIZE)
                photo = ImageTk.PhotoImage(image)
                self._thumbnail_refs.append(photo)
                label.configure(image=photo, text="")
                return
            except Exception:
                pass
        label.configure(text="No\nPreview")

    def _select(self, wp):
        self.selected_asset_path = wp.asset_path
        self.destroy()
