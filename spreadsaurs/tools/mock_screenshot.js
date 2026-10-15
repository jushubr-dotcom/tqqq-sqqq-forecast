// Plays a few moves on the mock sheet and writes an HTML approximation of the Encounter tab.
const fs = require('fs');
const vm = require('vm');
const { loadGame } = require('./load');
const { createSpreadsheetApp } = require('./mock_sheets');

const { app, ss } = createSpreadsheetApp();
const ctx = loadGame({ SpreadsheetApp: app });
ctx.setupSpreadsaurs();
vm.runInContext('Math.random = mulberry32(11)', ctx);
const enc = ss.sheets.find((s) => s.name === '🦖 Encounter');
const tick = (a1) => { const r = ss.getSheetByName('🦖 Encounter').getRange(a1); r.setValue(true); ctx.onEdit({ range: r, value: 'TRUE' }); };
tick('V7');

const widths = (c) => (c <= 20 ? 16 : c === 21 ? 460 : c === 22 ? 70 : 40);
const heights = (r) => (r === 1 ? 44 : 18);
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
let html = `<html><head><meta charset="utf-8"><style>
body{margin:0;background:#fff;font-family:Arial, sans-serif;font-size:13px}
table{border-collapse:collapse;table-layout:fixed}
td{padding:0 4px;white-space:nowrap;overflow:visible}
td.px{padding:0}
.cb{display:inline-block;width:14px;height:14px;border:2px solid #5f6368;border-radius:2px}
</style></head><body><table>`;
for (let r = 1; r <= 24; r++) {
  html += `<tr style="height:${heights(r)}px">`;
  for (let c = 1; c <= 22; c++) {
    const bg = enc.bg.get(r + ',' + c) || '#ffffff';
    const v = enc.get(r, c);
    let content = '';
    if (enc.checkboxes.has(r + ',' + c)) content = '<span class="cb"></span>';
    else if (v !== '') content = esc(v);
    let style = `width:${widths(c)}px;max-width:${widths(c)}px;background:${bg};`;
    if (r === 1 && c === 21) style += 'font-size:28px;font-weight:bold;color:#2b2d42;';
    if ([3, 7, 11, 13, 18, 21].includes(r) && c === 21) style += 'font-weight:bold;';
    if (r === 21 && c === 21) style += 'color:#c0392b;';
    if ([5, 10].includes(r) && c === 21) style += 'font-style:italic;color:#666;';
    if (r === 23 && c === 21) style += 'color:#1f618d;';
    if (c === 22 && r === 9) style += 'border:1px solid #333;text-align:center;';
    if (c === 22) style += 'text-align:center;';
    html += `<td class="${c <= 20 ? 'px' : ''}" style="${style}">${content}</td>`;
  }
  html += '</tr>';
}
html += '</table></body></html>';
fs.writeFileSync(process.argv[2], html);
