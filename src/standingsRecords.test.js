import { buildStandings, recordText } from './standingsRecords';
const teams=['A','B','C'].map((team,team_id)=>({team,team_id,conference:'Big 12'}));
const game=(id,home,away,extra={})=>({id,home,away,seasonType:'regular',conferenceGame:true,completed:false,prediction:{home_win_probability:.6,predicted_margin:3},...extra});
const row=(data,name,projected=false)=>buildStandings(data,projected).flatMap(g=>g.rows).find(t=>t.team===name);
test('finals only, distinguish league games, exclude postseason and championships',()=>{
 const data={teams,games:[game(1,'A','B',{completed:true,homePoints:21,awayPoints:10}),game(2,'A','C',{conferenceGame:false,completed:true,homePoints:0,awayPoints:7}),game(3,'A','B'),game(4,'A','B',{seasonType:'postseason',completed:true,homePoints:21,awayPoints:0}),game(5,'A','B',{notes:'Conference Championship',completed:true,homePoints:21,awayPoints:0})]};
 expect(recordText(row(data,'A').league)).toBe('1–0');expect(recordText(row(data,'A').overall)).toBe('1–1');
});
test('projected records conserve wins and losses and include in-progress games',()=>{
 const data={teams,games:[game(1,'A','B',{date:'2020-01-01',homePoints:0,awayPoints:14}),game(2,'B','C',{prediction:{home_win_probability:.2}})]};
 const rows=buildStandings(data,true)[0].rows;expect(rows.reduce((s,t)=>s+t.league.wins,0)).toBe(2);expect(rows.reduce((s,t)=>s+t.league.losses,0)).toBe(2);expect(recordText(row(data,'A',true).league,true)).toBe('0.6–0.4');
});
test('missing predictions, duplicate games, shared positions',()=>{
 const g=game(1,'A','B',{completed:true,homePoints:7,awayPoints:7}), data={teams,games:[g,g,game(2,'A','C',{prediction:null})]};
 expect(recordText(row(data,'A',true).league)).toBe('0–0–1');expect(row(data,'A',true).unprojected).toBe(1);expect(row(data,'A').position).toBe(row(data,'B').position);
});
test('Army Navy and FCS wins count overall only',()=>{
 const data={teams:[{team:'Army',conference:'American'},{team:'Navy',conference:'American'},{team:'Notre Dame',conference:'FBS Independents'}],games:[game(1,'Army','Navy'),game(2,'Notre Dame','FCS')]};
 expect(recordText(row(data,'Army',true).league)).toBe('0–0');expect(recordText(row(data,'Army',true).overall,true)).toBe('0.6–0.4');expect(recordText(row(data,'Notre Dame',true).overall,true)).toBe('0.6–0.4');
});
