from datetime import datetime,timedelta,timezone
import numpy as np
import ap_model as ap
GROUPS={
 'score': [f'{period}_{loc}_{metric}' for period in ['season','recent'] for loc in ['home','away','neutral'] for metric in ['win','loss','margin','close_win','big_win']],
 'ap': [f'{period}_ap_{bucket}_{metric}' for period in ['season','recent'] for bucket in ['top5','6to10','11to25','unranked','fcs'] for metric in ['win','loss','margin','close_home_win']],
 'eff': [f'{period}_eff_{metric}' for period in ['season','recent'] for metric in ['opponent','win_quality','loss_quality','margin_quality','own_strength','missing']],
 'effbucket': [f'{period}_eff_{bucket}_{metric}' for period in ['season','recent'] for bucket in ['top10','11to25','26to60','61plus','missing'] for metric in ['win','loss','margin']],
}

def poll_available(p):
    # Exact publication timestamps are absent. Use the end of the release date,
    # never the pre-publication feature cutoff, when selecting the pregame poll.
    return datetime.fromisoformat(p['releaseDate']+'T00:00:00+00:00')+timedelta(days=1) if p.get('releaseDate') else None

def pregame_poll(polls,kickoff,year):
    eligible=[p for p in polls if p['season']==year and poll_available(p) is not None and poll_available(p)<=kickoff]
    return max(eligible,key=poll_available) if eligible else None

def game_factors(g,side,polls,eff):
    other='away' if side=='home' else 'home';margin=g[side+'Points']-g[other+'Points'];m=float(np.clip(margin,-35,35))/35
    loc='neutral' if g.get('neutralSite') else side
    pre=pregame_poll(polls,ap.timestamp(g['startDate']),g['season']);rank=ap.ranks(pre).get(str(g[other+'Id']))
    bucket='fcs' if g.get(other+'Classification')=='fcs' else 'top5' if rank and rank<=5 else '6to10' if rank and rank<=10 else '11to25' if rank and rank<=25 else 'unranked'
    metrics={'win':float(margin>0),'loss':float(margin<0),'margin':m,'close_win':float(0<margin<=7),'big_win':float(margin>=21),'close_home_win':float(0<margin<=7 and loc=='home')}
    values={'score':{},'ap':{},'eff':{},'effbucket':{}}
    for metric in ['win','loss','margin','close_win','big_win']:values['score'][f'{loc}_{metric}']=metrics[metric]
    for metric in ['win','loss','margin','close_home_win']:values['ap'][f'{bucket}_{metric}']=metrics[metric]
    snap=eff.get(str(g['id']),{});opp=snap.get(other);own=snap.get(side)
    if snap:assert ap.timestamp(snap['asOf'])<=ap.timestamp(g['startDate'])
    if opp:
        z=opp['z'];values['eff']={'opponent':z,'win_quality':metrics['win']*z,'loss_quality':metrics['loss']*z,'margin_quality':m*z,'own_strength':own['z'] if own else 0.}
        b='top10' if opp['rank']<=10 else '11to25' if opp['rank']<=25 else '26to60' if opp['rank']<=60 else '61plus'
    else:values['eff']={'missing':1.};b='missing'
    for metric in ['win','loss','margin']:values['effbucket'][f'{b}_{metric}']=metrics[metric]
    return values,rank

def additions(p,previous,teams,games,factors):
    result={group:np.zeros((len(teams),len(names))) for group,names in GROUPS.items()};fixed=np.zeros((len(teams),2))
    if not p.get('cutoff'):return result,fixed
    cutoff=ap.timestamp(p['cutoff']);prevcut=ap.timestamp(previous['cutoff']) if previous and previous.get('cutoff') else datetime(p['season'],1,1,tzinfo=timezone.utc)
    lookup={str(t['teamId']):i for i,t in enumerate(teams)};indices={group:{name:i for i,name in enumerate(names)} for group,names in GROUPS.items()}
    for g in games:
        if g['season']!=p['season'] or not ap.finished(g,cutoff):continue
        for side in ['home','away']:
            i=lookup.get(str(g[side+'Id']))
            if i is None:continue
            values,rank=factors[(g['id'],side)]
            if rank and rank<=25:
                other='away' if side=='home' else 'home';margin=g[side+'Points']-g[other+'Points'];fixed[i,0]+=float(margin>0)/5;fixed[i,1]+=float(margin<0)/5
            periods=['season']+(['recent'] if ap.timestamp(g['startDate'])>=prevcut else [])
            for period in periods:
                for group,entries in values.items():
                    prefix='' if group=='score' else 'ap_' if group=='ap' else 'eff_'
                    for name,value in entries.items():result[group][i,indices[group][f'{period}_{prefix}{name}']]+=value/(12 if period=='season' else 1)
    return result,fixed

