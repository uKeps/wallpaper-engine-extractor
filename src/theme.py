"""Colors, font and button shared by every window of the app."""

import tkinter as tk

# Colors
BG_COLOR = "#121214"
SURFACE_COLOR = "#1e1e24"
TEXT_COLOR = "#e2e2e7"
TEXT_MUTED = "#8e8e9f"
PRIMARY_COLOR = "#2563eb"  # white text on it is 5.17:1
PRIMARY_HOVER = "#1d4ed8"
ACCENT_COLOR = "#10b981"
BORDER_COLOR = "#2e2e38"
LOG_BG = "#0d0d0f"

# Tk falls back to the closest system font where Segoe UI isn't installed
FONT = "Segoe UI"


class ModernButton(tk.Button):
    """A flat Tkinter button with a hover color."""
    def __init__(self, master, **kwargs):
        hover_bg = kwargs.pop("hover_bg", PRIMARY_HOVER)
        normal_bg = kwargs.setdefault("bg", PRIMARY_COLOR)

        options = dict(
            fg="#ffffff",
            relief="flat",
            activebackground=hover_bg,
            activeforeground="#ffffff",
            disabledforeground=TEXT_MUTED,
            cursor="hand2",
            padx=14,
            pady=7,
            font=(FONT, 10),
            bd=0,
            # Keyboard focus ring, invisible until the button has focus
            highlightthickness=1,
            highlightcolor=TEXT_COLOR,
            highlightbackground=master["bg"],
        )
        super().__init__(master, **{**options, **kwargs})

        self.bind("<Enter>", lambda e: self["state"] != "disabled" and self.configure(bg=hover_bg))
        self.bind("<Leave>", lambda e: self["state"] != "disabled" and self.configure(bg=normal_bg))
