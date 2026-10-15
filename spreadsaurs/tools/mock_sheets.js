// A small in-memory stand-in for SpreadsheetApp, enough to run Spreadsaurs end to end in Node.
// Formatting calls are accepted and ignored; values, backgrounds, checkboxes and visibility are tracked.

function colToNum(letters) {
  let n = 0;
  for (const ch of letters) n = n * 26 + (ch.charCodeAt(0) - 64);
  return n;
}
function numToCol(n) {
  let s = '';
  while (n > 0) { const m = (n - 1) % 26; s = String.fromCharCode(65 + m) + s; n = Math.floor((n - 1) / 26); }
  return s;
}
function parseA1(a1) {
  const m = a1.match(/^([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?$/);
  if (!m) throw new Error('Bad A1: ' + a1);
  const r1 = +m[2], c1 = colToNum(m[1]);
  const r2 = m[3] ? +m[4] : r1, c2 = m[3] ? colToNum(m[3]) : c1;
  return [r1, c1, r2 - r1 + 1, c2 - c1 + 1];
}

class MockRange {
  constructor(sheet, row, col, nr, nc) { Object.assign(this, { sheet, row, col, nr, nc }); }
  _each(fn) { for (let i = 0; i < this.nr; i++) for (let j = 0; j < this.nc; j++) fn(this.row + i, this.col + j, i, j); }
  _check(arr) {
    if (arr.length !== this.nr || arr.some((r) => r.length !== this.nc)) {
      throw new Error(`Dimension mismatch on ${this.getA1Notation()}: got ${arr.length}x${arr[0] && arr[0].length}, need ${this.nr}x${this.nc}`);
    }
  }
  _bounds() {
    if (this.row < 1 || this.col < 1 || this.row + this.nr - 1 > this.sheet.maxRows || this.col + this.nc - 1 > this.sheet.maxCols) {
      throw new Error(`Range ${this.getA1Notation()} outside sheet ${this.sheet.name} (${this.sheet.maxRows}x${this.sheet.maxCols})`);
    }
  }
  getValue() { return this.sheet.get(this.row, this.col); }
  getValues() { const out = []; for (let i = 0; i < this.nr; i++) { const r = []; for (let j = 0; j < this.nc; j++) r.push(this.sheet.get(this.row + i, this.col + j)); out.push(r); } return out; }
  setValue(v) { this._bounds(); this._each((r, c) => this.sheet.set(r, c, v)); return this.proxy; }
  setValues(vals) { this._bounds(); this._check(vals); this._each((r, c, i, j) => this.sheet.set(r, c, vals[i][j])); return this.proxy; }
  setFormula(f) { return this.setValue(f); }
  clearContent() { this._each((r, c) => this.sheet.cells.delete(r + ',' + c)); return this.proxy; }
  setBackground(c) { this._each((r, cc) => this.sheet.bg.set(r + ',' + cc, c)); return this.proxy; }
  setBackgrounds(arr) { this._bounds(); this._check(arr); this._each((r, c, i, j) => this.sheet.bg.set(r + ',' + c, arr[i][j])); return this.proxy; }
  getBackground() { return this.sheet.bg.get(this.row + ',' + this.col) || '#ffffff'; }
  insertCheckboxes() { this._bounds(); this._each((r, c) => { this.sheet.checkboxes.add(r + ',' + c); this.sheet.set(r, c, false); }); return this.proxy; }
  clearDataValidations() { this._each((r, c) => this.sheet.checkboxes.delete(r + ',' + c)); return this.proxy; }
  getA1Notation() { const a = numToCol(this.col) + this.row; return this.nr === 1 && this.nc === 1 ? a : a + ':' + numToCol(this.col + this.nc - 1) + (this.row + this.nr - 1); }
  getRow() { return this.row; }
  getColumn() { return this.col; }
  getNumRows() { return this.nr; }
  getNumColumns() { return this.nc; }
  getSheet() { return this.sheet.proxy; }
}

class MockSheet {
  constructor(ss, name) {
    Object.assign(this, { ss, name, cells: new Map(), bg: new Map(), checkboxes: new Set(), maxRows: 1000, maxCols: 26, hidden: false });
    this.proxy = chainableObj(this);
  }
  get(r, c) { const v = this.cells.get(r + ',' + c); return v === undefined ? '' : v; }
  set(r, c, v) { if (v === '' || v === null) this.cells.delete(r + ',' + c); else this.cells.set(r + ',' + c, v); }
  getName() { return this.name; }
  getRange(a, b, c, d) {
    const args = typeof a === 'string' ? parseA1(a) : [a, b, c || 1, d || 1];
    const rg = new MockRange(this, ...args);
    rg.proxy = chainableObj(rg);
    return rg.proxy;
  }
  getLastRow() { let m = 0; for (const k of this.cells.keys()) m = Math.max(m, +k.split(',')[0]); return m; }
  getMaxRows() { return this.maxRows; }
  getMaxColumns() { return this.maxCols; }
  insertRowsAfter(_, n) { this.maxRows += n; return this.proxy; }
  insertColumnsAfter(_, n) { this.maxCols += n; return this.proxy; }
  clear() { this.cells.clear(); this.bg.clear(); this.checkboxes.clear(); return this.proxy; }
  clearContents() { this.cells.clear(); return this.proxy; }
  hideSheet() {
    const visible = this.ss.sheets.filter((s) => !s.hidden);
    if (visible.length === 1 && visible[0] === this) throw new Error('Cannot hide the only visible sheet');
    this.hidden = true; return this.proxy;
  }
  showSheet() { this.hidden = false; return this.proxy; }
  isSheetHidden() { return this.hidden; }
  activate() { this.ss.active = this; return this.proxy; }
}

function chainableObj(obj) {
  const p = new Proxy(obj, {
    get(t, prop) {
      if (prop in t) { const v = t[prop]; return typeof v === 'function' ? v.bind(t) : v; }
      if (typeof prop === 'symbol') return undefined;
      return () => p;
    },
  });
  return p;
}

class MockSpreadsheet {
  constructor() { this.sheets = []; this.toasts = []; this.add('Sheet1'); this.active = this.sheets[0]; this.proxy = chainableObj(this); }
  add(name) { const s = new MockSheet(this, name); this.sheets.push(s); return s; }
  getSheetByName(name) { const s = this.sheets.find((x) => x.name === name); return s ? s.proxy : null; }
  insertSheet(name) { if (this.sheets.some((x) => x.name === name)) throw new Error('dup sheet ' + name); const s = this.add(name); this.active = s; return s.proxy; }
  getSheets() { return this.sheets.map((s) => s.proxy); }
  deleteSheet(sp) { this.sheets = this.sheets.filter((s) => s.proxy !== sp); }
  setActiveSheet(sp) { this.active = this.sheets.find((s) => s.proxy === sp); if (this.active.hidden) this.active.hidden = false; return sp; }
  getActiveSheet() { return this.active.proxy; }
  moveActiveSheet(pos) { const a = this.active; this.sheets = this.sheets.filter((s) => s !== a); this.sheets.splice(pos - 1, 0, a); }
  toast(msg) { this.toasts.push(msg); }
}

function createSpreadsheetApp() {
  const ss = new MockSpreadsheet();
  const app = {
    getActive: () => ss.proxy,
    getActiveSpreadsheet: () => ss.proxy,
    getUi: () => chainableObj({}),
  };
  return { app, ss };
}

module.exports = { createSpreadsheetApp, parseA1 };
