import { fireEvent, render, screen } from '@testing-library/react';
import WeeklyPredictions from './WeeklyPredictions';

test('orders weeks by season then week and opens only the newest season', async () => {
  const originalFetch = global.fetch;
  global.fetch = jest.fn().mockResolvedValue({ json: async () => ({
    weeks: [
      { year: 2025, week: 1, games: [{ matchup: 'Older season game' }] },
      { year: 2025, week: 14, games: [] },
      { year: 2026, week: 1, games: [{ matchup: 'Newest season game' }] },
    ], metrics: null,
  }) });
  try {
    render(<WeeklyPredictions />);
    await screen.findByRole('button', { name: 'Week 1 (2026)' });
    expect(screen.getAllByRole('button').map(button => button.querySelector('span').textContent)).toEqual([
      'Week 1 (2026)', 'Week 14 (2025)', 'Week 1 (2025)',
    ]);
    expect(screen.getByText('Newest season game')).toBeInTheDocument();
    expect(screen.queryByText('Older season game')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Week 1 (2025)' }));
    expect(screen.getByText('Older season game')).toBeInTheDocument();
    expect(screen.queryByText('Newest season game')).not.toBeInTheDocument();
  } finally {
    global.fetch = originalFetch;
  }
});

test('shows only the latest saved prediction', async () => {
  const originalFetch = global.fetch;
  global.fetch = jest.fn().mockResolvedValue({ json: async () => ({
    weeks: [{ year: 2026, week: 0, games: [{
      matchup: 'North Carolina vs TCU', predicted: '2.94M', revised_predicted: '3.78M', actual: '4.908M',
    }] }], metrics: null,
  }) });
  try {
    render(<WeeklyPredictions />);
    expect(await screen.findByText('3.78M')).toBeInTheDocument();
    expect(screen.queryByText(/2.94M/)).not.toBeInTheDocument();
    expect(screen.queryByText(/original forecasts/)).not.toBeInTheDocument();
  } finally {
    global.fetch = originalFetch;
  }
});


test('ranked matchups keep both logos and missing stats render safely', async () => {
  const originalFetch = global.fetch;
  global.fetch = jest.fn().mockResolvedValue({ json: async () => ({
    weeks: [{ year: 2026, week: 2, games: [{ matchup: '#1 Ohio St. vs #4 Texas', predicted: '11.97M (8.52-16.81M) [retrospective]' }] }],
    metrics: { pregame: { median_error: null, mean_error: null }, postgame: null },
  }) });
  try {
    render(<WeeklyPredictions />);
    expect(await screen.findByAltText('Ohio St. logo')).toHaveAttribute('src', expect.stringContaining('/194.png'));
    expect(screen.getByAltText('Texas logo')).toHaveAttribute('src', expect.stringContaining('/251.png'));
    expect(screen.getByText('#1 Ohio St.')).toBeInTheDocument();
    expect(screen.getByText('#4 Texas')).toBeInTheDocument();
    expect(screen.getByText('11.97M')).toBeInTheDocument();
    expect(screen.getByText('Retrospective')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Week 2 (2026)' })).toHaveAttribute('aria-expanded', 'true');
  } finally { global.fetch = originalFetch; }
});

test('summarizes latest pregame errors in collapsed weeks and excludes pending games', async () => {
  const originalFetch = global.fetch;
  global.fetch = jest.fn().mockResolvedValue({ json: async () => ({ weeks: [
    { year: 2026, week: 2, games: [{ matchup: 'Pending', percent_error: null }] },
    { year: 2026, week: 1, games: [
      { percent_error: 0, post_percent_error: 90 },
      { percent_error: 10 }, { percent_error: 25 }, { percent_error: 45 },
      { percent_error: null }, { percent_error: undefined },
    ] },
  ] }) });
  try {
    render(<WeeklyPredictions />);
    const week = await screen.findByRole('button', { name: 'Week 1 (2026)' });
    expect(week).toHaveAttribute('aria-expanded', 'false');
    expect(week).toHaveTextContent('4/6 games scored');
    expect(week).toHaveTextContent('Median error17.5%');
    expect(week).toHaveTextContent('Mean error20.0%');
    expect(week).toHaveTextContent('Within 10%50.0%');
    expect(week).toHaveTextContent('Within 25%75.0%');
    expect(screen.getByRole('button', { name: 'Week 2 (2026)' })).toHaveTextContent('Awaiting ratings');
    fireEvent.click(week);
    expect(week).toHaveAttribute('aria-expanded', 'true');
    expect(week).toHaveTextContent('Median error17.5%');
  } finally { global.fetch = originalFetch; }
});
