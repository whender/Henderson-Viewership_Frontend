"""Train the production AP movement model from earlier weekly polls only."""
import json,gzip,argparse
from pathlib import Path
import numpy as np
import ap_movement as m
ROOT=Path(__file__).parent
polls=json.loads(gzip.decompress((ROOT/'ap/polls.json.gz').read_bytes()));games=json.loads(gzip.decompress((ROOT/'ap/games.json.gz').read_bytes()))
market={r['id']:m.e.closing_consensus(r) for r in json.loads(gzip.decompress((ROOT/'ap/lines.json.gz').read_bytes()))}
votes=json.loads(gzip.decompress((ROOT/'ap/receiving_votes.json.gz').read_bytes()))
parser=argparse.ArgumentParser();parser.add_argument('--through',type=int,default=2025);through=parser.parse_args().through;obs=[];earlier=[]
for p in polls:
    if p['season']>through:continue
    if p['season']>=2015 and p['kind']=='regular':
        x,teams=m.matrix(p,earlier[-1] if earlier else None,earlier,[g for g in games if p['season']-1<=g['season']<=p['season']],market,votes=votes)
        lookup={str(t['teamId']):i for i,t in enumerate(teams)};official=m.ap.ranks(p)
        if not all(k in lookup for k in official):raise ValueError('Missing ranked team in training')
        actual={lookup[k]:r for k,r in official.items()};y=np.zeros(len(teams))
        for i,r in actual.items():y[i]=(26-r)/25
        obs.append({'season':p['season'],'kind':p['kind'],'x':x,'teams':teams,'y':y,'actual':actual})
    earlier.append(p)
model=m.fit(obs,through)
(ROOT/'ap/movement_model.json').write_text(json.dumps(model,separators=(',',':'),allow_nan=False)+'\n')
print('Trained',model['trainingPolls'],'weekly polls through',through)
