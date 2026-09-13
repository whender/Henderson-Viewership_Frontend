import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { getTeamLogoUrl } from './teamLogos';
import { buildStandings, recordText } from './standingsRecords';

export default function FootballStandings({ data }) {
  const [projected, setProjected] = useState(false);
  const [conference, setConference] = useState('');
  const standings = useMemo(() => buildStandings(data, projected), [data, projected]);
  const visible = standings.filter(group => !conference || group.conference === conference);
  const missing = visible.some(group => group.rows.some(t => t.unprojected));
  return <section className="home-panel cfb-standings">
    <div className="home-panel-header"><div><p className="home-kicker">{data.season} Season</p><h3>Conference Standings</h3></div>
      <div className="cfb-standings-toggle" role="group" aria-label="Standings view">
        <button type="button" aria-pressed={!projected} onClick={() => setProjected(false)}>Current</button>
        <button type="button" aria-pressed={projected} onClick={() => setProjected(true)}>Predicted</button>
      </div>
    </div>
    <div className="cfb-controls"><label>Conference<select value={conference} onChange={e => setConference(e.target.value)}><option value="">All conferences</option>{standings.map(g => <option key={g.conference}>{g.conference}</option>)}</select></label></div>
    <p className="cfb-footnote">{projected ? 'Projected final regular-season records: completed results plus the model’s picked winner in each remaining game, including games in progress. These are whole-game picks, not expected win totals.' : 'Completed regular-season games only. Games in progress count once final.'} Ordered by conference winning percentage; tied percentages share a position. Official conference tiebreakers are not applied. Independents are ordered by overall winning percentage.</p>
    {missing && <p role="status" className="cfb-notice">Some games have no usable result or forecast. Affected records are marked incomplete.</p>}
    {visible.map(group => <section key={group.conference} className="cfb-standings-conference" aria-label={group.conference}>
      <h4>{group.conference}</h4>
      <table className="cfb-table"><caption className="sr-only">{projected ? 'Predicted' : 'Current'} {group.conference} standings</caption><thead><tr><th scope="col">Pos.</th><th scope="col">Team</th><th scope="col">Conf.</th><th scope="col">Overall</th></tr></thead><tbody>{group.rows.map(team => <tr key={team.team_id}>
        <td className="cfb-rank">{team.position}</td><th scope="row"><Link className="cfb-team" to={`/football-model/teams/${encodeURIComponent(team.team)}`}><img src={team.logo || getTeamLogoUrl(team.team)} alt="" loading="lazy" onError={e => { e.currentTarget.style.visibility = 'hidden'; }} /><span>{team.team}{team.unprojected > 0 && <small>Incomplete · {team.unprojected} games</small>}</span></Link></th>
        <td className="cfb-number">{group.isIndependent ? '—' : recordText(team.league)}</td><td className="cfb-number">{recordText(team.overall)}</td>
      </tr>)}</tbody></table>
    </section>)}
    {!visible.length && <p>No conference standings available.</p>}
  </section>;
}
