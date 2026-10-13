// Orchestrates the active site adapter: loads both subtitle tracks, machine-translates
// when the site has no track in the viewer's language, and draws the two lines over
// the video in sync with playback. When subtitles are generated from the tab's audio
// instead, lines arrive live from the background worker and are shown as they come.
(function () {
  'use strict';
  // Injected declaratively on supported sites and on demand (popup "Listen") elsewhere.
  if (globalThis.__dualSubsContent) return;
  globalThis.__dualSubsContent = true;

  const { cueAt, sameLang } = globalThis.DualSubs;
  // Sites without an adapter still get the overlay for audio-generated subtitles.
  const GENERIC = { name: location.hostname.replace(/^www\./, ''), init() {}, currentKey: () => null };
  const adapter = (globalThis.DualSubsAdapters || []).find((a) => a.match()) || GENERIC;

  const DEFAULTS = globalThis.DUALSUBS_DEFAULTS;
  const LIVE_MIN_SECONDS = 2.5;
  const LIVE_MAX_SECONDS = 7;

  let settings = Object.assign({}, DEFAULTS);
  let state = { status: 'idle', key: null, orig: null, mine: null, error: null, translating: false };
  let listen = { status: 'off', detail: '' }; // audio transcription state for this tab
  let resolving = null;
  let generation = 0;

  // ---------- page hook bridge ----------
  const hookListeners = {};
  window.addEventListener('message', (e) => {
    if (e.source !== window || !e.data || e.data.source !== 'dualsubs-hook') return;
    (hookListeners[e.data.type] || []).forEach((cb) => cb(e.data.payload));
  });

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const ctx = {
    sleep,
    onHook(type, cb) {
      (hookListeners[type] = hookListeners[type] || []).push(cb);
    },
    waitForHook(type, timeout) {
      return new Promise((resolve) => {
        const list = (hookListeners[type] = hookListeners[type] || []);
        const cb = (payload) => {
          list.splice(list.indexOf(cb), 1);
          clearTimeout(timer);
          resolve(payload);
        };
        const timer = setTimeout(() => {
          list.splice(list.indexOf(cb), 1);
          resolve(null);
        }, timeout);
        list.push(cb);
      });
    },
    sendToPage(type) {
      window.postMessage({ source: 'dualsubs-content', type }, location.origin);
    },
    // Subtitle CDNs: the background worker has host permission, but the player itself
    // fetches these files from the page, so the page origin is a good fallback.
    async fetchText(url) {
      let res = null;
      try {
        res = await chrome.runtime.sendMessage({ type: 'fetchText', url });
      } catch (e) {
        /* worker unavailable */
      }
      if (res && !res.error) return res.text;
      const direct = await fetch(url, { credentials: 'omit' });
      if (!direct.ok) throw new Error((res && res.error) || 'HTTP ' + direct.status);
      return direct.text();
    },
    async mapLimit(items, limit, fn) {
      const out = new Array(items.length);
      let next = 0;
      const worker = async () => {
        while (next < items.length) {
          const i = next++;
          out[i] = await fn(items[i], i);
        }
      };
      await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
      return out;
    },
  };
  adapter.init(ctx);
  ctx.sendToPage('replay');

  // ---------- settings ----------
  chrome.storage.sync.get(DEFAULTS, (s) => {
    settings = s;
    applyNativeCss();
  });
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'sync') return;
    const reload = ['myLang', 'origLang'].some((k) => k in changes);
    for (const k in changes) settings[k] = changes[k].newValue;
    applyNativeCss();
    renderStyle();
    if (reload && state.status !== 'live') state.key = null; // re-resolve on next tick
  });

  chrome.runtime.onMessage.addListener((msg, sender, reply) => {
    if (msg.type === 'status') {
      reply({
        site: adapter.name,
        supported: adapter !== GENERIC,
        status: state.status,
        error: state.error,
        orig: state.orig && { lang: state.orig.lang, label: state.orig.label },
        mine: state.mine && { lang: state.mine.lang, label: state.mine.label, machine: !!state.mine.machine },
        translating: state.translating,
        listen,
        hasVideo: !!findVideo(),
      });
    } else if (msg.type === 'ping') {
      reply({ ok: true });
    } else if (msg.type === 'listenState') {
      listen = { status: msg.status, detail: msg.detail || '' };
      if (msg.status === 'listening' || msg.status === 'loading') startLive();
      if (msg.status === 'off' || msg.status === 'error') stopLive();
    } else if (msg.type === 'transcript') {
      addLiveLine(msg.text, msg.lang);
    }
  });

  // ---------- loading site subtitles ----------
  function tick() {
    refreshVideo();
    if (!settings.enabled || state.status === 'live') return;
    const key = adapter.currentKey();
    if (!key || key === state.key || resolving || !video) return;

    const gen = ++generation;
    state = { status: 'loading', key, orig: null, mine: null, error: null, translating: false };
    resolving = adapter
      .resolve(ctx, settings)
      .then((r) => {
        if (gen !== generation) return;
        if (!r || r.error) {
          state.status = 'error';
          state.error = (r && r.error) || 'Could not load subtitles.';
          return;
        }
        state.orig = r.orig;
        state.mine = r.mine;
        state.status = 'ready';
        if (!state.mine && !sameLang(r.orig.lang, settings.myLang)) machineTranslate(gen);
      })
      .catch((e) => {
        if (gen !== generation) return;
        state.status = 'error';
        state.error = 'Could not load subtitles (' + e.message + ').';
      })
      .finally(() => {
        resolving = null;
      });
  }

  // Translate the original track in batches; lines appear as each batch returns.
  async function machineTranslate(gen) {
    const src = state.orig;
    const cues = src.cues.map((c) => ({ start: c.start, end: c.end, text: '' }));
    state.mine = { lang: settings.myLang, label: 'Machine translation', cues, machine: true };
    state.translating = true;
    const BATCH = 60;
    // Translate around the current playback position first.
    const now = video ? video.currentTime : 0;
    const order = [];
    for (let i = 0; i < cues.length; i += BATCH) order.push(i);
    order.sort((a, b) => Math.abs(cues[a].start - now) - Math.abs(cues[b].start - now));

    for (const i of order) {
      if (gen !== generation) return;
      const slice = src.cues.slice(i, i + BATCH).map((c) => c.text.replace(/\n/g, ' '));
      try {
        const res = await chrome.runtime.sendMessage({
          type: 'translate',
          texts: slice,
          source: src.lang,
          target: settings.myLang,
        });
        if (res && res.texts) res.texts.forEach((t, j) => (cues[i + j].text = t || ''));
      } catch (e) {
        /* leave this batch untranslated */
      }
    }
    state.translating = false;
  }

  // ---------- subtitles generated from the tab's audio ----------
  // Speech is transcribed a moment after it is spoken, so each line is shown from the
  // moment it arrives rather than at its (already passed) original time.
  function startLive() {
    if (state.status === 'live') return;
    generation++;
    state = {
      status: 'live',
      key: state.key,
      orig: { lang: settings.origLang !== 'auto' ? settings.origLang : '', label: 'From audio', cues: [] },
      mine: { lang: settings.myLang, label: 'Machine translation', cues: [], machine: true },
      error: null,
      translating: false,
    };
    applyNativeCss();
  }

  function stopLive() {
    if (state.status !== 'live') return;
    state = { status: 'idle', key: null, orig: null, mine: null, error: null, translating: false };
    applyNativeCss();
  }

  function liveNow() {
    return video ? video.currentTime : performance.now() / 1000;
  }

  function pushLive(cues, start, text) {
    const end = start + Math.min(LIVE_MAX_SECONDS, Math.max(LIVE_MIN_SECONDS, text.length / 15));
    // After seeking backwards, drop lines from the "future" so the list stays sorted.
    while (cues.length && cues[cues.length - 1].start >= start) cues.pop();
    const prev = cues[cues.length - 1];
    if (prev && prev.end > start) prev.end = start; // a new line replaces the previous one
    const cue = { start, end, text };
    cues.push(cue);
    return cue;
  }

  async function addLiveLine(text, lang) {
    if (!text) return;
    startLive();
    if (lang) state.orig.lang = lang;
    const gen = generation;
    const start = liveNow();
    pushLive(state.orig.cues, start, text);
    const mineCue = pushLive(state.mine.cues, start, '');
    if (state.orig.lang && sameLang(state.orig.lang, settings.myLang)) return;
    try {
      const res = await chrome.runtime.sendMessage({
        type: 'translate',
        texts: [text],
        source: state.orig.lang,
        target: settings.myLang,
      });
      if (gen !== generation || !res || !res.texts) return;
      if (res.detected && !state.orig.lang) state.orig.lang = res.detected;
      // Speech already in the viewer's language: show a single line.
      if (!sameLang(state.orig.lang || res.detected, settings.myLang)) mineCue.text = res.texts[0] || '';
    } catch (e) {
      /* translation unavailable: original line only */
    }
  }

  // ---------- rendering ----------
  let video = null;
  let host, lineTop, lineBottom;
  let lastTop = null;
  let lastBottom = null;

  // Some players (Disney+) keep their <video> inside shadow roots.
  function allVideos(root, out) {
    root.querySelectorAll('video').forEach((v) => out.push(v));
    root.querySelectorAll('*').forEach((el) => {
      if (el.shadowRoot) allVideos(el.shadowRoot, out);
    });
    return out;
  }

  function refreshVideo() {
    let list = Array.from(document.querySelectorAll('video'));
    if (!list.length) list = allVideos(document, []);
    let best = null;
    let bestArea = 0;
    for (const v of list) {
      const r = v.getBoundingClientRect();
      const area = r.width * r.height;
      if (area > bestArea && v.readyState > 0) {
        best = v;
        bestArea = area;
      }
    }
    video = best;
  }

  function findVideo() {
    if (!video || !video.isConnected) refreshVideo();
    return video;
  }

  // The overlay keeps its styles in its own shadow root so it renders the same wherever
  // it has to live (including inside a player's shadow DOM in fullscreen).
  const OVERLAY_CSS = `
    :host { all: initial; position: fixed; z-index: 2147483646; pointer-events: none; display: flex;
      flex-direction: column; justify-content: flex-end; align-items: center; gap: 0.25em;
      box-sizing: border-box; font-size: var(--dualsubs-size, 26px); }
    .line { max-width: 90%; padding: 0.1em 0.45em; border-radius: 0.2em; background: rgba(0, 0, 0, 0.72);
      color: #fff; font: 500 1em/1.3 system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", sans-serif;
      text-align: center; white-space: pre-line; text-shadow: 0 1px 2px rgba(0, 0, 0, 0.9);
      pointer-events: auto; user-select: text; }
    .mine { color: #ffe066; font-size: 0.92em; }
  `;

  function ensureOverlay() {
    if (!host) {
      host = document.createElement('dualsubs-overlay');
      const root = host.attachShadow({ mode: 'open' });
      const style = document.createElement('style');
      style.textContent = OVERLAY_CSS;
      lineTop = document.createElement('div');
      lineBottom = document.createElement('div');
      root.append(style, lineTop, lineBottom);
      renderStyle();
    }
    // Must live inside the fullscreen element or it disappears in fullscreen.
    const fs = document.fullscreenElement;
    const parent = fs ? fs.shadowRoot || fs : document.body;
    if (host.parentNode !== parent) parent.appendChild(host);
    return host;
  }

  function renderStyle() {
    if (!host) return;
    host.style.setProperty('--dualsubs-size', settings.fontSize + 'px');
    lineTop.className = 'line ' + (settings.origOnTop ? 'orig' : 'mine');
    lineBottom.className = 'line ' + (settings.origOnTop ? 'mine' : 'orig');
    lastTop = lastBottom = null;
  }

  function setLine(el, text, last) {
    if (text === last) return last;
    el.textContent = text || '';
    el.style.display = text ? '' : 'none';
    return text;
  }

  let nativeStyle, shadowStyle;
  function applyNativeCss() {
    if (!nativeStyle) {
      nativeStyle = document.createElement('style');
      (document.head || document.documentElement).appendChild(nativeStyle);
    }
    const ours = state.status === 'ready' || state.status === 'live';
    const hide = settings.enabled && settings.hideNative && ours && adapter.nativeCaptionSelector;
    const css = hide ? adapter.nativeCaptionSelector + '{display:none!important}' : '';
    nativeStyle.textContent = css;
    // Players that render inside shadow DOM (Disney+) need the rule in that root too.
    const root = video && video.getRootNode();
    if (root instanceof ShadowRoot) {
      if (!shadowStyle || shadowStyle.getRootNode() !== root) {
        shadowStyle = document.createElement('style');
        root.appendChild(shadowStyle);
      }
      shadowStyle.textContent = css;
    }
  }

  let lastStatus = null;
  function frame() {
    requestAnimationFrame(frame);
    if (state.status !== lastStatus) {
      lastStatus = state.status;
      applyNativeCss();
    }
    const show = settings.enabled && (state.status === 'ready' || state.status === 'live') && state.orig;
    const v = show && findVideo();
    if (!show || (!v && state.status !== 'live')) {
      if (host) host.style.display = 'none';
      return;
    }
    ensureOverlay();
    // Audio-only pages (no <video>) still get live lines along the bottom of the window.
    const r = v ? v.getBoundingClientRect() : { left: 0, top: 0, width: innerWidth, height: innerHeight };
    host.style.display = '';
    host.style.left = r.left + 'px';
    host.style.width = r.width + 'px';
    host.style.top = r.top + 'px';
    host.style.height = r.height + 'px';
    host.style.paddingBottom = (r.height * settings.bottom) / 100 + 'px';

    const live = state.status === 'live';
    const t = live ? liveNow() : v.currentTime - (Number(settings.offset) || 0);
    const o = cueAt(state.orig.cues, t);
    const m = state.mine ? cueAt(state.mine.cues, t) : null;
    const origText = o ? o.text : '';
    const mineText = m ? m.text : '';
    lastTop = setLine(lineTop, settings.origOnTop ? origText : mineText, lastTop);
    lastBottom = setLine(lineBottom, settings.origOnTop ? mineText : origText, lastBottom);
  }

  // Pick up an audio session that was already running when this page loaded.
  chrome.runtime
    .sendMessage({ type: 'listenStatus' })
    .then((s) => {
      if (s && s.status && s.status !== 'off') {
        listen = s;
        if (s.status === 'listening' || s.status === 'loading') startLive();
      }
    })
    .catch(() => {});

  setInterval(tick, 1000);
  requestAnimationFrame(frame);
})();
