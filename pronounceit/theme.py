"""PronounceIt palette, adapted from Caleb's Dashboard settings at 989db03.

The owner authorized reuse of these UI components under this project's MIT
license. The add-ons remain independent; no Dashboard import is required.
"""
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
    sidebar_bg: str
    accent_soft: str


DARK = ThemeTokens(
    name="dark",
    window_bg="#0B1118",
    primary_text="#F1F5F9",
    secondary_text="#A9B4C0",
    muted_text="#87939F",
    card_bg="#151D26",
    card_border="#2B3948",
    advanced_bg="#1B2631",
    field_bg="#1B2631",
    field_border="#62768A",
    focus_border="#B1C9DD",
    accent="#9FBAD1",
    accent_hover="#B1C9DD",
    accent_pressed="#8AA7BF",
    accent_text="#0D131A",
    button_bg="#1B2631",
    button_hover_bg="#202C37",
    button_pressed_bg="#263B4D",
    button_border="#3A4C5E",
    button_text="#F1F5F9",
    disabled_text="#A9B4C0",
    disabled_bg="#202C37",
    success="#63D49A",
    warning="#E2BD57",
    danger="#EE7880",
    popup_shadow="rgba(0, 0, 0, 0.38)",
    sidebar_bg="#090F15",
    accent_soft="#263B4D",
)


LIGHT = ThemeTokens(
    name="light",
    window_bg="#F3F6F8",
    primary_text="#111827",
    secondary_text="#52606D",
    muted_text="#637180",
    card_bg="#FFFFFF",
    card_border="#C7D1DB",
    advanced_bg="#F7F9FB",
    field_bg="#F7F9FB",
    field_border="#7D8FA1",
    focus_border="#315D7A",
    accent="#315D7A",
    accent_hover="#506D87",
    accent_pressed="#445F78",
    accent_text="#FFFFFF",
    button_bg="#F7F9FB",
    button_hover_bg="#EDF1F4",
    button_pressed_bg="#DFEAF3",
    button_border="#AAB8C5",
    button_text="#111827",
    disabled_text="#52606D",
    disabled_bg="#EDF1F4",
    success="#2F7D50",
    warning="#8A6815",
    danger="#A6424A",
    popup_shadow="rgba(15, 23, 42, 0.20)",
    sidebar_bg="#E9EFF4",
    accent_soft="#DFEAF3",
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
        "border": tokens.card_border,
        "accent": tokens.accent,
        "accent-strong": tokens.focus_border,
        "accent-text": tokens.accent_text,
        "accent-hover": tokens.accent_hover,
        "accent-pressed": tokens.accent_pressed,
        "control-border": tokens.button_border,
        "disabled": tokens.disabled_text,
        "disabled-bg": tokens.disabled_bg,
        "hover": tokens.button_hover_bg,
        "shadow": tokens.popup_shadow,
        "status": tokens.success,
        "guidance": tokens.warning,
        "danger": tokens.danger,
    }


def dialog_qss(theme: str, object_name: str = "pronounceitOptions") -> str:
    t = theme_tokens(theme)
    r = f"QDialog#{object_name}"
    assets = (Path(__file__).parent / "assets").as_posix()
    return f"""
    {r} {{ background: {t.window_bg}; color: {t.primary_text}; }}
    {r} QWidget {{ background: transparent; color: {t.primary_text}; }}
    {r} QWidget[role="canvas"], {r} QWidget[role="page"] {{ background: {t.window_bg}; border: none; }}
    {r} QWidget[role="sidebar"] {{ background: {t.sidebar_bg}; border: none; border-right: 1px solid {t.card_border}; }}
    {r} QWidget[role="header"] {{ background: {t.window_bg}; border: none; border-bottom: 1px solid {t.card_border}; }}
    {r} QWidget[role="footer"] {{ background: {t.window_bg}; border: none; border-top: 1px solid {t.card_border}; }}
    {r} QWidget[role="card"] {{ background: {t.card_bg}; border: 1px solid {t.card_border}; border-radius: 10px; }}
    {r} QLabel {{ background: transparent; border: none; }}
    {r} QLabel[role="secondary"] {{ color: {t.muted_text}; }}
    {r} QLabel[role="error"] {{ color: {t.danger}; }}
    {r} QLabel[role="success"] {{ color: {t.success}; }}
    {r} QLabel[role="warning"] {{ color: {t.warning}; }}
    {r} QScrollArea {{ background: {t.window_bg}; border: none; }}
    {r} QScrollArea > QWidget > QWidget {{ background: {t.window_bg}; border: none; }}
    {r} QLineEdit, {r} QComboBox, {r} QSpinBox {{
        background: {t.field_bg}; color: {t.primary_text}; border: 1px solid {t.field_border};
        border-radius: 8px; min-height: 28px; padding: 2px 10px;
        selection-background-color: {t.accent}; selection-color: {t.accent_text};
    }}
    {r} QLineEdit:focus, {r} QComboBox:focus, {r} QSpinBox:focus {{ border: 3px solid {t.focus_border}; padding: 0px 8px; }}
    {r} QComboBox::drop-down {{ border: none; width: 28px; }}
    {r} QComboBox::down-arrow {{ image: url("{assets}/spin_down_{t.name}.svg"); width: 12px; height: 8px; }}
    {r} QComboBox QAbstractItemView {{ background: {t.card_bg}; color: {t.primary_text}; border: 1px solid {t.field_border}; selection-background-color: {t.accent_soft}; selection-color: {t.primary_text}; padding: 4px; }}
    {r} QComboBox QAbstractItemView::item {{ min-height: 30px; padding: 2px 8px; }}
    {r} QSpinBox {{ padding-right: 28px; }}
    {r} QSpinBox:focus {{ padding-right: 26px; }}
    {r} QSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 24px; border: none; }}
    {r} QSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 24px; border: none; }}
    {r} QSpinBox::up-arrow {{ image: url("{assets}/spin_up_{t.name}.svg"); width: 10px; height: 6px; }}
    {r} QSpinBox::down-arrow {{ image: url("{assets}/spin_down_{t.name}.svg"); width: 10px; height: 6px; }}
    {r} QPushButton {{ background: {t.button_bg}; color: {t.button_text}; border: 1px solid {t.button_border}; border-radius: 8px; min-height: 28px; padding: 2px 12px; font-weight: 600; }}
    {r} QPushButton:hover {{ background: {t.button_hover_bg}; }}
    {r} QPushButton:pressed {{ background: {t.button_pressed_bg}; }}
    {r} QPushButton:focus {{ border: 3px solid {t.focus_border}; padding: 0px 10px; }}
    {r} QPushButton[role="primary"] {{ background: {t.accent}; border-color: {t.accent}; color: {t.accent_text}; }}
    {r} QPushButton[role="primary"]:hover {{ background: {t.accent_hover}; }}
    {r} QPushButton[role="primary"]:pressed {{ background: {t.accent_pressed}; }}
    {r} QPushButton[role="quiet"], {r} QPushButton[role="disclosure"] {{ background: transparent; border-color: transparent; color: {t.secondary_text}; font-weight: 400; }}
    {r} QPushButton[role="quiet"]:hover, {r} QPushButton[role="disclosure"]:hover {{ background: {t.button_hover_bg}; }}
    {r} QPushButton[role="quiet"]:focus, {r} QPushButton[role="disclosure"]:focus {{ border-color: {t.focus_border}; }}
    {r} QPushButton[role="disclosure"] {{ text-align: left; }}
    {r} QPushButton[role="danger"] {{ color: {t.danger}; }}
    {r} QPushButton[role="switch"] {{ background: transparent; border: none; min-height: 34px; min-width: 44px; max-height: 34px; max-width: 44px; padding: 0; }}
    {r} QPushButton:disabled, {r} QLineEdit:disabled, {r} QComboBox:disabled, {r} QSpinBox:disabled {{ color: {t.disabled_text}; background: {t.disabled_bg}; border-color: {t.card_border}; }}
    {r} QListView {{ background: {t.card_bg}; color: {t.primary_text}; border: 1px solid {t.card_border}; border-radius: 8px; outline: none; }}
    {r} QListView::item {{ padding: 12px; border-bottom: 1px solid {t.card_border}; }}
    {r} QListView::item:selected {{ background: {t.accent_soft}; color: {t.primary_text}; }}
    {r} QListView:focus {{ border-color: {t.focus_border}; }}
    {r} QListWidget#pronounceitNav {{ background: transparent; border: none; padding: 0; }}
    {r} QListWidget#pronounceitNav::item {{ color: {t.secondary_text}; border: 1px solid transparent; border-left: 3px solid transparent; border-radius: 6px; padding: 0 8px; margin: 2px 0; min-height: 40px; }}
    {r} QListWidget#pronounceitNav::item:hover {{ background: {t.button_hover_bg}; }}
    {r} QListWidget#pronounceitNav::item:selected {{ color: {t.primary_text}; background: {t.accent_soft}; border-color: {t.card_border}; border-left-color: {t.accent}; }}
    {r} QListWidget#pronounceitNav::item:focus {{ border-color: {t.focus_border}; }}
    {r} QTextEdit {{ background: {t.card_bg}; color: {t.primary_text}; border: 1px solid {t.card_border}; border-radius: 8px; padding: 8px; selection-background-color: {t.accent}; selection-color: {t.accent_text}; }}
    {r} QProgressBar {{ background: {t.button_hover_bg}; border: none; border-radius: 3px; min-height: 6px; max-height: 6px; }}
    {r} QProgressBar::chunk {{ background: {t.accent}; border-radius: 3px; }}
    {r} QSlider::groove:horizontal {{ background: {t.field_border}; height: 4px; border-radius: 2px; }}
    {r} QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: 2px; }}
    {r} QSlider::handle:horizontal {{ background: {t.accent}; border: 2px solid {t.card_bg}; width: 16px; height: 16px; margin: -8px 0; border-radius: 10px; }}
    {r} QSlider::handle:horizontal:focus {{ border-color: {t.focus_border}; }}
    {r} QSlider::handle:horizontal:disabled {{ background: {t.disabled_text}; }}
    {r} QFrame[role="separator"] {{ background: {t.card_border}; max-height: 1px; border: none; }}
    {r} QScrollBar:vertical {{ background: {t.window_bg}; width: 10px; margin: 0; }}
    {r} QScrollBar::handle:vertical {{ background: {t.button_border}; min-height: 32px; border-radius: 5px; }}
    {r} QScrollBar::add-line:vertical, {r} QScrollBar::sub-line:vertical {{ height: 0; }}
    {r} QScrollBar::add-page:vertical, {r} QScrollBar::sub-page:vertical {{ background: transparent; }}
    """
