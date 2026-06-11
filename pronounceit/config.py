from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "hotkey": "Mod+P",
    "tts_voice": "",
    "tts_rate": 0,
    "tts_volume": 100,
    "audio_backend": "local_audio_then_tts",
    "auto_close_on_card_change": True,
    "allow_on_question_side": False,
    "show_context_menu": True,
    "show_save_button": True,
    "unknown_term_message": "Pronunciation unavailable",
}


@dataclass(frozen=True)
class PronounceItConfig:
    enabled: bool
    hotkey: str
    tts_voice: str
    tts_rate: int
    tts_volume: int
    audio_backend: str
    auto_close_on_card_change: bool
    allow_on_question_side: bool
    show_context_menu: bool
    show_save_button: bool
    unknown_term_message: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "PronounceItConfig":
        merged = {**DEFAULT_CONFIG, **(data or {})}
        audio_backend = str(merged.get("audio_backend") or "local_audio_then_tts")
        if audio_backend not in {"system_tts", "local_audio", "local_audio_then_tts"}:
            audio_backend = "local_audio_then_tts"
        return cls(
            enabled=bool(merged["enabled"]),
            hotkey=str(merged["hotkey"] or "Mod+P"),
            tts_voice=str(merged["tts_voice"] or ""),
            tts_rate=int(merged["tts_rate"] or 0),
            tts_volume=max(0, min(100, int(merged["tts_volume"] or 100))),
            audio_backend=audio_backend,
            auto_close_on_card_change=bool(merged["auto_close_on_card_change"]),
            allow_on_question_side=bool(merged["allow_on_question_side"]),
            show_context_menu=bool(merged["show_context_menu"]),
            show_save_button=bool(merged["show_save_button"]),
            unknown_term_message=str(merged["unknown_term_message"] or "Pronunciation unavailable"),
        )

    def as_js_payload(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "hotkey": self.hotkey,
            "allowOnQuestionSide": self.allow_on_question_side,
            "showContextMenu": self.show_context_menu,
            "showSaveButton": self.show_save_button,
            "unknownTermMessage": self.unknown_term_message,
        }

    def as_config_mapping(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "hotkey": self.hotkey,
            "tts_voice": self.tts_voice,
            "tts_rate": self.tts_rate,
            "tts_volume": self.tts_volume,
            "audio_backend": self.audio_backend,
            "auto_close_on_card_change": self.auto_close_on_card_change,
            "allow_on_question_side": self.allow_on_question_side,
            "show_context_menu": self.show_context_menu,
            "show_save_button": self.show_save_button,
            "unknown_term_message": self.unknown_term_message,
        }
