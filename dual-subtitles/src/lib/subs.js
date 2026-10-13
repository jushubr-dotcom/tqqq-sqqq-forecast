// Subtitle parsing and lookup helpers shared by every streaming-site adapter.
// A cue is { start, end, text } with times in seconds. Loaded as a classic
// content script (attaches to globalThis.DualSubs) and as a CommonJS module in tests.
(function (root) {
  'use strict';

  const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' };

  function decodeEntities(s) {
    return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e) => {
      if (e[0] === '#') {
        const code = e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
        return Number.isFinite(code) ? String.fromCodePoint(code) : m;
      }
      return ENTITIES[e.toLowerCase()] ?? m;
    });
  }

  function cleanText(s) {
    return s
      .split('\n')
      .map((l) => l.replace(/[ \t]+/g, ' ').trim())
      .filter(Boolean)
      .join('\n');
  }

  function finalize(cues) {
    return cues
      .filter((c) => c.text && Number.isFinite(c.start) && Number.isFinite(c.end) && c.end > c.start)
      .sort((a, b) => a.start - b.start);
  }

  // YouTube "json3" timedtext format.
  function parseJson3(data) {
    const json = typeof data === 'string' ? JSON.parse(data) : data;
    const cues = [];
    for (const ev of json.events || []) {
      if (!ev.segs) continue;
      const text = cleanText(ev.segs.map((s) => s.utf8 || '').join(''));
      if (!text) continue;
      const start = (ev.tStartMs || 0) / 1000;
      cues.push({ start, end: start + (ev.dDurationMs || 0) / 1000, text });
    }
    // Auto-generated tracks overlap heavily (rolling captions); clip each cue at the next one.
    const out = finalize(cues);
    for (let i = 0; i < out.length - 1; i++) {
      if (out[i].end > out[i + 1].start) out[i].end = Math.max(out[i + 1].start, out[i].start + 0.01);
    }
    return out;
  }

  function parseClock(t) {
    // 01:02:03.456, 02:03.456, 01:02:03,456
    const parts = t.trim().replace(',', '.').split(':').map(Number);
    if (parts.some((n) => !Number.isFinite(n))) return NaN;
    return parts.reduce((acc, n) => acc * 60 + n, 0);
  }

  function parseVtt(text) {
    const cues = [];
    const blocks = text.replace(/\r/g, '').split(/\n{2,}/);
    for (const block of blocks) {
      const lines = block.split('\n');
      const i = lines.findIndex((l) => l.includes('-->'));
      if (i === -1) continue;
      const [a, b] = lines[i].split('-->');
      const start = parseClock(a);
      const end = parseClock(b.trim().split(/\s+/)[0]);
      const body = lines.slice(i + 1).join('\n').replace(/<[^>]+>/g, '');
      cues.push({ start, end, text: cleanText(decodeEntities(body)) });
    }
    return finalize(cues);
  }

  // TTML / DFXP (Netflix, Prime Video). Regex based so it runs without a DOM.
  function parseTtml(xml) {
    const tickRateMatch = xml.match(/ttp:tickRate="(\d+)"/);
    const tickRate = tickRateMatch ? Number(tickRateMatch[1]) : 10000000;
    const frameRateMatch = xml.match(/ttp:frameRate="(\d+)"/);
    const frameRate = frameRateMatch ? Number(frameRateMatch[1]) : 30;

    function time(v) {
      if (v == null) return NaN;
      let m;
      if ((m = v.match(/^([\d.]+)t$/))) return Number(m[1]) / tickRate;
      if ((m = v.match(/^([\d.]+)(h|ms|m|s|f)$/))) {
        const n = Number(m[1]);
        return { h: n * 3600, m: n * 60, s: n, ms: n / 1000, f: n / frameRate }[m[2]];
      }
      if ((m = v.match(/^(\d+):(\d+):(\d+):(\d+)$/))) {
        return Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]) + Number(m[4]) / frameRate;
      }
      return parseClock(v);
    }

    const attr = (attrs, name) => {
      const m = attrs.match(new RegExp('\\b' + name + '="([^"]*)"'));
      return m ? m[1] : null;
    };

    const cues = [];
    const re = /<(?:tt:)?p\b([^>]*)>([\s\S]*?)<\/(?:tt:)?p>/g;
    let m;
    while ((m = re.exec(xml))) {
      const attrs = m[1];
      const start = time(attr(attrs, 'begin'));
      let end = time(attr(attrs, 'end'));
      if (!Number.isFinite(end)) end = start + time(attr(attrs, 'dur'));
      const body = m[2].replace(/<(?:tt:)?br\s*\/?>/g, '\n').replace(/<[^>]+>/g, '');
      cues.push({ start, end, text: cleanText(decodeEntities(body)) });
    }
    // Netflix splits one subtitle into several <p> regions with identical timing.
    const merged = [];
    for (const c of finalize(cues)) {
      const prev = merged[merged.length - 1];
      if (prev && prev.start === c.start && prev.end === c.end) prev.text += '\n' + c.text;
      else merged.push(c);
    }
    return merged;
  }

  function parseAny(text) {
    const head = text.trimStart().slice(0, 200);
    if (head.startsWith('{')) return parseJson3(text);
    if (head.startsWith('WEBVTT')) return parseVtt(text);
    if (head.startsWith('<')) return parseTtml(text);
    return parseVtt(text);
  }

  // Binary search for the cue showing at time t (seconds). Returns null if none.
  function cueAt(cues, t) {
    let lo = 0;
    let hi = cues.length - 1;
    let idx = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (cues[mid].start <= t) {
        idx = mid;
        lo = mid + 1;
      } else hi = mid - 1;
    }
    // Overlapping cues: walk back a few to find one still active.
    for (let i = idx; i >= 0 && i > idx - 5; i--) {
      if (cues[i].end > t) return cues[i];
    }
    return null;
  }

  // Normalize BCP-47-ish codes so "en-US", "en_us" and "en" compare equal at the base level.
  function baseLang(code) {
    return String(code || '').toLowerCase().replace('_', '-').split('-')[0];
  }

  function sameLang(a, b) {
    return !!a && !!b && baseLang(a) === baseLang(b);
  }

  // Choose the original-language track and the viewer's-language track from a
  // site's track list. Returns { orig, mine } where mine may be null (=> machine translate).
  function pickPair(tracks, { originalLang, myLang, origOverride } = {}) {
    const usable = tracks.filter((t) => !t.forced);
    const prefer = (list) => list.find((t) => !t.sdh) || list[0] || null;
    const ofLang = (lang) => usable.filter((t) => sameLang(t.lang, lang));

    let orig = null;
    if (origOverride && origOverride !== 'auto') orig = prefer(ofLang(origOverride));
    if (!orig && originalLang) orig = prefer(ofLang(originalLang));
    if (!orig) orig = prefer(usable.filter((t) => !sameLang(t.lang, myLang))) || prefer(usable);
    if (!orig) return { orig: null, mine: null };

    const mine = sameLang(orig.lang, myLang) ? null : prefer(ofLang(myLang));
    return { orig, mine };
  }

  const api = { pickPair, parseJson3, parseVtt, parseTtml, parseAny, cueAt, baseLang, sameLang, decodeEntities };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.DualSubs = Object.assign(root.DualSubs || {}, api);
})(typeof globalThis !== 'undefined' ? globalThis : this);
