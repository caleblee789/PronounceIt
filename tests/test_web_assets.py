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
let selectionRangeOverride = null;

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
  replaceChildren(...children) {
    for (const child of this.children) child.parentElement = null;
    this.children = [];
    this.childNodes = this.children;
    for (const child of children) this.appendChild(child);
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
        getRangeAt() { return selectionRangeOverride || selectionRange(); },
      };
    },
  },
  document: {
    body,
    createElement(tag) { return new Element(tag); },
    addEventListener(type, callback, options) {
      listeners[type] = listeners[type] || [];
      listeners[type].push({
        callback,
        capture: options === true || Boolean(options && options.capture),
      });
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
  const registered = listeners[type] || [];
  for (const listener of registered.filter((item) => item.capture)) listener.callback(event);
  if (!event.stopBeforeBubble) {
    for (const listener of registered.filter((item) => !item.capture)) listener.callback(event);
  }
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

    def test_delayed_quick_card_responses_are_discarded_after_close_or_replacement(self) -> None:
        self.run_node(r"""
function answer(request) {
  sandbox.window.PronounceIt.show({
    term: request.text, pronunciation: "guide", audioAvailable: true,
    autoPlay: true, requestId: request.requestId, request,
  });
}
emit("contextmenu", { ctrlKey: true });
const first = payload("pronounceit:lookup:");
emit("keydown", { key: "Escape" });
messages.length = 0;
answer(first);
if (body.querySelector(".pronounceit-popup") || messages.length) {
  throw new Error("Dismissed lookup reopened or played");
}
emit("contextmenu", { ctrlKey: true });
const second = payload("pronounceit:lookup:");
messages.length = 0;
emit("contextmenu", { ctrlKey: true });
const third = payload("pronounceit:lookup:");
messages.length = 0;
answer(second);
if (messages.length || body.querySelector(".pronounceit-popup").getAttribute("data-loading") !== "true") {
  throw new Error("Old lookup replaced the current loading card");
}
answer(third);
answer(third);
if (messages.filter(m => m.startsWith("pronounceit:audioLookup:")).length !== 1) {
  throw new Error("Current lookup must autoplay exactly once");
}
""")

    def test_disabling_addon_releases_keys_and_dismisses_pending_card(self) -> None:
        self.run_node(r"""
selectionText = "bundle";
selectionStart = source.indexOf("bundle");
selectionEnd = selectionStart + selectionText.length;
emit("contextmenu", { ctrlKey: true });
const request = payload("pronounceit:lookup:");
sandbox.window.PronounceIt.configure({ enabled: false });
messages.length = 0;
for (const key of ["Alt", "Control"]) {
  for (const type of ["keydown", "keyup"]) {
    const event = emit(type, { key });
    if (event.defaultPrevented || event.propagationStopped) throw new Error("Disabled add-on intercepted a key");
  }
}
sandbox.window.PronounceIt.show({ term: "bundle", audioAvailable: true, autoPlay: true,
  requestId: request.requestId, request });
if (messages.length || body.querySelector(".pronounceit-popup")) throw new Error("Disabled add-on left a card or played");
sandbox.window.PronounceIt.configure({ enabled: true });
emit("keydown", { key: "Alt" });
emit("keyup", { key: "Alt" });
if (messages.filter(m => m.startsWith("pronounceit:audioLookup:")).length !== 1) throw new Error("Re-enabling failed");
""")

    def test_audio_shortcut_works_with_matching_disabled_quick_card_key(self) -> None:
        self.run_node(r"""
sandbox.window.PronounceIt.configure({ directClickModifier: "alt", contextMenuModifier: "alt", showNativeContextMenu: false });
emit("pointerdown", { altKey: true });
emit("pointerup", { altKey: true });
emit("click", { altKey: true });
selectionText = "bundle";
selectionStart = source.indexOf("bundle");
selectionEnd = selectionStart + selectionText.length;
emit("keydown", { key: "Alt" });
emit("keyup", { key: "Alt" });
if (messages.filter(m => m.startsWith("pronounceit:audioLookup:")).length !== 2) throw new Error("Inactive quick-card shortcut blocked audio");
""")

    def test_javascript_uses_immediate_quick_card_and_no_legacy_hotkey_parser(self) -> None:
        js = (ROOT / "web" / "pronounceit.js").read_text(encoding="utf-8")

        self.assertIn("openQuickCard", js)
        self.assertIn("audioSourceLabel", js)
        self.assertIn("contextMenuModifier", js)
        self.assertIn('send("saveLookup", request)', js)
        self.assertNotIn("showContextMenu", js)
        self.assertNotIn("pronounceit-menu", js)
        self.assertNotIn("event.shiftKey ? rememberPointerRequest", js)
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

    def test_modifier_tap_after_plain_selection_works_for_option_and_platform_mod(self) -> None:
        self.run_node(
            r"""
emit("pointerdown", { clientX: 10, clientY: 10 });
emit("pointermove", { clientX: 80, clientY: 30 });
selectionText = "right bundle";
selectionStart = source.indexOf("right");
selectionEnd = selectionStart + selectionText.length;
selectionRect = { left: 8, top: 1, right: 90, bottom: 40, width: 82, height: 39 };
emit("pointerup", { clientX: 80, clientY: 30 });
emit("keydown", { key: "Alt", altKey: true });
selectionText = "";
selectionStart = selectionEnd;
emit("keyup", { key: "Alt" });
let lookups = messages.filter((message) => message.startsWith("pronounceit:audioLookup:"));
if (lookups.length !== 1) throw new Error(`Option after selection did not play once: ${JSON.stringify(messages)}`);
if (payload("pronounceit:audioLookup:").text !== "right bundle") throw new Error("Option lost the completed selection");

messages.length = 0;
selectionText = "bundle";
selectionStart = source.indexOf("bundle");
selectionEnd = selectionStart + selectionText.length;
sandbox.window.PronounceIt.configure({ directClickModifier: "mod", platformModifier: "meta" });
emit("keydown", { key: "Meta", metaKey: true });
emit("keyup", { key: "Meta" });
lookups = messages.filter((message) => message.startsWith("pronounceit:audioLookup:"));
if (lookups.length !== 1) throw new Error(`Platform modifier after selection did not play once: ${JSON.stringify(messages)}`);
"""
        )

    def test_modifier_tap_uses_settled_double_click_selection(self) -> None:
        self.run_node(
            r"""
emit("pointerdown", { clientX: 34, clientY: 14 });
emit("pointerup", { clientX: 34, clientY: 14 });
selectionText = "bundle";
selectionStart = source.indexOf("bundle");
selectionEnd = selectionStart + selectionText.length;
selectionRect = { left: 20, top: 1, right: 80, bottom: 24, width: 60, height: 23 };
emit("dblclick", { clientX: 34, clientY: 14 });
flushTimers();

selectionText = "";
selectionStart = selectionEnd;
emit("keydown", { key: "Alt", altKey: true });
emit("keyup", { key: "Alt" });
const lookups = messages.filter((message) => message.startsWith("pronounceit:audioLookup:"));
if (lookups.length !== 1) throw new Error(`Double-click selection did not play once: ${JSON.stringify(messages)}`);
const request = payload("pronounceit:audioLookup:");
if (request.text !== "bundle" || request.contextText.slice(request.contextOffsetStart, request.contextOffsetEnd) !== "bundle") {
  throw new Error(`Double-click selection lost context: ${JSON.stringify(request)}`);
}
"""
        )

    def test_plain_pointer_clears_cached_selection(self) -> None:
        self.run_node(
            r"""
selectionText = "bundle";
selectionStart = source.indexOf("bundle");
selectionEnd = selectionStart + selectionText.length;
emit("selectionchange");
emit("pointerdown", { clientX: 5, clientY: 5 });
selectionText = "";
selectionStart = selectionEnd;
emit("selectionchange");
emit("keydown", { key: "Alt", altKey: true });
emit("keyup", { key: "Alt" });
if (messages.some((message) => message.startsWith("pronounceit:audioLookup:"))) {
  throw new Error(`Collapsed selection replayed stale text: ${JSON.stringify(messages)}`);
}
"""
        )

    def test_capture_phase_modifier_handles_amboss_wrapped_selection(self) -> None:
        self.run_node(
            r"""
const before = { nodeType: 3, textContent: "ECG shows ", parentElement: wrapper };
const amboss = new Element("span");
const underline = new Element("u");
const ambossText = { nodeType: 3, textContent: "bundle", parentElement: underline };
const after = { nodeType: 3, textContent: " today.", parentElement: wrapper };
underline.textContent = "bundle";
underline.childNodes = [ambossText];
underline.children = [];
amboss.appendChild(underline);
amboss.textContent = "bundle";
amboss.parentElement = wrapper;
wrapper.textContent = "ECG shows bundle today.";
wrapper.childNodes = [before, amboss, after];
wrapper.children = [amboss];
selectionText = "bundle";
selectionRangeOverride = {
  startContainer: ambossText,
  endContainer: ambossText,
  startOffset: 0,
  endOffset: 6,
  commonAncestorContainer: ambossText,
  getBoundingClientRect() { return selectionRect; },
  getClientRects() { return [selectionRect]; },
};

emit("keydown", { key: "Alt", altKey: true, stopBeforeBubble: true });
emit("keyup", { key: "Alt", stopBeforeBubble: true });
const request = payload("pronounceit:audioLookup:");
if (request.text !== "bundle" || !request.contextText.includes("ECG shows bundle today.")) {
  throw new Error(`AMBOSS-wrapped selection was not preserved: ${JSON.stringify(request)}`);
}
"""
        )

    def test_modifier_selection_spanning_nested_markup_keeps_context_offsets(self) -> None:
        self.run_node(
            r"""
const before = { nodeType: 3, textContent: "right ", parentElement: wrapper };
const amboss = new Element("span");
const ambossText = { nodeType: 3, textContent: "bundle", parentElement: amboss };
const after = { nodeType: 3, textContent: " branch", parentElement: wrapper };
amboss.textContent = "bundle";
amboss.childNodes = [ambossText];
amboss.children = [];
amboss.parentElement = wrapper;
wrapper.textContent = "right bundle branch";
wrapper.childNodes = [before, amboss, after];
wrapper.children = [amboss];
selectionText = "right bundle";
selectionRangeOverride = {
  startContainer: before,
  endContainer: ambossText,
  startOffset: 0,
  endOffset: 6,
  commonAncestorContainer: wrapper,
  getBoundingClientRect() { return selectionRect; },
  getClientRects() { return [selectionRect]; },
};

emit("selectionchange");
emit("keydown", { key: "Alt", altKey: true });
emit("keyup", { key: "Alt" });
const request = payload("pronounceit:audioLookup:");
if (request.text !== "right bundle") throw new Error(`Nested selection changed text: ${JSON.stringify(request)}`);
if (request.contextText.slice(request.contextOffsetStart, request.contextOffsetEnd) !== "right bundle") {
  throw new Error(`Nested selection has bad context offsets: ${JSON.stringify(request)}`);
}

// Adjacent paragraphs must not concatenate into an unknown multiword term.
const paragraph = new Element("p");
const preceding = new Element("p");
const earlier = { nodeType: 3, textContent: "myocardial infarction", parentElement: preceding };
preceding.childNodes = [earlier];
paragraph.childNodes = [before, amboss, after];
before.parentElement = paragraph;
amboss.parentElement = paragraph;
after.parentElement = paragraph;
paragraph.parentElement = wrapper;
preceding.parentElement = wrapper;
wrapper.childNodes = [preceding, paragraph];
selectionRangeOverride.commonAncestorContainer = wrapper;
messages.length = 0;
emit("selectionchange");
emit("keydown", { key: "Alt", altKey: true });
emit("keyup", { key: "Alt" });
const blocks = payload("pronounceit:audioLookup:");
if (!blocks.contextText.includes("infarction\nright bundle")) throw new Error("Block boundary was lost");
if (blocks.contextText.slice(blocks.contextOffsetStart, blocks.contextOffsetEnd) !== "right bundle") throw new Error("Block offsets changed the selection");
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

    def test_ctrl_gestures_open_quick_card_autoplay_once_and_preserve_context(self) -> None:
        self.run_node(
            r"""
const plainRightClick = emit("contextmenu");
if (plainRightClick.defaultPrevented || plainRightClick.propagationStopped) {
  throw new Error("Plain right-click was suppressed");
}
if (messages.length) throw new Error(`Plain right-click triggered pronunciation: ${JSON.stringify(messages)}`);

const ctrlRightClick = emit("contextmenu", { ctrlKey: true });
if (!ctrlRightClick.defaultPrevented || !ctrlRightClick.propagationStopped) {
  throw new Error("Ctrl-right-click did not open the quick card");
}
let popup = body.querySelector(".pronounceit-popup");
if (!popup || popup.getAttribute("data-loading") !== "true") {
  throw new Error("Ctrl-right-click did not show an immediate loading card");
}
if (body.querySelector(".pronounceit-menu")) throw new Error("Legacy compact menu was shown");
let play = popup.querySelector(".pronounceit-play-button");
let save = popup.querySelector(".pronounceit-save-button");
if (!play.disabled || !save.disabled) throw new Error("Loading card actions should be disabled");
let request = payload("pronounceit:lookup:");
if (request.text !== "bundle" || request.autoPlay !== true) {
  throw new Error(`Ctrl-right-click did not preserve the request: ${JSON.stringify(request)}`);
}
if (messages.some((message) => message.startsWith("pronounceit:audioLookup:"))) {
  throw new Error(`Quick card played before lookup completed: ${JSON.stringify(messages)}`);
}

sandbox.window.PronounceIt.show({
  term: "bundle",
  pronunciation: "BUN-dul",
  audioSource: "audio",
  audioSourceLabel: "Audio pronunciation",
  audioAvailable: true,
  autoPlay: request.autoPlay,
  request,
  rect: request.rect,
});
popup = body.querySelector(".pronounceit-popup");
if (popup.getAttribute("data-loading") !== "false") throw new Error("Lookup did not populate the existing card");
play = popup.querySelector(".pronounceit-play-button");
save = popup.querySelector(".pronounceit-save-button");
if (play.disabled || save.disabled) throw new Error("Loaded quick card actions should be enabled");
if (messages.filter((message) => message.startsWith("pronounceit:audioLookup:")).length !== 1) {
  throw new Error(`Opening the loaded card should play once: ${JSON.stringify(messages)}`);
}
play.listeners.click({});
if (messages.filter((message) => message.startsWith("pronounceit:audioLookup:")).length !== 2) {
  throw new Error(`Play should repeat the pronunciation once: ${JSON.stringify(messages)}`);
}
save.listeners.click({});
for (const action of [payload("pronounceit:audioLookup:"), payload("pronounceit:saveLookup:")]) {
  if (action.text !== "bundle" || !action.contextText.includes("right bundle branch block")) {
    throw new Error(`Quick card action lost context: ${JSON.stringify(action)}`);
  }
}

emit("keydown", { key: "Escape" });
messages.length = 0;
selectionText = "right bundle";
selectionStart = source.indexOf("right");
selectionEnd = selectionStart + selectionText.length;
emit("selectionchange");
emit("keydown", { key: "Control", ctrlKey: true });
emit("keyup", { key: "Control" });
popup = body.querySelector(".pronounceit-popup");
if (!popup || popup.getAttribute("data-loading") !== "true") {
  throw new Error("Control after selection did not open the loading card");
}
request = payload("pronounceit:lookup:");
if (request.text !== "right bundle" || request.autoPlay !== true) throw new Error(`Selection should open and play its term: ${JSON.stringify(request)}`);

emit("keydown", { key: "Escape" });
messages.length = 0;
emit("pointerdown", { ctrlKey: true, clientX: 34, clientY: 14 });
emit("pointerup", { ctrlKey: true, clientX: 34, clientY: 14 });
popup = body.querySelector(".pronounceit-popup");
if (!popup || popup.getAttribute("data-loading") !== "true") {
  throw new Error("Ctrl-left-click did not open the loading card");
}
request = payload("pronounceit:lookup:");
if (request.text !== "right bundle" || request.autoPlay !== true) throw new Error(`Ctrl-left-click should open and play its term: ${JSON.stringify(request)}`);
"""
        )

    def test_context_modifier_quick_card_can_be_disabled(self) -> None:
        self.run_node(
            r"""
sandbox.window.PronounceIt.configure({ showNativeContextMenu: false });
emit("pointerdown", { ctrlKey: true, clientX: 34, clientY: 14 });
emit("pointerup", { ctrlKey: true, clientX: 34, clientY: 14 });
if (body.querySelector(".pronounceit-popup")) throw new Error("Disabled context path opened a quick card from Ctrl-click");
if (messages.length) throw new Error(`Disabled context path sent bridge messages from Ctrl-click: ${JSON.stringify(messages)}`);
selectionText = "right bundle";
selectionStart = source.indexOf("right");
selectionEnd = selectionStart + selectionText.length;
emit("selectionchange");
emit("keydown", { key: "Control", ctrlKey: true });
emit("keyup", { key: "Control" });
if (body.querySelector(".pronounceit-popup")) throw new Error("Disabled context path opened a quick card from selection");
if (messages.length) throw new Error(`Disabled context path sent bridge messages: ${JSON.stringify(messages)}`);
"""
        )

    def test_context_modifier_quick_card_wins_when_modifiers_overlap(self) -> None:
        self.run_node(
            r"""
sandbox.window.PronounceIt.configure({ directClickModifier: "ctrl", contextMenuModifier: "ctrl" });
selectionText = "right bundle";
selectionStart = source.indexOf("right");
selectionEnd = selectionStart + selectionText.length;
emit("selectionchange");
emit("keydown", { key: "Control", ctrlKey: true });
emit("keyup", { key: "Control" });
if (!body.querySelector(".pronounceit-popup")) throw new Error("Overlapping modifier did not open quick card");
if (messages.some((message) => message.startsWith("pronounceit:audioLookup:"))) {
  throw new Error(`Overlapping modifier played audio: ${JSON.stringify(messages)}`);
}
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
const play = popup && popup.querySelector(".pronounceit-play-button");
if (!play || play.textContent !== "Play") throw new Error("Play action was not simplified");
if (!save || save.disabled || save.textContent !== "Save") {
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

    def test_popup_uses_friendly_source_labels_and_updates_after_fallback(self) -> None:
        self.run_node(
            r"""
sandbox.window.PronounceIt.show({
  term: "clozapine",
  pronunciation: "KLOH-zuh-peen",
  found: true,
  audioSource: "audio",
  audioAvailable: true,
  request: { text: "clozapine", rect: {} },
  rect: {},
});
const popup = body.querySelector(".pronounceit-popup");
const badge = popup && popup.querySelector(".pronounceit-source");
if (!badge || badge.textContent !== "Audio pronunciation") {
  throw new Error("Recorded audio was not shown");
}
sandbox.window.PronounceIt.spoken({
  ok: true,
  audioSource: "computer",
  audioSourceLabel: "Computer voice",
  term: "clozapine",
});
if (badge.textContent !== "Computer voice" || !badge.className.includes("computer")) {
  throw new Error(`Actual fallback source was not shown: ${badge.textContent}`);
}
sandbox.window.PronounceIt.show({
  term: "unknown",
  pronunciation: "Unavailable",
  audioSource: "computer",
  audioAvailable: true,
  request: { text: "unknown", rect: {} },
  rect: {},
});
if (body.querySelector(".pronounceit-source").textContent !== "Computer voice") {
  throw new Error("Generated audio did not use the standard text-to-speech label");
}

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
if (!notice || notice.textContent !== "Reveal the answer before playing pronunciation." || notice.getAttribute("data-state") !== "info") {
  throw new Error(`Missing answer-side guidance: ${notice && notice.textContent}`);
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

    def test_css_contains_quick_card_and_stateful_notice_styles(self) -> None:
        css = (ROOT / "web" / "pronounceit.css").read_text(encoding="utf-8")

        self.assertIn(".pronounceit-popup", css)
        self.assertIn(".pronounceit-notice", css)
        self.assertIn('[data-state="loading"]', css)
        self.assertIn('[data-state="success"]', css)
        self.assertIn('[data-state="info"]', css)
        self.assertIn('[data-state="error"]', css)
        self.assertIn(".pronounceit-source.audio", css)
        self.assertIn(".pronounceit-source.loading", css)
        self.assertIn(".pronounceit-theme-light", css)
        self.assertIn(".pronounceit-theme-dark", css)
        self.assertNotIn(".pronounceit-theme-clinical_light", css)
        self.assertNotIn(".pronounceit-theme-slate", css)
        self.assertNotIn(".pronounceit-theme-high_contrast", css)
        self.assertNotIn(".pronounceit-menu", css)

    def test_runtime_theme_tokens_are_applied_to_popup(self) -> None:
        self.run_node(
            r"""
sandbox.window.PronounceIt.configure({
  theme: "dark",
  themeTokens: { bg: "#111827", accent: "#2563eb" },
});
sandbox.window.PronounceIt.show({
  found: true,
  term: "clozapine",
  pronunciation: "KLOH-zuh-peen",
  syllables: "clo-za-pine",
  audioAvailable: true,
  autoPlay: false,
});
const popup = body.querySelector(".pronounceit-popup");
if (!popup || popup.getAttribute("data-theme") !== "dark") throw new Error("Dark theme was not applied");
if (popup.style["--pronounceit-bg"] !== "#111827") throw new Error("Shared background token was not applied");
if (popup.style["--pronounceit-accent"] !== "#2563eb") throw new Error("Shared accent token was not applied");
if (popup.querySelector(".pronounceit-pronunciation").textContent !== "KLOH-zuh-peen") throw new Error("Guide missing");
sandbox.window.PronounceIt.show({ found: true, term: "unresolved", pronunciation: "", audioAvailable: true,
  audioStatus: "Computer voice ready", autoPlay: false });
if (body.querySelector(".pronounceit-pronunciation").textContent !== "Pronunciation unavailable") throw new Error("Audio status replaced missing guide");
if (body.querySelector(".pronounceit-play-button").disabled) throw new Error("Missing guide disabled playback");
"""
        )


if __name__ == "__main__":
    unittest.main()
