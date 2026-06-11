from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, PronounceItConfig
from .dictionary import PronunciationDictionary, display_term
from .qa import audit_pronunciations
from .storage import CustomPronunciations, SavedPronunciations, format_saved_entries, saved_entry_key
from .tts import (
    CommandTtsEngine,
    CompositeTtsEngine,
    GeneratedAudioFileEngine,
    LocalAudioFileEngine,
    QtTextToSpeechEngine,
    TtsSettings,
)


MESSAGE_PREFIX = "pronounceit:"
WEB_JS_FILE = Path("web") / "pronounceit.js"
WEB_CSS_FILE = Path("web") / "pronounceit.css"

_addon_module = ""
_addon_root: Path | None = None
_dictionary: PronunciationDictionary | None = None
_saved: SavedPronunciations | None = None
_custom: CustomPronunciations | None = None
_reviewer_answer_visible = False
_tts = CompositeTtsEngine()
_playback_diagnostics: list[dict[str, Any]] = []

_LOOKUP_START_SHORTCUT_MENU = "shortcut_context_menu"
_LOOKUP_START_SHORTCUT_ONLY = "shortcut_only"
_LOOKUP_START_OPTION_SELECT = "option_select"


def initialize(addon_module: str) -> None:
    global _addon_module, _addon_root, _dictionary, _saved, _custom, _tts
    _addon_module = addon_module
    _addon_root = Path(__file__).resolve().parent.parent
    _tts = CompositeTtsEngine(
        [
            LocalAudioFileEngine(_addon_root),
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

    mw.addonManager.setWebExports(addon_module, r"web/.*(css|js)")
    gui_hooks.webview_will_set_content.append(_on_webview_will_set_content)
    gui_hooks.webview_did_receive_js_message.append(_on_js_message)
    if hasattr(gui_hooks, "webview_will_show_context_menu"):
        gui_hooks.webview_will_show_context_menu.append(_on_webview_will_show_context_menu)
    if hasattr(gui_hooks, "reviewer_did_show_question"):
        gui_hooks.reviewer_did_show_question.append(_on_reviewer_show_question)
    if hasattr(gui_hooks, "reviewer_did_show_answer"):
        gui_hooks.reviewer_did_show_answer.append(_on_reviewer_show_answer)
    _install_config_action()
    _install_tools_menu_actions()


def _install_config_action() -> None:
    try:
        from aqt import mw
    except Exception:
        return

    try:
        mw.addonManager.setConfigAction(_addon_module, _show_config_dialog)
    except Exception:
        pass


def _install_tools_menu_actions() -> None:
    try:
        from aqt import mw
        from aqt.qt import QAction, QMenu
    except Exception:
        return

    pronounce_menu = QMenu("PronounceIt", mw)

    pronounce_action = QAction("Pronounce Current Selection", mw)
    pronounce_action.setShortcut(_config().hotkey.replace("Mod+", "Ctrl+"))
    pronounce_action.triggered.connect(_pronounce_current_reviewer_selection)
    pronounce_menu.addAction(pronounce_action)

    manual_action = QAction("Pronounce Manually...", mw)
    manual_action.triggered.connect(_pronounce_manually)
    pronounce_menu.addAction(manual_action)

    pronounce_menu.addSeparator()

    saved_action = QAction("Saved Pronunciations...", mw)
    saved_action.triggered.connect(_show_saved_pronunciations)
    pronounce_menu.addAction(saved_action)

    custom_action = QAction("Add or Update Custom Pronunciation...", mw)
    custom_action.triggered.connect(_add_or_update_custom_pronunciation)
    pronounce_menu.addAction(custom_action)

    audit_action = QAction("Dictionary Audit...", mw)
    audit_action.triggered.connect(_show_dictionary_audit)
    pronounce_menu.addAction(audit_action)

    pronounce_menu.addSeparator()

    config_action = QAction("Configure Add-on...", mw)
    config_action.triggered.connect(_show_config_dialog)
    pronounce_menu.addAction(config_action)

    mw.form.menuTools.addMenu(pronounce_menu)


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


def _add_modifier_items(combo: Any) -> None:
    for label, value in [
        ("Option/Alt", "alt"),
        ("Shift", "shift"),
        ("Command/Meta", "meta"),
        ("Control/Ctrl", "ctrl"),
        ("Mod (Ctrl or Command)", "mod"),
        ("Disabled", "disabled"),
    ]:
        combo.addItem(label, value)


def _modifier_display_name(value: str) -> str:
    return {
        "alt": "Option/Alt",
        "shift": "Shift",
        "meta": "Command/Meta",
        "ctrl": "Control/Ctrl",
        "mod": "Mod",
        "disabled": "Disabled",
    }.get(value, "Option/Alt")


def _behavior_preview_lines(config: PronounceItConfig) -> list[str]:
    audio_modifier = _modifier_display_name(config.direct_click_modifier)
    popup_modifier = _modifier_display_name(config.popup_click_modifier)
    audio_line = (
        "Audio-only lookup disabled"
        if config.direct_click_modifier == "disabled"
        else f"{audio_modifier} + left-click plays audio"
    )
    popup_line = (
        "Quick menu disabled"
        if config.popup_click_modifier == "disabled"
        else f"{popup_modifier} + right-click opens the quick menu"
    )
    return [
        f"{config.hotkey or DEFAULT_CONFIG['hotkey']} pronounces the current selection",
        audio_line,
        popup_line,
    ]


def _show_config_dialog() -> None:
    try:
        from aqt import mw
        from aqt.qt import (
            QCheckBox,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QFormLayout,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QSpinBox,
            QVBoxLayout,
        )
        from aqt.utils import showInfo
    except Exception:
        _show_text(
            "PronounceIt",
            "PronounceIt settings are available through the add-on config JSON.\n\n"
            "Saved words are stored in user_files/saved_pronunciations.json.",
        )
        return

    config = _config()
    dialog = QDialog(mw)
    dialog.setWindowTitle("PronounceIt Options")
    dialog.setObjectName("pronounceitOptions")
    dialog.setMinimumWidth(500)
    dialog.setStyleSheet(
        """
        QDialog#pronounceitOptions {
            background: #f7f9fb;
        }
        QDialog#pronounceitOptions QLabel#pronounceitIntro {
            color: #334155;
            font-size: 13px;
            line-height: 18px;
        }
        QDialog#pronounceitOptions QLabel#pronounceitHelp {
            color: #64748b;
            font-size: 12px;
            line-height: 16px;
        }
        QDialog#pronounceitOptions QLabel#pronounceitPreview {
            background: #eef7f8;
            border: 1px solid #c6dce3;
            border-radius: 8px;
            color: #17324a;
            font-size: 12px;
            line-height: 17px;
            padding: 10px 12px;
        }
        QDialog#pronounceitOptions QLabel#pronounceitSection {
            color: #0f172a;
            font-size: 12px;
            font-weight: 650;
            margin-top: 8px;
        }
        QDialog#pronounceitOptions QGroupBox {
            background: #ffffff;
            border: 1px solid #d7dee8;
            border-radius: 8px;
            font-weight: 650;
            margin-top: 14px;
            padding: 16px 12px 12px 12px;
        }
        QDialog#pronounceitOptions QGroupBox::title {
            color: #0f172a;
            left: 12px;
            padding: 0 4px;
            subcontrol-origin: margin;
        }
        QDialog#pronounceitOptions QLineEdit,
        QDialog#pronounceitOptions QComboBox,
        QDialog#pronounceitOptions QSpinBox {
            border: 1px solid #c7d0dd;
            border-radius: 6px;
            min-height: 28px;
            padding: 3px 8px;
        }
        QDialog#pronounceitOptions QLineEdit:focus,
        QDialog#pronounceitOptions QComboBox:focus,
        QDialog#pronounceitOptions QSpinBox:focus {
            border-color: #1f6f8b;
        }
        QDialog#pronounceitOptions QPushButton {
            border: 1px solid #c7d0dd;
            border-radius: 6px;
            min-height: 30px;
            padding: 5px 10px;
        }
        QDialog#pronounceitOptions QPushButton:hover {
            background: #eef6f8;
        }
        QDialog#pronounceitOptions QGroupBox#pronounceitAdvanced {
            background: #fbfcfe;
            border-color: #e2e8f0;
        }
        """
    )
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 18, 18, 14)
    layout.setSpacing(10)

    intro = QLabel(
        "Choose how PronounceIt appears while reviewing cards. "
        "Less common controls are under Advanced."
    )
    intro.setObjectName("pronounceitIntro")
    intro.setWordWrap(True)
    layout.addWidget(intro)

    preview = QLabel()
    preview.setObjectName("pronounceitPreview")
    preview.setWordWrap(True)
    layout.addWidget(preview)

    def make_form_group(title: str):
        group = QGroupBox(title)
        form = QFormLayout(group)
        form.setContentsMargins(10, 8, 10, 10)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(9)
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

    hotkey = QLineEdit(config.hotkey)
    hotkey.setPlaceholderText("Mod+P")
    hotkey.setToolTip(
        "Use Anki shortcut syntax. Mod maps to Ctrl on Windows/Linux and Cmd on macOS."
    )
    review_form.addRow("Keyboard shortcut", hotkey)

    direct_click = QComboBox()
    _add_modifier_items(direct_click)
    direct_click.setToolTip("Modifier for audio-only pronunciation while reviewing.")
    set_combo_data(direct_click, config.direct_click_modifier)
    review_form.addRow("Play audio with modifier + left-click", direct_click)

    popup_click = QComboBox()
    _add_modifier_items(popup_click)
    popup_click.setToolTip("Modifier for opening the pronunciation quick menu while reviewing.")
    set_combo_data(popup_click, config.popup_click_modifier)
    review_form.addRow("Open quick menu with modifier + right-click", popup_click)
    add_help(
        review_form,
        "Default: Option/Alt-left-click plays audio only; Option/Alt-right-click opens the quick menu.",
    )

    layout.addWidget(review_box)

    audio_box, audio_form = make_form_group("Audio")

    backend = QComboBox()
    backend.addItem("Use local audio, then system voice if needed", "local_audio_then_tts")
    backend.addItem("Use local audio only", "local_audio")
    backend.addItem("Use system voice only", "system_tts")
    backend.setToolTip(
        "Local audio uses bundled and generated clips. System voice is the operating system text-to-speech fallback."
    )
    backend_index = backend.findData(config.audio_backend)
    backend.setCurrentIndex(max(0, backend_index))
    audio_form.addRow("Audio behavior", backend)
    add_help(
        audio_form,
        "Recommended: use curated local clips first, generate a local clip when needed, then fall back to the system voice.",
    )

    layout.addWidget(audio_box)

    appearance_box, appearance_form = make_form_group("Appearance")
    theme = QComboBox()
    theme.addItem("System", "system")
    theme.addItem("Clinical Light", "clinical_light")
    theme.addItem("Slate", "slate")
    theme.addItem("High Contrast", "high_contrast")
    theme_index = theme.findData(config.theme)
    theme.setCurrentIndex(max(0, theme_index))
    appearance_form.addRow("Theme", theme)
    layout.addWidget(appearance_box)

    advanced_toggle = QPushButton("Show advanced settings")
    advanced_toggle.setCheckable(True)
    reset_button = QPushButton("Reset to defaults")
    toggle_row = QHBoxLayout()
    toggle_row.setSpacing(8)
    toggle_row.addWidget(advanced_toggle)
    toggle_row.addWidget(reset_button)
    layout.addLayout(toggle_row)

    advanced_box = QGroupBox("Advanced")
    advanced_box.setObjectName("pronounceitAdvanced")
    advanced_layout = QVBoxLayout(advanced_box)
    advanced_layout.setContentsMargins(10, 8, 10, 10)
    advanced_layout.setSpacing(10)
    advanced_box.setVisible(False)

    add_section(advanced_layout, "Study flow")
    study_form = QFormLayout()
    study_form.setHorizontalSpacing(16)
    study_form.setVerticalSpacing(9)
    allow_question = QCheckBox("Allow lookups before answer is shown")
    allow_question.setChecked(config.allow_on_question_side)
    allow_question.setToolTip("Disabled by default so pronunciation help stays answer-side during review.")
    study_form.addRow(allow_question)
    add_help(
        study_form,
        "Use this only if pronunciation help before reveal will not interfere with your study flow.",
    )
    advanced_layout.addLayout(study_form)

    add_section(advanced_layout, "Popup")
    popup_form = QFormLayout()
    popup_form.setHorizontalSpacing(16)
    popup_form.setVerticalSpacing(9)
    auto_close = QCheckBox("Close popup when the card changes")
    auto_close.setChecked(config.auto_close_on_card_change)
    popup_form.addRow(auto_close)

    show_save = QCheckBox("Show Save pronunciation in the quick menu")
    show_save.setChecked(config.show_save_button)
    popup_form.addRow(show_save)
    advanced_layout.addLayout(popup_form)

    add_section(advanced_layout, "Fallback voice")
    voice_form = QFormLayout()
    voice_form.setHorizontalSpacing(16)
    voice_form.setVerticalSpacing(9)
    voice = QLineEdit(config.tts_voice)
    voice.setPlaceholderText("System default")
    voice.setToolTip("Optional system voice name for generated and fallback speech.")
    voice_form.addRow("Voice", voice)

    rate = QSpinBox()
    rate.setRange(-10, 10)
    rate.setValue(config.tts_rate)
    rate.setToolTip("Applies where the system text-to-speech engine supports speed changes.")
    voice_form.addRow("Speed", rate)

    volume = QSpinBox()
    volume.setRange(0, 100)
    volume.setSuffix("%")
    volume.setValue(config.tts_volume)
    volume.setToolTip("Applies where the system text-to-speech engine supports volume changes.")
    voice_form.addRow("Volume", volume)
    advanced_layout.addLayout(voice_form)

    add_section(advanced_layout, "Files")
    button_row = QHBoxLayout()
    button_row.setSpacing(8)
    for label, target in [
        ("Saved List", _saved_pronunciations_path),
        ("Custom Pronunciations", _custom_pronunciations_path),
        ("Generated Audio", _generated_audio_dir),
        ("Add-on Folder", _addon_dir),
    ]:
        button = QPushButton(label)
        button.clicked.connect(lambda _checked=False, path_factory=target: _open_path(path_factory()))
        button_row.addWidget(button)
    advanced_layout.addLayout(button_row)
    layout.addWidget(advanced_box)

    def set_advanced_visible(visible: bool) -> None:
        advanced_box.setVisible(visible)
        advanced_toggle.setText("Hide advanced settings" if visible else "Show advanced settings")

    advanced_toggle.toggled.connect(set_advanced_visible)

    def current_preview_config() -> PronounceItConfig:
        return PronounceItConfig.from_mapping(
            {
                **config.as_config_mapping(),
                "hotkey": hotkey.text().strip() or DEFAULT_CONFIG["hotkey"],
                "direct_click_modifier": direct_click.currentData()
                or DEFAULT_CONFIG["direct_click_modifier"],
                "popup_click_modifier": popup_click.currentData()
                or DEFAULT_CONFIG["popup_click_modifier"],
            }
        )

    def update_preview(*_args) -> None:
        preview.setText("\n".join(_behavior_preview_lines(current_preview_config())))

    def reset_to_defaults(*_args) -> None:
        defaults = PronounceItConfig.from_mapping(DEFAULT_CONFIG)
        enabled.setChecked(defaults.enabled)
        hotkey.setText(defaults.hotkey)
        set_combo_data(direct_click, defaults.direct_click_modifier)
        set_combo_data(popup_click, defaults.popup_click_modifier)
        set_combo_data(backend, defaults.audio_backend)
        set_combo_data(theme, defaults.theme)
        allow_question.setChecked(defaults.allow_on_question_side)
        auto_close.setChecked(defaults.auto_close_on_card_change)
        show_save.setChecked(defaults.show_save_button)
        voice.setText(defaults.tts_voice)
        rate.setValue(defaults.tts_rate)
        volume.setValue(defaults.tts_volume)
        update_preview()

    hotkey.textChanged.connect(update_preview)
    direct_click.currentIndexChanged.connect(update_preview)
    popup_click.currentIndexChanged.connect(update_preview)
    reset_button.clicked.connect(reset_to_defaults)
    update_preview()

    try:
        button_flags = QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
    except AttributeError:
        button_flags = QDialogButtonBox.Save | QDialogButtonBox.Cancel
    buttons = QDialogButtonBox(button_flags)
    layout.addWidget(buttons)

    def save() -> None:
        next_config = {
            "enabled": enabled.isChecked(),
            "hotkey": hotkey.text().strip() or DEFAULT_CONFIG["hotkey"],
            "direct_click_modifier": direct_click.currentData() or DEFAULT_CONFIG["direct_click_modifier"],
            "popup_click_modifier": popup_click.currentData() or DEFAULT_CONFIG["popup_click_modifier"],
            "tts_voice": voice.text().strip(),
            "tts_rate": rate.value(),
            "tts_volume": volume.value(),
            "audio_backend": backend.currentData() or DEFAULT_CONFIG["audio_backend"],
            "auto_close_on_card_change": auto_close.isChecked(),
            "allow_on_question_side": allow_question.isChecked(),
            "activation_mode": "context_menu",
            "theme": theme.currentData() or DEFAULT_CONFIG["theme"],
            "show_context_menu": False,
            "show_save_button": show_save.isChecked(),
            "unknown_term_message": config.unknown_term_message,
        }
        _write_config(next_config)
        _send_reviewer_config()
        showInfo("PronounceIt options saved.")
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


def _show_saved_pronunciations() -> None:
    if not _saved:
        _show_text("PronounceIt Saved Pronunciations", "No saved pronunciations yet.")
        return
    items = _saved.load()
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
        _show_text("PronounceIt Saved Pronunciations", format_saved_entries(items))
        return

    dialog = QDialog(mw)
    dialog.setWindowTitle("PronounceIt Saved Pronunciations")
    dialog.setMinimumSize(720, 420)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(16, 16, 16, 14)
    layout.setSpacing(10)

    intro = QLabel("Saved words for pronunciations you want to revisit.")
    layout.addWidget(intro)

    search = QLineEdit()
    search.setPlaceholderText("Search saved words")
    layout.addWidget(search)

    empty = QLabel("Saved words will appear here after you use Save pronunciation from the quick menu.")
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
                "text": item.get("speechText") or item.get("term") or item.get("requestedText") or "",
                "term": item.get("term") or item.get("requestedText") or "",
                "audioFile": item.get("audioFile", ""),
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
        if _saved.remove_entry(saved_entry_key(item)):
            items[:] = _saved.load()
            refresh()

    search.textChanged.connect(refresh)
    table.itemSelectionChanged.connect(update_buttons)
    play_button.clicked.connect(play_selected)
    open_button.clicked.connect(open_selected)
    remove_button.clicked.connect(remove_selected)
    close_button.clicked.connect(dialog.reject)

    refresh()
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
        "PronounceIt Dictionary Audit",
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
        f"Missing bundled audio files: {len(audit.missing_audio_files)}",
        f"Unsafe TTS speech text: {len(audit.unsafe_speech_text)}",
        f"Missing stress markers: {len(audit.missing_stress_marker)}",
        f"Source lexicon pronunciation mismatches: {len(audit.source_lexicon_pronunciation_mismatches)}",
    ]
    if not audit.passed:
        lines.extend(["", "Missing terms:", *audit.missing_terms])
    _show_text("PronounceIt Dictionary Audit", "\n".join(lines))


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
        title="PronounceIt Custom Pronunciation",
    )
    if not pronunciation:
        return
    syllables = _ask_for_text(
        "Syllables:",
        default=str(current.get("syllables") or ""),
        title="PronounceIt Custom Pronunciation",
    )
    if not syllables:
        return
    speech_text = _ask_for_text(
        "Audio text override (optional):",
        default=str(current.get("speechText") or ""),
        title="PronounceIt Custom Pronunciation",
        preserve_punctuation=True,
    )
    record = _save_custom_pronunciation(term, pronunciation, syllables, speech_text)
    _show_text(
        "PronounceIt",
        "Custom pronunciation saved.\n\n"
        f"{record['term']}\n"
        f"Pronunciation: {record['pronunciation']}\n"
        f"Syllables: {record['syllables']}\n"
        f"Audio text: {record.get('speechText') or 'Derived from pronunciation'}",
    )


def _ask_for_term() -> str:
    try:
        from aqt.utils import getText

        text, ok = getText("Word or medical term:", title="PronounceIt")
        return display_term(text) if ok else ""
    except Exception:
        pass

    try:
        from aqt import mw
        from aqt.qt import QInputDialog

        text, ok = QInputDialog.getText(mw, "PronounceIt", "Word or medical term:")
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


def _show_manual_pronunciation(term: str) -> None:
    payload = _lookup_payload(term)
    lines = [
        payload.get("term") or payload.get("requestedText") or term,
        "",
        f"Pronunciation: {payload.get('pronunciation') or _config().unknown_term_message}",
        f"Syllables: {payload.get('syllables') or 'Unavailable'}",
        f"Audio text: {payload.get('speechText') or term}",
    ]
    _show_text("PronounceIt", "\n".join(lines))
    _handle_speak(
        {
            "text": payload.get("speechText") or term,
            "term": payload.get("term") or term,
            "audioFile": payload.get("audioFile", ""),
        }
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


def _on_webview_will_show_context_menu(webview: Any, menu: Any) -> None:
    return


def _pronounce_current_reviewer_selection() -> None:
    try:
        from aqt import mw
    except Exception:
        return
    reviewer = getattr(mw, "reviewer", None)
    if not _pronunciation_allowed():
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
        _handle_lookup(reviewer, {"text": selected_text, "rect": {}, "autoPlay": True})


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
    selected_text = display_term(str(payload.get("text", "")))
    context_text = str(payload.get("contextText") or "")
    if _dictionary and selected_text and context_text:
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
    return _lookup_payload(selected_text)


def _enrich_lookup_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    config = _config()
    audio_file = str(result.get("audioFile") or "")
    found = bool(result.get("found"))
    if found and audio_file and _audio_file_is_available(audio_file):
        result["audioKind"] = "bundled"
        result["audioStatus"] = "Bundled audio ready"
        result["audioHelp"] = "Play uses the curated local audio file for this term."
    elif config.audio_backend == "system_tts":
        result["audioKind"] = "system"
        result["audioStatus"] = "Audio ready"
        result["audioHelp"] = "Play uses system text-to-speech."
    else:
        result["audioKind"] = "generated"
        result["audioStatus"] = "Generated audio available"
        result["audioHelp"] = "Play creates or reuses a local audio file when possible."
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
            if resolved.is_file() and resolved.stat().st_size > 0:
                return True
        except OSError:
            continue
    return False


def _payload_is_saved(payload: dict[str, Any]) -> bool:
    if not _saved:
        return False
    try:
        return _saved.contains(payload)
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
        package = _addon_module
    if hasattr(web_content, "body"):
        web_content.body += _inline_reviewer_assets(config)
    else:
        web_content.css.append(f"/_addons/{package}/web/pronounceit.css")
        web_content.js.append(f"/_addons/{package}/web/pronounceit.js")


def _inline_reviewer_assets(config: PronounceItConfig) -> str:
    payload = json.dumps(_js_config_payload(config))
    css = _read_addon_asset(WEB_CSS_FILE)
    js = _read_addon_asset(WEB_JS_FILE)
    parts = [f"<script>window.PronounceItConfig = {payload};</script>"]
    if css:
        parts.append(f"<style>{css}</style>")
    if js:
        parts.append(f"<script>{js}</script>")
    return "".join(parts)


def _read_addon_asset(relative_path: Path) -> str:
    root = _addon_root or Path(__file__).resolve().parent.parent
    try:
        return (root / relative_path).read_text(encoding="utf-8")
    except Exception:
        return ""


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
    elif action == "menu":
        _handle_menu_lookup(context, payload)
    elif action == "speak":
        _handle_speak(payload, context)
    elif action == "save":
        _handle_save(context, payload)
    elif action == "ready":
        _send_config(context)
    return True, None


def _parse_message(message: str) -> tuple[str, dict[str, Any]]:
    body = message[len(MESSAGE_PREFIX) :]
    if ":" not in body:
        return body, {}
    action, raw_payload = body.split(":", 1)
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        payload = {}
    return action, payload


def _handle_lookup(context: Any, payload: dict[str, Any]) -> None:
    if not _pronunciation_allowed():
        _eval(context, "window.PronounceIt && window.PronounceIt.hide();")
        return
    result = _lookup_payload_from_request(payload)
    result["rect"] = payload.get("rect", {})
    result["config"] = _js_config_payload()
    result["autoPlay"] = bool(payload.get("autoPlay"))
    _eval(context, f"window.PronounceIt && window.PronounceIt.show({json.dumps(result)});")


def _handle_audio_lookup(context: Any, payload: dict[str, Any]) -> None:
    if not _pronunciation_allowed():
        _eval(context, "window.PronounceIt && window.PronounceIt.hide();")
        return
    result = _lookup_payload_from_request(payload)
    _handle_speak(
        {
            "text": result.get("speechText") or result.get("term") or result.get("requestedText") or "",
            "term": result.get("term") or result.get("requestedText") or "",
            "audioFile": result.get("audioFile", ""),
        },
        context,
    )


def _handle_menu_lookup(context: Any, payload: dict[str, Any]) -> None:
    if not _pronunciation_allowed():
        _eval(context, "window.PronounceIt && window.PronounceIt.hide();")
        return
    result = _lookup_payload_from_request(payload)
    result["rect"] = payload.get("rect", {})
    result["menuX"] = payload.get("menuX")
    result["menuY"] = payload.get("menuY")
    result["config"] = _js_config_payload()
    _eval(context, f"window.PronounceIt && window.PronounceIt.showMenu({json.dumps(result)});")


def _handle_speak(payload: dict[str, Any], context: Any | None = None) -> bool:
    text = display_term(str(payload.get("text") or payload.get("term") or ""))
    config = _config()
    settings = TtsSettings(
        voice=config.tts_voice,
        rate=config.tts_rate,
        volume=config.tts_volume,
        audio_backend=config.audio_backend,
        audio_file=str(payload.get("audioFile") or ""),
        term=display_term(str(payload.get("term") or "")),
    )
    result = _tts.speak_result(text, settings)
    _record_playback_diagnostic(text, settings, result)
    if context is not None:
        _send_spoken_result(context, result)
    return result.ok


def _record_playback_diagnostic(text: str, settings: TtsSettings, result: Any) -> None:
    _playback_diagnostics.append(
        {
            "text": text,
            "term": settings.term,
            "audioBackend": settings.audio_backend,
            "audioFile": settings.audio_file,
            "ok": bool(getattr(result, "ok", False)),
            "reason": str(getattr(result, "reason", "")),
            "attempts": list(getattr(result, "attempts", [])),
        }
    )
    del _playback_diagnostics[:-20]


def _send_spoken_result(context: Any, result: Any) -> None:
    payload = {
        "ok": bool(getattr(result, "ok", False)),
        "reason": str(getattr(result, "reason", "")),
    }
    _eval(context, f"window.PronounceIt && window.PronounceIt.spoken({json.dumps(payload)});")


def _handle_save(context: Any, payload: dict[str, Any]) -> None:
    if not _saved:
        return
    result = _saved.save_entry(_payload_with_origin(context, payload))
    js_payload = json.dumps(
        {
            "saved": result.saved,
            "duplicate": result.duplicate,
            "total": result.total,
            "alreadySaved": result.saved or result.duplicate,
        }
    )
    _eval(context, f"window.PronounceIt && window.PronounceIt.saved({js_payload});")


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
    payload = (config or _config()).as_js_payload()
    payload["answerVisible"] = _answer_visible()
    return payload


def _eval(context: Any, javascript: str) -> None:
    web = getattr(context, "web", None)
    if web is not None and hasattr(web, "eval"):
        web.eval(javascript)
