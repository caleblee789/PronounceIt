from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .audio import audio_file_has_content
from .audio_pack import AudioPackError, AudioPackManager
from .audio_pack_download import AudioPackDownloadController, AudioPackDownloadState
from .config import DEFAULT_CONFIG, PronounceItConfig
from .dictionary import PronunciationDictionary, display_term
from .qa import audit_pronunciations
from .storage import (
    CustomPronunciations,
    SavedPronunciations,
    StorageError,
    format_saved_entries,
    saved_entry_key,
)
from .theme import dialog_qss, theme_tokens, web_theme_tokens
from .tts import (
    AudioPackEngine,
    CommandTtsEngine,
    CompositeTtsEngine,
    GeneratedAudioFileEngine,
    LocalAudioFileEngine,
    QtTextToSpeechEngine,
    TtsResult,
    TtsSettings,
)


MESSAGE_PREFIX = "pronounceit:"
MAX_MESSAGE_LENGTH = 65_536
SUPPORT_URL = "https://buymeacoffee.com/caleblee78f"
SUPPORT_TOOLTIP = "If you're enjoying PronounceIt, consider buying me a coffee."
SUPPORT_IMAGE_NAME = "buy_me_a_coffee.png"
CALEB_ADDONS_MENU_TITLE = "Caleb M. Add-ons Settings"
CALEB_ADDONS_MENU_OBJECT_NAME = "caleb_m_addons_menu"
_AUDIO_SOURCE_LABELS = {
    "custom": "Custom audio",
    "azure": "Recorded audio",
    "recorded": "Recorded audio",
    "generated": "Computer voice",
    "live": "Computer voice",
}

_addon_module = ""
_addon_root: Path | None = None
_dictionary: PronunciationDictionary | None = None
_saved: SavedPronunciations | None = None
_custom: CustomPronunciations | None = None
_audio_pack: AudioPackManager | None = None
_audio_pack_download: AudioPackDownloadController | None = None
_reviewer_answer_visible = False
_tts = CompositeTtsEngine()
_playback_diagnostics: list[dict[str, Any]] = []
_runtime_diagnostics: list[str] = []
_hooks_installed = False

_LOOKUP_START_SHORTCUT_MENU = "shortcut_context_menu"
_LOOKUP_START_SHORTCUT_ONLY = "shortcut_only"
_LOOKUP_START_OPTION_SELECT = "option_select"


def _audio_source_label(source: Any) -> str:
    return _AUDIO_SOURCE_LABELS.get(
        str(source or "").casefold(),
        "Computer voice",
    )


@dataclass(frozen=True)
class _PackPresentation:
    status: str
    tone: str
    verified: bool = False
    progress_visible: bool = False
    progress_indeterminate: bool = False
    progress_percent: int = 0
    progress_text: str = ""


def _pack_presentation(state: AudioPackDownloadState) -> _PackPresentation:
    total = max(0, int(state.total_bytes))
    done = max(0, int(state.done_bytes))
    percent = min(100, round(done * 100 / total)) if total else 0

    if state.phase == "installed":
        return _PackPresentation("Installed", "installed", verified=True)
    if state.phase == "verifying":
        return _PackPresentation(
            "Verifying…", "downloading", progress_visible=True, progress_indeterminate=True
        )
    if state.phase == "preparing":
        return _PackPresentation(
            "Preparing…", "downloading", progress_visible=True, progress_indeterminate=True
        )
    if state.phase in {"downloading", "cancelling"}:
        verb = "Cancelling…" if state.phase == "cancelling" else "Downloading…"
        return _PackPresentation(
            f"{verb} {percent}%" if total else verb,
            "downloading",
            progress_visible=True,
            progress_indeterminate=not total,
            progress_percent=percent,
            progress_text=f"{percent}%" if total else verb,
        )
    if state.phase == "paused":
        return _PackPresentation(
            f"Paused • {percent}%" if total else "Paused",
            "paused",
            progress_visible=True,
            progress_indeterminate=not total,
            progress_percent=percent,
            progress_text=f"{percent}% • Ready to resume" if total else "Ready to resume",
        )
    if state.phase == "failed":
        status = "Verification failed" if "verif" in state.message.casefold() else "Download failed"
        return _PackPresentation(
            status,
            "failed",
            progress_visible=bool(total),
            progress_percent=percent,
            progress_text=f"{percent}% • Ready to resume" if total else "",
        )
    if state.phase == "cancelled":
        return _PackPresentation(
            "Download cancelled",
            "paused",
            progress_visible=bool(total),
            progress_percent=percent,
            progress_text=f"{percent}% • Ready to resume" if total else "",
        )
    if state.installed:
        return _PackPresentation("Installed", "installed", verified=True)
    if total:
        return _PackPresentation(
            "Not installed",
            "not-installed",
            progress_visible=True,
            progress_percent=percent,
            progress_text=f"{percent}% • Ready to resume",
        )
    return _PackPresentation("Not installed", "not-installed")


def initialize(addon_module: str) -> None:
    global _addon_module, _addon_root, _dictionary, _saved, _custom
    global _audio_pack, _audio_pack_download, _tts, _hooks_installed
    _addon_module = addon_module
    _addon_root = Path(__file__).resolve().parent.parent
    _migrate_theme_config()
    cache_bytes = _config().audio_pack_cache_mb * 1024 * 1024
    _audio_pack = AudioPackManager(_addon_root, cache_bytes=cache_bytes)
    _audio_pack_download = AudioPackDownloadController(_audio_pack)
    _tts = CompositeTtsEngine(
        [
            LocalAudioFileEngine(_addon_root),
            AudioPackEngine(_addon_root, _audio_pack),
            GeneratedAudioFileEngine(_addon_root),
            QtTextToSpeechEngine(),
            CommandTtsEngine(),
        ]
    )
    _reload_dictionary()
    _saved = SavedPronunciations(_addon_root)
    _custom = CustomPronunciations(_addon_root)

    try:
        from aqt import gui_hooks, mw
    except Exception:
        return

    _audio_pack_download = AudioPackDownloadController(
        _audio_pack,
        dispatch=lambda callback: mw.taskman.run_on_main(callback),
        notifier=_notify_audio_pack,
    )

    if _hooks_installed:
        return

    mw.addonManager.setWebExports(addon_module, r"web/.*(css|js)")
    gui_hooks.webview_will_set_content.append(_on_webview_will_set_content)
    gui_hooks.webview_did_receive_js_message.append(_on_js_message)
    if hasattr(gui_hooks, "reviewer_did_show_question"):
        gui_hooks.reviewer_did_show_question.append(_on_reviewer_show_question)
    if hasattr(gui_hooks, "reviewer_did_show_answer"):
        gui_hooks.reviewer_did_show_answer.append(_on_reviewer_show_answer)
    _install_config_action()
    _install_tools_menu_actions()
    _hooks_installed = True
    try:
        from aqt.qt import QTimer

        QTimer.singleShot(300, _maybe_show_audio_pack_onboarding)
    except Exception:
        pass


def _notify_audio_pack(message: str, error: bool = False) -> None:
    from .ui import feedback

    if error:
        _record_runtime_diagnostic(message)
        feedback("Could not finish the pack operation. Open Troubleshoot audio for details.", error=True)
    elif "cancel" in message.casefold():
        feedback("Download cancelled. Resume it in Audio settings.")
    else:
        feedback("Pronunciation pack is ready." if _audio_pack_download and _audio_pack_download.snapshot().installed else "Pronunciation pack updated.")


def _current_anki_theme() -> str:
    try:
        from aqt.theme import theme_manager

        return "dark" if bool(theme_manager.night_mode) else "light"
    except Exception:
        pass
    try:
        from aqt.qt import QApplication

        color = QApplication.palette().window().color()
        return "dark" if color.lightness() < 128 else "light"
    except Exception:
        return "light"


def _legacy_theme_choice(value: Any, current_theme: str) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized in {"light", "clinical_light"}:
        return "light"
    if normalized in {"dark", "slate", "high_contrast"}:
        return "dark"
    return "dark" if current_theme == "dark" else "light"


def _migrate_theme_config() -> dict[str, Any]:
    raw = _read_config_mapping()
    if raw.get("theme_initialized") is True and raw.get("theme") in {"light", "dark"}:
        return raw
    migrated = {
        **raw,
        "theme": _legacy_theme_choice(raw.get("theme"), _current_anki_theme()),
        "theme_initialized": True,
    }
    try:
        return _write_config(migrated)
    except Exception as exc:
        _record_runtime_diagnostic(f"Could not save appearance settings: {exc}")
        return raw


def _audio_pack_onboarding_needed(
    config: PronounceItConfig, state: AudioPackDownloadState
) -> bool:
    return not config.audio_pack_prompt_seen and not state.installed and not state.running


def _complete_audio_pack_onboarding(download: bool) -> None:
    global _audio_pack_download
    config = _config()
    _write_config({**config.as_config_mapping(), "audio_pack_prompt_seen": True})
    if download and _audio_pack_download is not None:
        _audio_pack_download.start()


def _maybe_show_audio_pack_onboarding() -> None:
    if _audio_pack_download is None:
        return
    state = _audio_pack_download.refresh()
    config = _config()
    if state.installed or state.running:
        if not config.audio_pack_prompt_seen:
            _complete_audio_pack_onboarding(False)
        return
    if not _audio_pack_onboarding_needed(config, state):
        return

    from .ui import show_onboarding

    show_onboarding()


def _install_config_action() -> None:
    try:
        from aqt import mw
    except Exception:
        return

    try:
        mw.addonManager.setConfigAction(_addon_module, _show_config_dialog)
    except Exception:
        pass


def _qt_object_name(widget: Any) -> str:
    getter = getattr(widget, "objectName", None)
    if callable(getter):
        try:
            return str(getter())
        except Exception:
            return ""
    return str(getter or "")


def _qt_menu_title(menu: Any) -> str:
    getter = getattr(menu, "title", None)
    if callable(getter):
        try:
            return str(getter())
        except Exception:
            return ""
    return str(getter or "")


def _qt_action_text(action: Any) -> str:
    text = getattr(action, "text", None)
    if callable(text):
        try:
            return str(text())
        except Exception:
            return ""
    return str(text or getattr(action, "label", ""))


def _menu_actions(menu: Any) -> list[Any]:
    actions_attr = getattr(menu, "actions", None)
    try:
        actions = actions_attr() if callable(actions_attr) else actions_attr
    except Exception:
        actions = []
    return list(actions or [])


def _set_caleb_menu_object_name(menu: Any) -> None:
    setter = getattr(menu, "setObjectName", None)
    if callable(setter):
        try:
            setter(CALEB_ADDONS_MENU_OBJECT_NAME)
        except Exception:
            pass


def _iter_submenus(menu: Any):
    for submenu in getattr(menu, "submenus", []) or []:
        if submenu is not None:
            yield submenu

    for action in _menu_actions(menu):
        if isinstance(action, tuple) and len(action) >= 2:
            action = action[1]
        menu_getter = getattr(action, "menu", None)
        if not callable(menu_getter):
            continue
        try:
            submenu = menu_getter()
        except Exception:
            submenu = None
        if submenu is not None:
            yield submenu


def _get_caleb_addons_menu(menu_bar: Any, main_window: Any):
    existing = getattr(main_window, "_caleb_m_addons_menu", None)
    if existing is not None:
        return existing

    for submenu in _iter_submenus(menu_bar):
        if (
            _qt_object_name(submenu) == CALEB_ADDONS_MENU_OBJECT_NAME
            or _qt_menu_title(submenu) == CALEB_ADDONS_MENU_TITLE
        ):
            _set_caleb_menu_object_name(submenu)
            main_window._caleb_m_addons_menu = submenu
            return submenu

    add_menu = getattr(menu_bar, "addMenu", None)
    if not callable(add_menu):
        return menu_bar

    submenu = add_menu(CALEB_ADDONS_MENU_TITLE)
    _set_caleb_menu_object_name(submenu)
    main_window._caleb_m_addons_menu = submenu
    return submenu


def _install_tools_menu_actions() -> None:
    try:
        from aqt import mw
        from aqt.qt import QAction
    except Exception:
        return

    existing = getattr(mw, "_pronounceit_settings_action", None)
    if existing is not None:
        return

    menu_bar = getattr(getattr(mw, "form", None), "menubar", None)
    if menu_bar is None:
        menu_bar_getter = getattr(mw, "menuBar", None)
        menu_bar = menu_bar_getter() if callable(menu_bar_getter) else None
    if menu_bar is None or not hasattr(menu_bar, "addMenu"):
        return

    submenu = _get_caleb_addons_menu(menu_bar, mw)
    for action in _menu_actions(submenu):
        if isinstance(action, tuple) and len(action) >= 2:
            action = action[1]
        if _qt_action_text(action) == "PronounceIt settings":
            mw._pronounceit_settings_action = action
            return

    config_action = QAction("PronounceIt settings", mw)
    config_action.triggered.connect(_show_config_dialog)
    submenu.addAction(config_action)
    mw._pronounceit_settings_action = config_action


def _lookup_start_choice(config: PronounceItConfig) -> str:
    if config.activation_mode == "option_select":
        return _LOOKUP_START_OPTION_SELECT
    if not config.show_context_menu:
        return _LOOKUP_START_SHORTCUT_ONLY
    return _LOOKUP_START_SHORTCUT_MENU


def _lookup_start_config(choice: str) -> dict[str, Any]:
    if choice == _LOOKUP_START_OPTION_SELECT:
        return {"activation_mode": "option_select", "show_context_menu": False}
    if choice == _LOOKUP_START_SHORTCUT_ONLY:
        return {"activation_mode": "context_menu", "show_context_menu": False}
    return {"activation_mode": "context_menu", "show_context_menu": True}


def _add_activation_modifier_items(combo: Any, platform: str | None = None) -> None:
    is_mac = (platform or sys.platform).startswith("darwin")
    items = [
        ("Option", "alt"),
        ("Shift", "shift"),
        ("Command", "meta"),
        ("Control", "ctrl"),
        ("Disabled", "disabled"),
    ] if is_mac else [
        ("Alt", "alt"),
        ("Shift", "shift"),
        ("Ctrl", "ctrl"),
        ("Meta", "meta"),
        ("Disabled", "disabled"),
    ]
    for label, value in items:
        combo.addItem(label, value)


def _platform_mod_key_name(platform: str | None = None) -> str:
    return "Command" if (platform or sys.platform).startswith("darwin") else "Ctrl"


def _modifier_display_name(value: str, platform: str | None = None) -> str:
    is_mac = (platform or sys.platform).startswith("darwin")
    return {
        "alt": "Option" if is_mac else "Alt",
        "shift": "Shift",
        "meta": "Command" if is_mac else "Meta",
        "ctrl": "Control" if is_mac else "Ctrl",
        "mod": _platform_mod_key_name(platform),
        "disabled": "Disabled",
    }.get(value, "Option" if is_mac else "Alt")


def _activation_modifier_ui_value(value: str, platform: str | None = None) -> str:
    if value == "mod":
        return "meta" if (platform or sys.platform).startswith("darwin") else "ctrl"
    return value


def _behavior_preview_lines(config: PronounceItConfig) -> list[str]:
    audio_modifier = _modifier_display_name(config.direct_click_modifier)
    menu_modifier = _modifier_display_name(config.native_context_menu_modifier)
    lines = ["Using PronounceIt"]
    if config.direct_click_modifier == "disabled":
        lines.append("• Playing pronunciation with a key is turned off.")
    else:
        lines.extend(
            [
                f"• Hold {audio_modifier} while clicking or dragging text to play pronunciation.",
                f"• Or select text, then tap {audio_modifier}.",
            ]
        )
    if not config.show_native_context_menu:
        lines.append("• The quick pronunciation card is turned off.")
    elif config.native_context_menu_modifier == "disabled":
        lines.append("• Opening the quick pronunciation card with a key is turned off.")
    else:
        lines.append(
            f"• Hold {menu_modifier} while clicking or right-clicking, or press "
            f"{menu_modifier} after selecting text, to open the quick pronunciation card."
        )
    return lines


def _support_image_path() -> Path:
    return Path(__file__).resolve().parent / "assets" / SUPPORT_IMAGE_NAME


def _support_button_style() -> str:
    image_path = _support_image_path().as_posix()
    return f"""
        QToolButton#buyMeACoffeeButton {{
            border: none;
            border-image: url(\"{image_path}\") 0 0 0 0 stretch stretch;
            background: transparent;
            padding: 0px;
        }}
        QToolButton#buyMeACoffeeButton:hover {{
            border: none;
            border-image: url(\"{image_path}\") 0 0 0 0 stretch stretch;
            background: transparent;
        }}
    """


def _show_config_dialog() -> None:
    from .ui import show_settings

    show_settings()


def _addon_dir() -> Path:
    return _addon_root or Path(__file__).resolve().parent.parent


def _saved_pronunciations_path() -> Path:
    return _addon_dir() / "user_files" / "saved_pronunciations.json"


def _custom_pronunciations_path() -> Path:
    return _addon_dir() / "user_files" / "custom_pronunciations.json"


def _generated_audio_dir() -> Path:
    return _addon_dir() / "user_files" / "generated_audio"


def _open_path(path: Path) -> None:
    try:
        from aqt.qt import QDesktopServices, QUrl
        from aqt.utils import showInfo
    except Exception:
        _show_text("PronounceIt", str(path))
        return

    try:
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                if path.name == "custom_pronunciations.json":
                    path.write_text('{\n  "terms": []\n}\n', encoding="utf-8")
                else:
                    path.write_text("[]\n", encoding="utf-8")
        else:
            path.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            raise OSError("No application could open this file or folder.")
    except Exception as exc:
        from .ui import error_dialog
        error_dialog("Could not open this file or folder.", f"{path}\n{exc}")


def _open_support_url() -> None:
    try:
        from aqt.qt import QDesktopServices, QUrl
        from aqt.utils import showInfo
    except Exception:
        _show_text("PronounceIt", SUPPORT_URL)
        return

    try:
        if not QDesktopServices.openUrl(QUrl(SUPPORT_URL)):
            from .ui import error_dialog
            error_dialog("Could not open the support page.", SUPPORT_URL)
    except Exception as exc:
        from .ui import error_dialog
        error_dialog("Could not open the support page.", str(exc))


def _show_saved_pronunciations() -> None:
    from .ui import show_saved

    show_saved()


def _current_saved_entry(item: dict[str, Any]) -> dict[str, Any]:
    """Refresh display text in memory without rewriting saved files or audio fields."""
    term = str(item.get("term") or item.get("requestedText") or "")
    payload = _lookup_payload(term)
    if item.get("source") == "user-override":
        if "useTextOverride" not in item and payload.get("source") == "user-override":
            return {**item, "useTextOverride": bool(payload.get("useTextOverride"))}
        return item
    return {**item, "pronunciation": payload.get("pronunciation", ""),
            "textSource": payload.get("textSource", ""), "textReviewStatus": payload.get("textReviewStatus", "")}


def _saved_entry_search_text(item: dict[str, Any]) -> str:
    parts = [
        item.get("term"),
        item.get("requestedText"),
        item.get("pronunciation"),
        item.get("source"),
        item.get("deckName"),
    ]
    return " ".join(str(part) for part in parts if part).casefold()


def _saved_entry_details(item: dict[str, Any]) -> str:
    details = []
    source = {"wiktionary": "Wiktionary", "cmudict": "CMUdict", "nci": "NCI",
              "moby": "Moby", "composed-guide": "Referenced words", "documented-correction": "Reference correction"}.get(item.get("textSource"))
    if item.get("source") == "user-override":
        source = "Custom pronunciation"
    deck_name = item.get("deckName")
    if source:
        details.append(f"Source: {source}")
    if deck_name:
        details.append(f"Deck: {deck_name}")
    return " | ".join(details) if details else "No details"


def _saved_entry_date(item: dict[str, Any]) -> str:
    created = str(item.get("createdAt") or "")
    if "T" in created:
        return created.split("T", 1)[0]
    return created or "Unknown"


def _saved_origin_search_query(item: dict[str, Any]) -> str:
    note_id = _clean_identifier(item.get("noteId"))
    if note_id:
        return f"nid:{note_id}"
    card_id = _clean_identifier(item.get("cardId"))
    if card_id:
        return f"cid:{card_id}"
    return ""


def _clean_identifier(value: Any) -> str:
    text = str(value or "").strip()
    return text if text.isdigit() else ""


def _open_saved_origin(item: dict[str, Any]) -> bool:
    query = _saved_origin_search_query(item)
    if not query:
        return False
    try:
        from aqt import dialogs, mw
        from aqt.utils import showInfo
    except Exception:
        _show_text("PronounceIt", f"Original card search: {query}")
        return False

    try:
        browser = dialogs.open("Browser", mw)
        _set_browser_search(browser, query)
        return True
    except Exception as exc:
        from .ui import error_dialog
        error_dialog("Could not open the original card.", f"{query}\n{exc}")
        return False


def _set_browser_search(browser: Any, query: str) -> None:
    if hasattr(browser, "search_for"):
        browser.search_for(query)
        return
    search_edit = getattr(getattr(browser, "form", None), "searchEdit", None)
    line_edit = search_edit.lineEdit() if hasattr(search_edit, "lineEdit") else search_edit
    if hasattr(line_edit, "setText"):
        line_edit.setText(query)
    if hasattr(browser, "onSearchActivated"):
        browser.onSearchActivated()
    elif hasattr(browser, "search"):
        browser.search()


def _show_dictionary_audit() -> None:
    from .ui import show_library

    show_library()


def _pronounce_manually() -> None:
    from .ui import show_search

    show_search()


def _add_or_update_custom_pronunciation() -> None:
    from .ui import show_custom

    show_custom()


def _ask_for_term() -> str:
    try:
        from aqt import mw
        from aqt.qt import QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout

        dialog = QDialog(mw)
        dialog.setWindowTitle("Search pronunciation")
        dialog.setMinimumWidth(380)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(QLabel("Word or medical term:"))
        term = QLineEdit()
        term.setAccessibleName("Word or medical term")
        layout.addWidget(term)
        buttons = QDialogButtonBox()
        try:
            accept_role = QDialogButtonBox.ButtonRole.AcceptRole
            cancel_button = QDialogButtonBox.StandardButton.Cancel
        except AttributeError:
            accept_role = QDialogButtonBox.AcceptRole
            cancel_button = QDialogButtonBox.Cancel
        search = buttons.addButton("Search", accept_role)
        buttons.addButton(cancel_button)
        search.setDefault(True)
        search.clicked.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        term.returnPressed.connect(dialog.accept)
        term.setFocus()
        accepted = dialog.exec() if hasattr(dialog, "exec") else dialog.exec_()
        return display_term(term.text()) if accepted else ""
    except Exception:
        try:
            from aqt.utils import getText

            text, ok = getText("Word or medical term:", title="Search pronunciation")
            return display_term(text) if ok else ""
        except Exception:
            return ""


def _ask_for_text(
    prompt: str,
    default: str = "",
    title: str = "PronounceIt",
    preserve_punctuation: bool = False,
) -> str:
    try:
        from aqt.utils import getText

        text, ok = getText(prompt, default=default, title=title)
        return text.strip() if ok and preserve_punctuation else display_term(text) if ok else ""
    except Exception:
        pass

    try:
        from aqt import mw
        from aqt.qt import QInputDialog

        text, ok = QInputDialog.getText(mw, title, prompt, text=default)
        return text.strip() if ok and preserve_punctuation else display_term(text) if ok else ""
    except Exception:
        return ""


def _save_custom_pronunciation(
    term: str,
    pronunciation: str,
    syllables: str = "",
    speech_text: str = "",
) -> dict[str, Any]:
    global _custom
    if _addon_root is None:
        raise RuntimeError("PronounceIt is not initialized")
    if _custom is None:
        _custom = CustomPronunciations(_addon_root)
    record = _custom.upsert_entry(
        display_term(term),
        display_term(pronunciation),
        display_term(syllables),
        speech_text.strip(),
    )
    _reload_dictionary()
    return record


def _pronunciation_detail_fields(payload: dict[str, Any], term: str) -> list[tuple[str, str]]:
    return [
        ("Word", str(payload.get("term") or payload.get("requestedText") or term)),
        ("Pronunciation", str(payload.get("pronunciation") or "Pronunciation unavailable")),
    ]


def _show_pronunciation_details(payload: dict[str, Any], term: str) -> None:
    from .ui import show_search

    show_search(term, payload)


def _show_manual_pronunciation(term: str) -> None:
    payload = _lookup_payload(term)
    _show_pronunciation_details(payload, term)


def _show_audio_diagnostics() -> None:
    from .ui import show_diagnostics

    show_diagnostics()


def _format_playback_diagnostics() -> str:
    if not _playback_diagnostics and not _runtime_diagnostics:
        return "No pronunciation playback attempts have been recorded yet."

    lines: list[str] = []
    if _runtime_diagnostics:
        lines.extend(["Runtime and data warnings", ""])
        for index, issue in enumerate(reversed(_runtime_diagnostics), 1):
            lines.append(f"{index}. {issue}")
        lines.append("")
    if _playback_diagnostics:
        lines.extend(["Recent playback attempts", ""])
    for index, item in enumerate(reversed(_playback_diagnostics), 1):
        status = "OK" if item.get("ok") else "FAILED"
        text = str(item.get("text") or item.get("term") or "(empty)")
        lines.append(f"{index}. {status}: {text}")
        term = str(item.get("term") or "")
        if term and term != text:
            lines.append(f"   Term: {term}")
        backend = str(item.get("audioBackend") or "")
        if backend:
            lines.append(f"   Playback mode: {backend}")
        audio_source = str(item.get("audioSource") or "")
        if audio_source:
            lines.append(f"   Source: {_audio_source_label(audio_source)}")
        audio_file = str(item.get("audioFile") or "")
        if audio_file:
            lines.append(f"   Audio file: {audio_file}")
        quality_tier = str(item.get("qualityTier") or "")
        if quality_tier:
            lines.append(f"   Quality tier: {quality_tier}")
        reason = str(item.get("reason") or "")
        if reason:
            lines.append(f"   Reason: {reason}")
        attempts = [str(attempt) for attempt in item.get("attempts", []) if str(attempt)]
        if attempts:
            lines.append("   Attempts:")
            for attempt in attempts:
                lines.append(f"   - {attempt}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _record_runtime_diagnostic(message: str) -> None:
    cleaned = " ".join(str(message or "").split())
    if not cleaned:
        return
    if cleaned in _runtime_diagnostics:
        _runtime_diagnostics.remove(cleaned)
    _runtime_diagnostics.append(cleaned)
    del _runtime_diagnostics[:-20]


def _storage_error_text(error: StorageError) -> str:
    return (
        "PronounceIt could not safely read or update this file, so the existing data was left "
        f"unchanged.\n\n{error.path}\n\n{error.reason}\n\n"
        "Correct or restore the JSON file, then try again."
    )


def _show_text(title: str, text: str) -> None:
    from .ui import show_report

    show_report(title, "More information about PronounceIt.", text)


def _read_config_mapping() -> dict[str, Any]:
    try:
        from aqt import mw

        raw = mw.addonManager.getConfig(_addon_module)
    except Exception:
        raw = None
    return raw if isinstance(raw, dict) else {}


def _write_config(mapping: dict[str, Any]) -> dict[str, Any]:
    next_config = PronounceItConfig.from_mapping(mapping).as_config_mapping()
    try:
        from aqt import mw
    except ImportError:
        return next_config
    mw.addonManager.writeConfig(_addon_module, next_config)
    if _audio_pack is not None:
        _audio_pack.cache_bytes = next_config["audio_pack_cache_mb"] * 1024 * 1024
    return next_config


def _config() -> PronounceItConfig:
    return PronounceItConfig.from_mapping(_read_config_mapping())


def _reload_dictionary() -> None:
    global _dictionary
    if _addon_root is None:
        _dictionary = PronunciationDictionary.bundled()
        return
    _dictionary = PronunciationDictionary.bundled(
        user_file=_addon_root / "user_files" / "custom_pronunciations.json"
    )
    for issue in _dictionary.load_issues:
        _record_runtime_diagnostic(issue)


def _pronounce_current_reviewer_selection() -> None:
    try:
        from aqt import mw
    except Exception:
        return
    reviewer = getattr(mw, "reviewer", None)
    if not _pronunciation_allowed():
        if reviewer is not None:
            _send_pronunciation_blocked(reviewer, {})
        return
    webview = getattr(reviewer, "web", None)
    selected_text = _selected_text_from_webview(webview)
    if selected_text:
        _pronounce_text_from_reviewer(selected_text)
    elif reviewer is not None:
        _eval(reviewer, "window.PronounceIt && window.PronounceIt.pronounceCurrent();")


def _selected_text_from_webview(webview: Any) -> str:
    if webview is None or not hasattr(webview, "selectedText"):
        return ""
    try:
        return display_term(str(webview.selectedText()))
    except Exception:
        return ""


def _pronounce_text_from_reviewer(selected_text: str) -> None:
    try:
        from aqt import mw
    except Exception:
        return
    reviewer = getattr(mw, "reviewer", None)
    if reviewer is not None and _pronunciation_allowed():
        encoded = json.dumps(display_term(selected_text))
        _eval(
            reviewer,
            f"window.PronounceIt && window.PronounceIt.playText({encoded});",
        )


def _lookup_payload(term: str) -> dict[str, Any]:
    clean = display_term(term)
    if _dictionary:
        return _enrich_lookup_payload(_dictionary.lookup(clean))
    return _enrich_lookup_payload({
        "requestedText": clean,
        "term": clean,
        "pronunciation": "",
        "syllables": "",
        "speechText": clean,
        "found": False,
    })


def _lookup_payload_from_request(payload: dict[str, Any]) -> dict[str, Any]:
    selected_text = display_term(str(payload.get("selectedText") or payload.get("text", "")))
    lookup_text = display_term(str(payload.get("text", "")))
    context_text = str(payload.get("contextText") or "")
    if _dictionary and lookup_text and context_text:
        try:
            start = int(payload.get("contextOffsetStart", 0))
            end = int(payload.get("contextOffsetEnd", start))
        except (TypeError, ValueError):
            start = 0
            end = 0
        context_match = _dictionary.best_context_match(context_text, start, end)
        if context_match:
            result = _enrich_lookup_payload(_dictionary.lookup(context_match))
            result["requestedText"] = selected_text
            return result
        context_fallback = _dictionary.context_fallback_term(context_text, start, end)
        if context_fallback and (
            context_fallback != lookup_text or selected_text != context_fallback
        ):
            result = _lookup_payload(context_fallback)
            result["requestedText"] = selected_text
            return result
    result = _lookup_payload(lookup_text or selected_text)
    if selected_text and lookup_text and selected_text != lookup_text:
        result["requestedText"] = selected_text
    return result


def _enrich_lookup_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    config = _config()
    audio_file = str(result.get("audioFile") or "")
    override = bool(result.get("useTextOverride"))
    local = bool(audio_file and _audio_file_is_available(audio_file))
    pack = False
    if config.audio_backend != "system_tts" and not override and not local and _audio_pack is not None:
        try:
            pack = _audio_pack.resolve(str(result.get("term") or result.get("requestedText") or "")) is not None
        except Exception as exc:
            _record_runtime_diagnostic(str(exc))
    recorded = (local or pack) and config.audio_backend != "system_tts" and not override
    if recorded:
        # A written correction can retain bundled audio; it is not a user recording.
        result["audioSource"] = "custom" if local and (audio_file.startswith("user_files/") or not (_addon_dir() / audio_file).is_file()) else "recorded" if result.get("audioProvider") == "kokoro-local" else "azure"
        result["audioStatus"] = "Custom audio ready" if result["audioSource"] == "custom" else "Recorded audio ready"
        result["audioHelp"] = "Play this recording."
    else:
        result["audioSource"] = "live" if config.audio_backend == "system_tts" else "generated"
        result["audioStatus"] = "Computer voice ready" if config.audio_backend != "local_audio" else "No recording available"
        result["audioHelp"] = "Play using your computer voice." if config.audio_backend != "local_audio" else "Choose a mode with computer voice in Audio settings to hear this term."
    result["audioSourceLabel"] = _audio_source_label(result["audioSource"]) if recorded or config.audio_backend != "local_audio" else "No recording available"
    result["audioAvailable"] = recorded or config.audio_backend != "local_audio"
    result["alreadySaved"] = _payload_is_saved(result)
    return result


def _audio_file_is_available(audio_file: str) -> bool:
    if not audio_file:
        return False
    relative = Path(audio_file)
    if relative.is_absolute() or ".." in relative.parts:
        return False
    root = _addon_dir()
    candidates = [
        root / relative,
        root / "user_files" / "audio" / relative.name,
    ]
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            continue
        try:
            if audio_file_has_content(resolved):
                return True
        except OSError:
            continue
    return False


def _payload_is_saved(payload: dict[str, Any]) -> bool:
    if not _saved:
        return False
    try:
        return _saved.contains(payload)
    except StorageError as exc:
        _record_runtime_diagnostic(str(exc))
        return False
    except Exception:
        return False


def _is_reviewer_context(context: Any) -> bool:
    return context.__class__.__name__ == "Reviewer" or (
        hasattr(context, "web") and hasattr(context, "card")
    )


def _on_webview_will_set_content(web_content: Any, context: Any) -> None:
    if not _is_reviewer_context(context):
        return
    # Keep the bridge available so enabling PronounceIt works without reloading
    # the reviewer. JavaScript receives the enabled flag in its ready callback.
    try:
        from aqt import mw

        package = mw.addonManager.addonFromModule(_addon_module)
    except Exception:
        package = _addon_module or "pronounceit"
    if hasattr(web_content, "css") and hasattr(web_content, "js"):
        web_content.css.append(f"/_addons/{package}/web/pronounceit.css")
        web_content.js.append(f"/_addons/{package}/web/pronounceit.js")
    elif hasattr(web_content, "body"):
        css_url = f"/_addons/{package}/web/pronounceit.css"
        js_url = f"/_addons/{package}/web/pronounceit.js"
        web_content.body += (
            f'<link rel="stylesheet" href="{css_url}">'
            f'<script src="{js_url}"></script>'
        )


def _on_js_message(handled: tuple[bool, Any], message: str, context: Any) -> tuple[bool, Any]:
    if not message.startswith(MESSAGE_PREFIX):
        return handled
    if not _is_reviewer_context(context):
        return handled

    action, payload = _parse_message(message)
    if action == "lookup":
        _handle_lookup(context, payload)
    elif action == "audioLookup":
        _handle_audio_lookup(context, payload)
    elif action == "speak":
        _handle_speak(payload, context)
    elif action == "save":
        _handle_save(context, payload)
    elif action == "saveLookup":
        _handle_save_lookup(context, payload)
    elif action == "support":
        _open_support_url()
    elif action == "ready":
        _send_config(context)
    return True, None


def _parse_message(message: str) -> tuple[str, dict[str, Any]]:
    if len(message) > MAX_MESSAGE_LENGTH:
        return "", {}
    body = message[len(MESSAGE_PREFIX) :]
    if ":" not in body:
        return body, {}
    action, raw_payload = body.split(":", 1)
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        payload = {}
    return action, payload if isinstance(payload, dict) else {}


def _send_pronunciation_blocked(context: Any, payload: dict[str, Any]) -> None:
    text = display_term(str(payload.get("selectedText") or payload.get("text") or ""))
    reason = "Reveal the answer before playing pronunciation."
    result = TtsResult(False, reason, ["pronunciation blocked before answer reveal"])
    _record_playback_diagnostic(
        text,
        TtsSettings(audio_backend=_config().audio_backend, term=text),
        result,
    )
    _send_spoken_result(context, result, text=text, term=text)


def _handle_lookup(context: Any, payload: dict[str, Any]) -> None:
    if not _pronunciation_allowed():
        _eval(context, "window.PronounceIt && window.PronounceIt.hide();")
        _send_pronunciation_blocked(context, payload)
        return
    result = _lookup_payload_from_request(payload)
    result["rect"] = payload.get("rect", {})
    result["config"] = _js_config_payload()
    result["autoPlay"] = bool(payload.get("autoPlay"))
    result["request"] = _playback_request_payload(payload)
    _eval(context, f"window.PronounceIt && window.PronounceIt.show({json.dumps(result)});")


def _handle_audio_lookup(context: Any, payload: dict[str, Any]) -> None:
    if not _pronunciation_allowed():
        _eval(context, "window.PronounceIt && window.PronounceIt.hide();")
        _send_pronunciation_blocked(context, payload)
        return
    result = _lookup_payload_from_request(payload)
    _handle_speak(_playback_payload_from_lookup(result), context)


def _playback_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "text",
        "selectedText",
        "contextText",
        "contextOffsetStart",
        "contextOffsetEnd",
        "rect",
    )
    return {key: payload[key] for key in keys if key in payload}


def _playback_payload_from_lookup(result: dict[str, Any]) -> dict[str, Any]:
    audio_file = str(result.get("audioFile") or "")
    audio_source = str(result.get("audioSource") or "")
    override = bool(result.get("useTextOverride"))
    text = result.get("speechText") if override else result.get("synthesisText")
    if audio_source not in {"custom", "azure", "recorded"} or not _audio_file_is_available(audio_file):
        audio_file = ""
    return {
        "text": text or result.get("term") or result.get("requestedText") or "",
        "term": result.get("term") or result.get("requestedText") or "",
        "audioFile": audio_file,
        "useTextOverride": override,
        "qualityTier": result.get("qualityTier", "fallback"),
        "synthesisStrategy": result.get("synthesisStrategy", "azure-native"),
        "audioReviewStatus": result.get("audioReviewStatus", "unreviewed"),
        "audioSource": audio_source,
        "audioSourceLabel": _audio_source_label(audio_source),
    }


def _handle_speak(payload: dict[str, Any], context: Any | None = None) -> bool:
    if context is not None and not _pronunciation_allowed():
        _send_pronunciation_blocked(context, payload)
        return False
    text = display_term(str(payload.get("text") or payload.get("term") or ""))
    config = _config()
    audio_source = str(payload.get("audioSource") or "")
    if audio_source not in {"custom", "azure", "recorded", "generated", "live"}:
        audio_source = (
            "custom"
            if payload.get("source") == "user-override"
            and _audio_file_is_available(str(payload.get("audioFile") or ""))
            else "azure"
            if _audio_file_is_available(str(payload.get("audioFile") or ""))
            else "live"
            if config.audio_backend == "system_tts"
            else "generated"
        )
    settings = TtsSettings(
        voice=config.tts_voice,
        rate=config.tts_rate,
        volume=config.tts_volume,
        audio_backend=config.audio_backend,
        audio_file=str(payload.get("audioFile") or ""),
        term=display_term(str(payload.get("term") or "")),
        use_text_override=bool(payload.get("useTextOverride")),
        quality_tier=str(payload.get("qualityTier") or ""),
        synthesis_strategy=str(payload.get("synthesisStrategy") or "azure-native"),
        audio_review_status=str(payload.get("audioReviewStatus") or "unreviewed"),
        audio_source_hint=audio_source,
    )
    result = _tts.speak_result(text, settings)
    _record_playback_diagnostic(text, settings, result)
    if context is not None:
        _send_spoken_result(context, result, text=text, term=settings.term)
    return result.ok


def _record_playback_diagnostic(text: str, settings: TtsSettings, result: Any) -> None:
    _playback_diagnostics.append(
        {
            "text": text,
            "term": settings.term,
            "audioBackend": settings.audio_backend,
            "audioFile": settings.audio_file,
            "qualityTier": settings.quality_tier,
            "synthesisStrategy": settings.synthesis_strategy,
            "audioReviewStatus": settings.audio_review_status,
            "audioSource": str(getattr(result, "audio_source", "") or ""),
            "ok": bool(getattr(result, "ok", False)),
            "reason": str(getattr(result, "reason", "")),
            "attempts": list(getattr(result, "attempts", [])),
        }
    )
    del _playback_diagnostics[:-20]


def _send_spoken_result(context: Any, result: Any, text: str = "", term: str = "") -> None:
    payload = {
        "ok": bool(getattr(result, "ok", False)),
        "reason": str(getattr(result, "reason", "")),
        "text": text,
        "term": term,
        "attempts": list(getattr(result, "attempts", [])),
        "audioSource": str(getattr(result, "audio_source", "") or ""),
        "audioSourceLabel": _audio_source_label(
            str(getattr(result, "audio_source", "") or "")
        ),
    }
    _eval(context, f"window.PronounceIt && window.PronounceIt.spoken({json.dumps(payload)});")


def _handle_save(context: Any, payload: dict[str, Any]) -> None:
    if not _saved:
        return
    try:
        result = _saved.save_entry(_payload_with_origin(context, payload))
    except StorageError as exc:
        _record_runtime_diagnostic(str(exc))
        js_payload = json.dumps(
            {
                "saved": False,
                "duplicate": False,
                "alreadySaved": False,
                "error": _storage_error_text(exc),
            }
        )
        _eval(context, f"window.PronounceIt && window.PronounceIt.saved({js_payload});")
        return
    js_payload = json.dumps(
        {
            "saved": result.saved,
            "duplicate": result.duplicate,
            "total": result.total,
            "alreadySaved": result.saved or result.duplicate,
        }
    )
    _eval(context, f"window.PronounceIt && window.PronounceIt.saved({js_payload});")


def _handle_save_lookup(context: Any, payload: dict[str, Any]) -> None:
    if not _pronunciation_allowed():
        _send_pronunciation_blocked(context, payload)
        return
    _handle_save(context, _lookup_payload_from_request(payload))


def _payload_with_origin(context: Any, payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    for key, value in _origin_metadata(context).items():
        if value not in (None, ""):
            result[key] = value
    return result


def _origin_metadata(context: Any) -> dict[str, Any]:
    card = getattr(context, "card", None)
    if card is None:
        return {}

    card_id = _object_value(card, "id")
    note_id = _object_value(card, "nid") or _object_value(card, "note_id")
    deck_id = _object_value(card, "did") or _object_value(card, "deck_id")
    note = _call_object_value(card, "note")
    if not note_id and note is not None:
        note_id = _object_value(note, "id")

    metadata: dict[str, Any] = {}
    if card_id not in (None, ""):
        metadata["cardId"] = card_id
    if note_id not in (None, ""):
        metadata["noteId"] = note_id
    if deck_id not in (None, ""):
        metadata["deckId"] = deck_id
        deck_name = _deck_name(deck_id)
        if deck_name:
            metadata["deckName"] = deck_name
    return metadata


def _object_value(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    try:
        value = getattr(obj, name)
    except Exception:
        return None
    if callable(value):
        try:
            return value()
        except Exception:
            return None
    return value


def _call_object_value(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    try:
        value = getattr(obj, name)
    except Exception:
        return None
    if not callable(value):
        return value
    try:
        return value()
    except Exception:
        return None


def _deck_name(deck_id: Any) -> str:
    try:
        from aqt import mw

        decks = getattr(getattr(mw, "col", None), "decks", None)
        if decks is None:
            return ""
        if hasattr(decks, "name"):
            return str(decks.name(deck_id) or "")
        if hasattr(decks, "get"):
            deck = decks.get(deck_id)
            if isinstance(deck, dict):
                return str(deck.get("name") or "")
    except Exception:
        return ""
    return ""


def _send_config(context: Any) -> None:
    _eval(
        context,
        "window.PronounceIt && window.PronounceIt.configure("
        + json.dumps(_js_config_payload())
        + ");",
    )


def _on_reviewer_show_question(card: Any) -> None:
    _set_reviewer_answer_visible(False)


def _on_reviewer_show_answer(card: Any) -> None:
    _set_reviewer_answer_visible(True)


def _set_reviewer_answer_visible(answer_visible: bool) -> None:
    global _reviewer_answer_visible
    _reviewer_answer_visible = answer_visible
    if not _config().auto_close_on_card_change:
        _send_reviewer_config()
        return
    try:
        from aqt import mw

        reviewer = getattr(mw, "reviewer", None)
    except Exception:
        reviewer = None
    if reviewer is not None:
        _eval(reviewer, "window.PronounceIt && window.PronounceIt.hide();")
        _send_config(reviewer)


def _send_reviewer_config() -> None:
    try:
        from aqt import mw

        reviewer = getattr(mw, "reviewer", None)
    except Exception:
        reviewer = None
    if reviewer is not None:
        _send_config(reviewer)


def _pronunciation_allowed() -> bool:
    config = _config()
    return config.enabled and (config.allow_on_question_side or _answer_visible())


def _answer_visible() -> bool:
    if _reviewer_answer_visible:
        return True
    try:
        from aqt import mw
    except Exception:
        return False
    return _reviewer_state_is_answer(getattr(mw, "reviewer", None))


def _reviewer_state_is_answer(reviewer: Any) -> bool:
    if reviewer is None:
        return False
    for attribute in ("state", "_state"):
        value = getattr(reviewer, attribute, "")
        try:
            value = value() if callable(value) else value
        except Exception:
            continue
        if str(value).casefold() == "answer":
            return True
    return False


def _js_config_payload(config: PronounceItConfig | None = None) -> dict[str, Any]:
    selected = config or _config()
    payload = selected.as_js_payload()
    payload["themeTokens"] = web_theme_tokens(selected.theme)
    payload["answerVisible"] = _answer_visible()
    payload["platformModifier"] = "meta" if sys.platform.startswith("darwin") else "ctrl"
    return payload


def _eval(context: Any, javascript: str) -> None:
    web = getattr(context, "web", None)
    if web is not None and hasattr(web, "eval"):
        web.eval(javascript)
