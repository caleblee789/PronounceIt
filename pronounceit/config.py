from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "hotkey": "Mod+P",
    "direct_click_modifier": "alt",
    "popup_click_modifier": "alt",
    "tts_voice": "",
    "tts_rate": 0,
    "tts_volume": 100,
    "audio_backend": "local_audio_then_tts",
    "auto_close_on_card_change": True,
    "allow_on_question_side": False,
    "activation_mode": "context_menu",
    "theme": "system",
    "show_context_menu": False,
    "show_save_button": True,
    "unknown_term_message": "Pronunciation unavailable",
}

SUPPORTED_THEMES = {"system", "clinical_light", "slate", "high_contrast"}
SUPPORTED_CLICK_MODIFIERS = {"alt", "shift", "meta", "ctrl", "mod", "disabled"}


@dataclass(frozen=True)
class PronounceItConfig:
    enabled: bool
    hotkey: str
    direct_click_modifier: str
    popup_click_modifier: str
    tts_voice: str
    tts_rate: int
    tts_volume: int
    audio_backend: str
    auto_close_on_card_change: bool
    allow_on_question_side: bool
    activation_mode: str
    theme: str
    show_context_menu: bool
    show_save_button: bool
    unknown_term_message: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "PronounceItConfig":
        merged = {**DEFAULT_CONFIG, **(data or {})}
        audio_backend = str(merged.get("audio_backend") or "local_audio_then_tts")
        if audio_backend not in {"system_tts", "local_audio", "local_audio_then_tts"}:
            audio_backend = "local_audio_then_tts"
        activation_mode = str(merged.get("activation_mode") or "context_menu")
        if activation_mode not in {"context_menu", "option_select"}:
            activation_mode = "context_menu"
        theme = str(merged.get("theme") or "system")
        if theme not in SUPPORTED_THEMES:
            theme = "system"
        direct_click_modifier = _click_modifier(
            merged.get("direct_click_modifier"),
            fallback="alt",
        )
        popup_click_modifier = _click_modifier(
            merged.get("popup_click_modifier"),
            fallback="alt",
        )
        return cls(
            enabled=bool(merged["enabled"]),
            hotkey=str(merged["hotkey"] or "Mod+P"),
            direct_click_modifier=direct_click_modifier,
            popup_click_modifier=popup_click_modifier,
            tts_voice=str(merged["tts_voice"] or ""),
            tts_rate=int(merged["tts_rate"] or 0),
            tts_volume=max(0, min(100, int(merged["tts_volume"] or 100))),
            audio_backend=audio_backend,
            auto_close_on_card_change=bool(merged["auto_close_on_card_change"]),
            allow_on_question_side=bool(merged["allow_on_question_side"]),
            activation_mode=activation_mode,
            theme=theme,
            show_context_menu=bool(merged["show_context_menu"]),
            show_save_button=bool(merged["show_save_button"]),
            unknown_term_message=str(merged["unknown_term_message"] or "Pronunciation unavailable"),
        )

    def as_js_payload(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "hotkey": self.hotkey,
            "directClickModifier": self.direct_click_modifier,
            "popupClickModifier": self.popup_click_modifier,
            "allowOnQuestionSide": self.allow_on_question_side,
            "activationMode": self.activation_mode,
            "theme": self.theme,
            "showContextMenu": self.show_context_menu,
            "showSaveButton": self.show_save_button,
            "unknownTermMessage": self.unknown_term_message,
        }

    def as_config_mapping(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "hotkey": self.hotkey,
            "direct_click_modifier": self.direct_click_modifier,
            "popup_click_modifier": self.popup_click_modifier,
            "tts_voice": self.tts_voice,
            "tts_rate": self.tts_rate,
            "tts_volume": self.tts_volume,
            "audio_backend": self.audio_backend,
            "auto_close_on_card_change": self.auto_close_on_card_change,
            "allow_on_question_side": self.allow_on_question_side,
            "activation_mode": self.activation_mode,
            "theme": self.theme,
            "show_context_menu": self.show_context_menu,
            "show_save_button": self.show_save_button,
            "unknown_term_message": self.unknown_term_message,
        }


def _click_modifier(value: Any, fallback: str) -> str:
    modifier = str(value or fallback).casefold()
    if modifier in {"option", "alt"}:
        return "alt"
    if modifier in {"cmd", "command", "meta"}:
        return "meta"
    if modifier in {"control", "ctrl"}:
        return "ctrl"
    if modifier in SUPPORTED_CLICK_MODIFIERS:
        return modifier
    return fallback
