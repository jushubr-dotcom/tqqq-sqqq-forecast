// Popup settings. They save to chrome.storage.sync and
// open tabs pick them up live through storage.onChanged.
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);

  const nameOf = (code) => (DUALSUBS_LANGUAGES.find(([c]) => c === code) || [code, code])[1];

  for (const [code, name] of DUALSUBS_LANGUAGES) {
    $('myLang').add(new Option(name, code));
    $('origLang').add(new Option(name, code));
  }

  const formatters = {
    fontSize: (v) => v + 'px',
    bottom: (v) => v + '%',
    offset: (v) => (v > 0 ? '+' : '') + Number(v).toFixed(2) + 's',
  };

  chrome.storage.sync.get(DUALSUBS_DEFAULTS, (s) => {
    for (const key of Object.keys(DUALSUBS_DEFAULTS)) {
      const el = $(key);
      if (!el) continue;
      if (el.type === 'checkbox') el.checked = !!s[key];
      else el.value = s[key];
      if (formatters[key]) $(key + '-val').textContent = formatters[key](s[key]);
      el.addEventListener('input', () => {
        const value = el.type === 'checkbox' ? el.checked : el.type === 'range' ? Number(el.value) : el.value;
        if (formatters[key]) $(key + '-val').textContent = formatters[key](value);
        chrome.storage.sync.set({ [key]: value });
      });
    }
  });

  // ---------- what's happening on the current tab ----------
  let tabId = null;

  function describe(st) {
    const t = $('now-text');
    $('now').hidden = false;
    if (st.status === 'ready' || st.status === 'live') {
      const from = st.status === 'live' ? ' (from audio)' : '';
      const parts = [st.site + ': ' + (st.orig.lang ? nameOf(st.orig.lang) : 'detecting language…') + from];
      if (st.mine) parts.push(nameOf(st.mine.lang) + (st.mine.machine ? ' (machine translated' + (st.translating ? ', in progress' : '') + ')' : ''));
      t.textContent = parts.join(' + ');
    } else if (st.status === 'loading') t.textContent = st.site + ': loading subtitles…';
    else if (st.status === 'error') t.textContent = st.site + ': ' + st.error + ' Try "Listen to this tab".';
    else if (!st.supported) t.textContent = st.site + ': no built-in subtitle support here. Use "Listen to this tab".';
    else t.textContent = st.site + ': start a video to see dual subtitles.';
  }

  function showListen(l) {
    const mine = l && l.tabId === tabId;
    const active = mine && (l.status === 'loading' || l.status === 'listening');
    $('listen').textContent = active ? 'Stop listening' : 'Listen to this tab';
    $('listen').dataset.active = active ? '1' : '';
    const text = $('audio-text');
    if (mine && l.status === 'loading') text.textContent = l.detail || 'Loading speech model…';
    else if (mine && l.status === 'listening') text.textContent = 'Listening. Lines appear a moment after they are spoken.';
    else if (mine && l.status === 'error') text.textContent = l.detail || 'Something went wrong.';
    else text.textContent = 'Generate subtitles from whatever is playing in this tab, on any site.';
  }

  function refresh() {
    if (tabId == null) return;
    chrome.tabs.sendMessage(tabId, { type: 'status' }, (st) => {
      if (chrome.runtime.lastError || !st) return;
      describe(st);
    });
    chrome.runtime.sendMessage({ type: 'getListen' }).then(showListen).catch(() => {});
  }

  $('listen').onclick = async () => {
    $('listen').disabled = true;
    const res = await chrome.runtime.sendMessage({ type: $('listen').dataset.active ? 'stopListening' : 'startListening', tabId });
    $('listen').disabled = false;
    if (res && res.error) {
      $('audio-text').textContent = /not been invoked|cannot be captured|chrome:\/\//i.test(res.error)
        ? "This page can't be captured. Open the video's tab, click the extension icon there and try again."
        : 'Could not start: ' + res.error;
    }
    refresh();
  };

  chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
    if (!tab) return;
    tabId = tab.id;
    refresh();
    setInterval(refresh, 1000);
  });
})();
