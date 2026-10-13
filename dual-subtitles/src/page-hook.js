// Runs in the page's MAIN world at document_start. Streaming players fetch their
// subtitle metadata themselves; we watch those responses and forward what we need
// to the isolated content script via window.postMessage.
(function () {
  'use strict';
  if (window.__dualSubsHooked) return;
  window.__dualSubsHooked = true;

  const SOURCE = 'dualsubs-hook';
  const host = location.hostname;
  const isYouTube = /(^|\.)youtube\.com$/.test(host);
  const isNetflix = /(^|\.)netflix\.com$/.test(host);
  const isPrime = /(^|\.)(primevideo|amazon)\.[a-z.]+$/.test(host);
  const isDisney = /(^|\.)disneyplus\.com$/.test(host);

  // The content script loads at document_idle, after players may already have fetched
  // their metadata, so keep recent messages and replay them when it asks.
  const history = [];
  function post(type, payload) {
    try {
      window.postMessage({ source: SOURCE, type, payload }, location.origin);
    } catch (e) {
      /* payload not cloneable; ignore */
    }
  }
  function emit(type, payload) {
    history.push({ type, payload });
    if (history.length > 30) history.shift();
    post(type, payload);
  }

  function absolute(url) {
    try {
      return new URL(url, location.href).href;
    } catch (e) {
      return url;
    }
  }

  // ---------- request / response watching (fetch + XHR) ----------
  function onRequest(url) {
    if (isYouTube && url.includes('/api/timedtext')) emit('yt-timedtext-url', absolute(url));
  }

  // Which responses we want to read. Returns a handler for the body text, or null.
  function responseHandler(url) {
    if (isPrime && /PlaybackResources|playback\/prs/i.test(url)) {
      return (text) => {
        const subs = extractPrimeSubs(JSON.parse(text));
        if (subs) emit('prime-subs', subs);
      };
    }
    if (isNetflix && /manifest|licensedManifest|pbo_manifests|playapi/i.test(url)) {
      return (text) => {
        const json = JSON.parse(text);
        const result = json && (json.result || json);
        if (result && Array.isArray(result.timedtexttracks) && result.movieId) emit('netflix-manifest', extractNetflixSubs(result));
      };
    }
    if (isDisney && /\.m3u8(\?|$)/i.test(url)) {
      return (text) => {
        // Only master playlists list subtitle renditions.
        if (text.startsWith('#EXTM3U') && /TYPE=SUBTITLES/.test(text)) emit('hls-master', { url: absolute(url), text });
      };
    }
    if (isDisney && /bamgrid|disneyplus|dssott/i.test(url)) {
      return (text) => {
        const m = text.length < 3e6 && text.match(/"originalLanguage"\s*:\s*"([A-Za-z-]+)"/);
        if (m) emit('disney-original-lang', m[1]);
      };
    }
    return null;
  }

  function safely(fn, text) {
    try {
      fn(text);
    } catch (e) {
      /* not the shape we expected */
    }
  }

  const origFetch = window.fetch;
  window.fetch = function (input, init) {
    const url = absolute(typeof input === 'string' ? input : (input && input.url) || String(input));
    onRequest(url);
    const p = origFetch.apply(this, arguments);
    const handler = responseHandler(url);
    if (handler) p.then((res) => res.clone().text().then((t) => safely(handler, t))).catch(() => {});
    return p;
  };

  const origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    const abs = absolute(String(url));
    onRequest(abs);
    const handler = responseHandler(abs);
    if (handler) {
      this.addEventListener('load', () => {
        let text = null;
        try {
          const r = this.response;
          if (this.responseType === '' || this.responseType === 'text') text = this.responseText;
          else if (this.responseType === 'json') text = JSON.stringify(r);
          else if (r instanceof ArrayBuffer) text = new TextDecoder().decode(r);
        } catch (e) {
          /* unreadable */
        }
        if (text) safely(handler, text);
      });
    }
    return origOpen.apply(this, arguments);
  };

  // ---------- Prime Video ----------
  function extractPrimeSubs(json) {
    const list = [].concat(
      json.subtitleUrls || [],
      (json.timedTextUrls && json.timedTextUrls.result && json.timedTextUrls.result.subtitleUrls) || [],
      (json.playbackUrls && json.playbackUrls.subtitleUrls) || []
    );
    if (!list.length) return null;
    const tracks = list
      .filter((s) => s.url)
      .map((s) => ({
        lang: s.languageCode,
        label: s.displayName || s.languageCode,
        url: s.url,
        sdh: /sdh/i.test(s.type || '') || /\[cc\]|sdh/i.test(s.displayName || ''),
        forced: false,
      }));
    const audio = (json.audioTracks || (json.catalogMetadata && json.catalogMetadata.audioTracks) || []).find(
      (a) => a.isOriginalLanguage || a.audioTrackType === 'original'
    );
    return { tracks, originalLang: audio ? audio.languageCode : null };
  }

  // ---------- Netflix ----------
  // The player builds its manifest request with JSON.stringify and reads the reply
  // with JSON.parse. We ask for WebVTT subtitles too and capture the track list.
  if (isNetflix) {
    const origStringify = JSON.stringify;
    JSON.stringify = function (value) {
      try {
        const params = value && value.params;
        if (params && Array.isArray(params.profiles) && !params.profiles.includes('webvtt-lssdh-ios8')) {
          params.profiles.push('webvtt-lssdh-ios8');
          if (params.showAllSubDubTracks === false) params.showAllSubDubTracks = true;
        }
      } catch (e) {
        /* ignore */
      }
      return origStringify.apply(this, arguments);
    };

    const origParse = JSON.parse;
    JSON.parse = function () {
      const value = origParse.apply(this, arguments);
      try {
        const result = value && (value.result || value);
        if (result && Array.isArray(result.timedtexttracks) && result.movieId) {
          emit('netflix-manifest', extractNetflixSubs(result));
        }
      } catch (e) {
        /* ignore */
      }
      return value;
    };
  }

  function extractNetflixSubs(result) {
    const tracks = [];
    for (const t of result.timedtexttracks) {
      if (t.isNoneTrack || !t.ttDownloadables) continue;
      const profile = t.ttDownloadables['webvtt-lssdh-ios8'] ? 'webvtt-lssdh-ios8' : Object.keys(t.ttDownloadables)[0];
      const d = t.ttDownloadables[profile];
      if (!d) continue;
      let url = null;
      if (Array.isArray(d.urls) && d.urls.length) url = d.urls[0].url;
      else if (d.downloadUrls) url = Object.values(d.downloadUrls)[0];
      if (!url) continue;
      tracks.push({
        lang: t.language,
        label: t.languageDescription || t.language,
        url,
        sdh: t.rawTrackType === 'closedcaptions',
        forced: !!t.isForcedNarrative,
      });
    }
    const native = (result.audio_tracks || []).find((a) => a.isNative);
    return { movieId: String(result.movieId), tracks, originalLang: native ? native.language : null };
  }

  // ---------- YouTube ----------
  // The content script asks for the current video's caption track list.
  window.addEventListener('message', (e) => {
    if (e.source !== window || !e.data || e.data.source !== 'dualsubs-content') return;
    if (e.data.type === 'replay') {
      history.forEach((m) => post(m.type, m.payload));
    } else if (e.data.type === 'yt-get-tracks') {
      const player = document.getElementById('movie_player');
      let pr = null;
      try {
        pr = player && player.getPlayerResponse ? player.getPlayerResponse() : window.ytInitialPlayerResponse;
      } catch (err) {
        pr = window.ytInitialPlayerResponse;
      }
      const r = pr && pr.captions && pr.captions.playerCaptionsTracklistRenderer;
      post('yt-tracks', {
        videoId: pr && pr.videoDetails ? pr.videoDetails.videoId : null,
        tracks: r
          ? (r.captionTracks || []).map((t) => ({
              lang: t.languageCode,
              label: (t.name && (t.name.simpleText || (t.name.runs || []).map((x) => x.text).join(''))) || t.languageCode,
              baseUrl: t.baseUrl,
              asr: t.kind === 'asr',
              translatable: !!t.isTranslatable,
            }))
          : [],
      });
    } else if (e.data.type === 'yt-enable-captions') {
      // Turning captions on makes the player request a signed timedtext URL we can reuse.
      const player = document.getElementById('movie_player');
      try {
        if (player && player.toggleSubtitlesOn) player.toggleSubtitlesOn();
        else {
          const btn = document.querySelector('.ytp-subtitles-button[aria-pressed="false"]');
          if (btn) btn.click();
        }
      } catch (err) {
        /* ignore */
      }
    }
  });
})();
