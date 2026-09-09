"""Publish AP poll outlooks independently of the football strength model."""
import argparse,gzip,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import httpx
import numpy as np
from ap_preseason import preseason_forecast
from ap_data import parse_options,parse_entries,normalize_poll,token
from ap_model import matrix,predict,ranks,LABELS,FEATURES,timestamp
ROOT=Path(__file__).resolve().parent

def dump_gzip(path,value):path.write_bytes(gzip.compress(json.dumps(value,separators=(',',':')).encode(),mtime=0))
def ranked(model,poll,previous,earlier,games,candidates):
    x,teams=matrix(poll,previous,earlier,games,candidates)
    scores=predict(model,x);order=np.argsort(-scores,kind='stable')
    z=(x-model['means'])/model['scales'];co=np.asarray(model['coefficients'][1:])
    output=[]
    for rank,i in enumerate(order[:40],1):
        terms=z[i]*co
        drivers=sorted(range(len(terms)),key=lambda j:abs(terms[j]),reverse=True)[:4]
        output.append({**teams[i],'rank':rank,'movement':teams[i]['previousRank']-rank if teams[i]['previousRank'] else None,
            'drivers':[{'feature':FEATURES[j],'label':LABELS[FEATURES[j]],'contribution':round(float(terms[j]),4)} for j in drivers]})
    return output

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--refresh',action='store_true');args=parser.parse_args()
    now=datetime.now(timezone.utc);football=json.loads((ROOT.parent/'public/football/model.json').read_text());year=football['season']
    polls=json.loads(gzip.decompress((ROOT/'ap/polls.json.gz').read_bytes()));history=json.loads(gzip.decompress((ROOT/'ap/games.json.gz').read_bytes()))
    lookup=json.loads((ROOT/'ap/identities.json').read_text())
    release=json.loads((ROOT/'ap/preseason_dates.json').read_text())['dates'].get(str(year))
    if args.refresh and (not release or now.date().isoformat()>=release):
        with httpx.Client(follow_redirects=True,timeout=40) as client:
            page=client.get(f'https://www.collegepollarchive.com/football/ap/seasons.cfm?seasonid={year}');page.raise_for_status()
            options=parse_options(page.text);known={p['id'] for p in polls}
            for opt in options:
                if opt['id'] not in known:
                    url=f"https://www.collegepollarchive.com/football/ap/seasons.cfm?appollid={opt['id']}"
                    response=client.get(url);response.raise_for_status()
                    p=normalize_poll({'season':year,**opt,'ranks':parse_entries(response.text),'source':url},lookup)
                    if any(str(r['teamId']).startswith('archive:') for r in p['ranks']):raise ValueError('Unmapped AP team; refusing ambiguous publication')
                    polls.append(p)
        polls.sort(key=lambda p:p['id']);dump_gzip(ROOT/'ap/polls.json.gz',polls)
    raw=list({g['id']:g for g in json.loads(gzip.decompress((ROOT/'games.json.gz').read_bytes()))}.values())
    keep=['id','season','week','seasonType','startDate','completed','homeId','homeTeam','awayId','awayTeam','homePoints','awayPoints','homeClassification','awayClassification','homeConference','awayConference','neutralSite']
    fbs_ids={t['team_id'] for t in football['teams']}
    history=[g for g in history if g['season']!=year]+[{k:g.get(k) for k in keep} for g in raw if g['season']==year and (g.get('homeId') in fbs_ids or g.get('awayId') in fbs_ids)]
    if args.refresh:dump_gzip(ROOT/'ap/games.json.gz',history)
    model=json.loads((ROOT/'ap/model.json').read_text())
    if model['trainedThrough']!=year-1:raise ValueError('Retrain the AP model through the previous season before publishing')
    current=[p for p in polls if p['season']==year]
    preseason_mode=not current
    latest=current[-1] if current else next(p for p in reversed(polls) if p['season']<year)
    candidates=[{'team':t['team'],'teamId':t['team_id'],'conference':t['conference']} for t in football['teams']]
    source_games=[g for g in history if year-1<=g['season']<=year]
    preseason=preseason_forecast(year,polls,history,candidates)
    official_preseason=next((p for p in current if p['kind']=='preseason'),None)
    preseason['official']=official_preseason['ranks'] if official_preseason else []
    # Forecast the next Sunday release. The date is an estimate, explicitly labeled in the UI.
    base=timestamp(latest['cutoff']) if latest['kind']=='regular' and latest.get('cutoff') else now
    days=(6-base.weekday())%7
    target=(base+timedelta(days=days)).replace(hour=16,minute=0,second=0,microsecond=0)
    if target<=base:target+=timedelta(days=7)
    if preseason_mode:
        target=timestamp(preseason['releaseDate']+'T00:00:00+00:00')
    nextpoll={'season':year,'kind':'preseason' if preseason_mode else 'regular','cutoff':target.isoformat(),'size':25}
    sofar={**nextpoll,'cutoff':min(now,target).isoformat()}
    projections={g['id']:g for g in football['games']};assumptions=[];projected=[]
    for g in source_games:
        p=projections.get(g['id']);ng=dict(g)
        if not preseason_mode and g['season']==year and not g.get('completed') and timestamp(g['startDate'])+timedelta(hours=4)<=target and timestamp(g['startDate'])>now:
            if p and p.get('prediction'):
                pred=p['prediction'];margin=pred['predicted_margin'];hwin=pred['home_win_probability']>=.5
                signed=max(abs(margin),1)*(1 if hwin else -1)
                # Synthetic scores carry ONLY the expected winner/margin into resume features.
                ng.update(completed=True,homePoints=max(signed,0),awayPoints=max(-signed,0))
                assumptions.append({'id':g['id'],'home':g['homeTeam'],'away':g['awayTeam'],'date':g['startDate'],'winner':g['homeTeam'] if hwin else g['awayTeam'],'margin':round(abs(signed),1)})
        projected.append(ng)
    output_path=ROOT.parent/'public/football/ap.json'
    previous_output=json.loads(output_path.read_text()) if output_path.exists() else {}
    # Preserve a published next-poll forecast after its target becomes official.
    saved=previous_output.get('publishedForecasts',{})
    previous_forecast=previous_output.get('next',{})
    if previous_forecast and previous_forecast.get('previousPollId')!=latest['id']:
        key=str(previous_forecast['previousPollId']+1)
        actual=next((p for p in polls if str(p['id'])==key),None)
        if actual and actual.get('cutoff') and timestamp(previous_output['asOf'])<timestamp(actual['cutoff']):
            saved.setdefault(key,{'asOf':previous_output['asOf'],'rows':previous_forecast['rows'],'basis':'Projected remaining games'})
    # These reconstructions exclude the target ranking but are distinct from stored live forecasts.
    previous=next((p for p in reversed(polls) if p['id']<latest['id']),None)
    earlier=[p for p in polls if p['id']<latest['id']]
    latest_rows=(preseason['rows'] if latest['kind']=='preseason' else ranked(model,latest,previous,earlier,source_games,candidates)) if current else []
    next_rows=preseason['rows'] if preseason_mode else ranked(model,nextpoll,latest,polls,projected,candidates)
    sofar_rows=preseason['rows'] if preseason_mode else ranked(model,sofar,latest,polls,source_games,candidates)
    # Score only historical regular polls; final/preseason timing limitations remain explicit.
    evaluation=model['evaluation'];n=sum(e['polls'] for e in evaluation)
    stats={k:sum(e[k]*e['polls'] for e in evaluation)/n for k in ['overlap','rankError','baselineOverlap','baselineRankError']};stats['polls']=n
    coverage=json.loads((ROOT/'ap/coverage.json').read_text());coverage.update(polls=len(polls),endYear=year)
    coefficients=[{'feature':name,'label':LABELS[name],'effect':round(model['coefficients'][i+1],4)} for i,name in enumerate(FEATURES)]
    out={'schemaVersion':1,'asOf':now.isoformat(),'season':year,'trainingThrough':model['trainedThrough'],'trainingPolls':model['trainingPolls'],
        'preseason':preseason,'activeModel':'preseason' if preseason_mode else 'in-season','coverage':coverage,'excludedTrainingPolls':model['excludedPolls'],'evaluation':evaluation,'overallEvaluation':stats,
        'latest':{'pollId':latest['id'],'label':latest['label'] if current else 'Preseason poll not released','releaseDate':latest['releaseDate'] if current else None,'official':latest['ranks'] if current else [],'rows':saved.get(str(latest['id']),{}).get('rows',latest_rows),'forecastSource':'Archived forecast' if str(latest['id']) in saved else 'Historical reconstruction'},
        'next':{'previousPollId':latest['id'],'estimatedReleaseDate':target.date().isoformat(),'rows':next_rows,'resultsSoFar':sofar_rows,'assumptions':assumptions},
        'drivers':sorted(coefficients,key=lambda c:-abs(c['effect'])),'publishedForecasts':saved,
        'history':[{'id':p['id'],'season':p['season'],'label':p['label'],'size':p['size'],'releaseDate':p['releaseDate'],'ranks':p['ranks']} for p in reversed(polls)],
        'methodology':['Predicts AP voting order, not team strength or the CFP committee.',
            'Trained on prior seasons only; previous polls and results available before release supply the features.',
            'All archived polls contribute poll-history information. A small number of polls without matching game identities are excluded as training targets.',
            'Preseason rankings use a separate roster-informed model trained only on earlier preseason polls. Weekly forecasts use the in-season model.',
            'Preseason release dates come from College Poll Archive; input cutoffs use the start of release day. Annual offseason inputs are treated as pre-poll information, not as live forecast archives.',
            'Historical final polls without a verified release date use poll-history features only; game-result features are masked.',
            'Historical Top 10/20/25 rankings are normalized within each era. Recent seasons have greater weight.',
            'Validation uses 2019–2025 in-season polls, fitting only earlier seasons each year. Rank error caps unranked teams at 26.',
            'Next-release projections assume the football model’s favored teams win the remaining listed games. They are a scenario, not calibrated rank probabilities.',
            'Feature effects describe statistical associations, not causes. Scores are not projected AP vote totals.'],
        'sources':[{'title':'College Poll Archive · AP history','url':'https://www.collegepollarchive.com/football/ap/seasons.cfm'}, {'title':'College Football Data · game results','url':'https://collegefootballdata.com'}]}
    temporary=output_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(out,separators=(',',':'),allow_nan=False));temporary.replace(output_path);print('Published AP outlook',len(polls),'historical polls',len(assumptions),'projected games')
if __name__=='__main__':main()
