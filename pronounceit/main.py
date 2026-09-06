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
    "azure": "High Quality Downloaded Pack",
    "recorded": "High Quality Downloaded Pack",
    "generated": "Standard text-to-speech",
    "live": "Standard text-to-speech",
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
        "Standard text-to-speech",
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

        QTimer.singleShot(0, _maybe_show_audio_pack_onboarding)
    except Exception:
        pass


def _notify_audio_pack(message: str, error: bool = False) -> None:
    if error:
        _record_runtime_diagnostic(message)
    try:
        from aqt.utils import tooltip

        tooltip(message, period=6000)
    except Exception:
        return


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
    return _write_config(migrated)


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

    try:
        from aqt import mw
        from aqt.qt import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
    except Exception:
        return

    dialog = QDialog(mw)
    dialog.setObjectName("pronounceitOnboarding")
    dialog.setWindowTitle("Optional offline pronunciation pack")
    dialog.setMinimumWidth(500)
    dialog.setStyleSheet(dialog_qss(config.theme, "pronounceitOnboarding"))
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(22, 22, 22, 18)
    layout.setSpacing(14)

    title = QLabel("Download high-quality offline pronunciations?")
    title.setObjectName("pronounceitTitle")
    title.setWordWrap(True)
    layout.addWidget(title)

    description = QLabel(
        "The optional pronunciation pack provides consistent, high-quality audio and "
        "downloads in the background, so you can continue using Anki.\n\n"
        "If you choose Not now, PronounceIt will keep using bundled or local audio and "
        "fall back to your system voice when it is available."
    )
    description.setObjectName("pronounceitIntro")
    description.setWordWrap(True)
    layout.addWidget(description)

    buttons = QHBoxLayout()
    buttons.addStretch(1)
    not_now = QPushButton("Not now")
    download = QPushButton(
        "Resume pronunciation pack" if state.total_shards else "Download pronunciation pack"
    )
    download.setObjectName("pronounceitPrimary")
    buttons.addWidget(not_now)
    buttons.addWidget(download)
    layout.addLayout(buttons)

    handled = {"value": False}

    def finish(should_download: bool) -> None:
        if handled["value"]:
            return
        handled["value"] = True
        _complete_audio_pack_onboarding(should_download)

    download.clicked.connect(lambda _checked=False: (finish(True), dialog.accept()))
    not_now.clicked.connect(lambda _checked=False: (finish(False), dialog.reject()))
    if hasattr(dialog, "rejected"):
        dialog.rejected.connect(lambda: finish(False))
    if hasattr(dialog, "exec"):
        dialog.exec()
    else:
        dialog.exec_()


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
    try:
        from aqt import mw
        from aqt.qt import (
            QCheckBox,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QFormLayout,
            QFrame,
            QGridLayout,
            QGroupBox,
            QHBoxLayout,
            QIcon,
            QLabel,
            QLineEdit,
            QPushButton,
            QProgressBar,
            QScrollArea,
            QSpinBox,
            QTimer,
            QToolButton,
            Qt,
            QVBoxLayout,
            QWidget,
        )
        from aqt.utils import askUser, showInfo
    except Exception:
        _show_text(
            "PronounceIt",
            "PronounceIt settings are available through the add-on config JSON.\n\n"
            "Saved words are stored in user_files/saved_pronunciations.json.",
        )
        return

    config = _config()
    dialog = QDialog(mw)
    dialog.setWindowTitle("PronounceIt settings")
    dialog.setObjectName("pronounceitOptions")
    dialog.setMinimumSize(540, 520)
    dialog.setStyleSheet(dialog_qss(config.theme))
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 18, 18, 14)
    layout.setSpacing(10)

    scroll_area = QScrollArea()
    scroll_area.setObjectName("pronounceitScroll")
    scroll_area.setWidgetResizable(True)
    try:
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
    except AttributeError:
        scroll_area.setFrameShape(QFrame.NoFrame)
    try:
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    except AttributeError:
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    scroll_widget = QWidget()
    scroll_widget.setObjectName("pronounceitScrollWidget")
    body_layout = QVBoxLayout(scroll_widget)
    body_layout.setContentsMargins(0, 0, 16, 4)
    body_layout.setSpacing(18)

    title = QLabel("PronounceIt settings")
    title.setObjectName("pronounceitTitle")
    body_layout.addWidget(title)

    intro = QLabel(
        "Choose how to hear and view pronunciations while reviewing. More options are available below."
    )
    intro.setObjectName("pronounceitIntro")
    intro.setWordWrap(True)
    body_layout.addWidget(intro)

    preview = QLabel()
    preview.setObjectName("pronounceitPreview")
    preview.setWordWrap(True)
    body_layout.addWidget(preview)

    def polish_form(form) -> None:
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        try:
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        except AttributeError:
            form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

    def make_form_group(title: str):
        group = QGroupBox(title)
        form = QFormLayout(group)
        form.setContentsMargins(10, 10, 10, 10)
        polish_form(form)
        return group, form

    def add_help(form, text: str) -> None:
        help_label = QLabel(text)
        help_label.setObjectName("pronounceitHelp")
        help_label.setWordWrap(True)
        form.addRow("", help_label)

    def add_section(layout_obj, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("pronounceitSection")
        layout_obj.addWidget(label)

    def set_combo_data(combo, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(max(0, index))

    review_box, review_form = make_form_group("Review")

    enabled = QCheckBox("Enable PronounceIt")
    enabled.setChecked(config.enabled)
    review_form.addRow(enabled)

    activation_modifier = QComboBox()
    _add_activation_modifier_items(activation_modifier)
    activation_modifier.setAccessibleName("Key for playing pronunciation")
    activation_modifier.setToolTip(
        "Hold this key while clicking or dragging over text, or press it after selecting text."
    )
    set_combo_data(
        activation_modifier,
        _activation_modifier_ui_value(config.direct_click_modifier),
    )
    review_form.addRow("Play pronunciation with", activation_modifier)

    context_menu_modifier = QComboBox()
    _add_activation_modifier_items(context_menu_modifier)
    context_menu_modifier.setAccessibleName("Key for opening the quick pronunciation card")
    context_menu_modifier.setToolTip(
        "Hold this key while clicking or right-clicking, or press it after selecting text."
    )
    set_combo_data(
        context_menu_modifier,
        _activation_modifier_ui_value(config.native_context_menu_modifier),
    )
    review_form.addRow("Open quick card with", context_menu_modifier)

    show_native_menu = QCheckBox("Show the quick pronunciation card")
    show_native_menu.setChecked(config.show_native_context_menu)
    review_form.addRow(show_native_menu)
    add_help(
        review_form,
        "The quick card shows pronunciation details and actions without leaving your review.",
    )

    theme = QComboBox()
    theme.addItem("Light", "light")
    theme.addItem("Dark", "dark")
    theme_index = theme.findData(config.theme)
    theme.setCurrentIndex(max(0, theme_index))
    theme.setToolTip("Preview Light or Dark immediately; Save keeps the selection.")
    review_form.addRow("Theme", theme)

    body_layout.addWidget(review_box)

    advanced_toggle = QPushButton("Show advanced settings")
    advanced_toggle.setCheckable(True)
    reset_button = QPushButton("Reset to defaults")
    support_button = QToolButton()
    support_button.setObjectName("buyMeACoffeeButton")
    support_button.setToolTip(SUPPORT_TOOLTIP)
    support_button.setAccessibleName("Buy Me a Coffee")
    if hasattr(support_button, "setAccessibleDescription"):
        support_button.setAccessibleDescription(SUPPORT_TOOLTIP)
    try:
        support_button.setCursor(Qt.CursorShape.PointingHandCursor)
    except AttributeError:
        support_button.setCursor(Qt.PointingHandCursor)
    support_button.setFixedSize(98, 28)
    support_button.setStyleSheet(_support_button_style())
    if _support_image_path().exists():
        support_button.setIcon(QIcon())
    else:
        support_button.setText("Buy me a coffee")
    toggle_row = QHBoxLayout()
    toggle_row.setContentsMargins(0, 0, 18, 0)
    toggle_row.setSpacing(8)
    toggle_row.addWidget(advanced_toggle)
    toggle_row.addWidget(reset_button)
    toggle_row.addStretch(1)
    toggle_row.addWidget(support_button)
    body_layout.addLayout(toggle_row)

    advanced_box = QGroupBox("Advanced")
    advanced_box.setObjectName("pronounceitAdvanced")
    advanced_layout = QVBoxLayout(advanced_box)
    advanced_layout.setContentsMargins(10, 10, 10, 12)
    advanced_layout.setSpacing(14)
    advanced_box.setVisible(False)

    add_section(advanced_layout, "Before showing the answer")
    study_form = QFormLayout()
    polish_form(study_form)
    allow_question = QCheckBox("Allow pronunciation before the answer is shown")
    allow_question.setChecked(config.allow_on_question_side)
    allow_question.setToolTip("Turn this off if hearing a term early would reveal the answer.")
    study_form.addRow(allow_question)
    add_help(
        study_form,
        "Turn this off if hearing a term early would reveal the answer.",
    )
    advanced_layout.addLayout(study_form)

    add_section(advanced_layout, "Pronunciation cards")
    popup_form = QFormLayout()
    polish_form(popup_form)
    auto_close = QCheckBox("Close open pronunciation cards when moving to the next card")
    auto_close.setChecked(config.auto_close_on_card_change)
    popup_form.addRow(auto_close)

    show_save = QCheckBox('Show “Save pronunciation” in pronunciation details and the quick card')
    show_save.setChecked(config.show_save_button)
    popup_form.addRow(show_save)
    advanced_layout.addLayout(popup_form)

    add_section(advanced_layout, "Audio")
    audio_form = QFormLayout()
    polish_form(audio_form)
    backend = QComboBox()
    backend.addItem(
        "Use available pronunciation audio, then computer voice if needed",
        "local_audio_then_tts",
    )
    backend.addItem("Use available pronunciation audio only", "local_audio")
    backend.addItem("Use computer voice only", "system_tts")
    backend.setToolTip(
        "Choose which types of audio PronounceIt may use."
    )
    backend_index = backend.findData(config.audio_backend)
    backend.setCurrentIndex(max(0, backend_index))
    audio_form.addRow("When playing pronunciation", backend)
    add_help(
        audio_form,
        "Available audio includes custom recordings, the offline pack, and pronunciations already created on this computer.",
    )
    advanced_layout.addLayout(audio_form)

    pack_box, pack_form = make_form_group("Offline pronunciation pack")
    pack_status_row = QWidget()
    pack_status_layout = QHBoxLayout(pack_status_row)
    pack_status_layout.setContentsMargins(0, 0, 0, 0)
    pack_status_layout.setSpacing(8)
    pack_status = QLabel()
    pack_status.setWordWrap(True)
    pack_status.setAccessibleName("Offline pronunciation pack status")
    pack_verified = QLabel("Verified")
    pack_verified.setAccessibleName("Offline pronunciation pack verified")
    initial_theme = theme_tokens(config.theme)
    pack_verified.setStyleSheet(
        f"background: {initial_theme.success}; color: {initial_theme.accent_text}; "
        "border-radius: 7px; font-size: 10px; font-weight: 700; padding: 1px 6px;"
    )
    pack_verified.setVisible(False)
    pack_status_layout.addWidget(pack_status)
    pack_status_layout.addWidget(pack_verified)
    pack_status_layout.addStretch(1)
    pack_form.addRow("Status", pack_status_row)
    pack_progress = QProgressBar()
    pack_progress.setRange(0, 100)
    pack_progress.setValue(0)
    pack_progress.setTextVisible(True)
    pack_progress.setAccessibleName("Offline pronunciation pack progress")
    pack_progress_label = QLabel("Progress")
    pack_form.addRow(pack_progress_label, pack_progress)
    pack_buttons = QHBoxLayout()
    pack_download = QPushButton("Download")
    pack_pause = QPushButton("Pause")
    pack_cancel = QPushButton("Cancel")
    pack_verify = QPushButton("Check downloaded files")
    pack_remove = QPushButton("Remove pack")
    pack_pause.setEnabled(False)
    pack_cancel.setEnabled(False)
    for pack_button in (pack_download, pack_pause, pack_cancel, pack_verify, pack_remove):
        pack_buttons.addWidget(pack_button)
    pack_form.addRow("", pack_buttons)
    add_help(
        pack_form,
        "Optional. Downloads in the background and provides consistent, high-quality pronunciation without an internet connection. It stays installed when the add-on updates.",
    )
    body_layout.insertWidget(body_layout.indexOf(review_box) + 1, pack_box)

    def audio_pack_manager() -> AudioPackManager:
        global _audio_pack
        if _audio_pack is None:
            _audio_pack = AudioPackManager(
                _addon_dir(),
                cache_bytes=config.audio_pack_cache_mb * 1024 * 1024,
            )
        return _audio_pack

    def audio_pack_controller() -> AudioPackDownloadController:
        global _audio_pack_download
        if _audio_pack_download is None:
            _audio_pack_download = AudioPackDownloadController(audio_pack_manager())
        return _audio_pack_download

    def set_pack_status_tone(tone: str) -> None:
        colors = theme_tokens(theme.currentData() or config.theme)
        colors = {
            "installed": colors.success,
            "downloading": colors.focus_border,
            "paused": colors.warning,
            "not-installed": colors.muted_text,
            "failed": colors.danger,
        }
        pack_status.setStyleSheet(f"color: {colors[tone]}; font-weight: 600;")
        verified = theme_tokens(theme.currentData() or config.theme)
        pack_verified.setStyleSheet(
            f"background: {verified.success}; color: {verified.accent_text}; "
            "border-radius: 7px; font-size: 10px; font-weight: 700; padding: 1px 6px;"
        )

    def refresh_pack_status() -> None:
        state = audio_pack_controller().refresh()
        presentation = _pack_presentation(state)
        pack_status.setText(presentation.status)
        pack_status.setToolTip(state.error or state.message)
        set_pack_status_tone(presentation.tone)
        pack_verified.setVisible(presentation.verified)
        pack_progress_label.setVisible(presentation.progress_visible)
        pack_progress.setVisible(presentation.progress_visible)
        if presentation.progress_indeterminate:
            pack_progress.setRange(0, 0)
        else:
            pack_progress.setRange(0, 100)
            pack_progress.setValue(presentation.progress_percent)
            pack_progress.setFormat(presentation.progress_text)

        if state.running:
            pack_pause.setText("Resume" if state.paused else "Pause")
            pack_pause.setEnabled(state.phase in {"downloading", "paused"})
            pack_cancel.setEnabled(state.phase in {"preparing", "downloading", "paused"})
            pack_download.setEnabled(False)
            pack_verify.setEnabled(False)
            pack_remove.setEnabled(False)
            return
        pack_download.setText("Update" if state.installed else "Download")
        pack_download.setEnabled(True)
        pack_verify.setEnabled(state.total_shards > 0)
        pack_remove.setEnabled(state.total_shards > 0 or state.installed)
        pack_pause.setText("Pause")
        pack_pause.setEnabled(False)
        pack_cancel.setEnabled(False)

    def start_pack_download(*_args) -> None:
        audio_pack_controller().start()
        refresh_pack_status()

    def toggle_pack_pause(*_args) -> None:
        controller = audio_pack_controller()
        if controller.snapshot().paused:
            controller.resume()
        else:
            controller.pause()
        refresh_pack_status()

    def verify_pack(*_args) -> None:
        audio_pack_controller().start_verify()
        refresh_pack_status()

    def cancel_pack_download(*_args) -> None:
        audio_pack_controller().cancel()
        refresh_pack_status()

    def remove_pack(*_args) -> None:
        if not askUser(
            "Remove the offline pronunciation pack?\n\n"
            "Saved pronunciations, custom pronunciations, and generated pronunciation files will not be removed.",
            title="PronounceIt",
            defaultno=True,
        ):
            return
        try:
            audio_pack_controller().remove()
        except AudioPackError as exc:
            showInfo(f"Could not remove the offline pronunciation pack.\n\n{exc}", title="PronounceIt")
        refresh_pack_status()

    pack_download.clicked.connect(start_pack_download)
    pack_pause.clicked.connect(toggle_pack_pause)
    pack_cancel.clicked.connect(cancel_pack_download)
    pack_verify.clicked.connect(verify_pack)
    pack_remove.clicked.connect(remove_pack)
    pack_timer = QTimer(dialog)
    pack_timer.timeout.connect(refresh_pack_status)
    pack_timer.start(250)
    refresh_pack_status()

    add_section(advanced_layout, "Computer voice")
    voice_form = QFormLayout()
    polish_form(voice_form)
    voice = QLineEdit(config.tts_voice)
    voice.setPlaceholderText("Use computer default")
    voice.setToolTip("Leave blank to use your computer's default voice.")
    voice_form.addRow("Voice name", voice)

    rate = QSpinBox()
    rate.setRange(-10, 10)
    rate.setValue(config.tts_rate)
    rate.setToolTip("Some computer voices may ignore this setting.")
    voice_form.addRow("Speaking speed", rate)

    volume = QSpinBox()
    volume.setRange(0, 100)
    volume.setSuffix("%")
    volume.setValue(config.tts_volume)
    volume.setToolTip("Some computer voices may ignore this setting.")
    voice_form.addRow("Volume", volume)
    advanced_layout.addLayout(voice_form)

    add_section(advanced_layout, "Pronunciation tools")
    tool_items = [
        ("Play selected text", _pronounce_current_reviewer_selection),
        ("Search pronunciation", _pronounce_manually),
        ("Saved pronunciations", _show_saved_pronunciations),
        ("Add custom pronunciation", _add_or_update_custom_pronunciation),
        ("Check pronunciation library", _show_dictionary_audit),
        ("Troubleshoot playback", _show_audio_diagnostics),
    ]
    tools_grid = QGridLayout()
    tools_grid.setSpacing(8)
    for index, (label, callback) in enumerate(tool_items):
        button = QPushButton(label)
        button.clicked.connect(lambda _checked=False, handler=callback: handler())
        tools_grid.addWidget(button, index // 2, index % 2)
    advanced_layout.addLayout(tools_grid)

    add_section(advanced_layout, "Files")
    files_grid = QGridLayout()
    files_grid.setSpacing(8)
    for index, (label, target) in enumerate([
        ("Open saved pronunciations file", _saved_pronunciations_path),
        ("Open custom pronunciations file", _custom_pronunciations_path),
        ("Open computer-generated audio", _generated_audio_dir),
        ("Open PronounceIt folder", _addon_dir),
    ]):
        button = QPushButton(label)
        button.clicked.connect(lambda _checked=False, path_factory=target: _open_path(path_factory()))
        files_grid.addWidget(button, index // 2, index % 2)
    advanced_layout.addLayout(files_grid)
    body_layout.addWidget(advanced_box)

    body_layout.addStretch(1)
    scroll_area.setWidget(scroll_widget)
    layout.addWidget(scroll_area, 1)

    def set_advanced_visible(visible: bool) -> None:
        advanced_box.setVisible(visible)
        advanced_toggle.setText("Hide advanced settings" if visible else "Show advanced settings")
        target_height = dialog.maximumHeight() if visible else min(dialog.maximumHeight(), 560)
        dialog.resize(max(dialog.width(), 620), target_height)
        if visible:
            QTimer.singleShot(0, lambda: scroll_area.ensureWidgetVisible(advanced_box, 0, 12))

    advanced_toggle.toggled.connect(set_advanced_visible)

    def current_preview_config() -> PronounceItConfig:
        return PronounceItConfig.from_mapping(
            {
                **config.as_config_mapping(),
                "direct_click_modifier": activation_modifier.currentData()
                or DEFAULT_CONFIG["direct_click_modifier"],
                "native_context_menu_modifier": context_menu_modifier.currentData()
                or DEFAULT_CONFIG["native_context_menu_modifier"],
                "show_native_context_menu": show_native_menu.isChecked(),
                "theme": theme.currentData() or config.theme,
            }
        )

    def update_preview(*_args) -> None:
        preview.setText("\n".join(_behavior_preview_lines(current_preview_config())))

    def preview_theme(*_args) -> None:
        dialog.setStyleSheet(dialog_qss(theme.currentData() or config.theme))
        support_button.setStyleSheet(_support_button_style())
        refresh_pack_status()

    def reset_to_defaults(*_args) -> None:
        defaults = PronounceItConfig.from_mapping(
            {
                **DEFAULT_CONFIG,
                "theme": _current_anki_theme(),
                "theme_initialized": True,
                "audio_pack_prompt_seen": config.audio_pack_prompt_seen,
            }
        )
        enabled.setChecked(defaults.enabled)
        set_combo_data(
            activation_modifier,
            _activation_modifier_ui_value(defaults.direct_click_modifier),
        )
        set_combo_data(
            context_menu_modifier,
            _activation_modifier_ui_value(defaults.native_context_menu_modifier),
        )
        show_native_menu.setChecked(defaults.show_native_context_menu)
        set_combo_data(backend, defaults.audio_backend)
        set_combo_data(theme, defaults.theme)
        allow_question.setChecked(defaults.allow_on_question_side)
        auto_close.setChecked(defaults.auto_close_on_card_change)
        show_save.setChecked(defaults.show_save_button)
        voice.setText(defaults.tts_voice)
        rate.setValue(defaults.tts_rate)
        volume.setValue(defaults.tts_volume)
        update_preview()
        preview_theme()

    activation_modifier.currentIndexChanged.connect(update_preview)
    context_menu_modifier.currentIndexChanged.connect(update_preview)
    show_native_menu.toggled.connect(update_preview)
    theme.currentIndexChanged.connect(preview_theme)
    reset_button.clicked.connect(reset_to_defaults)
    support_button.clicked.connect(lambda _checked=False: _open_support_url())
    update_preview()

    try:
        button_flags = QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
    except AttributeError:
        button_flags = QDialogButtonBox.Save | QDialogButtonBox.Cancel
    buttons = QDialogButtonBox(button_flags)
    layout.addWidget(buttons)

    try:
        screen = dialog.screen()
        available_height = screen.availableGeometry().height() if screen else 760
    except Exception:
        available_height = 760
    max_dialog_height = max(520, min(720, available_height - 80))
    dialog.setMaximumHeight(max_dialog_height)
    dialog.resize(620, min(620, max_dialog_height))

    def save() -> None:
        next_config = {
            "enabled": enabled.isChecked(),
            "hotkey": config.hotkey,
            "direct_click_modifier": activation_modifier.currentData()
            or DEFAULT_CONFIG["direct_click_modifier"],
            "popup_click_modifier": config.popup_click_modifier,
            "native_context_menu_modifier": context_menu_modifier.currentData()
            or DEFAULT_CONFIG["native_context_menu_modifier"],
            "show_native_context_menu": show_native_menu.isChecked(),
            "tts_voice": voice.text().strip(),
            "tts_rate": rate.value(),
            "tts_volume": volume.value(),
            "audio_backend": backend.currentData() or DEFAULT_CONFIG["audio_backend"],
            "audio_pack_cache_mb": config.audio_pack_cache_mb,
            "auto_close_on_card_change": auto_close.isChecked(),
            "allow_on_question_side": allow_question.isChecked(),
            "activation_mode": config.activation_mode,
            "theme": theme.currentData() or DEFAULT_CONFIG["theme"],
            "theme_initialized": True,
            "audio_pack_prompt_seen": config.audio_pack_prompt_seen,
            "show_context_menu": config.show_context_menu,
            "show_save_button": show_save.isChecked(),
            "unknown_term_message": config.unknown_term_message,
        }
        _write_config(next_config)
        _send_reviewer_config()
        showInfo("PronounceIt settings saved.")
        dialog.accept()

    buttons.accepted.connect(save)
    buttons.rejected.connect(dialog.reject)
    if hasattr(dialog, "exec"):
        dialog.exec()
    else:
        dialog.exec_()


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
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    except Exception as exc:
        showInfo(f"Could not open {path}.\n\n{exc}", title="PronounceIt")


def _open_support_url() -> None:
    try:
        from aqt.qt import QDesktopServices, QUrl
        from aqt.utils import showInfo
    except Exception:
        _show_text("PronounceIt", SUPPORT_URL)
        return

    try:
        if not QDesktopServices.openUrl(QUrl(SUPPORT_URL)):
            showInfo(f"Could not open {SUPPORT_URL}.", title="PronounceIt")
    except Exception as exc:
        showInfo(f"Could not open {SUPPORT_URL}.\n\n{exc}", title="PronounceIt")


def _show_saved_pronunciations() -> None:
    if not _saved:
        _show_text("PronounceIt saved pronunciations", "No saved pronunciations yet.")
        return
    try:
        items = _saved.load()
    except StorageError as exc:
        _record_runtime_diagnostic(str(exc))
        _show_text("PronounceIt saved pronunciations", _storage_error_text(exc))
        return
    try:
        from aqt import mw
        from aqt.qt import (
            QAbstractItemView,
            QDialog,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QPushButton,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
        )
    except Exception:
        _show_text("PronounceIt saved pronunciations", format_saved_entries(items))
        return

    dialog = QDialog(mw)
    dialog.setWindowTitle("PronounceIt saved pronunciations")
    dialog.setMinimumSize(640, 300)
    dialog.resize(720, 420)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(16, 16, 16, 14)
    layout.setSpacing(10)

    intro = QLabel("Pronunciations you've saved for later review.")
    layout.addWidget(intro)

    search = QLineEdit()
    search.setPlaceholderText("Search saved words")
    layout.addWidget(search)

    empty = QLabel(
        "Saved pronunciations will appear here after you choose Save pronunciation "
        "in the details popup or quick pronunciation card."
    )
    empty.setWordWrap(True)
    layout.addWidget(empty)

    table = QTableWidget(0, 4)
    table.setHorizontalHeaderLabels(["Term", "Pronunciation", "Details", "Saved"])
    table.setAlternatingRowColors(True)
    try:
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    except AttributeError:
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    layout.addWidget(table)

    action_row = QHBoxLayout()
    play_button = QPushButton("Play")
    open_button = QPushButton("Open Original")
    remove_button = QPushButton("Remove")
    close_button = QPushButton("Close")
    action_row.addWidget(play_button)
    action_row.addWidget(open_button)
    action_row.addWidget(remove_button)
    action_row.addStretch(1)
    action_row.addWidget(close_button)
    layout.addLayout(action_row)

    visible_items: list[dict[str, Any]] = []

    def selected_item() -> dict[str, Any] | None:
        row = table.currentRow()
        if row < 0 or row >= len(visible_items):
            return None
        return visible_items[row]

    def update_buttons() -> None:
        item = selected_item()
        has_item = item is not None
        play_button.setEnabled(has_item)
        remove_button.setEnabled(has_item)
        open_button.setEnabled(bool(item and _saved_origin_search_query(item)))

    def add_cell(row: int, column: int, text: str) -> None:
        table.setItem(row, column, QTableWidgetItem(text))

    def refresh() -> None:
        query = search.text().strip().casefold()
        visible_items.clear()
        for item in items:
            if not query or query in _saved_entry_search_text(item):
                visible_items.append(item)

        table.setRowCount(len(visible_items))
        for row, item in enumerate(visible_items):
            term = str(item.get("term") or item.get("requestedText") or "Unknown term")
            pronunciation = str(item.get("pronunciation") or "Pronunciation unavailable")
            details = _saved_entry_details(item)
            created = _saved_entry_date(item)
            add_cell(row, 0, term)
            add_cell(row, 1, pronunciation)
            add_cell(row, 2, details)
            add_cell(row, 3, created)

        empty.setVisible(not visible_items)
        table.setVisible(bool(visible_items))
        if visible_items:
            table.selectRow(0)
        update_buttons()

    def play_selected() -> None:
        item = selected_item()
        if not item:
            return
        _handle_speak(
            {
                "text": (
                    item.get("speechText")
                    if item.get("source") == "user-override" and item.get("speechText")
                    else item.get("term") or item.get("requestedText") or ""
                ),
                "term": item.get("term") or item.get("requestedText") or "",
                "audioFile": item.get("audioFile", ""),
                "useTextOverride": item.get("source") == "user-override" and bool(item.get("speechText")),
                "qualityTier": item.get("qualityTier", "fallback"),
                "synthesisStrategy": item.get("synthesisStrategy", "azure-native"),
                "audioReviewStatus": item.get("audioReviewStatus", "unreviewed"),
                "source": item.get("source", ""),
            }
        )

    def open_selected() -> None:
        item = selected_item()
        if item:
            _open_saved_origin(item)

    def remove_selected() -> None:
        item = selected_item()
        if not item or not _saved:
            return
        try:
            if _saved.remove_entry(saved_entry_key(item)):
                items[:] = _saved.load()
                refresh()
        except StorageError as exc:
            _record_runtime_diagnostic(str(exc))
            _show_text("PronounceIt saved pronunciations", _storage_error_text(exc))

    search.textChanged.connect(refresh)
    table.itemSelectionChanged.connect(update_buttons)
    play_button.clicked.connect(play_selected)
    open_button.clicked.connect(open_selected)
    remove_button.clicked.connect(remove_selected)
    close_button.clicked.connect(dialog.reject)

    refresh()
    if not items:
        dialog.resize(640, 320)
    if hasattr(dialog, "exec"):
        dialog.exec()
    else:
        dialog.exec_()


def _saved_entry_search_text(item: dict[str, Any]) -> str:
    parts = [
        item.get("term"),
        item.get("requestedText"),
        item.get("pronunciation"),
        item.get("syllables"),
        item.get("source"),
        item.get("deckName"),
    ]
    return " ".join(str(part) for part in parts if part).casefold()


def _saved_entry_details(item: dict[str, Any]) -> str:
    details = []
    syllables = item.get("syllables")
    source = item.get("source")
    deck_name = item.get("deckName")
    if syllables:
        details.append(f"Syllables: {syllables}")
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
        showInfo(f"Could not open the original card.\n\nSearch: {query}\n\n{exc}", title="PronounceIt")
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
    audit = audit_pronunciations()
    lines = [
        "PronounceIt dictionary audit",
        "",
        f"Status: {'PASS' if audit.passed else 'FAIL'}",
        f"Bundled dictionary terms: {audit.dictionary_terms}",
        f"High-yield checklist terms: {audit.checklist_terms}",
        f"Source lexicon terms: {audit.source_lexicon_terms}",
        f"Missing checklist terms: {len(audit.missing_terms)}",
        f"Missing source lexicon terms: {len(audit.missing_source_lexicon_terms)}",
        f"Missing pronunciations: {len(audit.missing_pronunciation)}",
        f"Missing syllables: {len(audit.missing_syllables)}",
        f"Missing TTS speech text: {len(audit.missing_speech_text)}",
        f"Missing high-yield bundled audio files: {len(audit.missing_audio_files)}",
        f"Legacy zero-frame placeholders excluded from packages: {audit.excluded_audio_placeholders}",
        f"Unsafe TTS speech text: {len(audit.unsafe_speech_text)}",
        f"Missing stress markers: {len(audit.missing_stress_marker)}",
        f"Source lexicon pronunciation mismatches: {len(audit.source_lexicon_pronunciation_mismatches)}",
        "Quality tiers: "
        + ", ".join(f"{tier}={count}" for tier, count in sorted(audit.quality_tiers.items())),
    ]
    if not audit.passed:
        lines.extend(["", "Missing terms:", *audit.missing_terms])
    _show_text("PronounceIt dictionary audit", "\n".join(lines))


def _pronounce_manually() -> None:
    term = _ask_for_term()
    if term:
        _show_manual_pronunciation(term)


def _add_or_update_custom_pronunciation() -> None:
    term = _ask_for_term()
    if not term:
        return
    current = _lookup_payload(term)
    pronunciation = _ask_for_text(
        "Student-friendly pronunciation:",
        default=str(current.get("pronunciation") or ""),
        title="Add custom pronunciation",
    )
    if not pronunciation:
        return
    syllables = _ask_for_text(
        "Syllables:",
        default=str(current.get("syllables") or ""),
        title="Add custom pronunciation",
    )
    if not syllables:
        return
    speech_text = _ask_for_text(
        "Speech text override (optional):",
        default=str(current.get("speechText") or ""),
        title="Add custom pronunciation",
        preserve_punctuation=True,
    )
    try:
        record = _save_custom_pronunciation(term, pronunciation, syllables, speech_text)
    except StorageError as exc:
        _record_runtime_diagnostic(str(exc))
        _show_text("PronounceIt", _storage_error_text(exc))
        return
    _show_text(
        "PronounceIt",
        "Custom pronunciation saved.\n\n"
        f"{record['term']}\n"
        f"Pronunciation: {record['pronunciation']}\n"
        f"Syllables: {record['syllables']}\n"
        f"Speech text: {record.get('speechText') or 'Derived from pronunciation'}",
    )


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
    syllables: str,
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
        ("Pronunciation", str(payload.get("pronunciation") or _config().unknown_term_message)),
    ]


def _show_pronunciation_details(payload: dict[str, Any], term: str) -> None:
    fields = _pronunciation_detail_fields(payload, term)
    try:
        from aqt import mw
        from aqt.qt import QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout

        dialog = QDialog(mw)
        dialog.setWindowTitle("Pronunciation details")
        dialog.setMinimumWidth(600)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(16)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(14)
        for label, value in fields:
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            try:
                from aqt.qt import Qt

                value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            except (AttributeError, ImportError):
                try:
                    value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                except Exception:
                    pass
            form.addRow(label, value_label)
        layout.addLayout(form)
        try:
            close_flag = QDialogButtonBox.StandardButton.Close
        except AttributeError:
            close_flag = QDialogButtonBox.Close
        buttons = QDialogButtonBox(close_flag)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if hasattr(dialog, "exec"):
            dialog.exec()
        else:
            dialog.exec_()
    except Exception:
        _show_text(
            "Pronunciation details",
            "\n\n".join(f"{label}\n{value}" for label, value in fields),
        )


def _show_manual_pronunciation(term: str) -> None:
    payload = _lookup_payload(term)
    _show_pronunciation_details(payload, term)
    _handle_speak(
        {
            "text": payload.get("synthesisText") or term,
            "term": payload.get("term") or term,
            "audioFile": payload.get("audioFile", ""),
            "useTextOverride": payload.get("source") == "user-override" and bool(payload.get("speechText")),
            "qualityTier": payload.get("qualityTier", "fallback"),
            "synthesisStrategy": payload.get("synthesisStrategy", "azure-native"),
            "audioReviewStatus": payload.get("audioReviewStatus", "unreviewed"),
        }
    )


def _show_audio_diagnostics() -> None:
    _show_text("PronounceIt playback diagnostics", _format_playback_diagnostics())


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
    try:
        from aqt.utils import showText

        showText(text, title=title)
        return
    except Exception:
        pass
    try:
        from aqt.utils import showInfo

        showInfo(text, title=title)
    except Exception:
        return


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

        mw.addonManager.writeConfig(_addon_module, next_config)
    except Exception:
        pass
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
    found = bool(result.get("found"))
    if (
        found
        and result.get("source") == "user-override"
        and audio_file
        and _audio_file_is_available(audio_file)
    ):
        result["audioSource"] = "custom"
        result["audioStatus"] = "Custom audio ready"
        result["audioHelp"] = "Play uses your custom audio file."
    elif found and audio_file and _audio_file_is_available(audio_file):
        result["audioSource"] = "recorded" if result.get("audioProvider") == "kokoro-local" else "azure"
        result["audioStatus"] = "High Quality Downloaded Pack ready"
        result["audioHelp"] = "Play uses High Quality Downloaded Pack audio."
    elif found and _audio_pack is not None and _audio_pack.status().installed:
        result["audioSource"] = "recorded" if result.get("audioProvider") == "kokoro-local" else "azure"
        result["audioStatus"] = "High Quality Downloaded Pack ready"
        result["audioHelp"] = "Play uses High Quality Downloaded Pack audio."
    elif config.audio_backend == "system_tts":
        result["audioSource"] = "live"
        result["audioStatus"] = "Standard text-to-speech ready"
        result["audioHelp"] = "Play uses your system voice."
    else:
        result["audioSource"] = "generated"
        result["audioStatus"] = "Standard text-to-speech ready"
        result["audioHelp"] = "Play uses standard text-to-speech when needed."
    result["audioSourceLabel"] = _audio_source_label(result["audioSource"])
    result["audioAvailable"] = True
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
    config = _config()
    if not config.enabled:
        return
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
    if audio_source not in {"custom", "azure", "recorded"} or not _audio_file_is_available(audio_file):
        audio_file = ""
    return {
        "text": result.get("synthesisText") or result.get("term") or result.get("requestedText") or "",
        "term": result.get("term") or result.get("requestedText") or "",
        "audioFile": audio_file,
        "useTextOverride": result.get("source") == "user-override" and bool(result.get("speechText")),
        "qualityTier": result.get("qualityTier", "fallback"),
        "synthesisStrategy": result.get("synthesisStrategy", "azure-native"),
        "audioReviewStatus": result.get("audioReviewStatus", "unreviewed"),
        "audioSource": audio_source,
        "audioSourceLabel": _audio_source_label(audio_source),
    }


def _handle_speak(payload: dict[str, Any], context: Any | None = None) -> bool:
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
