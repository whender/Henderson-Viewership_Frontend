import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import FootballStandings from './FootballStandings';
test('switches records, filters conferences, and links teams with logos', () => {
 const data={season:2026,teams:[{team:'BYU',team_id:252,conference:'Big 12'},{team:'Arizona',team_id:12,conference:'Big 12'},{team:'Alabama',team_id:333,conference:'SEC'}],games:[{id:1,home:'BYU',away:'Arizona',seasonType:'regular',conferenceGame:true,completed:false,prediction:{home_win_probability:.7}}]};
 render(<MemoryRouter><FootballStandings data={data}/></MemoryRouter>);
 expect(screen.getByRole('button',{name:'Current'})).toHaveAttribute('aria-pressed','true');
 fireEvent.click(screen.getByRole('button',{name:'Predicted'}));expect(screen.getAllByText('1–0')).toHaveLength(2);
 fireEvent.change(screen.getByLabelText('Conference'),{target:{value:'Big 12'}});expect(screen.queryByRole('link',{name:'Alabama'})).not.toBeInTheDocument();
 expect(screen.getByRole('link',{name:'BYU'})).toHaveAttribute('href','/football-model/teams/BYU');expect(screen.getAllByRole('presentation')[0]).toHaveAttribute('src',expect.stringContaining('espncdn'));
});
