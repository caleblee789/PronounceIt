"""PronounceIt-owned Qt surfaces. Imported lazily from the Anki entry points."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from aqt import mw
from aqt.qt import (
    QApplication, QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListView, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QSpinBox, QStandardItem, QStandardItemModel, QTabWidget, QTextEdit, QTimer,
    Qt, QVBoxLayout, QWidget,
)

from . import main as core
from .config import DEFAULT_CONFIG, PronounceItConfig
from .storage import StorageError, saved_entry_key
from .theme import dialog_qss, web_theme_tokens


def label(text: str = "", role: str = "") -> QLabel:
    result = QLabel(text)
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setWordWrap(True)
    result.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    result.setProperty("role", role)
    result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return result


def button(text: str, callback=None, role: str = "") -> QPushButton:
    result = QPushButton(text)
    result.setProperty("role", role)
    result.setAutoDefault(False)
    if callback:
        result.clicked.connect(lambda _checked=False: callback())
    return result


def status(target: QLabel, text: str, error: bool = False) -> None:
    target.setText(text)
    target.setProperty("role", "error" if error else "success")
    target.style().unpolish(target)
    target.style().polish(target)
    target.setVisible(bool(text))


class Dialog(QDialog):
    def __init__(self, title: str, parent=None, theme: str | None = None):
        super().__init__(parent or mw)
        self.setWindowTitle(title)
        self.setObjectName("pronounceitDialog")
        self.theme = theme or getattr(parent, "theme", None) or core._config().theme
        self.setStyleSheet(dialog_qss(self.theme, self.objectName()))
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(16, 16, 16, 16)
        self.outer.setSpacing(12)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(0, 0, 4, 0)
        self.body.setSpacing(12)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(body)
        self.outer.addWidget(self.scroll, 1)
        self.footer = QHBoxLayout()
        self.footer.setSpacing(8)
        self.outer.addLayout(self.footer)
        self.message = label()
        self.message.hide()
        self.body.addWidget(self.message)

    def fit(self, width: int, height: int) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        area = screen.availableGeometry()
        max_width, max_height = max(280, area.width() - 48), max(180, area.height() - 80)
        self.setMinimumSize(min(360, max_width), min(120, max_height))
        self.resize(min(width, max_width), min(height, max_height))
        self.move(area.center() - self.rect().center())

    def close_button(self) -> None:
        self.footer.addStretch()
        self.footer.addWidget(button("Close", self.reject))

    def set_theme(self, theme: str) -> None:
        self.theme = theme
        self.setStyleSheet(dialog_qss(theme, self.objectName()))


def disclosure(layout: QVBoxLayout, title: str, widget: QWidget) -> QPushButton:
    toggle = button("▸ " + title, role="quiet")
    toggle.setCheckable(True)
    toggle.setProperty("disclosure", True)
    toggle.setProperty("contentHeight", widget.sizeHint().height() + 8)
    toggle.setStyleSheet("text-align: left")
    widget.hide()
    growth = {"height": 0}
    def expand(opened):
        widget.setVisible(opened)
        toggle.setText(("▾ " if opened else "▸ ") + title)
        window = widget.window()
        if isinstance(window, QDialog):
            if opened:
                before = window.height()
                limit = window.screen().availableGeometry().height() - 80
                window.resize(window.width(), min(limit, before + widget.sizeHint().height() + 8))
                growth["height"] = window.height() - before
            else:
                window.resize(window.width(), window.height() - growth["height"])
    toggle.toggled.connect(expand)
    layout.addWidget(toggle)
    layout.addWidget(widget)
    return toggle


def column() -> tuple[QWidget, QVBoxLayout]:
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    return w, layout


def field(layout: QVBoxLayout, text: str, widget: QWidget, help_text: str = "") -> None:
    layout.addWidget(label(text, "section"))
    widget.setAccessibleName(text)
    layout.addWidget(widget)
    if help_text:
        layout.addWidget(label(help_text, "secondary"))


def section(layout: QVBoxLayout, text: str) -> None:
    if layout.count():
        line = QFrame()
        line.setProperty("role", "separator")
        layout.addWidget(line)
    layout.addWidget(label(text, "section"))


def technical(layout: QVBoxLayout, text: str) -> None:
    container, body = column()
    report = QTextEdit()
    report.setReadOnly(True)
    report.setPlainText(text)
    report.setMinimumHeight(110)
    report.setMaximumHeight(220)
    body.addWidget(report)
    copy = button("Copy details", lambda: QApplication.clipboard().setText(text), "quiet")
    body.addWidget(copy, 0, Qt.AlignmentFlag.AlignLeft)
    disclosure(layout, "Technical details", container)


def feedback(text: str, parent=None, error: bool = False) -> None:
    # A short, owned dialog avoids inheriting mismatched colors from Anki tooltips.
    dialog = Dialog("PronounceIt", parent)
    dialog.body.addWidget(label(text, "error" if error else "success"))
    dialog.close_button()
    dialog.fit(380, 130)
    dialog.setModal(False)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.show()
    QTimer.singleShot(2500 if not error else 6000, dialog.close)
    # Keep its Python wrapper alive until Qt destroys the window.
    _feedback.append(dialog)
    dialog.destroyed.connect(lambda: _feedback.remove(dialog) if dialog in _feedback else None)


_feedback: list[Dialog] = []


def error_dialog(text: str, details: str, parent=None) -> None:
    dialog = Dialog("PronounceIt", parent)
    dialog.body.addWidget(label(text, "error"))
    technical(dialog.body, details)
    dialog.close_button()
    dialog.fit(460, 190)
    dialog.exec()


def play(payload: dict, target: QLabel) -> None:
    status(target, "Playing…")
    ok = core._handle_speak(core._playback_payload_from_lookup(payload))
    status(target, "Played." if ok else "Could not play this pronunciation. Check your audio settings or open Troubleshoot audio.", not ok)


def save(payload: dict, target: QLabel, control: QPushButton) -> None:
    try:
        if core._saved is None:
            raise RuntimeError("Saved pronunciations are unavailable")
        result = core._saved.save_entry(payload)
        if result.saved or result.duplicate:
            control.setText("Saved")
            control.setEnabled(False)
            status(target, "")
        else:
            status(target, "Choose a term before saving.", True)
    except (StorageError, RuntimeError) as exc:
        core._record_runtime_diagnostic(str(exc))
        status(target, "Could not save. Your existing pronunciations are unchanged. See Troubleshoot audio for details.", True)


class Result(QWidget):
    def __init__(self, payload: dict, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(8)
        term = str(payload.get("term") or payload.get("requestedText") or "")
        self.layout.addWidget(label(term, "title"))
        pronunciation = str(payload.get("pronunciation") or "")
        self.layout.addWidget(label(pronunciation or "No pronunciation guide found", "pronunciation" if pronunciation else "secondary"))
        if not pronunciation and payload.get("audioAvailable"):
            self.layout.addWidget(label("You can still listen using the available audio.", "secondary"))
        row = QHBoxLayout()
        self.message = label()
        self.message.hide()
        play_button = button("Play", lambda: play(payload, self.message), "primary")
        play_button.setEnabled(bool(payload.get("audioAvailable", True)))
        row.addWidget(play_button)
        if core._config().show_save_button:
            saved = bool(payload.get("alreadySaved"))
            save_button = button("Saved" if saved else "Save")
            save_button.setEnabled(not saved)
            save_button.clicked.connect(lambda: save(payload, self.message, save_button))
            row.addWidget(save_button)
        row.addStretch()
        self.layout.addLayout(row)
        self.layout.addWidget(self.message)
        details, dl = column()
        dl.addWidget(label("Audio: " + str(payload.get("audioSourceLabel") or "Determined when played"), "secondary"))
        if payload.get("source") == "user-override":
            dl.addWidget(label("Custom pronunciation", "secondary"))
        disclosure(self.layout, "Details", details)


def show_search(term: str = "", payload: dict | None = None, parent=None) -> None:
    dialog = Dialog("Search pronunciation", parent)
    row = QHBoxLayout()
    query = QLineEdit(term)
    query.setPlaceholderText("Word or medical term")
    query.setAccessibleName("Word or medical term")
    query.setClearButtonEnabled(True)
    row.addWidget(query, 1)
    search = button("Search", role="primary")
    row.addWidget(search)
    dialog.body.addLayout(row)
    holder = QWidget()
    results = QVBoxLayout(holder)
    results.setContentsMargins(0, 0, 0, 0)
    dialog.body.addWidget(holder)
    def lookup(initial=None):
        value = core.display_term(query.text())
        if not value:
            status(dialog.message, "Enter a word or medical term.", True)
            query.setFocus()
            return
        status(dialog.message, "")
        while results.count():
            results.takeAt(0).widget().deleteLater()
        results.addWidget(Result(initial if initial is not None else core._lookup_payload(value)))
        if dialog.height() < 245:
            dialog.resize(dialog.width(), min(245, dialog.screen().availableGeometry().height() - 80))
    search.clicked.connect(lambda: lookup())
    query.returnPressed.connect(lambda: lookup())
    dialog.close_button()
    dialog.fit(500, 245 if term else 125)
    if term:
        lookup(payload)
    else:
        query.setFocus()
    dialog.exec()


def show_custom(parent=None) -> None:
    dialog = Dialog("Add custom pronunciation", parent)
    term, pronunciation, speech = QLineEdit(), QLineEdit(), QLineEdit()
    field(dialog.body, "Term", term)
    field(dialog.body, "Pronunciation", pronunciation, "Use capitals for stress, for example: my-oh-KAR-dee-ul.")
    extra, extra_layout = column()
    field(extra_layout, "Text read aloud (optional)", speech, "Leave blank to use the normal audio pronunciation.")
    disclosure(dialog.body, "Additional options", extra)
    loaded = {"term": ""}
    def populate():
        value = core.display_term(term.text())
        if not value or value == loaded["term"]:
            return
        current = core._lookup_payload(value)
        if not pronunciation.isModified():
            pronunciation.setText(str(current.get("pronunciation") or ""))
        custom = current.get("source") == "user-override"
        if not speech.isModified():
            speech.setText(str(current.get("speechText") or "") if custom else "")
        dialog.setWindowTitle("Edit custom pronunciation" if custom else "Add custom pronunciation")
        loaded["term"] = value
    term.editingFinished.connect(populate)
    def commit():
        name = core.display_term(term.text())
        guide = pronunciation.text().strip()
        if not name or not guide:
            status(dialog.message, "Enter a term and its pronunciation.", True)
            (term if not name else pronunciation).setFocus()
            return
        try:
            core._save_custom_pronunciation(name, guide, speech_text=speech.text().strip())
        except StorageError as exc:
            core._record_runtime_diagnostic(str(exc))
            status(dialog.message, "Could not save. Your changes are still here; check file permissions and try again.", True)
            return
        dialog.accept()
        feedback("Custom pronunciation saved.", parent)
    dialog.footer.addStretch()
    dialog.footer.addWidget(button("Cancel", dialog.reject))
    dialog.footer.addWidget(button("Save", commit, "primary"))
    dialog.fit(520, 260)
    term.setFocus()
    dialog.exec()


def show_saved(parent=None) -> None:
    dialog = Dialog("Saved pronunciations", parent)
    try:
        items = [core._current_saved_entry(item) for item in core._saved.load()] if core._saved else []
    except StorageError as exc:
        core._record_runtime_diagnostic(str(exc))
        error_dialog("Could not open saved pronunciations. Your existing file is unchanged.", str(exc), parent)
        return
    query = QLineEdit()
    query.setPlaceholderText("Search saved words")
    query.setAccessibleName("Search saved words")
    query.setClearButtonEnabled(True)
    dialog.body.addWidget(query)
    empty = label("No saved pronunciations yet.", "section")
    hint = label("Save a pronunciation from a quick card to find it here.", "secondary")
    clear = button("Clear search", query.clear, "quiet")
    dialog.body.addWidget(empty)
    dialog.body.addWidget(hint)
    dialog.body.addWidget(clear, 0, Qt.AlignmentFlag.AlignLeft)
    view = QListView()
    view.setWordWrap(True)
    view.setTextElideMode(Qt.TextElideMode.ElideNone)
    view.setResizeMode(QListView.ResizeMode.Adjust)
    view.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
    model = QStandardItemModel(view)
    view.setModel(model)
    dialog.body.addWidget(view)
    guide = label("", "pronunciation")
    dialog.body.addWidget(guide)
    play_button = button("Play", role="primary")
    browse = button("Show in Browse")
    remove = button("Remove", role="danger")
    dialog.footer.addWidget(play_button)
    dialog.footer.addWidget(browse)
    dialog.footer.addWidget(remove)
    dialog.close_button()
    visible: list[dict] = []
    def selected():
        index = view.currentIndex().row()
        return visible[index] if 0 <= index < len(visible) else None
    def update():
        item = selected()
        for control in (play_button, browse, remove):
            control.setVisible(bool(items))
        guide.setText(str(item.get("pronunciation") or "No pronunciation guide found") if item else "")
        guide.setVisible(bool(item))
        play_button.setEnabled(bool(item))
        browse.setEnabled(bool(item and core._saved_origin_search_query(item)))
        remove.setEnabled(bool(item))
    view.selectionModel().currentChanged.connect(lambda *_: update())
    def refresh():
        previous = saved_entry_key(selected() or {})
        needle = query.text().strip().casefold()
        view.selectionModel().blockSignals(True)
        model.clear()
        visible[:] = [item for item in items if not needle or needle in core._saved_entry_search_text(item)]
        for item in visible:
            date = ""
            try:
                date = datetime.fromisoformat(str(item.get("createdAt", ""))).strftime("%b %d, %Y")
            except ValueError:
                pass
            entry = QStandardItem(str(item.get("term") or item.get("requestedText")) + ("\nSaved " + date if date else ""))
            entry.setData(saved_entry_key(item), Qt.ItemDataRole.UserRole)
            entry.setEditable(False)
            model.appendRow(entry)
        view.selectionModel().blockSignals(False)
        view.setVisible(bool(visible))
        empty.setVisible(not visible)
        hint.setVisible(not visible and not needle)
        clear.setVisible(not visible and bool(needle))
        empty.setText(f'No matches for “{query.text().strip()}”.' if needle else "No saved pronunciations yet.")
        view.setFixedHeight(min(260, max(64, len(visible) * 60)))
        if visible:
            row = next((i for i, item in enumerate(visible) if saved_entry_key(item) == previous), 0)
            view.setCurrentIndex(model.index(row, 0))
        update()
    def remove_selected():
        item = selected()
        if not item:
            return
        try:
            core._saved.remove_entry(saved_entry_key(item))
            items[:] = [i for i in items if saved_entry_key(i) != saved_entry_key(item)]
            refresh()
        except StorageError as exc:
            core._record_runtime_diagnostic(str(exc))
            status(dialog.message, "Could not remove this pronunciation. Try again after checking file permissions.", True)
    play_button.clicked.connect(lambda: play(core._enrich_lookup_payload(selected()), dialog.message) if selected() else None)
    def show_origin():
        if selected() and core._open_saved_origin(selected()):
            dialog.accept()
    browse.clicked.connect(show_origin)
    remove.clicked.connect(remove_selected)
    query.textChanged.connect(refresh)
    refresh()
    dialog.fit(620, min(490, 178 + len(items) * 60) if items else 190)
    dialog.exec()


def show_report(title: str, summary: str, details: str, parent=None, error: bool = False) -> None:
    dialog = Dialog(title, parent)
    dialog.body.addWidget(label(summary, "error" if error else "secondary"))
    technical(dialog.body, details)
    dialog.close_button()
    dialog.fit(590, min(440, 160 + summary.count("\n") * 20))
    dialog.exec()


def show_library(parent=None) -> None:
    dialog = Dialog("Check pronunciation library", parent)
    heading = label("Checking library…", "section")
    dialog.body.addWidget(heading)
    detail = label("", "secondary")
    dialog.body.addWidget(detail)
    dialog.close_button()
    dialog.fit(500, 200)
    alive = {"value": True}
    dialog.finished.connect(lambda *_: alive.update(value=False))
    def finished(future):
        if not alive["value"]:
            return
        try:
            audit = future.result()
            heading.setText("Library check passed" if audit.passed else "The library needs attention")
            detail.setText(f"{audit.dictionary_terms:,} terms checked. " + ("PronounceIt is ready to use." if audit.passed else "Open the details to see which files need attention."))
            technical(dialog.body, json.dumps(audit.as_dict(), indent=2))
        except Exception as exc:
            heading.setText("Could not check the library")
            detail.setText("Try again. If the problem continues, reopen Anki.")
            technical(dialog.body, str(exc))
    mw.taskman.run_in_background(core.audit_pronunciations, finished)
    dialog.exec()


def show_diagnostics(parent=None) -> None:
    attempts = list(reversed(core._playback_diagnostics))
    lines = []
    if core._runtime_diagnostics:
        lines.append("Some data could not be read or updated. Your existing files were preserved.")
    for item in attempts[:5]:
        term = str(item.get("term") or item.get("text") or "Pronunciation")
        lines.append(term + " — " + ("Played" if item.get("ok") else "Could not play"))
        if item.get("ok"):
            lines.append(core._audio_source_label(item.get("audioSource")))
        else:
            lines.append("Check your audio settings and try again.")
        lines.append("")
    show_report("Troubleshoot audio", "\n".join(lines).strip() or "No audio has been played yet. Play a pronunciation, then return here if you need help.", core._format_playback_diagnostics(), parent)


def show_onboarding() -> None:
    dialog = Dialog("Offline pronunciations")
    dialog.body.addWidget(label("Download offline pronunciations?", "title"))
    dialog.body.addWidget(label("Add more recordings to listen without an internet connection. The download runs in the background.", "secondary"))
    dialog.footer.addStretch()
    dialog.footer.addWidget(button("Not now", dialog.reject))
    dialog.footer.addWidget(button("Download pack", dialog.accept, "primary"))
    dialog.fit(500, 175)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    core._complete_audio_pack_onboarding(accepted)


class Settings(Dialog):
    def __init__(self):
        super().__init__("PronounceIt settings")
        self.config = core._config()
        self.controls: dict[str, Any] = {}
        self.tabs = QTabWidget()
        self.outer.removeWidget(self.scroll)
        self.scroll.hide()
        self.outer.insertWidget(0, self.tabs, 1)
        self.review = self.page("Review")
        self.audio = self.page("Audio")
        self.tools = self.page("Tools")
        self.footer.addWidget(button("Restore defaults", self.restore, "quiet"))
        self.footer.addWidget(button("Support", core._open_support_url, "quiet"))
        self.footer.addStretch()
        self.footer.addWidget(button("Cancel", self.reject))
        self.footer.addWidget(button("Save", self.commit, "primary"))
        self.settings_message = label()
        self.settings_message.hide()
        self.outer.insertWidget(1, self.settings_message)
        self.build_review()
        self.build_audio()
        self.build_tools()
        self.load(self.config)
        self.fit(660, 550)
        self.tabs.currentChanged.connect(self.fit_tab)
        self.finished.connect(lambda *_: core._send_reviewer_config())

    def fit_tab(self, index):
        page = self.tabs.widget(index).widget()
        extra = sum(int(item.property("contentHeight") or 0) for item in page.findChildren(QPushButton) if item.property("disclosure") and item.isChecked())
        height = (550, 450, 370)[index] + extra
        self.resize(self.width(), min(height, self.screen().availableGeometry().height() - 80))

    def page(self, name):
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        widget, layout = column()
        layout.setContentsMargins(2, 16, 8, 8)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        area.setWidget(widget)
        self.tabs.addTab(area, name)
        return layout

    def check(self, layout, key, text):
        check = QCheckBox(text)
        self.controls[key] = check
        layout.addWidget(check)
        return check

    def combo(self, layout, key, title, choices):
        combo = QComboBox()
        for text, value in choices:
            combo.addItem(text, value)
        self.controls[key] = combo
        field(layout, title, combo)
        return combo

    def build_review(self):
        self.check(self.review, "enabled", "Enable PronounceIt").toggled.connect(self.dependencies)
        section(self.review, "Shortcuts")
        self.shortcut_help = {}
        for key, text in [("direct_click_modifier", "Play audio"), ("native_context_menu_modifier", "Open quick card")]:
            combo = QComboBox()
            core._add_activation_modifier_items(combo)
            self.controls[key] = combo
            row = QHBoxLayout()
            row.addWidget(label(text), 1)
            row.addWidget(combo)
            self.review.addLayout(row)
            help_label = label("", "secondary")
            self.shortcut_help[key] = help_label
            self.review.addWidget(help_label)
            combo.currentIndexChanged.connect(self.dependencies)
        how, hl = column()
        hl.addWidget(label("Hold your chosen key while clicking or selecting a term, or select text first and tap the key. Plain right-click keeps Anki’s menu.", "secondary"))
        disclosure(self.review, "How to use", how)
        section(self.review, "Review behavior")
        self.check(self.review, "show_native_context_menu", "Show quick card").toggled.connect(self.dependencies)
        self.check(self.review, "allow_on_question_side", "Allow pronunciation before revealing the answer")
        self.check(self.review, "auto_close_on_card_change", "Close quick card when changing cards")
        self.check(self.review, "show_save_button", "Show Save button")
        row = QHBoxLayout()
        row.addWidget(label("Appearance"), 1)
        theme = QComboBox()
        theme.addItem("Light", "light")
        theme.addItem("Dark", "dark")
        self.controls["theme"] = theme
        row.addWidget(theme)
        self.review.addLayout(row)
        theme.currentIndexChanged.connect(self.preview)

    def build_audio(self):
        mode = self.combo(self.audio, "audio_backend", "Play using", [("Recordings, then computer voice", "local_audio_then_tts"), ("Recordings only", "local_audio"), ("Computer voice only", "system_tts")])
        self.audio.addWidget(label("Recordings include audio bundled with PronounceIt, your recordings, and the optional pack.", "secondary"))
        mode.currentIndexChanged.connect(self.dependencies)
        section(self.audio, "Offline pronunciation pack")
        self.pack_status = label("", "section")
        self.audio.addWidget(self.pack_status)
        self.pack_help = label("", "secondary")
        self.audio.addWidget(self.pack_help)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.audio.addWidget(self.progress)
        row = QHBoxLayout()
        self.pack_buttons = {}
        for action in ["Download pack", "Pause", "Cancel download", "Check files", "Remove"]:
            control = button(action, lambda a=action: self.pack_action(a), "primary" if action == "Download pack" else "danger" if action == "Remove" else "")
            self.pack_buttons[action] = control
            row.addWidget(control)
        row.addStretch()
        self.audio.addLayout(row)
        section(self.audio, "Computer voice")
        row = QHBoxLayout()
        row.addWidget(label("Volume"), 1)
        volume = QSpinBox()
        volume.setRange(0, 100)
        volume.setSuffix("%")
        self.controls["tts_volume"] = volume
        row.addWidget(volume)
        self.audio.addLayout(row)
        voice_options, vl = column()
        voice = QLineEdit()
        voice.setPlaceholderText("Use computer default")
        self.controls["tts_voice"] = voice
        field(vl, "Voice name", voice)
        # The existing scale is preserved. Show its neutral value without jargon.
        class Speed(QSpinBox):
            def textFromValue(self, value):
                return "Normal" if value == 0 else str(value)
            def valueFromText(self, text):
                return 0 if text.strip().casefold() == "normal" else super().valueFromText(text)
        rate = Speed()
        rate.setRange(-10, 10)
        self.controls["tts_rate"] = rate
        field(vl, "Speaking speed", rate, "Some voices use their own speed and volume.")
        disclosure(self.audio, "Voice options", voice_options)
        self.pack_timer = QTimer(self)
        self.pack_timer.timeout.connect(self.refresh_pack)
        self.pack_timer.start(400)
        self.finished.connect(self.pack_timer.stop)
        self.refresh_pack()

    def build_tools(self):
        for heading, entries in [
            ("Pronunciations", [("Search", lambda: show_search(parent=self)), ("Saved pronunciations", lambda: show_saved(self)), ("Add custom pronunciation", lambda: show_custom(self))]),
            ("Help", [("Check library", lambda: show_library(self)), ("Troubleshoot audio", lambda: show_diagnostics(self))]),
        ]:
            section(self.tools, heading)
            row = QHBoxLayout()
            for title, callback in entries:
                row.addWidget(button(title, callback))
            row.addStretch()
            self.tools.addLayout(row)
        self.selection_button = button("Play selected text", core._pronounce_current_reviewer_selection, "quiet")
        self.tools.addWidget(self.selection_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.selection_help = label("Select a term in the reviewer to use this action.", "secondary")
        self.tools.addWidget(self.selection_help)
        reviewer = getattr(mw, "reviewer", None)
        selected = core._selected_text_from_webview(getattr(reviewer, "web", None)) if reviewer else ""
        self.selection_button.setEnabled(bool(selected and mw.state == "review"))
        self.selection_help.setVisible(not self.selection_button.isEnabled())
        files, fl = column()
        for title, target in [("Saved pronunciations file", core._saved_pronunciations_path), ("Custom pronunciations file", core._custom_pronunciations_path), ("Computer voice audio folder", core._generated_audio_dir), ("PronounceIt folder", core._addon_dir)]:
            fl.addWidget(button(title, lambda t=target: core._open_path(t()), "quiet"), 0, Qt.AlignmentFlag.AlignLeft)
        disclosure(self.tools, "Files", files)

    def load(self, config):
        for key, control in self.controls.items():
            value = getattr(config, key)
            if isinstance(control, QCheckBox):
                control.setChecked(value)
            elif isinstance(control, QComboBox):
                control.setCurrentIndex(max(0, control.findData(core._activation_modifier_ui_value(value) if key in {"direct_click_modifier", "native_context_menu_modifier"} else value)))
            elif isinstance(control, QSpinBox):
                control.setValue(value)
            else:
                control.setText(value)
        self.dependencies()
        self.preview()

    def dependencies(self):
        if "theme" not in self.controls or "tts_voice" not in self.controls:
            return
        enabled = self.controls["enabled"].isChecked()
        popup = enabled and self.controls["show_native_context_menu"].isChecked()
        for key in ["direct_click_modifier", "show_native_context_menu", "allow_on_question_side"]:
            self.controls[key].setEnabled(enabled)
        for key in ["native_context_menu_modifier", "auto_close_on_card_change", "show_save_button"]:
            self.controls[key].setEnabled(popup)
        for key, help_label in self.shortcut_help.items():
            combo = self.controls[key]
            help_label.setText("Shortcut is off." if combo.currentData() == "disabled" else f"Select text, then tap {combo.currentText()}.")
        voice = self.controls["audio_backend"].currentData() != "local_audio"
        for key in ["tts_voice", "tts_rate", "tts_volume"]:
            self.controls[key].setEnabled(voice)

    def preview(self):
        if "theme" not in self.controls:
            return
        self.set_theme(self.controls["theme"].currentData() or self.config.theme)
        reviewer = getattr(mw, "reviewer", None)
        if reviewer and getattr(reviewer, "web", None):
            data = {"theme": self.theme, "themeTokens": web_theme_tokens(self.theme)}
            core._eval(reviewer, "window.PronounceIt && window.PronounceIt.configure(" + json.dumps(data) + ");")

    def restore(self):
        defaults = {**DEFAULT_CONFIG, "theme": core._current_anki_theme(), "theme_initialized": True, "audio_pack_prompt_seen": self.config.audio_pack_prompt_seen}
        self.load(PronounceItConfig.from_mapping(defaults))

    def commit(self):
        values = self.config.as_config_mapping()
        for key, control in self.controls.items():
            values[key] = control.isChecked() if isinstance(control, QCheckBox) else control.currentData() if isinstance(control, QComboBox) else control.value() if isinstance(control, QSpinBox) else control.text().strip()
        values["theme_initialized"] = True
        # Pack operations may have completed onboarding while this draft was open.
        values["audio_pack_prompt_seen"] = core._config().audio_pack_prompt_seen
        try:
            core._write_config(values)
        except Exception as exc:
            core._record_runtime_diagnostic(str(exc))
            status(self.settings_message, "Could not save settings. Please try again.", True)
            return
        self.accept()
        feedback("Settings saved.")

    def refresh_pack(self):
        controller = core._audio_pack_download
        if controller is None:
            self.pack_status.setText("Pack unavailable")
            return
        state = controller.refresh()
        self.pack_state = state
        view = core._pack_presentation(state)
        self.pack_status.setText(view.status.replace("Verifying", "Checking files"))
        self.progress.setVisible(view.progress_visible)
        self.progress.setRange(0, 0 if view.progress_indeterminate else 100)
        self.progress.setValue(view.progress_percent)
        help_text = "Add more recordings to listen offline."
        if state.phase == "paused":
            help_text = "Resume whenever you’re ready. Downloaded files are kept."
        elif state.phase == "verifying":
            help_text = "Checking downloaded files. This may take a moment."
        elif state.phase == "cancelling":
            help_text = "Stopping the download. Downloaded files will be kept."
        elif state.running:
            help_text = "The download continues when you close settings."
        elif state.phase == "failed":
            help_text = "The download could not finish. Check your connection and available disk space, then try again."
        elif state.phase == "cancelled":
            help_text = "Resume to finish the download. Downloaded files are kept."
        elif state.installed:
            help_text = "Ready to use. Your recordings stay installed when PronounceIt updates."
        self.pack_help.setText(help_text)
        for control in self.pack_buttons.values():
            control.hide()
        start = self.pack_buttons["Download pack"]
        if not state.running:
            start.setText("Update" if state.installed else "Resume" if state.total_bytes or state.total_shards else "Retry" if state.phase == "failed" else "Download pack")
            start.show()
            if state.installed or state.total_shards:
                self.pack_buttons["Check files"].show()
                self.pack_buttons["Remove"].show()
        else:
            if state.phase in {"downloading", "paused"}:
                pause = self.pack_buttons["Pause"]
                pause.setText("Resume" if state.paused else "Pause")
                pause.show()
            if state.phase in {"preparing", "downloading", "paused"}:
                self.pack_buttons["Cancel download"].show()

    def pack_action(self, action):
        controller = core._audio_pack_download
        if controller is None:
            return
        try:
            if action == "Download pack":
                core._complete_audio_pack_onboarding(True)
            elif action == "Pause":
                controller.resume() if self.pack_state.paused else controller.pause()
            elif action == "Cancel download":
                controller.cancel()
            elif action == "Check files":
                controller.start_verify()
            elif action == "Remove":
                confirm = Dialog("Remove pronunciation pack?", self)
                confirm.body.addWidget(label("This removes the downloaded pack. Your saved words and custom pronunciations stay available."))
                confirm.footer.addStretch()
                confirm.footer.addWidget(button("Keep pack", confirm.reject))
                confirm.footer.addWidget(button("Remove pack", confirm.accept, "danger"))
                confirm.fit(460, 190)
                if confirm.exec() == QDialog.DialogCode.Accepted:
                    controller.remove()
        except Exception as exc:
            core._record_runtime_diagnostic(str(exc))
            status(self.settings_message, "Could not complete this action. Open Troubleshoot audio for details.", True)
        self.refresh_pack()


_settings: Settings | None = None


def show_settings() -> None:
    # Keep one settings draft while allowing Browse to open from the saved list.
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        def closed(*_):
            global _settings
            _settings = None
        _settings.finished.connect(closed)
    _settings.show()
    _settings.raise_()
    _settings.activateWindow()
