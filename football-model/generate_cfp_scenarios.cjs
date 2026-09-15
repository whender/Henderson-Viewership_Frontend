// Use the same ranking implementation for exported scenarios and browser edits.
let input = '';
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', async () => {
  const {projectScenario, contenderPool} = await import('../src/cfpScenario.mjs');
  const engine = JSON.parse(input);
  process.stdout.write(JSON.stringify({main: projectScenario(engine), alternatives: Array.from({length: 25}, (_, i) => {
    const scenario = projectScenario(engine, i + 1);
    return {...scenario, rows: scenario.rows.slice(0, 40)};
  }), eligibleTeams: contenderPool(engine)}));
});
