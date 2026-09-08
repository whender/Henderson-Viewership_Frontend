import { fireEvent, render, screen, within, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ApPollPredictor from './ApPollPredictor';
const row={team:'Texas',teamId:251,rank:1,previousRank:2,movement:1,wins:2,losses:0,drivers:[{feature:'wins',label:'Season wins',contribution:.1}]};
const data={schemaVersion:1,asOf:new Date().toISOString(),season:2026,trainingThrough:2025,trainingPolls:1263,excludedTrainingPolls:[],coverage:{polls:1269,startYear:1936,endYear:2026},overallEvaluation:{polls:102,overlap:.9,rankError:1.6,baselineOverlap:.89,baselineRankError:2.3},evaluation:[],drivers:[],methodology:['Prior seasons only.'],sources:[],latest:{pollId:1269,label:'September 8',forecastSource:'Historical reconstruction',official:[{school:'Texas',teamId:251,rank:2}],rows:[row]},next:{estimatedReleaseDate:'2026-09-13',rows:[row],resultsSoFar:[{...row,wins:1}],assumptions:[]},history:[{id:1269,season:2026,label:'September 8',size:25,ranks:[{school:'Texas',teamId:251,rank:2,record:'1-0'}]},{id:248,season:1961,label:'Preseason',size:10,ranks:[{school:'Texas',teamId:251,rank:4,record:'0-0'}]}]};
beforeEach(()=>{global.fetch=jest.fn().mockResolvedValue({ok:true,json:async()=>data});});
afterEach(()=>{jest.restoreAllMocks();});
function open(){render(<MemoryRouter><ApPollPredictor /></MemoryRouter>);}
test('renders projected and completed-only outlook with ESPN logos',async()=>{
 open();await screen.findByText('Next release outlook');expect(screen.getByText('2–0')).toBeInTheDocument();expect(screen.getByRole('presentation')).toHaveAttribute('src','https://a.espncdn.com/i/teamlogos/ncaa/500/251.png');
 fireEvent.change(screen.getByLabelText('Forecast basis'),{target:{value:'sofar'}});expect(screen.getByText('1–0')).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Find a team'),{target:{value:'BYU'}});expect(screen.getByRole('status')).toHaveTextContent('No teams');
});
test('historical selector preserves the actual Top 10 era',async()=>{
 open();await screen.findByText('Next release outlook');fireEvent.click(screen.getByRole('button',{name:'Poll archive'}));fireEvent.change(screen.getByLabelText('AP season'),{target:{value:'1961'}});expect(screen.getByText('1961 · Preseason · AP Top 10')).toBeInTheDocument();expect(within(screen.getByRole('table')).getByText('4')).toBeInTheDocument();
});
test('labels latest reconstruction and shows baseline validation',async()=>{
 open();await screen.findByText('Next release outlook');fireEvent.click(screen.getByRole('button',{name:'Latest poll check'}));expect(screen.getByText(/Historical reconstruction/)).toBeInTheDocument();fireEvent.click(screen.getByRole('button',{name:'Model & accuracy'}));expect(screen.getByText('1.60')).toBeInTheDocument();expect(screen.getByText('Previous-poll baseline: 2.30')).toBeInTheDocument();
});
test('reports data errors without fabricating a ranking',async()=>{
 global.fetch.mockResolvedValue({ok:false});open();await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent('temporarily unavailable'));expect(screen.queryByRole('table')).not.toBeInTheDocument();
});
