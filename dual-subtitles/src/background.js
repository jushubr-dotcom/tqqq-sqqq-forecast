// Service worker: cross-origin subtitle downloads, machine translation for sites
// without a track in the viewer's language, and the "listen to the audio" session
// (tab capture handed to the offscreen document, which runs speech recognition).
importScripts('config.js');

// ---------- translation ----------
async function translate(texts, source, target) {
  const { translateApiKey } = await chrome.storage.sync.get({ translateApiKey: '' });
  const key = translateApiKey || CONFIG.googleTranslateApiKey;
  if (key) return translateGoogleCloud(texts, source, target, key);
  return translateFree(texts, source, target);
}

function baseCode(lang) {
  return lang ? lang.split('-')[0] : '';
}

// Google Cloud Translation v2 (paid, recommended for production).
async function translateGoogleCloud(texts, source, target, key) {
  const res = await fetch('https://translation.googleapis.com/language/translate/v2?key=' + encodeURIComponent(key), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(Object.assign({ q: texts, target, format: 'text' }, source ? { source: baseCode(source) } : {})),
  });
  if (!res.ok) throw new Error('translate ' + res.status);
  const json = await res.json();
  const list = json.data.translations;
  return { texts: list.map((t) => t.translatedText), detected: source || (list[0] && list[0].detectedSourceLanguage) || '' };
}

// Keyless Google endpoint used by many browser tools. Fine for development;
// not an official API, so configure a key before publishing widely.
async function translateFree(texts, source, target) {
  const joined = texts.join('\n');
  const url =
    'https://translate.googleapis.com/translate_a/single?client=gtx&dt=t' +
    '&sl=' + encodeURIComponent(baseCode(source) || 'auto') +
    '&tl=' + encodeURIComponent(target);
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'q=' + encodeURIComponent(joined),
  });
  if (!res.ok) throw new Error('translate ' + res.status);
  const json = await res.json();
  const out = (json[0] || []).map((seg) => seg[0] || '').join('').split('\n');
  const detected = source || (typeof json[2] === 'string' ? json[2] : '');
  if (out.length === texts.length) return { texts: out.map((s) => s.trim()), detected };
  // Line count drifted; fall back to one request per line.
  const each = await Promise.all(texts.map((t) => (t ? translateFree([t], source, target).then((r) => r.texts[0]) : '')));
  return { texts: each, detected };
}

// ---------- messages ----------
chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  const handlers = {
    fetchText: async () => {
      const res = await fetch(msg.url);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return { text: await res.text() };
    },
    translate: () => translate(msg.texts, msg.source || '', msg.target),
    startListening: () => startListening(msg.tabId),
    stopListening: () => stopListening(),
    getListen: () => getListen(),
    // A content script asking whether its tab is being listened to.
    listenStatus: async () => {
      const l = await getListen();
      return sender.tab && l.tabId === sender.tab.id ? l : { status: 'off' };
    },
    'asr-status': () => setListen(msg.tabId, msg.status, msg.detail),
    'asr-transcript': () => chrome.tabs.sendMessage(msg.tabId, { type: 'transcript', text: msg.text, lang: msg.lang }).catch(() => {}),
  };
  if (msg.target === 'offscreen') return false;
  const handler = handlers[msg.type];
  if (!handler) return false;
  Promise.resolve()
    .then(handler)
    .then((r) => reply(r === undefined ? { ok: true } : r))
    .catch((e) => reply({ error: String((e && e.message) || e) }));
  return true; // async reply
});

// ---------- listening to the tab's audio ----------
const CONTENT_FILES = [
  'lib/subs.js',
  'lib/settings.js',
  'adapters/youtube.js',
  'adapters/netflix.js',
  'adapters/prime.js',
  'adapters/disney.js',
  'content.js',
];

async function getListen() {
  const { listen } = await chrome.storage.session.get('listen');
  return listen || { tabId: null, status: 'off', detail: '' };
}

async function setListen(tabId, status, detail) {
  const listen = status === 'off' ? { tabId: null, status, detail: '' } : { tabId, status, detail: detail || '' };
  await chrome.storage.session.set({ listen });
  if (tabId != null) chrome.tabs.sendMessage(tabId, { type: 'listenState', status, detail: detail || '' }).catch(() => {});
}

// Sites without an adapter don't have the content script yet; inject it on demand.
async function ensureContentScript(tabId) {
  try {
    if (await chrome.tabs.sendMessage(tabId, { type: 'ping' })) return;
  } catch (e) {
    /* not injected */
  }
  await chrome.scripting.executeScript({ target: { tabId }, files: CONTENT_FILES });
}

async function ensureOffscreen() {
  const existing = await chrome.runtime.getContexts({ contextTypes: ['OFFSCREEN_DOCUMENT'] });
  if (existing.length) return;
  await chrome.offscreen.createDocument({
    url: 'offscreen.html',
    reasons: ['USER_MEDIA', 'AUDIO_PLAYBACK'],
    justification: 'Transcribes the audio playing in the tab to generate subtitles.',
  });
}

// Must run right after the user invoked the extension on this tab (popup or shortcut);
// Chrome only allows tab capture then.
async function startListening(tabId) {
  const current = await getListen();
  if (current.tabId != null && current.tabId !== tabId) await stopListening();
  const streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tabId });
  await ensureContentScript(tabId);
  await ensureOffscreen();
  const s = await chrome.storage.sync.get({ asrModel: 'base', origLang: 'auto', asrModelId: '', asrModelHost: '' });
  await setListen(tabId, 'loading', 'Starting…');
  await chrome.runtime.sendMessage({
    target: 'offscreen',
    type: 'start',
    streamId,
    tabId,
    options: { model: s.asrModel, language: s.origLang, modelId: s.asrModelId, modelHost: s.asrModelHost },
  });
  return { ok: true };
}

async function stopListening() {
  const current = await getListen();
  try {
    await chrome.runtime.sendMessage({ target: 'offscreen', type: 'stop' });
  } catch (e) {
    /* no offscreen document */
  }
  await setListen(current.tabId, 'off');
  return { ok: true };
}

chrome.commands.onCommand.addListener(async (command, tab) => {
  if (command !== 'toggle-listen' || !tab) return;
  const current = await getListen();
  if (current.tabId === tab.id && current.status !== 'error') stopListening();
  else startListening(tab.id).catch((e) => setListen(tab.id, 'error', String(e.message || e)));
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  if ((await getListen()).tabId === tabId) stopListening();
});

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') chrome.tabs.create({ url: chrome.runtime.getURL('welcome.html') });
});
