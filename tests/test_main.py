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

    def addMenu(self, menu):
        submenu = menu if isinstance(menu, FakeMenu) else FakeMenu(str(menu))
        self.submenus.append(submenu)
        return submenu

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
        self.assertEqual(len(reviewer.web.scripts), 2)
        self.assertEqual(reviewer.web.scripts[0], "window.PronounceIt && window.PronounceIt.hide();")
        self.assertIn("window.PronounceIt && window.PronounceIt.spoken", reviewer.web.scripts[1])
        self.assertIn('"ok": false', reviewer.web.scripts[1])
        self.assertIn('"reason": "Reveal the answer before using PronounceIt."', reviewer.web.scripts[1])
        self.assertIn('"term": "agranulocytosis"', reviewer.web.scripts[1])
        self.assertIn("pronunciation blocked before answer reveal", reviewer.web.scripts[1])

    def test_audio_lookup_blocked_on_question_side_returns_spoken_status(self) -> None:
        reviewer = FakeReviewer()
        original_answer_visible = main._reviewer_answer_visible
        try:
            main._reviewer_answer_visible = False
            handled = main._on_js_message(
                (False, None),
                "pronounceit:audioLookup:" + json.dumps({"text": "clozapine"}),
                reviewer,
            )
        finally:
            main._reviewer_answer_visible = original_answer_visible

        self.assertEqual(handled, (True, None))
        self.assertEqual(len(reviewer.web.scripts), 2)
        self.assertEqual(reviewer.web.scripts[0], "window.PronounceIt && window.PronounceIt.hide();")
        self.assertIn('"ok": false', reviewer.web.scripts[1])
        self.assertIn('"reason": "Reveal the answer before using PronounceIt."', reviewer.web.scripts[1])
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

    def test_reviewer_context_menu_routes_to_reviewer_webview(self) -> None:
        reviewer = FakeReviewer()
        menu = FakeMenu()
        original_config = main._config
        original_import = __import__

        class FakeMw:
            state = "review"

        def fake_import(name, *args, **kwargs):
            if name == "aqt":
                class FakeAqt:
                    mw = FakeMw()

                return FakeAqt
            return original_import(name, *args, **kwargs)

        import builtins

        try:
            builtins.__import__ = fake_import
            main._config = lambda: PronounceItConfig.from_mapping({})
            main._on_reviewer_will_show_context_menu(reviewer, menu)
        finally:
            main._config = original_config
            builtins.__import__ = original_import

        self.assertEqual([submenu.title for submenu in menu.submenus], ["PronounceIt"])

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

    def test_native_context_menu_hook_adds_actions_in_review(self) -> None:
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
        webview = FakeWebView("clozapine")
        try:
            builtins.__import__ = fake_import
            main._on_webview_will_show_context_menu(webview, menu)
        finally:
            builtins.__import__ = original_import

        self.assertEqual(menu.actions, [])
        self.assertEqual(len(menu.submenus), 1)
        submenu = menu.submenus[0]
        self.assertEqual(
            [label for label, _action in submenu.actions],
            ["Play pronunciation", "Show pronunciation details…", "Save pronunciation"],
        )
        for _label, action in submenu.actions:
            action.callback()
        self.assertEqual(
            menu.submenus[0].title,
            "PronounceIt",
        )
        self.assertEqual(
            webview.scripts,
            [
                "window.PronounceIt && window.PronounceIt.playContextTarget();",
                "window.PronounceIt && window.PronounceIt.showContextDetails();",
                "window.PronounceIt && window.PronounceIt.saveContextTarget();",
            ],
        )

    def test_native_context_menu_hook_hides_save_when_disabled(self) -> None:
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
            main._config = lambda: PronounceItConfig.from_mapping({"show_save_button": False})
            builtins.__import__ = fake_import
            main._on_webview_will_show_context_menu(FakeWebView("clozapine"), menu)
        finally:
            main._config = original_config
            builtins.__import__ = original_import

        self.assertEqual(
            [label for label, _action in menu.submenus[0].actions],
            ["Play pronunciation", "Show pronunciation details…"],
        )

    def test_native_context_menu_hook_is_hidden_outside_review(self) -> None:
        class FakeMw:
            state = "deckBrowser"

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

        self.assertEqual(menu.submenus, [])

    def test_native_context_menu_hook_can_be_disabled(self) -> None:
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
            main._config = lambda: PronounceItConfig.from_mapping(
                {"show_native_context_menu": False}
            )
            builtins.__import__ = fake_import
            main._on_webview_will_show_context_menu(FakeWebView("clozapine"), menu)
        finally:
            builtins.__import__ = original_import
            main._config = original_config

        self.assertEqual(menu.submenus, [])

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

    def test_tools_menu_installs_pronounceit_actions(self) -> None:
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

        self.assertEqual(FakeMw.form.menuTools.submenus, [])
        self.assertEqual(len(FakeMw.form.menuTools.actions), 3)
        labels = [label for label, _action in FakeMw.form.menuTools.actions]
        self.assertEqual(
            labels,
            [
                "Pronounce Word or Selection",
                "PronounceIt Settings...",
                "PronounceIt Audio Diagnostics...",
            ],
        )
        self.assertIs(
            FakeMw.form.menuTools.actions[0][1].callback,
            main._pronounce_current_reviewer_selection,
        )
        self.assertEqual(FakeMw.form.menuTools.actions[0][1].shortcut, "")
        self.assertIs(FakeMw.form.menuTools.actions[1][1].callback, main._show_config_dialog)
        self.assertIs(FakeMw.form.menuTools.actions[2][1].callback, main._show_audio_diagnostics)

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
                f"Hold {main._modifier_display_name('alt')} while clicking or dragging, or tap {main._modifier_display_name('alt')} after selecting",
                "Right-click plays and opens pronunciation details",
                "Shift + right-click opens Anki's menu with PronounceIt actions",
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
        self.assertIn("Backend: local_audio_then_tts", text)
        self.assertIn("Audio file: audio/clozapine.aiff", text)
        self.assertIn("Reason: local audio unavailable", text)
        self.assertIn("local-audio-file: local audio unavailable", text)

    def test_write_config_sanitizes_config_mapping(self) -> None:
        written = main._write_config({"audio_backend": "bad", "tts_volume": 200, "theme": "neon"})

        self.assertEqual(written["audio_backend"], "local_audio_then_tts")
        self.assertEqual(written["tts_volume"], 100)
        self.assertEqual(written["theme"], "system")

    def test_show_manual_pronunciation_displays_guide_and_speaks_fluent_term(self) -> None:
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
