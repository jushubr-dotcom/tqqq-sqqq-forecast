// Prints every species' sprite grid (normal + shiny) as JSON for the preview renderer.
const { loadGame } = require('./load');
const g = loadGame().__game;
const out = [];
for (let sp = 0; sp < g.SPECIES_COUNT; sp++) {
  out.push({ name: g.speciesInfo(sp).name, normal: g.spriteGrid(sp, false, 'color'), shiny: g.spriteGrid(sp, true, 'color') });
}
process.stdout.write(JSON.stringify(out));
