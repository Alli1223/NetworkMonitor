"""Centralised QSS theme generation for light and dark modes."""

from .theme import ColorTheme, ModeColors


def generate_qss(mode: ModeColors, colors: ColorTheme) -> str:
    return f"""
* {{
    color: {mode.text_primary};
    font-family: "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif;
    font-size: 12px;
}}

QMainWindow, QWidget#central, QDialog {{
    background-color: {mode.bg_primary};
}}

QFrame#card {{
    background-color: {mode.bg_secondary};
    border: 1px solid {mode.border_subtle};
    border-radius: 10px;
}}

QLabel#title {{
    font-size: 13px;
    font-weight: 600;
    color: {mode.text_title};
    letter-spacing: 0.3px;
}}

QLabel#bigMetric {{
    font-size: 22px;
    font-weight: 700;
    color: {mode.text_bright};
}}

QLabel#inlineMetric {{
    font-size: 13px;
    font-weight: 600;
    color: {mode.text_bright};
}}

QLabel#downAccent {{ color: {colors.download}; font-weight: 600; }}
QLabel#upAccent   {{ color: {colors.upload}; font-weight: 600; }}

QLabel#subtle {{
    color: {mode.text_subtle};
    font-size: 11px;
}}

QPushButton#iconBtn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 2px 6px;
    color: {mode.text_title};
    font-size: 16px;
    min-width: 26px;
    min-height: 26px;
}}
QPushButton#iconBtn:hover {{
    background: {mode.bg_input};
    border-color: {mode.border};
}}

QComboBox, QSpinBox, QPushButton, QCheckBox {{
    background-color: {mode.bg_input};
    border: 1px solid {mode.border};
    border-radius: 6px;
    padding: 4px 8px;
    color: {mode.text_primary};
    min-height: 22px;
}}

QComboBox:hover, QSpinBox:hover, QPushButton:hover {{
    border-color: {colors.download};
}}

QPushButton {{
    padding: 6px 14px;
}}

QPushButton#primary {{
    background-color: {mode.selection_bg};
    border-color: {mode.selection_bg};
    color: white;
    font-weight: 600;
}}

QPushButton#primary:hover {{
    background-color: {colors.download};
    border-color: {colors.download};
}}

QPushButton:disabled {{
    color: {mode.text_disabled};
    background-color: {mode.bg_secondary};
}}

QComboBox QAbstractItemView {{
    background-color: {mode.bg_secondary};
    border: 1px solid {mode.border};
    selection-background-color: {mode.selection_bg};
    color: {mode.text_primary};
}}

QMenu {{
    background-color: {mode.bg_secondary};
    border: 1px solid {mode.border};
    color: {mode.text_primary};
    padding: 4px;
}}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background-color: {mode.selection_bg}; }}

QStatusBar {{ color: {mode.text_subtle}; }}
QToolTip {{ background-color: {mode.bg_secondary}; color: {mode.text_primary}; border: 1px solid {mode.border}; }}

QCheckBox::indicator {{
    width: 14px; height: 14px;
    border: 1px solid {mode.border};
    border-radius: 3px;
    background: {mode.bg_input};
}}
QCheckBox::indicator:checked {{
    background: {mode.selection_bg};
    border-color: {mode.selection_bg};
}}

QSlider::groove:horizontal {{
    height: 6px;
    background: {mode.bg_input};
    border: 1px solid {mode.border};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {mode.selection_bg};
    border: none;
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: {colors.download};
}}
"""
