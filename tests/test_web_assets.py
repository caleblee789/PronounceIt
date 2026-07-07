from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


NODE_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[1], "utf8");
const listeners = {};
const messages = [];
let timers = [];
let source = "ECG shows right bundle branch block today.";
let pointOffset = source.indexOf("bundle") + 2;
let pointEnabled = true;
let selectionText = "";
let selectionStart = 0;
let selectionEnd = 0;
let selectionRect = { left: 2, top: 2, right: 12, bottom: 12, width: 10, height: 10 };

class Element {
  constructor(tag) {
    this.tagName = tag;
    this.nodeType = 1;
    this.children = [];
    this.childNodes = this.children;
    this.listeners = {};
    this.attributes = {};
    this.style = {};
    this.className = "";
    this.textContent = "";
    this.parentElement = null;
    this.disabled = false;
  }
  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }
  remove() {
    if (!this.parentElement) return;
    this.parentElement.children = this.parentElement.children.filter((item) => item !== this);
    this.parentElement.childNodes = this.parentElement.children;
    this.parentElement = null;
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name]; }
  addEventListener(type, callback) { this.listeners[type] = callback; }
  contains(target) {
    if (target === this) return true;
    return this.children.some((child) => child.contains && child.contains(target));
  }
  querySelector(selector) {
    const wanted = selector.startsWith(".") ? selector.slice(1) : selector;
    for (const child of this.children) {
      if (String(child.className || "").split(/\s+/).includes(wanted)) return child;
      const nested = child.querySelector && child.querySelector(selector);
      if (nested) return nested;
    }
    return null;
  }
  getBoundingClientRect() {
    return { left: 10, top: 10, right: 190, bottom: 50, width: 180, height: 40 };
  }
  focus() {}
}

const body = new Element("body");
const wrapper = new Element("div");
body.appendChild(wrapper);
const textNode = { nodeType: 3, textContent: source, parentElement: wrapper };
wrapper.textContent = source;
wrapper.childNodes = [textNode];

function selectionRange() {
  return {
    startContainer: textNode,
    endContainer: textNode,
    startOffset: selectionStart,
    endOffset: selectionEnd,
    getBoundingClientRect() { return selectionRect; },
    getClientRects() { return [selectionRect]; },
  };
}

const sandbox = {
  pycmd(message) { messages.push(message); },
  Node: { TEXT_NODE: 3 },
  NodeFilter: { SHOW_TEXT: 4 },
  window: {
    PointerEvent: function PointerEvent() {},
    PronounceItConfig: {
      enabled: true,
      answerVisible: true,
      directClickModifier: "alt",
      platformModifier: "meta",
      showSaveButton: true,
    },
    PronounceItTestHooks: {},
    innerWidth: 900,
    innerHeight: 700,
    addEventListener(type, callback) { listeners["window:" + type] = callback; },
    clearTimeout(id) { timers = timers.filter((timer) => timer.id !== id); },
    setTimeout(callback) {
      const id = timers.length + 1;
      timers.push({ id, callback });
      return id;
    },
    matchMedia() { return { matches: false }; },
    getSelection() {
      if (!selectionText && selectionStart === selectionEnd) {
        return { rangeCount: 0, toString() { return ""; } };
      }
      return {
        rangeCount: 1,
        toString() { return selectionText; },
        getRangeAt() { return selectionRange(); },
      };
    },
  },
  document: {
    body,
    createElement(tag) { return new Element(tag); },
    addEventListener(type, callback) {
      listeners[type] = listeners[type] || [];
      listeners[type].push(callback);
    },
    caretRangeFromPoint() {
      if (!pointEnabled) return null;
      textNode.textContent = source;
      wrapper.textContent = source;
      return {
        startContainer: textNode,
        startOffset: pointOffset,
        getBoundingClientRect() {
          return { left: 30, top: 8, right: 42, bottom: 20, width: 12, height: 12 };
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

function emit(type, overrides) {
  const event = Object.assign({
    altKey: false,
    ctrlKey: false,
    metaKey: false,
    shiftKey: false,
    key: "",
    repeat: false,
    button: 0,
    pointerId: 1,
    clientX: 34,
    clientY: 14,
    target: wrapper,
    preventDefault() { this.defaultPrevented = true; },
    stopPropagation() { this.propagationStopped = true; },
  }, overrides || {});
  for (const callback of listeners[type] || []) callback(event);
  return event;
}

function flushTimers() {
  const pending = timers;
  timers = [];
  for (const timer of pending) timer.callback();
}

function payload(prefix, index = 0) {
  const matches = messages.filter((message) => message.startsWith(prefix));
  if (!matches[index]) throw new Error(`Missing ${prefix}: ${JSON.stringify(messages)}`);
  return JSON.parse(matches[index].slice(prefix.length));
}
"""


class WebAssetTests(unittest.TestCase):
    def run_node(self, assertions: str) -> None:
        if not shutil.which("node"):
            self.skipTest("node is not available")
        completed = subprocess.run(
            ["node", "-e", NODE_HARNESS + "\n" + assertions, str(ROOT / "web" / "pronounceit.js")],
            check=False,
            text=True,
            capture_output=True,
        )
        if completed.returncode:
            self.fail(completed.stderr or completed.stdout)

    def test_javascript_uses_native_context_bridge_and_no_custom_menu_or_hotkey_parser(self) -> None:
        js = (ROOT / "web" / "pronounceit.js").read_text(encoding="utf-8")

        self.assertIn("playContextTarget", js)
        self.assertIn("showContextDetails", js)
        self.assertIn("saveContextTarget", js)
        self.assertIn('send("saveLookup", request)', js)
        self.assertNotIn("function showMenu", js)
        self.assertNotIn("function hotkeyMatches", js)
        self.assertNotIn('send("menu"', js)

    def test_modifier_click_sends_one_request_and_allows_immediate_replay(self) -> None:
        self.run_node(
            r"""
for (let attempt = 0; attempt < 2; attempt += 1) {
  emit("pointerdown", { altKey: true });
  emit("pointerup", { altKey: true });
  emit("click", { altKey: true });
}
const lookups = messages.filter((message) => message.startsWith("pronounceit:audioLookup:"));
if (lookups.length !== 2) throw new Error(`Expected two deliberate plays: ${JSON.stringify(messages)}`);
const request = JSON.parse(lookups[0].replace("pronounceit:audioLookup:", ""));
if (request.text !== "bundle" || request.contextText.slice(request.contextOffsetStart, request.contextOffsetEnd) !== "bundle") {
  throw new Error(`Bad pointer request: ${JSON.stringify(request)}`);
}
"""
        )

    def test_modifier_drag_waits_for_fresh_selection_and_plays_once(self) -> None:
        self.run_node(
            r"""
emit("pointerdown", { altKey: true, clientX: 10, clientY: 10 });
emit("pointermove", { altKey: true, clientX: 30, clientY: 30 });
selectionText = "ight bun";
selectionStart = source.indexOf("right") + 1;
selectionEnd = source.indexOf("bundle") + 3;
selectionRect = { left: 8, top: 1, right: 80, bottom: 40, width: 72, height: 39 };
emit("pointerup", { altKey: true, clientX: 30, clientY: 30 });
if (messages.some((message) => message.startsWith("pronounceit:audioLookup:"))) {
  throw new Error(`Drag played before selection settled: ${JSON.stringify(messages)}`);
}
flushTimers();
const lookups = messages.filter((message) => message.startsWith("pronounceit:audioLookup:"));
if (lookups.length !== 1) throw new Error(`Expected one deferred play: ${JSON.stringify(messages)}`);
const request = payload("pronounceit:audioLookup:");
if (request.text !== "right bundle" || request.selectedText !== "ight bun") {
  throw new Error(`Partial selection did not expand to word bounds: ${JSON.stringify(request)}`);
}
"""
        )

    def test_extra_modifier_cancels_activation(self) -> None:
        self.run_node(
            r"""
emit("pointerdown", { altKey: true, shiftKey: true });
emit("pointerup", { altKey: true, shiftKey: true });
if (messages.some((message) => message.startsWith("pronounceit:audioLookup:"))) {
  throw new Error(`Extra modifier played audio: ${JSON.stringify(messages)}`);
}
"""
        )

    def test_modifier_tap_plays_selection_and_gesture_keyup_does_not_duplicate(self) -> None:
        self.run_node(
            r"""
selectionText = "bundle";
selectionStart = source.indexOf("bundle");
selectionEnd = selectionStart + selectionText.length;
selectionRect = { left: 20, top: 1, right: 80, bottom: 24, width: 60, height: 23 };
emit("keydown", { key: "Alt", altKey: true });
emit("keyup", { key: "Alt" });
if (messages.filter((message) => message.startsWith("pronounceit:audioLookup:")).length !== 1) {
  throw new Error(`Modifier tap did not play once: ${JSON.stringify(messages)}`);
}
messages.length = 0;
emit("keydown", { key: "Alt", altKey: true });
emit("pointerdown", { altKey: true });
emit("pointerup", { altKey: true });
emit("keyup", { key: "Alt" });
if (messages.filter((message) => message.startsWith("pronounceit:audioLookup:")).length !== 1) {
  throw new Error(`Gesture keyup duplicated playback: ${JSON.stringify(messages)}`);
}
"""
        )

    def test_modifier_tap_requires_selection_and_is_cancelled_by_another_key(self) -> None:
        self.run_node(
            r"""
emit("keydown", { key: "Alt", altKey: true });
emit("keyup", { key: "Alt" });
if (messages.length) throw new Error(`Empty modifier tap was not silent: ${JSON.stringify(messages)}`);
selectionText = "bundle";
selectionStart = source.indexOf("bundle");
selectionEnd = selectionStart + selectionText.length;
emit("keydown", { key: "Alt", altKey: true });
emit("keydown", { key: "x", altKey: true });
emit("keyup", { key: "Alt" });
if (messages.length) throw new Error(`Cancelled modifier tap played: ${JSON.stringify(messages)}`);
"""
        )

    def test_platform_modifier_is_exact(self) -> None:
        self.run_node(
            r"""
sandbox.window.PronounceIt.configure({ directClickModifier: "mod", platformModifier: "meta" });
emit("pointerdown", { ctrlKey: true });
emit("pointerup", { ctrlKey: true });
emit("pointerdown", { metaKey: true });
emit("pointerup", { metaKey: true });
const lookups = messages.filter((message) => message.startsWith("pronounceit:audioLookup:"));
if (lookups.length !== 1) throw new Error(`Platform modifier mismatch: ${JSON.stringify(messages)}`);
"""
        )

    def test_pointer_wins_over_stale_selection_outside_click(self) -> None:
        self.run_node(
            r"""
selectionText = "right";
selectionStart = source.indexOf("right");
selectionEnd = selectionStart + selectionText.length;
selectionRect = { left: 1, top: 1, right: 12, bottom: 12, width: 11, height: 11 };
emit("pointerdown", { altKey: true, clientX: 34, clientY: 14 });
emit("pointerup", { altKey: true, clientX: 34, clientY: 14 });
const request = payload("pronounceit:audioLookup:");
if (request.text !== "bundle" || request.selectedText !== "bundle") {
  throw new Error(`Stale selection won: ${JSON.stringify(request)}`);
}
"""
        )

    def test_selection_under_click_is_preserved_with_context(self) -> None:
        self.run_node(
            r"""
selectionText = "right bundle";
selectionStart = source.indexOf("right");
selectionEnd = selectionStart + selectionText.length;
selectionRect = { left: 20, top: 1, right: 80, bottom: 24, width: 60, height: 23 };
emit("pointerdown", { altKey: true, clientX: 34, clientY: 14 });
emit("pointerup", { altKey: true, clientX: 34, clientY: 14 });
const request = payload("pronounceit:audioLookup:");
if (request.text !== "right bundle" || request.contextText.slice(request.contextOffsetStart, request.contextOffsetEnd) !== "right bundle") {
  throw new Error(`Selection context was lost: ${JSON.stringify(request)}`);
}
"""
        )

    def test_plain_right_click_autoplays_details_and_shift_preserves_native_menu(self) -> None:
        self.run_node(
            r"""
const event = emit("contextmenu");
if (!event.defaultPrevented || !event.propagationStopped) throw new Error("Plain right-click was not captured");
const automatic = payload("pronounceit:lookup:");
if (!automatic.autoPlay || automatic.text !== "bundle") {
  throw new Error(`Right-click did not autoplay pointed term: ${JSON.stringify(automatic)}`);
}
const shiftEvent = emit("contextmenu", { shiftKey: true });
if (shiftEvent.defaultPrevented || shiftEvent.propagationStopped) throw new Error("Shift-right-click was suppressed");
if (messages.filter((message) => message.startsWith("pronounceit:lookup:")).length !== 1) {
  throw new Error(`Shift-right-click triggered lookup: ${JSON.stringify(messages)}`);
}
sandbox.window.PronounceIt.playContextTarget();
sandbox.window.PronounceIt.showContextDetails();
sandbox.window.PronounceIt.saveContextTarget();
const play = payload("pronounceit:audioLookup:");
const details = payload("pronounceit:lookup:", 1);
const save = payload("pronounceit:saveLookup:");
for (const request of [play, details, save]) {
  if (request.text !== "bundle" || !request.contextText.includes("right bundle branch block")) {
    throw new Error(`Context bridge drifted: ${JSON.stringify(request)}`);
  }
}
if (details.autoPlay !== false) throw new Error(`Details must not autoplay: ${JSON.stringify(details)}`);
"""
        )

    def test_right_click_without_text_keeps_native_menu(self) -> None:
        self.run_node(
            r"""
pointEnabled = false;
source = "";
wrapper.textContent = "";
textNode.textContent = "";
const event = emit("contextmenu");
if (event.defaultPrevented || event.propagationStopped) throw new Error("Empty target suppressed native menu");
if (messages.length) throw new Error(`Empty target sent bridge message: ${JSON.stringify(messages)}`);
"""
        )

    def test_details_popup_save_uses_preserved_request_and_disables_after_save(self) -> None:
        self.run_node(
            r"""
const request = {
  text: "bundle",
  selectedText: "bun",
  contextText: source,
  contextOffsetStart: source.indexOf("bundle"),
  contextOffsetEnd: source.indexOf("bundle") + 3,
  rect: { left: 20, top: 1, right: 80, bottom: 24, width: 60, height: 23 },
};
sandbox.window.PronounceIt.show({
  term: "right bundle branch block",
  pronunciation: "RYT BUN-dul branch block",
  found: true,
  audioAvailable: true,
  alreadySaved: false,
  request,
  rect: request.rect,
});
const popup = body.querySelector(".pronounceit-popup");
const save = popup && popup.querySelector(".pronounceit-save-button");
if (!save || save.disabled || save.textContent !== "Save pronunciation") {
  throw new Error("Save action missing from details popup");
}
save.listeners.click();
const savedRequest = payload("pronounceit:saveLookup:");
if (savedRequest.contextText !== source || savedRequest.contextOffsetStart !== request.contextOffsetStart) {
  throw new Error(`Save lost context: ${JSON.stringify(savedRequest)}`);
}
sandbox.window.PronounceIt.saved({ alreadySaved: true, duplicate: false });
if (!save.disabled || save.textContent !== "Saved") throw new Error("Save action did not update");
"""
        )

    def test_details_popup_respects_disabled_save_setting(self) -> None:
        self.run_node(
            r"""
sandbox.window.PronounceIt.configure({ showSaveButton: false });
sandbox.window.PronounceIt.show({
  term: "bundle",
  pronunciation: "BUN-dul",
  found: true,
  audioAvailable: true,
  request: { text: "bundle", selectedText: "bundle", rect: {} },
  rect: {},
});
const popup = body.querySelector(".pronounceit-popup");
if (popup.querySelector(".pronounceit-save-button")) throw new Error("Disabled Save action was shown");
"""
        )

    def test_shortcut_bridge_prefers_selection_then_pointer(self) -> None:
        self.run_node(
            r"""
selectionText = "bundle";
selectionStart = source.indexOf("bundle");
selectionEnd = selectionStart + selectionText.length;
sandbox.window.PronounceIt.pronounceCurrent();
if (payload("pronounceit:audioLookup:").text !== "bundle") throw new Error("Selection was not used");
messages.length = 0;
selectionText = "";
selectionStart = 0;
selectionEnd = 0;
emit("pointermove");
sandbox.window.PronounceIt.pronounceCurrent();
if (payload("pronounceit:audioLookup:").text !== "bundle") throw new Error("Pointer fallback was not used");
"""
        )

    def test_no_target_attempt_shows_actionable_status(self) -> None:
        self.run_node(
            r"""
pointEnabled = false;
source = "";
wrapper.textContent = "";
textNode.textContent = "";
sandbox.window.PronounceIt.pronounceCurrent();
const notice = body.querySelector(".pronounceit-notice");
if (!notice || notice.textContent !== "Point to or select a word first." || notice.getAttribute("data-state") !== "error") {
  throw new Error(`Missing no-target status: ${notice && notice.textContent}`);
}
"""
        )

    def test_status_reports_loading_success_and_failure_accessibly(self) -> None:
        self.run_node(
            r"""
emit("pointerdown", { altKey: true });
emit("pointerup", { altKey: true });
let notice = body.querySelector(".pronounceit-notice");
if (!notice || notice.textContent !== "Playing…" || notice.getAttribute("aria-live") !== "polite") {
  throw new Error("Missing loading status");
}
sandbox.window.PronounceIt.spoken({ ok: true, term: "right bundle branch block" });
notice = body.querySelector(".pronounceit-notice");
if (!notice || notice.textContent !== "Played right bundle branch block" || notice.getAttribute("data-state") !== "success") {
  throw new Error(`Missing success status: ${notice && notice.textContent}`);
}
emit("pointerdown", { altKey: true });
emit("pointerup", { altKey: true });
sandbox.window.PronounceIt.spoken({ ok: false, reason: "Reveal the answer before using PronounceIt." });
notice = body.querySelector(".pronounceit-notice");
if (!notice || !notice.textContent.includes("Reveal the answer") || notice.getAttribute("data-state") !== "error") {
  throw new Error(`Missing failure status: ${notice && notice.textContent}`);
}
"""
        )

    def test_word_extraction_and_context_offsets_cover_medical_terms(self) -> None:
        self.run_node(
            r"""
const hooks = sandbox.window.PronounceItTestHooks;
if (hooks.extractTermAtOffset("beta-blocker", 6) !== "beta-blocker") throw new Error("hyphenated term failed");
if (hooks.extractTermAtOffset("Crohn’s", 3) !== "Crohn") throw new Error("apostrophe boundary failed");
const context = hooks.contextFromText("Treat acute interstitial nephritis today", 12, 24);
if (context.contextText.slice(context.contextOffsetStart, context.contextOffsetEnd) !== "interstitial") {
  throw new Error(`Context offsets failed: ${JSON.stringify(context)}`);
}
"""
        )

    def test_css_contains_popup_and_stateful_notice_without_custom_menu(self) -> None:
        css = (ROOT / "web" / "pronounceit.css").read_text(encoding="utf-8")

        self.assertIn(".pronounceit-popup", css)
        self.assertIn(".pronounceit-notice", css)
        self.assertIn('[data-state="loading"]', css)
        self.assertIn('[data-state="success"]', css)
        self.assertIn('[data-state="error"]', css)
        self.assertNotIn(".pronounceit-menu", css)


if __name__ == "__main__":
    unittest.main()
