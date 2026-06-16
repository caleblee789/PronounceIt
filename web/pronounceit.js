(function () {
  "use strict";

  const MESSAGE_PREFIX = "pronounceit:";
  const DEFAULT_CONFIG = {
    enabled: true,
    hotkey: "Mod+P",
    directClickModifier: "alt",
    popupClickModifier: "alt",
    allowOnQuestionSide: false,
    answerVisible: false,
    activationMode: "context_menu",
    theme: "system",
    showContextMenu: true,
    showSaveButton: true,
    unknownTermMessage: "Pronunciation unavailable",
  };
  const CONTEXT_LIMIT = 160;
  const SUPPORT_TOOLTIP = "If you're enjoying PronounceIt, consider buying me a coffee.";

  let config = Object.assign({}, DEFAULT_CONFIG, window.PronounceItConfig || {});
  let lastPayload = null;
  let pendingRequest = null;
  let lastPointerRequest = null;
  let lastPointerCaptureAt = 0;
  let directClickRequest = null;
  let lastDirectClickKey = "";
  let lastDirectClickAt = 0;
  let menuEl = null;
  let popupEl = null;

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
    const request = pendingRequest || selectedText({ allowCollapsed: true }) || lastPointerRequest;
    if (!request) {
      return;
    }
    pendingRequest = null;
    hideMenu();
    send("lookup", Object.assign({}, request, options || {}));
  }

  function requestAudioOnly(request) {
    if (!canPronounce() || !request) {
      return;
    }
    send("audioLookup", request);
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

  function rememberDirectClickRequest(event) {
    if (
      !canPronounce() ||
      isPronounceItElement(event && event.target) ||
      !isPrimaryClick(event) ||
      !modifierMatches(event, config.directClickModifier)
    ) {
      directClickRequest = null;
      return null;
    }
    directClickRequest = pointerRequest(event);
    if (directClickRequest) {
      lastPointerRequest = directClickRequest;
    }
    return directClickRequest;
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
    pendingRequest = selectedText({ allowCollapsed: true }) || lastPointerRequest;
    requestPronunciation();
  }

  function canPronounce() {
    return Boolean(config.enabled && (config.allowOnQuestionSide || config.answerVisible));
  }

  function hotkeyMatches(event) {
    const parts = String(config.hotkey || "Mod+P")
      .toLowerCase()
      .split("+")
      .map((part) => part.trim())
      .filter(Boolean);
    const key = parts[parts.length - 1];
    const wantsMod = parts.includes("mod");
    const wantsCtrl = parts.includes("ctrl") || parts.includes("control");
    const wantsMeta = parts.includes("cmd") || parts.includes("command") || parts.includes("meta");
    const wantsAlt = parts.includes("alt") || parts.includes("option");
    const wantsShift = parts.includes("shift");
    const modOk = wantsMod ? event.ctrlKey || event.metaKey : true;
    return (
      event.key.toLowerCase() === key &&
      modOk &&
      (!wantsCtrl || event.ctrlKey) &&
      (!wantsMeta || event.metaKey) &&
      (!wantsAlt || event.altKey) &&
      (!wantsShift || event.shiftKey)
    );
  }

  function modifierMatches(event, modifier) {
    const normalized = String(modifier || "").toLowerCase();
    if (!normalized || normalized === "disabled") {
      return false;
    }
    if (normalized === "alt" || normalized === "option") {
      return Boolean(event.altKey);
    }
    if (normalized === "shift") {
      return Boolean(event.shiftKey);
    }
    if (normalized === "meta" || normalized === "cmd" || normalized === "command") {
      return Boolean(event.metaKey);
    }
    if (normalized === "ctrl" || normalized === "control") {
      return Boolean(event.ctrlKey);
    }
    if (normalized === "mod") {
      return Boolean(event.ctrlKey || event.metaKey);
    }
    return false;
  }

  function isPrimaryClick(event) {
    return event.button === undefined || event.button === 0;
  }

  function requestMenu(event, request) {
    send("menu", Object.assign({}, request, {
      menuX: event.clientX,
      menuY: event.clientY,
    }));
  }

  function showMenu(payload) {
    hideMenu();
    lastPayload = payload;
    menuEl = document.createElement("div");
    applyTheme(menuEl, "pronounceit-menu");
    menuEl.setAttribute("role", "menu");

    const header = document.createElement("div");
    header.className = "pronounceit-menu-term";
    header.textContent = payload.term || payload.requestedText || "";
    menuEl.appendChild(header);

    const actionGroup = document.createElement("div");
    actionGroup.className = "pronounceit-menu-actions";
    menuEl.appendChild(actionGroup);

    const play = document.createElement("button");
    play.type = "button";
    play.className = "pronounceit-menu-command pronounceit-menu-primary";
    play.textContent = "Play pronunciation";
    play.setAttribute("role", "menuitem");
    play.addEventListener("click", function (event) {
      event.stopPropagation();
      playFromMenu(payload);
    });
    actionGroup.appendChild(play);

    if (config.showSaveButton && !payload.alreadySaved) {
      const save = document.createElement("button");
      save.type = "button";
      save.className = "pronounceit-menu-command pronounceit-menu-save";
      save.textContent = "Save pronunciation";
      save.setAttribute("role", "menuitem");
      save.addEventListener("click", function (event) {
        event.stopPropagation();
        saveFromMenu(payload);
      });
      actionGroup.appendChild(save);
    }

    const support = document.createElement("button");
    support.type = "button";
    support.className = "pronounceit-menu-support";
    support.textContent = "";
    support.title = SUPPORT_TOOLTIP;
    support.setAttribute("aria-label", SUPPORT_TOOLTIP);
    support.setAttribute("role", "menuitem");
    support.appendChild(coffeeIcon());
    support.addEventListener("click", function (event) {
      event.stopPropagation();
      send("support", {});
      hideMenu();
    });
    menuEl.appendChild(support);

    const status = document.createElement("div");
    status.className = "pronounceit-menu-status";
    status.setAttribute("data-empty", "true");
    menuEl.appendChild(status);

    document.body.appendChild(menuEl);
    placeElement(menuEl, Number(payload.menuX || 24), Number(payload.menuY || 24));

    if (payload.autoPlay) {
      playFromMenu(payload);
    }
  }

  function coffeeIcon() {
    const icon = document.createElement("span");
    icon.className = "pronounceit-coffee-icon";

    const lid = document.createElement("span");
    lid.className = "pronounceit-coffee-lid";
    icon.appendChild(lid);

    const cup = document.createElement("span");
    cup.className = "pronounceit-coffee-cup";
    icon.appendChild(cup);

    return icon;
  }

  function hideMenu() {
    if (menuEl) {
      menuEl.remove();
      menuEl = null;
    }
  }

  function playFromMenu(payload) {
    playResolvedPayload(payload, updateMenuStatus);
  }

  function saveFromMenu(payload) {
    send("save", payload);
  }

  function menuCanSave() {
    return Boolean(lastPayload && config.showSaveButton && !lastPayload.alreadySaved);
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

  function playResolvedPayload(payload, statusCallback) {
    const playback = playbackInfo(payload || {});
    if (!playback.audioAvailable) {
      return false;
    }
    if (typeof statusCallback === "function") {
      statusCallback("Playing...");
    }
    send("speak", {
      text: playback.playText,
      term: playback.word,
      audioFile: (payload && payload.audioFile) || "",
    });
    return true;
  }

  function updateMenuStatus(text) {
    if (!menuEl) {
      return;
    }
    const status = menuEl.querySelector(".pronounceit-menu-status");
    if (status) {
      status.textContent = text || "";
      status.setAttribute("data-empty", text ? "false" : "true");
    }
  }

  function hidePopup() {
    if (popupEl) {
      popupEl.remove();
      popupEl = null;
    }
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
    hideMenu();

    const playback = playbackInfo(payload);

    popupEl = document.createElement("div");
    applyTheme(popupEl, "pronounceit-popup");
    popupEl.setAttribute("role", "dialog");
    popupEl.setAttribute("aria-label", "Pronunciation");

    function playPayload() {
      playResolvedPayload(payload, updateStatus);
    }

    const card = createPronunciationCard({
      word: playback.word,
      pronunciation: payload.pronunciation || payload.audioStatus || payload.audioHelp || "Generated audio available",
      isCurated: Boolean(payload.found),
      source: sourceLabel(payload),
      onPlay: playPayload,
      audioAvailable: playback.audioAvailable,
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

    card.appendChild(header);
    card.appendChild(pronunciationBlock);
    card.appendChild(actions);

    return card;
  }

  function sourceLabel(payload) {
    if (payload.found) {
      return "Curated";
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
      updateMenuStatus("");
      return;
    }
    updateStatus("Could not play audio.");
    updateMenuStatus("Could not play audio.");
  }

  function saved(result) {
    if (result.alreadySaved) {
      lastPayload = Object.assign({}, lastPayload || {}, { alreadySaved: true });
      if (menuEl) {
        const save = menuEl.querySelector(".pronounceit-menu-save");
        if (save) {
          save.textContent = result.duplicate ? "Already saved" : "Saved";
          save.disabled = true;
          save.setAttribute("aria-disabled", "true");
          save.className = "pronounceit-menu-command pronounceit-menu-save pronounceit-menu-saved";
        }
      }
    }
    if (!popupEl) {
      return;
    }
    const status = popupEl.querySelector(".pronounceit-status");
    if (status) {
      status.textContent = result.duplicate ? "Already in your list." : "Saved.";
    }
  }

  function configure(nextConfig) {
    config = Object.assign({}, config, nextConfig || {});
    if (menuEl) {
      applyTheme(menuEl, "pronounceit-menu");
    }
    if (popupEl) {
      applyTheme(popupEl, "pronounceit-popup");
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

  function pronounceDirectClick(event) {
    if (
      !canPronounce() ||
      !isPrimaryClick(event) ||
      !modifierMatches(event, config.directClickModifier)
    ) {
      return;
    }
    const request = directClickRequest || rememberPointerRequest(event);
    if (!request) {
      return;
    }
    const key = directClickDedupKey(request);
    const now = Date.now();
    if (key === lastDirectClickKey && now - lastDirectClickAt < 350) {
      return;
    }
    lastDirectClickKey = key;
    lastDirectClickAt = now;
    event.preventDefault();
    requestAudioOnly(request);
    directClickRequest = null;
  }

  function directClickDedupKey(request) {
    return [
      request.text || "",
      request.contextText || "",
      request.contextOffsetStart || 0,
      request.contextOffsetEnd || 0,
    ].join("|");
  }

  document.addEventListener("keydown", function (event) {
    if (menuEl) {
      if (event.key === "Escape") {
        event.preventDefault();
        hideMenu();
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        playFromMenu(lastPayload || {});
        return;
      }
      if ((event.key === "s" || event.key === "S") && menuCanSave()) {
        event.preventDefault();
        saveFromMenu(lastPayload);
        return;
      }
    }
    if (popupEl && event.key === "Escape") {
      event.preventDefault();
      hidePopup();
      return;
    }
    if (!canPronounce() || !hotkeyMatches(event)) {
      return;
    }
    pendingRequest = selectedText({ allowCollapsed: true }) || lastPointerRequest;
    if (!pendingRequest) {
      return;
    }
    event.preventDefault();
    requestPronunciation();
  });

  document.addEventListener("contextmenu", function (event) {
    if (
      !canPronounce() ||
      isPronounceItElement(event && event.target) ||
      !modifierMatches(event, config.popupClickModifier)
    ) {
      return;
    }
    pendingRequest = rememberPointerRequest(event);
    if (!pendingRequest) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    hideMenu();
    requestMenu(event, pendingRequest);
  }, true);

  document.addEventListener("click", rememberPointerRequest, true);
  document.addEventListener("click", pronounceDirectClick, true);
  document.addEventListener("mousedown", rememberDirectClickRequest, true);
  document.addEventListener("mousedown", rememberPointerRequest, true);
  document.addEventListener("mouseup", rememberPointerRequest, true);
  document.addEventListener("mouseup", pronounceDirectClick, true);
  document.addEventListener("pointerdown", rememberDirectClickRequest, true);
  document.addEventListener("pointerdown", rememberPointerRequest, true);
  document.addEventListener("pointerup", rememberPointerRequest, true);
  document.addEventListener("pointerup", pronounceDirectClick, true);
  document.addEventListener("pointermove", rememberPointerRequestThrottled, true);
  document.addEventListener("mousemove", rememberPointerRequestThrottled, true);
  document.addEventListener("focusin", rememberPointerRequest, true);

  document.addEventListener("click", function (event) {
    if (menuEl && !menuEl.contains(event.target)) {
      hideMenu();
    }
    if (popupEl && !popupEl.contains(event.target)) {
      hidePopup();
    }
  });

  window.addEventListener("resize", function () {
    hideMenu();
    hidePopup();
  });

  window.PronounceIt = {
    configure: configure,
    show: show,
    showMenu: showMenu,
    spoken: spoken,
    saved: saved,
    hide: hidePopup,
    pronounceCurrent: pronounceCurrent,
  };

  if (window.PronounceItTestHooks) {
    window.PronounceItTestHooks.extractTermAtOffset = extractTermAtOffset;
    window.PronounceItTestHooks.extractTermSpanAtOffset = extractTermSpanAtOffset;
    window.PronounceItTestHooks.contextFromText = contextFromText;
    window.PronounceItTestHooks.termFromElement = termFromElement;
  }

  send("ready", {});
})();
