import numpy as np
import ap_voter_features as v
ap=v.ap
METRICS=['expected','residual','over','under','disappointing_win','ranked_disappointing_win','home_disappointing_win','missing']
def closing_consensus(row):
    # One observation per provider. Never use scores or opening spreads to fill gaps.
    books={''.join(c for c in x['provider'].casefold() if c.isalnum()):float(x['spread']) for x in row.get('lines',[]) if isinstance(x.get('spread'),(float,int)) and not isinstance(x['spread'],bool) and np.isfinite(x['spread'])}
    real={p:s for p,s in books.items() if 'consensus' not in p.lower()}
    books=real or books
    return None if not books else {'homeExpected':-float(np.median(list(books.values()))),'providers':books,'range':max(books.values())-min(books.values())}

def market_factors(game,side,market,polls):
    if market is None:return {'missing':1.}
    other='away' if side=='home' else 'home';actual=game[side+'Points']-game[other+'Points'];expected=market['homeExpected']*(1 if side=='home' else -1)
    residual=float(np.clip(actual-expected,-35,35))/35
    p=v.pregame_poll(polls,ap.timestamp(game['startDate']),game['season']);strength=ap.rank_strength(p).get(str(game[side+'Id']),0.)
    disappointment=min(residual,0.) if actual>0 else 0.
    return {'expected':float(np.clip(expected,-49,49))/35,'residual':residual,'over':max(residual,0.),'under':min(residual,0.),'disappointing_win':disappointment,'ranked_disappointing_win':strength*disappointment,'home_disappointing_win':disappointment*int(side=='home' and not game.get('neutralSite')),'missing':0.}

def market_matrix(p,previous,teams,games,factors):
    names=[f'{period}_{m}' for period in ['season','recent'] for m in METRICS];lookup={str(t['teamId']):i for i,t in enumerate(teams)};idx={n:i for i,n in enumerate(names)};out=np.zeros((len(teams),len(names)))
    if not p.get('cutoff'):return out
    cutoff=ap.timestamp(p['cutoff']);prevcut=ap.timestamp(previous['cutoff']) if previous and previous.get('cutoff') else ap.timestamp(f"{p['season']}-01-01T00:00:00+00:00")
    for g in games:
        if g['season']!=p['season'] or not ap.finished(g,cutoff):continue
        for side in ['home','away']:
            i=lookup.get(str(g[side+'Id']))
            if i is None:continue
            for period in ['season']+(['recent'] if ap.timestamp(g['startDate'])>=prevcut else []):
                for name,value in factors[(g['id'],side)].items():out[i,idx[f'{period}_{name}']]+=value/(12 if period=='season' else 1)
    return out

