import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import FootballWeekly from './FootballWeekly';

const completed = {
  id: 1, week: 1, date: '2026-09-05T20:00:00Z', completed: true,
  home: 'BYU', away: 'Notre Dame', homePoints: 28, awayPoints: 21,
  homeLogo: 'https://a.espncdn.com/i/teamlogos/ncaa/500/252.png',
  awayLogo: 'https://a.espncdn.com/i/teamlogos/ncaa/500/87.png',
  predictionSource: 'reconstructed', predictionAsOf: '2026-09-05T20:00:00Z',
  prediction: { predicted_margin: 10, home_win_probability: .8 },
};
const data = { season: 2026, teams: [{ team: 'BYU' }, { team: 'Notre Dame' }], games: [
  completed,
  { ...completed, id: 2, week: 2, date: '2026-09-12T00:00:00Z', completed: false,
    predictionSource: 'current', homePoints: null, awayPoints: null },
] };
function open(value = data, path = '/football-model/weekly') {
  render(<MemoryRouter initialEntries={[path]}><FootballWeekly data={value} /></MemoryRouter>);
}

test('opens upcoming week and keeps season stats when changing weeks', () => {
  open();
  expect(screen.getByLabelText('Prediction week')).toHaveValue('regular:2');
  const season = screen.getByRole('region', { name: 'Season overall' });
  expect(within(season).getByText('1–0')).toBeInTheDocument();
  expect(within(screen.getByRole('table')).getByText('Upcoming')).toBeInTheDocument();
  fireEvent.click(screen.getByText('Previous week'));
  expect(screen.getByLabelText('Prediction week')).toHaveValue('regular:1');
  expect(screen.getByText('21–28')).toBeInTheDocument();
  expect(screen.getByText('Correct')).toBeInTheDocument();
  expect(screen.getByText('3.0 pt error')).toBeInTheDocument();
  expect(screen.getByText('Reconstructed pregame')).toBeInTheDocument();
  expect(within(season).getByText('1–0')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'BYU' })).toHaveAttribute('href', '/football-model/teams/BYU');
});

test('archived-only filter excludes reconstructed games from results and stats', () => {
  open(data, '/football-model/weekly?week=regular%3A1');
  fireEvent.change(screen.getByLabelText('Forecasts'), { target: { value: 'archived' } });
  expect(screen.getByRole('status')).toHaveTextContent('No games match');
  expect(within(screen.getByRole('region', { name: 'Season overall' })).getByText('0 graded games')).toBeInTheDocument();
});

test('search and misses filters only affect displayed rows', () => {
  open(data, '/football-model/weekly?week=regular%3A1');
  fireEvent.change(screen.getByLabelText('Game status'), { target: { value: 'misses' } });
  expect(screen.getByRole('status')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Game status'), { target: { value: 'all' } });
  fireEvent.change(screen.getByLabelText('Find a matchup'), { target: { value: 'absent team' } });
  expect(screen.getByRole('status')).toBeInTheDocument();
  expect(within(screen.getByRole('region', { name: 'Season overall' })).getByText('1 graded games')).toBeInTheDocument();
});

test('empty schedule has disabled week controls and no invented percentages', () => {
  open({ ...data, games: [] });
  expect(screen.getByText('Previous week')).toBeDisabled();
  expect(screen.getByText('Next week')).toBeDisabled();
  expect(screen.getByText('No graded winner picks')).toBeInTheDocument();
});
