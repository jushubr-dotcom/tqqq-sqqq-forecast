const test = require('node:test');
const assert = require('node:assert/strict');
const S = require('../src/lib/subs.js');

test('parseJson3 reads YouTube events and clips rolling overlaps', () => {
  const cues = S.parseJson3({
    events: [
      { tStartMs: 0, dDurationMs: 4000, segs: [{ utf8: 'Hola ' }, { utf8: 'amigo' }] },
      { tStartMs: 1000, dDurationMs: 0, aAppend: 1, segs: [{ utf8: '\n' }] },
      { tStartMs: 2500, dDurationMs: 3000, segs: [{ utf8: '¿Qué tal?' }] },
      { tStartMs: 6000, dDurationMs: 1000 },
    ],
  });
  assert.deepEqual(cues, [
    { start: 0, end: 2.5, text: 'Hola amigo' },
    { start: 2.5, end: 5.5, text: '¿Qué tal?' },
  ]);
});

test('parseVtt handles headers, settings and tags', () => {
  const vtt = 'WEBVTT\n\nNOTE x\n\n1\n00:00:01.000 --> 00:00:02.500 line:80%\n<i>Bonjour</i> &amp; salut\n\n00:01:00.000 --> 00:01:01.000\nDeux\nlignes\n';
  assert.deepEqual(S.parseVtt(vtt), [
    { start: 1, end: 2.5, text: 'Bonjour & salut' },
    { start: 60, end: 61, text: 'Deux\nlignes' },
  ]);
});

test('parseTtml handles ticks, clock times, <br/> and split regions', () => {
  const xml = `<?xml version="1.0"?>
<tt xmlns="http://www.w3.org/ns/ttml" xmlns:ttp="http://www.w3.org/ns/ttml#parameter" ttp:tickRate="10000000">
<body><div>
<p begin="10000000t" end="25000000t" region="top"><span>Guten</span><br/>Tag</p>
<p begin="10000000t" end="25000000t" region="bottom">zweite</p>
<p begin="00:00:03.000" end="00:00:04.250">Danke &lt;3</p>
<p begin="5s" dur="1s">Bitte</p>
</div></body></tt>`;
  assert.deepEqual(S.parseTtml(xml), [
    { start: 1, end: 2.5, text: 'Guten\nTag\nzweite' },
    { start: 3, end: 4.25, text: 'Danke <3' },
    { start: 5, end: 6, text: 'Bitte' },
  ]);
});

test('parseAny dispatches on content', () => {
  assert.equal(S.parseAny('WEBVTT\n\n00:00.000 --> 00:01.000\nhi')[0].text, 'hi');
  assert.equal(S.parseAny('{"events":[{"tStartMs":0,"dDurationMs":1000,"segs":[{"utf8":"yo"}]}]}')[0].text, 'yo');
  assert.equal(S.parseAny('<tt><p begin="0s" end="1s">x</p></tt>')[0].text, 'x');
});

test('cueAt finds the active cue or null', () => {
  const cues = [
    { start: 0, end: 1, text: 'a' },
    { start: 2, end: 5, text: 'b' },
    { start: 3, end: 4, text: 'c' },
  ];
  assert.equal(S.cueAt(cues, 0.5).text, 'a');
  assert.equal(S.cueAt(cues, 1.5), null);
  assert.equal(S.cueAt(cues, 3.5).text, 'c');
  assert.equal(S.cueAt(cues, 4.5).text, 'b');
  assert.equal(S.cueAt(cues, 9), null);
  assert.equal(S.cueAt([], 1), null);
});

test('pickPair prefers native audio language and a viewer-language track', () => {
  const tracks = [
    { lang: 'en', sdh: true },
    { lang: 'ko', sdh: false },
    { lang: 'en', sdh: false },
    { lang: 'ko', forced: true },
    { lang: 'pt-BR', sdh: false },
  ];
  let r = S.pickPair(tracks, { originalLang: 'ko', myLang: 'pt' });
  assert.equal(r.orig.lang, 'ko');
  assert.equal(r.mine.lang, 'pt-BR');

  r = S.pickPair(tracks, { originalLang: 'ko', myLang: 'de' });
  assert.equal(r.mine, null, 'no German track => machine translation');

  r = S.pickPair(tracks, { originalLang: null, myLang: 'ko', origOverride: 'en' });
  assert.equal(r.orig.lang, 'en');
  assert.equal(r.orig.sdh, false);
  assert.equal(r.mine.lang, 'ko');

  r = S.pickPair(tracks, { originalLang: 'en', myLang: 'en' });
  assert.equal(r.mine, null, 'same language => single line');
});

test('parseM3u8Master lists subtitle renditions once and flags forced/SDH/original audio', () => {
  const master = [
    '#EXTM3U',
    '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",NAME="English [Original]",LANGUAGE="en",DEFAULT=YES,URI="a/en.m3u8"',
    '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",NAME="Español",LANGUAGE="es",URI="a/es.m3u8"',
    '#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="sub",NAME="English [CC]",LANGUAGE="en",CHARACTERISTICS="public.accessibility.transcribes-spoken-dialog,public.accessibility.describes-music-and-sound",URI="r/en_sdh.m3u8"',
    '#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="sub",NAME="English",LANGUAGE="en",FORCED=NO,URI="r/en.m3u8"',
    '#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="sub",NAME="Español",LANGUAGE="es-419",FORCED=YES,URI="r/es_forced.m3u8"',
    '#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="sub2",NAME="English",LANGUAGE="en",FORCED=NO,URI="r/en.m3u8"',
    '#EXT-X-STREAM-INF:BANDWIDTH=1,SUBTITLES="sub"',
    'v/1.m3u8',
  ].join('\n');
  const { subtitles, audio } = S.parseM3u8Master(master, 'https://cdn.example/ps01/master.m3u8?x=1');
  assert.equal(subtitles.length, 3);
  assert.deepEqual(subtitles[0], {
    lang: 'en', label: 'English [CC]', url: 'https://cdn.example/ps01/r/en_sdh.m3u8', forced: false, sdh: true,
  });
  assert.equal(subtitles[2].forced, true);
  assert.equal(audio.find((a) => a.original).lang, 'en');
  const pair = S.pickPair(subtitles, { originalLang: 'en', myLang: 'es' });
  assert.equal(pair.orig.url, 'https://cdn.example/ps01/r/en.m3u8');
  assert.equal(pair.mine, null, 'only a forced Spanish track => machine translation');
});

test('parseM3u8Media + mergeCues join WebVTT segments without duplicates', () => {
  const media = '#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6.0,\nseg0.vtt\n#EXTINF:6.0,\nhttps://other.example/seg1.vtt\n#EXT-X-ENDLIST\n';
  assert.deepEqual(S.parseM3u8Media(media, 'https://cdn.example/r/en.m3u8'), [
    'https://cdn.example/r/seg0.vtt',
    'https://other.example/seg1.vtt',
  ]);
  const a = S.parseVtt('WEBVTT\nX-TIMESTAMP-MAP=MPEGTS:900000,LOCAL:00:00:00.000\n\n00:00:01.000 --> 00:00:07.000\nspans\n\n00:00:02.000 --> 00:00:03.000\nfirst');
  const b = S.parseVtt('WEBVTT\n\n00:00:01.000 --> 00:00:07.000\nspans\n\n00:00:08.000 --> 00:00:09.000\nsecond');
  assert.deepEqual(S.mergeCues([b, a]).map((c) => c.text), ['spans', 'first', 'second']);
});
