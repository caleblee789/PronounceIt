(function () {
  "use strict";

  const MESSAGE_PREFIX = "pronounceit:";
  const DEFAULT_CONFIG = {
    enabled: true,
    directClickModifier: "alt",
    platformModifier: "ctrl",
    allowOnQuestionSide: false,
    answerVisible: false,
    activationMode: "context_menu",
    theme: "system",
    showSaveButton: true,
    unknownTermMessage: "Pronunciation unavailable",
  };
  const CONTEXT_LIMIT = 160;

  let config = Object.assign({}, DEFAULT_CONFIG, window.PronounceItConfig || {});
  let lastPayload = null;
  let pendingRequest = null;
  let lastPointerRequest = null;
  let lastPointerCaptureAt = 0;
  let directGesture = null;
  let activationKeyDown = false;
  let activationKeyCancelled = false;
  let activationKeyUsedByGesture = false;
  let suppressClickUntil = 0;
  let contextRequest = null;
  let activeRequest = null;
  let popupEl = null;
  let noticeEl = null;
  let noticeTimer = null;

  function send(action, payload) {
    if (typeof pycmd !== "function") {
      return;
    }
    pycmd(MESSAGE_PREFIX + action + ":" + JSON.stringify(payload || {}));
  }

  function selectedText(options) {
    const allowCollapsed = Boolean(options && options.allowCollapsed);
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) {
      return null;
    }
    const rawText = selection.toString();
    const selected = rawText.trim();
    const range = selection.getRangeAt(0);
    if (!selected) {
      return allowCollapsed ? requestFromCollapsedRange(range) : null;
    }
    const rect = range.getBoundingClientRect();
    const expanded = expandedSelectionFromRange(range);
    const text = expanded && expanded.text ? expanded.text : selected;
    return requestFromTextContext(
      text,
      selected,
      rect,
      expanded && expanded.context ? expanded.context : contextFromSelectionRange(range, text)
    );
  }

  function selectedTextAtPoint(event) {
    if (!event || !Number.isFinite(event.clientX) || !Number.isFinite(event.clientY)) {
      return null;
    }
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0 || !String(selection.toString() || "").trim()) {
      return null;
    }
    for (let index = 0; index < selection.rangeCount; index += 1) {
      const range = selection.getRangeAt(index);
      if (rangeContainsPoint(range, event.clientX, event.clientY)) {
        return selectedText();
      }
    }
    return null;
  }

  function rangeContainsPoint(range, x, y) {
    if (!range) {
      return false;
    }
    if (typeof range.getClientRects === "function") {
      const rects = range.getClientRects();
      for (let index = 0; index < rects.length; index += 1) {
        if (pointInRect(x, y, rects[index])) {
          return true;
        }
      }
    }
    if (typeof range.getBoundingClientRect === "function") {
      return pointInRect(x, y, range.getBoundingClientRect());
    }
    return false;
  }

  function requestFromCollapsedRange(range) {
    if (!range || !range.startContainer || range.startContainer.nodeType !== Node.TEXT_NODE) {
      return null;
    }
    const nodeText = range.startContainer.textContent || "";
    const span = extractTermSpanAtOffset(nodeText, range.startOffset);
    if (!span) {
      return null;
    }
    const rect = typeof range.getBoundingClientRect === "function"
      ? range.getBoundingClientRect()
      : null;
    return requestFromTextContext(
      span.text,
      span.text,
      rect,
      contextFromTextNode(range.startContainer, span.start, span.end)
    );
  }

  function wordAtPoint(x, y) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      return null;
    }
    const range = rangeAtPoint(x, y);
    if (!range || !range.startContainer || range.startContainer.nodeType !== Node.TEXT_NODE) {
      return null;
    }

    const text = range.startContainer.textContent || "";
    const span = extractTermSpanAtOffset(text, range.startOffset);
    if (!span) {
      return null;
    }

    const rect = range.getBoundingClientRect();
    return requestFromTextContext(
      span.text,
      span.text,
      rect,
      contextFromTextNode(range.startContainer, span.start, span.end),
      x,
      y
    );
  }

  function requestFromElementPoint(element, x, y) {
    if (!element || element === document.body || !Number.isFinite(x) || !Number.isFinite(y)) {
      return null;
    }
    const textNodes = textNodesUnder(element);
    for (const node of textNodes) {
      const parent = node.parentElement;
      if (!parent || typeof parent.getBoundingClientRect !== "function") {
        continue;
      }
      const rect = parent.getBoundingClientRect();
      if (!pointInRect(x, y, rect)) {
        continue;
      }
      const text = node.textContent || "";
      const offset = nearestTextOffset(text, x, rect);
      const span = extractTermSpanAtOffset(text, offset);
      if (!span) {
        continue;
      }
      return requestFromTextContext(
        span.text,
        span.text,
        rect,
        contextFromTextNode(node, span.start, span.end),
        x,
        y
      );
    }

    if (typeof element.getBoundingClientRect !== "function") {
      return null;
    }
    const rect = element.getBoundingClientRect();
    if (!pointInRect(x, y, rect)) {
      return null;
    }
    const text = String(element.textContent || "").replace(/\u00a0/g, " ");
    const offset = nearestTextOffset(text, x, rect);
    const span = extractTermSpanAtOffset(text, offset);
    if (!span) {
      return null;
    }
    return requestFromTextContext(
      span.text,
      span.text,
      rect,
      contextFromText(text, span.start, span.end),
      x,
      y
    );
  }

  function textNodesUnder(element) {
    const nodes = [];
    if (!element) {
      return nodes;
    }
    if (element.nodeType === Node.TEXT_NODE) {
      nodes.push(element);
      return nodes;
    }
    if (element.childNodes && element.childNodes.length) {
      for (const child of element.childNodes) {
        nodes.push.apply(nodes, textNodesUnder(child));
      }
    }
    return nodes;
  }

  function pointInRect(x, y, rect) {
    return Boolean(rect && x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom);
  }

  function termFromElement(element) {
    let current = element && element.nodeType === Node.TEXT_NODE ? element.parentElement : element;
    let depth = 0;
    while (current && current !== document.body && depth < 5) {
      const text = normalizedElementText(current.textContent || "");
      if (isPlausibleElementTerm(text) && typeof current.getBoundingClientRect === "function") {
        return requestFromTextAndRect(text, current.getBoundingClientRect());
      }
      current = current.parentElement;
      depth += 1;
    }
    return null;
  }

  function normalizedElementText(text) {
    return stripClozeMarkup(text).replace(/\u00a0/g, " ").trim().replace(/\s+/g, " ");
  }

  function isPlausibleElementTerm(text) {
    if (!/[A-Za-z]/.test(text) || text.length > 80) {
      return false;
    }
    if (text.split(/\s+/).filter(Boolean).length > 4) {
      return false;
    }
    return /^[A-Za-z][A-Za-z0-9'\u2010-\u2015 -]{0,79}$/.test(text);
  }

  function requestFromTextAndRect(text, rect) {
    return requestFromTextContext(
      text,
      text,
      rect,
      contextFromText(text, 0, String(text || "").length),
      0,
      0
    );
  }

  function requestFromTextContext(text, selected, rect, context, fallbackX, fallbackY) {
    const normalizedText = String(text || "").trim();
    const normalizedSelected = String(selected || normalizedText).trim();
    if (!normalizedText || !/[A-Za-z]/.test(normalizedText)) {
      return null;
    }
    return Object.assign({
      text: normalizedText,
      selectedText: normalizedSelected || normalizedText,
      rect: rectPayload(rect, fallbackX, fallbackY),
    }, context || {});
  }

  function rectPayload(rect, fallbackX, fallbackY) {
    const x = Number.isFinite(fallbackX) ? fallbackX : 0;
    const y = Number.isFinite(fallbackY) ? fallbackY : 0;
    const left = Number(rect && rect.left);
    const top = Number(rect && rect.top);
    const right = Number(rect && rect.right);
    const bottom = Number(rect && rect.bottom);
    const width = Number(rect && rect.width);
    const height = Number(rect && rect.height);
    const safeLeft = Number.isFinite(left) ? left : x;
    const safeTop = Number.isFinite(top) ? top : y;
    return {
      left: safeLeft,
      top: safeTop,
      right: Number.isFinite(right) ? right : safeLeft,
      bottom: Number.isFinite(bottom) ? bottom : safeTop,
      width: Number.isFinite(width) && width > 0 ? width : 1,
      height: Number.isFinite(height) && height > 0 ? height : 1,
    };
  }

  function stripClozeMarkup(text) {
    return String(text || "").replace(/\{\{c\d+::([^{}]*?)(?:::[^{}]*)?\}\}/gi, "$1");
  }

  function extractTermAtOffset(text, offset) {
    const span = extractTermSpanAtOffset(text, offset);
    return span ? span.text : null;
  }

  function extractTermSpanAtOffset(text, offset) {
    const safeOffset = Math.max(0, Math.min(offset, text.length));
    const left = text.slice(0, safeOffset);
    const right = text.slice(safeOffset);
    const leftMatch = left.match(/[A-Za-z0-9'\u2010-\u2015-]+$/);
    const rightMatch = right.match(/^[A-Za-z0-9'\u2010-\u2015-]+/);
    const word = ((leftMatch && leftMatch[0]) || "") + ((rightMatch && rightMatch[0]) || "");
    if (!/[A-Za-z]/.test(word)) {
      return null;
    }
    const leftLength = leftMatch ? leftMatch[0].length : 0;
    return {
      text: word,
      start: safeOffset - leftLength,
      end: safeOffset - leftLength + word.length,
    };
  }

  function expandedSelectionFromRange(range) {
    if (
      !range ||
      !range.startContainer ||
      range.startContainer !== range.endContainer ||
      range.startContainer.nodeType !== Node.TEXT_NODE
    ) {
      return null;
    }
    const nodeText = range.startContainer.textContent || "";
    const expanded = expandOffsetsToTokenBoundaries(nodeText, range.startOffset, range.endOffset);
    if (!expanded || expanded.start === expanded.end) {
      return null;
    }
    const text = nodeText.slice(expanded.start, expanded.end).trim();
    if (!text || !/[A-Za-z]/.test(text)) {
      return null;
    }
    return {
      text: text,
      context: contextFromTextNode(range.startContainer, expanded.start, expanded.end),
    };
  }

  function expandOffsetsToTokenBoundaries(text, start, end) {
    const source = String(text || "");
    if (!source) {
      return null;
    }
    let safeStart = Math.max(0, Math.min(Number(start) || 0, source.length));
    let safeEnd = Math.max(safeStart, Math.min(Number(end) || safeStart, source.length));
    while (safeStart > 0 && isTokenChar(source.charAt(safeStart - 1))) {
      safeStart -= 1;
    }
    while (safeEnd < source.length && isTokenChar(source.charAt(safeEnd))) {
      safeEnd += 1;
    }
    return { start: safeStart, end: safeEnd };
  }

  function isTokenChar(char) {
    return /[A-Za-z0-9'\u2010-\u2015-]/.test(char || "");
  }

  function contextFromSelectionRange(range, selected) {
    if (!range) {
      return {};
    }
    if (
      range.startContainer &&
      range.startContainer === range.endContainer &&
      range.startContainer.nodeType === Node.TEXT_NODE
    ) {
      return contextFromTextNode(range.startContainer, range.startOffset, range.endOffset);
    }

    const element = range.commonAncestorContainer &&
      (range.commonAncestorContainer.nodeType === Node.TEXT_NODE
        ? range.commonAncestorContainer.parentElement
        : range.commonAncestorContainer);
    const text = normalizedElementText((element && element.textContent) || "");
    const selectedText = normalizedElementText(selected || "");
    const offset = selectedText ? text.indexOf(selectedText) : -1;
    if (offset >= 0) {
      return contextFromText(text, offset, offset + selectedText.length);
    }
    return {};
  }

  function contextFromTextNode(node, start, end) {
    const nodeText = (node && node.textContent) || "";
    const parentContext = contextFromParentText(node, nodeText, start, end);
    if (parentContext.contextText) {
      return parentContext;
    }
    return contextFromText(nodeText, start, end);
  }

  function contextFromParentText(node, nodeText, start, end) {
    let current = node && node.parentElement;
    let depth = 0;
    while (current && current !== document.body && depth < 5) {
      const text = String(current.textContent || "").replace(/\u00a0/g, " ");
      if (text && text.length <= 1000 && text.length > String(nodeText || "").length) {
        const nodeOffset = nodeText ? text.indexOf(nodeText) : -1;
        if (nodeOffset >= 0) {
          return contextFromText(text, nodeOffset + start, nodeOffset + end);
        }
      }
      current = current.parentElement;
      depth += 1;
    }
    return {};
  }

  function contextFromText(text, start, end) {
    const source = String(text || "").replace(/\u00a0/g, " ");
    if (!source) {
      return {};
    }
    const safeStart = Math.max(0, Math.min(Number(start) || 0, source.length));
    const safeEnd = Math.max(safeStart, Math.min(Number(end) || safeStart, source.length));
    const selectedLength = Math.max(0, safeEnd - safeStart);
    const extra = Math.max(0, CONTEXT_LIMIT - selectedLength);
    let windowStart = Math.max(0, safeStart - Math.floor(extra / 2));
    let windowEnd = Math.min(source.length, windowStart + CONTEXT_LIMIT);
    windowStart = Math.max(0, windowEnd - CONTEXT_LIMIT);
    return {
      contextText: source.slice(windowStart, windowEnd),
      contextOffsetStart: safeStart - windowStart,
      contextOffsetEnd: safeEnd - windowStart,
    };
  }

  function rangeAtPoint(x, y) {
    if (document.caretRangeFromPoint) {
      return document.caretRangeFromPoint(x, y);
    }
    if (document.caretPositionFromPoint) {
      const position = document.caretPositionFromPoint(x, y);
      if (!position) {
        return null;
      }
      const range = document.createRange();
      range.setStart(position.offsetNode, position.offset);
      range.collapse(true);
      return range;
    }
    return textNodeRangeAtPoint(x, y);
  }

  function textNodeRangeAtPoint(x, y) {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      const parent = node.parentElement;
      if (parent) {
        const rect = parent.getBoundingClientRect();
        if (x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom) {
          const range = document.createRange();
          const text = node.textContent || "";
          range.setStart(node, nearestTextOffset(text, x, rect));
          range.collapse(true);
          return range;
        }
      }
      node = walker.nextNode();
    }
    return null;
  }

  function nearestTextOffset(text, x, rect) {
    if (!text.length || !rect.width) {
      return 0;
    }
    const ratio = Math.max(0, Math.min(1, (x - rect.left) / rect.width));
    return Math.max(0, Math.min(text.length, Math.round(text.length * ratio)));
  }

  function requestPronunciation(options) {
    if (!canPronounce()) {
      return;
    }
    const request = pendingRequest || currentPronounceRequest();
    if (!request) {
      showNotice("Point to or select a word first.", "error");
      return false;
    }
    pendingRequest = null;
    send("lookup", Object.assign({}, request, options || {}));
    return true;
  }

  function requestAudioOnly(request) {
    if (!canPronounce()) {
      return false;
    }
    if (!request) {
      showNotice("Point to or select a word first.", "error");
      return false;
    }
    activeRequest = request;
    showNotice("Playing…", "loading", request.rect, 0);
    send("audioLookup", request);
    return true;
  }

  function rememberPointerRequest(event) {
    if (isPronounceItElement(event && event.target)) {
      return null;
    }
    const request = pointerRequest(event);
    if (request) {
      lastPointerRequest = request;
    }
    return request;
  }

  function pointerRequest(event) {
    if (!event) {
      return null;
    }
    if (!Number.isFinite(event.clientX) || !Number.isFinite(event.clientY)) {
      return selectedText() || termFromElement(event.target);
    }
    const request =
      selectedTextAtPoint(event) ||
      wordAtPoint(event.clientX, event.clientY) ||
      requestFromElementPoint(event.target, event.clientX, event.clientY) ||
      termFromElement(event.target);
    return request;
  }

  function isPronounceItElement(target) {
    let current = target && target.nodeType === Node.TEXT_NODE ? target.parentElement : target;
    let depth = 0;
    while (current && current !== document.body && depth < 8) {
      const className = String(current.className || "");
      if (className.split(/\s+/).some((name) => name.indexOf("pronounceit-") === 0)) {
        return true;
      }
      current = current.parentElement || current.parent || null;
      depth += 1;
    }
    return false;
  }

  function beginDirectGesture(event) {
    if (
      !canPronounce() ||
      isPronounceItElement(event && event.target) ||
      !isPrimaryClick(event) ||
      !modifierMatches(event, config.directClickModifier)
    ) {
      directGesture = null;
      return null;
    }
    const request = pointerRequest(event);
    if (request) {
      lastPointerRequest = request;
    }
    activationKeyUsedByGesture = true;
    directGesture = {
      pointerId: event.pointerId,
      startX: Number(event.clientX || 0),
      startY: Number(event.clientY || 0),
      startTarget: event.target,
      initialSelectionText: selectionValue(),
      moved: false,
      request: request,
    };
    return request;
  }

  function updateDirectGesture(event) {
    if (!directGesture || !sameGesturePointer(event, directGesture)) {
      return;
    }
    const dx = Number(event.clientX || 0) - directGesture.startX;
    const dy = Number(event.clientY || 0) - directGesture.startY;
    if (Math.hypot(dx, dy) > 6) {
      directGesture.moved = true;
    }
  }

  function finishDirectGesture(event) {
    const gesture = directGesture;
    directGesture = null;
    if (
      !gesture ||
      !sameGesturePointer(event, gesture) ||
      !isPrimaryClick(event) ||
      !modifierMatches(event, config.directClickModifier)
    ) {
      return;
    }
    suppressClickUntil = Date.now() + 500;
    if (!gesture.moved) {
      if (typeof event.preventDefault === "function") {
        event.preventDefault();
      }
      if (typeof event.stopPropagation === "function") {
        event.stopPropagation();
      }
      requestAudioOnly(gesture.request);
      return;
    }

    const endPoint = {
      clientX: Number(event.clientX || 0),
      clientY: Number(event.clientY || 0),
      target: event.target,
    };
    window.setTimeout(function () {
      const selected =
        selectedTextAtPoint(endPoint) ||
        selectedTextAtPoint({
          clientX: gesture.startX,
          clientY: gesture.startY,
          target: gesture.startTarget,
        });
      const currentSelection = selectionValue();
      const changedSelection =
        currentSelection && currentSelection !== gesture.initialSelectionText
          ? selectedText()
          : null;
      requestAudioOnly(selected || changedSelection || pointerRequest(endPoint) || gesture.request);
    }, 0);
  }

  function cancelDirectGesture() {
    directGesture = null;
    if (activationKeyDown) {
      activationKeyCancelled = true;
    }
  }

  function sameGesturePointer(event, gesture) {
    return (
      gesture.pointerId === undefined ||
      event.pointerId === undefined ||
      gesture.pointerId === event.pointerId
    );
  }

  function suppressActivatedClick(event) {
    if (Date.now() > suppressClickUntil) {
      return;
    }
    suppressClickUntil = 0;
    if (typeof event.preventDefault === "function") {
      event.preventDefault();
    }
    if (typeof event.stopPropagation === "function") {
      event.stopPropagation();
    }
  }

  function rememberPointerRequestThrottled(event) {
    const now = Date.now();
    if (now - lastPointerCaptureAt < 75) {
      return;
    }
    lastPointerCaptureAt = now;
    rememberPointerRequest(event);
  }

  function pronounceCurrent() {
    if (!canPronounce()) {
      return;
    }
    requestAudioOnly(currentPronounceRequest());
  }

  function playText(text) {
    const clean = String(text || "").trim();
    if (!clean || !canPronounce()) {
      if (!clean) showNotice("Point to or select a word first.", "error");
      return;
    }
    requestAudioOnly({ text: clean, selectedText: clean, rect: {} });
  }

  function currentPronounceRequest() {
    return selectedText() || lastPointerRequest || selectedText({ allowCollapsed: true });
  }

  function selectionValue() {
    const selection = window.getSelection();
    return selection ? String(selection.toString() || "").trim() : "";
  }

  function canPronounce() {
    return Boolean(config.enabled);
  }

  function modifierMatches(event, modifier) {
    const normalized = String(modifier || "").toLowerCase();
    if (!normalized || normalized === "disabled") {
      return false;
    }
    const expected = { alt: false, ctrl: false, meta: false, shift: false };
    if (normalized === "alt" || normalized === "option") expected.alt = true;
    else if (normalized === "shift") expected.shift = true;
    else if (normalized === "meta" || normalized === "cmd" || normalized === "command") expected.meta = true;
    else if (normalized === "ctrl" || normalized === "control") expected.ctrl = true;
    else if (normalized === "mod") expected[config.platformModifier === "meta" ? "meta" : "ctrl"] = true;
    else return false;
    return (
      Boolean(event.altKey) === expected.alt &&
      Boolean(event.ctrlKey) === expected.ctrl &&
      Boolean(event.metaKey) === expected.meta &&
      Boolean(event.shiftKey) === expected.shift
    );
  }

  function activationModifierKey() {
    const normalized = String(config.directClickModifier || "").toLowerCase();
    if (normalized === "alt" || normalized === "option") return "Alt";
    if (normalized === "shift") return "Shift";
    if (normalized === "meta" || normalized === "cmd" || normalized === "command") return "Meta";
    if (normalized === "ctrl" || normalized === "control") return "Control";
    if (normalized === "mod") return config.platformModifier === "meta" ? "Meta" : "Control";
    return "";
  }

  function handleActivationKeyDown(event) {
    const key = activationModifierKey();
    if (!key) {
      return;
    }
    if (event.key !== key) {
      if (activationKeyDown) {
        activationKeyCancelled = true;
      }
      return;
    }
    if (!activationKeyDown) {
      activationKeyDown = true;
      activationKeyCancelled = false;
      activationKeyUsedByGesture = false;
    }
    if (selectionValue() && typeof event.preventDefault === "function") {
      event.preventDefault();
    }
  }

  function handleActivationKeyUp(event) {
    if (event.key !== activationModifierKey() || !activationKeyDown) {
      return;
    }
    const shouldPlay = !activationKeyCancelled && !activationKeyUsedByGesture;
    activationKeyDown = false;
    activationKeyCancelled = false;
    activationKeyUsedByGesture = false;
    if (!shouldPlay) {
      return;
    }
    const request = selectedText();
    if (!request) {
      return;
    }
    if (typeof event.preventDefault === "function") {
      event.preventDefault();
    }
    if (typeof event.stopPropagation === "function") {
      event.stopPropagation();
    }
    requestAudioOnly(request);
  }

  function isPrimaryClick(event) {
    return event.button === undefined || event.button === 0;
  }

  function showNotice(text, state, rect, duration) {
    if (
      !text ||
      !document.body ||
      typeof document.createElement !== "function" ||
      typeof document.body.appendChild !== "function"
    ) {
      return;
    }
    if (!noticeEl) {
      noticeEl = document.createElement("div");
      applyTheme(noticeEl, "pronounceit-notice");
      noticeEl.setAttribute("role", "status");
      noticeEl.setAttribute("aria-live", "polite");
      document.body.appendChild(noticeEl);
    }
    noticeEl.textContent = text;
    noticeEl.setAttribute("data-state", state || "info");
    placeNotice(rect);
    if (noticeTimer && typeof window.clearTimeout === "function") {
      window.clearTimeout(noticeTimer);
    }
    const timeout = duration === undefined ? (state === "error" ? 4000 : 1600) : duration;
    if (timeout > 0 && typeof window.setTimeout === "function") {
      noticeTimer = window.setTimeout(hideNotice, timeout);
    }
  }

  function placeNotice(rect) {
    if (!noticeEl) return;
    const anchor = rect || {};
    const hasAnchor = Number.isFinite(Number(anchor.left)) && Number.isFinite(Number(anchor.bottom));
    noticeEl.setAttribute("data-anchored", hasAnchor ? "true" : "false");
    if (!hasAnchor) {
      noticeEl.style.left = "50%";
      noticeEl.style.top = "18px";
      noticeEl.style.transform = "translateX(-50%)";
      return;
    }
    noticeEl.style.transform = "none";
    placeElement(noticeEl, Number(anchor.left), Number(anchor.bottom) + 8);
  }

  function hideNotice() {
    if (noticeTimer && typeof window.clearTimeout === "function") {
      window.clearTimeout(noticeTimer);
    }
    noticeTimer = null;
    if (noticeEl) {
      noticeEl.remove();
      noticeEl = null;
    }
  }

  function playbackInfo(payload) {
    const word = payload.term || payload.requestedText || "";
    const playText = payload.speechText || word;
    return {
      word: word,
      playText: playText,
      audioAvailable: Boolean(playText || payload.audioFile),
    };
  }

  function playbackRequest(payload) {
    const source = payload || {};
    const raw = source.request && typeof source.request === "object" ? source.request : source;
    const text = raw.text || raw.selectedText || source.requestedText || source.term || "";
    const selectedText = raw.selectedText || source.requestedText || text;
    const request = Object.assign({}, raw, {
      text: text,
      selectedText: selectedText,
    });
    if (!request.rect && source.rect) {
      request.rect = source.rect;
    }
    return request;
  }

  function requestPlayback(payload, statusCallback) {
    const playback = playbackInfo(payload || {});
    if (!playback.audioAvailable) {
      return false;
    }
    const request = playbackRequest(payload || {});
    if (!request.text) {
      return false;
    }
    if (typeof statusCallback === "function") {
      statusCallback("Playing...");
    }
    activeRequest = request;
    send("audioLookup", request);
    return true;
  }

  function hidePopup() {
    if (popupEl) {
      popupEl.remove();
      popupEl = null;
    }
  }

  function hideAll() {
    hidePopup();
    hideNotice();
  }

  function placeElement(element, left, top) {
    const margin = 10;
    const rect = element.getBoundingClientRect();
    const maxLeft = window.innerWidth - rect.width - margin;
    const maxTop = window.innerHeight - rect.height - margin;
    element.style.left = Math.max(margin, Math.min(left, maxLeft)) + "px";
    element.style.top = Math.max(margin, Math.min(top, maxTop)) + "px";
  }

  function show(payload) {
    lastPayload = payload;
    hidePopup();

    const playback = playbackInfo(payload);

    popupEl = document.createElement("div");
    applyTheme(popupEl, "pronounceit-popup");
    popupEl.setAttribute("role", "dialog");
    popupEl.setAttribute("aria-label", "Pronunciation");

    function playPayload() {
      requestPlayback(payload, updateStatus);
    }

    function savePayload() {
      const request = playbackRequest(payload);
      if (!request.text) {
        updateStatus("Could not save pronunciation: no term selected.");
        return;
      }
      updateStatus("Saving…");
      contextRequest = request;
      send("saveLookup", request);
    }

    const card = createPronunciationCard({
      word: playback.word,
      pronunciation: payload.pronunciation || payload.audioStatus || payload.audioHelp || "Generated audio available",
      isCurated: Boolean(payload.found),
      source: sourceLabel(payload),
      onPlay: playPayload,
      onSave: savePayload,
      audioAvailable: playback.audioAvailable,
      showSave: Boolean(config.showSaveButton),
      alreadySaved: Boolean(payload.alreadySaved),
    });

    const status = document.createElement("div");
    status.className = "pronounceit-status";
    status.setAttribute("data-empty", "true");

    popupEl.appendChild(card);
    popupEl.appendChild(status);
    document.body.appendChild(popupEl);

    const rect = payload.rect || {};
    placeElement(popupEl, Number(rect.left || 24), Number(rect.bottom || 24) + 8);

    if (payload.autoPlay && playback.audioAvailable) {
      playPayload();
    }
  }

  function createPronunciationCard(options) {
    const word = options.word || "";
    const source = options.source || (options.isCurated ? "Curated" : "Fallback");
    const card = document.createElement("section");
    card.className = "pronounceit-card";

    const header = document.createElement("div");
    header.className = "pronounceit-card-header";

    const term = document.createElement("h2");
    term.className = "pronounceit-term";
    term.textContent = word;

    const badge = document.createElement("div");
    badge.className = "pronounceit-source";
    badge.textContent = source;

    header.appendChild(term);
    header.appendChild(badge);

    const pronunciationBlock = document.createElement("div");
    pronunciationBlock.className = "pronounceit-pronunciation-block";

    const label = document.createElement("div");
    label.className = "pronounceit-pronunciation-label";
    label.textContent = "Pronunciation";

    const pronunciation = document.createElement("div");
    pronunciation.className = options.isCurated ? "pronounceit-pronunciation" : "pronounceit-pronunciation generated";
    pronunciation.textContent = options.pronunciation || "Pronunciation unavailable";

    pronunciationBlock.appendChild(label);
    pronunciationBlock.appendChild(pronunciation);

    const actions = document.createElement("div");
    actions.className = "pronounceit-actions";

    const play = document.createElement("button");
    play.type = "button";
    play.className = "pronounceit-play-button pronounceit-icon-button";
    play.title = "Play pronunciation";
    play.setAttribute("aria-label", "Play pronunciation of " + (word || "selected term"));
    play.textContent = "Play pronunciation";
    play.disabled = !options.audioAvailable;
    play.addEventListener("click", options.onPlay);
    actions.appendChild(play);

    if (options.showSave) {
      const save = document.createElement("button");
      save.type = "button";
      save.className = "pronounceit-save-button";
      save.title = options.alreadySaved ? "Pronunciation already saved" : "Save pronunciation";
      save.setAttribute("aria-label", save.title);
      save.textContent = options.alreadySaved ? "Saved" : "Save pronunciation";
      save.disabled = Boolean(options.alreadySaved);
      save.addEventListener("click", options.onSave);
      actions.appendChild(save);
    }

    card.appendChild(header);
    card.appendChild(pronunciationBlock);
    card.appendChild(actions);

    return card;
  }

  function sourceLabel(payload) {
    const qualityTier = String(payload.qualityTier || "").toLowerCase();
    if (qualityTier === "verified") {
      return "Verified";
    }
    if (qualityTier === "curated") {
      return "Curated";
    }
    if (qualityTier === "generated") {
      return "Generated guide";
    }
    if (qualityTier === "fallback") {
      return "Unverified fallback";
    }
    if (payload.audioKind === "generated") {
      return "Generated";
    }
    return "Fallback";
  }

  function updateStatus(text) {
    if (!popupEl) {
      return;
    }
    const status = popupEl.querySelector(".pronounceit-status");
    if (status) {
      status.textContent = text || "";
      status.setAttribute("data-empty", text ? "false" : "true");
    }
  }

  function spoken(result) {
    if (!result || result.ok) {
      updateStatus("");
      if (!popupEl) {
        const term = String((result && (result.term || result.text)) || (activeRequest && activeRequest.text) || "").trim();
        showNotice(term ? "Played " + term : "Played pronunciation", "success", activeRequest && activeRequest.rect);
      } else {
        hideNotice();
      }
      activeRequest = null;
      return;
    }
    const reason = result.reason ? "Could not play audio: " + result.reason : "Could not play audio.";
    updateStatus(reason);
    if (!popupEl) {
      showNotice(reason, "error", activeRequest && activeRequest.rect);
    }
    activeRequest = null;
  }

  function saved(result) {
    if (result && result.error) {
      const message = "Could not save pronunciation: " + result.error;
      updateStatus(message);
      if (!popupEl) {
        showNotice(message, "error", contextRequest && contextRequest.rect);
      }
      return;
    }
    if (result.alreadySaved) {
      lastPayload = Object.assign({}, lastPayload || {}, { alreadySaved: true });
    }
    if (!popupEl) {
      showNotice(
        result.duplicate ? "Already saved" : "Saved pronunciation",
        "success",
        contextRequest && contextRequest.rect
      );
      return;
    }
    const status = popupEl.querySelector(".pronounceit-status");
    if (status) {
      status.textContent = result.duplicate ? "Already in your list." : "Saved.";
    }
    const save = popupEl.querySelector(".pronounceit-save-button");
    if (save) {
      save.textContent = "Saved";
      save.title = "Pronunciation already saved";
      save.setAttribute("aria-label", save.title);
      save.disabled = true;
    }
  }

  function configure(nextConfig) {
    config = Object.assign({}, config, nextConfig || {});
    if (popupEl) {
      applyTheme(popupEl, "pronounceit-popup");
    }
    if (noticeEl) {
      applyTheme(noticeEl, "pronounceit-notice");
    }
  }

  function applyTheme(element, baseClass) {
    const theme = resolveTheme(config.theme);
    element.className = baseClass + " pronounceit-theme-" + theme;
    element.setAttribute("data-theme", theme);
  }

  function resolveTheme(themeName) {
    if (themeName === "clinical_light" || themeName === "slate" || themeName === "high_contrast") {
      return themeName;
    }
    if (themeName === "system" && prefersDarkMode()) {
      return "slate";
    }
    return "clinical_light";
  }

  function prefersDarkMode() {
    return Boolean(
      window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
    );
  }

  function contextTarget() {
    const request = contextRequest || currentPronounceRequest();
    if (!request) {
      showNotice("Point to or select a word first.", "error");
      return null;
    }
    return request;
  }

  function playContextTarget() {
    requestAudioOnly(contextTarget());
  }

  function showContextDetails() {
    const request = contextTarget();
    if (!request) return;
    pendingRequest = request;
    requestPronunciation({ autoPlay: false });
  }

  function saveContextTarget() {
    const request = contextTarget();
    if (!request) return;
    showNotice("Saving…", "loading", request.rect, 0);
    send("saveLookup", request);
  }

  document.addEventListener("keydown", function (event) {
    if (popupEl && event.key === "Escape") {
      event.preventDefault();
      hidePopup();
      return;
    }
    handleActivationKeyDown(event);
  });

  document.addEventListener("keyup", handleActivationKeyUp);

  document.addEventListener("contextmenu", function (event) {
    if (
      event.shiftKey ||
      !canPronounce() ||
      isPronounceItElement(event && event.target)
    ) {
      contextRequest = null;
      return;
    }
    const request = rememberPointerRequest(event);
    if (!request) {
      contextRequest = null;
      return;
    }
    contextRequest = request;
    pendingRequest = request;
    if (typeof event.preventDefault === "function") {
      event.preventDefault();
    }
    if (typeof event.stopPropagation === "function") {
      event.stopPropagation();
    }
    requestPronunciation({ autoPlay: true });
  }, true);

  function handlePointerDown(event) {
    rememberPointerRequest(event);
    beginDirectGesture(event);
  }

  function handlePointerMove(event) {
    updateDirectGesture(event);
    rememberPointerRequestThrottled(event);
  }

  function handlePointerUp(event) {
    finishDirectGesture(event);
    rememberPointerRequest(event);
  }

  if (typeof window.PointerEvent === "function") {
    document.addEventListener("pointerdown", handlePointerDown, true);
    document.addEventListener("pointermove", handlePointerMove, true);
    document.addEventListener("pointerup", handlePointerUp, true);
    document.addEventListener("pointercancel", cancelDirectGesture, true);
  } else {
    document.addEventListener("mousedown", handlePointerDown, true);
    document.addEventListener("mousemove", handlePointerMove, true);
    document.addEventListener("mouseup", handlePointerUp, true);
  }
  document.addEventListener("click", suppressActivatedClick, true);
  document.addEventListener("focusin", rememberPointerRequest, true);

  document.addEventListener("click", function (event) {
    if (popupEl && !popupEl.contains(event.target)) {
      hidePopup();
    }
  });

  window.addEventListener("resize", function () {
    hidePopup();
    hideNotice();
  });

  window.PronounceIt = {
    configure: configure,
    show: show,
    spoken: spoken,
    saved: saved,
    hide: hideAll,
    pronounceCurrent: pronounceCurrent,
    playText: playText,
    playContextTarget: playContextTarget,
    showContextDetails: showContextDetails,
    saveContextTarget: saveContextTarget,
  };

  if (window.PronounceItTestHooks) {
    window.PronounceItTestHooks.extractTermAtOffset = extractTermAtOffset;
    window.PronounceItTestHooks.extractTermSpanAtOffset = extractTermSpanAtOffset;
    window.PronounceItTestHooks.contextFromText = contextFromText;
    window.PronounceItTestHooks.termFromElement = termFromElement;
  }

  send("ready", {});
})();
