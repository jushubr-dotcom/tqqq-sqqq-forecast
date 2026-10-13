// YouTube: caption tracks come from the player response. Since 2024 YouTube signs
// timedtext requests with a proof-of-origin token, so we let the player make one
// request (captions on), copy its token, and reuse it for both of our tracks.
// YouTube's own `tlang` parameter gives us the translation for free.
(function () {
  'use strict';
  const { sameLang } = globalThis.DualSubs;

  let signedUrl = null; // last timedtext URL the player requested

  function videoId() {
    if (location.pathname === '/watch') return new URLSearchParams(location.search).get('v');
    const m = location.pathname.match(/^\/(?:shorts|live|embed)\/([\w-]{6,})/);
    return m ? m[1] : null;
  }

  function signedFor(id) {
    if (!signedUrl) return null;
    try {
      const u = new URL(signedUrl);
      return u.searchParams.get('v') === id ? u : null;
    } catch (e) {
      return null;
    }
  }

  function buildUrl(track, id, tlang) {
    const u = new URL(track.baseUrl, location.origin);
    const signed = signedFor(id);
    if (signed) {
      for (const k of ['pot', 'potc', 'c', 'cver', 'cplayer', 'cos', 'cosver', 'cbr', 'cbrver']) {
        const v = signed.searchParams.get(k);
        if (v) u.searchParams.set(k, v);
      }
    }
    u.searchParams.set('fmt', 'json3');
    if (tlang) u.searchParams.set('tlang', tlang);
    else u.searchParams.delete('tlang');
    return u.href;
  }

  async function load(ctx, url) {
    const res = await fetch(url, { credentials: 'include' });
    const text = await res.text();
    if (!text.trim()) throw new Error('empty-caption-response');
    return globalThis.DualSubs.parseJson3(text);
  }

  async function getTracks(ctx, id) {
    for (let attempt = 0; attempt < 20; attempt++) {
      ctx.sendToPage('yt-get-tracks');
      const data = await ctx.waitForHook('yt-tracks', 1000);
      if (data && data.videoId === id) return data.tracks;
      await ctx.sleep(500);
    }
    return null;
  }

  async function ensureSigned(ctx, id) {
    if (signedFor(id)) return;
    ctx.sendToPage('yt-enable-captions');
    const deadline = Date.now() + 6000;
    while (!signedFor(id) && Date.now() < deadline) await ctx.sleep(200);
  }

  globalThis.DualSubsAdapters = (globalThis.DualSubsAdapters || []).concat({
    name: 'YouTube',
    match: () => /(^|\.)youtube\.com$/.test(location.hostname),
    nativeCaptionSelector: '.ytp-caption-window-container',

    init(ctx) {
      ctx.onHook('yt-timedtext-url', (url) => {
        signedUrl = url;
      });
    },

    currentKey: () => videoId(),

    async resolve(ctx, settings) {
      const id = videoId();
      const tracks = await getTracks(ctx, id);
      if (!tracks || !tracks.length) return { error: 'This video has no subtitles.' };

      // The auto-generated (ASR) track is in the spoken language, so it tells us the original.
      const asr = tracks.find((t) => t.asr);
      const origLang =
        settings.origLang && settings.origLang !== 'auto' ? settings.origLang : (asr || tracks[0]).lang;
      const orig =
        tracks.find((t) => !t.asr && sameLang(t.lang, origLang)) ||
        tracks.find((t) => sameLang(t.lang, origLang)) ||
        tracks[0];

      await ensureSigned(ctx, id);
      const origCues = await load(ctx, buildUrl(orig, id));
      const result = { key: id, orig: { lang: orig.lang, label: orig.label, cues: origCues }, mine: null };
      if (sameLang(orig.lang, settings.myLang)) return result;

      const own = tracks.find((t) => !t.asr && sameLang(t.lang, settings.myLang));
      try {
        if (own) {
          result.mine = { lang: own.lang, label: own.label, cues: await load(ctx, buildUrl(own, id)) };
        } else if (orig.translatable) {
          result.mine = {
            lang: settings.myLang,
            label: 'Auto-translated',
            cues: await load(ctx, buildUrl(orig, id, settings.myLang)),
          };
        }
      } catch (e) {
        // Fall through: the content script machine-translates the original track.
      }
      return result;
    },
  });
})();
