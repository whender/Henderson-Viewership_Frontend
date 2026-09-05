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
    expect(screen.getAllByRole('button').map(button => button.textContent)).toEqual([
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
