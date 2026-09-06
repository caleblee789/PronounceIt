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


from .ui_components import (
    SettingsCard, apply_fonts, button, column, disclosure, field, label, status, surface,
)


class Dialog(QDialog):
    """A contained editor with a fixed header/footer and one content region."""
    def __init__(self, title: str, parent=None, theme: str | None = None, scrollable: bool = True):
        super().__init__(parent or mw)
        self.setWindowTitle(title)
        self.setObjectName("pronounceitDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.theme = theme or getattr(parent, "theme", None) or core._config().theme
        self.setStyleSheet(dialog_qss(self.theme, self.objectName()))
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(0, 0, 0, 0)
        self.outer.setSpacing(0)
        header, header_layout = column("header")
        header_layout.setContentsMargins(24, 16, 24, 16)
        self.heading = label(title, "page_title")
        header_layout.addWidget(self.heading)
        self.outer.addWidget(header)
        body_widget, self.body = column("canvas")
        self.body.setContentsMargins(24, 20, 24, 20)
        self.body.setSpacing(16)
        if scrollable:
            self.body.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.scroll = QScrollArea()
            self.scroll.setWidgetResizable(True)
            self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.scroll.setFrameShape(QFrame.Shape.NoFrame)
            self.scroll.viewport().setProperty("role", "canvas")
            self.scroll.setWidget(body_widget)
            self.outer.addWidget(self.scroll, 1)
        else:
            self.scroll = None
            self.outer.addWidget(body_widget, 1)
        self.message = label()
        self.message.hide()
        self.body.addWidget(self.message)
        footer = surface("footer")
        self.footer = QHBoxLayout(footer)
        self.footer.setContentsMargins(24, 10, 24, 10)
        self.footer.setSpacing(8)
        self.outer.addWidget(footer)
        self.notice_timer = QTimer(self)
        self.notice_timer.setSingleShot(True)
        self.notice_timer.timeout.connect(lambda: status(self.message, ""))

    def fit(self, width: int, height: int) -> None:
        apply_fonts(self)
        screen = self.screen() or QApplication.primaryScreen()
        area = screen.availableGeometry()
        max_width, max_height = max(280, area.width() - 48), max(180, area.height() - 48)
        self.setMinimumSize(min(400, max_width), min(190, max_height))
        self.resize(min(width, max_width), min(height, max_height))
        parent = self.parentWidget()
        center = parent.frameGeometry().center() if parent else area.center()
        point = center - self.rect().center()
        point.setX(max(area.left(), min(point.x(), area.right() - self.width())))
        point.setY(max(area.top(), min(point.y(), area.bottom() - self.height())))
        self.move(point)

    def close_button(self) -> None:
        self.footer.addStretch()
        self.footer.addWidget(button("Close", self.reject))

    def set_theme(self, theme: str) -> None:
        self.theme = theme
        self.setStyleSheet(dialog_qss(theme, self.objectName()))
        apply_fonts(self)

    def show_feedback(self, text: str, error: bool = False) -> None:
        self.notice_timer.stop()
        status(self.message, text, error)
        if not error:
            self.notice_timer.start(3500)


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
    owner = parent or _settings
    if owner is not None and owner.isVisible() and hasattr(owner, "show_feedback"):
        owner.show_feedback(text, error)
        return
    # Background completion has no originating surface when Settings is closed.
    dialog = Dialog("PronounceIt", parent)
    dialog.body.addWidget(label(text, "error" if error else "success"))
    dialog.close_button()
    dialog.fit(440, 220)
    dialog.setModal(False)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.show()
    if not error:
        QTimer.singleShot(3500, dialog.close)
    # Keep its Python wrapper alive until Qt destroys the window.
    _feedback.append(dialog)
    dialog.destroyed.connect(lambda: _feedback.remove(dialog) if dialog in _feedback else None)


_feedback: list[Dialog] = []


def error_dialog(text: str, details: str, parent=None) -> None:
    dialog = Dialog("PronounceIt", parent)
    dialog.body.addWidget(label(text, "error"))
    technical(dialog.body, details)
    dialog.close_button()
    dialog.fit(500, 300)
    dialog.exec()


def play(payload: dict, target: QLabel) -> None:
    status(target, "Playing…")
    ok = core._handle_speak(core._playback_payload_from_lookup(payload))
    status(target, "Playback started." if ok else "Could not play this pronunciation. Check your audio settings or open Troubleshoot audio.", not ok)


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


class Result(SettingsCard):
    def __init__(self, payload: dict, parent=None):
        super().__init__("")
        if parent is not None:
            self.setParent(parent)
        self.layout = self.body
        term = str(payload.get("term") or payload.get("requestedText") or "")
        self.layout.addWidget(label(term, "title"))
        pronunciation = str(payload.get("pronunciation") or "")
        self.layout.addWidget(label("Written pronunciation", "secondary"))
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
        if payload.get("custom"):
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
        apply_fonts(dialog)
    search.clicked.connect(lambda: lookup())
    query.returnPressed.connect(lambda: lookup())
    dialog.close_button()
    dialog.fit(560, 360)
    if term:
        lookup(payload)
    else:
        results.addWidget(label("Enter a word or medical term to see its pronunciation.", "secondary"))
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
        custom = current.get("custom")
        if not speech.isModified():
            speech.setText(str(current.get("speechText") or "") if current.get("useTextOverride") else "")
        title = "Edit custom pronunciation" if custom else "Add custom pronunciation"
        dialog.setWindowTitle(title)
        dialog.heading.setText(title)
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
    dialog.fit(560, 420)
    term.setFocus()
    dialog.exec()


def show_saved(parent=None) -> None:
    dialog = Dialog("Saved pronunciations", parent, scrollable=False)
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
    view.setMinimumHeight(80)
    view.setAccessibleName("Saved pronunciations")
    dialog.body.addWidget(view, 1)
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
        play_button.setEnabled(bool(item and core._enrich_lookup_payload(item).get("audioAvailable")))
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
    dialog.fit(720, 520)
    dialog.exec()


def show_report(title: str, summary: str, details: str, parent=None, error: bool = False) -> None:
    dialog = Dialog(title, parent)
    dialog.body.addWidget(label(summary, "error" if error else "secondary"))
    technical(dialog.body, details)
    dialog.close_button()
    dialog.fit(590, 440)
    dialog.exec()


def show_library(parent=None) -> None:
    dialog = Dialog("Check pronunciation library", parent)
    heading = label("Checking library…", "section")
    dialog.body.addWidget(heading)
    detail = label("", "secondary")
    dialog.body.addWidget(detail)
    dialog.close_button()
    dialog.fit(540, 320)
    alive = {"value": True}
    dialog.finished.connect(lambda *_: alive.update(value=False))
    def finished(future):
        if not alive["value"]:
            return
        try:
            audit = future.result()
            heading.setText("Library check passed" if audit.passed else "The library needs attention")
            detail.setText(f"{audit.audio_terms:,} audio pronunciations · {audit.written_terms:,} written pronunciations" + ("" if audit.passed else " — open the details to see which files need attention."))
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
    dialog = Dialog("Download the audio library?")
    dialog.body.addWidget(label("Download all 95,902 audio pronunciations in one library (about 1.03 GiB). Written pronunciations are already included. The download runs in the background.", "secondary"))
    dialog.footer.addStretch()
    dialog.footer.addWidget(button("Not now", dialog.reject))
    dialog.footer.addWidget(button("Download library", dialog.accept, "primary"))
    dialog.fit(540, 260)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    try:
        core._complete_audio_pack_onboarding(accepted)
    except Exception as exc:
        core._record_runtime_diagnostic(str(exc))
        feedback("Could not save your download choice. Try again in Audio settings.", error=True)


from .settings import Settings


_settings: Settings | None = None
_settings_open_pending = False


def show_settings() -> None:
    """Let the native menu close before constructing any settings widgets."""
    global _settings_open_pending
    if _settings is not None:
        _settings.setFocus()
        return
    if _settings_open_pending:
        return
    _settings_open_pending = True
    QTimer.singleShot(0, _open_settings)


def _open_settings() -> None:
    # Retain the Anki-owned dialog and draft while allowing Show in Browse.
    # Forcing window activation here can switch macOS Spaces during menu exit.
    global _settings, _settings_open_pending
    _settings_open_pending = False
    if _settings is None:
        _settings = Settings()
        _settings.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        def closed(*_):
            global _settings
            _settings = None
        _settings.finished.connect(closed)
    _settings.show()
    _settings.setFocus()
