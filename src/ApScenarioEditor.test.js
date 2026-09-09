import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import fs from 'fs';
import ApScenarioEditor from './ApScenarioEditor';
const full = JSON.parse(fs.readFileSync('public/football/ap-simulator.json', 'utf8'));
const editable = { ...(full.games.find(g => g.editable) || full.games[0]), editable: true, completed: false };
const payload = { ...full, games: full.games.map(g => (g.id === editable.id ? editable : { ...g, editable: false })) };
const forecast = { asOf: payload.asOf, modelVersion: payload.modelVersion, next: { previousPollId: payload.pollId, simulator: { url: '/football/ap-simulator.json' } } };
afterEach(() => jest.restoreAllMocks());

test('winner selection fills editable scores, applies results and resets', async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => payload });
  const onResult = jest.fn();render(<ApScenarioEditor forecast={forecast} onResult={onResult} />);
  fireEvent.click(await screen.findByRole('button', { name: `Pick ${editable.awayTeam} to beat ${editable.homeTeam}` }));
  const home = screen.getByRole('spinbutton', { name: `${editable.homeTeam} score against ${editable.awayTeam}` });
  const away = screen.getByRole('spinbutton', { name: `${editable.awayTeam} score against ${editable.homeTeam}` });
  expect(home).toHaveValue(20);expect(away).toHaveValue(27);
  fireEvent.change(home, { target: { value: '27' } });expect(screen.getByRole('button', { name: 'Update prediction' })).toBeDisabled();
  fireEvent.change(home, { target: { value: '10' } });fireEvent.click(screen.getByRole('button', { name: 'Update prediction' }));
  expect(onResult).toHaveBeenCalledWith(expect.objectContaining({ count: 1, asOf: payload.asOf, rows: expect.any(Array) }));
  fireEvent.click(screen.getByRole('button', { name: 'Reset all picks' }));expect(home).toHaveValue(null);expect(onResult).toHaveBeenLastCalledWith(null);
});

test('rejects a mismatched forecast snapshot', async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ ...payload, pollId: -1 }) });
  render(<ApScenarioEditor forecast={forecast} onResult={jest.fn()} />);
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('forecast is updating'));
});

test('restores picks when returning to the custom forecast', async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => payload });
  const savedDraft = { asOf: payload.asOf, edits: { [editable.id]: { home: '10', away: '35' } }, dirty: false, applied: 1 };
  render(<ApScenarioEditor forecast={forecast} onResult={jest.fn()} savedDraft={savedDraft} />);
  expect(await screen.findByRole('spinbutton', { name: `${editable.awayTeam} score against ${editable.homeTeam}` })).toHaveValue(35);
  expect(screen.getByRole('status')).toHaveTextContent('1 custom result applied');
});
