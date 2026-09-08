"""Fit all historical AP polls and evaluate on strictly later seasons."""
import argparse,gzip,json
from pathlib import Path
import numpy as np
from ap_model import matrix,fit,evaluate,ranks
ROOT=Path(__file__).resolve().parent

def main():
    polls=json.loads(gzip.decompress((ROOT/'ap/polls.json.gz').read_bytes()));games=json.loads(gzip.decompress((ROOT/'ap/games.json.gz').read_bytes()))
    parser=argparse.ArgumentParser();parser.add_argument('--through',type=int,default=2025);args=parser.parse_args();through=args.through
    observations=[];excluded=[];earlier=[]
    for p in polls:
        if p['season']>through:continue
        relevant=[g for g in games if p['season']-1<=g['season']<=p['season']]
        x,teams=matrix(p,earlier[-1] if earlier else None,earlier,relevant)
        lookup={str(t['teamId']):i for i,t in enumerate(teams)};official=ranks(p)
        missing=[k for k in official if k not in lookup]
        if not missing and len(teams)>=p['size']:
            y=np.zeros(len(teams));actual={}
            for k,r in official.items():y[lookup[k]]=max(0,(p['size']+1-r)/p['size']);actual[lookup[k]]=r
            observations.append({'id':p['id'],'season':p['season'],'kind':p['kind'],'size':p['size'],'x':x,'y':y,'actual':actual})
        else:excluded.append({'id':p['id'],'season':p['season'],'missingIds':missing})
        earlier.append(p)
        if p['id']%100==0:print('features',p['id'],flush=True)
    evaluation=[]
    for year in range(2019,through+1):
        model=fit(observations,year-1)
        target=[o for o in observations if o['season']==year and o['kind']=='regular']
        result={'season':year,**evaluate(model,target)};evaluation.append(result);print('evaluation',result,flush=True)
    model=fit(observations,through)
    model['evaluation']=evaluation;model['excludedPolls']=excluded;model['trainingStart']=1936
    model['trainingPollsByYear']={str(y):sum(o['season']==y for o in observations) for y in range(1936,through+1)}
    (ROOT/'ap/model.json').write_text(json.dumps(model,indent=2))
    print('FITTED',model['trainingPolls'],'EXCLUDED',len(excluded),excluded[:10],flush=True)
if __name__=='__main__':main()
