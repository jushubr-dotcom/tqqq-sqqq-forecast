const test = require('node:test');
const assert = require('node:assert/strict');
const { createSegmenter, cleanTranscript } = require('../src/lib/segmenter.js');

const RATE = 16000;
const tone = (sec, amp = 0.2) => Float32Array.from({ length: Math.round(sec * RATE) }, (_, i) => amp * Math.sin(i / 5));
const quiet = (sec) => new Float32Array(Math.round(sec * RATE));

function feed(seg, parts) {
  for (const p of parts) for (let i = 0; i < p.length; i += 1600) seg.push(p.slice(i, i + 1600));
}

test('cuts speech at pauses and drops silence and blips', () => {
  const chunks = [];
  const seg = createSegmenter({ sampleRate: RATE, onChunk: (c) => chunks.push(c.length / RATE) });
  feed(seg, [quiet(1), tone(1.5), quiet(1), tone(0.1), quiet(1), tone(2), quiet(1)]);
  assert.equal(chunks.length, 2, 'two utterances; the 0.1 s blip is ignored');
  assert.ok(chunks[0] > 1.5 && chunks[0] < 2.4, 'first chunk ≈ speech + preroll + pause: ' + chunks[0]);
});

test('splits continuous speech at maxSeconds', () => {
  const chunks = [];
  const seg = createSegmenter({ sampleRate: RATE, maxSeconds: 4, onChunk: (c) => chunks.push(c.length / RATE) });
  feed(seg, [tone(10), quiet(1)]);
  assert.equal(chunks.length, 3);
  assert.ok(chunks.every((s) => s <= 4.3));
});

test('cleanTranscript strips sound tags and known hallucinations', () => {
  assert.equal(cleanTranscript(' [Music] Hola,  ¿qué tal? ♪ '), 'Hola, ¿qué tal?');
  assert.equal(cleanTranscript('(applause)'), '');
  assert.equal(cleanTranscript('Thank you for watching!'), '');
  assert.equal(cleanTranscript('...'), '');
  assert.equal(cleanTranscript('こんにちは'), 'こんにちは');
});
