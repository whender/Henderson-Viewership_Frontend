import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from './App';

jest.mock('./FootballModel', () => () => <h2>Football model content</h2>);
beforeEach(() => { global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({}) }); });
afterEach(() => { jest.restoreAllMocks(); localStorage.clear(); });

test('separate football model route works with basketball selected', async () => {
  localStorage.setItem('henderson-viewership-sport', 'basketball');
  await act(async () => { render(<MemoryRouter initialEntries={['/football-model']}><App /></MemoryRouter>); });
  expect(screen.getByText('Football model content')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Football Model' })).toHaveAttribute('href', '/football-model');
});

test('mobile navigation includes the independent football model tab', async () => {
  await act(async () => { render(<MemoryRouter><App /></MemoryRouter>); });
  fireEvent.click(screen.getByRole('button', { name: 'Open menu' }));
  const links = screen.getAllByRole('link', { name: 'Football Model' });
  expect(links).toHaveLength(2);
  fireEvent.click(links[1]);
  expect(screen.getByText('Football model content')).toBeInTheDocument();
});
