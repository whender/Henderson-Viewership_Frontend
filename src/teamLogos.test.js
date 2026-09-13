import { getTeamLogoUrl, parseMatchupTeams, getTeamTheme } from './teamLogos';

test.each(['#1 Ohio St.', '# 1 Ohio St.', 'No. 1 Ohio St.', 'No 1 Ohio St.', '1 Ohio St.', '  #1 Ohio St.'])('rank prefix resolves logo and theme: %s', name => {
  expect(getTeamLogoUrl(name)).toBe(getTeamLogoUrl('Ohio St.'));
  expect(getTeamTheme(name)).toEqual(getTeamTheme('Ohio St.'));
});
test('cleans both ranked teams while preserving school names with parentheses', () => {
  expect(parseMatchupTeams('#1 Ohio St. vs #4 Texas')).toEqual(['Ohio St.', 'Texas']);
  expect(getTeamLogoUrl('#12 Miami (OH)')).toBe(getTeamLogoUrl('Miami (OH)'));
  expect(getTeamLogoUrl('#3 No Such Team')).toBeNull();
});
