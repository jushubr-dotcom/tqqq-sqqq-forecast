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
  chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
    if (!tab) return;
    chrome.tabs.sendMessage(tab.id, { type: 'status' }, (st) => {
      if (chrome.runtime.lastError || !st) return;
      $('now').hidden = false;
      const t = $('now-text');
      if (st.status === 'ready') {
        const parts = [st.site + ': ' + nameOf(st.orig.lang)];
        if (st.mine) parts.push(nameOf(st.mine.lang) + (st.mine.machine ? ' (machine translated' + (st.translating ? ', in progress' : '') + ')' : ''));
        t.textContent = parts.join(' + ');
      } else if (st.status === 'loading') t.textContent = st.site + ': loading subtitles…';
      else if (st.status === 'error') t.textContent = st.site + ': ' + st.error;
      else t.textContent = st.site + ': start a video to see dual subtitles.';
    });
  });
})();
