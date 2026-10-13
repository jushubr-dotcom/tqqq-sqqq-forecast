// Disney+: the player streams HLS. The page hook captures the master playlist, which
// lists one subtitle rendition per language; each rendition is a media playlist of
// short WebVTT segments that we download and join.
(function () {
  'use strict';
  const { pickPair, parseM3u8Master, parseM3u8Media, parseVtt, mergeCues } = globalThis.DualSubs;

  let master = null; // { url, text }
  let seq = 0;
  let originalLang = null;

  const onPlayer = () => /^\/([a-z]{2}(-[a-z]{2})?\/)?(video|play)\//i.test(location.pathname);

  async function loadRendition(ctx, track) {
    const playlist = await ctx.fetchText(track.url);
    const segments = parseM3u8Media(playlist, track.url);
    const lists = await ctx.mapLimit(segments, 6, async (url) => {
      try {
        return parseVtt(await ctx.fetchText(url));
      } catch (e) {
        return [];
      }
    });
    return mergeCues(lists);
  }

  globalThis.DualSubsAdapters = (globalThis.DualSubsAdapters || []).concat({
    name: 'Disney+',
    match: () => /(^|\.)disneyplus\.com$/.test(location.hostname),
    nativeCaptionSelector: '.dss-subtitle-renderer-wrapper, .dss-subtitle-renderer-cue-window, .hive-subtitle-renderer-wrapper',

    init(ctx) {
      ctx.onHook('hls-master', (m) => {
        if (master && master.url === m.url) return;
        master = m;
        seq++;
      });
      ctx.onHook('disney-original-lang', (lang) => {
        originalLang = lang;
      });
    },

    currentKey: () => (onPlayer() && master ? location.pathname + '#' + seq : null),

    async resolve(ctx, settings) {
      const { subtitles, audio } = parseM3u8Master(master.text, master.url);
      if (!subtitles.length) return { error: 'No subtitles found for this title.' };
      const origAudio = audio.find((a) => a.original);
      const { orig, mine } = pickPair(subtitles, {
        originalLang: originalLang || (origAudio && origAudio.lang),
        myLang: settings.myLang,
        origOverride: settings.origLang,
      });
      if (!orig) return { error: 'No subtitles found for this title.' };

      const [origCues, mineCues] = await Promise.all([
        loadRendition(ctx, orig),
        mine ? loadRendition(ctx, mine).catch(() => null) : null,
      ]);
      return {
        key: location.pathname + '#' + seq,
        orig: { lang: orig.lang, label: orig.label, cues: origCues },
        mine: mineCues && mineCues.length ? { lang: mine.lang, label: mine.label, cues: mineCues } : null,
      };
    },
  });
})();
