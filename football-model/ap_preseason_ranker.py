"""Temporal preseason reputation features and pairwise ordering of a fixed Top 25."""
import numpy as np
import ap_model as ap
VERSION="ap-preseason-pairwise-v1"
HISTORY_EXTRA=['previous_preseason','two_year_preseason','three_year_preseason_mean','five_year_preseason_mean','five_year_preseason_presence','previous_preseason_minus_final','best_recent_preseason','previous_final_x_preseason']

def history_features(teams,year,prior):
    # Filter by year here as defense in depth: caller cannot inject target-year rankings.
    pre={p['season']:ap.rank_strength(p) for p in prior if p['season']<year and p['kind']=='preseason'}
    last=next((p for p in reversed(prior) if p['season']<year),None);final=ap.rank_strength(last);rows=[]
    for t in teams:
        k=str(t['teamId']);values=[pre.get(y,{}).get(k,0.) for y in range(year-5,year)];prev=pre.get(year-1,{}).get(k,0.);f=final.get(k,0.)
        rows.append([prev,pre.get(year-2,{}).get(k,0.),np.mean(values[-3:]),np.mean(values),sum(v>0 for v in values)/5,prev-f,max(values),f*prev])
    return np.array(rows)

def fit_pairwise(obs,key,through):
    train=[o for o in obs if o['season']<=through];x=np.concatenate([o[key] for o in train]);means=x.mean(axis=0);scales=np.maximum(x.std(axis=0),1e-5);diff=[];weights=[]
    for o in train:
        z=(o[key]-means)/scales;ranked=sorted(o['actual'],key=o['actual'].get);unranked=[i for i in range(len(z)) if i not in o['actual']];pairs=[]
        for a in ranked:
            pairs.extend((a,b) for b in ranked if o['actual'][b]>o['actual'][a])
            pairs.extend((a,b) for b in unranked)
        diff.extend(z[a]-z[b] for a,b in pairs);weights.extend([2**(-(through-o['season'])/20)/len(pairs)]*len(pairs))
    d=np.array(diff);w=np.array(weights);w*=len(w)/w.sum();beta=np.zeros(d.shape[1]);alpha=80.
    for _ in range(20):
        p=1/(1+np.exp(-np.clip(d@beta,-30,30)));grad=d.T@(w*(p-1))+alpha*beta;h=d.T@(d*(w*p*(1-p))[:,None])+np.eye(len(beta))*alpha;step=np.linalg.solve(h,grad);beta-=step
        if np.max(np.abs(step))<1e-6:break
    return {'means':means.tolist(),'scales':scales.tolist(),'coefficients':beta.tolist(),'trainedThrough':through,'trainingPolls':len(train),'features':HISTORY_EXTRA,'alpha':alpha}

def selection_then_pairwise(base,comparison,size=25):
    order=np.argsort(-base,kind='stable');selected=order[:size]
    reranked=selected[np.argsort(-comparison[selected],kind='stable')]
    final=np.concatenate([reranked,order[size:]])
    scores=np.empty(len(base));scores[final]=np.arange(len(base),0,-1)
    return scores

def predict_pairwise(model,x):
    if model['features'] != HISTORY_EXTRA:
        raise ValueError('Preseason comparison feature schema mismatch')
    return ((x-model['means'])/model['scales'])@np.asarray(model['coefficients'])
