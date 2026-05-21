"""Theme definitions for light/dark mode and color palettes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModeColors:
    bg_primary: str
    bg_secondary: str
    bg_input: str
    border: str
    border_subtle: str
    text_primary: str
    text_title: str
    text_bright: str
    text_subtle: str
    text_disabled: str
    selection_bg: str


@dataclass(frozen=True)
class ColorTheme:
    label: str
    download: str
    upload: str
    fill_r: int
    fill_g: int
    fill_b: int
    fill_a: int


DARK = ModeColors(
    bg_primary="#0d1117",
    bg_secondary="#161b22",
    bg_input="#21262d",
    border="#30363d",
    border_subtle="#21262d",
    text_primary="#e6edf3",
    text_title="#c9d1d9",
    text_bright="#f0f6fc",
    text_subtle="#7d8590",
    text_disabled="#6e7681",
    selection_bg="#1f6feb",
)

LIGHT = ModeColors(
    bg_primary="#ffffff",
    bg_secondary="#f6f8fa",
    bg_input="#eaeef2",
    border="#d0d7de",
    border_subtle="#d8dee4",
    text_primary="#1f2328",
    text_title="#424a53",
    text_bright="#0d1117",
    text_subtle="#656d76",
    text_disabled="#8c959f",
    selection_bg="#0969da",
)

MODES: dict[str, ModeColors] = {
    "dark": DARK,
    "light": LIGHT,
}

COLOR_THEMES: dict[str, ColorTheme] = {
    "ocean": ColorTheme("Ocean", "#4f9dff", "#22c55e", 79, 157, 255, 60),
    "sunset": ColorTheme("Sunset", "#f97316", "#f43f5e", 249, 115, 22, 60),
    "cyber": ColorTheme("Cyber", "#a855f7", "#06b6d4", 168, 85, 247, 60),
    "emerald": ColorTheme("Emerald", "#14b8a6", "#f59e0b", 20, 184, 166, 60),
}

DEFAULT_MODE = "dark"
DEFAULT_COLOR_THEME = "ocean"
