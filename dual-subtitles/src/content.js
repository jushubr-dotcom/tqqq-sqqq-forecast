// Orchestrates the active site adapter: loads both subtitle
// tracks, machine-translates when the site has no track in the viewer's language,
// and draws the two lines over the video in sync with playback.
(function () {
  'use strict';
  const { cueAt, sameLang } = globalThis.DualSubs;
  const adapter = (globalThis.DualSubsAdapters || []).find((a) => a.match());
  if (!adapter) return;

  const DEFAULTS = globalThis.DUALSUBS_DEFAULTS;

  let settings = Object.assign({}, DEFAULTS);
  let state = { status: 'idle', key: null, orig: null, mine: null, error: null, translating: false };
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
    async fetchText(url) {
      const res = await chrome.runtime.sendMessage({ type: 'fetchText', url });
      if (!res || res.error) throw new Error((res && res.error) || 'fetch failed');
      return res.text;
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
    if (reload) state.key = null; // re-resolve on next tick
  });

  chrome.runtime.onMessage.addListener((msg, sender, reply) => {
    if (msg.type === 'status') {
      reply({
        site: adapter.name,
        status: state.status,
        error: state.error,
        orig: state.orig && { lang: state.orig.lang, label: state.orig.label },
        mine: state.mine && { lang: state.mine.lang, label: state.mine.label, machine: !!state.mine.machine },
        translating: state.translating,
      });
    }
  });

  // ---------- loading ----------
  function tick() {
    if (!settings.enabled) return;
    const key = adapter.currentKey();
    if (!key || key === state.key || resolving || !findVideo()) return;

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
    const video = findVideo();
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

  // ---------- rendering ----------
  let overlay, lineTop, lineBottom;
  let lastTop = null;
  let lastBottom = null;

  function findVideo() {
    let best = null;
    let bestArea = 0;
    for (const v of document.querySelectorAll('video')) {
      const r = v.getBoundingClientRect();
      const area = r.width * r.height;
      if (area > bestArea && v.readyState > 0) {
        best = v;
        bestArea = area;
      }
    }
    return best;
  }

  function ensureOverlay() {
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.className = 'dualsubs-overlay';
      lineTop = document.createElement('div');
      lineBottom = document.createElement('div');
      overlay.append(lineTop, lineBottom);
      renderStyle();
    }
    // Must live inside the fullscreen element or it disappears in fullscreen.
    const parent = document.fullscreenElement || document.body;
    if (overlay.parentNode !== parent) parent.appendChild(overlay);
    return overlay;
  }

  function renderStyle() {
    if (!overlay) return;
    overlay.style.setProperty('--dualsubs-size', settings.fontSize + 'px');
    lineTop.className = 'dualsubs-line ' + (settings.origOnTop ? 'dualsubs-orig' : 'dualsubs-mine');
    lineBottom.className = 'dualsubs-line ' + (settings.origOnTop ? 'dualsubs-mine' : 'dualsubs-orig');
    lastTop = lastBottom = null;
  }

  function setLine(el, text, last) {
    if (text === last) return last;
    el.textContent = text || '';
    el.style.display = text ? '' : 'none';
    return text;
  }

  let nativeStyle;
  function applyNativeCss() {
    if (!nativeStyle) {
      nativeStyle = document.createElement('style');
      (document.head || document.documentElement).appendChild(nativeStyle);
    }
    const hide = settings.enabled && settings.hideNative && adapter.nativeCaptionSelector;
    nativeStyle.textContent = hide ? adapter.nativeCaptionSelector + '{display:none!important}' : '';
  }

  function frame() {
    requestAnimationFrame(frame);
    const show = settings.enabled && state.status === 'ready' && state.orig;
    const video = show && findVideo();
    if (!video) {
      if (overlay) overlay.style.display = 'none';
      return;
    }
    ensureOverlay();
    const r = video.getBoundingClientRect();
    overlay.style.display = '';
    overlay.style.left = r.left + 'px';
    overlay.style.width = r.width + 'px';
    overlay.style.top = r.top + 'px';
    overlay.style.height = r.height + 'px';
    overlay.style.paddingBottom = (r.height * settings.bottom) / 100 + 'px';

    const t = video.currentTime - (Number(settings.offset) || 0);
    const o = cueAt(state.orig.cues, t);
    const m = state.mine ? cueAt(state.mine.cues, t) : null;
    const origText = o ? o.text : '';
    const mineText = m ? m.text : '';
    lastTop = setLine(lineTop, settings.origOnTop ? origText : mineText, lastTop);
    lastBottom = setLine(lineBottom, settings.origOnTop ? mineText : origText, lastBottom);
  }

  setInterval(tick, 1000);
  requestAnimationFrame(frame);
})();
