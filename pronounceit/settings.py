"""Dashboard-derived settings workspace; pronunciation services stay in main."""
from __future__ import annotations

import json
from typing import Any

from aqt import mw
from aqt.qt import (
    QAbstractButton, QApplication, QComboBox, QDialog, QEvent, QGridLayout,
    QHBoxLayout, QIcon, QLabel, QLineEdit, QListWidget, QProgressBar, QPushButton,
    QScrollArea, QSettings, QSize, QSizePolicy, QSlider, QSpinBox,
    QStackedWidget, QTimer, QVBoxLayout, QWidget, Qt,
)

from . import main as core
from .config import DEFAULT_CONFIG, PronounceItConfig
from .theme import dialog_qss, web_theme_tokens
from .ui_components import (
    ActivityIndicator, CardGrid, FieldRow, SettingsCard, SettingsSwitch,
    ValueSlider, apply_fonts, button, column, disclosure, field, label,
    status, surface,
)


class Settings(QDialog):
    SECTIONS = (
        ("Review", "Choose how pronunciation works while you study."),
        ("Audio", "Choose your playback source and manage the audio library."),
        ("Tools", "Find, save, and customize pronunciations."),
        ("About & support", "About PronounceIt, your local files, and support."),
    )
    GEOMETRY_KEY = "pronounceit/settings/geometry-v1"

    def __init__(self):
        super().__init__(mw)
        self.setObjectName("pronounceitSettings")
        self.setWindowTitle("PronounceIt settings")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.config = core._config()
        self.theme = self.config.theme
        self.controls: dict[str, Any] = {}
        self._loading = True
        self._closing = False
        self._prompt = None
        self._footer_compact = None
        self.setStyleSheet(dialog_qss(self.theme, self.objectName()))
        self._build_shell()
        self.build_review()
        self.build_audio()
        self.build_tools()
        self.build_about()
        self.load(self.config)
        for control in self.controls.values():
            if isinstance(control, QAbstractButton):
                control.toggled.connect(self.changed)
            elif isinstance(control, QComboBox):
                control.currentIndexChanged.connect(self.changed)
            elif isinstance(control, (QSpinBox, QSlider)):
                control.valueChanged.connect(self.changed)
            else:
                control.textChanged.connect(self.changed)
        self.saved_timer = QTimer(self)
        self.saved_timer.setSingleShot(True)
        self.saved_timer.setInterval(3500)
        self.saved_timer.timeout.connect(self.update_dirty)
        self.pack_timer = QTimer(self)
        self.pack_timer.timeout.connect(self.refresh_pack)
        self.pack_timer.start(400)
        self.finished.connect(self.pack_timer.stop)
        self.finished.connect(lambda *_: core._send_reviewer_config())
        self._initial_geometry()
        self.navigate(0)
        self.refresh_pack()

    def _build_shell(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.workspace_stack = QStackedWidget()
        outer.addWidget(self.workspace_stack)
        self.workspace = surface("canvas")
        self.workspace_stack.addWidget(self.workspace)
        grid = QGridLayout(self.workspace)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(1, 1)
        self.sidebar, sidebar = column("sidebar")
        self.sidebar.setFixedWidth(184)
        sidebar.setContentsMargins(16, 20, 16, 16)
        sidebar.setSpacing(8)
        sidebar.addWidget(label("PronounceIt", "brand"))
        sidebar.addWidget(label("Pronunciation for Anki", "secondary"))
        sidebar.addSpacing(12)
        self.nav = QListWidget()
        self.nav.setObjectName("pronounceitNav")
        self.nav.setAccessibleName("Settings sections")
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for title, _ in self.SECTIONS:
            self.nav.addItem(title)
        sidebar.addWidget(self.nav, 1)
        grid.addWidget(self.sidebar, 0, 0, 4, 1)
        self.header, header = column("header")
        header.setContentsMargins(24, 12, 24, 12)
        header.setSpacing(4)
        self.header.setMinimumHeight(72)
        self.page_title = label("", "page_title")
        self.page_help = label("", "secondary")
        header.addWidget(self.page_title)
        header.addWidget(self.page_help)
        self.compact_nav = QComboBox()
        self.compact_nav.setAccessibleName("Settings sections")
        self.compact_nav.addItems([title for title, _ in self.SECTIONS])
        self.compact_row = FieldRow("Section", self.compact_nav)
        self.compact_row.hide()
        header.addWidget(self.compact_row)
        grid.addWidget(self.header, 0, 1)
        self.pages = QStackedWidget()
        self.pages.setMinimumWidth(0)
        grid.addWidget(self.pages, 1, 1)
        self.page_layouts = [self.page() for _ in self.SECTIONS]
        self.error_region, errors = column("canvas")
        errors.setContentsMargins(24, 8, 24, 8)
        self.settings_message = label("", "error")
        self.settings_message.setAccessibleName("Settings error")
        errors.addWidget(self.settings_message)
        self.error_region.hide()
        grid.addWidget(self.error_region, 2, 1)
        self.footer = surface("footer")
        self.footer.setMinimumHeight(56)
        self.footer_grid = QGridLayout(self.footer)
        self.footer_grid.setContentsMargins(16, 8, 16, 8)
        self.footer_grid.setHorizontalSpacing(8)
        self.footer_grid.setVerticalSpacing(6)
        self.donate = button("", core._open_support_url, "quiet")
        self.donate.setAccessibleName("Buy Me a Coffee")
        self.donate.setToolTip("Donate to support the creator")
        asset = core._addon_dir() / "pronounceit" / "assets" / core.SUPPORT_IMAGE_NAME
        if asset.exists():
            self.donate.setIcon(QIcon(str(asset)))
            self.donate.setIconSize(QSize(98, 28))
            self.donate.setFixedSize(106, 36)
        else:
            self.donate.setText("Buy me a coffee")
        self.footer_status = label("", "secondary")
        self.footer_status.setAccessibleName("Settings save status")
        self.discard_button = button("Discard changes", self.discard, "quiet")
        self.close_control = button("Close", self.request_close)
        self.save_control = button("Save changes", self.commit, "primary")
        self.save_control.setAccessibleDescription("Apply all changes without closing settings.")
        self.save_control.setMinimumWidth(124)
        self._arrange_footer(False)
        grid.addWidget(self.footer, 3, 1)
        self.nav.currentRowChanged.connect(self.navigate)
        self.compact_nav.currentIndexChanged.connect(self.navigate)

    def page(self):
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.viewport().setProperty("role", "canvas")
        widget, body = column("page")
        body.setContentsMargins(24, 24, 24, 24)
        body.setSpacing(16)
        body.setAlignment(Qt.AlignmentFlag.AlignTop)
        area.setWidget(widget)
        self.pages.addWidget(area)
        return body

    def _arrange_footer(self, compact):
        if self._footer_compact == compact:
            return
        self._footer_compact = compact
        widgets = [self.donate, self.footer_status, self.discard_button, self.close_control, self.save_control]
        for widget in widgets:
            self.footer_grid.removeWidget(widget)
        self.footer_grid.setColumnStretch(1, 1)
        self.footer_grid.addWidget(self.donate, 0, 0)
        self.footer_grid.addWidget(self.close_control, 0, 3)
        self.footer_grid.addWidget(self.save_control, 0, 4)
        if compact:
            self.footer_grid.addWidget(self.footer_status, 1, 0, 1, 3)
            self.footer_grid.addWidget(self.discard_button, 1, 3, 1, 2)
        else:
            self.footer_grid.addWidget(self.footer_status, 0, 1)
            self.footer_grid.addWidget(self.discard_button, 0, 2)

    def navigate(self, index):
        if not 0 <= index < len(self.SECTIONS):
            return
        for widget, setter in [(self.nav, self.nav.setCurrentRow), (self.compact_nav, self.compact_nav.setCurrentIndex)]:
            widget.blockSignals(True)
            setter(index)
            widget.blockSignals(False)
        self.pages.setCurrentIndex(index)
        self.page_title.setText(self.SECTIONS[index][0])
        self.page_help.setText(self.SECTIONS[index][1])
        self.update_selection()

    def _initial_geometry(self):
        available = self.screen().availableGeometry()
        width, height = max(280, available.width() - 48), max(180, available.height() - 48)
        self.setMinimumSize(min(860, width), min(640, height))
        self.resize(min(1080, width), min(760, height))
        saved = QSettings().value(self.GEOMETRY_KEY)
        if saved:
            self.restoreGeometry(saved)
        self.resize(min(self.width(), width), min(self.height(), height))
        if not saved or not available.contains(self.frameGeometry()):
            self.move(available.center() - self.rect().center())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "sidebar"):
            return
        compact = self.width() < 860
        self.sidebar.setVisible(not compact)
        self.compact_row.setVisible(compact)
        self._arrange_footer(self.width() - (0 if compact else 184) < 680)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.ApplicationFontChange:
            apply_fonts(self)

    def check(self, card, key, text, help_text=""):
        control = SettingsSwitch(text, help_text)
        self.controls[key] = control
        card.body.addWidget(FieldRow(text, control, help_text))
        return control

    def build_review(self):
        body = self.page_layouts[0]
        behavior = SettingsCard("Review behavior")
        self.check(behavior, "enabled", "Enable PronounceIt")
        self.check(behavior, "allow_on_question_side", "Allow before revealing the answer", "Turn off when hearing a term could reveal the answer.")
        body.addWidget(behavior)
        shortcuts = SettingsCard("Shortcuts")
        self.shortcut_help = {}
        for key, title in [("direct_click_modifier", "Play audio"), ("native_context_menu_modifier", "Open quick card")]:
            control = QComboBox()
            control.setMinimumWidth(130)
            core._add_activation_modifier_items(control)
            self.controls[key] = control
            row = FieldRow(title, control, " ", stack_below=330)
            shortcuts.body.addWidget(row)
            self.shortcut_help[key] = row.help
        how, instructions = column()
        instructions.addWidget(label("Hold the key while clicking or selecting a term, or select text first and tap the key. Plain right-click keeps Anki’s menu.", "secondary"))
        disclosure(shortcuts.body, "How to use", how)
        quick = SettingsCard("Quick card")
        self.check(quick, "show_native_context_menu", "Show quick card")
        self.check(quick, "auto_close_on_card_change", "Close when changing cards")
        self.check(quick, "show_save_button", "Show Save button")
        self.quick_hint = label("Turn on the quick card to use these options.", "secondary")
        quick.body.addWidget(self.quick_hint)
        body.addWidget(CardGrid(shortcuts, quick))
        appearance = SettingsCard("Appearance")
        theme = QComboBox()
        theme.addItem("Light", "light")
        theme.addItem("Dark", "dark")
        theme.setMinimumWidth(130)
        self.controls["theme"] = theme
        appearance.body.addWidget(FieldRow("Color mode", theme, "Applies to PronounceIt settings and pronunciation cards."))
        body.addWidget(appearance)

    def build_audio(self):
        body = self.page_layouts[1]
        playback = SettingsCard("Playback")
        mode = QComboBox()
        for text, value in [("Audio, then computer voice", "local_audio_then_tts"), ("Audio only", "local_audio"), ("Computer voice only", "system_tts")]:
            mode.addItem(text, value)
        self.controls["audio_backend"] = mode
        playback.body.addWidget(FieldRow("Play using", mode, "Audio uses your custom recordings or the downloaded library.", stack_below=530))
        body.addWidget(playback)
        library = SettingsCard("Audio library", "All 95,902 audio pronunciations · About 1.03 GiB")
        status_row = QHBoxLayout()
        self.activity = ActivityIndicator()
        self.pack_status = label("", "section")
        status_row.addWidget(self.activity)
        status_row.addWidget(self.pack_status, 1)
        library.body.addLayout(status_row)
        self.pack_help = label("", "secondary")
        library.body.addWidget(self.pack_help)
        self.progress = QProgressBar()
        self.progress.setAccessibleName("Audio library download progress")
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setFixedHeight(6)
        library.body.addWidget(self.progress)
        self.progress_detail = label("", "secondary")
        library.body.addWidget(self.progress_detail)
        self.pack_buttons = {}
        actions = QHBoxLayout()
        actions.setSpacing(8)
        for action in ["Download library", "Pause", "Cancel download"]:
            control = button(action, lambda a=action: self.pack_action(a), "primary" if action == "Download library" else "")
            self.pack_buttons[action] = control
            actions.addWidget(control)
        actions.addStretch()
        library.body.addLayout(actions)
        maintenance, maintenance_body = column()
        for action, text in [("Check files", "Check downloaded files"), ("Remove", "Remove library")]:
            control = button(text, lambda a=action: self.pack_action(a), "danger" if action == "Remove" else "")
            self.pack_buttons[action] = control
            maintenance_body.addWidget(control, 0, Qt.AlignmentFlag.AlignLeft)
        self.maintenance = disclosure(library.body, "Manage library", maintenance)
        voice = SettingsCard("Computer voice")
        volume = ValueSlider("Computer voice volume", 0, 100, lambda value: f"{value}%")
        self.controls["tts_volume"] = volume.slider
        voice.body.addWidget(volume)
        speed = ValueSlider("Speaking speed", -10, 10, lambda value: "Normal" if not value else f"{value:+d}", ("Slower", "Normal", "Faster"))
        self.controls["tts_rate"] = speed.slider
        voice.body.addWidget(speed)
        self.voice_hint = label("Some voices use their own speed and volume.", "secondary")
        voice.body.addWidget(self.voice_hint)
        advanced, advanced_body = column()
        voice_name = QLineEdit()
        voice_name.setPlaceholderText("Use computer default")
        self.controls["tts_voice"] = voice_name
        field(advanced_body, "Voice name", voice_name, "Use the name of a voice installed on your computer.")
        disclosure(voice.body, "Advanced voice options", advanced)
        body.addWidget(CardGrid(library, voice))

    def build_tools(self):
        from . import ui
        body = self.page_layouts[2]
        tools = SettingsCard("Pronunciations")
        for title, help_text, action, callback in [
            ("Search", "Look up a word or medical term.", "Search", lambda: ui.show_search(parent=self)),
            ("Saved pronunciations", "Find your saved words and their original cards.", "Open saved", lambda: ui.show_saved(self)),
            ("Custom pronunciation", "Add or edit a written pronunciation or speech correction.", "Add custom", lambda: ui.show_custom(self)),
        ]:
            tools.body.addWidget(FieldRow(title, button(action, callback), help_text, stack_below=430))
        self.selection_button = button("Play selected text", core._pronounce_current_reviewer_selection)
        tools.body.addWidget(FieldRow("Current selection", self.selection_button, "Select a term in the reviewer to play it here.", stack_below=430))
        body.addWidget(tools)
        diagnostics = SettingsCard("Troubleshooting")
        diagnostics.body.addWidget(FieldRow("Pronunciation data", button("Check data", lambda: ui.show_library(self)), "Check the included terms and written guides.", stack_below=430))
        diagnostics.body.addWidget(FieldRow("Audio playback", button("Troubleshoot", lambda: ui.show_diagnostics(self)), "Review recent playback attempts and available audio sources.", stack_below=430))
        body.addWidget(diagnostics)

    def build_about(self):
        body = self.page_layouts[3]
        about = SettingsCard("PronounceIt", "Pronunciation help for Anki desktop.")
        metadata = {}
        try:
            metadata = json.loads((core._addon_dir() / "manifest.json").read_text())
        except (OSError, ValueError):
            pass
        about.body.addWidget(label("Version " + str(metadata.get("human_version") or metadata.get("version")) if metadata.get("human_version") or metadata.get("version") else "Development build", "secondary"))
        about.body.addWidget(FieldRow("Support the creator", button("Buy me a coffee", core._open_support_url), "Help support continued development.", stack_below=430))
        body.addWidget(about)
        files = SettingsCard("Your data", "Saved words, custom pronunciations, and audio stay on this computer. They are shared by profiles using this add-on and do not sync through AnkiWeb.")
        paths, paths_body = column()
        for title, getter in [("Saved pronunciations file", core._saved_pronunciations_path), ("Custom pronunciations file", core._custom_pronunciations_path), ("Computer voice audio folder", core._generated_audio_dir), ("PronounceIt folder", core._addon_dir)]:
            paths_body.addWidget(button(title, lambda get=getter: core._open_path(get()), "quiet"), 0, Qt.AlignmentFlag.AlignLeft)
        disclosure(files.body, "Open local files", paths)
        body.addWidget(files)
        defaults = SettingsCard("Settings")
        defaults.body.addWidget(FieldRow("Restore defaults", button("Restore defaults", self.restore), "Resets this draft. Save changes to apply; saved words and downloads are kept.", stack_below=430))
        body.addWidget(defaults)

    def update_selection(self):
        if not hasattr(self, "selection_button"):
            return
        reviewer = getattr(mw, "reviewer", None)
        selected = core._selected_text_from_webview(getattr(reviewer, "web", None)) if reviewer else ""
        self.selection_button.setEnabled(bool(selected and mw.state == "review"))

    def values(self):
        values = {}
        for key, control in self.controls.items():
            if isinstance(control, QAbstractButton):
                values[key] = control.isChecked()
            elif isinstance(control, QComboBox):
                values[key] = control.currentData()
            elif isinstance(control, (QSpinBox, QSlider)):
                values[key] = control.value()
            else:
                values[key] = control.text().strip()
        return values

    def load(self, config):
        self._loading = True
        for key, control in self.controls.items():
            value = getattr(config, key)
            if isinstance(control, QAbstractButton):
                control.setChecked(value)
            elif isinstance(control, QComboBox):
                if key in {"direct_click_modifier", "native_context_menu_modifier"}:
                    value = core._activation_modifier_ui_value(value)
                control.setCurrentIndex(max(0, control.findData(value)))
            elif isinstance(control, (QSpinBox, QSlider)):
                control.setValue(value)
            else:
                control.setText(value)
        self._loading = False
        self.dependencies()
        self.preview(force=True)
        self.update_dirty()

    def changed(self, *_):
        if self._loading:
            return
        self.dependencies()
        self.preview()
        self.update_dirty()

    def dependencies(self):
        enabled = self.controls["enabled"].isChecked()
        popup = enabled and self.controls["show_native_context_menu"].isChecked()
        for key in ["direct_click_modifier", "show_native_context_menu", "allow_on_question_side"]:
            self.controls[key].setEnabled(enabled)
        for key in ["native_context_menu_modifier", "auto_close_on_card_change", "show_save_button"]:
            self.controls[key].setEnabled(popup)
        self.quick_hint.setVisible(not popup)
        for key, help_label in self.shortcut_help.items():
            control = self.controls[key]
            help_label.setText("Shortcut is off." if control.currentData() == "disabled" else f"Select text, then tap {control.currentText()}.")
        voice = self.controls["audio_backend"].currentData() != "local_audio"
        for key in ["tts_voice", "tts_rate", "tts_volume"]:
            self.controls[key].setEnabled(voice)
        self.voice_hint.setText("Some voices use their own speed and volume." if voice else "Choose a playback mode with computer voice to use these options.")

    def preview(self, force=False):
        theme = self.controls["theme"].currentData() or self.config.theme
        if theme == self.theme and not force:
            return
        self.theme = theme
        self.setStyleSheet(dialog_qss(theme, self.objectName()))
        for switch in self.findChildren(SettingsSwitch):
            switch.update()
        apply_fonts(self)
        reviewer = getattr(mw, "reviewer", None)
        if reviewer and getattr(reviewer, "web", None):
            data = {"theme": self.theme, "themeTokens": web_theme_tokens(self.theme)}
            core._eval(reviewer, "window.PronounceIt && window.PronounceIt.configure(" + json.dumps(data) + ");")

    def dirty(self):
        for key, value in self.values().items():
            baseline = getattr(self.config, key)
            if key in {"direct_click_modifier", "native_context_menu_modifier"}:
                baseline = core._activation_modifier_ui_value(baseline)
            if value != baseline:
                return True
        return False

    def update_dirty(self):
        dirty = self.dirty()
        self.save_control.setEnabled(dirty)
        self.discard_button.setVisible(dirty)
        status(self.footer_status, "Unsaved changes" if dirty else "", tone="warning" if dirty else "secondary")

    def show_feedback(self, text, error=False):
        if error:
            self.settings_message.setText(text)
            self.error_region.show()
        else:
            status(self.footer_status, text)
            self.saved_timer.start()

    def discard(self):
        self.config = core._config()
        self.error_region.hide()
        self.load(self.config)
        core._send_reviewer_config()

    def restore(self):
        defaults = {**DEFAULT_CONFIG, "theme": core._current_anki_theme(), "theme_initialized": True,
                    "audio_pack_prompt_seen": core._config().audio_pack_prompt_seen}
        self.load(PronounceItConfig.from_mapping(defaults))

    def commit(self):
        # Start from the latest saved mapping so background onboarding and
        # non-editable configuration are never overwritten by an older draft.
        values = {**core._config().as_config_mapping(), **self.values(), "theme_initialized": True}
        try:
            saved = core._write_config(values)
        except Exception as exc:
            core._record_runtime_diagnostic(str(exc))
            self.show_feedback("Could not save changes. Your draft is still available. Please try again.", True)
            return False
        self.config = PronounceItConfig.from_mapping(saved)
        self.error_region.hide()
        self.update_dirty()
        core._send_reviewer_config()
        self.show_feedback("Saved")
        return True

    def refresh_pack(self):
        for control in self.pack_buttons.values():
            control.hide()
        controller = core._audio_pack_download
        if controller is None:
            self.pack_status.setText("Library unavailable")
            self.pack_help.setText("Reopen Anki, then return to Audio settings.")
            self.progress.hide()
            self.progress_detail.hide()
            self.activity.hide()
            self.maintenance.hide()
            self.maintenance.content.hide()
            return
        state = controller.refresh()
        self.pack_state = state
        view = core._pack_presentation(state)
        text = "Preparing download…" if state.phase == "preparing" else view.status.replace("Verifying", "Checking files")
        tone = "error" if view.tone == "failed" else "warning" if view.tone == "paused" else "success" if state.phase == "installed" else "section"
        status(self.pack_status, text, tone=tone)
        busy = view.progress_indeterminate and state.phase not in {"paused", "cancelled", "failed"}
        self.activity.setVisible(busy)
        self.progress.setVisible(view.progress_visible and not view.progress_indeterminate)
        self.progress.setValue(view.progress_percent)
        measurable = bool(state.total_bytes and view.progress_visible)
        self.progress_detail.setVisible(measurable)
        if measurable:
            done, total = state.done_bytes / 1024 ** 2, state.total_bytes / 1024 ** 2
            self.progress_detail.setText(f"{done:,.0f} of {total:,.0f} MiB")
        help_text = "Written pronunciations are already included. Download the library to add recorded audio."
        if state.phase == "paused":
            help_text = "Resume whenever you’re ready. Downloaded files are kept."
        elif state.phase == "verifying":
            help_text = "Checking downloaded files. This may take a moment."
        elif state.phase == "cancelling":
            help_text = "Stopping the download. Downloaded files will be kept."
        elif state.running:
            help_text = "The download continues when you close settings."
        elif state.phase == "failed":
            help_text = "Check your connection and available disk space, then try again."
        elif state.phase == "cancelled":
            help_text = "Resume to finish the download. Downloaded files are kept."
        elif state.installed:
            help_text = "Ready to use. The library stays installed when PronounceIt updates."
        self.pack_help.setText(help_text)
        manage = bool(not state.running and (state.installed or state.total_shards))
        self.maintenance.setVisible(manage)
        self.maintenance.content.setVisible(manage and self.maintenance.isChecked())
        if not state.running:
            start = self.pack_buttons["Download library"]
            start.setText("Update library" if state.installed else "Resume download" if state.total_bytes or state.total_shards else "Retry download" if state.phase == "failed" else "Download library")
            start.show()
            for action in ["Check files", "Remove"]:
                self.pack_buttons[action].setVisible(manage)
        else:
            if state.phase in {"downloading", "paused"}:
                pause = self.pack_buttons["Pause"]
                pause.setText("Resume" if state.paused else "Pause")
                pause.show()
            if state.phase in {"preparing", "downloading", "paused"}:
                self.pack_buttons["Cancel download"].show()

    def pack_action(self, action):
        from .ui import Dialog
        controller = core._audio_pack_download
        if controller is None:
            return
        try:
            if action == "Download library":
                core._complete_audio_pack_onboarding(True)
            elif action == "Pause":
                controller.resume() if self.pack_state.paused else controller.pause()
            elif action == "Cancel download":
                controller.cancel()
            elif action == "Check files":
                controller.start_verify()
            elif action == "Remove":
                confirm = Dialog("Remove audio library?", self)
                confirm.body.addWidget(label("This removes the downloaded audio library and partial downloads. Your saved words and custom pronunciations stay available."))
                confirm.footer.addStretch()
                confirm.footer.addWidget(button("Keep library", confirm.reject))
                confirm.footer.addWidget(button("Remove library", confirm.accept, "danger"))
                confirm.fit(500, 240)
                if confirm.exec() == QDialog.DialogCode.Accepted:
                    controller.remove()
        except Exception as exc:
            core._record_runtime_diagnostic(str(exc))
            self.show_feedback("Could not complete this action. Open Troubleshoot audio for details.", True)
        self.refresh_pack()

    def request_close(self):
        if self._prompt is not None:
            return
        if not self.dirty():
            self._close()
            return
        self._focus_before_prompt = QApplication.focusWidget()
        prompt, body = column("canvas")
        body.setContentsMargins(24, 24, 24, 24)
        body.addStretch()
        card = SettingsCard("Unsaved changes", "Save your changes before closing?")
        card.setMaximumWidth(560)
        keep = button("Keep editing", self._finish_prompt)
        discard = button("Discard changes", self._discard_and_close, "danger")
        save = button("Save and close", self._save_and_close, "primary")
        actions = QHBoxLayout()
        for control in [keep, discard, save]:
            actions.addWidget(control)
        card.body.addLayout(actions)
        body.addWidget(card, 0, Qt.AlignmentFlag.AlignCenter)
        body.addStretch()
        self._prompt = prompt
        self.workspace_stack.addWidget(prompt)
        self.workspace_stack.setCurrentWidget(prompt)
        apply_fonts(prompt)
        keep.setFocus()

    def _finish_prompt(self):
        if self._prompt is None:
            return
        prompt, self._prompt = self._prompt, None
        self.workspace_stack.setCurrentWidget(self.workspace)
        self.workspace_stack.removeWidget(prompt)
        prompt.deleteLater()
        focus = self._focus_before_prompt
        if focus is not None and focus.isVisible() and focus.isEnabled():
            focus.setFocus()

    def _discard_and_close(self):
        self._finish_prompt()
        self.discard()
        self._close()

    def _save_and_close(self):
        self._finish_prompt()
        if self.commit():
            self._close()

    def _close(self):
        QSettings().setValue(self.GEOMETRY_KEY, self.saveGeometry())
        self._closing = True
        super().reject()

    def reject(self):
        if self._prompt is not None:
            self._finish_prompt()
        else:
            self.request_close()

    def closeEvent(self, event):
        if self._closing:
            super().closeEvent(event)
        else:
            event.ignore()
            self.request_close()
