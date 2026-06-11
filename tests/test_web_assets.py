import unittest
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class WebAssetTests(unittest.TestCase):
    def test_javascript_contains_required_reviewer_actions(self) -> None:
        js = (ROOT / "web" / "pronounceit.js").read_text(encoding="utf-8")

        self.assertNotIn("Pronounce selected word", js)
        self.assertIn("Save pronunciation", js)
        self.assertNotIn("Add to pronunciation list", js)
        self.assertIn("showMenu", js)
        self.assertIn('send("audioLookup"', js)
        self.assertIn('send("lookup"', js)
        self.assertIn('send("speak"', js)
        self.assertIn("payload.audioFile", js)
        self.assertIn('send("save"', js)
        self.assertIn("payload.autoPlay", js)
        self.assertNotIn("payload.saveAfterLookup", js)
        self.assertNotIn("pronounceit-save", js)
        self.assertIn("payload.alreadySaved", js)
        self.assertIn("payload.speechText", js)
        self.assertIn("contextmenu", js)
        self.assertIn("keydown", js)
        self.assertIn("wordAtPoint", js)
        self.assertIn("lastPointerRequest", js)
        self.assertIn("pronounceCurrent", js)
        self.assertIn("allowOnQuestionSide", js)
        self.assertIn("activationMode", js)
        self.assertIn("theme", js)
        self.assertIn("answerVisible", js)
        self.assertIn("function canPronounce", js)
        self.assertIn("caretRangeFromPoint", js)
        self.assertIn("pendingRequest", js)
        self.assertIn("sourceLabel", js)

    def test_modified_context_menu_can_fall_back_to_word_under_pointer(self) -> None:
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
        self.assertIn("modifierMatches(event, config.popupClickModifier)", js)
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

    def test_theme_assets_define_presets_and_apply_theme_markers(self) -> None:
        js = (ROOT / "web" / "pronounceit.js").read_text(encoding="utf-8")
        css = (ROOT / "web" / "pronounceit.css").read_text(encoding="utf-8")

        for theme in ["system", "clinical_light", "slate", "high_contrast"]:
            with self.subTest(theme=theme):
                self.assertIn(theme, js)

        self.assertIn('applyTheme(menuEl, "pronounceit-menu")', js)
        self.assertIn('applyTheme(popupEl, "pronounceit-popup")', js)
        self.assertIn('element.setAttribute("data-theme", theme)', js)
        self.assertIn("prefers-color-scheme: dark", js)
        self.assertIn("--pronounceit-bg", css)
        self.assertIn("--pronounceit-accent", css)
        self.assertIn("--pronounceit-danger", css)
        self.assertIn(".pronounceit-theme-clinical_light", css)
        self.assertIn(".pronounceit-theme-slate", css)
        self.assertIn(".pronounceit-theme-high_contrast", css)

    def test_option_select_mode_pronounces_selected_text(self) -> None:
        if not shutil.which("node"):
            self.skipTest("node is not available")

        script = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[1], "utf8");
const listeners = {};
const messages = [];
const selectionRect = { left: 4, top: 5, right: 40, bottom: 15, width: 36, height: 10 };
const sandbox = {
  pycmd(message) { messages.push(message); },
  Node: { TEXT_NODE: 3 },
  NodeFilter: { SHOW_TEXT: 4 },
  window: {
    PronounceItConfig: {
      enabled: true,
      allowOnQuestionSide: true,
      activationMode: "option_select",
    },
    PronounceItTestHooks: {},
    addEventListener() {},
    getSelection() {
      return {
        rangeCount: 1,
        toString() { return "clozapine"; },
        getRangeAt() {
          return {
            getBoundingClientRect() { return selectionRect; },
          };
        },
      };
    },
  },
  document: {
    body: {},
    addEventListener(type, callback) {
      listeners[type] = listeners[type] || [];
      listeners[type].push(callback);
    },
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
messages.length = 0;
for (const callback of listeners.mouseup || []) {
  callback({ altKey: true, preventDefault() {} });
}
const lookup = messages.find((message) => message.startsWith("pronounceit:audioLookup:"));
if (!lookup) {
  throw new Error(`missing audio lookup message: ${JSON.stringify(messages)}`);
}
const payload = JSON.parse(lookup.replace("pronounceit:audioLookup:", ""));
if (payload.text !== "clozapine" || payload.autoPlay) {
  throw new Error(`bad lookup payload: ${JSON.stringify(payload)}`);
}
"""
        subprocess.run(
            ["node", "-e", script, str(ROOT / "web" / "pronounceit.js")],
            check=True,
            text=True,
            capture_output=True,
        )

    def test_selection_request_includes_bounded_context_offsets(self) -> None:
        if not shutil.which("node"):
            self.skipTest("node is not available")

        script = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[1], "utf8");
const listeners = {};
const messages = [];
const source = "intro ".repeat(40) + "ECG shows right bundle branch block today." + " outro".repeat(40);
const start = source.indexOf("bundle");
const textNode = { nodeType: 3, textContent: source };
const selectionRect = { left: 4, top: 5, right: 40, bottom: 15, width: 36, height: 10 };
const sandbox = {
  pycmd(message) { messages.push(message); },
  Node: { TEXT_NODE: 3 },
  NodeFilter: { SHOW_TEXT: 4 },
  window: {
    PronounceItConfig: {
      enabled: true,
      allowOnQuestionSide: true,
      popupClickModifier: "alt",
    },
    addEventListener() {},
    getSelection() {
      return {
        rangeCount: 1,
        toString() { return "bundle"; },
        getRangeAt() {
          return {
            startContainer: textNode,
            endContainer: textNode,
            startOffset: start,
            endOffset: start + "bundle".length,
            getBoundingClientRect() { return selectionRect; },
          };
        },
      };
    },
  },
  document: {
    body: {},
    addEventListener(type, callback) {
      listeners[type] = listeners[type] || [];
      listeners[type].push(callback);
    },
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
messages.length = 0;
for (const callback of listeners.keydown || []) {
  callback({
    key: "p",
    ctrlKey: true,
    metaKey: false,
    altKey: false,
    shiftKey: false,
    preventDefault() {},
  });
}
const lookup = messages.find((message) => message.startsWith("pronounceit:lookup:"));
if (!lookup) {
  throw new Error(`missing lookup message: ${JSON.stringify(messages)}`);
}
const payload = JSON.parse(lookup.replace("pronounceit:lookup:", ""));
if (payload.text !== "bundle" || payload.contextText.length > 160) {
  throw new Error(`bad bounded payload: ${JSON.stringify(payload)}`);
}
if (payload.contextText.slice(payload.contextOffsetStart, payload.contextOffsetEnd) !== "bundle") {
  throw new Error(`bad context payload: ${JSON.stringify(payload)}`);
}
if (!payload.contextText.includes("right bundle branch block")) {
  throw new Error(`missing phrase context: ${JSON.stringify(payload)}`);
}
"""
        subprocess.run(
            ["node", "-e", script, str(ROOT / "web" / "pronounceit.js")],
            check=True,
            text=True,
            capture_output=True,
        )

    def test_pointer_request_includes_text_node_context(self) -> None:
        if not shutil.which("node"):
            self.skipTest("node is not available")

        script = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[1], "utf8");
const listeners = {};
const messages = [];
const source = "ECG shows right bundle branch block today.";
const start = source.indexOf("bundle");
const textNode = { nodeType: 3, textContent: source };
const sandbox = {
  pycmd(message) { messages.push(message); },
  Node: { TEXT_NODE: 3 },
  NodeFilter: { SHOW_TEXT: 4 },
  window: {
    PronounceItConfig: {
      enabled: true,
      allowOnQuestionSide: true,
    },
    addEventListener() {},
    getSelection() { return null; },
  },
  document: {
    body: {},
    addEventListener(type, callback) {
      listeners[type] = listeners[type] || [];
      listeners[type].push(callback);
    },
    caretRangeFromPoint() {
      return {
        startContainer: textNode,
        startOffset: start + 2,
        getBoundingClientRect() {
          return { left: 12, top: 14, right: 20, bottom: 24, width: 8, height: 10 };
        },
      };
    },
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
messages.length = 0;
for (const callback of listeners.contextmenu || []) {
  callback({
    altKey: true,
    clientX: 18,
    clientY: 19,
    target: sandbox.document.body,
    preventDefault() {},
    stopPropagation() {},
  });
}
const lookup = messages.find((message) => message.startsWith("pronounceit:menu:"));
if (!lookup) {
  throw new Error(`missing menu message: ${JSON.stringify(messages)}`);
}
const payload = JSON.parse(lookup.replace("pronounceit:menu:", ""));
if (
  payload.text !== "bundle" ||
  payload.contextText !== source ||
  payload.contextOffsetStart !== start ||
  payload.contextOffsetEnd !== start + "bundle".length
) {
  throw new Error(`bad pointer context payload: ${JSON.stringify(payload)}`);
}
"""
        subprocess.run(
            ["node", "-e", script, str(ROOT / "web" / "pronounceit.js")],
            check=True,
            text=True,
            capture_output=True,
        )

    def test_pointer_request_uses_parent_phrase_context_for_wrapped_word(self) -> None:
        if not shutil.which("node"):
            self.skipTest("node is not available")

        script = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[1], "utf8");
const listeners = {};
const messages = [];
const parent = { textContent: "ECG shows right bundle branch block today.", parentElement: null };
const span = { textContent: "bundle", parentElement: parent };
const textNode = { nodeType: 3, textContent: "bundle", parentElement: span };
parent.parentElement = null;
const sandbox = {
  pycmd(message) { messages.push(message); },
  Node: { TEXT_NODE: 3 },
  NodeFilter: { SHOW_TEXT: 4 },
  window: {
    PronounceItConfig: {
      enabled: true,
      allowOnQuestionSide: true,
      popupClickModifier: "alt",
    },
    addEventListener() {},
    getSelection() { return null; },
  },
  document: {
    body: {},
    addEventListener(type, callback) {
      listeners[type] = listeners[type] || [];
      listeners[type].push(callback);
    },
    caretRangeFromPoint() {
      return {
        startContainer: textNode,
        startOffset: 2,
        getBoundingClientRect() {
          return { left: 12, top: 14, right: 20, bottom: 24, width: 8, height: 10 };
        },
      };
    },
    caretPositionFromPoint: null,
    createRange() {
      return { setStart() {}, collapse() {} };
    },
    createTreeWalker() {
      return { nextNode() { return null; } };
    },
  },
};
parent.parentElement = sandbox.document.body;
vm.createContext(sandbox);
vm.runInContext(code, sandbox, { filename: "pronounceit.js" });
messages.length = 0;
for (const callback of listeners.contextmenu || []) {
  callback({
    altKey: true,
    clientX: 18,
    clientY: 19,
    target: span,
    preventDefault() {},
    stopPropagation() {},
  });
}
const lookup = messages.find((message) => message.startsWith("pronounceit:menu:"));
if (!lookup) {
  throw new Error(`missing menu message: ${JSON.stringify(messages)}`);
}
const payload = JSON.parse(lookup.replace("pronounceit:menu:", ""));
if (
  payload.text !== "bundle" ||
  payload.contextText !== parent.textContent ||
  payload.contextText.slice(payload.contextOffsetStart, payload.contextOffsetEnd) !== "bundle"
) {
  throw new Error(`bad parent context payload: ${JSON.stringify(payload)}`);
}
"""
        subprocess.run(
            ["node", "-e", script, str(ROOT / "web" / "pronounceit.js")],
            check=True,
            text=True,
            capture_output=True,
        )

    def test_plain_right_click_does_not_trigger_pronounceit(self) -> None:
        if not shutil.which("node"):
            self.skipTest("node is not available")

        script = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[1], "utf8");
const listeners = {};
const messages = [];
const source = "ECG shows right bundle branch block today.";
const textNode = { nodeType: 3, textContent: source };
const sandbox = {
  pycmd(message) { messages.push(message); },
  Node: { TEXT_NODE: 3 },
  NodeFilter: { SHOW_TEXT: 4 },
  window: {
    PronounceItConfig: {
      enabled: true,
      allowOnQuestionSide: true,
      popupClickModifier: "alt",
    },
    addEventListener() {},
    getSelection() { return null; },
  },
  document: {
    body: {},
    addEventListener(type, callback) {
      listeners[type] = listeners[type] || [];
      listeners[type].push(callback);
    },
    caretRangeFromPoint() {
      return {
        startContainer: textNode,
        startOffset: source.indexOf("bundle") + 2,
        getBoundingClientRect() {
          return { left: 12, top: 14, right: 20, bottom: 24, width: 8, height: 10 };
        },
      };
    },
    caretPositionFromPoint: null,
    createRange() { return { setStart() {}, collapse() {} }; },
    createTreeWalker() { return { nextNode() { return null; } }; },
  },
};
vm.createContext(sandbox);
vm.runInContext(code, sandbox, { filename: "pronounceit.js" });
messages.length = 0;
for (const callback of listeners.contextmenu || []) {
  callback({
    altKey: false,
    ctrlKey: false,
    clientX: 18,
    clientY: 19,
    target: sandbox.document.body,
    preventDefault() { throw new Error("plain right-click should not be prevented"); },
    stopPropagation() { throw new Error("plain right-click should not stop propagation"); },
  });
}
if (messages.some((message) => message.startsWith("pronounceit:lookup:") || message.startsWith("pronounceit:menu:"))) {
  throw new Error(`plain right-click sent PronounceIt message: ${JSON.stringify(messages)}`);
}
"""
        subprocess.run(
            ["node", "-e", script, str(ROOT / "web" / "pronounceit.js")],
            check=True,
            text=True,
            capture_output=True,
        )

    def test_custom_shift_modifiers_for_left_and_right_click(self) -> None:
        if not shutil.which("node"):
            self.skipTest("node is not available")

        script = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[1], "utf8");
const listeners = {};
const messages = [];
const source = "ECG shows right bundle branch block today.";
const start = source.indexOf("bundle");
const textNode = { nodeType: 3, textContent: source };
const sandbox = {
  pycmd(message) { messages.push(message); },
  Node: { TEXT_NODE: 3 },
  NodeFilter: { SHOW_TEXT: 4 },
  window: {
    PronounceItConfig: {
      enabled: true,
      allowOnQuestionSide: true,
      directClickModifier: "shift",
      popupClickModifier: "shift",
    },
    addEventListener() {},
    getSelection() { return null; },
  },
  document: {
    body: {},
    addEventListener(type, callback) {
      listeners[type] = listeners[type] || [];
      listeners[type].push(callback);
    },
    caretRangeFromPoint() {
      return {
        startContainer: textNode,
        startOffset: start + 2,
        getBoundingClientRect() {
          return { left: 12, top: 14, right: 20, bottom: 24, width: 8, height: 10 };
        },
      };
    },
    caretPositionFromPoint: null,
    createRange() { return { setStart() {}, collapse() {} }; },
    createTreeWalker() { return { nextNode() { return null; } }; },
  },
};
vm.createContext(sandbox);
vm.runInContext(code, sandbox, { filename: "pronounceit.js" });
messages.length = 0;
for (const callback of listeners.mouseup || []) {
  callback({
    shiftKey: true,
    button: 0,
    clientX: 18,
    clientY: 19,
    target: sandbox.document.body,
    preventDefault() {},
  });
}
for (const callback of listeners.contextmenu || []) {
  callback({
    shiftKey: true,
    clientX: 18,
    clientY: 19,
    target: sandbox.document.body,
    preventDefault() {},
    stopPropagation() {},
  });
}
const audio = messages.find((message) => message.startsWith("pronounceit:audioLookup:"));
const popup = messages.find((message) => message.startsWith("pronounceit:menu:"));
if (!audio || !popup) {
  throw new Error(`missing shift modifier messages: ${JSON.stringify(messages)}`);
}
const popupPayload = JSON.parse(popup.replace("pronounceit:menu:", ""));
if (popupPayload.text !== "bundle") {
  throw new Error(`bad popup payload: ${JSON.stringify(popupPayload)}`);
}
"""
        subprocess.run(
            ["node", "-e", script, str(ROOT / "web" / "pronounceit.js")],
            check=True,
            text=True,
            capture_output=True,
        )

    def test_option_click_without_selection_pronounces_pointer_word(self) -> None:
        if not shutil.which("node"):
            self.skipTest("node is not available")

        script = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[1], "utf8");
const listeners = {};
const messages = [];
const source = "ECG shows right bundle branch block today.";
const start = source.indexOf("bundle");
const textNode = { nodeType: 3, textContent: source };
const sandbox = {
  pycmd(message) { messages.push(message); },
  Node: { TEXT_NODE: 3 },
  NodeFilter: { SHOW_TEXT: 4 },
  window: {
    PronounceItConfig: {
      enabled: true,
      allowOnQuestionSide: true,
      directClickModifier: "alt",
    },
    addEventListener() {},
    getSelection() { return null; },
  },
  document: {
    body: {},
    addEventListener(type, callback) {
      listeners[type] = listeners[type] || [];
      listeners[type].push(callback);
    },
    caretRangeFromPoint() {
      return {
        startContainer: textNode,
        startOffset: start + 2,
        getBoundingClientRect() {
          return { left: 12, top: 14, right: 20, bottom: 24, width: 8, height: 10 };
        },
      };
    },
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
messages.length = 0;
for (const callback of listeners.mouseup || []) {
  callback({
    altKey: true,
    clientX: 18,
    clientY: 19,
    target: sandbox.document.body,
    preventDefault() {},
  });
}
const lookup = messages.find((message) => message.startsWith("pronounceit:audioLookup:"));
if (!lookup) {
  throw new Error(`missing audio lookup message: ${JSON.stringify(messages)}`);
}
const payload = JSON.parse(lookup.replace("pronounceit:audioLookup:", ""));
if (
  payload.text !== "bundle" ||
  payload.autoPlay ||
  payload.contextText !== source ||
  payload.contextOffsetStart !== start ||
  payload.contextOffsetEnd !== start + "bundle".length
) {
  throw new Error(`bad option-click payload: ${JSON.stringify(payload)}`);
}
"""
        subprocess.run(
            ["node", "-e", script, str(ROOT / "web" / "pronounceit.js")],
            check=True,
            text=True,
            capture_output=True,
        )

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
const cloze = {
  textContent: "{{c1::clozapine::antipsychotic}}",
  parentElement: body,
  getBoundingClientRect() { return rect; },
};
const clozeRequest = termFromElement(cloze);
if (!clozeRequest || clozeRequest.text !== "clozapine") {
  throw new Error(`bad cloze request: ${JSON.stringify(clozeRequest)}`);
}
"""
        subprocess.run(
            ["node", "-e", script, str(ROOT / "web" / "pronounceit.js")],
            check=True,
            text=True,
            capture_output=True,
        )

    def test_popup_play_status_updates_from_spoken_callback(self) -> None:
        if not shutil.which("node"):
            self.skipTest("node is not available")

        script = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[1], "utf8");
const messages = [];
const elements = [];
function makeElement(tag) {
  const element = {
    tag,
    type: "",
    className: "",
    textContent: "",
    title: "",
    style: {},
    children: [],
    listeners: {},
    parent: null,
    setAttribute(name, value) { this[name] = value; },
    appendChild(child) { child.parent = this; this.children.push(child); },
    remove() {
      if (this.parent) {
        this.parent.children = this.parent.children.filter((child) => child !== this);
      }
    },
    contains(target) { return target === this || this.children.some((child) => child.contains && child.contains(target)); },
    addEventListener(type, callback) { this.listeners[type] = callback; },
    getBoundingClientRect() { return { left: 0, top: 0, right: 100, bottom: 80, width: 100, height: 80 }; },
    querySelector(selector) {
      const className = selector.startsWith(".") ? selector.slice(1) : selector;
      const stack = [...this.children];
      while (stack.length) {
        const current = stack.shift();
        if ((current.className || "").split(/\s+/).includes(className)) {
          return current;
        }
        stack.push(...(current.children || []));
      }
      return null;
    },
  };
  elements.push(element);
  return element;
}
const body = makeElement("body");
const sandbox = {
  pycmd(message) { messages.push(message); },
  Node: { TEXT_NODE: 3 },
  NodeFilter: { SHOW_TEXT: 4 },
  window: {
    innerWidth: 800,
    innerHeight: 600,
    PronounceItConfig: {},
    addEventListener() {},
    getSelection() { return null; },
  },
  document: {
    body,
    addEventListener() {},
    createElement: makeElement,
    caretRangeFromPoint: null,
    caretPositionFromPoint: null,
    createRange() { return { setStart() {}, collapse() {} }; },
    createTreeWalker() { return { nextNode() { return null; } }; },
  },
};
body.appendChild = function(child) { child.parent = body; this.children.push(child); };
vm.createContext(sandbox);
vm.runInContext(code, sandbox, { filename: "pronounceit.js" });
messages.length = 0;
sandbox.window.PronounceIt.show({
  term: "clozapine",
  speechText: "kloh zuh peen",
  audioFile: "audio/clozapine.aiff",
  found: true,
  rect: { left: 12, bottom: 24 },
  autoPlay: true,
});
const source = body.querySelector(".pronounceit-source");
if (!source || source.textContent !== "Curated") {
  throw new Error(`expected curated source label, got ${source && source.textContent}`);
}
const status = body.querySelector(".pronounceit-status");
if (!status || status.textContent !== "Playing...") {
  throw new Error(`expected playing status, got ${status && status.textContent}`);
}
if (body.querySelector(".pronounceit-save")) {
  throw new Error("popup should not contain a save button");
}
const speak = messages.find((message) => message.startsWith("pronounceit:speak:"));
if (!speak) {
  throw new Error(`missing speak message: ${JSON.stringify(messages)}`);
}
const payload = JSON.parse(speak.replace("pronounceit:speak:", ""));
if (payload.text !== "kloh zuh peen" || payload.audioFile !== "audio/clozapine.aiff") {
  throw new Error(`bad speak payload: ${JSON.stringify(payload)}`);
}
sandbox.window.PronounceIt.spoken({ ok: false, reason: "local audio unavailable" });
if (status.textContent !== "Could not play audio.") {
  throw new Error(`expected failure status, got ${status.textContent}`);
}
sandbox.window.PronounceIt.spoken({ ok: true });
if (status.textContent !== "") {
  throw new Error(`expected cleared status, got ${status.textContent}`);
}
sandbox.window.PronounceIt.show({
  term: "notarealmedicalword",
  audioKind: "generated",
  found: false,
  rect: { left: 12, bottom: 24 },
});
const generatedSource = body.querySelector(".pronounceit-source");
if (!generatedSource || generatedSource.textContent !== "Generated") {
  throw new Error(`expected generated source label, got ${generatedSource && generatedSource.textContent}`);
}
"""
        subprocess.run(
            ["node", "-e", script, str(ROOT / "web" / "pronounceit.js")],
            check=True,
            text=True,
            capture_output=True,
        )

    def test_quick_menu_keyboard_shortcuts_use_selected_term(self) -> None:
        if not shutil.which("node"):
            self.skipTest("node is not available")

        script = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[1], "utf8");
const listeners = {};
const messages = [];
const elements = [];
function makeElement(tag) {
  const element = {
    tag,
    type: "",
    className: "",
    textContent: "",
    title: "",
    style: {},
    children: [],
    listeners: {},
    parent: null,
    setAttribute(name, value) { this[name] = value; },
    appendChild(child) { child.parent = this; this.children.push(child); },
    remove() {
      if (this.parent) {
        this.parent.children = this.parent.children.filter((child) => child !== this);
      }
    },
    contains(target) { return target === this || this.children.some((child) => child.contains && child.contains(target)); },
    addEventListener(type, callback) { this.listeners[type] = callback; },
    getBoundingClientRect() { return { left: 0, top: 0, right: 220, bottom: 120, width: 220, height: 120 }; },
    querySelector(selector) {
      const className = selector.startsWith(".") ? selector.slice(1) : selector;
      const stack = [...this.children];
      while (stack.length) {
        const current = stack.shift();
        if ((current.className || "").split(/\s+/).includes(className)) {
          return current;
        }
        stack.push(...(current.children || []));
      }
      return null;
    },
  };
  elements.push(element);
  return element;
}
const body = makeElement("body");
const sandbox = {
  pycmd(message) { messages.push(message); },
  Node: { TEXT_NODE: 3 },
  NodeFilter: { SHOW_TEXT: 4 },
  window: {
    innerWidth: 800,
    innerHeight: 600,
    PronounceItConfig: {},
    addEventListener() {},
    getSelection() { return null; },
  },
  document: {
    body,
    addEventListener(type, callback) { listeners[type] = callback; },
    createElement: makeElement,
    caretRangeFromPoint: null,
    caretPositionFromPoint: null,
    createRange() { return { setStart() {}, collapse() {} }; },
    createTreeWalker() { return { nextNode() { return null; } }; },
  },
};
body.appendChild = function(child) { child.parent = body; this.children.push(child); };
vm.createContext(sandbox);
vm.runInContext(code, sandbox, { filename: "pronounceit.js" });
messages.length = 0;
sandbox.window.PronounceIt.showMenu({
  term: "clozapine",
  speechText: "kloh zuh peen",
  audioFile: "audio/clozapine.aiff",
  found: true,
  menuX: 12,
  menuY: 24,
});
const menuTerm = body.querySelector(".pronounceit-menu-term");
if (!menuTerm || menuTerm.textContent !== "clozapine") {
  throw new Error(`expected menu term, got ${menuTerm && menuTerm.textContent}`);
}
if (!elements.some((element) => element.textContent === "Save pronunciation")) {
  throw new Error("missing Save pronunciation action");
}
listeners.keydown({ key: "Enter", preventDefault() {} });
const speak = messages.find((message) => message.startsWith("pronounceit:speak:"));
if (!speak) {
  throw new Error(`missing speak message after Enter: ${JSON.stringify(messages)}`);
}
messages.length = 0;
sandbox.window.PronounceIt.showMenu({
  term: "clozapine",
  speechText: "kloh zuh peen",
  audioFile: "audio/clozapine.aiff",
  found: true,
  menuX: 12,
  menuY: 24,
});
listeners.keydown({ key: "s", preventDefault() {} });
const save = messages.find((message) => message.startsWith("pronounceit:save:"));
if (!save) {
  throw new Error(`missing save message after S: ${JSON.stringify(messages)}`);
}
sandbox.window.PronounceIt.saved({ saved: true, duplicate: false, alreadySaved: true });
const saveButton = body.querySelector(".pronounceit-menu-save");
if (!saveButton || saveButton.textContent !== "Saved" || !saveButton.disabled) {
  throw new Error(`expected saved menu feedback, got ${saveButton && saveButton.textContent}`);
}
messages.length = 0;
sandbox.window.PronounceIt.showMenu({
  term: "clozapine",
  speechText: "kloh zuh peen",
  audioFile: "audio/clozapine.aiff",
  found: true,
  menuX: 12,
  menuY: 24,
});
listeners.keydown({ key: "Escape", preventDefault() {} });
if (body.querySelector(".pronounceit-menu")) {
  throw new Error("menu should close on Escape");
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
