const {projectScenario, averageScenarios, eligibleGames} = require('./cfpScenario.mjs');
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

test('average resumes equal the browsable projections, including forced results', () => {
 const g=eligibleGames(engine,data.next.eligibleTeams)[0];
 const overrides={[g.id]:g.awayKey};
 const average=averageScenarios(engine,overrides,data.next.eligibleTeams);
 const scenarios=Array.from({length:25},(_,i)=>projectScenario(engine,i+1,overrides,data.next.eligibleTeams));
 for (const row of average.rows) {
  const rows=scenarios.map(s=>s.rows.find(r=>r.key===row.key));
  expect(row.wins).toBeCloseTo(rows.reduce((s,r)=>s+r.wins,0)/25,10);
  expect(row.losses).toBeCloseTo(rows.reduce((s,r)=>s+r.losses,0)/25,10);
  expect(row.averageRank).toBeCloseTo(rows.reduce((s,r)=>s+r.rank,0)/25,10);
 }
 expect(average.assumptions.find(a=>a.id===g.id).homeWinFrequency).toBe(0);
 expect(average.rows.map(r=>r.averageRank)).toEqual(average.rows.map(r=>r.averageRank).sort((a,b)=>a-b));
});
