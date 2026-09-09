"""Export public, key-free inputs for exact browser-side AP scenario inference."""
import ap_movement as m


def build_simulator(model,target,previous,polls,games,projected,market,candidates,votes,rows,as_of):
    x,teams=m.matrix(target,previous,polls,games,market,candidates,votes)
    top={str(t['teamId']) for t in rows[:40]}
    defaults={g['id']:g for g in projected}
    cutoff=m.ap.timestamp(target['cutoff']);now=m.ap.timestamp(as_of)
    prevcut=m.ap.timestamp(previous['cutoff'])
    output=[]
    for g in games:
        if g['season']!=target['season']:continue
        start=m.ap.timestamp(g['startDate'])
        if start+m.ap.timedelta(hours=4)>cutoff:continue
        actual=m.ap.finished(g,cutoff)
        future=not g.get('completed') and start>now
        editable=future and bool({str(g['homeId']),str(g['awayId'])}&top)
        default=defaults[g['id']]
        predicted=not actual and m.ap.finished(default,cutoff)
        if not actual and not predicted and not editable:continue
        pre=m.v.pregame_poll(polls,start,g['season']);strength=m.ap.rank_strength(pre);ranks=m.ap.ranks(pre)
        def bucket(side):
            other='away' if side=='home' else 'home';rank=ranks.get(str(g[other+'Id']))
            return 'fcs' if g.get(other+'Classification')=='fcs' else 'top5' if rank and rank<=5 else '6to10' if rank and rank<=10 else '11to25' if rank and rank<=25 else 'unranked'
        output.append({**{k:g.get(k) for k in ['id','startDate','homeId','awayId','homeTeam','awayTeam','neutralSite']},
            'completed':actual,'editable':editable,'recent':start>=prevcut,
            'homePoints':default['homePoints'] if actual or predicted else None,'awayPoints':default['awayPoints'] if actual or predicted else None,
            'homeBucket':bucket('home'),'awayBucket':bucket('away'),
            'homeRankedOpponent':str(g['awayId']) in ranks,'awayRankedOpponent':str(g['homeId']) in ranks,
            'homeStrength':strength.get(str(g['homeId']),0.),'awayStrength':strength.get(str(g['awayId']),0.),
            'homeExpected':market[g['id']]['homeExpected'] if market.get(g['id']) else None})
    return {'schemaVersion':1,'asOf':as_of,'pollId':previous['id'],'releaseDate':target['cutoff'],'modelVersion':model['version'],
        'model':model,'teams':teams,'baseFeatures':x.tolist(),'games':sorted(output,key=lambda g:(g['startDate'],g['id']))}
