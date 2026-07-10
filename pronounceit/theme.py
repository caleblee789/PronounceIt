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
    window_bg="#0b1220",
    primary_text="#e5e7eb",
    secondary_text="#cbd5e1",
    muted_text="#9ca3af",
    card_bg="#111827",
    card_border="#5b6b82",
    advanced_bg="#0f172a",
    field_bg="#0f172a",
    field_border="#5b6b82",
    focus_border="#60a5fa",
    accent="#2563eb",
    accent_hover="#1d4ed8",
    accent_pressed="#1e40af",
    accent_text="#ffffff",
    button_bg="#111827",
    button_hover_bg="#1f2937",
    button_pressed_bg="#0f172a",
    button_border="#5b6b82",
    button_text="#e5e7eb",
    disabled_text="#94a3b8",
    disabled_bg="#182234",
    success="#6fd28c",
    warning="#f4bd55",
    danger="#fca5a5",
    popup_shadow="rgba(0, 0, 0, 0.38)",
)


LIGHT = ThemeTokens(
    name="light",
    window_bg="#f7f9fc",
    primary_text="#1f2937",
    secondary_text="#3f4a59",
    muted_text="#667085",
    card_bg="#ffffff",
    card_border="#7c8ba1",
    advanced_bg="#f7f9fb",
    field_bg="#ffffff",
    field_border="#7c8ba1",
    focus_border="#5b8def",
    accent="#2563eb",
    accent_hover="#1d4ed8",
    accent_pressed="#1e40af",
    accent_text="#ffffff",
    button_bg="#f5f7fb",
    button_hover_bg="#eef2ff",
    button_pressed_bg="#e7edf8",
    button_border="#7c8ba1",
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
        "border": tokens.card_border,
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
    root = f"QDialog#{object_name}"
    asset_dir = Path(__file__).resolve().parent / "assets"
    up_arrow = (asset_dir / f"spin_up_{t.name}.svg").as_posix()
    down_arrow = (asset_dir / f"spin_down_{t.name}.svg").as_posix()
    return f"""
        {root} {{
            background: {t.window_bg};
            color: {t.primary_text};
        }}
        {root} QWidget#pronounceitScrollWidget,
        {root} QScrollArea#pronounceitScroll {{
            background: transparent;
            border: none;
        }}
        {root} QLabel {{
            color: {t.primary_text};
            font-size: 13px;
        }}
        {root} QLabel#pronounceitTitle {{
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 1px;
        }}
        {root} QLabel#pronounceitIntro {{
            color: {t.secondary_text};
            font-size: 14px;
        }}
        {root} QLabel#pronounceitHelp {{
            color: {t.muted_text};
            font-size: 12px;
        }}
        {root} QLabel#pronounceitPreview {{
            background: {t.advanced_bg};
            border: 1px solid {t.card_border};
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            padding: 11px 13px;
        }}
        {root} QLabel#pronounceitSection {{
            font-size: 13px;
            font-weight: 700;
            margin-top: 16px;
        }}
        {root} QGroupBox {{
            background: {t.card_bg};
            border: 1px solid {t.card_border};
            border-radius: 8px;
            color: {t.primary_text};
            font-size: 13px;
            font-weight: 700;
            margin-top: 14px;
            padding: 18px 14px 14px 14px;
        }}
        {root} QGroupBox::title {{
            left: 14px;
            padding: 0 5px;
            subcontrol-origin: margin;
        }}
        {root} QCheckBox {{
            color: {t.primary_text};
            font-size: 13px;
            spacing: 8px;
        }}
        {root} QLineEdit,
        {root} QKeySequenceEdit,
        {root} QComboBox,
        {root} QSpinBox {{
            border: 1px solid {t.field_border};
            border-radius: 6px;
            background: {t.field_bg};
            color: {t.primary_text};
            font-size: 13px;
            min-height: 30px;
            padding: 4px 9px;
        }}
        {root} QComboBox QAbstractItemView {{
            background: {t.field_bg};
            color: {t.primary_text};
            selection-background-color: {t.accent};
            selection-color: {t.accent_text};
        }}
        {root} QLineEdit:focus,
        {root} QKeySequenceEdit:focus,
        {root} QComboBox:focus,
        {root} QSpinBox:focus {{
            border-color: {t.focus_border};
        }}
        {root} QSpinBox {{ padding-right: 24px; }}
        {root} QSpinBox::up-button {{
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 22px;
            right: 22px;
            background: {t.button_bg};
            border-left: 1px solid {t.field_border};
            border-bottom: 1px solid {t.field_border};
            border-top-right-radius: 5px;
        }}
        {root} QSpinBox::down-button {{
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 22px;
            right: 22px;
            background: {t.button_bg};
            border-left: 1px solid {t.field_border};
            border-bottom-right-radius: 5px;
        }}
        {root} QSpinBox::up-button:hover,
        {root} QSpinBox::down-button:hover {{ background: {t.button_hover_bg}; }}
        {root} QSpinBox::up-arrow {{
            image: url("{up_arrow}");
            width: 8px;
            height: 5px;
        }}
        {root} QSpinBox::down-arrow {{
            image: url("{down_arrow}");
            width: 8px;
            height: 5px;
        }}
        {root} QProgressBar {{
            min-height: 22px;
            border: 1px solid {t.field_border};
            border-radius: 6px;
            background: {t.field_bg};
            color: {t.primary_text};
            text-align: center;
        }}
        {root} QProgressBar::chunk {{
            border-radius: 5px;
            background: {t.accent};
        }}
        {root} QPushButton {{
            border: 1px solid {t.button_border};
            border-radius: 6px;
            background: {t.button_bg};
            color: {t.button_text};
            font-size: 13px;
            font-weight: 600;
            min-height: 30px;
            padding: 5px 16px;
        }}
        {root} QPushButton:hover {{ background: {t.button_hover_bg}; }}
        {root} QPushButton:pressed {{ background: {t.button_pressed_bg}; }}
        {root} QPushButton:checked {{ border-color: {t.focus_border}; }}
        {root} QPushButton:disabled {{
            background: {t.disabled_bg};
            color: {t.disabled_text};
        }}
        {root} QPushButton#pronounceitPrimary {{
            background: {t.accent};
            border-color: {t.accent};
            color: {t.accent_text};
        }}
        {root} QPushButton#pronounceitPrimary:hover {{
            background: {t.accent_hover};
            border-color: {t.accent_hover};
        }}
        {root} QGroupBox#pronounceitAdvanced {{ background: {t.card_bg}; }}
    """
