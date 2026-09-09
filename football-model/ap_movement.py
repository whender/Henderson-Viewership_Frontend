from pathlib import Path
import json
import numpy as np
import ap_market as e
import ap_poll_context as poll_context
v=e.v;ap=e.ap
VERSION="ap-movement-v3"
CONTEXT=['early','early_previous','early_underperformance','early_disappointing_win','early_home_disappointment','top10_disappointment','early_top10_disappointment','peer_margin','peer_surprise','peer_ranked_wins','peer_margin_gap','peer_surprise_gap','impressive_peers','above_margin','above_surprise']

def context_features(base,market,teams):
    """Only pre-release features: nearby teams defined by previous AP rank."""
    ix={m:i for i,m in enumerate(e.METRICS)};recent=market[:,len(e.METRICS):]
    n=base[:,5]*12+base[:,6]*12;early=np.maximum(0,1-n/4)
    previous=np.array([t['previousRank'] or 40 for t in teams]);margin=base[:,14];surprise=recent[:,ix['residual']]
    quality_idx=[len(ap.FEATURES)+v.GROUPS['ap'].index('recent_ap_'+b+'_win') for b in ['top5','6to10','11to25']]
    quality=base[:,quality_idx].sum(axis=1);out=[]
    for i,p in enumerate(previous):
        below=np.where((previous>p)&(previous<=min(p+5,25)))[0];above=np.where((previous<p)&(previous>=max(p-5,1)))[0]
        def avg(x,ids):return float(x[ids].mean()) if len(ids) else 0.
        pm=avg(margin,below);ps=avg(surprise,below);dw=recent[i,ix['disappointing_win']]
        impressive=float(np.sum((quality[below]>0)|((margin[below]>.6)&(surprise[below]>0))))/5
        out.append([early[i],early[i]*base[i,0],early[i]*min(surprise[i],0),early[i]*dw,early[i]*recent[i,ix['home_disappointing_win']],dw*int(p<=10),dw*early[i]*int(p<=10),pm,ps,avg(quality,below),pm-margin[i],ps-surprise[i],impressive,avg(margin,above),avg(surprise,above)])
    return np.array(out)

class BoostedMovement:
    """Small fixed histogram gradient boosting model; quantiles fitted on training only."""
    def __init__(self,trees=100,depth=3,min_leaf=45,rate=.05):self.n_trees=trees;self.depth=depth;self.min_leaf=min_leaf;self.rate=rate
    def fit(self,x,y,w):
        self.edges=[np.unique(np.quantile(x[:,j],np.linspace(0,1,25)[1:-1])) for j in range(x.shape[1])]
        bins=self.bin(x);self.bias=float(np.average(y,weights=w));pred=np.full(len(y),self.bias);self.trees=[]
        def build(ids,residual,depth):
            wt=w[ids];total=wt.sum();weighted=(wt*residual[ids]);mean=weighted.sum()/total
            if depth==0 or len(ids)<2*self.min_leaf:return float(mean)
            best=None;best_gain=0.
            for j in range(x.shape[1]):
                count=np.bincount(bins[ids,j],minlength=25).cumsum()[:-1];leftw=np.bincount(bins[ids,j],weights=wt,minlength=25).cumsum()[:-1];lefts=np.bincount(bins[ids,j],weights=weighted,minlength=25).cumsum()[:-1]
                valid=(count>=self.min_leaf)&(len(ids)-count>=self.min_leaf)&(leftw>0)&(total-leftw>0)
                gain=np.where(valid,lefts**2/np.maximum(leftw,1e-12)+(weighted.sum()-lefts)**2/np.maximum(total-leftw,1e-12)-weighted.sum()**2/total,-np.inf)
                k=int(np.argmax(gain))
                if gain[k]>best_gain:best_gain=float(gain[k]);best=(j,k)
            if best is None:return float(mean)
            j,k=best;mask=bins[ids,j]<=k
            return (j,k,build(ids[mask],residual,depth-1),build(ids[~mask],residual,depth-1))
        for _ in range(self.n_trees):
            tree=build(np.arange(len(y)),y-pred,self.depth);self.trees.append(tree);pred+=self.rate*self.apply(tree,bins)
        return self
    def bin(self,x):return np.column_stack([np.searchsorted(edge,x[:,j],side='right') for j,edge in enumerate(self.edges)]).astype(np.uint8)
    def apply(self,tree,bins):
        out=np.zeros(len(bins))
        def walk(t,ids):
            if isinstance(t,float):out[ids]=t;return
            j,k,left,right=t;mask=bins[ids,j]<=k;walk(left,ids[mask]);walk(right,ids[~mask])
        walk(tree,np.arange(len(bins)));return out
    def predict(self,x):
        b=self.bin(x);return self.bias+sum((self.rate*self.apply(t,b) for t in self.trees),np.zeros(len(x)))


FEATURES=ap.FEATURES+v.GROUPS['ap']+[f'{period}_{m}' for period in ['season','recent'] for m in e.METRICS]+CONTEXT+poll_context.VOTE_FEATURES+poll_context.CONF_FEATURES

def matrix(p,previous,earlier,games,market,candidates=None,votes=None):
    games=list({g['id']:g for g in games}.values())
    x,teams=ap.matrix(p,previous,earlier,games,candidates)
    usable=[g for g in games if g['season']==p['season'] and p.get('cutoff') and ap.finished(g,ap.timestamp(p['cutoff']))]
    factors={(g['id'],side):v.game_factors(g,side,earlier,{}) for g in usable for side in ['home','away']}
    mf={(g['id'],side):e.market_factors(g,side,market.get(g['id']),earlier) for g in usable for side in ['home','away']}
    extra,fixed=v.additions(p,previous,teams,games,factors);x[:,10:12]=fixed
    base=np.column_stack([x,extra['ap']]);m=e.market_matrix(p,previous,teams,games,mf)
    vf,cf=poll_context.features(teams,previous,p,votes or {})
    return np.column_stack([base,m,context_features(base,m,teams),vf,cf]),teams

def fit(observations,through):
    obs=[o for o in observations if o['season']<=through and o['kind']=='regular']
    x=np.concatenate([o['x'] for o in obs]);y=np.concatenate([o['y']-o['x'][:,0] for o in obs])
    weights=[]
    for o in obs:
        rare=np.array([bool(t['previousRank'] and t['previousRank']<=10 and o['x'][i,12]>0 and o['x'][i,13]==0 and o['actual'].get(i,26)-t['previousRank']>=3) for i,t in enumerate(o['teams'])])
        weights.append(np.full(len(o['y']),2**(-(through-o['season'])/20))/len(o['y'])*(1+3*(o['y']>0))*(1+7*rare))
    w=np.concatenate(weights);w*=len(w)/w.sum();tree=BoostedMovement(min_leaf=20).fit(x,y,w)
    return {'version':VERSION,'features':FEATURES,'trainedThrough':through,'trainingPolls':len(obs),'trainingStart':2015,'bias':tree.bias,'rate':tree.rate,'edges':[a.tolist() for a in tree.edges],'trees':tree.trees}

def predict(model,x):
    if model['version']!=VERSION or model['features']!=FEATURES:raise ValueError('AP movement feature schema mismatch')
    tree=BoostedMovement();tree.bias=model['bias'];tree.rate=model['rate'];tree.edges=[np.array(a) for a in model['edges']];tree.trees=model['trees']
    return x[:,0]+tree.predict(x)

def win_context(p,prev,teams,games):
    cutoff=ap.timestamp(p['cutoff']);start=ap.timestamp(prev['cutoff']) if prev and prev.get('cutoff') else ap.timestamp(f"{p['season']}-01-01T00:00:00+00:00")
    results={str(t['teamId']):[] for t in teams}
    for g in games:
        if g['season']!=p['season'] or not ap.finished(g,cutoff) or ap.timestamp(g['startDate'])<start:continue
        for side,other in [('home','away'),('away','home')]:
            if str(g[side+'Id']) in results:results[str(g[side+'Id'])].append(g[side+'Points']-g[other+'Points'])
    return np.array([min(results[str(t['teamId'])]) if results[str(t['teamId'])] else 0 for t in teams])


def comfortable_win_scores(scores,previous,margins):
    """Shrink negative score movement after big wins; peer-driven rank drops remain possible."""
    strength=np.clip((np.asarray(margins)-14)/28,0,1)
    return scores+np.maximum(previous-scores,0)*strength

def ranked(model,p,previous,earlier,games,market,candidates,votes=None):
    games=list({g['id']:g for g in games}.values())
    x,teams=matrix(p,previous,earlier,games,market,candidates,votes);raw=predict(model,x)
    margins=win_context(p,previous,teams,games)
    scores=comfortable_win_scores(raw,x[:,0],margins);order=np.argsort(-scores,kind='stable');output=[]
    for rank,i in enumerate(order[:40],1):
        t=teams[i];drivers=[{'feature':'previous_ap','label':f"Previous AP: {t['previousRank'] or 'Unranked'}",'contribution':None,'detail':'Starting poll position'}, {'feature':'recent_results','label':f"Since previous poll: {int(x[i,12])} wins, {int(x[i,13])} losses",'contribution':None,'detail':'Observed or scenario results'}]
        prior_votes=(votes or {}).get(str(previous['id'])) if previous else None
        points=next((r['points'] for r in prior_votes or [] if str(r['teamId'])==str(t['teamId'])),0)
        drivers.extend([{'feature':'prior_votes','label':'Previous AP vote points','contribution':None,'detail':str(points) if prior_votes is not None else 'Unavailable'}, {'feature':'conference','label':'Conference','contribution':None,'detail':poll_context.conference_group(t.get('conference'))}])
        residual=x[i,FEATURES.index('recent_residual')]*35
        missing=int(x[i,FEATURES.index('recent_missing')]);played=int(x[i,12]+x[i,13])
        label='No new games since previous poll' if not played else 'Vegas lines unavailable for recent games' if missing>=played else f'Versus Vegas expectations: {residual:+.1f} points'
        drivers.append({'feature':'vegas_residual','label':label,'contribution':None,'detail':f'Sum for games with lines; {missing} recent games without lines'})
        if scores[i]>raw[i]:drivers.append({'feature':'comfortable_win','label':'Comfortable-win adjustment','contribution':None,'detail':f'Negative movement softened after wins by at least {margins[i]:g} points'})
        output.append({**t,'rank':rank,'movement':t['previousRank']-rank if t['previousRank'] else None,'drivers':drivers})
    return output
