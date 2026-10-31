"""Dialog for browsing Wallpaper Engine wallpapers installed via Steam Workshop."""

import threading
import tkinter as tk
from tkinter import ttk

from wallpaper_engine_extractor.steam_finder import find_installed_wallpapers
from wallpaper_engine_extractor.theme import (
    BG_COLOR, BORDER_COLOR, FONT, PRIMARY_COLOR, SURFACE_COLOR, TEXT_COLOR, TEXT_MUTED, ModernButton,
)

try:
    from PIL import Image, ImageOps, ImageTk
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

THUMB_SIZE = (96, 54)


def _load_thumbnail(wp):
    """Decode a preview off the UI thread; the Tk image is made later, on the main thread."""
    if not HAS_PILLOW or wp.preview_path is None:
        return None
    try:
        with Image.open(wp.preview_path) as image:
            return ImageOps.fit(image.convert("RGB"), THUMB_SIZE)
    except Exception:
        return None


class WallpaperBrowserDialog(tk.Toplevel):
    """Modal dialog listing installed Steam Workshop wallpapers with preview thumbnails."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Find in Steam")
        self.geometry(f"600x560+{master.winfo_rootx() + 40}+{master.winfo_rooty() + 40}")
        self.minsize(460, 360)
        self.configure(bg=BG_COLOR)
        self.transient(master)
        self.grab_set()
        self.focus_set()

        self.selected_asset_path = None
        self.selected_title = None
        self._rows = []  # (frame, wallpaper, PhotoImage kept alive, widgets to repaint)
        self._current = None

        self._build_widgets()
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self._current and self._select(self._current[1]))
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _build_widgets(self):
        main = tk.Frame(self, bg=BG_COLOR, padx=28, pady=24)
        main.pack(fill="both", expand=True)

        tk.Label(main, text="Find in Steam", font=(FONT, 16, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="w")
        self.status_label = tk.Label(
            main, text="Wallpapers you are subscribed to on the Steam Workshop.",
            font=(FONT, 10), bg=BG_COLOR, fg=TEXT_MUTED
        )
        self.status_label.pack(anchor="w", pady=(2, 18))

        # Packed before the list so it keeps its space when the window shrinks
        footer = tk.Frame(main, bg=BG_COLOR)
        footer.pack(side="bottom", fill="x", pady=(16, 0))
        self.btn_select = ModernButton(footer, text="Select", command=lambda: self._select(self._current[1]))
        self.btn_select.configure(state="disabled", bg=SURFACE_COLOR)
        self.btn_select.pack(side="right")
        ModernButton(
            footer, text="Cancel", bg=BORDER_COLOR, hover_bg="#3a3a46", command=self.destroy
        ).pack(side="right", padx=(0, 8))
        if not HAS_PILLOW:
            tk.Label(
                footer, text="Install Pillow to see previews", font=(FONT, 9), bg=BG_COLOR, fg=TEXT_MUTED
            ).pack(side="left")

        # Search box: shown once there is something to search
        self.search_box = tk.Frame(
            main, bg=SURFACE_COLOR, padx=12, pady=7, highlightthickness=1, highlightbackground=BORDER_COLOR
        )
        tk.Label(self.search_box, text="Search", font=(FONT, 10), bg=SURFACE_COLOR, fg=TEXT_MUTED).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filter())
        self.search_entry = tk.Entry(
            self.search_box, textvariable=self.search_var, font=(FONT, 10), bg=SURFACE_COLOR, fg=TEXT_COLOR,
            insertbackground=TEXT_COLOR, relief="flat", bd=0, highlightthickness=0
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(10, 0))

        self.list_frame = tk.Frame(main, bg=BG_COLOR)
        self.list_frame.pack(fill="both", expand=True)
        self.canvas = canvas = tk.Canvas(self.list_frame, bg=BG_COLOR, highlightthickness=0)

        # A slim scrollbar: just the thumb, no arrows
        style = ttk.Style(self)
        style.layout("Slim.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {
            "sticky": "ns", "children": [("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]
        })])
        style.configure(
            "Slim.Vertical.TScrollbar", troughcolor=BG_COLOR, background=BORDER_COLOR, bordercolor=BG_COLOR,
            lightcolor=BORDER_COLOR, darkcolor=BORDER_COLOR, gripcount=0, arrowsize=8
        )
        style.map("Slim.Vertical.TScrollbar", background=[("active", "#3a3a46")])
        scrollbar = ttk.Scrollbar(
            self.list_frame, orient="vertical", command=canvas.yview, style="Slim.Vertical.TScrollbar"
        )

        self.items_frame = tk.Frame(canvas, bg=BG_COLOR)
        window = canvas.create_window((0, 0), window=self.items_frame, anchor="nw")
        self.items_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        canvas.pack(side="left", fill="both", expand=True)

        def on_scroll(first, last):
            scrollbar.set(first, last)
            if float(first) <= 0 and float(last) >= 1:
                scrollbar.pack_forget()  # everything fits
            else:
                scrollbar.pack(side="right", fill="y", padx=(8, 0))
        canvas.configure(yscrollcommand=on_scroll)

        # Windows and macOS report the wheel as <MouseWheel>, X11 as buttons 4 and 5
        def scroll(units):
            if canvas.yview() != (0.0, 1.0):
                canvas.yview_scroll(units, "units")
        self.bind("<MouseWheel>", lambda e: scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1)))
        self.bind("<Button-4>", lambda e: scroll(-1))
        self.bind("<Button-5>", lambda e: scroll(1))

        # Centered message for the scanning, empty and no-match states
        self.message = tk.Frame(self.items_frame, bg=BG_COLOR)
        self.message_title = tk.Label(self.message, font=(FONT, 11, "bold"), bg=BG_COLOR, fg=TEXT_COLOR)
        self.message_title.pack()
        self.message_detail = tk.Label(
            self.message, font=(FONT, 10), bg=BG_COLOR, fg=TEXT_MUTED, wraplength=380, justify="center"
        )
        self.message_detail.pack(pady=(4, 0))
        self._show_message("Scanning Steam libraries...")

    def _show_message(self, title, detail=""):
        if not self.winfo_exists():
            return
        self.message_title.configure(text=title)
        self.message_detail.configure(text=detail)
        self.message.pack(pady=(70, 0))

    def _scan_worker(self):
        try:
            wallpapers = sorted(
                find_installed_wallpapers(), key=lambda w: (w.asset_path is None, w.title.casefold())
            )
            thumbnails = [_load_thumbnail(wp) for wp in wallpapers]
        except Exception as e:
            error = str(e)
            self.after(0, lambda: self._show_message("Couldn't scan Steam libraries", error))
            return
        self.after(0, lambda: self._populate(wallpapers, thumbnails))

    def _populate(self, wallpapers, thumbnails):
        if not self.winfo_exists():
            return
        if not wallpapers:
            self._show_message(
                "No wallpapers found",
                "Subscribe to a wallpaper on the Steam Workshop and let Wallpaper Engine download it, "
                "then try again. You can still pick a scene.pkg or video with Browse files."
            )
            return

        extractable = sum(wp.asset_path is not None for wp in wallpapers)
        self.status_label.configure(text=f"{len(wallpapers)} installed, {extractable} can be extracted.")
        self.message.pack_forget()
        for wp, thumbnail in zip(wallpapers, thumbnails):
            self._add_row(wp, thumbnail)
        self.search_box.pack(fill="x", pady=(0, 12), before=self.list_frame)
        self.search_entry.focus_set()

    def _add_row(self, wp, thumbnail):
        extractable = wp.asset_path is not None

        row = tk.Frame(
            self.items_frame, bg=BG_COLOR, padx=8, pady=8, highlightthickness=1, highlightbackground=BG_COLOR
        )
        row.pack(fill="x")

        thumb_box = tk.Frame(row, width=THUMB_SIZE[0], height=THUMB_SIZE[1], bg=BORDER_COLOR)
        thumb_box.pack_propagate(False)
        thumb_box.pack(side="left")
        photo = ImageTk.PhotoImage(thumbnail) if thumbnail else None
        thumb = tk.Label(
            thumb_box, image=photo, text="" if photo else "No preview",
            font=(FONT, 8), bg=BORDER_COLOR, fg=TEXT_MUTED, bd=0
        )
        thumb.pack(fill="both", expand=True)

        info = tk.Frame(row, bg=BG_COLOR)
        info.pack(side="left", fill="x", expand=True, padx=(14, 0))
        title = tk.Label(
            info, text=wp.title, font=(FONT, 10, "bold"), bg=BG_COLOR,
            fg=TEXT_COLOR if extractable else TEXT_MUTED, anchor="w", justify="left", wraplength=380
        )
        title.pack(anchor="w")

        if extractable:
            detail = f"{wp.wp_type.capitalize()} · {wp.workshop_id}"
        elif wp.wp_type == "web":
            detail = "Web wallpaper, nothing to extract"
        else:
            detail = "No image or video file found"
        subtitle = tk.Label(info, text=detail, font=(FONT, 9), bg=BG_COLOR, fg=TEXT_MUTED, anchor="w")
        subtitle.pack(anchor="w", pady=(2, 0))

        entry = (row, wp, photo, (row, info, title, subtitle))
        self._rows.append(entry)
        if not extractable:
            return
        for widget in (row, thumb, info, title, subtitle):
            widget.configure(cursor="hand2")
            widget.bind("<Enter>", lambda e: self._paint(entry, hover=True))
            widget.bind("<Leave>", lambda e: self._paint(entry, hover=False))
            widget.bind("<Button-1>", lambda e: self._highlight(entry))
            widget.bind("<Double-Button-1>", lambda e: self._select(wp))

    def _paint(self, entry, hover):
        current = entry is self._current
        bg = SURFACE_COLOR if hover or current else BG_COLOR
        for widget in entry[3]:
            widget.configure(bg=bg)
        entry[0].configure(highlightbackground=PRIMARY_COLOR if current else bg)

    def _highlight(self, entry):
        previous, self._current = self._current, entry
        if previous:
            self._paint(previous, hover=False)
        self._paint(entry, hover=True)
        self.btn_select.configure(state="normal", bg=PRIMARY_COLOR)

    def _apply_filter(self):
        query = self.search_var.get().strip().casefold()
        matches = [e for e in self._rows if query in f"{e[1].title} {e[1].workshop_id}".casefold()]
        for entry in self._rows:
            entry[0].pack_forget()
        for entry in matches:
            entry[0].pack(fill="x")

        if self._current not in matches and self._current:
            previous, self._current = self._current, None
            self._paint(previous, hover=False)
            self.btn_select.configure(state="disabled", bg=SURFACE_COLOR)

        if matches:
            self.message.pack_forget()
        else:
            self._show_message("No matches", f'Nothing installed matches "{query}".')
        self.canvas.yview_moveto(0)

    def _select(self, wp):
        self.selected_asset_path = wp.asset_path
        self.selected_title = wp.title
        self.destroy()
