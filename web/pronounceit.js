(function () {
  "use strict";

  const MESSAGE_PREFIX = "pronounceit:";
  const DEFAULT_CONFIG = {
    enabled: true,
    hotkey: "Mod+P",
    allowOnQuestionSide: false,
    answerVisible: false,
    showContextMenu: true,
    showSaveButton: true,
    unknownTermMessage: "Pronunciation unavailable",
  };

  let config = Object.assign({}, DEFAULT_CONFIG, window.PronounceItConfig || {});
  let lastPayload = null;
  let pendingRequest = null;
  let lastPointerRequest = null;
  let lastPointerCaptureAt = 0;
  let menuEl = null;
  let popupEl = null;

  function send(action, payload) {
    if (typeof pycmd !== "function") {
      return;
    }
    pycmd(MESSAGE_PREFIX + action + ":" + JSON.stringify(payload || {}));
  }

  function selectedText() {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) {
      return null;
    }
    const text = selection.toString().trim();
    if (!text) {
      return null;
    }
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    return {
      text: text,
      rect: {
        left: rect.left,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
        width: rect.width,
        height: rect.height,
      },
    };
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
    const word = extractTermAtOffset(text, range.startOffset);
    if (!word) {
      return null;
    }

    const rect = range.getBoundingClientRect();
    return {
      text: word,
      rect: {
        left: rect.left || x,
        top: rect.top || y,
        right: rect.right || x,
        bottom: rect.bottom || y,
        width: rect.width || 1,
        height: rect.height || 1,
      },
    };
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
    return String(text || "").replace(/\u00a0/g, " ").trim().replace(/\s+/g, " ");
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
    return {
      text: text,
      rect: {
        left: rect.left || 0,
        top: rect.top || 0,
        right: rect.right || rect.left || 0,
        bottom: rect.bottom || rect.top || 0,
        width: rect.width || 1,
        height: rect.height || 1,
      },
    };
  }

  function extractTermAtOffset(text, offset) {
    const safeOffset = Math.max(0, Math.min(offset, text.length));
    const left = text.slice(0, safeOffset);
    const right = text.slice(safeOffset);
    const leftMatch = left.match(/[A-Za-z0-9'\u2010-\u2015-]+$/);
    const rightMatch = right.match(/^[A-Za-z0-9'\u2010-\u2015-]+/);
    const word = ((leftMatch && leftMatch[0]) || "") + ((rightMatch && rightMatch[0]) || "");
    return /[A-Za-z]/.test(word) ? word : null;
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
    const request = pendingRequest || selectedText() || lastPointerRequest;
    if (!request) {
      return;
    }
    pendingRequest = null;
    hideMenu();
    send("lookup", Object.assign({}, request, options || {}));
  }

  function rememberPointerRequest(event) {
    const request =
      selectedText() ||
      termFromElement(event.target) ||
      wordAtPoint(event.clientX, event.clientY);
    if (request) {
      lastPointerRequest = request;
    }
    return request;
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
    pendingRequest = selectedText() || lastPointerRequest;
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
    menuEl.className = "pronounceit-menu";
    const play = document.createElement("button");
    play.type = "button";
    play.textContent = "Play";
    play.addEventListener("click", function (event) {
      event.stopPropagation();
      show(Object.assign({}, payload, { autoPlay: true }));
    });
    menuEl.appendChild(play);

    if (config.showSaveButton && !payload.alreadySaved) {
      const save = document.createElement("button");
      save.type = "button";
      save.textContent = "Add to pronunciation list";
      save.addEventListener("click", function (event) {
        event.stopPropagation();
        show(Object.assign({}, payload, { saveAfterLookup: true }));
      });
      menuEl.appendChild(save);
    }

    document.body.appendChild(menuEl);
    placeElement(menuEl, Number(payload.menuX || 24), Number(payload.menuY || 24));
  }

  function hideMenu() {
    if (menuEl) {
      menuEl.remove();
      menuEl = null;
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

    popupEl = document.createElement("div");
    popupEl.className = "pronounceit-popup";
    popupEl.setAttribute("role", "dialog");
    popupEl.setAttribute("aria-label", "Pronunciation");

    const term = document.createElement("div");
    term.className = "pronounceit-term";
    term.textContent = payload.term || payload.requestedText || "";

    const pronunciation = document.createElement("div");
    pronunciation.className = payload.found ? "pronounceit-pronunciation" : "pronounceit-pronunciation generated";
    pronunciation.textContent = payload.pronunciation || payload.audioStatus || "Generated audio available";

    const syllables = document.createElement("div");
    syllables.className = "pronounceit-syllables";
    syllables.textContent = payload.syllables ? "Syllables: " + payload.syllables : (payload.audioHelp || "Play creates or reuses local audio when possible.");

    const actions = document.createElement("div");
    actions.className = "pronounceit-actions";

    const play = document.createElement("button");
    play.type = "button";
    play.className = "pronounceit-icon-button";
    play.title = "Play pronunciation";
    play.setAttribute("aria-label", "Play pronunciation");
    play.textContent = "Play";
    function playPayload() {
      send("speak", {
        text: payload.speechText || payload.term || payload.requestedText || "",
        term: payload.term || payload.requestedText || "",
        audioFile: payload.audioFile || "",
      });
    }

    play.addEventListener("click", playPayload);
    actions.appendChild(play);

    if (config.showSaveButton && !payload.alreadySaved) {
      const save = document.createElement("button");
      save.type = "button";
      save.className = "pronounceit-save";
      save.textContent = "Add to pronunciation list";
      save.addEventListener("click", function () {
        send("save", lastPayload || payload);
      });
      actions.appendChild(save);
    }

    const status = document.createElement("div");
    status.className = "pronounceit-status";

    popupEl.appendChild(term);
    popupEl.appendChild(pronunciation);
    popupEl.appendChild(syllables);
    popupEl.appendChild(actions);
    popupEl.appendChild(status);
    document.body.appendChild(popupEl);

    const rect = payload.rect || {};
    placeElement(popupEl, Number(rect.left || 24), Number(rect.bottom || 24) + 8);

    if (payload.autoPlay) {
      playPayload();
    }
    if (payload.saveAfterLookup && !payload.alreadySaved) {
      send("save", lastPayload || payload);
    }
  }

  function saved(result) {
    if (!popupEl) {
      return;
    }
    const status = popupEl.querySelector(".pronounceit-status");
    if (!status) {
      return;
    }
    status.textContent = result.duplicate ? "Already in your list." : "Saved.";
    if (result.alreadySaved) {
      lastPayload = Object.assign({}, lastPayload || {}, { alreadySaved: true });
      const save = popupEl.querySelector(".pronounceit-save");
      if (save) {
        save.remove();
      }
    }
  }

  function configure(nextConfig) {
    config = Object.assign({}, config, nextConfig || {});
  }

  document.addEventListener("keydown", function (event) {
    if (!canPronounce() || !hotkeyMatches(event)) {
      return;
    }
    pendingRequest = selectedText() || lastPointerRequest;
    if (!pendingRequest) {
      return;
    }
    event.preventDefault();
    requestPronunciation();
  });

  document.addEventListener("contextmenu", function (event) {
    if (!canPronounce() || !config.showContextMenu) {
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
  document.addEventListener("mousedown", rememberPointerRequest, true);
  document.addEventListener("mouseup", rememberPointerRequest, true);
  document.addEventListener("pointerdown", rememberPointerRequest, true);
  document.addEventListener("pointerup", rememberPointerRequest, true);
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
    saved: saved,
    hide: hidePopup,
    pronounceCurrent: pronounceCurrent,
  };

  if (window.PronounceItTestHooks) {
    window.PronounceItTestHooks.extractTermAtOffset = extractTermAtOffset;
    window.PronounceItTestHooks.termFromElement = termFromElement;
  }

  send("ready", {});
})();
