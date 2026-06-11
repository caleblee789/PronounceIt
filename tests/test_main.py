import json
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pronounceit import main
from pronounceit.config import PronounceItConfig
from pronounceit.dictionary import PronunciationDictionary
from pronounceit.tts import TtsResult


class FakeWeb:
    def __init__(self) -> None:
        self.scripts: list[str] = []

    def eval(self, javascript: str) -> None:
        self.scripts.append(javascript)


class FakeReviewer:
    def __init__(self) -> None:
        self.web = FakeWeb()
        self.card = object()


class FakeWebView:
    def __init__(self, selected_text: str) -> None:
        self._selected_text = selected_text

    def selectedText(self) -> str:
        return self._selected_text


class FakeAction:
    def __init__(self, label: str = "", parent=None) -> None:
        self.label = label
        self.shortcut = ""
        self.callback = None
        self.triggered = self

    def connect(self, callback) -> None:
        self.callback = callback

    def setShortcut(self, shortcut: str) -> None:
        self.shortcut = shortcut


class FakeMenu:
    def __init__(self, title: str = "", parent=None) -> None:
        self.title = title
        self.actions: list[tuple[str, FakeAction]] = []
        self.submenus: list[FakeMenu] = []

    def addAction(self, action_or_label) -> FakeAction:
        if isinstance(action_or_label, FakeAction):
            action = action_or_label
            label = action.label
        else:
            label = str(action_or_label)
            action = FakeAction(label)
        self.actions.append((label, action))
        return action

    def addMenu(self, menu) -> None:
        self.submenus.append(menu)

    def addSeparator(self) -> None:
        self.actions.append(("---", FakeAction("---")))


class FakeTts:
    def __init__(self, result: TtsResult) -> None:
        self.result = result
        self.calls: list[tuple[str, object]] = []

    def speak_result(self, text: str, settings) -> TtsResult:
        self.calls.append((text, settings))
        return self.result


class FakeWebContent:
    def __init__(self) -> None:
        self.css: list[str] = []
        self.js: list[str] = []
        self.body = ""


def make_phrase_dictionary() -> PronunciationDictionary:
    entries = {}
    PronunciationDictionary._merge_entries(
        entries,
        [
            {
                "term": "bundle branch block",
                "pronunciation": "BUN-dul branch block",
                "syllables": "bun-dle branch block",
            },
            {
                "term": "right bundle branch block",
                "pronunciation": "RYT BUN-dul branch block",
                "syllables": "right bun-dle branch block",
            },
        ],
        "test",
    )
    return PronunciationDictionary(entries)


class MainMessageTests(unittest.TestCase):
    def setUp(self) -> None:
        main._dictionary = PronunciationDictionary.bundled()
        main._reviewer_answer_visible = True

    def test_lookup_message_returns_popup_payload_with_phonetic_audio_text(self) -> None:
        reviewer = FakeReviewer()
        payload = {
            "text": "agranulocytosis",
            "rect": {"left": 10, "bottom": 20},
        }
        handled = main._on_js_message(
            (False, None),
            "pronounceit:lookup:" + json.dumps(payload),
            reviewer,
        )

        self.assertEqual(handled, (True, None))
        self.assertEqual(len(reviewer.web.scripts), 1)
        script = reviewer.web.scripts[0]
        self.assertIn("window.PronounceIt.show", script)
        self.assertIn("uh-GRAN-yoo-loh-sy-TOH-sis", script)
        self.assertIn("uh gran yoo loh sy toh sis", script)

    def test_lookup_message_uses_longest_context_phrase(self) -> None:
        reviewer = FakeReviewer()
        main._dictionary = make_phrase_dictionary()
        context = "ECG shows right bundle branch block today."
        start = context.index("branch")
        payload = {
            "text": "branch",
            "contextText": context,
            "contextOffsetStart": start,
            "contextOffsetEnd": start + len("branch"),
            "rect": {"left": 4, "bottom": 8},
            "autoPlay": True,
            "saveAfterLookup": True,
        }
        handled = main._on_js_message(
            (False, None),
            "pronounceit:lookup:" + json.dumps(payload),
            reviewer,
        )

        self.assertEqual(handled, (True, None))
        self.assertEqual(len(reviewer.web.scripts), 1)
        script = reviewer.web.scripts[0]
        self.assertIn("window.PronounceIt.show", script)
        self.assertIn('"requestedText": "branch"', script)
        self.assertIn('"term": "right bundle branch block"', script)
        self.assertIn('"left": 4', script)
        self.assertIn('"autoPlay": true', script)
        self.assertIn('"saveAfterLookup": true', script)

    def test_menu_lookup_uses_longest_context_phrase(self) -> None:
        reviewer = FakeReviewer()
        main._dictionary = make_phrase_dictionary()
        context = "ECG shows right bundle branch block today."
        start = context.index("bundle")
        payload = {
            "text": "bundle",
            "contextText": context,
            "contextOffsetStart": start,
            "contextOffsetEnd": start + len("bundle"),
            "rect": {"left": 6, "bottom": 10},
            "menuX": 30,
            "menuY": 40,
        }
        handled = main._on_js_message(
            (False, None),
            "pronounceit:menu:" + json.dumps(payload),
            reviewer,
        )

        self.assertEqual(handled, (True, None))
        self.assertEqual(len(reviewer.web.scripts), 1)
        script = reviewer.web.scripts[0]
        self.assertIn("window.PronounceIt.showMenu", script)
        self.assertIn('"requestedText": "bundle"', script)
        self.assertIn('"term": "right bundle branch block"', script)
        self.assertIn('"menuX": 30', script)
        self.assertIn('"menuY": 40', script)

    def test_audio_lookup_uses_longest_context_phrase_without_popup(self) -> None:
        reviewer = FakeReviewer()
        original_tts = main._tts
        fake_tts = FakeTts(TtsResult(True, "playing local audio"))
        try:
            main._dictionary = make_phrase_dictionary()
            main._tts = fake_tts
            context = "ECG shows right bundle branch block today."
            start = context.index("bundle")
            handled = main._on_js_message(
                (False, None),
                "pronounceit:audioLookup:"
                + json.dumps(
                    {
                        "text": "bundle",
                        "contextText": context,
                        "contextOffsetStart": start,
                        "contextOffsetEnd": start + len("bundle"),
                    }
                ),
                reviewer,
            )
        finally:
            main._tts = original_tts

        self.assertEqual(handled, (True, None))
        self.assertEqual(len(fake_tts.calls), 1)
        self.assertEqual(fake_tts.calls[0][1].term, "right bundle branch block")
        self.assertEqual(len(reviewer.web.scripts), 1)
        self.assertIn("window.PronounceIt && window.PronounceIt.spoken", reviewer.web.scripts[0])

    def test_lookup_message_is_blocked_on_question_side_by_default(self) -> None:
        reviewer = FakeReviewer()
        original_answer_visible = main._reviewer_answer_visible
        try:
            main._reviewer_answer_visible = False
            handled = main._on_js_message(
                (False, None),
                "pronounceit:lookup:" + json.dumps({"text": "agranulocytosis"}),
                reviewer,
            )
        finally:
            main._reviewer_answer_visible = original_answer_visible

        self.assertEqual(handled, (True, None))
        self.assertEqual(reviewer.web.scripts, ["window.PronounceIt && window.PronounceIt.hide();"])

    def test_lookup_message_can_be_enabled_on_question_side(self) -> None:
        reviewer = FakeReviewer()
        original_answer_visible = main._reviewer_answer_visible
        original_config = main._config
        try:
            main._reviewer_answer_visible = False
            main._config = lambda: PronounceItConfig.from_mapping({"allow_on_question_side": True})
            handled = main._on_js_message(
                (False, None),
                "pronounceit:lookup:" + json.dumps({"text": "agranulocytosis"}),
                reviewer,
            )
        finally:
            main._reviewer_answer_visible = original_answer_visible
            main._config = original_config

        self.assertEqual(handled, (True, None))
        self.assertEqual(len(reviewer.web.scripts), 1)
        self.assertIn("window.PronounceIt.show", reviewer.web.scripts[0])

    def test_non_pronounceit_message_is_not_handled(self) -> None:
        reviewer = FakeReviewer()
        handled = main._on_js_message((False, None), "other:addon", reviewer)

        self.assertEqual(handled, (False, None))
        self.assertEqual(reviewer.web.scripts, [])

    def test_selected_text_from_webview_is_cleaned(self) -> None:
        text = main._selected_text_from_webview(FakeWebView("  Agranulocytosis, "))

        self.assertEqual(text, "Agranulocytosis")

    def test_reviewer_web_content_inlines_assets_after_config(self) -> None:
        web_content = FakeWebContent()
        reviewer = FakeReviewer()

        main._on_webview_will_set_content(web_content, reviewer)

        self.assertEqual(web_content.css, [])
        self.assertEqual(web_content.js, [])
        self.assertIn("window.PronounceItConfig", web_content.body)
        self.assertIn(".pronounceit-popup", web_content.body)
        self.assertIn("window.PronounceIt = {", web_content.body)
        self.assertLess(
            web_content.body.index("window.PronounceItConfig"),
            web_content.body.index("window.PronounceIt = {"),
        )

    def test_native_context_menu_hook_does_not_add_pronounce_action_in_review(self) -> None:
        class FakeMw:
            state = "review"

        original_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "aqt":
                class FakeAqt:
                    mw = FakeMw()

                return FakeAqt
            return original_import(name, *args, **kwargs)

        import builtins

        menu = FakeMenu()
        try:
            builtins.__import__ = fake_import
            main._on_webview_will_show_context_menu(FakeWebView("clozapine"), menu)
        finally:
            builtins.__import__ = original_import

        self.assertEqual(menu.actions, [])

    def test_native_context_menu_hook_stays_disabled_when_term_is_already_saved(self) -> None:
        class FakeMw:
            state = "review"

        class FakeSaved:
            def contains(self, payload):
                return True

        original_import = __import__
        original_saved = main._saved

        def fake_import(name, *args, **kwargs):
            if name == "aqt":
                class FakeAqt:
                    mw = FakeMw()

                return FakeAqt
            return original_import(name, *args, **kwargs)

        import builtins

        menu = FakeMenu()
        try:
            main._saved = FakeSaved()
            builtins.__import__ = fake_import
            main._on_webview_will_show_context_menu(FakeWebView("clozapine"), menu)
        finally:
            main._saved = original_saved
            builtins.__import__ = original_import

        self.assertEqual(menu.actions, [])

    def test_native_context_menu_hook_is_hidden_on_question_side_by_default(self) -> None:
        class FakeMw:
            state = "review"

        original_import = __import__
        original_answer_visible = main._reviewer_answer_visible

        def fake_import(name, *args, **kwargs):
            if name == "aqt":
                class FakeAqt:
                    mw = FakeMw()

                return FakeAqt
            return original_import(name, *args, **kwargs)

        import builtins

        menu = FakeMenu()
        try:
            main._reviewer_answer_visible = False
            builtins.__import__ = fake_import
            main._on_webview_will_show_context_menu(FakeWebView("clozapine"), menu)
        finally:
            builtins.__import__ = original_import
            main._reviewer_answer_visible = original_answer_visible

        self.assertEqual(menu.actions, [])

    def test_native_context_menu_hook_is_hidden_in_option_select_mode(self) -> None:
        class FakeMw:
            state = "review"

        original_import = __import__
        original_config = main._config

        def fake_import(name, *args, **kwargs):
            if name == "aqt":
                class FakeAqt:
                    mw = FakeMw()

                return FakeAqt
            return original_import(name, *args, **kwargs)

        import builtins

        menu = FakeMenu()
        try:
            main._config = lambda: PronounceItConfig.from_mapping({"activation_mode": "option_select"})
            builtins.__import__ = fake_import
            main._on_webview_will_show_context_menu(FakeWebView("clozapine"), menu)
        finally:
            builtins.__import__ = original_import
            main._config = original_config

        self.assertEqual(menu.actions, [])

    def test_pronunciation_allowed_recovers_when_reviewer_state_is_answer(self) -> None:
        class FakeReviewer:
            state = "answer"

        class FakeMw:
            reviewer = FakeReviewer()

        original_import = __import__
        original_answer_visible = main._reviewer_answer_visible

        def fake_import(name, *args, **kwargs):
            if name == "aqt":
                class FakeAqt:
                    mw = FakeMw()

                return FakeAqt
            return original_import(name, *args, **kwargs)

        import builtins

        try:
            main._reviewer_answer_visible = False
            builtins.__import__ = fake_import
            self.assertTrue(main._pronunciation_allowed())
            self.assertTrue(main._js_config_payload()["answerVisible"])
        finally:
            builtins.__import__ = original_import
            main._reviewer_answer_visible = original_answer_visible

    def test_pronunciation_allowed_keeps_question_state_blocked(self) -> None:
        class FakeReviewer:
            state = "question"

        class FakeMw:
            reviewer = FakeReviewer()

        original_import = __import__
        original_answer_visible = main._reviewer_answer_visible

        def fake_import(name, *args, **kwargs):
            if name == "aqt":
                class FakeAqt:
                    mw = FakeMw()

                return FakeAqt
            return original_import(name, *args, **kwargs)

        import builtins

        try:
            main._reviewer_answer_visible = False
            builtins.__import__ = fake_import
            self.assertFalse(main._pronunciation_allowed())
            self.assertFalse(main._js_config_payload()["answerVisible"])
        finally:
            builtins.__import__ = original_import
            main._reviewer_answer_visible = original_answer_visible

    def test_pronounce_current_selection_falls_back_to_reviewer_javascript(self) -> None:
        reviewer = FakeReviewer()

        class FakeMw:
            pass

        FakeMw.reviewer = reviewer

        original_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "aqt":
                class FakeAqt:
                    mw = FakeMw()

                return FakeAqt
            return original_import(name, *args, **kwargs)

        import builtins

        try:
            builtins.__import__ = fake_import
            main._pronounce_current_reviewer_selection()
        finally:
            builtins.__import__ = original_import

        self.assertEqual(
            reviewer.web.scripts,
            ["window.PronounceIt && window.PronounceIt.pronounceCurrent();"],
        )

    def test_tools_menu_installs_single_pronounceit_submenu(self) -> None:
        class FakeAddonManager:
            def getConfig(self, module):
                return {"hotkey": "Mod+P"}

        class FakeMw:
            addonManager = FakeAddonManager()

            class Form:
                menuTools = FakeMenu("Tools")

            form = Form()

        fake_aqt = types.ModuleType("aqt")
        fake_aqt.mw = FakeMw()
        fake_qt = types.ModuleType("aqt.qt")
        fake_qt.QAction = FakeAction
        fake_qt.QMenu = FakeMenu
        original_aqt = sys.modules.get("aqt")
        original_qt = sys.modules.get("aqt.qt")
        try:
            sys.modules["aqt"] = fake_aqt
            sys.modules["aqt.qt"] = fake_qt
            main._install_tools_menu_actions()
        finally:
            if original_aqt is None:
                sys.modules.pop("aqt", None)
            else:
                sys.modules["aqt"] = original_aqt
            if original_qt is None:
                sys.modules.pop("aqt.qt", None)
            else:
                sys.modules["aqt.qt"] = original_qt

        self.assertEqual(len(FakeMw.form.menuTools.submenus), 1)
        submenu = FakeMw.form.menuTools.submenus[0]
        self.assertEqual(submenu.title, "PronounceIt")
        labels = [label for label, _action in submenu.actions if label != "---"]
        self.assertEqual(
            labels,
            [
                "Pronounce Current Selection",
                "Pronounce Manually...",
                "Saved Pronunciations...",
                "Add or Update Custom Pronunciation...",
                "Dictionary Audit...",
                "Configure Add-on...",
            ],
        )
        self.assertEqual(submenu.actions[0][1].shortcut, "Ctrl+P")

    def test_lookup_start_choice_reflects_existing_config(self) -> None:
        self.assertEqual(
            main._lookup_start_choice(PronounceItConfig.from_mapping({})),
            main._LOOKUP_START_SHORTCUT_ONLY,
        )
        self.assertEqual(
            main._lookup_start_choice(
                PronounceItConfig.from_mapping({"show_context_menu": False})
            ),
            main._LOOKUP_START_SHORTCUT_ONLY,
        )
        self.assertEqual(
            main._lookup_start_choice(
                PronounceItConfig.from_mapping({"activation_mode": "option_select"})
            ),
            main._LOOKUP_START_OPTION_SELECT,
        )

    def test_lookup_start_config_writes_existing_keys(self) -> None:
        self.assertEqual(
            main._lookup_start_config(main._LOOKUP_START_SHORTCUT_MENU),
            {"activation_mode": "context_menu", "show_context_menu": True},
        )
        self.assertEqual(
            main._lookup_start_config(main._LOOKUP_START_SHORTCUT_ONLY),
            {"activation_mode": "context_menu", "show_context_menu": False},
        )
        self.assertEqual(
            main._lookup_start_config(main._LOOKUP_START_OPTION_SELECT),
            {"activation_mode": "option_select", "show_context_menu": False},
        )

    def test_lookup_start_config_defaults_to_shortcut_and_menu(self) -> None:
        self.assertEqual(
            main._lookup_start_config("unknown"),
            {"activation_mode": "context_menu", "show_context_menu": True},
        )

    def test_modifier_display_names_are_plain_language(self) -> None:
        self.assertEqual(main._modifier_display_name("alt"), "Option/Alt")
        self.assertEqual(main._modifier_display_name("meta"), "Command/Meta")
        self.assertEqual(main._modifier_display_name("disabled"), "Disabled")
        self.assertEqual(main._modifier_display_name("mystery"), "Option/Alt")

    def test_behavior_preview_lines_describe_current_controls(self) -> None:
        preview = main._behavior_preview_lines(
            PronounceItConfig.from_mapping(
                {
                    "hotkey": "Mod+P",
                    "direct_click_modifier": "alt",
                    "popup_click_modifier": "disabled",
                }
            )
        )

        self.assertEqual(
            preview,
            [
                "Mod+P pronounces the current selection",
                "Option/Alt + left-click plays audio",
                "Popup lookup disabled",
            ],
        )

    def test_lookup_payload_supports_manual_pronunciation(self) -> None:
        payload = main._lookup_payload("GCS")

        self.assertTrue(payload["found"])
        self.assertEqual(payload["term"], "Glasgow Coma Scale")
        self.assertEqual(payload["speechText"], "glaz goh koh muh skayl")
        self.assertEqual(payload["audioKind"], "bundled")
        self.assertFalse(payload["alreadySaved"])

    def test_lookup_payload_for_unknown_word_is_playable_generated_audio(self) -> None:
        payload = main._lookup_payload("notarealmedicalword")

        self.assertFalse(payload["found"])
        self.assertEqual(payload["audioKind"], "generated")
        self.assertEqual(payload["audioStatus"], "Generated audio available")
        self.assertTrue(payload["audioAvailable"])

    def test_lookup_payload_does_not_label_missing_bundled_audio_ready(self) -> None:
        with TemporaryDirectory() as tmp:
            original_root = main._addon_root
            original_config = main._config
            try:
                main._addon_root = Path(tmp)
                main._config = lambda: PronounceItConfig.from_mapping({})
                payload = main._enrich_lookup_payload(
                    {
                        "requestedText": "Example",
                        "term": "Example",
                        "pronunciation": "EX-am-pul",
                        "syllables": "ex-am-ple",
                        "speechText": "ex am pul",
                        "audioFile": "audio/example.aiff",
                        "found": True,
                    }
                )
            finally:
                main._addon_root = original_root
                main._config = original_config

        self.assertEqual(payload["audioKind"], "generated")
        self.assertNotEqual(payload["audioStatus"], "Bundled audio ready")

    def test_handle_speak_sends_success_callback(self) -> None:
        reviewer = FakeReviewer()
        original_tts = main._tts
        try:
            main._tts = FakeTts(TtsResult(True, "playing local audio"))
            ok = main._handle_speak(
                {"text": "kloh zuh peen", "term": "clozapine", "audioFile": "audio/clozapine.aiff"},
                reviewer,
            )
        finally:
            main._tts = original_tts

        self.assertTrue(ok)
        self.assertEqual(len(reviewer.web.scripts), 1)
        self.assertIn("window.PronounceIt && window.PronounceIt.spoken", reviewer.web.scripts[0])
        self.assertIn('"ok": true', reviewer.web.scripts[0])

    def test_handle_speak_sends_failure_callback(self) -> None:
        reviewer = FakeReviewer()
        original_tts = main._tts
        try:
            main._tts = FakeTts(TtsResult(False, "local audio unavailable"))
            ok = main._handle_speak(
                {"text": "kloh zuh peen", "term": "clozapine", "audioFile": "audio/missing.aiff"},
                reviewer,
            )
        finally:
            main._tts = original_tts

        self.assertFalse(ok)
        self.assertEqual(len(reviewer.web.scripts), 1)
        self.assertIn('"ok": false', reviewer.web.scripts[0])
        self.assertIn("local audio unavailable", reviewer.web.scripts[0])

    def test_write_config_sanitizes_config_mapping(self) -> None:
        written = main._write_config({"audio_backend": "bad", "tts_volume": 200, "theme": "neon"})

        self.assertEqual(written["audio_backend"], "local_audio_then_tts")
        self.assertEqual(written["tts_volume"], 100)
        self.assertEqual(written["theme"], "system")

    def test_show_manual_pronunciation_displays_and_speaks_phonetic_text(self) -> None:
        shown: list[tuple[str, str]] = []
        spoken: list[dict] = []
        original_show_text = main._show_text
        original_handle_speak = main._handle_speak

        try:
            main._show_text = lambda title, text: shown.append((title, text))
            main._handle_speak = lambda payload: spoken.append(payload)
            main._show_manual_pronunciation("agranulocytosis")
        finally:
            main._show_text = original_show_text
            main._handle_speak = original_handle_speak

        self.assertEqual(shown[0][0], "PronounceIt")
        self.assertIn("uh-GRAN-yoo-loh-sy-TOH-sis", shown[0][1])
        self.assertEqual(
            spoken,
            [
                {
                    "text": "uh gran yoo loh sy toh sis",
                    "term": "agranulocytosis",
                    "audioFile": "audio/agranulocytosis.aiff",
                }
            ],
        )

    def test_save_custom_pronunciation_reloads_dictionary(self) -> None:
        with TemporaryDirectory() as tmp:
            original_root = main._addon_root
            original_custom = main._custom
            original_dictionary = main._dictionary
            try:
                main._addon_root = Path(tmp)
                main._custom = None
                main._dictionary = PronunciationDictionary.bundled()
                record = main._save_custom_pronunciation(
                    "clozapine",
                    "LOCAL-KLOH-zuh-peen",
                    "clo-za-pine",
                    "custom audio kloh zuh peen",
                )
                payload = main._lookup_payload("clozapine")
            finally:
                main._addon_root = original_root
                main._custom = original_custom
                main._dictionary = original_dictionary

        self.assertEqual(record["pronunciation"], "LOCAL-KLOH-zuh-peen")
        self.assertEqual(payload["source"], "user-override")
        self.assertEqual(payload["speechText"], "custom audio kloh zuh peen")


if __name__ == "__main__":
    unittest.main()
