// Splits a stream of 16 kHz mono samples into speech chunks for transcription:
// a chunk ends after a short pause, or at maxSeconds so lines keep coming during
// continuous speech. Quiet stretches (no speech) are dropped.
(function (root) {
  'use strict';

  function createSegmenter(opts = {}) {
    const rate = opts.sampleRate || 16000;
    const frame = Math.round(rate * 0.02); // 20 ms analysis frames
    const minSpeech = opts.minSeconds ?? 0.6;
    const maxLen = Math.round(rate * (opts.maxSeconds ?? 6));
    const pauseFrames = Math.round((opts.pauseSeconds ?? 0.45) / 0.02);
    const padFrames = 10; // keep 200 ms before speech starts
    const onChunk = opts.onChunk || (() => {});

    let noise = 0.003; // running noise-floor estimate (RMS)
    let pending = new Float32Array(0); // samples not yet analysed (< 1 frame)
    let chunk = []; // Float32Array frames of the current chunk
    let preroll = [];
    let voiced = 0;
    let silentRun = 0;
    let inSpeech = false;

    function rms(f) {
      let s = 0;
      for (let i = 0; i < f.length; i++) s += f[i] * f[i];
      return Math.sqrt(s / f.length);
    }

    function flush() {
      if (inSpeech && voiced * 0.02 >= minSpeech) {
        const total = chunk.reduce((n, f) => n + f.length, 0);
        const out = new Float32Array(total);
        let o = 0;
        for (const f of chunk) {
          out.set(f, o);
          o += f.length;
        }
        onChunk(out);
      }
      chunk = [];
      voiced = 0;
      silentRun = 0;
      inSpeech = false;
    }

    function analyse(f) {
      const level = rms(f);
      const speech = level > Math.max(0.008, noise * 3);
      if (!speech) noise = noise * 0.995 + level * 0.005;

      if (!inSpeech) {
        preroll.push(f);
        if (preroll.length > padFrames) preroll.shift();
        if (speech) {
          inSpeech = true;
          chunk = preroll;
          preroll = [];
          voiced = 1;
        }
        return;
      }
      chunk.push(f);
      if (speech) {
        voiced++;
        silentRun = 0;
      } else silentRun++;
      const len = chunk.length * frame;
      if (silentRun >= pauseFrames || len >= maxLen) flush();
    }

    return {
      push(samples) {
        const all = new Float32Array(pending.length + samples.length);
        all.set(pending);
        all.set(samples, pending.length);
        let i = 0;
        for (; i + frame <= all.length; i += frame) analyse(all.slice(i, i + frame));
        pending = all.slice(i);
      },
      flush,
    };
  }

  // Whisper tends to "hear" these in music or silence.
  const HALLUCINATIONS = [
    /^thanks? (you )?(so much )?for watching/i,
    /^please subscribe/i,
    /^subtitles? by/i,
    /amara\.org/i,
    /^you$/i,
    /^\.+$/,
  ];

  function cleanTranscript(text) {
    const t = String(text || '')
      .replace(/\[[^\]]*\]|\([^)]*\)|♪+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    if (!t || !/[\p{L}\p{N}]/u.test(t)) return '';
    if (HALLUCINATIONS.some((re) => re.test(t))) return '';
    return t;
  }

  const api = { createSegmenter, cleanTranscript };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.DualSubsAudio = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
