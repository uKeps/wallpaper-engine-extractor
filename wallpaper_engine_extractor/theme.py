"""Colors, fonts, scaling and the drawn shapes shared by every window of the app.

Neutral zinc palette, one solid primary color, rounded corners. Shapes are drawn with Pillow
(antialiased on Windows, where Tk's own canvas isn't) and fall back to flat rectangles without it.
"""

import sys
import tkinter as tk
from tkinter import font as tkfont

try:
    from PIL import Image, ImageDraw, ImageTk
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


def _windows_prefers_light() -> bool:
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        ) as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 1
    except (ImportError, OSError):
        return False


# Follow the Windows app theme; dark everywhere else
DARK = not _windows_prefers_light()

if DARK:
    BG_COLOR = "#09090b"
    SURFACE_COLOR = "#18181b"
    TEXT_COLOR = "#fafafa"
    TEXT_MUTED = "#a1a1aa"
    BORDER_COLOR = "#27272a"
    STRONG_BORDER = "#3f3f46"
    PRIMARY_COLOR = "#fafafa"
    PRIMARY_TEXT = "#18181b"
    PRIMARY_HOVER = "#d4d4d8"
    SECONDARY_HOVER = "#27272a"
    ACCENT_COLOR = "#4ade80"
    WARNING_COLOR = "#fbbf24"
    ERROR_COLOR = "#f87171"
    LOG_BG = "#111113"
else:
    BG_COLOR = "#ffffff"
    SURFACE_COLOR = "#f4f4f5"
    TEXT_COLOR = "#09090b"
    TEXT_MUTED = "#71717a"
    BORDER_COLOR = "#e4e4e7"
    STRONG_BORDER = "#d4d4d8"
    PRIMARY_COLOR = "#18181b"
    PRIMARY_TEXT = "#fafafa"
    PRIMARY_HOVER = "#3f3f46"
    SECONDARY_HOVER = "#f4f4f5"
    ACCENT_COLOR = "#16a34a"
    WARNING_COLOR = "#b45309"
    ERROR_COLOR = "#dc2626"
    LOG_BG = "#fafafa"

# Tk falls back to the closest system font where Segoe UI isn't installed
FONT = "Segoe UI"
MONO_FONT = "Consolas"


def font(size: int, weight: str = "normal") -> tuple:
    """A font tuple; "semibold" uses Segoe UI Semibold on Windows and bold elsewhere."""
    if weight == "semibold":
        return ("Segoe UI Semibold", size) if sys.platform == "win32" else (FONT, size, "bold")
    return (FONT, size, weight) if weight != "normal" else (FONT, size)


# Pixel sizes are written for 96 DPI and scaled with px() once the window knows its DPI
SCALE = 1.0


def enable_dpi_awareness():
    """Render crisply on scaled Windows displays instead of being stretched by Windows. Call before Tk()."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def init_scale(root: tk.Misc):
    global SCALE
    SCALE = max(1.0, root.winfo_fpixels("1i") / 96)


def px(n: float) -> int:
    return round(n * SCALE)


def style_title_bar(window: tk.Misc):
    """Dark title bar on Windows 10/11 when the app is dark, so it doesn't sit under a white bar."""
    if sys.platform != "win32" or not DARK:
        return
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE, and its pre-20H1 number
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), 4) == 0:
                break
    except (AttributeError, OSError):
        pass


def rounded(w: int, h: int, radius: int, fill: str | None, outline: str | None = None,
            dash: bool = False, check: str | None = None):
    """A rounded rectangle as a Tk image (transparent corners), or None without Pillow.

    Sizes are already scaled. dash breaks the straight edges of the outline into dashes;
    check draws a check mark in that color.
    """
    if not HAS_PILLOW:
        return None
    k = 4  # drawn 4x larger, then shrunk: antialiased edges
    W, H, R = w * k, h * k, radius * k
    image = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    line = max(k, round(SCALE * k))
    draw.rounded_rectangle((0, 0, W - 1, H - 1), R, fill=fill, outline=outline, width=line if outline else 0)
    if dash and outline:
        gap = fill or (0, 0, 0, 0)
        step = px(6) * k
        for x in range(R + step // 2, W - R - step // 2, step * 2):
            draw.rectangle((x, 0, x + step - 1, line), fill=gap)
            draw.rectangle((x, H - 1 - line, x + step - 1, H - 1), fill=gap)
        for y in range(R + step // 2, H - R - step // 2, step * 2):
            draw.rectangle((0, y, line, y + step - 1), fill=gap)
            draw.rectangle((W - 1 - line, y, W - 1, y + step - 1), fill=gap)
    if check:
        points = [(0.27 * W, 0.52 * H), (0.43 * W, 0.68 * H), (0.74 * W, 0.34 * H)]
        draw.line(points, fill=check, width=round(0.12 * W), joint="curve")
    return ImageTk.PhotoImage(image.resize((w, h), Image.LANCZOS))


def upload_icon(size: int, color: str, bg: str, border: str):
    """An arrow over a tray in a rounded square, or None without Pillow."""
    if not HAS_PILLOW:
        return None
    k = 4
    S = size * k
    image = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, S - 1, S - 1), S // 4, fill=bg, outline=border, width=max(k, round(SCALE * k)))
    width = round(S * 0.055)
    c = S / 2
    draw.line([(c, S * 0.30), (c, S * 0.60)], fill=color, width=width)
    draw.line([(c - S * 0.13, S * 0.42), (c, S * 0.29), (c + S * 0.13, S * 0.42)], fill=color, width=width,
              joint="curve")
    draw.line([(S * 0.30, S * 0.60), (S * 0.30, S * 0.71), (S * 0.70, S * 0.71), (S * 0.70, S * 0.60)],
              fill=color, width=width, joint="curve")
    return ImageTk.PhotoImage(image.resize((size, size), Image.LANCZOS))


def rounded_photo(image, radius: int, bg: str):
    """Round the corners of a Pillow image (already sized) for display on bg."""
    k = 4
    mask = Image.new("L", (image.width * k, image.height * k), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, mask.width - 1, mask.height - 1), radius * k, fill=255)
    out = Image.new("RGB", image.size, bg)
    out.paste(image.convert("RGB"), (0, 0), mask.resize(image.size, Image.LANCZOS))
    return ImageTk.PhotoImage(out)


# (fill, text, outline, hover fill) per button variant
VARIANTS = {
    "primary": (PRIMARY_COLOR, PRIMARY_TEXT, None, PRIMARY_HOVER),
    "secondary": (BG_COLOR, TEXT_COLOR, STRONG_BORDER, SECONDARY_HOVER),
    "ghost": (None, TEXT_MUTED, None, SECONDARY_HOVER),
    "disabled": (SURFACE_COLOR, TEXT_MUTED, None, SURFACE_COLOR),
}


class ModernButton(tk.Label):
    """A rounded button: variant "primary", "secondary" (outlined), "ghost" or "disabled".

    A Label with the shape as its image and the text on top, so it can be restyled with restyle().
    """

    def __init__(self, master, text: str, command, variant: str = "primary", size: int = 10,
                 padx: int = 14, pady: int = 7):
        bg = master["bg"]
        super().__init__(
            master, bg=bg, bd=0, compound="center", font=font(size, "semibold"), takefocus=1,
            highlightthickness=1, highlightcolor=TEXT_MUTED, highlightbackground=bg,
        )
        self.command, self.pad = command, (px(padx), px(pady))
        self.text, self.variant, self.hover = text, variant, False
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._click)
        self.bind("<Return>", self._click)
        self.bind("<space>", self._click)
        self.restyle()

    def restyle(self, text: str | None = None, variant: str | None = None):
        self.text = self.text if text is None else text
        if variant and variant != self.variant:
            # a modal dialog can swallow <Leave>, so don't carry the hover look into a new role
            self.variant, self.hover = variant, False
        fill, fg, outline, hover = VARIANTS[self.variant]
        fill = hover if self.hover else fill
        f = tkfont.Font(font=self["font"])
        w = f.measure(self.text) + 2 * self.pad[0]
        h = f.metrics("linespace") + 2 * self.pad[1]
        self._image = rounded(w, h, px(8), fill, outline)
        # Disabled is only a look: Tk's disabled state stipples the text on X11
        cursor = "" if self.variant == "disabled" else "hand2"
        if self._image:
            self.configure(image=self._image, text=self.text, fg=fg, padx=0, pady=0, cursor=cursor)
        else:
            self.configure(image="", text=self.text, fg=fg, bg=fill or self.master["bg"],
                           padx=self.pad[0], pady=self.pad[1], cursor=cursor)

    def _set_hover(self, hover: bool):
        if self.variant != "disabled" and hover != self.hover:
            self.hover = hover
            self.restyle()

    def _click(self, event=None):
        released_outside = event is not None and event.type == tk.EventType.ButtonRelease and \
            self.winfo_containing(event.x_root, event.y_root) is not self
        if self.variant != "disabled" and not released_outside:
            self.command()
        return "break"  # Enter on a focused button must not also reach the window's Enter binding


class Card(tk.Canvas):
    """A fixed-size rounded panel; widgets go in .inner, placed at its center or left edge."""

    def __init__(self, master, width: int, height: int, fill: str, outline: str | None = None,
                 dash: bool = False, radius: int = 12, anchor: str = "center"):
        super().__init__(master, width=px(width), height=px(height), bg=master["bg"], highlightthickness=0, bd=0)
        self.size, self.radius, self.dash = (px(width), px(height)), px(radius), dash
        self.inner = tk.Frame(self, bg=fill)
        if anchor == "center":
            self.create_window(self.size[0] / 2, self.size[1] / 2, window=self.inner)
        else:  # full width, so widgets can sit at either end
            self.create_window(px(14), self.size[1] / 2, window=self.inner, anchor="w", width=self.size[0] - px(28))
        self.paint(fill, outline)

    def paint(self, fill: str, outline: str | None):
        self.delete("shape")
        self._image = rounded(*self.size, self.radius, fill, outline, self.dash)
        if self._image:
            self.create_image(0, 0, image=self._image, anchor="nw", tags="shape")
        else:
            self.create_rectangle(1, 1, self.size[0] - 2, self.size[1] - 2, fill=fill, outline=outline or fill,
                                  dash=(4, 4) if self.dash else None, tags="shape")
        self.tag_lower("shape")
