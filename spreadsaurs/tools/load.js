// Loads Code.gs into a Node sandbox so its pure functions can be tested and rendered.
const fs = require('fs');
const path = require('path');
const vm = require('vm');

function loadGame(extraGlobals) {
  const src = fs.readFileSync(path.join(__dirname, '..', 'Code.gs'), 'utf8');
  const ctx = vm.createContext(Object.assign({ console }, extraGlobals || {}));
  // Top-level const/let stay in the script scope, so expose what tests need.
  vm.runInContext(src + `
    ;globalThis.__game = { LINES, BODIES, ACCESSORIES, CANVAS_W, CANVAS_H, SPECIES_COUNT,
      spriteGrid, sceneGrid, speciesInfo, computeStats, power, makeQuiz, mulberry32, fnv1a,
      encodeDinoCode, decodeDinoCode, encodeTeamCode, decodeTeamCode, simulateBattle, bossTeam,
      dinoOfTheDay, wildDino, packDino, unpackDino, SHEETS };`, ctx);
  return ctx;
}
module.exports = { loadGame };
