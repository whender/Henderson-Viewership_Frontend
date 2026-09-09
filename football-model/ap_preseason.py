"""Separate preseason AP model with immutable, season-specific inputs."""
import gzip
import json
from pathlib import Path
import numpy as np
from ap_model import predict, matrix
from ap_preseason_ranker import predict_pairwise, selection_then_pairwise, VERSION

HISTORY = ['previous_rank','previous_rank_squared','prior_season_win_percentage','historical_poll_presence']
ROSTER = ['talent_z','recruiting_points_z','reconciled_offense_continuity','reconciled_passing_continuity',
    'roster_offense_retention_rate','roster_defense_retention_rate','qb_starter_returns','qb_pass_usage_retention_rate',
    'portal_all_net_rating_z','portal_qb_net_rating_z','coach_change','coach_tenure_years','talent_missing',
    'recruiting_missing','returning_missing','roster_missing','qb_retention_missing','portal_missing','coach_current_missing']
FEATURES = HISTORY + ['roster_offense','roster_defense'] + ROSTER
LABELS = dict(zip(FEATURES, ['Previous season AP finish','Previous AP finish (nonlinear)','Previous season winning percentage',
    'Three-year AP presence','Projected offensive efficiency','Projected defensive efficiency','Roster talent','Recruiting class',
    'Returning offensive production','Returning passing production','Offensive roster continuity','Defensive roster continuity',
    'Returning starting quarterback','Returning quarterback usage','Transfer talent balance','Quarterback transfer talent',
    'Coaching change','Head coach tenure','Talent data coverage','Recruiting data coverage','Returning production coverage',
    'Roster data coverage','Quarterback data coverage','Transfer data coverage','Coaching data coverage']))
ROOT=Path(__file__).parent

def load_inputs(path):
    data=json.loads(gzip.decompress(Path(path).read_bytes()))
    if data.get('schemaVersion')!=1 or data['features']!=FEATURES:
        raise ValueError('Preseason feature schema mismatch')
    seen=set()
    for o in data['observations']:
        if o['season'] in seen: raise ValueError('Duplicate preseason input season')
        seen.add(o['season'])
        x=np.asarray(o['x'],dtype=float)
        if x.shape!=(len(o['teams']),len(FEATURES)) or not np.isfinite(x).all():
            raise ValueError('Invalid preseason feature matrix')
        if len({str(t['teamId']) for t in o['teams']})!=len(o['teams']):
            raise ValueError('Duplicate preseason team')
        o['x']=x;o['y']=np.asarray(o['y'],dtype=float)
        o['actual']={int(i):r for i,r in o['actual'].items()}
        if o['y'].shape!=(len(x),) or not np.isfinite(o['y']).all():raise ValueError('Invalid preseason training targets')
    return data

def preseason_scores(model,x,extended=None):
    base=predict(model,np.asarray(x),feature_names=model['features'])
    if 'reranker' not in model:return base
    if model.get('version')!=VERSION or extended is None:
        raise ValueError('Missing or incompatible preseason comparison snapshot')
    z=np.asarray(extended,dtype=float)
    if z.shape!=(len(x),len(model['reranker']['means'])) or not np.isfinite(z).all():
        raise ValueError('Invalid preseason comparison snapshot')
    if model['reranker']['trainedThrough']!=model['trainedThrough']:
        raise ValueError('Preseason comparison model training cutoff mismatch')
    return selection_then_pairwise(base,predict_pairwise(model['reranker'],z))

def rank_rows(model,x,teams,extended=None):
    names=model['features']
    scores=preseason_scores(model,x,extended)
    terms=(np.asarray(x)-model['means'])/model['scales']*np.asarray(model['coefficients'][1:])
    rows=[]
    for rank,i in enumerate(np.argsort(-scores,kind='stable')[:40],1):
        t=teams[i];previous=t.get('previousRank')
        effects=sorted(range(len(names)),key=lambda j:abs(terms[i,j]),reverse=True)[:4]
        rows.append({**t,'wins':0,'losses':0,'ties':0,'rank':rank,'movement':previous-rank if previous else None,
            'drivers':([{'feature':'selection','label':'Top 25 selection','contribution':None,'detail':'Roster-informed preseason model'}, {'feature':'ordering','label':'Order within the Top 25','contribution':None,'detail':'Team comparisons using offseason inputs and prior AP history'}] if 'reranker' in model else [{'feature':names[j],'label':LABELS[names[j]],'contribution':round(float(terms[i,j]),4)} for j in effects])})
    return rows

def preseason_forecast(season,polls,games,candidates,artifact_path=None):
    path=Path(artifact_path) if artifact_path else ROOT/'ap/preseason_model.json'
    artifact=json.loads(path.read_text())
    if artifact['season']!=season or artifact['model']['trainedThrough']!=season-1:
        raise ValueError('Prepare the preseason model for this season before publishing')
    # Stored input vectors never read this season's poll or results during publication.
    snapshot=artifact.get('snapshot')
    if snapshot and snapshot.get('season')==season and len(snapshot.get('teams',[]))>=25:
        x=np.asarray(snapshot['x'],dtype=float)
        if x.shape!=(len(snapshot['teams']),len(FEATURES)) or not np.isfinite(x).all():
            raise ValueError('Corrupt preseason input snapshot')
        model=artifact['model'];rows=rank_rows(model,x,snapshot['teams'],snapshot.get('extended'));basis='Roster-informed selection with pairwise ranking' if 'reranker' in model else 'Roster-informed preseason model'
    else:
        from ap_model import FEATURES as SHARED
        earlier=[p for p in polls if p['season']<season]
        target={'season':season,'kind':'preseason','cutoff':None,'size':25}
        x,teams=matrix(target,earlier[-1] if earlier else None,earlier,[g for g in games if g['season']<season],candidates)
        rows=rank_rows(artifact['fallback'],x[:,[SHARED.index(k) for k in HISTORY]],teams)
        basis='Poll-history fallback · roster inputs unavailable'
    return {'season':season,'rows':rows,'basis':basis,'generatedAt':artifact['generatedAt'],
        'releaseDate':artifact['releaseDate'],'inputBasis':artifact['inputBasis'],'evaluation':artifact['evaluation'],
        'overallEvaluation':artifact['overallEvaluation'],'trainingThrough':artifact['model']['trainedThrough'],
        'trainingPolls':artifact['model']['trainingPolls'],'forecastSource':artifact['forecastSource']}
