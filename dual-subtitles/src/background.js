// Service worker: subscription status (ExtensionPay), cross-origin subtitle
// downloads, and machine translation for sites without a track in the viewer's language.
importScripts('vendor/ExtPay.js', 'config.js');

const extpay = ExtPay(CONFIG.extensionPayId);
extpay.startBackground();

const DAY = 24 * 60 * 60 * 1000;
const TRIAL_MS = CONFIG.trialDays * DAY;
// If ExtensionPay can't be reached, trust the last good answer for this long.
const OFFLINE_GRACE_MS = 3 * DAY;

async function getLicense() {
  try {
    const user = await extpay.getUser();
    const now = Date.now();
    const trialStart = user.trialStartedAt ? new Date(user.trialStartedAt).getTime() : null;
    const trialEndsAt = trialStart ? trialStart + TRIAL_MS : null;
    let status = 'none';
    if (user.paid) status = 'paid';
    else if (trialEndsAt && now < trialEndsAt) status = 'trial';
    else if (trialStart || user.paidAt) status = 'expired';

    const license = {
      status,
      active: status === 'paid' || status === 'trial',
      trialEndsAt,
      email: user.email || null,
      plan: user.plan || null,
      checkedAt: now,
    };
    await chrome.storage.local.set({ license });
    return license;
  } catch (e) {
    const { license } = await chrome.storage.local.get('license');
    if (license && Date.now() - license.checkedAt < OFFLINE_GRACE_MS) return Object.assign({}, license, { offline: true });
    return { status: 'unknown', active: false, offline: true, error: String(e && e.message) };
  }
}

async function notifyTabs() {
  const tabs = await chrome.tabs.query({});
  for (const tab of tabs) chrome.tabs.sendMessage(tab.id, { type: 'licenseChanged' }).catch(() => {});
}
extpay.onPaid.addListener(notifyTabs);
extpay.onTrialStarted.addListener(notifyTabs);

// ---------- translation ----------
async function translate(texts, source, target) {
  const { translateApiKey } = await chrome.storage.sync.get({ translateApiKey: '' });
  const key = translateApiKey || CONFIG.googleTranslateApiKey;
  if (key) return translateGoogleCloud(texts, source, target, key);
  return translateFree(texts, source, target);
}

// Google Cloud Translation v2 (paid, recommended for production).
async function translateGoogleCloud(texts, source, target, key) {
  const res = await fetch('https://translation.googleapis.com/language/translate/v2?key=' + encodeURIComponent(key), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ q: texts, source: source.split('-')[0], target, format: 'text' }),
  });
  if (!res.ok) throw new Error('translate ' + res.status);
  const json = await res.json();
  return json.data.translations.map((t) => t.translatedText);
}

// Keyless Google endpoint used by many browser tools. Fine for development;
// not an official API, so configure a key before selling the extension.
async function translateFree(texts, source, target) {
  const joined = texts.join('\n');
  const url =
    'https://translate.googleapis.com/translate_a/single?client=gtx&dt=t' +
    '&sl=' + encodeURIComponent(source ? source.split('-')[0] : 'auto') +
    '&tl=' + encodeURIComponent(target);
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'q=' + encodeURIComponent(joined),
  });
  if (!res.ok) throw new Error('translate ' + res.status);
  const json = await res.json();
  const out = (json[0] || []).map((seg) => seg[0] || '').join('').split('\n');
  if (out.length === texts.length) return out.map((s) => s.trim());
  // Line count drifted; fall back to one request per line.
  return Promise.all(texts.map((t) => (t ? translateFree([t], source, target).then((r) => r[0]) : '')));
}

// ---------- messages ----------
chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  const handlers = {
    license: () => getLicense(),
    openTrial: () => extpay.openTrialPage(CONFIG.trialDays === 30 ? '1-month' : CONFIG.trialDays + '-day'),
    openPayment: () => extpay.openPaymentPage(),
    openLogin: () => extpay.openLoginPage(),
    fetchText: async () => {
      const res = await fetch(msg.url);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return { text: await res.text() };
    },
    translate: async () => ({ texts: await translate(msg.texts, msg.source || '', msg.target) }),
  };
  const handler = handlers[msg.type];
  if (!handler) return false;
  Promise.resolve()
    .then(handler)
    .then((r) => reply(r === undefined ? { ok: true } : r))
    .catch((e) => reply({ error: String((e && e.message) || e) }));
  return true; // async reply
});

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') chrome.tabs.create({ url: chrome.runtime.getURL('welcome.html') });
});
