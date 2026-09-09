import fs from 'fs';
import { predictScenario, validateScores } from './apScenario';
const payload = JSON.parse(fs.readFileSync('public/football/ap-simulator.json', 'utf8'));
const data = JSON.parse(fs.readFileSync('public/football/ap.json', 'utf8'));

test('default scenario reproduces published projected rankings and records without mutating inputs', () => {
  const before = JSON.stringify(payload);
  const rows = predictScenario(payload);
  const fields = r => [r.teamId, r.rank, r.wins, r.losses, r.ties];
  expect(rows.map(fields)).toEqual(data.next.rows.map(fields));
  expect(JSON.stringify(payload)).toBe(before);
});

test('rejects invalid scores and attempts to modify completed or unlisted games', () => {
  for (const pair of [['', 7], [7, 7], [-1, 7], [1.5, 7], [201, 7]]) expect(validateScores(...pair)).not.toBe('');
  expect(validateScores(0, 7)).toBe('');
  const done = payload.games.find(g => g.completed);
  if (done) expect(() => predictScenario(payload, { [done.id]: { home: 30, away: 0 } })).toThrow('Only listed upcoming');
  expect(() => predictScenario(payload, { nonexistent: { home: 30, away: 0 } })).toThrow('Only listed upcoming');
});
