// Offscreen document: captures the tab's audio, keeps it audible, cuts it into speech
// chunks and transcribes them on-device with Whisper (Transformers.js + ONNX Runtime).
// Nothing leaves the computer except the finished text, which goes to translation.
import { pipeline, env, Tensor } from './vendor/transformers/transformers.min.js';

const { createSegmenter, cleanTranscript } = globalThis.DualSubsAudio;

const MODELS = {
  tiny: 'onnx-community/whisper-tiny',
  base: 'onnx-community/whisper-base',
  small: 'onnx-community/whisper-small',
};

env.allowLocalModels = false;
env.backends.onnx.wasm.wasmPaths = {
  mjs: chrome.runtime.getURL('vendor/transformers/ort-wasm-simd-threaded.asyncify.mjs'),
  wasm: chrome.runtime.getURL('vendor/transformers/ort-wasm-simd-threaded.asyncify.wasm'),
};
env.backends.onnx.wasm.numThreads = 1;
// Extension URLs can't go in the Cache API; the wasm file is already local anyway.
env.useWasmCache = false;

let session = null; // { tabId, stream, contexts, segmenter }
let asr = null; // { key, run }
const queue = [];
let busy = false;

function status(tabId, value, detail) {
  chrome.runtime.sendMessage({ type: 'asr-status', tabId, status: value, detail: detail || '' }).catch(() => {});
}

async function loadModel(tabId, opts) {
  const id = opts.modelId || MODELS[opts.model] || MODELS.base;
  const key = id + '|' + (opts.modelHost || '');
  if (asr && asr.key === key) return asr.run;
  if (opts.modelHost) env.remoteHost = opts.modelHost;

  const files = {};
  const progress_callback = (p) => {
    if (p.status === 'progress' && p.total) {
      files[p.file] = [p.loaded, p.total];
      const [loaded, total] = Object.values(files).reduce((a, [l, t]) => [a[0] + l, a[1] + t], [0, 0]);
      status(tabId, 'loading', 'Downloading speech model (first time only): ' + Math.round((loaded / total) * 100) + '%');
    }
  };
  status(tabId, 'loading', 'Loading speech model…');
  let run = null;
  if (navigator.gpu && !opts.forceWasm) {
    try {
      run = await pipeline('automatic-speech-recognition', id, {
        device: 'webgpu',
        dtype: { encoder_model: 'fp32', decoder_model_merged: 'q4' },
        progress_callback,
      });
    } catch (e) {
      run = null; // fall back to WebAssembly
    }
  }
  if (!run) run = await pipeline('automatic-speech-recognition', id, { device: 'wasm', dtype: 'q8', progress_callback });
  asr = { key, run };
  return run;
}

// Whisper needs to be told the spoken language (Transformers.js otherwise assumes
// English), so detect it: one decoder step after the start token scores every
// language token. The first few chunks vote, then the language stays fixed.
const DETECT_CHUNKS = 3;

async function detectLanguage(run, audio) {
  const { input_features } = await run.processor(audio);
  const cfg = run.model.generation_config;
  const sot = cfg.decoder_start_token_id;
  const decoder_input_ids = new Tensor('int64', BigInt64Array.from([BigInt(sot)]), [1, 1]);
  const { logits } = await run.model({ input_features, decoder_input_ids });
  const vocab = logits.dims.at(-1);
  const data = logits.data;
  const offset = data.length - vocab; // logits for the last (only) position
  let best = null;
  let bestScore = -Infinity;
  for (const [token, id] of Object.entries(cfg.lang_to_id || {})) {
    const score = data[offset + id];
    if (score > bestScore) {
      bestScore = score;
      best = token.slice(2, -2); // "<|fr|>" -> "fr"
    }
  }
  return best;
}

async function drain() {
  if (busy || !session) return;
  busy = true;
  try {
    while (queue.length && session) {
      const { audio, tabId } = queue.shift();
      const run = asr && asr.run;
      if (!run || !session) break;
      let language = session.language;
      if (!language && run.model.generation_config.lang_to_id) {
        const guess = await detectLanguage(run, audio);
        if (guess) {
          session.votes[guess] = (session.votes[guess] || 0) + 1;
          language = guess;
          const total = Object.values(session.votes).reduce((a, b) => a + b, 0);
          if (total >= DETECT_CHUNKS) {
            session.language = Object.entries(session.votes).sort((a, b) => b[1] - a[1])[0][0];
          }
        }
      }
      const out = await run(audio, Object.assign({ task: 'transcribe' }, language ? { language } : {}));
      const text = cleanTranscript(out && out.text);
      if (text && session && session.tabId === tabId) {
        chrome.runtime.sendMessage({ type: 'asr-transcript', tabId, text, lang: language || '' }).catch(() => {});
      }
    }
  } catch (e) {
    if (session) status(session.tabId, 'error', 'Speech recognition failed: ' + (e.message || e));
  } finally {
    busy = false;
  }
}

// Start transcribing a MediaStream (the captured tab audio).
async function startWithStream(stream, tabId, opts = {}) {
  stop();
  // Capturing a tab mutes it, so play the audio back at full quality…
  const playback = new AudioContext();
  playback.createMediaStreamSource(stream).connect(playback.destination);
  // …and analyse a 16 kHz copy for Whisper.
  const ctx16 = new AudioContext({ sampleRate: 16000 });
  await ctx16.audioWorklet.addModule(chrome.runtime.getURL('audio-worklet.js'));
  const src = ctx16.createMediaStreamSource(stream);
  const tap = new AudioWorkletNode(ctx16, 'dualsubs-tap');
  const silent = ctx16.createGain();
  silent.gain.value = 0;
  src.connect(tap).connect(silent).connect(ctx16.destination);

  const language = opts.language && opts.language !== 'auto' ? opts.language.split('-')[0] : null;
  const segmenter = createSegmenter({
    sampleRate: 16000,
    onChunk: (audio) => {
      queue.push({ audio, tabId });
      // Stay live: if transcription falls behind, skip the oldest speech.
      while (queue.length > 2) queue.shift();
      drain();
    },
  });
  tap.port.onmessage = (e) => segmenter.push(e.data);
  session = { tabId, stream, contexts: [playback, ctx16], segmenter, language, votes: {} };
  stream.getAudioTracks().forEach((t) => (t.onended = () => stop(true)));

  try {
    await loadModel(tabId, opts);
  } catch (e) {
    status(tabId, 'error', 'Could not load the speech model: ' + (e.message || e));
    stop();
    return;
  }
  if (session && session.tabId === tabId) {
    status(tabId, 'listening', '');
    drain();
  }
}

function stop(notify) {
  if (!session) return;
  const { tabId, stream, contexts } = session;
  session = null;
  queue.length = 0;
  stream.getTracks().forEach((t) => t.stop());
  contexts.forEach((c) => c.close().catch(() => {}));
  if (notify) status(tabId, 'off', '');
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg.target !== 'offscreen') return false;
  if (msg.type === 'start') {
    navigator.mediaDevices
      .getUserMedia({ audio: { mandatory: { chromeMediaSource: 'tab', chromeMediaSourceId: msg.streamId } }, video: false })
      .then((stream) => startWithStream(stream, msg.tabId, msg.options))
      .catch((e) => status(msg.tabId, 'error', 'Could not capture the tab audio: ' + (e.message || e)));
  } else if (msg.type === 'stop') {
    stop(true);
  }
  reply({ ok: true });
  return false;
});

// Used by the automated tests, which feed a recorded stream instead of a tab capture.
globalThis.dualSubsStartWithStream = startWithStream;
