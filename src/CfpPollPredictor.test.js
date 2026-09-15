import { fireEvent, render, screen } from '@testing-library/react';
import CfpPollPredictor from './CfpPollPredictor';
const row = {key:'id:251',team:'Texas',teamId:251,rank:1,wins:2,losses:0,qualityWins:1,bestWins:[{gameId:1,team:'Georgia',teamId:61}],worstLosses:[],drivers:[]};
const data = {schemaVersion:1,asOf:new Date().toISOString(),season:2026,firstRelease:'2026-11-03',trainingThrough:2025,trainingPolls:72,archivePolls:72,today:[row],next:{releaseDate:'2026-11-03',rows:[{...row,wins:8}],assumptions:[],unprojectedGames:0},latest:null,history:[{season:2025,releaseDate:'2025-12-07',forecastSource:'Historical reconstruction',rows:[{...row,record:'12-1',predictedRank:3}]}],overallEvaluation:{polls:41,historical_mean_absolute_rank_error:3.72,baselineRankError:4.01,historical_top_25_recall:.891,historical_top_12_recall:.86},evaluation:[],methodology:[],sources:[]};
beforeEach(()=>{global.fetch=jest.fn().mockResolvedValue({ok:true,json:async()=>data});});
afterEach(()=>jest.restoreAllMocks());
test('defaults to actual results, uses ESPN logos and switches to labeled scenario',async()=>{
 render(<CfpPollPredictor />);await screen.findByText('Resume rankings today');expect(screen.getByText('2–0')).toBeInTheDocument();expect(screen.getByAltText('Georgia')).toHaveAttribute('src','https://a.espncdn.com/i/teamlogos/ncaa/500/61.png');expect(screen.queryByText('Why this rank?')).not.toBeInTheDocument();expect(screen.getByText('None')).toBeInTheDocument();expect(screen.getByRole('presentation')).toHaveAttribute('src','https://a.espncdn.com/i/teamlogos/ncaa/500/251.png');
 fireEvent.change(screen.getByLabelText('Ranking basis'),{target:{value:'projected'}});expect(screen.getByText('8–0')).toBeInTheDocument();expect(screen.getByText(/Most likely selects/)).toBeInTheDocument();
});
test('handles unreleased rankings and distinguishes historical reconstruction',async()=>{
 render(<CfpPollPredictor />);await screen.findByText('Resume rankings today');fireEvent.click(screen.getByRole('button',{name:'Latest rankings'}));expect(screen.getByText(/No official 2026/)).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Rankings archive'}));expect(screen.getByText(/Historical reconstruction/)).toBeInTheDocument();expect(screen.getByText('3')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Model & accuracy'}));expect(screen.getByText('3.72')).toBeInTheDocument();expect(screen.getByText(/without the AP model/)).toBeInTheDocument();
});
test('shows fetch failures without invented rankings',async()=>{global.fetch.mockResolvedValue({ok:false});render(<CfpPollPredictor />);expect(await screen.findByRole('alert')).toHaveTextContent('temporarily unavailable');expect(screen.queryByRole('table')).not.toBeInTheDocument();});

test('projection arrows change records and logos together and return to main', async () => {
 const alternative={rows:[{...row,wins:7,losses:1,bestWins:[],worstLosses:[{gameId:2,team:'Oklahoma',teamId:201}]}],assumptions:[]};
 global.fetch.mockResolvedValue({ok:true,json:async()=>({...data,next:{...data.next,alternatives:[alternative]}})});
 render(<CfpPollPredictor />);await screen.findByText('Resume rankings today');
 fireEvent.change(screen.getByLabelText('Ranking basis'),{target:{value:'projected'}});
 fireEvent.click(screen.getByRole('button',{name:'Next projection'}));
 expect(screen.getByText('7–1')).toBeInTheDocument();expect(screen.getByAltText('Oklahoma')).toBeInTheDocument();expect(screen.queryByAltText('Georgia')).not.toBeInTheDocument();
 expect(screen.getByRole('status')).toHaveTextContent('Projection 1 of 1');
 fireEvent.click(screen.getByRole('button',{name:'Previous projection'}));
 expect(screen.getByText('8–0')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Previous projection'}));
 expect(screen.getByText('7–1')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Most likely'}));
 expect(screen.getByText('8–0')).toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'Refresh simulation'})).not.toBeInTheDocument();
});

test('outcome editor limits teams, shares game outcomes, and clears overrides', async () => {
 const {projectScenario} = require('./cfpScenario.mjs');
 const teams=[row,{key:'id:201',team:'Oklahoma',teamId:201},{key:'id:61',team:'Georgia',teamId:61}].map((t,i)=>({...t,power:10-i}));
 const model={feature_schema:['wins','losses'],coefficients:{wins:1,losses:-1},feature_scales:{wins:1,losses:1},comparable_window:0,head_to_head_coefficient:0,common_opponent_coefficient:0};
 const game={id:1,homeKey:row.key,awayKey:'id:201',home:'Texas',away:'Oklahoma',homeId:251,awayId:201,homeClassification:'fbs',awayClassification:'fbs',projected:true,probability:.9,margin:7,date:'2026-10-10T18:00:00Z',powerChange:[0,0,0]};
 const engine={version:1,teams,games:[game],model};
 const eligible=teams.slice(0,2).map(t=>({...t,probability:.8}));
 const next={...data.next,...projectScenario(engine),alternatives:Array.from({length:25},(_,i)=>projectScenario(engine,i+1)),scenarioEngine:engine,eligibleTeams:eligible,simulation:{count:1000}};
 global.fetch.mockResolvedValue({ok:true,json:async()=>({...data,next})});
 render(<CfpPollPredictor />); await screen.findByText('Resume rankings today');
 fireEvent.change(screen.getByLabelText('Ranking basis'),{target:{value:'projected'}});
 const teamSelect=screen.getByLabelText('Team to customize');
 expect([...teamSelect.options].map(o=>o.value)).toEqual(['id:251','id:201']);
 const winner=screen.getByLabelText('Winner: Oklahoma at Texas');
 fireEvent.change(winner,{target:{value:'id:201'}});
 expect(screen.getByRole('status')).toHaveTextContent('Custom outcomes');
 expect(screen.getByRole('row', {name:/^\d+ Texas /})).toHaveTextContent('0–1');
 fireEvent.change(teamSelect,{target:{value:'id:201'}});
 expect(screen.getByLabelText('Winner: Oklahoma at Texas')).toHaveValue('id:201');
 fireEvent.click(screen.getByRole('button',{name:'Next projection'}));
 expect(screen.getByRole('row', {name:/^\d+ Texas /})).toHaveTextContent('0–1');
 fireEvent.click(screen.getByRole('button',{name:'Most likely'}));
 fireEvent.click(screen.getByRole('button',{name:'Clear all outcomes'}));
 expect(screen.getByRole('row', {name:/^\d+ Texas /})).toHaveTextContent('1–0');
 expect(screen.getByLabelText('Winner: Oklahoma at Texas')).toHaveValue('');
});
