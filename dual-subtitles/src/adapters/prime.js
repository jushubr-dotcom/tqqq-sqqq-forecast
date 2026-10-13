// Prime Video (primevideo.com and amazon.* /gp/video): the page hook captures the
// GetPlaybackResources response, which lists TTML subtitle URLs per language.
(function () {
  'use strict';
  const { pickPair, parseAny } = globalThis.DualSubs;

  let current = null;
  let seq = 0;

  globalThis.DualSubsAdapters = (globalThis.DualSubsAdapters || []).concat({
    name: 'Prime Video',
    match: () => /(^|\.)(primevideo|amazon)\.[a-z.]+$/.test(location.hostname),
    nativeCaptionSelector: '.atvwebplayersdk-captions-overlay',

    init(ctx) {
      ctx.onHook('prime-subs', (data) => {
        // Ignore duplicate responses for the same title.
        const sig = data.tracks.map((t) => t.url).join('|');
        if (current && current.sig === sig) return;
        current = Object.assign({ sig }, data);
        seq++;
      });
    },

    // The player opens over the detail page without a URL change, so a new
    // playback-resources response is what marks a new title.
    currentKey: () => (current ? 'prime-' + seq : null),

    async resolve(ctx, settings) {
      const data = current;
      const { orig, mine } = pickPair(data.tracks, {
        originalLang: data.originalLang,
        myLang: settings.myLang,
        origOverride: settings.origLang,
      });
      if (!orig) return { error: 'No subtitles found for this title.' };

      const [origText, mineText] = await Promise.all([
        ctx.fetchText(orig.url),
        mine ? ctx.fetchText(mine.url).catch(() => null) : null,
      ]);
      return {
        key: 'prime-' + seq,
        orig: { lang: orig.lang, label: orig.label, cues: parseAny(origText) },
        mine: mineText ? { lang: mine.lang, label: mine.label, cues: parseAny(mineText) } : null,
      };
    },
  });
})();
