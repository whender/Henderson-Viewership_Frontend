"""Export exact linear power-rating responses for interactive CFP scenarios."""
from dataclasses import replace
from datetime import timedelta
import numpy as np
from cfbpredict.games import completed_games
from cfbpredict.model import ModelConfig, diminishing_margin
from cfbpredict.committee_history import _is_fbs_championship


def scenario_payload(games, predictions, cutoff, model):
    games=sorted({g.id:g for g in games}.values(),key=lambda g:(g.start_date,g.id))
    future=[]; missing=[]
    for g in games:
        if g.completed or g.start_date+timedelta(hours=4)>cutoff: continue
        p=predictions.get(g.id,{}).get('prediction')
        if p and np.isfinite(p['home_win_probability']) and 0<=p['home_win_probability']<=1 and np.isfinite(p['predicted_margin']):
            future.append((g,p))
        elif 'fbs' in (g.home_classification,g.away_classification): missing.append(g.id)
    magnitudes={g.id:max(1,int(np.floor(abs(p['predicted_margin'])+.5))) for g,p in future}
    replacements={g.id:replace(g,completed=True,home_points=magnitudes[g.id],away_points=0) for g,p in future}
    usable=completed_games([replacements.get(g.id,g) for g in games],as_of=cutoff,result_buffer=timedelta(hours=4))
    fbs=[g for g in usable if g.home_classification==g.away_classification=='fbs']
    keys=sorted({k for g in fbs for k in (g.home_key,g.away_key)}); index={k:i for i,k in enumerate(keys)}; n=len(keys)
    if len(fbs)<2: return None
    config=ModelConfig(half_life_days=120,fbs_only=True,result_buffer_hours=4)
    x=np.zeros((len(fbs),2*n+1)); weights=[]; margins=[]
    for i,g in enumerate(fbs):
        x[i,index[g.home_key]]=1;x[i,index[g.away_key]]=-1
        if not g.neutral_site:x[i,n+index[g.home_key]]=1;x[i,-1]=1
        weights.append(.5**(max((cutoff-g.start_date).total_seconds()/86400,0)/120))
        margins.append(diminishing_margin(g.margin,threshold=config.margin_diminishing_threshold,tail_scale=config.margin_tail_scale))
    weights=np.array(weights); diagonal=np.full(2*n+1,config.ridge_alpha);diagonal[n:2*n]=config.team_home_field_prior_weight;diagonal[-1]=config.home_field_prior_weight
    system=x.T@(x*weights[:,None])+np.diag(diagonal)
    response=np.linalg.solve(system,x.T*weights)[:n]
    prior=np.zeros(2*n+1);prior[-1]=config.home_field_prior_weight*config.home_field_prior
    base=response@np.array(margins)+np.linalg.solve(system,prior)[:n]
    changes={g.id:(response[:,i]*(-2*margins[i])).tolist() for i,g in enumerate(fbs) if g.id in replacements}
    teams={}
    for g in usable:
        for side in ('home','away'):
            k=getattr(g,side+'_key')
            if k in index and getattr(g,side+'_classification')=='fbs':teams[k]={'key':k,'team':getattr(g,side+'_team'),'teamId':getattr(g,side+'_id'),'conference':getattr(g,side+'_conference'),'power':float(base[index[k]])}
    probs={g.id:p['home_win_probability'] for g,p in future}
    result=[]
    for g in usable:
        if g.margin==0 or not (g.home_key in teams or g.away_key in teams):continue
        result.append({'id':g.id,'homeKey':g.home_key,'awayKey':g.away_key,'home':g.home_team,'away':g.away_team,'homeId':g.home_id,'awayId':g.away_id,'homeClassification':g.home_classification,'awayClassification':g.away_classification,'date':g.start_date.isoformat(),'neutral':g.neutral_site,'conferenceGame':bool(g.conference_game),'championship':_is_fbs_championship(g),'homeWin':g.margin>0,'projected':g.id in replacements,'probability':probs.get(g.id),'margin':magnitudes.get(g.id,abs(g.margin)),'powerChange':changes.get(g.id)})
    return {'version':1,'teams':[teams[k] for k in keys],'games':result,'model':model.to_dict(),'missingGames':missing,'cutoff':cutoff.isoformat()}
