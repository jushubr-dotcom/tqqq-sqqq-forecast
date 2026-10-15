/**
 * 🦖 SPREADSAURS — catch, trade and battle funny dinosaurs inside a Google Sheet.
 *
 * Setup (about 2 minutes):
 *   1. Create a blank Google Sheet.
 *   2. Extensions → Apps Script. Delete the sample code, paste this whole file, click Save.
 *   3. Choose `setupSpreadsaurs` in the function dropdown and click Run. Approve the permissions.
 *   4. Go back to the sheet and tick the checkboxes to play.
 *
 * Everything (your dinos, your dex, your snacks) lives inside your own copy of the sheet.
 */

// ─────────────────────────────── Config ───────────────────────────────

const SHEETS = {
  decoy: 'FY25 Budget',
  encounter: '🦖 Encounter',
  collection: 'Collection',
  dex: 'Dex',
  trade: 'Trade & Battle',
  state: '_state',
};
const GAME_SHEETS = ['encounter', 'collection', 'dex', 'trade'];

const CANVAS_W = 18;
const CANVAS_H = 20;
const SNACKS_PER_DAY = 10;
const BOSS_SNACK_REWARD = 5;
const WILD_SHINY_ODDS = 64;
const MAX_LEVEL = 50;
const SPECIES_COUNT = 24;

const FIXED_COLORS = {
  O: '#2b2d42', // outline
  W: '#ffffff', // eye whites, teeth, claws
  K: '#141414', // pupils
  M: '#c0392b', // mouth
  P: '#ff9ec4', // blush
};

const ACCESSORY_COLORS = {
  R: '#e63946', r: '#9d0208', // tie
  Y: '#f6c90e', y: '#d49b00', // gold
  H: '#1d1d1f', h: '#e63946', // top hat + band
  S: '#111111', s: '#7f8fa6', // shades + glint
  C: '#2d7dd2', c: '#174a7e', // cap + brim
  Q: '#ff5d8f', q: '#ffd23f', // party hat
  V: '#9aa5b1', v: '#fff4d6', // viking helmet + horns
  G: '#2b2d42',               // glasses
  N: '#6f4e37', U: '#f5f5f5', // coffee + mug
};

const SKY = '#eaf4ff';
const GRASS = '#bfe8a6';
const SILHOUETTE = '#c7ccd6';

// Body sprites. B/L/D come from the species palette; O/W/K/M/P are fixed colors.
// Anchors are [x, y] inside the sprite and tell accessories where to sit.
const BODIES = {
  rex: {
    rows: [
      '........OOOOOOO...',
      '.......OBBBBBBBOO.',
      '......OBBBWWBBBBBO',
      '......OBBBWKBBBBBO',
      '......OBPBBBBBBBBO',
      '......OBBBBBOMMMMO',
      '......OBBBBBBWOWO.',
      '...OOOOBBBBBOOO...',
      '..OBBBBBLLLBOBO...',
      '.OBBBBBBLLLBBO....',
      'OBOOOBBBLLLBBO....',
      'OO...OBBOOOBBO....',
      '.....OBO...OBO....',
      '.....OOO...OOO....',
    ],
    anchors: { head: [11, 0], eye: [10, 2], neck: [9, 7], hand: [13, 8] },
  },
  trike: {
    rows: [
      '.......OO....OO...',
      '......ODDO..OWO...',
      '.....ODDDDOOWO....',
      '.....ODDBBBBBOO...',
      '.....ODBBWWBBBBOO.',
      '.....ODBBWKBBBBBWO',
      '.....ODBPBBBBBBBOO',
      '..OOOODBBBBBOMMO..',
      '.OBBBBOOBBBBBOO...',
      'OBBBLLLLLBBBBO....',
      'OBBBLLLLLBBBO.....',
      '.OBOOBBOOOBBO.....',
      '.OBO.OBO..OBO.....',
      '.OOO.OOO..OOO.....',
    ],
    anchors: { head: [10, 3], eye: [9, 4], neck: [9, 8], hand: [12, 9] },
  },
  stego: {
    rows: [
      '......O...O.......',
      '.....ODO.ODO......',
      '...O.ODDODDDOOOOO.',
      '..ODOODDDDDDOBBBBO',
      '..ODDBBBBBBBBBWWBO',
      '.OBBBBBBBBBBBBWKBO',
      'OWOBBLLLLLLBBPBBMO',
      '.OBBBLLLLLLLBBBOO.',
      '..OOBBLLLLLBBOO...',
      '...OBBOOBBOOBBO...',
      '...OBO.OBO.OBO....',
      '...OOO.OOO.OOO....',
    ],
    anchors: { head: [15, 2], eye: [14, 4], neck: [12, 7], hand: [13, 8] },
  },
  noodle: {
    rows: [
      '...........OOOO...',
      '..........OBBBBO..',
      '..........OBWWBBO.',
      '..........OBWKBMO.',
      '..........OBPBOO..',
      '..........OBBO....',
      '.........OBBO.....',
      '.........OBBO.....',
      '....OOOOOBBBO.....',
      '...OBBBBBBBBBO....',
      '..OBBBBLLLLBBBO...',
      '.OBBBBLLLLLLBBO...',
      'OBOOBBLLLLLLBBO...',
      'OO.OBBOOOOOOBBO...',
      '...OBBO....OBBO...',
      '...OOOO....OOOO...',
    ],
    anchors: { head: [13, 0], eye: [12, 2], neck: [11, 5], hand: [13, 10] },
  },
  raptor: {
    rows: [
      '..........OOOOO...',
      '.........OBBBBBOO.',
      '.........OBWWBBBBO',
      '.........OBWKBBBBO',
      '.........OBPBBOMMO',
      '........OBBBBBOOO.',
      '.......OBBBO......',
      '.OO...OBBLBOO.....',
      'OBBOOOBBLLBBBO....',
      '.OBBBBBBLLBOOWO...',
      '..OOBBBBLLBO......',
      '....OBBBBBBO......',
      '....OBBOOBBO......',
      '...OBBO.OBBO......',
      '...OWWO.OWWO......',
      '...OOOO.OOOO......',
    ],
    anchors: { head: [12, 0], eye: [11, 2], neck: [10, 6], hand: [13, 9] },
  },
  ptero: {
    rows: [
      '.....OO...........',
      '......ODO.........',
      '.......ODOOOO.....',
      '......OBBBBBBOOOO.',
      '......OBWWBBBBBBBO',
      '......OBWKBBOOOOO.',
      '......OBPBBO......',
      'O......OBBO......O',
      'OBO...OBLLBO...OBO',
      'OBBBOOBBLLBBOOBBBO',
      '.OBBBBBBLLBBBBBBO.',
      '..OBBBBBLLBBBBBO..',
      '...OOOOBLLBOOOO...',
      '......OBBBBO......',
      '......OBOOBO......',
      '......OO..OO......',
    ],
    anchors: { head: [9, 3], eye: [8, 4], neck: [9, 8], hand: [11, 9] },
  },
  ankylo: {
    rows: [
      '.....O..O..O......',
      '....ODOODOODO.....',
      '...ODDDDDDDDDO....',
      '..ODDDDDDDDDDDOOO.',
      '.ODDDDDDDDDDDOBBBO',
      'OOODDDDDDDDDOBOOBO',
      'ODOBBBBBBBBBBBWKBO',
      'ODDOBBLLLLLBBBBMMO',
      '.OOOBBLLLLLBBBBOO.',
      '...OBBOOOOOBBO....',
      '...OBO....OBO.....',
      '...OOO....OOO.....',
    ],
    // The mug balances on its back: ankylos have no hands.
    anchors: { head: [15, 3], eye: [14, 5], neck: [12, 8], hand: [8, 2] },
  },
  bonk: {
    rows: [
      '........OOOO......',
      '.......OLLLLO.....',
      '......OLLLLLLO....',
      '......OOBBBBBOO...',
      '......OBBWWBBBBO..',
      '......OBBWKBBBBBO.',
      '......OBPBBBOMMMO.',
      '.......OBBBBBOOO..',
      '...OO.OBBLLBO.....',
      '..OBBOBBLLLBBO....',
      '.OBBBBBBLLLBOBO...',
      '..OOBBBBLLLBO.....',
      '....OBBBBBBBO.....',
      '....OBBOOOBBO.....',
      '....OBO...OBO.....',
      '....OOO...OOO.....',
    ],
    anchors: { head: [10, 0], eye: [9, 4], neck: [9, 8], hand: [13, 10] },
  },
};

// Accessories: `at` names a body anchor, [ox, oy] shifts the accessory's top-left from it.
const ACCESSORIES = {
  tie:     { at: 'neck', ox: -1, oy: 0,  rows: ['.r.', '.R.', 'RRR', 'RRR', '.R.'] },
  crown:   { at: 'head', ox: -2, oy: -1, rows: ['Y.Y.Y', 'YyYyY'] },
  tophat:  { at: 'head', ox: -2, oy: -3, rows: ['.HHH.', '.HHH.', '.hhh.', 'HHHHH'] },
  cap:     { at: 'head', ox: -2, oy: -1, rows: ['.CCC..', 'CCCCcc'] },
  party:   { at: 'head', ox: -2, oy: -2, rows: ['..q..', '.QqQ.', 'QqQqQ'] },
  viking:  { at: 'head', ox: -2, oy: -1, rows: ['v...v', 'vVVVv', '.VVV.'] },
  shades:  { at: 'eye',  ox: -1, oy: 0,  rows: ['SsSS', '.SS.'] },
  monocle: { at: 'eye',  ox: -1, oy: -1, rows: ['.YY.', 'Y..Y', 'Y..Y', '.YY.', '...y', '...y'] },
  glasses: { at: 'eye',  ox: -1, oy: -1, rows: ['.GG.', 'G..G', 'G..G', '.GG.'] },
  mug:     { at: 'hand', ox: 0,  oy: -2, rows: ['NNN.', 'UUUU', 'UUU.'] },
  chain:   { at: 'neck', ox: -2, oy: 0,  rows: ['Y...Y', '.Y.Y.', '..Y..'] },
};

const DEPTS = {
  Finance:   { emoji: '📈', beats: 'Marketing' },
  Marketing: { emoji: '📣', beats: 'IT' },
  IT:        { emoji: '💻', beats: 'HR' },
  HR:        { emoji: '🧾', beats: 'Finance' },
};

// 8 evolution lines × 3 stages = 24 species. Species id = line * 3 + stage.
const LINES = [
  {
    body: 'rex', dept: 'Finance', move: 'Budget Cut', base: [55, 68, 45, 42],
    palette: { B: '#6cc04a', L: '#d4f5b0', D: '#3d8a2a' },
    shiny:   { B: '#e74c8c', L: '#fbd3e3', D: '#9b1d55' },
    stages: [
      { name: 'Smol Rex', acc: [], flavor: 'Arms too short to reach the keyboard. Types with its nose.' },
      { name: 'Tie Rex', acc: ['tie'], flavor: 'Wears a tie to every meeting. Has never said anything in one.' },
      { name: 'CEO Rex', acc: ['tie', 'crown', 'shades'], flavor: 'Announced layoffs and a yacht on the same day. Arms still too short to sign either.' },
    ],
  },
  {
    body: 'trike', dept: 'HR', move: 'Mandatory Training', base: [62, 55, 62, 31],
    palette: { B: '#f39c38', L: '#ffe0b0', D: '#8e44ad' },
    shiny:   { B: '#5dade2', L: '#d6eaf8', D: '#1f618d' },
    stages: [
      { name: 'Tricerablob', acc: [], flavor: 'Three horns, zero plans. Mostly eats the free bagels.' },
      { name: 'Tricera-tophat', acc: ['tophat'], flavor: 'Found a top hat in the lost & found. Now insists on being called "Sir".' },
      { name: 'Tricera-tycoon', acc: ['tophat', 'monocle'], flavor: 'Owns 40% of the office plants. Charges the cactus rent.' },
    ],
  },
  {
    body: 'stego', dept: 'IT', move: '#REF! Beam', base: [58, 50, 66, 36],
    palette: { B: '#3fb5a8', L: '#c7f2ec', D: '#e0525a' },
    shiny:   { B: '#c39bd3', L: '#f4ecf7', D: '#f5b041' },
    stages: [
      { name: 'Stegosnack', acc: [], flavor: 'Its back plates are stacked sticky notes. Do not peel.' },
      { name: 'Stegospreadsheet', acc: ['glasses'], flavor: 'Knows every VLOOKUP error by heart. #N/A is its love language.' },
      { name: 'Stegosaurus Excelsior', acc: ['glasses', 'crown'], flavor: 'Has ascended. Speaks only in pivot tables.' },
    ],
  },
  {
    body: 'noodle', dept: 'Marketing', move: 'Synergy Slam', base: [75, 48, 50, 37],
    palette: { B: '#9b72d9', L: '#e6dcff', D: '#6a47a8' },
    shiny:   { B: '#58d68d', L: '#e9f7ef', D: '#1e8449' },
    stages: [
      { name: 'Noodle', acc: [], flavor: 'Neck so long it attends meetings on two floors at once.' },
      { name: 'Noodlenecktie', acc: ['tie'], flavor: 'Needed 14 feet of tie. Expensed it.' },
      { name: 'Noodle Supreme', acc: ['tie', 'tophat'], flavor: 'Sees over every cubicle. Knows exactly who is on Etsy right now.' },
    ],
  },
  {
    body: 'raptor', dept: 'Marketing', move: 'Viral Bars', base: [45, 62, 38, 65],
    palette: { B: '#4a90e2', L: '#cfe3fb', D: '#2c5fa0' },
    shiny:   { B: '#ec7063', L: '#fadbd8', D: '#922b21' },
    stages: [
      { name: 'Velocirappy', acc: [], flavor: 'Eats deadlines raw. Moves fast and breaks the printer.' },
      { name: 'Velocicapper', acc: ['cap'], flavor: 'A backwards cap means "creative mode". It is never not in creative mode.' },
      { name: 'Velocirapper MC', acc: ['cap', 'chain', 'shades'], flavor: 'Dropped a diss track about the Q3 numbers. Went platinum internally.' },
    ],
  },
  {
    body: 'ptero', dept: 'Finance', move: 'Swoop & Delegate', base: [48, 55, 40, 67],
    palette: { B: '#f4d03f', L: '#fff6c4', D: '#d35400' },
    shiny:   { B: '#48c9b0', L: '#d1f2eb', D: '#117864' },
    stages: [
      { name: 'Pterodaftyl', acc: [], flavor: 'Flies into the glass door every Monday. Every. Single. Monday.' },
      { name: 'Pterodactie', acc: ['tie'], flavor: 'Has no neck, so it wears the tie on its belly. Nobody has told it.' },
      { name: 'Pterodirector', acc: ['tie', 'shades'], flavor: 'Circles the open-plan office hunting for idle browser tabs.' },
    ],
  },
  {
    body: 'ankylo', dept: 'IT', move: 'Reply-All Club', base: [65, 45, 75, 25],
    palette: { B: '#b08968', L: '#ecdcc8', D: '#6b4f3a' },
    shiny:   { B: '#85929e', L: '#e5e8e8', D: '#2e4053' },
    stages: [
      { name: 'Grumpylosaurus', acc: [], flavor: 'Armored against small talk. The tail club is for "quick calls".' },
      { name: 'Grumpylo Barista', acc: ['mug'], flavor: 'Nine coffees in. Still grumpy. Now also fast.' },
      { name: 'Grumpylo Overlord', acc: ['mug', 'crown'], flavor: 'Rules the break room. The microwave queue answers to it.' },
    ],
  },
  {
    body: 'bonk', dept: 'HR', move: 'Team-Building Headbutt', base: [55, 66, 50, 39],
    palette: { B: '#f28cb1', L: '#ffe0ec', D: '#c2577f' },
    shiny:   { B: '#f7dc6f', L: '#fef9e7', D: '#b7950b' },
    stages: [
      { name: 'Bonkhead', acc: [], flavor: 'Settles arguments by headbutting the whiteboard. Whiteboard: 0, Bonkhead: 47.' },
      { name: 'Partyheadosaurus', acc: ['party'], flavor: 'Attends every office birthday, including the made-up ones.' },
      { name: 'Bonkasaurus Prime', acc: ['viking'], flavor: 'Wears a helmet to performance reviews. Smart.' },
    ],
  },
];

const RARITY = ['Common', 'Uncommon', 'Rare'];
const CATCH_CHANCE = [0.6, 0.38, 0.2];
const QUIZ_BONUS = 0.3;
const FLEE_CHANCE = 0.25;

// ─────────────────────────────── Pure helpers ───────────────────────────────

function fnv1a(str) {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function randInt(rng, n) {
  return Math.floor(rng() * n);
}

function todayUTC() {
  return new Date().toISOString().slice(0, 10);
}

function pad(n, width) {
  return String(n).padStart(width, '0');
}

function speciesInfo(sp) {
  const lineIdx = Math.floor(sp / 3);
  const stage = sp % 3;
  const line = LINES[lineIdx];
  return {
    sp: sp, lineIdx: lineIdx, stage: stage, line: line, dept: line.dept,
    name: line.stages[stage].name, flavor: line.stages[stage].flavor,
  };
}

function pickStage(rng, weights) {
  const r = rng();
  if (r < weights[0]) return 0;
  if (r < weights[0] + weights[1]) return 1;
  return 2;
}

function makeDino(sp, shiny, rng, lv) {
  return {
    sp: sp,
    shiny: !!shiny,
    iv: [randInt(rng, 16), randInt(rng, 16), randInt(rng, 16), randInt(rng, 16)],
    lv: lv,
  };
}

function wildDino(rng) {
  const sp = randInt(rng, LINES.length) * 3 + pickStage(rng, [0.7, 0.25]);
  return makeDino(sp, randInt(rng, WILD_SHINY_ODDS) === 0, rng, 1 + randInt(rng, 5));
}

/** The same Dino of the Day for every player on Earth, picked from the UTC date. */
function dinoOfTheDay(day) {
  const rng = mulberry32(fnv1a('dotd:' + day));
  const sp = randInt(rng, LINES.length) * 3 + pickStage(rng, [0.45, 0.35]);
  const shiny = randInt(rng, 16) === 0;
  return makeDino(sp, shiny, rng, 5);
}

/** [hp, atk, def, spd] */
function computeStats(d) {
  const info = speciesInfo(d.sp);
  const mult = 1 + 0.45 * info.stage;
  const lvMult = 1 + (d.lv - 1) * 0.03;
  return info.line.base.map(function (b, i) {
    return Math.round((b * mult + d.iv[i] * 2) * lvMult);
  });
}

function power(d) {
  return computeStats(d).reduce(function (a, b) { return a + b; }, 0);
}

function makeQuiz(rng) {
  const n = function (lo, hi) { return lo + randInt(rng, hi - lo + 1); };
  const kind = randInt(rng, 5);
  if (kind === 0) {
    const a = n(2, 40), b = n(2, 40), c = n(2, 40);
    return { q: '=SUM(' + a + ', ' + b + ', ' + c + ')', a: a + b + c };
  }
  if (kind === 1) {
    const xs = [n(1, 99), n(1, 99), n(1, 99), n(1, 99)];
    return { q: '=MAX(' + xs.join(', ') + ')', a: Math.max.apply(null, xs) };
  }
  if (kind === 2) {
    const xs = [n(1, 99), n(1, 99), n(1, 99), n(1, 99)];
    return { q: '=MIN(' + xs.join(', ') + ')', a: Math.min.apply(null, xs) };
  }
  if (kind === 3) {
    const a = n(2, 60);
    const b = a + 2 * n(1, 20);
    return { q: '=AVERAGE(' + a + ', ' + b + ')', a: (a + b) / 2 };
  }
  const a = n(2, 12), b = n(2, 12);
  return { q: '=PRODUCT(' + a + ', ' + b + ')', a: a * b };
}

// ─────────────────────────────── Sprites ───────────────────────────────

/**
 * Returns a CANVAS_H × CANVAS_W grid of hex colors (null = transparent).
 * mode: 'color' | 'silhouette'
 */
function spriteGrid(sp, shiny, mode) {
  const info = speciesInfo(sp);
  const body = BODIES[info.line.body];
  const palette = shiny ? info.line.shiny : info.line.palette;
  const grid = [];
  for (let y = 0; y < CANVAS_H; y++) grid.push(new Array(CANVAS_W).fill(null));

  const h = body.rows.length;
  const w = Math.max.apply(null, body.rows.map(function (r) { return r.length; }));
  const ox = Math.floor((CANVAS_W - w) / 2);
  const oy = CANVAS_H - 1 - h; // leave the bottom row for grass

  const paint = function (x, y, color) {
    if (x >= 0 && x < CANVAS_W && y >= 0 && y < CANVAS_H) grid[y][x] = color;
  };

  body.rows.forEach(function (row, y) {
    for (let x = 0; x < row.length; x++) {
      const ch = row[x];
      if (ch === '.') continue;
      paint(ox + x, oy + y, palette[ch] || FIXED_COLORS[ch]);
    }
  });

  info.line.stages[info.stage].acc.forEach(function (name) {
    const acc = ACCESSORIES[name];
    const anchor = body.anchors[acc.at];
    const ax = ox + anchor[0] + acc.ox;
    const ay = oy + anchor[1] + acc.oy;
    acc.rows.forEach(function (row, y) {
      for (let x = 0; x < row.length; x++) {
        const ch = row[x];
        if (ch === '.') continue;
        paint(ax + x, ay + y, ACCESSORY_COLORS[ch]);
      }
    });
  });

  if (mode === 'silhouette') {
    for (let y = 0; y < CANVAS_H; y++) {
      for (let x = 0; x < CANVAS_W; x++) if (grid[y][x]) grid[y][x] = SILHOUETTE;
    }
  }
  return grid;
}

function sceneGrid(dino) {
  const grid = dino ? spriteGrid(dino.sp, dino.shiny, 'color') : null;
  const out = [];
  for (let y = 0; y < CANVAS_H; y++) {
    const row = [];
    for (let x = 0; x < CANVAS_W; x++) {
      const c = grid && grid[y][x];
      row.push(c || (y === CANVAS_H - 1 ? GRASS : SKY));
    }
    out.push(row);
  }
  return out;
}

// ─────────────────────────────── Trade codes ───────────────────────────────
// A dino packs into 40 bits: species(5) shiny(1) ivs(4×4) level(6) salt(12).
// That's 8 Crockford base-32 characters, plus a 2-character checksum.

const B32 = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

function toB32(value, len) {
  let s = '';
  for (let i = 0; i < len; i++) {
    s = B32[value % 32] + s;
    value = Math.floor(value / 32);
  }
  return s;
}

function fromB32(str) {
  let v = 0;
  for (let i = 0; i < str.length; i++) {
    const d = B32.indexOf(str[i]);
    if (d < 0) return -1;
    v = v * 32 + d;
  }
  return v;
}

function checksum(payload) {
  return toB32(fnv1a(payload + '|spreadsaurs') % 1024, 2);
}

function packDino(d, salt) {
  let v = d.sp;
  v = v * 2 + (d.shiny ? 1 : 0);
  d.iv.forEach(function (iv) { v = v * 16 + iv; });
  v = v * 64 + Math.min(63, Math.max(0, d.lv - 1));
  v = v * 4096 + (salt % 4096);
  return toB32(v, 8);
}

function unpackDino(chunk) {
  let v = fromB32(chunk);
  if (v < 0) return null;
  v = Math.floor(v / 4096);
  const lv = (v % 64) + 1; v = Math.floor(v / 64);
  const iv = [];
  for (let i = 0; i < 4; i++) { iv.unshift(v % 16); v = Math.floor(v / 16); }
  const shiny = v % 2 === 1; v = Math.floor(v / 2);
  const sp = v;
  if (sp >= SPECIES_COUNT || lv > MAX_LEVEL) return null;
  return { sp: sp, shiny: shiny, iv: iv, lv: lv };
}

function normalizeCode(raw, prefix) {
  let s = String(raw || '').toUpperCase().replace(/[^0-9A-Z]/g, '');
  if (s.indexOf(prefix) !== 0) return null;
  s = s.slice(prefix.length).replace(/O/g, '0').replace(/[IL]/g, '1');
  return s;
}

function encodeDinoCode(d, salt) {
  const p = packDino(d, salt);
  return 'DINO-' + p.slice(0, 4) + '-' + p.slice(4, 8) + '-' + checksum(p);
}

/** Returns { dino, key } or null. `key` identifies the code so it can only be redeemed once. */
function decodeDinoCode(raw) {
  const s = normalizeCode(raw, 'DINO');
  if (!s || s.length !== 10) return null;
  const p = s.slice(0, 8);
  if (checksum(p) !== s.slice(8)) return null;
  const dino = unpackDino(p);
  return dino ? { dino: dino, key: p } : null;
}

function encodeTeamCode(team) {
  const p = team.map(function (d) { return packDino(d, 0); }).join('');
  const groups = p.match(/.{8}/g);
  return 'TEAM-' + groups.join('-') + '-' + checksum('T' + p);
}

function decodeTeamCode(raw) {
  const s = normalizeCode(raw, 'TEAM');
  if (!s || (s.length - 2) % 8 !== 0 || s.length < 10 || s.length > 26) return null;
  const p = s.slice(0, -2);
  if (checksum('T' + p) !== s.slice(-2)) return null;
  const team = p.match(/.{8}/g).map(unpackDino);
  if (team.some(function (d) { return !d; })) return null;
  return { team: team, key: p };
}

// ─────────────────────────────── Battles ───────────────────────────────

function typeMultiplier(attDept, defDept) {
  if (DEPTS[attDept].beats === defDept) return 1.5;
  if (DEPTS[defDept].beats === attDept) return 0.75;
  return 1;
}

/**
 * Simulates a 3v3 battle. Deterministic for a given seed, so both players see the same fight.
 * teamA / teamB: arrays of { sp, shiny, iv, lv, name? }.
 * Returns { winner: 'A' | 'B', log: string[] }.
 */
function simulateBattle(teamA, teamB, seed, labelA, labelB) {
  const rng = mulberry32(seed);
  const toFighter = function (d) {
    const info = speciesInfo(d.sp);
    const st = computeStats(d);
    return {
      name: (d.name || info.name) + (d.shiny ? ' ✨' : ''),
      dept: info.dept, move: info.line.move,
      hp: st[0] * 2, maxHp: st[0] * 2, atk: st[1], def: st[2], spd: st[3],
    };
  };
  const A = teamA.map(toFighter);
  const B = teamB.map(toFighter);
  const log = [];
  let ia = 0, ib = 0, turns = 0;

  log.push(labelA + ' sends out ' + A[0].name + '!  ' + labelB + ' sends out ' + B[0].name + '!');
  while (ia < A.length && ib < B.length && turns < 300) {
    turns++;
    const a = A[ia], b = B[ib];
    const aFirst = a.spd > b.spd || (a.spd === b.spd && rng() < 0.5);
    const order = aFirst ? [[a, b, 'A'], [b, a, 'B']] : [[b, a, 'B'], [a, b, 'A']];
    for (let k = 0; k < 2; k++) {
      const att = order[k][0], def = order[k][1];
      if (att.hp <= 0 || def.hp <= 0) continue;
      const signature = rng() < 0.7;
      const mult = signature ? typeMultiplier(att.dept, def.dept) : 1;
      const crit = rng() < 1 / 16 ? 1.5 : 1;
      const roll = 0.85 + rng() * 0.15;
      const dmg = Math.max(1, Math.round(att.atk * 0.6 * (att.atk / (att.atk + def.def)) * mult * crit * roll));
      def.hp = Math.max(0, def.hp - dmg);
      let line = att.name + ' used ' + (signature ? att.move : 'Tail Slap') + '! (−' + dmg + ' HP)';
      if (mult > 1) line += ' It\'s super effective ' + DEPTS[att.dept].emoji;
      if (mult < 1) line += ' Not very effective…';
      if (crit > 1) line += ' CRITICAL HIT (they were cc\'d)';
      log.push(line);
      if (def.hp <= 0) {
        log.push('💤 ' + def.name + ' fainted… (went to lunch)');
        if (order[k][2] === 'A') {
          ib++;
          if (ib < B.length) log.push(labelB + ' sends out ' + B[ib].name + '!');
        } else {
          ia++;
          if (ia < A.length) log.push(labelA + ' sends out ' + A[ia].name + '!');
        }
      }
    }
  }

  let winner;
  if (ia >= A.length) winner = 'B';
  else if (ib >= B.length) winner = 'A';
  else {
    // Ran out of turns: whoever has more HP left (as a share) wins.
    const share = function (team) {
      return team.reduce(function (s, f) { return s + f.hp / f.maxHp; }, 0);
    };
    winner = share(A) >= share(B) ? 'A' : 'B';
  }
  return { winner: winner, log: log };
}

function bossTeam(day) {
  const rng = mulberry32(fnv1a('boss:' + day));
  const team = [];
  for (let i = 0; i < 3; i++) {
    const sp = randInt(rng, LINES.length) * 3 + (i === 2 ? 2 : 1 + randInt(rng, 2));
    const d = makeDino(sp, false, rng, 6 + randInt(rng, 7));
    d.name = 'Auditor\'s ' + speciesInfo(sp).name;
    team.push(d);
  }
  return team;
}

// ─────────────────────────────── State ───────────────────────────────

function defaultState() {
  return {
    day: '',
    snacks: SNACKS_PER_DAY,
    dotdDone: false,
    dotdTries: 0,
    encounter: null,
    seen: new Array(SPECIES_COUNT).fill(false),
    caught: new Array(SPECIES_COUNT).fill(false),
    shinyCaught: 0,
    nextId: 1,
    usedCodes: [],
    beaten: [],
    bossDone: false,
    share: '',
  };
}

function rollDay(st) {
  const today = todayUTC();
  if (st.day === today) return;
  st.day = today;
  st.snacks = SNACKS_PER_DAY;
  st.dotdDone = false;
  st.dotdTries = 0;
  st.beaten = [];
  st.bossDone = false;
  st.share = '';
  if (st.encounter && st.encounter.dotd) st.encounter = null;
}

function loadState(ss) {
  let sheet = ss.getSheetByName(SHEETS.state);
  if (!sheet) {
    sheet = ss.insertSheet(SHEETS.state);
    sheet.hideSheet();
  }
  const st = defaultState();
  const last = sheet.getLastRow();
  if (last > 0) {
    sheet.getRange(1, 1, last, 2).getValues().forEach(function (row) {
      if (row[0] && row[1] !== '') {
        try { st[row[0]] = JSON.parse(row[1]); } catch (err) { /* ignore a corrupted key */ }
      }
    });
  }
  return st;
}

function saveState(ss, st) {
  const sheet = ss.getSheetByName(SHEETS.state);
  const keys = Object.keys(st);
  sheet.clearContents();
  // Plain-text format stops Sheets from turning stored JSON like "false" into a checkbox value or a date.
  sheet.getRange(1, 1, keys.length, 2).setNumberFormat('@');
  sheet.getRange(1, 1, keys.length, 2).setValues(keys.map(function (k) {
    return [k, JSON.stringify(st[k])];
  }));
}

// ─────────────────────────────── Collection sheet I/O ───────────────────────────────

const COL = {
  id: 1, species: 2, nick: 3, dept: 4, stage: 5, shiny: 6, lv: 7,
  hp: 8, atk: 9, def: 10, spd: 11, power: 12, team: 13, send: 14, caught: 15, dna: 16,
};
const COLLECTION_HEADERS = [
  'ID', 'Species', 'Nickname', 'Dept', 'Stage', 'Shiny', 'Lv',
  'HP', 'ATK', 'DEF', 'SPD', 'Power', 'Team ⚔️', 'Send ✉️', 'Caught', 'dna',
];
const FIRST_DATA_ROW = 4;

function readCollection(ss) {
  const sheet = ss.getSheetByName(SHEETS.collection);
  const last = sheet.getLastRow();
  if (last < FIRST_DATA_ROW) return [];
  const rows = sheet.getRange(FIRST_DATA_ROW, 1, last - FIRST_DATA_ROW + 1, COL.dna).getValues();
  const list = [];
  rows.forEach(function (r, i) {
    const dna = String(r[COL.dna - 1] || '');
    const parts = dna.split('|');
    if (!r[0] || parts.length !== 3) return;
    list.push({
      row: FIRST_DATA_ROW + i,
      id: String(r[COL.id - 1]),
      nick: String(r[COL.nick - 1] || ''),
      team: r[COL.team - 1] === true,
      caught: r[COL.caught - 1],
      sp: Number(parts[0]),
      shiny: parts[1] === '1',
      iv: parts[2].split(',').map(Number),
      lv: Number(r[COL.lv - 1]) || 1,
    });
  });
  return list;
}

function writeCollection(ss, list) {
  const sheet = ss.getSheetByName(SHEETS.collection);
  const last = Math.max(sheet.getLastRow(), FIRST_DATA_ROW);
  const clearRows = last - FIRST_DATA_ROW + 1;
  const old = sheet.getRange(FIRST_DATA_ROW, 1, clearRows, COL.dna);
  old.clearContent();
  old.clearDataValidations();
  if (!list.length) return;

  const values = list.map(function (d) {
    const info = speciesInfo(d.sp);
    const st = computeStats(d);
    return [
      d.id, info.name, d.nick, DEPTS[info.dept].emoji + ' ' + info.dept, info.stage + 1,
      d.shiny ? '✨' : '', d.lv, st[0], st[1], st[2], st[3], power(d),
      d.team, false, d.caught, d.sp + '|' + (d.shiny ? 1 : 0) + '|' + d.iv.join(','),
    ];
  });
  sheet.getRange(FIRST_DATA_ROW, 1, values.length, COL.dna).setValues(values);
  sheet.getRange(FIRST_DATA_ROW, COL.team, values.length, 2).insertCheckboxes();
  // insertCheckboxes resets values, so restore the team ticks.
  sheet.getRange(FIRST_DATA_ROW, COL.team, values.length, 1).setValues(values.map(function (v) {
    return [v[COL.team - 1]];
  }));
}

function newId(st) {
  return '#' + pad(st.nextId++, 4);
}

function addToCollection(ss, st, dino) {
  const list = readCollection(ss);
  const entry = {
    id: newId(st), nick: '', team: false, caught: todayUTC(),
    sp: dino.sp, shiny: dino.shiny, iv: dino.iv.slice(), lv: dino.lv,
  };
  list.push(entry);
  writeCollection(ss, list);
  st.seen[dino.sp] = true;
  st.caught[dino.sp] = true;
  if (dino.shiny) st.shinyCaught++;
  return entry;
}

function getTeam(list) {
  const picked = list.filter(function (d) { return d.team; }).slice(0, 3);
  if (picked.length) return picked;
  return list.slice().sort(function (a, b) { return power(b) - power(a); }).slice(0, 3);
}

function displayName(d) {
  return d.nick ? d.nick : speciesInfo(d.sp).name;
}

// ─────────────────────────────── Game actions ───────────────────────────────

function withGame(fn) {
  const ss = SpreadsheetApp.getActive();
  const st = loadState(ss);
  rollDay(st);
  const result = fn(ss, st);
  saveState(ss, st);
  return result;
}

function actionLook() {
  withGame(function (ss, st) {
    let enc;
    if (!st.dotdDone) {
      enc = dinoOfTheDay(st.day);
      enc.dotd = true;
    } else {
      enc = wildDino(Math.random);
      enc.dotd = false;
    }
    enc.day = st.day;
    enc.tries = 0;
    enc.quiz = makeQuiz(Math.random);
    st.encounter = enc;
    st.seen[enc.sp] = true;
    const name = speciesInfo(enc.sp).name + (enc.shiny ? ' ✨' : '');
    const msg = enc.dotd
      ? '🌟 The DINO OF THE DAY appeared: ' + name + '! Every player sees this one today.'
      : 'A wild ' + name + ' wandered out of the pivot tables!';
    refreshEncounter(ss, st, msg);
    renderDex(ss, st);
  });
}

function actionThrow() {
  withGame(function (ss, st) {
    const sheet = ss.getSheetByName(SHEETS.encounter);
    const enc = st.encounter;
    if (!enc) return refreshEncounter(ss, st, 'Nothing here yet. Tick 🔍 Look for dinos first.');
    if (st.snacks <= 0) {
      return refreshEncounter(ss, st, 'Out of snacks! New ones arrive at midnight UTC, or beat the Daily Boss for +' + BOSS_SNACK_REWARD + '.');
    }
    const answer = sheet.getRange('V9').getValue();
    const correct = answer !== '' && Math.abs(Number(answer) - enc.quiz.a) < 1e-9;
    st.snacks--;
    enc.tries++;
    if (enc.dotd) st.dotdTries = enc.tries;

    const info = speciesInfo(enc.sp);
    const chance = CATCH_CHANCE[info.stage] + (correct ? QUIZ_BONUS : 0) - (enc.shiny ? 0.05 : 0);
    const name = info.name + (enc.shiny ? ' ✨' : '');
    const quizNote = answer === '' ? '' : (correct ? ' Formula correct, +30% catch chance!' : ' Wrong answer (it was ' + enc.quiz.a + ').');

    if (Math.random() < chance) {
      const entry = addToCollection(ss, st, enc);
      if (enc.dotd) {
        st.dotdDone = true;
        st.share = shareText(st, info, enc);
      }
      st.encounter = null;
      sheet.getRange('V9').clearContent();
      refreshEncounter(ss, st, '🎉 Gotcha!' + quizNote + ' ' + name + ' joined your Collection as ' + entry.id + '.', enc);
      renderDex(ss, st);
      return;
    }

    enc.quiz = makeQuiz(Math.random);
    sheet.getRange('V9').clearContent();
    if (!enc.dotd && Math.random() < FLEE_CHANCE) {
      st.encounter = null;
      return refreshEncounter(ss, st, '💨 ' + name + ' ate the snack and ran off to a meeting.' + quizNote);
    }
    refreshEncounter(ss, st, 'So close! ' + name + ' sniffed the snack and backed away.' + quizNote + ' Try again.');
  });
}

function actionRun() {
  withGame(function (ss, st) {
    const was = st.encounter;
    st.encounter = null;
    const msg = was && was.dotd
      ? 'You walked away. The Dino of the Day will still be here when you come back.'
      : 'You backed away slowly and pretended to check your email.';
    refreshEncounter(ss, st, msg);
  });
}

function shareText(st, info, enc) {
  const caughtCount = st.caught.filter(Boolean).length;
  return '🦖 SPREADSAURS ' + st.day + ' · Dino of the Day: ' + info.name + (enc.shiny ? ' ✨' : '') +
    ' · caught with ' + '🍪'.repeat(enc.tries) + ' · Dex ' + caughtCount + '/' + SPECIES_COUNT;
}

function actionSend(row) {
  withGame(function (ss, st) {
    const list = readCollection(ss);
    const idx = list.findIndex(function (d) { return d.row === row; });
    if (idx < 0) return;
    const d = list[idx];
    const code = encodeDinoCode(d, Math.floor(Math.random() * 4096));
    st.usedCodes.push(decodeDinoCode(code).key);
    list.splice(idx, 1);
    writeCollection(ss, list);
    const trade = ss.getSheetByName(SHEETS.trade);
    trade.getRange('C4').setValue(code);
    setTradeMessage(ss, '✉️ ' + displayName(d) + ' is packed in a box. Send the code above to a friend. (Only one person can redeem it.)');
    ss.setActiveSheet(trade);
  });
}

function actionReceive() {
  withGame(function (ss, st) {
    const trade = ss.getSheetByName(SHEETS.trade);
    const raw = trade.getRange('C6').getValue();
    const decoded = decodeDinoCode(raw);
    if (!decoded) return setTradeMessage(ss, '❌ That doesn\'t look like a valid DINO code. Check for typos.');
    if (st.usedCodes.indexOf(decoded.key) >= 0) return setTradeMessage(ss, '❌ This code was already used in this sheet.');
    st.usedCodes.push(decoded.key);
    const entry = addToCollection(ss, st, decoded.dino);
    trade.getRange('C6').clearContent();
    renderDex(ss, st);
    setTradeMessage(ss, '📦 You unboxed ' + speciesInfo(decoded.dino.sp).name + (decoded.dino.shiny ? ' ✨' : '') +
      ' (Lv ' + decoded.dino.lv + ')! It\'s in your Collection as ' + entry.id + '.');
  });
}

function actionTeamCode() {
  withGame(function (ss, st) {
    const team = getTeam(readCollection(ss));
    if (!team.length) return setTradeMessage(ss, 'Catch a dino first, then you can make a team code.');
    const code = encodeTeamCode(team);
    ss.getSheetByName(SHEETS.trade).getRange('C8').setValue(code);
    setTradeMessage(ss, '🛡️ Team code ready: ' + team.map(displayName).join(', ') +
      '. Post it anywhere and let people battle you. (Tick ⚔️ Team in Collection to pick your 3.)');
  });
}

function actionBattle() {
  withGame(function (ss, st) {
    const trade = ss.getSheetByName(SHEETS.trade);
    const decoded = decodeTeamCode(trade.getRange('C10').getValue());
    if (!decoded) return setTradeMessage(ss, '❌ That doesn\'t look like a valid TEAM code.');
    const list = readCollection(ss);
    const mine = getTeam(list);
    if (!mine.length) return setTradeMessage(ss, 'You need at least one dino to battle.');
    const myKey = mine.map(function (d) { return packDino(d, 0); }).join('');
    if (myKey === decoded.key) return setTradeMessage(ss, 'That\'s your own team code. Battling yourself is called "a Tuesday".');

    // Both players get the same seed (and the same fight) no matter who runs it.
    const meFirst = myKey < decoded.key;
    const seed = fnv1a((meFirst ? myKey + '|' + decoded.key : decoded.key + '|' + myKey) + '|' + st.day);
    const myTeam = mine.map(function (d) { return withName(d); });
    const result = meFirst
      ? simulateBattle(myTeam, decoded.team, seed, 'You', 'Rival')
      : simulateBattle(decoded.team, myTeam, seed, 'Rival', 'You');
    const won = (result.winner === 'A') === meFirst;

    let reward = '';
    if (won && st.beaten.indexOf(decoded.key) < 0) {
      st.beaten.push(decoded.key);
      levelUp(ss, list, mine);
      reward = ' Your team gained +1 level.';
    }
    writeBattleLog(ss, result.log, won ? '🏆 YOU WIN!' + reward : '😵 You lost. Same teams get a rematch tomorrow.');
  });
}

function actionBoss() {
  withGame(function (ss, st) {
    const list = readCollection(ss);
    const mine = getTeam(list);
    if (!mine.length) return setTradeMessage(ss, 'You need at least one dino to face The Auditor.');
    const boss = bossTeam(st.day);
    const myKey = mine.map(function (d) { return packDino(d, 0); }).join('');
    const result = simulateBattle(mine.map(withName), boss, fnv1a('bossfight:' + st.day + '|' + myKey), 'You', 'The Auditor');
    const won = result.winner === 'A';
    let reward = '';
    if (won && !st.bossDone) {
      st.bossDone = true;
      st.snacks += BOSS_SNACK_REWARD;
      levelUp(ss, list, mine);
      reward = ' +' + BOSS_SNACK_REWARD + ' snacks and +1 level for your team.';
    } else if (won) {
      reward = ' (Today\'s reward already claimed.)';
    }
    writeBattleLog(ss, result.log, won
      ? '🏆 The Auditor has been audited!' + reward
      : '📋 The Auditor found discrepancies. Try a different team (the fight replays the same way with the same team).');
    refreshEncounter(ss, st, null);
  });
}

function actionEvolve() {
  withGame(function (ss, st) {
    let list = readCollection(ss);
    const evolved = [];
    for (let sp = 0; sp < SPECIES_COUNT; sp++) {
      if (sp % 3 === 2) continue;
      let group = list.filter(function (d) { return d.sp === sp; });
      while (group.length >= 3) {
        group.sort(function (a, b) {
          if (a.team !== b.team) return a.team ? 1 : -1;
          return power(a) - power(b);
        });
        const used = group.slice(0, 3);
        const child = {
          id: newId(st), nick: '', team: used.some(function (d) { return d.team; }), caught: todayUTC(),
          sp: sp + 1,
          shiny: used.some(function (d) { return d.shiny; }),
          iv: [0, 1, 2, 3].map(function (i) { return Math.max.apply(null, used.map(function (d) { return d.iv[i]; })); }),
          lv: Math.max.apply(null, used.map(function (d) { return d.lv; })),
        };
        list = list.filter(function (d) { return used.indexOf(d) < 0; });
        list.push(child);
        st.seen[sp + 1] = true;
        st.caught[sp + 1] = true;
        evolved.push(speciesInfo(sp).name + ' → ' + speciesInfo(sp + 1).name);
        group = group.slice(3);
      }
    }
    const sheet = ss.getSheetByName(SHEETS.collection);
    if (!evolved.length) {
      sheet.getRange('C2').setValue('Nothing to evolve yet: you need 3 of the same species (stage 1 or 2).');
      return;
    }
    writeCollection(ss, list);
    renderDex(ss, st);
    sheet.getRange('C2').setValue('🧬 Evolved: ' + evolved.join(' · '));
    notify(ss, '🧬 ' + evolved.join(' · '));
  });
}

function withName(d) {
  const copy = { sp: d.sp, shiny: d.shiny, iv: d.iv, lv: d.lv };
  if (d.nick) copy.name = d.nick;
  return copy;
}

function levelUp(ss, list, team) {
  const ids = team.map(function (d) { return d.id; });
  list.forEach(function (d) {
    if (ids.indexOf(d.id) >= 0) d.lv = Math.min(MAX_LEVEL, d.lv + 1);
  });
  writeCollection(ss, list);
}

// ─────────────────────────────── Boss key ───────────────────────────────

function bossKey() {
  const ss = SpreadsheetApp.getActive();
  const decoy = ss.getSheetByName(SHEETS.decoy) || buildDecoy(ss);
  decoy.showSheet();
  ss.setActiveSheet(decoy);
  GAME_SHEETS.forEach(function (key) {
    const sh = ss.getSheetByName(SHEETS[key]);
    if (sh) sh.hideSheet();
  });
}

function restoreGame() {
  const ss = SpreadsheetApp.getActive();
  GAME_SHEETS.forEach(function (key) {
    const sh = ss.getSheetByName(SHEETS[key]);
    if (sh) sh.showSheet();
  });
  ss.setActiveSheet(ss.getSheetByName(SHEETS.encounter));
}

// ─────────────────────────────── Rendering ───────────────────────────────

function refreshEncounter(ss, st, message, shownDino) {
  const sheet = ss.getSheetByName(SHEETS.encounter);
  const enc = st.encounter;
  const dino = enc || shownDino || null;
  sheet.getRange(3, 2, CANVAS_H, CANVAS_W).setBackgrounds(sceneGrid(dino));

  let status = 'The office is quiet… tick 🔍 to look for dinos.';
  let details = '';
  let flavor = '';
  if (dino) {
    const info = speciesInfo(dino.sp);
    status = (enc ? (enc.dotd ? '🌟 Dino of the Day: ' : 'Wild ') : 'Caught: ') + info.name + (dino.shiny ? ' ✨ SHINY' : '');
    details = DEPTS[info.dept].emoji + ' ' + info.dept + ' · ' + RARITY[info.stage] + ' · Lv ' + dino.lv +
      ' · #' + pad(dino.sp + 1, 2);
    flavor = '“' + info.flavor + '”';
  }
  sheet.getRange('U3').setValue(status);
  sheet.getRange('U4').setValue(details);
  sheet.getRange('U5').setValue(flavor);
  sheet.getRange('U9').setValue(enc ? 'Earn its trust: what is  ' + enc.quiz.q + '  ?' : '');
  sheet.getRange('U15').setValue('🍪 Snacks left today: ' + st.snacks);
  sheet.getRange('U16').setValue(st.dotdDone
    ? '🌟 Dino of the Day: caught! Come back tomorrow for a new one.'
    : '🌟 Dino of the Day: still out there. Your first 🔍 of the day finds it.');
  sheet.getRange('U19').setValue(st.share || '(Catch the Dino of the Day to get your share line.)');
  if (message !== null && message !== undefined) {
    sheet.getRange('U23').setValue(message);
    notify(ss, message);
  }
}

function renderDex(ss, st) {
  const sheet = ss.getSheetByName(SHEETS.dex);
  const blockW = CANVAS_W + 1;
  const blockH = CANVAS_H + 3;
  const cols = 6 * blockW;
  const rows = 4 * blockH;
  const bg = [];
  const vals = [];
  for (let y = 0; y < rows; y++) {
    bg.push(new Array(cols).fill('#ffffff'));
    vals.push(new Array(cols).fill(''));
  }
  for (let sp = 0; sp < SPECIES_COUNT; sp++) {
    const r0 = Math.floor(sp / 6) * blockH;
    const c0 = (sp % 6) * blockW;
    const info = speciesInfo(sp);
    const grid = spriteGrid(sp, false, st.caught[sp] ? 'color' : 'silhouette');
    if (st.seen[sp] || st.caught[sp]) {
      for (let y = 0; y < CANVAS_H; y++) {
        for (let x = 0; x < CANVAS_W; x++) if (grid[y][x]) bg[r0 + y][c0 + x] = grid[y][x];
      }
    } else {
      // Never seen: a faint "?" card.
      for (let y = 2; y < CANVAS_H - 1; y++) {
        for (let x = 1; x < CANVAS_W - 1; x++) bg[r0 + y][c0 + x] = '#f1f3f6';
      }
    }
    vals[r0 + CANVAS_H][c0] = '#' + pad(sp + 1, 2) + ' ' + (st.seen[sp] || st.caught[sp] ? info.name : '???');
    vals[r0 + CANVAS_H + 1][c0] = st.caught[sp] ? DEPTS[info.dept].emoji + ' ' + info.dept + ' · ' + RARITY[info.stage] : (st.seen[sp] ? 'seen, not caught' : '');
  }
  sheet.getRange(3, 2, rows, cols).setBackgrounds(bg).setValues(vals);
  const caught = st.caught.filter(Boolean).length;
  const seen = st.seen.filter(Boolean).length;
  sheet.getRange('A1').setValue('📖 DEX   ' + caught + '/' + SPECIES_COUNT + ' caught · ' + seen + ' seen · ✨ ' + st.shinyCaught + ' shiny');
}

function setTradeMessage(ss, msg) {
  ss.getSheetByName(SHEETS.trade).getRange('B14').setValue(msg);
  notify(ss, msg);
}

function writeBattleLog(ss, lines, verdict) {
  const sheet = ss.getSheetByName(SHEETS.trade);
  const maxLines = 120;
  sheet.getRange(17, 2, maxLines + 1, 1).clearContent();
  const shown = lines.length > maxLines ? lines.slice(0, maxLines - 1).concat(['… (' + (lines.length - maxLines + 1) + ' more moves)']) : lines;
  sheet.getRange(17, 2, shown.length, 1).setValues(shown.map(function (l) { return [l]; }));
  setTradeMessage(ss, verdict);
}

function notify(ss, msg) {
  try { ss.toast(msg, 'Spreadsaurs 🦖', 6); } catch (err) { /* toasts are optional */ }
}

// ─────────────────────────────── Layout ───────────────────────────────

function getOrCreate(ss, name) {
  return ss.getSheetByName(name) || ss.insertSheet(name);
}

function ensureSize(sheet, rows, cols) {
  if (sheet.getMaxRows() < rows) sheet.insertRowsAfter(sheet.getMaxRows(), rows - sheet.getMaxRows());
  if (sheet.getMaxColumns() < cols) sheet.insertColumnsAfter(sheet.getMaxColumns(), cols - sheet.getMaxColumns());
}

function label(sheet, a1, text, opts) {
  const r = sheet.getRange(a1).setValue(text);
  opts = opts || {};
  if (opts.size) r.setFontSize(opts.size);
  if (opts.bold) r.setFontWeight('bold');
  if (opts.color) r.setFontColor(opts.color);
  if (opts.italic) r.setFontStyle('italic');
  return r;
}

function checkbox(sheet, a1) {
  sheet.getRange(a1).insertCheckboxes().setValue(false).setHorizontalAlignment('center');
}

function buildDecoy(ss) {
  const sheet = getOrCreate(ss, SHEETS.decoy);
  sheet.clear();
  sheet.setColumnWidth(1, 170);
  sheet.setColumnWidths(2, 6, 110);
  label(sheet, 'A1', 'FY25 Operating Budget: Draft v3 (CONFIDENTIAL)', { size: 14, bold: true });
  label(sheet, 'A2', 'Owner: Finance Ops · Do not forward', { italic: true, color: '#666666' });
  const header = [['Department', 'Q1', 'Q2', 'Q3', 'Q4', 'FY Total', 'vs. Plan']];
  sheet.getRange('A3:G3').setValues(header).setFontWeight('bold').setBackground('#e8eaed');
  const depts = [
    ['Engineering', 1420000, 1465000, 1510000, 1530000, 0.021],
    ['Sales', 980000, 1010000, 1045000, 1120000, -0.013],
    ['Marketing', 610000, 585000, 640000, 705000, 0.034],
    ['Customer Success', 410000, 415000, 428000, 431000, -0.004],
    ['G&A', 355000, 352000, 361000, 366000, 0.008],
    ['People / HR', 228000, 231000, 236000, 240000, -0.011],
    ['Facilities', 190000, 190000, 196000, 205000, 0.017],
    ['IT', 265000, 271000, 268000, 284000, 0.026],
    ['Legal', 142000, 138000, 151000, 149000, -0.019],
    ['R&D Programs', 320000, 344000, 362000, 371000, 0.042],
  ];
  depts.forEach(function (d, i) {
    const row = 4 + i;
    sheet.getRange(row, 1, 1, 5).setValues([d.slice(0, 5)]);
    sheet.getRange(row, 6).setFormula('=SUM(B' + row + ':E' + row + ')');
    sheet.getRange(row, 7).setValue(d[5]);
  });
  sheet.getRange('A14').setValue('Total').setFontWeight('bold');
  ['B', 'C', 'D', 'E', 'F'].forEach(function (c) {
    sheet.getRange(c + '14').setFormula('=SUM(' + c + '4:' + c + '13)').setFontWeight('bold');
  });
  sheet.getRange('B4:F14').setNumberFormat('$#,##0');
  sheet.getRange('G4:G13').setNumberFormat('+0.0%;-0.0%');
  sheet.getRange('A14:G14').setBorder(true, null, null, null, null, null);
  sheet.setFrozenRows(3);
  label(sheet, 'A16', 'Reconciled', { color: '#999999' });
  checkbox(sheet, 'B16');
  return sheet;
}

function buildEncounter(ss) {
  const sheet = getOrCreate(ss, SHEETS.encounter);
  ensureSize(sheet, 26, 23);
  sheet.setHiddenGridlines(true);
  sheet.setColumnWidths(1, 20, 16);
  sheet.setColumnWidth(21, 460);
  sheet.setColumnWidth(22, 70);
  sheet.setColumnWidth(23, 120);
  sheet.setRowHeight(1, 44);
  sheet.setRowHeights(2, 24, 18);
  sheet.getRange('U2:V26').setFontSize(10).setVerticalAlignment('middle');
  label(sheet, 'U1', '🦖 SPREADSAURS', { size: 22, bold: true, color: '#2b2d42' });
  label(sheet, 'U3', '', { bold: true, size: 11 });
  label(sheet, 'U5', '', { italic: true, color: '#555555' });
  label(sheet, 'U7', '🔍 Look for dinos  →', { bold: true });
  label(sheet, 'U10', '   (type the answer in the yellow box for +30% catch chance)', { italic: true, color: '#777777' });
  label(sheet, 'U11', '🍪 Throw a snack  →', { bold: true });
  label(sheet, 'U13', '🏃 Run away  →', { bold: true });
  label(sheet, 'U18', '📣 Share your Dino of the Day:', { bold: true });
  label(sheet, 'U21', '🙈 BOSS KEY: hide the game  →', { bold: true, color: '#c0392b' });
  label(sheet, 'U23', '', { color: '#1f618d' });
  sheet.getRange('V9').setBackground('#fff3a8').setHorizontalAlignment('center')
    .setBorder(true, true, true, true, null, null);
  ['V7', 'V11', 'V13', 'V21'].forEach(function (a1) { checkbox(sheet, a1); });
  return sheet;
}

function buildCollection(ss) {
  const sheet = getOrCreate(ss, SHEETS.collection);
  ensureSize(sheet, 50, COL.dna);
  const widths = [60, 170, 120, 110, 55, 50, 40, 50, 50, 50, 50, 60, 70, 65, 95, 60];
  widths.forEach(function (w, i) { sheet.setColumnWidth(i + 1, w); });
  label(sheet, 'A1', '🦖 Collection', { size: 16, bold: true });
  label(sheet, 'B2', '← 🧬 Evolve: merge 3 identical dinos into the next stage', { bold: true });
  checkbox(sheet, 'A2');
  label(sheet, 'C2', '', { italic: true, color: '#555555' });
  sheet.getRange(3, 1, 1, COL.dna).setValues([COLLECTION_HEADERS])
    .setFontWeight('bold').setBackground('#e8eaed');
  sheet.setFrozenRows(3);
  sheet.hideColumns(COL.dna);
  sheet.getRange(FIRST_DATA_ROW, COL.stage, 1000, 3).setHorizontalAlignment('center');
  return sheet;
}

function buildDex(ss) {
  const sheet = getOrCreate(ss, SHEETS.dex);
  const blockW = CANVAS_W + 1;
  const blockH = CANVAS_H + 3;
  ensureSize(sheet, 2 + 4 * blockH + 2, 1 + 6 * blockW + 1);
  sheet.setHiddenGridlines(true);
  sheet.setColumnWidths(1, 1 + 6 * blockW + 1, 8);
  sheet.setRowHeight(1, 32);
  sheet.setRowHeight(2, 8);
  for (let b = 0; b < 4; b++) {
    const r0 = 3 + b * blockH;
    sheet.setRowHeights(r0, CANVAS_H, 8);
    sheet.setRowHeights(r0 + CANVAS_H, 2, 14);
    sheet.setRowHeight(r0 + CANVAS_H + 2, 10);
  }
  sheet.getRange(3, 2, 4 * blockH, 6 * blockW).setFontSize(8);
  label(sheet, 'A1', '📖 DEX', { size: 16, bold: true });
  return sheet;
}

function buildTrade(ss) {
  const sheet = getOrCreate(ss, SHEETS.trade);
  ensureSize(sheet, 140, 4);
  sheet.setColumnWidth(1, 20);
  sheet.setColumnWidth(2, 420);
  sheet.setColumnWidth(3, 360);
  sheet.setColumnWidth(4, 70);
  label(sheet, 'B2', '✉️ Trade & ⚔️ Battle', { size: 16, bold: true });
  label(sheet, 'B4', '✉️ SEND: tick "Send ✉️" on a dino in Collection. Its code shows up here →', { bold: true });
  sheet.getRange('C4').setFontFamily('Roboto Mono').setFontWeight('bold');
  label(sheet, 'B6', '📥 RECEIVE: paste a friend\'s DINO code in the yellow box, then tick →', { bold: true });
  label(sheet, 'B8', '🛡️ YOUR TEAM CODE: tick to generate, then share it →', { bold: true });
  sheet.getRange('C8').setFontFamily('Roboto Mono').setFontWeight('bold');
  label(sheet, 'B10', '⚔️ BATTLE: paste a friend\'s TEAM code, then tick →', { bold: true });
  label(sheet, 'B12', '👔 DAILY BOSS: fight The Auditor (+' + BOSS_SNACK_REWARD + ' snacks if you win) →', { bold: true });
  label(sheet, 'B14', '', { color: '#1f618d', bold: true });
  label(sheet, 'B16', 'BATTLE LOG', { bold: true, color: '#777777' });
  ['C6', 'C10'].forEach(function (a1) {
    sheet.getRange(a1).setBackground('#fff3a8').setFontFamily('Roboto Mono')
      .setBorder(true, true, true, true, null, null);
  });
  ['D6', 'D8', 'D10', 'D12'].forEach(function (a1) { checkbox(sheet, a1); });
  return sheet;
}

// ─────────────────────────────── Entry points ───────────────────────────────

/** Run this once from the Apps Script editor. Safe to re-run: it repairs the layout and keeps your dinos. */
function setupSpreadsaurs() {
  const ss = SpreadsheetApp.getActive();
  buildDecoy(ss);
  buildEncounter(ss);
  buildCollection(ss);
  buildDex(ss);
  buildTrade(ss);
  const st = loadState(ss);
  rollDay(st);
  saveState(ss, st);

  // Tab order: the decoy budget sits first so the game never opens on screen by accident.
  ['decoy', 'encounter', 'collection', 'dex', 'trade'].forEach(function (key, i) {
    const sh = ss.getSheetByName(SHEETS[key]);
    ss.setActiveSheet(sh);
    ss.moveActiveSheet(i + 1);
  });
  const blank = ss.getSheetByName('Sheet1');
  if (blank && blank.getLastRow() === 0) ss.deleteSheet(blank);

  writeCollection(ss, readCollection(ss));
  renderDex(ss, st);
  refreshEncounter(ss, st, 'Welcome to Spreadsaurs! Tick 🔍 Look for dinos to begin.');
  restoreGame();
}

/** Wipes every dino and starts over. */
function resetSpreadsaurs() {
  const ss = SpreadsheetApp.getActive();
  const state = ss.getSheetByName(SHEETS.state);
  if (state) state.clearContents();
  const coll = ss.getSheetByName(SHEETS.collection);
  if (coll) writeCollection(ss, []);
  setupSpreadsaurs();
}

function onOpen() {
  SpreadsheetApp.getUi().createMenu('🦖 Spreadsaurs')
    .addItem('🙈 Boss key (hide the game)', 'bossKey')
    .addItem('🎮 Back to the game', 'restoreGame')
    .addSeparator()
    .addItem('Set up / repair the game', 'setupSpreadsaurs')
    .addItem('Start over (deletes all dinos)', 'resetSpreadsaurs')
    .addToUi();
}

/** Checkboxes act as buttons: tick one and the matching action runs. */
function onEdit(e) {
  if (!e || !e.range) return;
  const range = e.range;
  if (range.getNumRows() !== 1 || range.getNumColumns() !== 1) return;
  if (String(e.value).toUpperCase() !== 'TRUE') return;
  const handler = findHandler(range.getSheet().getName(), range);
  if (!handler) return;
  range.setValue(false);
  try {
    handler();
  } catch (err) {
    notify(SpreadsheetApp.getActive(), 'Oops: ' + err.message);
  }
}

function findHandler(sheetName, range) {
  const a1 = range.getA1Notation();
  if (sheetName === SHEETS.encounter) {
    return { V7: actionLook, V11: actionThrow, V13: actionRun, V21: bossKey }[a1] || null;
  }
  if (sheetName === SHEETS.collection) {
    if (a1 === 'A2') return actionEvolve;
    if (range.getColumn() === COL.send && range.getRow() >= FIRST_DATA_ROW) {
      const row = range.getRow();
      return function () { actionSend(row); };
    }
    return null;
  }
  if (sheetName === SHEETS.trade) {
    return { D6: actionReceive, D8: actionTeamCode, D10: actionBattle, D12: actionBoss }[a1] || null;
  }
  if (sheetName === SHEETS.decoy && a1 === 'B16') return restoreGame;
  return null;
}
