"""Publish committee-rank predictions, historical results and backtests."""
import argparse,gzip,json
from dataclasses import replace
from datetime import datetime,timezone,timedelta
from pathlib import Path
import httpx
import numpy as np
from cfbpredict.games import Game
from cfbpredict.committee import CommitteeModel
from cfbpredict.committee_history import build_resume_state,_team_token
from cfbpredict.model import InsufficientDataError
from cfp_data import HISTORY_URL,import_new_polls
ROOT=Path(__file__).parent
LABELS={'wins':'Wins','losses':'Losses','win_percentage':'Winning percentage','record_strength':'Record strength',
    'schedule_strength':'Schedule strength','average_opponent_quality':'Opponent quality','strong_schedule_rate':'Strong opponents faced',
    'best_win_quality':'Best win','second_best_win_quality':'Second-best win','top_10_wins':'Wins over model-rated top 10 teams',
    'top_25_wins':'Wins over model-rated top 25 teams','road_quality_wins':'Quality road wins','bad_losses':'Losses to weaker opponents',
    'fcs_games':'FCS games','conference_champion':'Conference championship','conference_runner_up':'Conference runner-up',
    'power_rating':'Opponent-adjusted strength','undefeated':'Unbeaten record','one_loss':'One-loss record'}

def identities(games):
    out={}
    for g in sorted(games,key=lambda g:g.start_date):
        for side in ['home','away']:
            out[getattr(g,side+'_key')]=getattr(g,side+'_id')
    return out

def rankings(model,games,cutoff,ids):
    try:resumes,results=build_resume_state(games,cutoff)
    except InsufficientDataError:return []
    rows=[]
    for rank in model.rank(resumes,results)[:40]:
        r=rank.resume
        rows.append({'rank':rank.rank,'team':rank.team,'teamId':ids.get(rank.key),'key':rank.key,'wins':r.wins,'losses':r.losses,
            'conference':r.conference,'recordStrength':round(r.record_strength,2),'scheduleStrength':round(r.schedule_strength,3),
            'qualityWins':r.top_25_wins,'badLosses':r.bad_losses,
            'drivers':[{'feature':name,'label':LABELS.get(name,name),'contribution':round(value,4)} for name,value in sorted(rank.contributions,key=lambda t:-abs(t[1]))[:4]]})
    return rows

SIMULATIONS=10000
SIMULATION_SEED=2026

def scenario_games(games,predictions,now,cutoff):
    """Choose a coherent simulation nearest rounded mean wins, never independent team records."""
    games=list({g.id:g for g in games}.values())
    eligible=[];missing=[]
    for g in sorted(games,key=lambda g:(g.start_date,g.id)):
        if not g.completed and now<g.start_date and g.start_date+timedelta(hours=4)<=cutoff:
            pred=predictions.get(g.id,{}).get('prediction')
            if pred:
                p=pred['home_win_probability']
                if not np.isfinite(p) or not 0<=p<=1:raise ValueError('Invalid game win probability')
                eligible.append((g,pred))
            elif g.home_classification=='fbs' or g.away_classification=='fbs':missing.append(g.id)
    if not eligible:return games,[],missing
    rng=np.random.default_rng(SIMULATION_SEED)
    probabilities=np.array([p['home_win_probability'] for _,p in eligible])
    outcomes=rng.random((SIMULATIONS,len(eligible)))<probabilities
    keys=sorted({key for g,_ in eligible for key in (g.home_key,g.away_key)})
    counts=np.zeros((SIMULATIONS,len(keys)),dtype=np.int16);indices={k:i for i,k in enumerate(keys)}
    for j,(g,_) in enumerate(eligible):
        counts[:,indices[g.home_key]]+=outcomes[:,j]
        counts[:,indices[g.away_key]]+=~outcomes[:,j]
    # Completed wins add an integer to every simulation, so rounding remaining wins is equivalent.
    means=counts.mean(axis=0);targets=np.floor(means+.5)
    distance=((counts-targets)**2).sum(axis=1)
    candidates=np.flatnonzero(distance==distance.min())
    # Break equal record-distance ties with the probability of the complete result slate.
    logs=outcomes[candidates]@np.log(np.clip(probabilities,1e-15,1))+(~outcomes[candidates])@np.log(np.clip(1-probabilities,1e-15,1))
    chosen=outcomes[candidates[int(np.argmax(logs))]]
    replacements={};assumptions=[]
    for j,(g,pred) in enumerate(eligible):
        margin=max(int(np.floor(abs(pred['predicted_margin'])+.5)),1)
        home=bool(chosen[j]);signed=margin if home else -margin
        replacements[g.id]=replace(g,completed=True,home_points=max(signed,0),away_points=max(-signed,0))
        assumptions.append({'id':g.id,'home':g.home_team,'away':g.away_team,'winner':g.home_team if home else g.away_team,'margin':margin,
            'winnerProbability':float(probabilities[j] if home else 1-probabilities[j])})
    return [replacements.get(g.id,g) for g in games],assumptions,missing

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--refresh',action='store_true');args=parser.parse_args()
    now=datetime.now(timezone.utc)
    football=json.loads((ROOT.parent/'public/football/model.json').read_text());year=football['season']
    raw=json.loads(gzip.decompress((ROOT/'games.json.gz').read_bytes()))
    games=[Game.from_cfbd(g) for g in {g['id']:g for g in raw}.values()]
    ids=identities(games);name_ids={_team_token(g.home_team):g.home_id for g in games};name_ids.update({_team_token(g.away_team):g.away_id for g in games})
    polls=json.loads((ROOT/'cfp/polls.json').read_text())['polls']
    calendar=json.loads((ROOT/'cfp/schedule.json').read_text())
    dates=calendar['seasons'].get(str(year))
    if not dates:raise ValueError('Add the officially announced CFP release schedule for this season')
    if args.refresh and now.date().isoformat()>=dates[0]:
        response=httpx.get(HISTORY_URL,follow_redirects=True,timeout=45);response.raise_for_status()
        polls=import_new_polls(response.text,polls,games,now)
    validation=json.loads((ROOT/'cfp/validation.json').read_text())
    if validation['trainingThrough']!=year-1:raise ValueError('Retrain CFP model through the preceding season')
    model=CommitteeModel.load(ROOT/'cfp/model.json');current=[p for p in polls if p['season']==year]
    known={p['release_date'] for p in current}
    next_date=next((day for day in dates if day not in known),None)
    target=datetime.fromisoformat((next_date or dates[-1])+'T12:00:00+00:00')
    season_games=[g for g in games if g.season==year]
    today=rankings(model,season_games,min(now,datetime.fromisoformat(dates[-1]+'T12:00:00+00:00')),ids)
    projected,assumptions,missing=scenario_games(season_games,{g['id']:g for g in football['games']},now,target)
    outlook=rankings(model,projected,target,ids)
    output_path=ROOT.parent/'public/football/cfp.json';old=json.loads(output_path.read_text()) if output_path.exists() else {}
    saved=old.get('publishedForecasts',{})
    old_next=old.get('next',{})
    if old_next.get('releaseDate') and old_next['releaseDate'] in known:
        boundary=datetime.fromisoformat(old_next['releaseDate']+'T12:00:00+00:00')
        if datetime.fromisoformat(old['asOf'])<boundary:
            saved.setdefault(old_next['releaseDate'],{'asOf':old['asOf'],'rows':old_next['rows']})
    history=[]
    for p in reversed(polls):
        reconstructed=validation['reconstructed'].get(p['release_date'])
        live=saved.get(p['release_date'])
        predicted=live['rows'] if live else reconstructed
        if predicted is None and p['season']==year:
            predicted=rankings(model,season_games,datetime.fromisoformat(p['release_date']+'T12:00:00+00:00'),ids)
        by_name={_team_token(r['team']):r for r in predicted or []}
        rows=[{**e,'teamId':name_ids.get(_team_token(e['team'])),'predictedRank':by_name.get(_team_token(e['team']),{}).get('rank')} for e in p['entries']]
        history.append({'season':p['season'],'releaseDate':p['release_date'],'rows':rows,'forecastSource':'Archived forecast' if live else 'Historical reconstruction' if predicted else 'Not backtested'})
    evaluation=validation['evaluation'];count=sum(e['historical_poll_count'] for e in evaluation)
    keys=['historical_mean_absolute_rank_error','historical_top_25_recall','historical_top_12_recall','historical_pairwise_accuracy']
    stats={k:sum(e[k]*e['historical_poll_count'] for e in evaluation)/count for k in keys};stats['polls']=int(count)
    stats['baselineRankError']=sum(e['baseline']['historical_mean_absolute_rank_error']*e['historical_poll_count'] for e in evaluation)/count
    out={'schemaVersion':1,'asOf':now.isoformat(),'season':year,'firstRelease':dates[0],'schedule':dates,'trainingThrough':validation['trainingThrough'],
        'trainingPolls':validation['trainingPolls'],'archivePolls':len(polls),'next':{'releaseDate':next_date,'rows':outlook,'assumptions':assumptions,'unprojectedGames':len(missing),'simulation':{'count':SIMULATIONS,'seed':SIMULATION_SEED,'method':'Representative simulation nearest rounded average team wins; ties favor more probable game results'}},
        'today':today,'latest':next((p for p in history if p['season']==year),None),'history':history,'evaluation':evaluation,'overallEvaluation':stats,'publishedForecasts':saved,
        'methodology':['Predicts committee Top 25 order, not playoff seeds or qualification probabilities.',
            'Trained on CFP rankings starting in 2014; AP polls are not training targets or inputs.',
            'Each validation year trains only on earlier seasons. Target poll ranks and records never enter ranking inputs.',
            'Game results are included after a four-hour buffer. Historical release cutoffs are noon UTC on the official release date.',
            'Team resumes capture record and schedule strength, quality wins, bad losses, conference championships and opponent-adjusted strength. Head-to-head and common opponents modify comparable-team comparisons.',
            'Quality-win thresholds use model-rated opponents, not official committee top-25 membership. Scoring margins enter the underlying strength rating, not a direct committee resume feature.',
            'Rank error uses full predicted ranks without capping at 26. Top 12 membership is a ranking metric, not playoff-field accuracy.',
            'Run 10,000 independent game-outcome simulations using current football-model win probabilities. Select a coherent slate nearest rounded average team wins, breaking ties by slate probability, then rank its resumes. Whole-number records can differ from independent rounding to keep opponents consistent. Model margin magnitudes supply hypothetical scoring margins. This is a representative scenario, not an average CFP rank or a guaranteed outcome.'],
        'sources':[{'title':'Official CFP rankings history','url':HISTORY_URL},{'title':'CFP release schedule','url':calendar['source']},{'title':'Committee selection protocol','url':'https://collegefootballplayoff.com/sports/2016/10/24/selection-committee-protocol'}]}
    temp=output_path.with_suffix('.tmp');temp.write_text(json.dumps(out,separators=(',',':'),allow_nan=False));temp.replace(output_path)
    if args.refresh:(ROOT/'cfp/polls.json').write_text(json.dumps({'schema_version':1,'polls':polls},indent=2)+'\n')
    print('Published CFP',stats,'projected games',len(assumptions),flush=True)
if __name__=='__main__':main()
