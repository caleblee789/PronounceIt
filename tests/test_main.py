import json
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pronounceit import main
from pronounceit.config import PronounceItConfig
from pronounceit.dictionary import PronunciationDictionary
from pronounceit.storage import SavedPronunciations
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


class FakeOriginCard:
    id = 123
    nid = 456
    did = 789


class FakeWebView:
    def __init__(self, selected_text: str) -> None:
        self._selected_text = selected_text
        self.title = "main webview"
        self.scripts: list[str] = []

    def selectedText(self) -> str:
        return self._selected_text

    def eval(self, javascript: str) -> None:
        self.scripts.append(javascript)


class FakeAction:
    def __init__(self, label: str = "", parent=None) -> None:
        self.label = label
        self.text = label
        self._menu = None
        self.shortcut = ""
        self.callback = None
        self.triggered = self

    def connect(self, callback) -> None:
        self.callback = callback

    def setShortcut(self, shortcut: str) -> None:
        self.shortcut = shortcut

    def menu(self):
        return self._menu


class FakeMenu:
    def __init__(self, title: str = "", parent=None) -> None:
        self.title = title
        self._object_name = ""
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

    def addMenu(self, menu):
        submenu = menu if isinstance(menu, FakeMenu) else FakeMenu(str(menu))
        action = FakeAction(submenu.title, self)
        action._menu = submenu
        self.submenus.append(submenu)
        return submenu

    def addSeparator(self) -> None:
        self.actions.append(("---", FakeAction("---")))

    def setObjectName(self, name: str) -> None:
        self._object_name = name

    def objectName(self) -> str:
        return self._object_name


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
                "term": "bundle",
                "pronunciation": "BUN-dul",
                "syllables": "bun-dle",
            },
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
            {
                "term": "acute interstitial nephritis",
                "pronunciation": "uh-KYOOT in-tur-STISH-ul neh-FRY-tis",
                "syllables": "a-cute in-ter-sti-tial ne-phri-tis",
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

    def test_lookup_message_prefers_context_phrase_over_exact_word_match(self) -> None:
        reviewer = FakeReviewer()
        main._dictionary = make_phrase_dictionary()
        context = "ECG shows right bundle branch block today."
        start = context.index("bundle")
        handled = main._on_js_message(
            (False, None),
            "pronounceit:lookup:"
            + json.dumps(
                {
                    "text": "bundle",
                    "selectedText": "bundle",
                    "contextText": context,
                    "contextOffsetStart": start,
                    "contextOffsetEnd": start + len("bundle"),
                    "rect": {"left": 4, "bottom": 8},
                }
            ),
            reviewer,
        )

        self.assertEqual(handled, (True, None))
        script = reviewer.web.scripts[0]
        self.assertIn('"requestedText": "bundle"', script)
        self.assertIn('"term": "right bundle branch block"', script)

    def test_save_lookup_uses_longest_context_phrase(self) -> None:
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
        }
        captured = []
        original_handle_save = main._handle_save
        try:
            main._handle_save = lambda context, resolved: captured.append(resolved)
            handled = main._on_js_message(
                (False, None),
                "pronounceit:saveLookup:" + json.dumps(payload),
                reviewer,
            )
        finally:
            main._handle_save = original_handle_save

        self.assertEqual(handled, (True, None))
        self.assertEqual(captured[0]["requestedText"], "bundle")
        self.assertEqual(captured[0]["term"], "right bundle branch block")

    def test_support_message_opens_support_url(self) -> None:
        reviewer = FakeReviewer()
        original_open_support_url = main._open_support_url
        calls = []
        try:
            main._open_support_url = lambda: calls.append(main.SUPPORT_URL)
            handled = main._on_js_message((False, None), "pronounceit:support:{}", reviewer)
        finally:
            main._open_support_url = original_open_support_url

        self.assertEqual(handled, (True, None))
        self.assertEqual(calls, ["https://buymeacoffee.com/caleblee78f"])

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
        self.assertIn('"term": "right bundle branch block"', reviewer.web.scripts[0])

    def test_audio_lookup_uses_fluent_raw_term_instead_of_spaced_respellings(self) -> None:
        reviewer = FakeReviewer()
        original_tts = main._tts
        fake_tts = FakeTts(TtsResult(True, "playing local audio"))
        try:
            main._tts = fake_tts
            handled = main._on_js_message(
                (False, None),
                "pronounceit:audioLookup:" + json.dumps({"text": "agranulocytosis"}),
                reviewer,
            )
        finally:
            main._tts = original_tts

        self.assertEqual(handled, (True, None))
        self.assertEqual(len(fake_tts.calls), 1)
        self.assertEqual(fake_tts.calls[0][0], "agranulocytosis")
        self.assertEqual(fake_tts.calls[0][1].term, "agranulocytosis")
        self.assertEqual(fake_tts.calls[0][1].quality_tier, "verified")
        self.assertIn('"ok": true', reviewer.web.scripts[0])
        self.assertIn('"term": "agranulocytosis"', reviewer.web.scripts[0])

    def test_audio_lookup_uses_acute_interstitial_nephritis_context(self) -> None:
        reviewer = FakeReviewer()
        original_tts = main._tts
        fake_tts = FakeTts(TtsResult(True, "playing local audio"))
        try:
            main._dictionary = make_phrase_dictionary()
            main._tts = fake_tts
            context = "Does this patient have acute interstitial nephritis (AIN)?"
            start = context.index("interstitial")
            handled = main._on_js_message(
                (False, None),
                "pronounceit:audioLookup:"
                + json.dumps(
                    {
                        "text": "interstitial",
                        "contextText": context,
                        "contextOffsetStart": start,
                        "contextOffsetEnd": start + len("interstitial"),
                    }
                ),
                reviewer,
            )
        finally:
            main._tts = original_tts

        self.assertEqual(handled, (True, None))
        self.assertEqual(len(fake_tts.calls), 1)
        self.assertEqual(fake_tts.calls[0][1].term, "acute interstitial nephritis")

    def test_audio_lookup_expands_partial_unknown_phrase_from_context(self) -> None:
        reviewer = FakeReviewer()
        original_tts = main._tts
        fake_tts = FakeTts(TtsResult(True, "playing generated audio"))
        try:
            main._dictionary = make_phrase_dictionary()
            main._tts = fake_tts
            context = "REM sleep improves memory."
            start = context.index("REM") + 1
            end = context.index("sleep") + len("sle")
            handled = main._on_js_message(
                (False, None),
                "pronounceit:audioLookup:"
                + json.dumps(
                    {
                        "text": "REM sleep",
                        "selectedText": "EM sle",
                        "contextText": context,
                        "contextOffsetStart": start,
                        "contextOffsetEnd": end,
                    }
                ),
                reviewer,
            )
        finally:
            main._tts = original_tts

        self.assertEqual(handled, (True, None))
        self.assertEqual(len(fake_tts.calls), 1)
        self.assertEqual(fake_tts.calls[0][0], "REM sleep")
        self.assertEqual(fake_tts.calls[0][1].term, "REM sleep")

    def test_audio_lookup_for_unknown_single_word_uses_generated_fallback_payload(self) -> None:
        reviewer = FakeReviewer()
        original_tts = main._tts
        fake_tts = FakeTts(TtsResult(True, "playing generated audio"))
        try:
            main._tts = fake_tts
            handled = main._on_js_message(
                (False, None),
                "pronounceit:audioLookup:" + json.dumps({"text": "notarealmedicalword"}),
                reviewer,
            )
        finally:
            main._tts = original_tts

        self.assertEqual(handled, (True, None))
        self.assertEqual(len(fake_tts.calls), 1)
        self.assertEqual(fake_tts.calls[0][0], "notarealmedicalword")
        self.assertEqual(fake_tts.calls[0][1].term, "notarealmedicalword")
        self.assertEqual(fake_tts.calls[0][1].audio_file, "")
        self.assertIn('"ok": true', reviewer.web.scripts[0])

    def test_audio_lookup_failure_reports_reason_term_and_attempts(self) -> None:
        reviewer = FakeReviewer()
        original_tts = main._tts
        fake_tts = FakeTts(
            TtsResult(
                False,
                "local audio unavailable",
                ["local-audio-file: local audio unavailable"],
            )
        )
        try:
            main._tts = fake_tts
            handled = main._on_js_message(
                (False, None),
                "pronounceit:audioLookup:" + json.dumps({"text": "clozapine"}),
                reviewer,
            )
        finally:
            main._tts = original_tts

        self.assertEqual(handled, (True, None))
        script = reviewer.web.scripts[0]
        self.assertIn('"ok": false', script)
        self.assertIn('"reason": "local audio unavailable"', script)
        self.assertIn('"term": "clozapine"', script)
        self.assertIn("local-audio-file: local audio unavailable", script)

    def test_lookup_message_is_blocked_when_question_side_is_explicitly_disabled(self) -> None:
        reviewer = FakeReviewer()
        original_answer_visible = main._reviewer_answer_visible
        original_config = main._config
        try:
            main._reviewer_answer_visible = False
            main._config = lambda: PronounceItConfig.from_mapping(
                {"allow_on_question_side": False}
            )
            handled = main._on_js_message(
                (False, None),
                "pronounceit:lookup:" + json.dumps({"text": "agranulocytosis"}),
                reviewer,
            )
        finally:
            main._reviewer_answer_visible = original_answer_visible
            main._config = original_config

        self.assertEqual(handled, (True, None))
        self.assertEqual(len(reviewer.web.scripts), 2)
        self.assertEqual(reviewer.web.scripts[0], "window.PronounceIt && window.PronounceIt.hide();")
        self.assertIn("window.PronounceIt && window.PronounceIt.spoken", reviewer.web.scripts[1])
        self.assertIn('"ok": false', reviewer.web.scripts[1])
        self.assertIn('"reason": "Reveal the answer before playing pronunciation."', reviewer.web.scripts[1])
        self.assertIn('"term": "agranulocytosis"', reviewer.web.scripts[1])
        self.assertIn("pronunciation blocked before answer reveal", reviewer.web.scripts[1])

    def test_audio_lookup_blocked_on_question_side_returns_spoken_status(self) -> None:
        reviewer = FakeReviewer()
        original_answer_visible = main._reviewer_answer_visible
        original_config = main._config
        try:
            main._reviewer_answer_visible = False
            main._config = lambda: PronounceItConfig.from_mapping(
                {"allow_on_question_side": False}
            )
            handled = main._on_js_message(
                (False, None),
                "pronounceit:audioLookup:" + json.dumps({"text": "clozapine"}),
                reviewer,
            )
        finally:
            main._reviewer_answer_visible = original_answer_visible
            main._config = original_config

        self.assertEqual(handled, (True, None))
        self.assertEqual(len(reviewer.web.scripts), 2)
        self.assertEqual(reviewer.web.scripts[0], "window.PronounceIt && window.PronounceIt.hide();")
        self.assertIn('"ok": false', reviewer.web.scripts[1])
        self.assertIn('"reason": "Reveal the answer before playing pronunciation."', reviewer.web.scripts[1])
        self.assertIn('"term": "clozapine"', reviewer.web.scripts[1])

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

    def test_native_context_menu_injection_is_retired(self) -> None:
        source = Path(main.__file__).read_text(encoding="utf-8")

        self.assertNotIn("reviewer_will_show_context_menu.append", source)
        self.assertNotIn('menu.addMenu("PronounceIt")', source)

    def test_selected_text_uses_audio_only_javascript_path(self) -> None:
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
            main._pronounce_text_from_reviewer("  Clozapine, ")
        finally:
            builtins.__import__ = original_import

        self.assertEqual(
            reviewer.web.scripts,
            ['window.PronounceIt && window.PronounceIt.playText("Clozapine");'],
        )
        self.assertNotIn("PronounceIt.show", reviewer.web.scripts[0])

    def test_reviewer_web_content_uses_csp_safe_external_assets(self) -> None:
        web_content = FakeWebContent()
        reviewer = FakeReviewer()

        main._on_webview_will_set_content(web_content, reviewer)

        self.assertEqual(web_content.css, ["/_addons/pronounceit/web/pronounceit.css"])
        self.assertEqual(web_content.js, ["/_addons/pronounceit/web/pronounceit.js"])
        self.assertEqual(web_content.body, "")

    def test_parse_message_rejects_non_object_and_oversized_payloads(self) -> None:
        action, payload = main._parse_message("pronounceit:lookup:[]")
        self.assertEqual(action, "lookup")
        self.assertEqual(payload, {})

        action, payload = main._parse_message(
            "pronounceit:lookup:" + json.dumps({"text": "x" * 70000})
        )
        self.assertEqual(action, "")
        self.assertEqual(payload, {})

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
        original_config = main._config

        def fake_import(name, *args, **kwargs):
            if name == "aqt":
                class FakeAqt:
                    mw = FakeMw()

                return FakeAqt
            return original_import(name, *args, **kwargs)

        import builtins

        try:
            main._reviewer_answer_visible = False
            main._config = lambda: PronounceItConfig.from_mapping(
                {"allow_on_question_side": False}
            )
            builtins.__import__ = fake_import
            self.assertFalse(main._pronunciation_allowed())
            self.assertFalse(main._js_config_payload()["answerVisible"])
        finally:
            builtins.__import__ = original_import
            main._reviewer_answer_visible = original_answer_visible
            main._config = original_config

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

    def test_tools_menu_installs_pronounceit_actions(self) -> None:
        class FakeAddonManager:
            def getConfig(self, module):
                return {"hotkey": "Mod+P"}

        class FakeMw:
            addonManager = FakeAddonManager()

            class Form:
                menuTools = FakeMenu("Tools")
                menubar = FakeMenu("Menu Bar")

            form = Form()

        fake_aqt = types.ModuleType("aqt")
        fake_aqt.mw = FakeMw()
        fake_qt = types.ModuleType("aqt.qt")
        fake_qt.QAction = FakeAction
        original_aqt = sys.modules.get("aqt")
        original_qt = sys.modules.get("aqt.qt")
        try:
            sys.modules["aqt"] = fake_aqt
            sys.modules["aqt.qt"] = fake_qt
            main._install_tools_menu_actions()
            main._install_tools_menu_actions()
            delattr(fake_aqt.mw, "_pronounceit_settings_action")
            delattr(fake_aqt.mw, "_caleb_m_addons_menu")
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

        self.assertEqual(FakeMw.form.menuTools.actions, [])
        self.assertEqual(FakeMw.form.menuTools.submenus, [])
        self.assertEqual(len(FakeMw.form.menubar.submenus), 1)
        submenu = FakeMw.form.menubar.submenus[0]
        self.assertEqual(submenu.title, "Caleb M. Add-ons Settings")
        self.assertEqual(submenu.objectName(), "caleb_m_addons_menu")
        self.assertEqual(len(submenu.actions), 1)
        labels = [label for label, _action in submenu.actions]
        self.assertEqual(labels, ["PronounceIt settings"])
        self.assertIs(submenu.actions[0][1].callback, main._show_config_dialog)
        self.assertEqual(submenu.actions[0][1].shortcut, "")

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
        self.assertEqual(main._modifier_display_name("alt", platform="darwin"), "Option")
        self.assertEqual(main._modifier_display_name("alt", platform="linux"), "Alt")
        self.assertEqual(main._modifier_display_name("meta", platform="darwin"), "Command")
        self.assertEqual(main._modifier_display_name("ctrl", platform="linux"), "Ctrl")
        self.assertEqual(main._modifier_display_name("mod", platform="darwin"), "Command")
        self.assertEqual(main._modifier_display_name("mod", platform="linux"), "Ctrl")
        self.assertEqual(main._modifier_display_name("disabled", platform="darwin"), "Disabled")
        self.assertEqual(main._modifier_display_name("mystery", platform="linux"), "Alt")

    def test_legacy_mod_modifier_maps_to_one_physical_key_in_settings(self) -> None:
        self.assertEqual(main._activation_modifier_ui_value("mod", platform="darwin"), "meta")
        self.assertEqual(main._activation_modifier_ui_value("mod", platform="linux"), "ctrl")
        self.assertEqual(main._activation_modifier_ui_value("alt", platform="darwin"), "alt")

    def test_pack_presentation_uses_semantic_user_facing_states(self) -> None:
        installed = main._pack_presentation(
            main.AudioPackDownloadState(phase="installed", installed=True)
        )
        downloading = main._pack_presentation(
            main.AudioPackDownloadState(phase="downloading", done_bytes=10, total_bytes=100)
        )
        verifying = main._pack_presentation(
            main.AudioPackDownloadState(phase="verifying", installed=True)
        )
        paused = main._pack_presentation(
            main.AudioPackDownloadState(phase="paused", done_bytes=25, total_bytes=100)
        )
        failed = main._pack_presentation(
            main.AudioPackDownloadState(
                phase="failed",
                done_bytes=25,
                total_bytes=100,
                message="Verification failed.",
            )
        )

        self.assertEqual((installed.status, installed.tone, installed.verified), ("Installed", "installed", True))
        self.assertEqual((downloading.status, downloading.progress_text), ("Downloading… 10%", "10%"))
        self.assertEqual((verifying.status, verifying.progress_indeterminate), ("Verifying…", True))
        self.assertEqual((paused.status, paused.progress_text), ("Paused • 25%", "25% • Ready to resume"))
        self.assertEqual((failed.status, failed.tone), ("Verification failed", "failed"))

    def test_audio_pack_onboarding_needed_only_once_for_missing_pack(self) -> None:
        unseen = PronounceItConfig.from_mapping({"audio_pack_prompt_seen": False})
        seen = PronounceItConfig.from_mapping({"audio_pack_prompt_seen": True})

        self.assertTrue(
            main._audio_pack_onboarding_needed(unseen, main.AudioPackDownloadState())
        )
        self.assertFalse(
            main._audio_pack_onboarding_needed(
                unseen, main.AudioPackDownloadState(phase="installed", installed=True)
            )
        )
        self.assertFalse(
            main._audio_pack_onboarding_needed(
                unseen, main.AudioPackDownloadState(phase="downloading")
            )
        )
        self.assertFalse(
            main._audio_pack_onboarding_needed(seen, main.AudioPackDownloadState())
        )

    def test_audio_pack_onboarding_persists_before_starting_download(self) -> None:
        calls: list[object] = []

        class Controller:
            def start(self):
                calls.append("start")
                return True

        original_config = main._config
        original_write = main._write_config
        original_controller = main._audio_pack_download
        try:
            main._config = lambda: PronounceItConfig.from_mapping(
                {"audio_pack_prompt_seen": False, "audio_backend": "local_audio_then_tts"}
            )
            main._write_config = lambda mapping: calls.append(dict(mapping)) or mapping
            main._audio_pack_download = Controller()
            main._complete_audio_pack_onboarding(True)
        finally:
            main._config = original_config
            main._write_config = original_write
            main._audio_pack_download = original_controller

        self.assertTrue(calls[0]["audio_pack_prompt_seen"])
        self.assertEqual(calls[0]["audio_backend"], "local_audio_then_tts")
        self.assertEqual(calls[1], "start")

    def test_legacy_theme_migration_resolves_and_persists_once(self) -> None:
        original_read = main._read_config_mapping
        original_write = main._write_config
        original_current = main._current_anki_theme
        writes: list[dict] = []
        try:
            main._read_config_mapping = lambda: {"theme": "system"}
            main._current_anki_theme = lambda: "dark"
            main._write_config = lambda mapping: writes.append(dict(mapping)) or mapping
            migrated = main._migrate_theme_config()
        finally:
            main._read_config_mapping = original_read
            main._write_config = original_write
            main._current_anki_theme = original_current

        self.assertEqual(migrated["theme"], "dark")
        self.assertTrue(migrated["theme_initialized"])
        self.assertEqual(writes, [migrated])

    def test_support_button_reuses_progressbar_asset_format(self) -> None:
        self.assertTrue(main._support_image_path().is_file())
        style = main._support_button_style()
        self.assertIn("buyMeACoffeeButton", style)
        self.assertIn("buy_me_a_coffee.png", style)

    def test_behavior_preview_lines_describe_current_controls(self) -> None:
        preview = main._behavior_preview_lines(
            PronounceItConfig.from_mapping(
                {
                    "direct_click_modifier": "alt",
                }
            )
        )

        self.assertEqual(
            preview,
            [
                "Using PronounceIt",
                f"• Hold {main._modifier_display_name('alt')} while clicking or dragging text to play pronunciation.",
                f"• Or select text, then tap {main._modifier_display_name('alt')}.",
                f"• Hold {main._modifier_display_name('ctrl')} while clicking or right-clicking, or press {main._modifier_display_name('ctrl')} after selecting text, to open the quick pronunciation card.",
            ],
        )

    def test_lookup_payload_supports_manual_pronunciation(self) -> None:
        payload = main._lookup_payload("GCS")

        self.assertTrue(payload["found"])
        self.assertEqual(payload["term"], "Glasgow Coma Scale")
        self.assertEqual(payload["speechText"], "glaz goh koh muh skayl")
        self.assertEqual(payload["audioSource"], "azure")
        self.assertEqual(payload["audioSourceLabel"], "High Quality Downloaded Pack")
        self.assertFalse(payload["alreadySaved"])

    def test_lookup_payload_for_unknown_word_is_playable_generated_audio(self) -> None:
        payload = main._lookup_payload("notarealmedicalword")

        self.assertFalse(payload["found"])
        self.assertEqual(payload["audioSource"], "generated")
        self.assertEqual(payload["audioSourceLabel"], "Standard text-to-speech")
        self.assertEqual(payload["audioStatus"], "Standard text-to-speech ready")
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

        self.assertEqual(payload["audioSource"], "generated")
        self.assertEqual(payload["audioSourceLabel"], "Standard text-to-speech")
        self.assertNotEqual(payload["audioStatus"], "High Quality Downloaded Pack ready")

    def test_lookup_payload_classifies_playable_user_audio_as_custom(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio_file = root / "user_files" / "audio" / "example.wav"
            audio_file.parent.mkdir(parents=True)
            audio_file.write_bytes(b"custom audio")
            original_root = main._addon_root
            original_config = main._config
            try:
                main._addon_root = root
                main._config = lambda: PronounceItConfig.from_mapping({})
                payload = main._enrich_lookup_payload(
                    {
                        "term": "Example",
                        "audioFile": "example.wav",
                        "source": "user-override",
                        "found": True,
                    }
                )
            finally:
                main._addon_root = original_root
                main._config = original_config

        self.assertEqual(payload["audioSource"], "custom")
        self.assertEqual(payload["audioSourceLabel"], "Custom audio")
        self.assertEqual(payload["audioStatus"], "Custom audio ready")

    def test_lookup_payload_classifies_pack_and_system_tts_sources(self) -> None:
        class InstalledStatus:
            installed = True

        class InstalledPack:
            def status(self):
                return InstalledStatus()

        original_pack = main._audio_pack
        original_config = main._config
        try:
            main._audio_pack = InstalledPack()
            main._config = lambda: PronounceItConfig.from_mapping({})
            pack_payload = main._enrich_lookup_payload({"term": "Example", "found": True})
            main._audio_pack = None
            main._config = lambda: PronounceItConfig.from_mapping(
                {"audio_backend": "system_tts"}
            )
            live_payload = main._enrich_lookup_payload({"term": "Unknown", "found": False})
        finally:
            main._audio_pack = original_pack
            main._config = original_config

        self.assertEqual(pack_payload["audioSource"], "azure")
        self.assertEqual(pack_payload["audioSourceLabel"], "High Quality Downloaded Pack")
        self.assertEqual(live_payload["audioSource"], "live")
        self.assertEqual(live_payload["audioSourceLabel"], "Standard text-to-speech")

    def test_handle_save_includes_reviewer_origin_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            reviewer = FakeReviewer()
            reviewer.card = FakeOriginCard()
            original_saved = main._saved
            original_deck_name = main._deck_name
            try:
                main._saved = SavedPronunciations(Path(tmp))
                main._deck_name = lambda deck_id: "Medical School" if deck_id == 789 else ""
                main._handle_save(
                    reviewer,
                    {
                        "term": "Agranulocytosis",
                        "requestedText": "agranulocytosis",
                        "pronunciation": "uh-GRAN-yoo-loh-sy-TOH-sis",
                        "syllables": "a-gran-u-lo-cy-to-sis",
                        "found": True,
                    },
                )
                saved = main._saved.load()
            finally:
                main._saved = original_saved
                main._deck_name = original_deck_name

        self.assertEqual(saved[0]["cardId"], 123)
        self.assertEqual(saved[0]["noteId"], 456)
        self.assertEqual(saved[0]["deckId"], 789)
        self.assertEqual(saved[0]["deckName"], "Medical School")
        self.assertIn("window.PronounceIt && window.PronounceIt.saved", reviewer.web.scripts[0])

    def test_handle_save_reports_corrupt_storage_without_overwriting_it(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "user_files" / "saved_pronunciations.json"
            path.parent.mkdir()
            path.write_text("not json", encoding="utf-8")
            reviewer = FakeReviewer()
            original_saved = main._saved
            original_runtime = list(main._runtime_diagnostics)
            try:
                main._saved = SavedPronunciations(root)
                main._runtime_diagnostics.clear()
                main._handle_save(reviewer, {"term": "clozapine"})
            finally:
                main._saved = original_saved
                main._runtime_diagnostics[:] = original_runtime

            self.assertEqual(path.read_text(encoding="utf-8"), "not json")
            self.assertIn('"saved": false', reviewer.web.scripts[0])
            self.assertIn('"error":', reviewer.web.scripts[0])

    def test_saved_origin_search_prefers_note_id_then_card_id(self) -> None:
        self.assertEqual(
            main._saved_origin_search_query({"noteId": 456, "cardId": 123}),
            "nid:456",
        )
        self.assertEqual(main._saved_origin_search_query({"cardId": "123"}), "cid:123")
        self.assertEqual(main._saved_origin_search_query({"cardId": "not-an-id"}), "")

    def test_handle_speak_sends_success_callback(self) -> None:
        reviewer = FakeReviewer()
        original_tts = main._tts
        try:
            main._tts = FakeTts(
                TtsResult(True, "playing local audio", audio_source="azure")
            )
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
        self.assertIn('"audioSource": "azure"', reviewer.web.scripts[0])
        self.assertIn('"audioSourceLabel": "High Quality Downloaded Pack"', reviewer.web.scripts[0])

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

    def test_format_playback_diagnostics_includes_recent_attempts(self) -> None:
        original_diagnostics = list(main._playback_diagnostics)
        original_runtime = list(main._runtime_diagnostics)
        try:
            main._runtime_diagnostics[:] = ["custom pronunciations entry 2 was skipped"]
            main._playback_diagnostics[:] = [
                {
                    "text": "kloh zuh peen",
                    "term": "clozapine",
                    "audioBackend": "local_audio_then_tts",
                    "audioFile": "audio/clozapine.aiff",
                    "audioSource": "azure",
                    "ok": False,
                    "reason": "local audio unavailable",
                    "attempts": ["local-audio-file: local audio unavailable"],
                }
            ]

            text = main._format_playback_diagnostics()
        finally:
            main._playback_diagnostics[:] = original_diagnostics
            main._runtime_diagnostics[:] = original_runtime

        self.assertIn("Runtime and data warnings", text)
        self.assertIn("custom pronunciations entry 2 was skipped", text)
        self.assertIn("FAILED: kloh zuh peen", text)
        self.assertIn("Term: clozapine", text)
        self.assertIn("Playback mode: local_audio_then_tts", text)
        self.assertIn("Source: High Quality Downloaded Pack", text)
        self.assertIn("Audio file: audio/clozapine.aiff", text)
        self.assertIn("Reason: local audio unavailable", text)
        self.assertIn("local-audio-file: local audio unavailable", text)

    def test_write_config_sanitizes_config_mapping(self) -> None:
        written = main._write_config({"audio_backend": "bad", "tts_volume": 200, "theme": "neon"})

        self.assertEqual(written["audio_backend"], "local_audio_then_tts")
        self.assertEqual(written["tts_volume"], 100)
        self.assertEqual(written["theme"], "light")

    def test_show_manual_pronunciation_displays_guide_and_speaks_fluent_term(self) -> None:
        shown: list[tuple[dict, str]] = []
        spoken: list[dict] = []
        original_show_details = main._show_pronunciation_details
        original_handle_speak = main._handle_speak

        try:
            main._show_pronunciation_details = lambda payload, term: shown.append((payload, term))
            main._handle_speak = lambda payload: spoken.append(payload)
            main._show_manual_pronunciation("agranulocytosis")
        finally:
            main._show_pronunciation_details = original_show_details
            main._handle_speak = original_handle_speak

        self.assertEqual(shown[0][1], "agranulocytosis")
        self.assertEqual(shown[0][0]["pronunciation"], "uh-GRAN-yoo-loh-sy-TOH-sis")
        self.assertEqual(
            spoken,
            [
                {
                    "text": "agranulocytosis",
                    "term": "agranulocytosis",
                    "audioFile": "audio/agranulocytosis.mp3",
                    "useTextOverride": False,
                    "qualityTier": "verified",
                    "synthesisStrategy": "azure-native",
                    "audioReviewStatus": "passed",
                }
            ],
        )

    def test_pronunciation_details_use_user_facing_field_names(self) -> None:
        fields = main._pronunciation_detail_fields(
            {
                "term": "agranulocytosis",
                "pronunciation": "uh-GRAN-yoo-loh-sy-TOH-sis",
                "syllables": "a·gran·u·lo·cy·to·sis",
                "speechText": "uh gran yoo loh sy toh sis",
            },
            "agranulocytosis",
        )

        self.assertEqual(
            fields,
            [
                ("Word", "agranulocytosis"),
                ("Pronunciation", "uh-GRAN-yoo-loh-sy-TOH-sis"),
                ("Syllables", "a·gran·u·lo·cy·to·sis"),
                ("Speech text", "uh gran yoo loh sy toh sis"),
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
