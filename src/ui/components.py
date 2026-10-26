"""Minimalist UI theme constants and animated components for CustomTkinter."""
from typing import Optional, Tuple
import customtkinter as ctk

# Minimalist Dark Palette (Obsidian / Ice Cyan / Muted Slate)
THEME = {
    "bg_main": "#0D0E12",        # Main canvas background
    "card_bg": "#15171E",        # Surface cards
    "card_bg_hover": "#1A1D26",  # Slightly lighter on hover
    "card_border": "#222631",    # Subtle borders
    "card_border_glow": "#38BDF8",# Accent border on hover
    "input_bg": "#101217",       # Input fields background
    "input_border": "#252A36",   # Input border
    "text_primary": "#F1F5F9",   # Crisp white-slate text
    "text_secondary": "#94A3B8", # Muted slate labels
    "text_accent": "#38BDF8",    # Sky blue / Ice Cyan accent
    "accent_primary": "#38BDF8", # Primary action accent
    "accent_hover": "#0284C7",   # Darker accent for hover
    "btn_neutral_bg": "#1C202A", # Neutral button background
    "btn_neutral_hover": "#262C3A", # Neutral button hover
    "btn_neutral_border": "#2D3444",
    "danger_bg": "#1E1419",
    "danger_border": "#4C1D24",
    "danger_hover": "#E11D48",
    "success_dot": "#34D399",    # Active green indicator
}


def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """Convert hex string (e.g. #1E222A) to RGB tuple."""
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb: Tuple[float, float, float]) -> str:
    """Convert RGB tuple to hex string."""
    r = max(0, min(255, int(round(rgb[0]))))
    g = max(0, min(255, int(round(rgb[1]))))
    b = max(0, min(255, int(round(rgb[2]))))
    return f"#{r:02x}{g:02x}{b:02x}"


def lerp_color(color_a: str, color_b: str, t: float) -> str:
    """Linearly interpolate between color_a and color_b by factor t in [0, 1]."""
    ra, ga, ba = hex_to_rgb(color_a)
    rb, gb, bb = hex_to_rgb(color_b)
    return rgb_to_hex((ra + (rb - ra) * t, ga + (gb - ga) * t, ba + (bb - ba) * t))


class AnimatedButton(ctk.CTkButton):
    """
    A minimalist CustomTkinter button with smooth 60fps color transition animations
    on hover and click press/release bounce.
    """

    def __init__(
        self,
        master,
        normal_bg: str = THEME["btn_neutral_bg"],
        hover_bg: str = THEME["btn_neutral_hover"],
        press_bg: Optional[str] = None,
        normal_border: str = THEME["btn_neutral_border"],
        hover_border: Optional[str] = None,
        border_width: int = 1,
        corner_radius: int = 8,
        transition_steps: int = 6,
        step_delay_ms: int = 14,
        **kwargs
    ):
        self.normal_bg = normal_bg
        self.hover_bg = hover_bg
        self.press_bg = press_bg or lerp_color(normal_bg, "#000000", 0.35)
        self.normal_border = normal_border
        self.hover_border = hover_border or normal_border
        self.transition_steps = transition_steps
        self.step_delay_ms = step_delay_ms

        self._anim_job = None
        self._current_step = 0
        self._target_step = 0

        # We disable CTk's built-in instantaneous hover by matching colors or handling ourselves
        super().__init__(
            master,
            fg_color=self.normal_bg,
            hover_color=self.hover_bg,
            border_color=self.normal_border,
            border_width=border_width,
            corner_radius=corner_radius,
            **kwargs
        )

        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")

    def set_colors(self, normal_bg: str, hover_bg: str, normal_border: Optional[str] = None, hover_border: Optional[str] = None):
        """Update colors dynamically (e.g. active states)."""
        self.normal_bg = normal_bg
        self.hover_bg = hover_bg
        if normal_border:
            self.normal_border = normal_border
        if hover_border:
            self.hover_border = hover_border
        self.configure(fg_color=self.normal_bg, border_color=self.normal_border)

    def _animate(self):
        if self._current_step == self._target_step:
            self._anim_job = None
            return

        # Advance step toward target
        if self._current_step < self._target_step:
            self._current_step += 1
        else:
            self._current_step -= 1

        t = self._current_step / float(self.transition_steps)

        # Interpolate background and border colors
        cur_bg = lerp_color(self.normal_bg, self.hover_bg, t)
        cur_border = lerp_color(self.normal_border, self.hover_border, t)

        try:
            self.configure(fg_color=cur_bg, border_color=cur_border)
            self._anim_job = self.after(self.step_delay_ms, self._animate)
        except Exception:
            self._anim_job = None

    def _on_enter(self, _):
        self._target_step = self.transition_steps
        if self._anim_job is None:
            self._animate()

    def _on_leave(self, _):
        self._target_step = 0
        if self._anim_job is None:
            self._animate()

    def _on_press(self, _):
        if self._anim_job:
            self.after_cancel(self._anim_job)
            self._anim_job = None
        self.configure(fg_color=self.press_bg)

    def _on_release(self, _):
        self._target_step = self.transition_steps
        self._animate()
