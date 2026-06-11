import unittest
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class WebAssetTests(unittest.TestCase):
    def test_javascript_contains_required_reviewer_actions(self) -> None:
        js = (ROOT / "web" / "pronounceit.js").read_text(encoding="utf-8")

        self.assertNotIn("Pronounce selected word", js)
        self.assertIn("Add to pronunciation list", js)
        self.assertIn("showMenu", js)
        self.assertIn('send("menu"', js)
        self.assertIn('send("lookup"', js)
        self.assertIn('send("speak"', js)
        self.assertIn("payload.audioFile", js)
        self.assertIn('send("save"', js)
        self.assertIn("payload.autoPlay", js)
        self.assertIn("payload.saveAfterLookup", js)
        self.assertIn("payload.alreadySaved", js)
        self.assertIn("payload.speechText", js)
        self.assertIn("contextmenu", js)
        self.assertIn("keydown", js)
        self.assertIn("wordAtPoint", js)
        self.assertIn("lastPointerRequest", js)
        self.assertIn("pronounceCurrent", js)
        self.assertIn("allowOnQuestionSide", js)
        self.assertIn("answerVisible", js)
        self.assertIn("function canPronounce", js)
        self.assertIn("caretRangeFromPoint", js)
        self.assertIn("pendingRequest", js)

    def test_context_menu_can_fall_back_to_word_under_pointer(self) -> None:
        js = (ROOT / "web" / "pronounceit.js").read_text(encoding="utf-8")

        self.assertIn("pendingRequest = rememberPointerRequest(event)", js)
        self.assertIn("termFromElement(event.target)", js)
        self.assertIn("[A-Za-z0-9'\\u2010-\\u2015-]+$", js)
        self.assertIn("^[A-Za-z0-9'\\u2010-\\u2015-]+", js)
        self.assertIn("function termFromElement", js)
        self.assertIn("function isPlausibleElementTerm", js)
        self.assertIn("event.stopPropagation()", js)
        self.assertIn("}, true);", js)
        self.assertIn("function rangeAtPoint", js)
        self.assertIn("function textNodeRangeAtPoint", js)
        self.assertIn("function nearestTextOffset", js)
        self.assertIn("requestMenu(event, pendingRequest)", js)

    def test_hotkey_and_tools_can_use_last_pointer_word(self) -> None:
        js = (ROOT / "web" / "pronounceit.js").read_text(encoding="utf-8")

        self.assertIn("function rememberPointerRequest", js)
        self.assertIn("document.addEventListener(\"mousedown\", rememberPointerRequest, true)", js)
        self.assertIn("document.addEventListener(\"mouseup\", rememberPointerRequest, true)", js)
        self.assertIn("document.addEventListener(\"click\", rememberPointerRequest, true)", js)
        self.assertIn("document.addEventListener(\"pointerdown\", rememberPointerRequest, true)", js)
        self.assertIn("document.addEventListener(\"pointermove\", rememberPointerRequestThrottled, true)", js)
        self.assertIn("document.addEventListener(\"focusin\", rememberPointerRequest, true)", js)
        self.assertIn("document.addEventListener(\"mousemove\", rememberPointerRequestThrottled, true)", js)
        self.assertIn("pendingRequest = selectedText() || lastPointerRequest", js)

    def test_word_extraction_handles_hyphenated_medical_terms(self) -> None:
        if not shutil.which("node"):
            self.skipTest("node is not available")

        script = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[1], "utf8");
const hooks = {};
const sandbox = {
  pycmd() {},
  Node: { TEXT_NODE: 3 },
  NodeFilter: { SHOW_TEXT: 4 },
  window: {
    PronounceItConfig: {},
    PronounceItTestHooks: hooks,
    addEventListener() {},
  },
  document: {
    addEventListener() {},
    caretRangeFromPoint: null,
    caretPositionFromPoint: null,
    createRange() {
      return { setStart() {}, collapse() {} };
    },
    createTreeWalker() {
      return { nextNode() { return null; } };
    },
    body: {},
  },
};
vm.createContext(sandbox);
vm.runInContext(code, sandbox, { filename: "pronounceit.js" });
const extract = sandbox.window.PronounceItTestHooks.extractTermAtOffset;
if (typeof extract !== "function") {
  throw new Error("extractTermAtOffset hook was not registered");
}
const cases = [
  ["Wolff-Parkinson-White", 8, "Wolff-Parkinson-White"],
  ["Wolff\u2011Parkinson\u2011White", 8, "Wolff\u2011Parkinson\u2011White"],
  ["piperacillin-tazobactam", 13, "piperacillin-tazobactam"],
  ["sulfamethoxazole-trimethoprim", 20, "sulfamethoxazole-trimethoprim"],
  ["12-34", 2, null],
];
for (const [text, offset, expected] of cases) {
  const actual = extract(text, offset);
  if (actual !== expected) {
    throw new Error(`${text} at ${offset}: expected ${expected}, got ${actual}`);
  }
}
"""
        subprocess.run(
            ["node", "-e", script, str(ROOT / "web" / "pronounceit.js")],
            check=True,
            text=True,
            capture_output=True,
        )

    def test_element_term_extraction_handles_marked_medical_terms(self) -> None:
        if not shutil.which("node"):
            self.skipTest("node is not available")

        script = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[1], "utf8");
const hooks = {};
const body = {};
const sandbox = {
  pycmd() {},
  Node: { TEXT_NODE: 3 },
  NodeFilter: { SHOW_TEXT: 4 },
  window: {
    PronounceItConfig: {},
    PronounceItTestHooks: hooks,
    addEventListener() {},
  },
  document: {
    body,
    addEventListener() {},
    caretRangeFromPoint: null,
    caretPositionFromPoint: null,
    createRange() {
      return { setStart() {}, collapse() {} };
    },
    createTreeWalker() {
      return { nextNode() { return null; } };
    },
  },
};
vm.createContext(sandbox);
vm.runInContext(code, sandbox, { filename: "pronounceit.js" });
const termFromElement = sandbox.window.PronounceItTestHooks.termFromElement;
const rect = { left: 10, top: 20, right: 110, bottom: 40, width: 100, height: 20 };
const element = {
  textContent: "Wolff-Parkinson-White",
  parentElement: body,
  getBoundingClientRect() { return rect; },
};
const request = termFromElement(element);
if (!request || request.text !== "Wolff-Parkinson-White" || request.rect.left !== 10) {
  throw new Error(`bad element request: ${JSON.stringify(request)}`);
}
const parent = {
  textContent: "Tx of erysipelas + cellulitis?",
  parentElement: body,
  getBoundingClientRect() { return rect; },
};
if (termFromElement(parent) !== null) {
  throw new Error("overbroad element text should be rejected");
}
"""
        subprocess.run(
            ["node", "-e", script, str(ROOT / "web" / "pronounceit.js")],
            check=True,
            text=True,
            capture_output=True,
        )

    def test_css_contains_popup_and_menu_styles(self) -> None:
        css = (ROOT / "web" / "pronounceit.css").read_text(encoding="utf-8")

        self.assertIn(".pronounceit-popup", css)
        self.assertIn(".pronounceit-menu", css)
        self.assertIn(".pronounceit-pronunciation.generated", css)
        self.assertIn("position: fixed", css)
        self.assertIn("z-index", css)


if __name__ == "__main__":
    unittest.main()
