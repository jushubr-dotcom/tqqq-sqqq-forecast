// Netflix: the page hook captures each title's manifest (and asks Netflix to include
// WebVTT downloads). Subtitle files live on Netflix's CDN, so they are fetched by the
// background worker, which has host permission and is not subject to page CORS.
(function () {
  'use strict';
  const { pickPair, parseAny } = globalThis.DualSubs;

  const manifests = new Map(); // movieId -> { tracks, originalLang }
  let latest = null;

  function watchId() {
    const m = location.pathname.match(/^\/watch\/(\d+)/);
    return m ? m[1] : null;
  }

  globalThis.DualSubsAdapters = (globalThis.DualSubsAdapters || []).concat({
    name: 'Netflix',
    match: () => /(^|\.)netflix\.com$/.test(location.hostname),
    nativeCaptionSelector: '.player-timedtext',

    init(ctx) {
      ctx.onHook('netflix-manifest', (m) => {
        manifests.set(m.movieId, m);
        latest = m;
      });
    },

    currentKey: () => watchId(),

    async resolve(ctx, settings) {
      const id = watchId();
      const deadline = Date.now() + 15000;
      while (!manifests.has(id) && Date.now() < deadline) await ctx.sleep(250);
      // Episode URLs sometimes differ from the manifest's movieId; fall back to the newest manifest.
      const manifest = manifests.get(id) || latest;
      if (!manifest || !manifest.tracks.length) {
        return { error: 'No subtitles found. Try reloading the page (Netflix must load after the extension).' };
      }

      const { orig, mine } = pickPair(manifest.tracks, {
        originalLang: manifest.originalLang,
        myLang: settings.myLang,
        origOverride: settings.origLang,
      });
      if (!orig) return { error: 'No subtitles found for this title.' };

      const [origText, mineText] = await Promise.all([
        ctx.fetchText(orig.url),
        mine ? ctx.fetchText(mine.url).catch(() => null) : null,
      ]);
      return {
        key: id,
        orig: { lang: orig.lang, label: orig.label, cues: parseAny(origText) },
        mine: mineText ? { lang: mine.lang, label: mine.label, cues: parseAny(mineText) } : null,
      };
    },
  });
})();
