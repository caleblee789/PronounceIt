from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, PronounceItConfig
from .dictionary import PronunciationDictionary, display_term
from .qa import audit_pronunciations
from .storage import CustomPronunciations, SavedPronunciations, format_saved_entries
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
    layout = QVBoxLayout(dialog)

    intro = QLabel("Adjust PronounceIt behavior and open its local files.")
    intro.setWordWrap(True)
    layout.addWidget(intro)

    settings_box = QGroupBox("Settings")
    form = QFormLayout(settings_box)

    enabled = QCheckBox("Enable PronounceIt")
    enabled.setChecked(config.enabled)
    form.addRow(enabled)

    hotkey = QLineEdit(config.hotkey)
    hotkey.setPlaceholderText("Mod+P")
    form.addRow("Hotkey", hotkey)

    allow_question = QCheckBox("Allow pronunciation before showing the answer")
    allow_question.setChecked(config.allow_on_question_side)
    form.addRow(allow_question)

    show_context = QCheckBox("Show quick menu on right-click/control-click")
    show_context.setChecked(config.show_context_menu)
    form.addRow(show_context)

    show_save = QCheckBox("Show Add to pronunciation list")
    show_save.setChecked(config.show_save_button)
    form.addRow(show_save)

    auto_close = QCheckBox("Close popup when the card changes")
    auto_close.setChecked(config.auto_close_on_card_change)
    form.addRow(auto_close)

    backend = QComboBox()
    backend.addItem("Bundled/generated audio, then system TTS", "local_audio_then_tts")
    backend.addItem("Bundled/generated audio only", "local_audio")
    backend.addItem("System text-to-speech only", "system_tts")
    backend_index = backend.findData(config.audio_backend)
    backend.setCurrentIndex(max(0, backend_index))
    form.addRow("Audio", backend)

    voice = QLineEdit(config.tts_voice)
    voice.setPlaceholderText("System default")
    form.addRow("TTS voice", voice)

    rate = QSpinBox()
    rate.setRange(-10, 10)
    rate.setValue(config.tts_rate)
    form.addRow("TTS rate", rate)

    volume = QSpinBox()
    volume.setRange(0, 100)
    volume.setSuffix("%")
    volume.setValue(config.tts_volume)
    form.addRow("TTS volume", volume)

    layout.addWidget(settings_box)

    tools_box = QGroupBox("Files and Tools")
    tools_layout = QVBoxLayout(tools_box)
    button_row = QHBoxLayout()
    for label, target in [
        ("Saved List", _saved_pronunciations_path),
        ("Custom Pronunciations", _custom_pronunciations_path),
        ("Generated Audio", _generated_audio_dir),
        ("Add-on Folder", _addon_dir),
    ]:
        button = QPushButton(label)
        button.clicked.connect(lambda _checked=False, path_factory=target: _open_path(path_factory()))
        button_row.addWidget(button)
    tools_layout.addLayout(button_row)

    audit_button = QPushButton("Run Dictionary Audit")
    audit_button.clicked.connect(_show_dictionary_audit)
    tools_layout.addWidget(audit_button)
    layout.addWidget(tools_box)

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
            "tts_voice": voice.text().strip(),
            "tts_rate": rate.value(),
            "tts_volume": volume.value(),
            "audio_backend": backend.currentData() or DEFAULT_CONFIG["audio_backend"],
            "auto_close_on_card_change": auto_close.isChecked(),
            "allow_on_question_side": allow_question.isChecked(),
            "show_context_menu": show_context.isChecked(),
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
    _show_text("PronounceIt Saved Pronunciations", format_saved_entries(_saved.load()))


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
    try:
        from aqt import mw
    except Exception:
        return
    if getattr(mw, "state", None) != "review":
        return
    if not _pronunciation_allowed():
        return
    selected_text = _selected_text_from_webview(webview)
    if not selected_text:
        return
    play_action = menu.addAction("PronounceIt: Play")
    play_action.triggered.connect(
        lambda _checked=False, text=selected_text: _pronounce_text_from_reviewer(text)
    )
    payload = _lookup_payload(selected_text)
    if not payload.get("alreadySaved") and _config().show_save_button:
        save_action = menu.addAction("PronounceIt: Add to pronunciation list")
        save_action.triggered.connect(
            lambda _checked=False, text=selected_text: _save_text_from_reviewer(text)
        )


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


def _save_text_from_reviewer(selected_text: str) -> None:
    try:
        from aqt import mw
    except Exception:
        return
    reviewer = getattr(mw, "reviewer", None)
    if reviewer is not None and _pronunciation_allowed():
        _handle_lookup(reviewer, {"text": selected_text, "rect": {}, "saveAfterLookup": True})


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


def _enrich_lookup_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    config = _config()
    audio_file = str(result.get("audioFile") or "")
    found = bool(result.get("found"))
    if found and audio_file:
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
    elif action == "menu":
        _handle_menu_lookup(context, payload)
    elif action == "speak":
        _handle_speak(payload)
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
    selected_text = display_term(str(payload.get("text", "")))
    result = _lookup_payload(selected_text)
    result["rect"] = payload.get("rect", {})
    result["config"] = _js_config_payload()
    result["autoPlay"] = bool(payload.get("autoPlay"))
    result["saveAfterLookup"] = bool(payload.get("saveAfterLookup")) and not result.get("alreadySaved")
    _eval(context, f"window.PronounceIt && window.PronounceIt.show({json.dumps(result)});")


def _handle_menu_lookup(context: Any, payload: dict[str, Any]) -> None:
    if not _pronunciation_allowed():
        _eval(context, "window.PronounceIt && window.PronounceIt.hide();")
        return
    selected_text = display_term(str(payload.get("text", "")))
    result = _lookup_payload(selected_text)
    result["rect"] = payload.get("rect", {})
    result["menuX"] = payload.get("menuX")
    result["menuY"] = payload.get("menuY")
    result["config"] = _js_config_payload()
    _eval(context, f"window.PronounceIt && window.PronounceIt.showMenu({json.dumps(result)});")


def _handle_speak(payload: dict[str, Any]) -> None:
    text = display_term(str(payload.get("text") or payload.get("term") or ""))
    config = _config()
    _tts.speak(
        text,
        TtsSettings(
            voice=config.tts_voice,
            rate=config.tts_rate,
            volume=config.tts_volume,
            audio_backend=config.audio_backend,
            audio_file=str(payload.get("audioFile") or ""),
            term=display_term(str(payload.get("term") or "")),
        ),
    )


def _handle_save(context: Any, payload: dict[str, Any]) -> None:
    if not _saved:
        return
    result = _saved.save_entry(payload)
    js_payload = json.dumps(
        {
            "saved": result.saved,
            "duplicate": result.duplicate,
            "total": result.total,
            "alreadySaved": result.saved or result.duplicate,
        }
    )
    _eval(context, f"window.PronounceIt && window.PronounceIt.saved({js_payload});")


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
