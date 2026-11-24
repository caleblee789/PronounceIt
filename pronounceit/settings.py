"""Dashboard-derived settings workspace; pronunciation services stay in main."""
from __future__ import annotations

import json
from typing import Any

from aqt import mw
from aqt.qt import (
    QAbstractButton, QApplication, QBoxLayout, QComboBox, QDialog, QEvent,
    QGridLayout, QHBoxLayout, QLineEdit, QListWidget, QProgressBar, QScrollArea,
    QSettings, QSizePolicy, QSlider, QSpinBox, QStackedWidget, QTimer, QVBoxLayout, Qt,
)

from . import __version__, main as core
from .audio_pack import read_release_metadata
from .config import DEFAULT_CONFIG, PronounceItConfig
from .theme import dialog_qss, web_theme_tokens
from .ui_components import (
    ActivityIndicator, CardGrid, FieldRow, SettingsCard, SettingsSwitch,
    ValueSlider, apply_fonts, button, column, disclosure, field, label,
    status, surface,
)


def audio_library_summary() -> str:
    """Read the small bundled release binding, without scanning audio files."""
    release = read_release_metadata(core._addon_dir())
    parts = []
    count = release.get("assetCount")
    if type(count) is int and count > 0:
        parts.append(f"{count:,} recordings")
    voice = release.get("voice")
    if isinstance(voice, str) and voice.strip():
        parts.append(voice.strip().capitalize() + " voice")
    size = release.get("packBytes")
    if type(size) is int and size > 0:
        parts.append(f"{size / 1024 ** 3:.2f} GiB")
    return " · ".join(parts)


class Settings(QDialog):
    SECTIONS = ("Review", "Audio", "Tools", "About & support")
    GEOMETRY_KEY = "pronounceit/settings/geometry-v2"

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
        self.pack_state = None
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
        self.pack_timer.timeout.connect(self.update_selection)
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
        sidebar.setContentsMargins(12, 16, 12, 12)
        sidebar.setSpacing(12)
        sidebar.addWidget(label("PronounceIt", "brand"))
        self.nav = QListWidget()
        self.nav.setObjectName("pronounceitNav")
        self.nav.setAccessibleName("Settings sections")
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for title in self.SECTIONS:
            self.nav.addItem(title)
        sidebar.addWidget(self.nav, 1)
        grid.addWidget(self.sidebar, 0, 0, 4, 1)
        self.header, header = column("header")
        self.header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header.setContentsMargins(18, 12, 18, 12)
        self.page_title = label("", "page_title")
        header.addWidget(self.page_title)
        self.compact_nav = QComboBox()
        self.compact_nav.addItems(self.SECTIONS)
        self.compact_row = FieldRow("Settings section", self.compact_nav, stack_below=265)
        self.compact_row.hide()
        header.addWidget(self.compact_row)
        grid.addWidget(self.header, 0, 1)
        self.pages = QStackedWidget()
        self.pages.setMinimumWidth(0)
        grid.addWidget(self.pages, 1, 1)
        self.page_layouts = [self.page() for _ in self.SECTIONS]
        self.error_region, errors = column("canvas")
        errors.setContentsMargins(18, 8, 18, 8)
        self.settings_message = label("", "error")
        self.settings_message.setAccessibleName("Settings error")
        errors.addWidget(self.settings_message)
        self.error_region.hide()
        grid.addWidget(self.error_region, 2, 1)
        self.footer = surface("footer")
        self.footer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.footer_grid = QGridLayout(self.footer)
        self.footer_grid.setContentsMargins(16, 8, 16, 8)
        self.footer_grid.setHorizontalSpacing(8)
        self.footer_grid.setVerticalSpacing(4)
        self.footer_status = label("", "secondary")
        self.footer_status.setAccessibleName("Settings save status")
        self.discard_button = button("Discard changes", self.discard, "quiet")
        self.close_control = button("Close", self.request_close)
        self.save_control = button("Save changes", self.commit, "primary")
        self.save_control.setAccessibleDescription("Apply all changes without closing settings.")
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
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(12)
        body.setAlignment(Qt.AlignmentFlag.AlignTop)
        area.setWidget(widget)
        self.pages.addWidget(area)
        return body

    def _arrange_footer(self, compact):
        if self._footer_compact == compact:
            return
        self._footer_compact = compact
        actions = (self.discard_button, self.close_control, self.save_control)
        for widget in (self.footer_status, *actions):
            self.footer_grid.removeWidget(widget)
        self.footer_grid.setColumnStretch(0, 1)
        self.footer_grid.addWidget(self.footer_status, 0, 0, 1, 4 if compact else 1)
        for column_index, action in enumerate(actions, 1):
            self.footer_grid.addWidget(action, int(compact), column_index)

    def navigate(self, index):
        if not 0 <= index < len(self.SECTIONS):
            return
        for widget, setter in [(self.nav, self.nav.setCurrentRow), (self.compact_nav, self.compact_nav.setCurrentIndex)]:
            widget.blockSignals(True)
            setter(index)
            widget.blockSignals(False)
        self.pages.setCurrentIndex(index)
        self.page_title.setText(self.SECTIONS[index])
        self.update_selection()

    def _initial_geometry(self):
        available = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        width, height = max(280, available.width() - 48), max(180, available.height() - 48)
        self.setMinimumSize(min(560, width), min(440, height))
        self.resize(min(900, width), min(620, height))
        saved = QSettings().value(self.GEOMETRY_KEY)
        if saved:
            self.restoreGeometry(saved)
        self.resize(min(self.width(), width), min(self.height(), height))
        if not saved or not available.contains(self.frameGeometry()):
            self.move(available.center() - self.rect().center())
        self._arrange_workspace()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "save_control"):
            return
        self._arrange_workspace()
        if self._prompt is not None:
            self._arrange_prompt()

    def _arrange_workspace(self):
        sidebar_width = max(178, self.nav.fontMetrics().horizontalAdvance(self.SECTIONS[-1]) + 66)
        self.sidebar.setFixedWidth(sidebar_width)
        compact = self.width() < max(720, sidebar_width + 520)
        self.sidebar.setVisible(not compact)
        self.compact_row.setVisible(compact)
        self.page_title.setVisible(not compact)
        panel_width = self.width() - (0 if compact else sidebar_width)
        actions = (self.discard_button, self.close_control, self.save_control)
        action_width = sum(control.sizeHint().width() for control in actions)
        status_width = self.footer_status.fontMetrics().horizontalAdvance("Unsaved changes")
        self._arrange_footer(panel_width < action_width + status_width + 64)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.ApplicationFontChange:
            apply_fonts(self)
            if hasattr(self, "save_control"):
                self._arrange_workspace()

    def check(self, card, key, text, help_text=""):
        control = SettingsSwitch(text, help_text)
        self.controls[key] = control
        card.body.addWidget(FieldRow(text, control, help_text))
        return control

    def build_review(self):
        body = self.page_layouts[0]
        behavior = SettingsCard("Review behavior")
        self.check(behavior, "enabled", "Enable PronounceIt")
        self.check(behavior, "allow_on_question_side", "Allow before revealing the answer")
        self.check(behavior, "show_right_click_play_audio", "Right-click Play audio",
                   "Show Play audio below Copy when you right-click selected text.")
        body.addWidget(behavior)
        shortcuts = SettingsCard("Shortcuts")
        for key, title in [("direct_click_modifier", "Play audio"), ("native_context_menu_modifier", "Open quick card")]:
            control = QComboBox()
            control.setMinimumWidth(130)
            core._add_activation_modifier_items(control)
            self.controls[key] = control
            shortcuts.body.addWidget(FieldRow(title, control, stack_below=280))
        how, instructions = column()
        instructions.addWidget(label("Hold the shortcut key while clicking or selecting text, or tap it after selecting text.", "secondary"))
        disclosure(shortcuts.body, "How to use", how)
        self.shortcut_conflict = label("The quick card takes priority when both shortcuts use the same key.", "warning")
        shortcuts.body.addWidget(self.shortcut_conflict)
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
        appearance.body.addWidget(FieldRow("Color mode", theme))
        body.addWidget(appearance)

    def build_audio(self):
        body = self.page_layouts[1]
        playback = SettingsCard("Playback")
        mode = QComboBox()
        for text, value in [("Audio, then computer voice", "local_audio_then_tts"), ("Audio only", "local_audio"), ("Computer voice only", "system_tts")]:
            mode.addItem(text, value)
        self.controls["audio_backend"] = mode
        playback.body.addWidget(FieldRow("Play using", mode, stack_below=390))
        body.addWidget(playback)
        library = SettingsCard("Audio library", audio_library_summary())
        status_row = QHBoxLayout()
        self.activity = ActivityIndicator()
        self.pack_status = label("", "section")
        self.pack_status.setAccessibleName("Audio library status")
        status_row.addWidget(self.activity)
        status_row.addWidget(self.pack_status, 1)
        library.body.addLayout(status_row)
        self.pack_help = label("", "secondary")
        library.body.addWidget(self.pack_help)
        self.pack_error = label("", "error")
        self.pack_error.hide()
        library.body.addWidget(self.pack_error)
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
        for action in ["Download library", "Check files", "Pause", "Cancel download"]:
            control = button(action, lambda a=action: self.pack_action(a), "primary" if action in {"Download library", "Check files"} else "")
            self.pack_buttons[action] = control
            actions.addWidget(control)
        actions.addStretch()
        library.body.addLayout(actions)
        maintenance, maintenance_body = column()
        self.pack_versions = label("", "secondary")
        maintenance_body.addWidget(self.pack_versions)
        self.pack_buttons["Remove"] = button("Remove library", lambda: self.pack_action("Remove"), "danger")
        maintenance_body.addWidget(self.pack_buttons["Remove"], 0, Qt.AlignmentFlag.AlignLeft)
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
        for title, action, callback in [
            ("Search pronunciations", "Search", lambda: ui.show_search(parent=self)),
            ("Saved pronunciations", "Open saved", lambda: ui.show_saved(self)),
            ("Custom pronunciations", "Add custom", lambda: ui.show_custom(self)),
        ]:
            tools.body.addWidget(FieldRow(title, button(action, callback), stack_below=360))
        self.selection_button = button("Play selected text", core._pronounce_current_reviewer_selection)
        selection = FieldRow("Current selection", self.selection_button, "Select text on the current review card.", stack_below=360)
        self.selection_help = selection.help
        tools.body.addWidget(selection)
        body.addWidget(tools)
        diagnostics = SettingsCard("Troubleshooting")
        diagnostics.body.addWidget(FieldRow("Pronunciation data", button("Check data", lambda: ui.show_library(self)), stack_below=360))
        diagnostics.body.addWidget(FieldRow("Audio playback", button("Troubleshoot", lambda: ui.show_diagnostics(self)), "Review recent playback attempts.", stack_below=360))
        body.addWidget(diagnostics)

    def build_about(self):
        body = self.page_layouts[3]
        about = SettingsCard("PronounceIt", f"Version {__version__}")
        about.body.addWidget(FieldRow("Support the creator", button("Buy Me a Coffee", core._open_support_url, "quiet"), stack_below=360))
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
        in_review = (
            getattr(mw, "state", None) == "review"
            and getattr(reviewer, "web", None) is not None
        )
        allowed = self.config.enabled and (self.config.allow_on_question_side or core._answer_visible())
        self.selection_button.setEnabled(in_review and allowed)
        if not self.config.enabled:
            guidance = "Enable PronounceIt in Review settings."
        elif not in_review:
            guidance = "Open a review card to use this action."
        elif not allowed:
            guidance = "Reveal the answer to use this action."
        else:
            guidance = "Select text on the current review card."
        if self.selection_help.text() != guidance:
            self.selection_help.setText(guidance)
            self.selection_button.setAccessibleDescription(guidance)

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
        for key in ["direct_click_modifier", "show_native_context_menu", "allow_on_question_side", "show_right_click_play_audio"]:
            self.controls[key].setEnabled(enabled)
        for key in ["native_context_menu_modifier", "auto_close_on_card_change", "show_save_button"]:
            self.controls[key].setEnabled(popup)
        self.quick_hint.setVisible(not popup)
        direct_key = self.controls["direct_click_modifier"].currentData()
        quick_key = self.controls["native_context_menu_modifier"].currentData()
        self.shortcut_conflict.setVisible(popup and direct_key == quick_key and direct_key != "disabled")
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
        self._arrange_workspace()
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
        self.update_selection()
        core._send_reviewer_config()
        self.show_feedback("Saved")
        return True

    def refresh_pack(self):
        controller = core._audio_pack_download
        if controller is None:
            status(self.pack_status, "Library unavailable", tone="error")
            self.pack_help.setText("Restart Anki to try again.")
            self.pack_help.show()
            self.progress.hide()
            self.progress_detail.hide()
            self.activity.hide()
            self.maintenance.hide()
            self.maintenance.content.hide()
            for control in self.pack_buttons.values():
                control.hide()
            return
        state = controller.refresh()
        if state == self.pack_state:
            return
        self.pack_state = state
        phase = state.phase
        view = core._pack_presentation(state)
        text = view.status.replace("Verifying", "Checking files")
        if phase == "installed" and state.verified:
            text = "Installed and verified"
        tone = {"failed": "error", "paused": "warning", "installed": "success"}.get(view.tone, "section")
        status(self.pack_status, text, tone=tone)
        busy = view.progress_indeterminate and phase not in {"paused", "cancelled", "failed"}
        self.activity.setVisible(busy)
        self.progress.setVisible(view.progress_visible and not view.progress_indeterminate)
        self.progress.setValue(view.progress_percent)
        measurable = bool(state.total_bytes and view.progress_visible and not view.progress_indeterminate)
        self.progress_detail.setVisible(measurable)
        if measurable:
            done, total = state.done_bytes / 1024 ** 2, state.total_bytes / 1024 ** 2
            self.progress_detail.setText(f"{done:,.0f} of {total:,.0f} MiB")
        help_text = {
            "idle": "Download recordings for offline playback.",
            "update-available": "Download the library that matches this add-on.",
            "incomplete": "Resume to finish the download.",
            "preparing": "The download continues when you close settings.",
            "downloading": "The download continues when you close settings.",
            "paused": "Downloaded files are kept until you resume.",
            "cancelling": "Downloaded files will be kept.",
            "cancelled": "Resume to finish the download.",
            "failed": state.error or "Check your connection and available space, then retry.",
            "installed": "Ready for offline playback.",
        }.get(phase, "")
        self.pack_help.setText(help_text)
        self.pack_help.setVisible(bool(help_text))

        can_manage = not state.running
        manage = can_manage and bool(state.active_version or state.total_shards)
        versions = []
        if state.active_version:
            versions.append(f"Installed library {state.active_version}")
        if state.target_version and state.target_version != state.active_version:
            versions.append(f"Available library {state.target_version}")
        self.pack_versions.setText("\n".join(versions))
        self.pack_versions.setVisible(bool(versions))
        self.maintenance.setVisible(manage)
        self.maintenance.content.setVisible(manage and self.maintenance.isChecked())
        self.pack_buttons["Remove"].setVisible(manage)
        removal_failed = phase == "failed" and "remov" in state.message.casefold()
        can_check = can_manage and (phase == "installed" or removal_failed and state.installed)
        self.pack_buttons["Check files"].setVisible(can_check)
        start = self.pack_buttons["Download library"]
        download_label = {
            "update-available": "Update Audio",
            "incomplete": "Resume download",
            "cancelled": "Resume download",
        }.get(phase, "Download library")
        if phase == "failed":
            if "verif" in state.message.casefold():
                download_label = "Repair library"
            elif "download" in state.message.casefold():
                download_label = "Retry download"
        start.setText(download_label)
        start.setVisible(can_manage and not can_check)
        pause = self.pack_buttons["Pause"]
        pause.setText("Resume" if state.paused else "Pause")
        pause.setVisible(phase in {"downloading", "paused"})
        self.pack_buttons["Cancel download"].setVisible(phase in {"preparing", "downloading", "paused"})

    def pack_action(self, action):
        from .ui import Dialog
        controller = core._audio_pack_download
        if controller is None:
            return
        self.pack_error.hide()
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
            status(self.pack_error, "Could not complete this action. See Audio playback in Tools for details.", error=True)
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
        self._prompt_actions = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        for control in (keep, discard, save):
            self._prompt_actions.addWidget(control)
        card.body.addLayout(self._prompt_actions)
        body.addWidget(card, 0, Qt.AlignmentFlag.AlignCenter)
        body.addStretch()
        self._prompt = prompt
        self.workspace_stack.addWidget(prompt)
        self.workspace_stack.setCurrentWidget(prompt)
        apply_fonts(prompt)
        self._arrange_prompt()
        keep.setFocus()

    def _arrange_prompt(self):
        actions = self._prompt_actions
        required = sum(actions.itemAt(i).widget().sizeHint().width() for i in range(actions.count())) + 96
        actions.setDirection(QBoxLayout.Direction.LeftToRight if self.width() >= required else QBoxLayout.Direction.TopToBottom)

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
