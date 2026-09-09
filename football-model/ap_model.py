"""AP voter-behavior model. Inputs never contain the target poll's rankings."""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import numpy as np

FEATURES = ['previous_rank','previous_rank_squared','previous_movement','preseason_rank',
            'last_season_final','wins','losses','win_percentage','average_margin','schedule_strength',
            'ranked_wins','ranked_losses','recent_wins','recent_losses','recent_margin',
            'previous_rank_x_recent_loss','previous_rank_x_recent_win','previous_rank_x_recent_margin',
            'prior_season_win_percentage','historical_poll_presence','season_progress','preseason_poll',
            'results_unavailable','top25_era']
LABELS = dict(zip(FEATURES, ['Previous AP position','Previous position (nonlinear)','Recent AP movement','Preseason AP position',
    'Previous season final AP position','Season wins','Season losses','Winning percentage','Average scoring margin','Opponent winning percentage',
    'Wins over previously ranked teams','Losses to previously ranked teams','Wins since previous poll','Losses since previous poll','Recent scoring margin',
    'Previous position × recent loss','Previous position × recent win','Previous position × recent margin',
    'Previous season winning percentage','Three-year AP presence','Season progress','Preseason poll','Unavailable result timing','Top 25 era']))

def timestamp(value):
    return datetime.fromisoformat(value.replace('Z','+00:00'))

def rank_strength(poll):
    if not poll:return {}
    n=poll['size']
    return {str(r['teamId']):max(0.,(n+1-r['rank'])/n) for r in poll['ranks'] if r['rank']<=n and r.get('teamId') is not None}

def ranks(poll):
    return {str(r['teamId']):r['rank'] for r in poll['ranks'] if r.get('teamId') is not None and r['rank']<=poll['size']} if poll else {}

def finished(g,cutoff):
    return bool(g.get('completed') and g.get('homePoints') is not None and g.get('awayPoints') is not None
                and timestamp(g['startDate'])+timedelta(hours=4)<=cutoff)

def matrix(poll, previous, earlier, games, candidates=None):
    """Return candidate features using strictly earlier polls and buffered results."""
    year=poll['season']; prior=[p for p in earlier if p['season']<year]
    last=prior[-1] if prior else None
    season_polls=[p for p in earlier if p['season']==year]
    pre=next((p for p in season_polls if p['kind']=='preseason'),None)
    prev=rank_strength(previous); pre_rank=rank_strength(pre); last_rank=rank_strength(last)
    prior_prev=rank_strength(earlier[-2] if len(earlier)>1 else None)
    ids={}; season_games=[g for g in games if g['season']==year]
    for g in season_games:
        for side in ['home','away']:
            key=g.get(side+'Id');cl=g.get(side+'Classification')
            if key is not None and (year < 1978 or cl in (None,'fbs') or str(key) in prev):
                ids[str(key)]={'team':g[side+'Team'],'teamId':key,'conference':g.get(side+'Conference')}
    if previous:
        for r in previous['ranks']:
            if r.get('teamId') is not None:ids.setdefault(str(r['teamId']),{'team':r['school'],'teamId':r['teamId'],'conference':r.get('conference')})
    if candidates is not None:ids={str(t['teamId']):t for t in candidates}
    cutoff=timestamp(poll['cutoff']) if poll.get('cutoff') else None
    prevcut=timestamp(previous['cutoff']) if previous and previous.get('cutoff') else datetime(year,1,1,tzinfo=timezone.utc)
    # Undated historical finals retain poll-history features, but no guessed game information.
    usable=[g for g in season_games if cutoff and finished(g,cutoff)]
    stats=defaultdict(lambda:[0.,0.,0.,0.,0.,0.,0.,0.,0.,[]])
    for g in usable:
        for side,other in [('home','away'),('away','home')]:
            key=str(g[side+'Id']);opp=str(g[other+'Id']);s=stats[key];margin=g[side+'Points']-g[other+'Points']
            s[0]+=margin>0;s[1]+=margin<0;s[2]+=margin==0;s[3]+=np.clip(margin,-35,35);s[9].append(opp)
            s[4]+=int(margin>0)*int(opp in prev);s[5]+=int(margin<0)*int(opp in prev)
            if timestamp(g['startDate'])>=prevcut:
                s[6]+=margin>0;s[7]+=margin<0;s[8]+=np.clip(margin,-35,35)
    old=defaultdict(lambda:[0,0])
    for g in games:
        if g['season']==year-1 and g.get('completed') and g.get('homePoints') is not None and g.get('awayPoints') is not None:
            for side,other in [('home','away'),('away','home')]:
                a=old[str(g[side+'Id'])];a[0]+=g[side+'Points']>g[other+'Points'];a[1]+=1
    history=defaultdict(float);hp=[p for p in prior if p['season']>=year-3]
    for p in hp:
        for key,value in rank_strength(p).items():history[key]+=value/max(len(hp),1)
    values=[];meta=[]
    for key,t in sorted(ids.items(),key=lambda it:it[1]['team']):
        s=stats[key];n=s[0]+s[1]+s[2];p=prev.get(key,0.);rec=s[6]+s[7];wp=(s[0]+.5*s[2])/n if n else 0.
        sos=np.mean([(stats[o][0]+.5*stats[o][2])/max(sum(stats[o][:3]),1) for o in s[9]]) if s[9] else 0.
        recent=s[8]/max(rec,1)/35
        v=[p,p*p,p-prior_prev.get(key,0.),pre_rank.get(key,0.),last_rank.get(key,0.),s[0]/12,s[1]/12,wp,s[3]/max(n,1)/35,sos,s[4]/5,s[5]/5,s[6],s[7],recent,p*s[7],p*s[6],p*recent,old[key][0]/max(old[key][1],1),history[key],min(n/12,1),float(poll['kind']=='preseason'),float(cutoff is None),float(year>=1989)]
        values.append(v);meta.append({**t,'wins':int(s[0]),'losses':int(s[1]),'ties':int(s[2]),'previousRank':ranks(previous).get(key),'previousStrength':p})
    return np.array(values,dtype=float),meta

def fit(observations,through,alpha=80.,feature_names=None):
    obs=[o for o in observations if o['season']<=through]
    x=np.concatenate([o['x'] for o in obs]);y=np.concatenate([o['y'] for o in obs])
    # Every historical season contributes; recent voting behavior receives more weight.
    weights=np.concatenate([np.full(len(o['y']),2**(-(through-o['season'])/20))/len(o['y'])*(1+3*(o['y']>0)) for o in obs])
    weights*=len(weights)/weights.sum()
    means=np.average(x,axis=0,weights=weights);scales=np.sqrt(np.average((x-means)**2,axis=0,weights=weights));scales=np.maximum(scales,1e-5)
    z=np.column_stack([np.ones(len(x)),(x-means)/scales]);penalty=np.eye(z.shape[1])*alpha;penalty[0,0]=0
    coef=np.linalg.solve(z.T@(z*weights[:,None])+penalty,z.T@(weights*y))
    return {'features':list(feature_names) if feature_names is not None else FEATURES,'means':means.tolist(),'scales':scales.tolist(),'coefficients':coef.tolist(),'trainedThrough':through,'trainingPolls':len(obs),'alpha':alpha}

def predict(model,x,feature_names=None):
    if model['features']!=(list(feature_names) if feature_names is not None else FEATURES):raise ValueError('AP feature schema mismatch')
    return np.column_stack([np.ones(len(x)),(x-model['means'])/model['scales']])@model['coefficients']

def evaluate(model,obs):
    output=[]
    for o in obs:
        scores=predict(model,o['x']);order=np.argsort(-scores,kind='stable');positions={int(i):rank+1 for rank,i in enumerate(order)}
        actual=o['actual'];size=o['size'];top={i for i,r in actual.items() if r<=size};pred=set(order[:size]);baseline=np.argsort(-o['x'][:,0],kind='stable');bp={int(i):j+1 for j,i in enumerate(baseline)}
        output.append({'overlap':len(top&pred)/max(len(top),1),'rankError':np.mean([abs(min(positions[i],size+1)-r) for i,r in actual.items() if r<=size]),'baselineOverlap':len(top&set(baseline[:size]))/max(len(top),1),'baselineRankError':np.mean([abs(min(bp[i],size+1)-r) for i,r in actual.items() if r<=size])})
    return {'polls':len(output),**{k:float(np.mean([o[k] for o in output])) for k in output[0]}} if output else {'polls':0}
