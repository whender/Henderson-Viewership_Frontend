import { fireEvent, render, screen } from '@testing-library/react';
import CfpPollPredictor from './CfpPollPredictor';
const row = {key:'id:251',team:'Texas',teamId:251,rank:1,wins:2,losses:0,qualityWins:1,bestWins:[{gameId:1,team:'Georgia',teamId:61}],worstLosses:[],drivers:[]};
const data = {schemaVersion:1,asOf:new Date().toISOString(),season:2026,firstRelease:'2026-11-03',trainingThrough:2025,trainingPolls:72,archivePolls:72,today:[row],next:{releaseDate:'2026-11-03',rows:[{...row,wins:8}],assumptions:[],unprojectedGames:0},latest:null,history:[{season:2025,releaseDate:'2025-12-07',forecastSource:'Historical reconstruction',rows:[{...row,record:'12-1',predictedRank:3}]}],overallEvaluation:{polls:41,historical_mean_absolute_rank_error:3.72,baselineRankError:4.01,historical_top_25_recall:.891,historical_top_12_recall:.86},evaluation:[],methodology:[],sources:[]};
beforeEach(()=>{global.fetch=jest.fn().mockResolvedValue({ok:true,json:async()=>data});});
afterEach(()=>jest.restoreAllMocks());
test('defaults to actual results, uses ESPN logos and switches to labeled scenario',async()=>{
 render(<CfpPollPredictor />);await screen.findByText('Resume rankings today');expect(screen.getByText('2–0')).toBeInTheDocument();expect(screen.getByAltText('Georgia')).toHaveAttribute('src','https://a.espncdn.com/i/teamlogos/ncaa/500/61.png');expect(screen.queryByText('Why this rank?')).not.toBeInTheDocument();expect(screen.getByText('None')).toBeInTheDocument();expect(screen.getByRole('presentation')).toHaveAttribute('src','https://a.espncdn.com/i/teamlogos/ncaa/500/251.png');
 fireEvent.change(screen.getByLabelText('Ranking basis'),{target:{value:'projected'}});expect(screen.getByText('8–0')).toBeInTheDocument();expect(screen.getByText(/simulations of/)).toBeInTheDocument();
});
test('handles unreleased rankings and distinguishes historical reconstruction',async()=>{
 render(<CfpPollPredictor />);await screen.findByText('Resume rankings today');fireEvent.click(screen.getByRole('button',{name:'Latest rankings'}));expect(screen.getByText(/No official 2026/)).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Rankings archive'}));expect(screen.getByText(/Historical reconstruction/)).toBeInTheDocument();expect(screen.getByText('3')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Model & accuracy'}));expect(screen.getByText('3.72')).toBeInTheDocument();expect(screen.getByText(/without the AP model/)).toBeInTheDocument();
});
test('shows fetch failures without invented rankings',async()=>{global.fetch.mockResolvedValue({ok:false});render(<CfpPollPredictor />);expect(await screen.findByRole('alert')).toHaveTextContent('temporarily unavailable');expect(screen.queryByRole('table')).not.toBeInTheDocument();});

test('refresh simulation changes records and opponent logos together', async () => {
 const alternative={rows:[{...row,wins:7,losses:1,bestWins:[],worstLosses:[{gameId:2,team:'Oklahoma',teamId:201}]}],assumptions:[]};
 global.fetch.mockResolvedValue({ok:true,json:async()=>({...data,next:{...data.next,alternatives:[alternative]}})});
 render(<CfpPollPredictor />);await screen.findByText('Resume rankings today');
 fireEvent.change(screen.getByLabelText('Ranking basis'),{target:{value:'projected'}});
 fireEvent.click(screen.getByRole('button',{name:'Refresh simulation'}));
 expect(screen.getByText('7–1')).toBeInTheDocument();expect(screen.getByAltText('Oklahoma')).toBeInTheDocument();expect(screen.queryByAltText('Georgia')).not.toBeInTheDocument();
 expect(screen.getByRole('status')).toHaveTextContent('Scenario 2 of 2');
});
