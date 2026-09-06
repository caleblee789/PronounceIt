from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ThemeTokens:
    name: str
    window_bg: str
    primary_text: str
    secondary_text: str
    muted_text: str
    card_bg: str
    card_border: str
    advanced_bg: str
    field_bg: str
    field_border: str
    focus_border: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_text: str
    button_bg: str
    button_hover_bg: str
    button_pressed_bg: str
    button_border: str
    button_text: str
    disabled_text: str
    disabled_bg: str
    success: str
    warning: str
    danger: str
    popup_shadow: str


DARK = ThemeTokens(
    name="dark",
    window_bg="#1c1f24",
    primary_text="#eef1f5",
    secondary_text="#c4ccd6",
    muted_text="#adb6c2",
    card_bg="#24282f",
    card_border="#68768a",
    advanced_bg="#20242b",
    field_bg="#20242b",
    field_border="#68768a",
    focus_border="#60a5fa",
    accent="#2563eb",
    accent_hover="#1d4ed8",
    accent_pressed="#1e40af",
    accent_text="#ffffff",
    button_bg="#24282f",
    button_hover_bg="#1f2937",
    button_pressed_bg="#20242b",
    button_border="#68768a",
    button_text="#eef1f5",
    disabled_text="#a8b3c2",
    disabled_bg="#30363f",
    success="#6fd28c",
    warning="#f4bd55",
    danger="#fca5a5",
    popup_shadow="rgba(0, 0, 0, 0.38)",
)


LIGHT = ThemeTokens(
    name="light",
    window_bg="#f5f6f8",
    primary_text="#1f2937",
    secondary_text="#3f4a59",
    muted_text="#667085",
    card_bg="#ffffff",
    card_border="#7c8798",
    advanced_bg="#f5f6f8",
    field_bg="#ffffff",
    field_border="#7c8798",
    focus_border="#5b8def",
    accent="#2563eb",
    accent_hover="#1d4ed8",
    accent_pressed="#1e40af",
    accent_text="#ffffff",
    button_bg="#ffffff",
    button_hover_bg="#eaf0fb",
    button_pressed_bg="#e7edf8",
    button_border="#7c8798",
    button_text="#1f2937",
    disabled_text="#596579",
    disabled_bg="#eef2f7",
    success="#15803d",
    warning="#a16207",
    danger="#b42318",
    popup_shadow="rgba(15, 23, 42, 0.20)",
)


def theme_tokens(theme: str) -> ThemeTokens:
    return DARK if str(theme).casefold() == "dark" else LIGHT


def web_theme_tokens(theme: str) -> dict[str, str]:
    tokens = theme_tokens(theme)
    return {
        "bg": tokens.card_bg,
        "surface": tokens.advanced_bg,
        "text": tokens.primary_text,
        "muted": tokens.muted_text,
        "border": "#39414c" if tokens.name == "dark" else "#d9dfe7",
        "accent": tokens.accent,
        "accent-strong": tokens.focus_border,
        "accent-text": tokens.accent_text,
        "hover": tokens.button_hover_bg,
        "shadow": tokens.popup_shadow,
        "status": tokens.success,
        "guidance": tokens.warning,
        "danger": tokens.danger,
    }


def dialog_qss(theme: str, object_name: str = "pronounceitOptions") -> str:
    t = theme_tokens(theme)
    r = f"QDialog#{object_name}"
    separator = "#39414c" if t.name == "dark" else "#d9dfe7"
    return f"""
    {r} {{ background: {t.window_bg}; color: {t.primary_text}; }}
    {r} QWidget {{ color: {t.primary_text}; font-size: 13px; }}
    {r} QLabel {{ background: transparent; }}
    {r} QLabel[role="title"] {{ font-size: 18px; font-weight: 600; }}
    {r} QLabel[role="section"] {{ font-weight: 600; }}
    {r} QLabel[role="secondary"] {{ color: {t.muted_text}; font-size: 12px; }}
    {r} QLabel[role="pronunciation"] {{ color: {t.primary_text}; font-size: 20px; font-weight: 600; }}
    {r} QLabel[role="error"] {{ color: {t.danger}; }}
    {r} QLabel[role="success"] {{ color: {t.success}; }}
    {r} QScrollArea, {r} QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    {r} QTabWidget::tab-bar {{ alignment: left; }}
    {r} QTabWidget::pane {{ border: none; border-top: 1px solid {separator}; }}
    {r} QTabBar::tab {{ padding: 10px 18px; background: transparent; border-bottom: 2px solid transparent; }}
    {r} QTabBar::tab:selected {{ color: {t.focus_border if t.name == "dark" else t.accent}; border-bottom-color: {t.accent}; font-weight: 600; }}
    {r} QTabBar::tab:hover {{ background: {t.button_hover_bg}; }}
    {r} QLineEdit, {r} QComboBox, {r} QSpinBox {{
        background: {t.field_bg}; color: {t.primary_text}; border: 1px solid {t.field_border};
        border-radius: 6px; min-height: 22px; padding: 4px 8px;
        selection-background-color: {t.accent}; selection-color: {t.accent_text};
    }}
    {r} QLineEdit:focus, {r} QComboBox:focus, {r} QSpinBox:focus {{ border-color: {t.focus_border}; }}
    {r} QComboBox QAbstractItemView {{ background: {t.field_bg}; color: {t.primary_text}; selection-background-color: {t.accent}; selection-color: white; }}
    {r} QSpinBox {{ padding-right: 24px; }}
    {r} QSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 22px; border: none; }}
    {r} QSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; border: none; }}
    {r} QSpinBox::up-arrow {{ image: url("{Path(__file__).parent.as_posix()}/assets/spin_up_{t.name}.svg"); width: 10px; height: 6px; }}
    {r} QSpinBox::down-arrow {{ image: url("{Path(__file__).parent.as_posix()}/assets/spin_down_{t.name}.svg"); width: 10px; height: 6px; }}
    {r} QCheckBox {{ spacing: 8px; padding: 3px 0; }}
    {r} QPushButton {{ background: {t.button_bg}; color: {t.button_text}; border: 1px solid {t.button_border}; border-radius: 6px; min-height: 22px; padding: 4px 12px; font-weight: 600; }}
    {r} QPushButton:hover {{ background: {t.button_hover_bg}; }}
    {r} QPushButton:pressed {{ background: {t.button_pressed_bg}; }}
    {r} QPushButton:focus {{ border-color: {t.focus_border}; }}
    {r} QPushButton[role="primary"] {{ background: {t.accent}; border-color: {t.accent}; color: white; }}
    {r} QPushButton[role="primary"]:hover {{ background: {t.accent_hover}; }}
    {r} QPushButton[role="quiet"] {{ background: transparent; border-color: transparent; color: {t.secondary_text}; font-weight: 400; }}
    {r} QPushButton[role="danger"] {{ color: {t.danger}; }}
    {r} QPushButton:disabled, {r} QLineEdit:disabled, {r} QComboBox:disabled, {r} QSpinBox:disabled {{ color: {t.disabled_text}; background: {t.disabled_bg}; border-color: {separator}; }}
    {r} QCheckBox:disabled {{ color: {t.disabled_text}; }}
    {r} QListView {{ background: {t.card_bg}; color: {t.primary_text}; border: 1px solid {separator}; border-radius: 6px; outline: none; }}
    {r} QListView::item {{ padding: 8px; border-bottom: 1px solid {separator}; }}
    {r} QListView::item:selected {{ background: {t.button_hover_bg}; color: {t.primary_text}; }}
    {r} QTextEdit {{ background: {t.card_bg}; color: {t.primary_text}; border: 1px solid {separator}; border-radius: 6px; padding: 8px; }}
    {r} QProgressBar {{ background: {t.field_bg}; border: 1px solid {separator}; border-radius: 4px; min-height: 16px; text-align: center; color: {t.primary_text}; }}
    {r} QProgressBar::chunk {{ background: {t.accent}; border-radius: 3px; }}
    {r} QFrame[role="separator"] {{ background: {separator}; max-height: 1px; border: none; }}
    """
