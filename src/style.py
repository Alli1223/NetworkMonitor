"""Centralised QSS for the dark, compact, modern look."""

DARK_QSS = """
* {
    color: #e6edf3;
    font-family: "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif;
    font-size: 12px;
}

QMainWindow, QWidget#central {
    background-color: #0d1117;
}

QFrame#card {
    background-color: #161b22;
    border: 1px solid #21262d;
    border-radius: 10px;
}

QLabel#title {
    font-size: 13px;
    font-weight: 600;
    color: #c9d1d9;
    letter-spacing: 0.3px;
}

QLabel#bigMetric {
    font-size: 22px;
    font-weight: 700;
    color: #f0f6fc;
}

QLabel#inlineMetric {
    font-size: 13px;
    font-weight: 600;
    color: #f0f6fc;
}

QLabel#downAccent { color: #4f9dff; font-weight: 600; }
QLabel#upAccent   { color: #22c55e; font-weight: 600; }

QLabel#subtle {
    color: #7d8590;
    font-size: 11px;
}

QPushButton#iconBtn {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 2px 6px;
    color: #c9d1d9;
    font-size: 16px;
    min-width: 26px;
    min-height: 26px;
}
QPushButton#iconBtn:hover {
    background: #21262d;
    border-color: #30363d;
}

QComboBox, QSpinBox, QPushButton, QCheckBox {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 4px 8px;
    color: #e6edf3;
    min-height: 22px;
}

QComboBox:hover, QSpinBox:hover, QPushButton:hover {
    border-color: #4f9dff;
}

QPushButton {
    padding: 6px 14px;
}

QPushButton#primary {
    background-color: #1f6feb;
    border-color: #1f6feb;
    color: white;
    font-weight: 600;
}

QPushButton#primary:hover {
    background-color: #388bfd;
    border-color: #388bfd;
}

QPushButton:disabled {
    color: #6e7681;
    background-color: #161b22;
}

QComboBox QAbstractItemView {
    background-color: #161b22;
    border: 1px solid #30363d;
    selection-background-color: #1f6feb;
    color: #e6edf3;
}

QMenu {
    background-color: #161b22;
    border: 1px solid #30363d;
    color: #e6edf3;
    padding: 4px;
}
QMenu::item { padding: 6px 18px; border-radius: 4px; }
QMenu::item:selected { background-color: #1f6feb; }

QStatusBar { color: #7d8590; }
QToolTip { background-color: #161b22; color: #e6edf3; border: 1px solid #30363d; }

QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #30363d;
    border-radius: 3px;
    background: #21262d;
}
QCheckBox::indicator:checked {
    background: #1f6feb;
    border-color: #1f6feb;
}
"""
