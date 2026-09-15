const {projectScenario, eligibleGames} = require('./cfpScenario.mjs');
const data = require('../public/football/cfp.json');
const engine = data.next.scenarioEngine;
test('projections repeat exactly, have coherent winners and reject disallowed overrides', () => {
  expect(projectScenario(engine, 4)).toEqual(projectScenario(engine, 4));
  const base=projectScenario(engine);
  expect(base.assumptions.every(g=>g.homeWin===(g.probability>=.5))).toBe(true);
  const allowed=eligibleGames(engine,data.next.eligibleTeams);
  const outside=engine.games.find(g=>g.projected&&!allowed.some(a=>a.id===g.id));
  expect(outside).toBeDefined();
  expect(projectScenario(engine,0,{[outside.id]:outside.probability>=.5?outside.awayKey:outside.homeKey},data.next.eligibleTeams)).toEqual(base);
  const finished=engine.games.find(g=>!g.projected);
  expect(projectScenario(engine,0,{[finished.id]:finished.homeKey},data.next.eligibleTeams)).toEqual(base);
  const g=allowed[0];
  expect(projectScenario(engine,0,{[g.id]:'unrelated-team'},data.next.eligibleTeams)).toEqual(base);
});
