// End-to-end tests for Code.gs against the mock Sheets API. Run: node tools/test.js
const assert = require('assert');
const { loadGame } = require('./load');
const { createSpreadsheetApp } = require('./mock_sheets');

let passed = 0;
function test(name, fn) {
  try { fn(); passed++; console.log('✓ ' + name); } catch (err) { console.error('✗ ' + name + '\n  ' + (err.stack || err)); process.exitCode = 1; }
}

function newGame() {
  const { app, ss } = createSpreadsheetApp();
  const ctx = loadGame({ SpreadsheetApp: app });
  ctx.setupSpreadsaurs();
  return { ctx, ss, g: ctx.__game };
}
function sheet(ss, name) { return ss.sheets.find((s) => s.name === name); }
function tick(ctx, ss, sheetName, a1) {
  const range = ss.getSheetByName(sheetName).getRange(a1);
  range.setValue(true);
  ctx.onEdit({ range, value: 'TRUE' });
  assert.strictEqual(range.getValue(), false, a1 + ' checkbox should reset');
}
function setRandom(ctx, value) { ctx.__rand = value; require('vm').runInContext('Math.random = () => (typeof __rand === "function" ? __rand() : __rand)', ctx); }
function state(ctx) { return ctx.loadState(ctx.SpreadsheetApp.getActive()); }

// ── Pure logic ──
const { g } = newGame();

test('all 24 sprites fit the canvas and use only known colors', () => {
  for (let sp = 0; sp < g.SPECIES_COUNT; sp++) {
    for (const shiny of [false, true]) {
      const grid = g.spriteGrid(sp, shiny, 'color');
      assert.strictEqual(grid.length, g.CANVAS_H);
      grid.forEach((row) => {
        assert.strictEqual(row.length, g.CANVAS_W);
        row.forEach((c) => assert.ok(c === null || /^#[0-9a-f]{6}$/i.test(c), `species ${sp} bad color ${c}`));
      });
    }
  }
});

test('every body row has the declared width and every sprite char has a color', () => {
  for (const [name, body] of Object.entries(g.BODIES)) {
    body.rows.forEach((r, i) => {
      assert.strictEqual(r.length, 18, `${name} row ${i} has width ${r.length}`);
      assert.ok(/^[.OBLDWKMP]+$/.test(r), `${name} row ${i} has unknown char`);
    });
  }
});

test('dino codes round-trip for every species, shiny and level', () => {
  for (let sp = 0; sp < 24; sp++) {
    for (const shiny of [false, true]) {
      const d = { sp, shiny, iv: [sp % 16, 15, 0, 7], lv: 1 + (sp * 2) % 50 };
      const code = g.encodeDinoCode(d, 1234);
      assert.ok(/^DINO-[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{2}$/.test(code), code);
      const back = g.decodeDinoCode(code.toLowerCase().replace(/-/g, ' '));
      assert.deepStrictEqual(JSON.parse(JSON.stringify(back.dino)), d);
    }
  }
});

test('tampered or garbage codes are rejected', () => {
  const code = g.encodeDinoCode({ sp: 3, shiny: false, iv: [1, 2, 3, 4], lv: 5 }, 99);
  const chars = code.split('');
  const i = 6;
  chars[i] = chars[i] === 'A' ? 'B' : 'A';
  assert.strictEqual(g.decodeDinoCode(chars.join('')), null);
  assert.strictEqual(g.decodeDinoCode('hello'), null);
  assert.strictEqual(g.decodeDinoCode(''), null);
  assert.strictEqual(g.decodeTeamCode(code), null);
});

test('team codes round-trip with 1 to 3 dinos', () => {
  for (let n = 1; n <= 3; n++) {
    const team = [];
    for (let k = 0; k < n; k++) team.push({ sp: k * 5, shiny: k === 1, iv: [k, k + 1, k + 2, k + 3], lv: 10 + k });
    const back = g.decodeTeamCode(g.encodeTeamCode(team));
    assert.strictEqual(back.team.length, n);
    assert.deepStrictEqual(JSON.parse(JSON.stringify(back.team)), team);
  }
});

test('Dino of the Day is the same for everyone on a given day and varies across days', () => {
  assert.deepStrictEqual(JSON.parse(JSON.stringify(g.dinoOfTheDay('2026-10-15'))), JSON.parse(JSON.stringify(g.dinoOfTheDay('2026-10-15'))));
  const species = new Set();
  for (let d = 1; d <= 60; d++) species.add(g.dinoOfTheDay('2026-11-' + String(d).padStart(2, '0')).sp);
  assert.ok(species.size > 10, 'only ' + species.size + ' distinct DotD species in 60 days');
});

test('battles are deterministic and always finish with a winner', () => {
  const a = [{ sp: 2, shiny: false, iv: [5, 5, 5, 5], lv: 10 }];
  const b = [{ sp: 7, shiny: false, iv: [5, 5, 5, 5], lv: 10 }, { sp: 12, shiny: true, iv: [1, 1, 1, 1], lv: 3 }];
  const r1 = g.simulateBattle(a, b, 42, 'You', 'Rival');
  const r2 = g.simulateBattle(a, b, 42, 'You', 'Rival');
  assert.deepStrictEqual(r1, r2);
  assert.ok(['A', 'B'].includes(r1.winner));
  assert.ok(r1.log.some((l) => l.includes('fainted')));
});

test('quiz answers are correct', () => {
  const rng = g.mulberry32(7);
  for (let i = 0; i < 200; i++) {
    const q = g.makeQuiz(rng);
    const expr = q.q.slice(1).replace(/SUM\(/, 'sum(').replace(/MAX\(/, 'Math.max(').replace(/MIN\(/, 'Math.min(').replace(/AVERAGE\(/, 'avg(').replace(/PRODUCT\(/, 'prod(');
    const sum = (...x) => x.reduce((a, b) => a + b, 0);
    const avg = (...x) => sum(...x) / x.length;
    const prod = (...x) => x.reduce((a, b) => a * b, 1);
    assert.strictEqual(eval(expr), q.a, q.q);
    assert.ok(Number.isInteger(q.a), 'non-integer answer for ' + q.q);
  }
});

// ── Full game flow on the mock spreadsheet ──
test('setup builds every sheet, decoy first, state hidden, Sheet1 removed', () => {
  const { ss } = newGame();
  const names = ss.sheets.map((s) => s.name);
  assert.deepStrictEqual(names.slice(0, 5), ['FY25 Budget', '🦖 Encounter', 'Collection', 'Dex', 'Trade & Battle']);
  assert.ok(sheet(ss, '_state').hidden);
  assert.ok(!names.includes('Sheet1'));
  assert.strictEqual(ss.active.name, '🦖 Encounter');
});

test('first look of the day finds the Dino of the Day, and catching it makes a share line', () => {
  const { ctx, ss, g } = newGame();
  setRandom(ctx, 0.5);
  tick(ctx, ss, '🦖 Encounter', 'V7');
  let st = state(ctx);
  assert.ok(st.encounter && st.encounter.dotd);
  const dotd = g.dinoOfTheDay(st.day);
  assert.strictEqual(st.encounter.sp, dotd.sp);
  // Encounter scene shows the dino (some non-sky, non-grass pixels).
  const enc = sheet(ss, '🦖 Encounter');
  const bgs = ss.getSheetByName('🦖 Encounter').getRange(3, 2, 20, 18);
  let painted = 0;
  for (let r = 3; r < 23; r++) for (let c = 2; c < 20; c++) { const v = enc.bg.get(r + ',' + c); if (v !== '#eaf4ff' && v !== '#bfe8a6') painted++; }
  assert.ok(painted > 40, 'sprite not drawn');

  // Answer the quiz correctly, and force a successful catch.
  enc.set(9, 22, st.encounter.quiz.a);
  setRandom(ctx, 0.01);
  tick(ctx, ss, '🦖 Encounter', 'V11');
  st = state(ctx);
  assert.strictEqual(st.encounter, null);
  assert.ok(st.dotdDone);
  assert.strictEqual(st.snacks, 9);
  assert.ok(st.share.includes('SPREADSAURS') && st.share.includes('🍪'), st.share);
  assert.ok(st.caught[dotd.sp]);
  const coll = sheet(ss, 'Collection');
  assert.strictEqual(coll.get(4, 1), '#0001');
  assert.strictEqual(coll.get(4, 2), g.speciesInfo(dotd.sp).name);
  assert.ok(coll.checkboxes.has('4,13') && coll.checkboxes.has('4,14'));
  // Dex header updated
  assert.ok(String(sheet(ss, 'Dex').get(1, 1)).includes('1/24 caught'));
});

test('second look is a wild dino; failed throws use snacks; running away clears it', () => {
  const { ctx, ss } = newGame();
  const st0 = state(ctx);
  st0.dotdDone = true;
  ctx.saveState(ctx.SpreadsheetApp.getActive(), st0);
  setRandom(ctx, 0.5);
  tick(ctx, ss, '🦖 Encounter', 'V7');
  assert.strictEqual(state(ctx).encounter.dotd, false);
  setRandom(ctx, 0.99); // miss, and don't flee
  tick(ctx, ss, '🦖 Encounter', 'V11');
  assert.strictEqual(state(ctx).snacks, 9);
  assert.ok(state(ctx).encounter);
  tick(ctx, ss, '🦖 Encounter', 'V13');
  assert.strictEqual(state(ctx).encounter, null);
});

test('throwing with no snacks left is refused', () => {
  const { ctx, ss } = newGame();
  setRandom(ctx, 0.5);
  tick(ctx, ss, '🦖 Encounter', 'V7');
  const st = state(ctx); st.snacks = 0; ctx.saveState(ctx.SpreadsheetApp.getActive(), st);
  tick(ctx, ss, '🦖 Encounter', 'V11');
  assert.strictEqual(state(ctx).snacks, 0);
  assert.ok(String(sheet(ss, '🦖 Encounter').get(23, 21)).includes('Out of snacks'));
});

function giveDinos(ctx, dinos) {
  const ss = ctx.SpreadsheetApp.getActive();
  const st = ctx.loadState(ss);
  dinos.forEach((d) => ctx.addToCollection(ss, st, d));
  ctx.saveState(ss, st);
}

test('evolve merges 3 of a kind into the next stage with the best IVs', () => {
  const { ctx, ss, g } = newGame();
  giveDinos(ctx, [
    { sp: 0, shiny: false, iv: [1, 9, 2, 3], lv: 2 },
    { sp: 0, shiny: true, iv: [8, 1, 2, 3], lv: 4 },
    { sp: 0, shiny: false, iv: [1, 1, 12, 3], lv: 1 },
    { sp: 3, shiny: false, iv: [0, 0, 0, 0], lv: 1 },
  ]);
  tick(ctx, ss, 'Collection', 'A2');
  const list = ctx.readCollection(ctx.SpreadsheetApp.getActive());
  assert.strictEqual(list.length, 2);
  const evolved = list.find((d) => d.sp === 1);
  assert.ok(evolved, 'no Tie Rex');
  assert.deepStrictEqual([...evolved.iv], [8, 9, 12, 3]);
  assert.strictEqual(evolved.lv, 4);
  assert.strictEqual(evolved.shiny, true);
  assert.ok(state(ctx).caught[1]);
  assert.ok(String(sheet(ss, 'Collection').get(2, 3)).includes('Tie Rex'));
});

test('send → receive moves a dino between two players, and a code works only once', () => {
  const p1 = newGame();
  giveDinos(p1.ctx, [{ sp: 14, shiny: true, iv: [3, 4, 5, 6], lv: 7 }, { sp: 0, shiny: false, iv: [1, 1, 1, 1], lv: 1 }]);
  tick(p1.ctx, p1.ss, 'Collection', 'N4');
  const code = sheet(p1.ss, 'Trade & Battle').get(4, 3);
  assert.ok(/^DINO-/.test(code), 'no code: ' + code);
  assert.strictEqual(p1.ctx.readCollection(p1.ctx.SpreadsheetApp.getActive()).length, 1);

  const p2 = newGame();
  sheet(p2.ss, 'Trade & Battle').set(6, 3, code);
  tick(p2.ctx, p2.ss, 'Trade & Battle', 'D6');
  const got = p2.ctx.readCollection(p2.ctx.SpreadsheetApp.getActive());
  assert.strictEqual(got.length, 1);
  assert.strictEqual(got[0].sp, 14);
  assert.strictEqual(got[0].shiny, true);
  assert.strictEqual(got[0].lv, 7);

  sheet(p2.ss, 'Trade & Battle').set(6, 3, code);
  tick(p2.ctx, p2.ss, 'Trade & Battle', 'D6');
  assert.strictEqual(p2.ctx.readCollection(p2.ctx.SpreadsheetApp.getActive()).length, 1);
  assert.ok(String(sheet(p2.ss, 'Trade & Battle').get(14, 2)).includes('already used'));

  // The sender can't redeem their own code either.
  sheet(p1.ss, 'Trade & Battle').set(6, 3, code);
  tick(p1.ctx, p1.ss, 'Trade & Battle', 'D6');
  assert.strictEqual(p1.ctx.readCollection(p1.ctx.SpreadsheetApp.getActive()).length, 1);
});

test('friend battles give both players the same result', () => {
  const p1 = newGame();
  const p2 = newGame();
  giveDinos(p1.ctx, [{ sp: 2, shiny: false, iv: [9, 9, 9, 9], lv: 8 }, { sp: 5, shiny: false, iv: [4, 4, 4, 4], lv: 6 }]);
  giveDinos(p2.ctx, [{ sp: 14, shiny: false, iv: [7, 7, 7, 7], lv: 9 }, { sp: 22, shiny: false, iv: [3, 3, 3, 3], lv: 5 }]);
  tick(p1.ctx, p1.ss, 'Trade & Battle', 'D8');
  tick(p2.ctx, p2.ss, 'Trade & Battle', 'D8');
  const c1 = sheet(p1.ss, 'Trade & Battle').get(8, 3);
  const c2 = sheet(p2.ss, 'Trade & Battle').get(8, 3);
  assert.ok(/^TEAM-/.test(c1) && /^TEAM-/.test(c2));
  sheet(p1.ss, 'Trade & Battle').set(10, 3, c2);
  sheet(p2.ss, 'Trade & Battle').set(10, 3, c1);
  tick(p1.ctx, p1.ss, 'Trade & Battle', 'D10');
  tick(p2.ctx, p2.ss, 'Trade & Battle', 'D10');
  const v1 = String(sheet(p1.ss, 'Trade & Battle').get(14, 2));
  const v2 = String(sheet(p2.ss, 'Trade & Battle').get(14, 2));
  assert.ok(v1.includes('WIN') !== v2.includes('WIN'), `both or neither won:\n  ${v1}\n  ${v2}`);
  // Same fight, seen from both sides: same number of log lines.
  const logLen = (ss) => { let n = 0; while (sheet(ss, 'Trade & Battle').get(17 + n, 2) !== '') n++; return n; };
  assert.strictEqual(logLen(p1.ss), logLen(p2.ss));
  // Winner levels up once; a rematch gives no second level.
  const winner = v1.includes('WIN') ? p1 : p2;
  const lvBefore = winner.ctx.readCollection(winner.ctx.SpreadsheetApp.getActive()).map((d) => d.lv);
  tick(winner.ctx, winner.ss, 'Trade & Battle', 'D10');
  const lvAfter = winner.ctx.readCollection(winner.ctx.SpreadsheetApp.getActive()).map((d) => d.lv);
  assert.deepStrictEqual(lvAfter, lvBefore);
});

test('daily boss: a strong team wins once for +5 snacks', () => {
  const { ctx, ss } = newGame();
  giveDinos(ctx, [0, 1, 2].map((k) => ({ sp: 2 + k * 3, shiny: false, iv: [15, 15, 15, 15], lv: 50 })));
  tick(ctx, ss, 'Trade & Battle', 'D12');
  assert.ok(String(sheet(ss, 'Trade & Battle').get(14, 2)).includes('audited'), sheet(ss, 'Trade & Battle').get(14, 2));
  assert.strictEqual(state(ctx).snacks, 15);
  tick(ctx, ss, 'Trade & Battle', 'D12');
  assert.strictEqual(state(ctx).snacks, 15);
});

test('boss key hides the game behind the budget, and the Reconciled box brings it back', () => {
  const { ctx, ss } = newGame();
  tick(ctx, ss, '🦖 Encounter', 'V21');
  assert.strictEqual(ss.active.name, 'FY25 Budget');
  ['🦖 Encounter', 'Collection', 'Dex', 'Trade & Battle'].forEach((n) => assert.ok(sheet(ss, n).hidden, n + ' visible'));
  tick(ctx, ss, 'FY25 Budget', 'B16');
  assert.strictEqual(ss.active.name, '🦖 Encounter');
  ['🦖 Encounter', 'Collection', 'Dex', 'Trade & Battle'].forEach((n) => assert.ok(!sheet(ss, n).hidden, n + ' hidden'));
});

test('re-running setup keeps your dinos', () => {
  const { ctx } = newGame();
  giveDinos(ctx, [{ sp: 9, shiny: false, iv: [1, 2, 3, 4], lv: 3 }]);
  ctx.setupSpreadsaurs();
  assert.strictEqual(ctx.readCollection(ctx.SpreadsheetApp.getActive()).length, 1);
  ctx.resetSpreadsaurs();
  assert.strictEqual(ctx.readCollection(ctx.SpreadsheetApp.getActive()).length, 0);
});

test('a new UTC day refills snacks and brings a new Dino of the Day', () => {
  const { ctx } = newGame();
  const ss = ctx.SpreadsheetApp.getActive();
  const st = ctx.loadState(ss);
  Object.assign(st, { day: '2000-01-01', snacks: 0, dotdDone: true, bossDone: true });
  ctx.rollDay(st);
  assert.strictEqual(st.snacks, 10);
  assert.strictEqual(st.dotdDone, false);
  assert.strictEqual(st.bossDone, false);
});

test('unrelated edits are ignored', () => {
  const { ctx, ss } = newGame();
  const range = ss.getSheetByName('Collection').getRange('C10');
  range.setValue('Fluffy');
  ctx.onEdit({ range, value: 'Fluffy' });
  assert.strictEqual(range.getValue(), 'Fluffy');
});

console.log(`\n${passed} passed`);
