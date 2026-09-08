import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import FootballModel from './FootballModel';
const data = {
  schemaVersion: 1, season: 2026, asOf: new Date().toISOString(),
  teams: [
    { team: 'BYU', team_id: 252, rank: 16, rating: 15.55, conference: 'Big 12', games: 1 },
    { team: 'Notre Dame', team_id: 87, rank: 3, rating: 29.25, conference: 'Independent', games: 1 },
  ],
  games: [{ id: 1, week: 7, date: '2026-10-17T04:00:00Z', home: 'BYU', away: 'Notre Dame', completed: false, prediction: { predicted_margin: -4.417, home_win_probability: .393, away_win_probability: .607 } }],
  scheduledMatchups: { '252:87:0': { margin: -4.417, probability: .393, date: '2026-10-17T04:00:00Z', actualHome: 'BYU', actualNeutral: false }, '252:87:1': { margin: -8.4, probability: .3, date: '2026-10-17T04:00:00Z', actualHome: 'BYU', actualNeutral: false }, '87:252:1': { margin: 8.4, probability: .7, date: '2026-10-17T04:00:00Z', actualHome: 'BYU', actualNeutral: false } },
  matchups: { '252:87:0': [-6.058, .353], '252:87:1': [-10, .25], '87:252:0': [14, .8] },
};
beforeEach(() => { global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => data }); });
afterEach(() => jest.restoreAllMocks());
function open(path) { render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/football-model/*" element={<FootballModel />} /></Routes></MemoryRouter>); }
test('hypothetical predictions change with venue and reject self-matchups', async () => {
  open('/football-model/predictor');
  expect(await screen.findByText('Notre Dame -4.4')).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText('Use scheduled game context'));
  expect(screen.getByText('Notre Dame -6.1')).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText('Neutral site'));
  expect(screen.getByText('Notre Dame -10.0')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Team 2'), { target: { value: 'BYU' } });
  expect(screen.getByRole('alert')).toHaveTextContent('Choose two different teams');
});
test('team profile shows scheduled spread instead of hypothetical line', async () => {
  open('/football-model/teams/BYU');
  expect(await screen.findByText('BYU +4.4')).toBeInTheDocument();
  expect(screen.getByText('39.3%')).toBeInTheDocument();
  expect(screen.queryByText('Notre Dame -6.1')).not.toBeInTheDocument();
});
test('failed load offers retry and recovers', async () => {
  global.fetch.mockRejectedValueOnce(new Error('Offline'));
  open('/football-model');
  expect(await screen.findByRole('alert')).toHaveTextContent('Offline');
  fireEvent.click(screen.getByText('Refresh data'));
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  expect(screen.getByText('Power Rankings')).toBeInTheDocument();
});

test('neutral scheduled spread stays the same after swapping teams', async () => {
  open('/football-model/predictor');
  expect(await screen.findByText('Notre Dame -4.4')).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText('Neutral site'));
  expect(screen.getByText('Notre Dame -8.4')).toBeInTheDocument();
  fireEvent.click(screen.getByText('Swap teams'));
  expect(screen.getByText('Notre Dame -8.4')).toBeInTheDocument();
  expect(screen.getByText('70.0%')).toBeInTheDocument();
});

test('completed game shows reconstructed pregame spread beside final score', async () => {
  const completed = { ...data.games[0], completed: true, homePoints: 28, awayPoints: 21,
    predictionSource: 'reconstructed', predictionAsOf: data.games[0].date };
  global.fetch.mockResolvedValue({ ok: true, json: async () => ({ ...data, games: [completed] }) });
  open('/football-model/teams/BYU');
  expect(await screen.findByText('BYU +4.4')).toBeInTheDocument();
  expect(screen.getByText('Pregame · reconstructed')).toBeInTheDocument();
  expect(screen.getByText('W 28–21')).toBeInTheDocument();
  expect(screen.getByText('39.3%')).toBeInTheDocument();
});

test('completed away-team spread has the opposite sign and archived label', async () => {
  const completed = { ...data.games[0], completed: true, homePoints: 28, awayPoints: 21,
    predictionSource: 'archived', predictionAsOf: '2026-10-16T00:00:00Z' };
  global.fetch.mockResolvedValue({ ok: true, json: async () => ({ ...data, games: [completed] }) });
  open('/football-model/teams/Notre%20Dame');
  expect(await screen.findByText('Notre Dame -4.4')).toBeInTheDocument();
  expect(screen.getByText('Pregame · archived')).toBeInTheDocument();
  expect(screen.getByText('L 21–28')).toBeInTheDocument();
  expect(screen.getByText('60.7%')).toBeInTheDocument();
});
