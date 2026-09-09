"""Fit the preseason-only model from reviewed, dated annual feature snapshots."""
import argparse,json,gzip
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from ap_model import fit,predict
from ap_preseason import FEATURES,HISTORY,load_inputs,preseason_scores
from ap_preseason_ranker import history_features,fit_pairwise,VERSION
ROOT=Path(__file__).parent

def evaluate(model,o):
    order=np.argsort(-preseason_scores(model,o['x'],o.get('extended')),kind='stable')
    positions={int(i):r+1 for r,i in enumerate(order)}
    actual=o['actual'];n=o['size']
    baseline=np.argsort(-o['x'][:,0],kind='stable');bp={int(i):r+1 for r,i in enumerate(baseline)}
    return {'season':o['season'],'polls':1,'overlap':len(set(order[:n])&set(actual))/len(actual),
        'rankError':float(np.mean([abs(min(positions[i],n+1)-r) for i,r in actual.items()])),
        'baselineOverlap':len(set(baseline[:n])&set(actual))/len(actual),
        'baselineRankError':float(np.mean([abs(min(bp[i],n+1)-r) for i,r in actual.items()]))}

def main():
    p=argparse.ArgumentParser();p.add_argument('--season',type=int,required=True)
    p.add_argument('--inputs',type=Path,default=ROOT/'ap/preseason_features.json.gz');args=p.parse_args()
    data=load_inputs(args.inputs);obs=data['observations'];year=args.season
    polls=json.loads(gzip.decompress((ROOT/'ap/polls.json.gz').read_bytes()))
    for o in obs:o['extended']=np.column_stack([o['x'],history_features(o['teams'],o['season'],polls)])
    dates=json.loads((ROOT/'ap/preseason_dates.json').read_text())['dates']
    if str(year) not in dates:raise ValueError('Add a verified preseason release date first')
    for o in obs:
        if o.get('releaseDate')!=dates.get(str(o['season'])) or not o.get('releaseDate'):
            raise ValueError('Preseason input dates do not match verified poll dates; rebuild inputs')
    training=[o for o in obs if o['season']<year]
    if len(training)<3:raise ValueError('At least three prior preseason polls required')
    model=fit(training,year-1,feature_names=FEATURES)
    model.update(version=VERSION,reranker=fit_pairwise(training,'extended',year-1))
    fallback=fit([{**o,'x':o['x'][:,:4]} for o in training],year-1,feature_names=HISTORY)
    target=next((o for o in obs if o['season']==year),None)
    evaluation=[]
    for o in training:
        if o['season']<2019:continue
        prior=fit(training,o['season']-1,feature_names=FEATURES)
        prior.update(version=VERSION,reranker=fit_pairwise(training,'extended',o['season']-1))
        evaluation.append(evaluate(prior,o))
    keys=['overlap','rankError','baselineOverlap','baselineRankError']
    stats={k:float(np.mean([e[k] for e in evaluation])) for k in keys};stats['polls']=len(evaluation)
    now=datetime.now(timezone.utc)
    result={'schemaVersion':1,'season':year,'releaseDate':dates[str(year)],'generatedAt':now.isoformat(),
        'forecastSource':'Historical reconstruction' if now.date().isoformat()>=dates[str(year)] else 'Pre-release forecast',
        'inputBasis':data['sourceAssumption'],'inputDateSource':data['dateSource'],'model':model,'fallback':fallback,'evaluation':evaluation,'overallEvaluation':stats,
        'snapshot':{'season':year,'x':target['x'].tolist(),'extended':target['extended'].tolist(),'teams':target['teams']} if target else None}
    path=ROOT/'ap/preseason_model.json';path.write_text(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n')
    print('Preseason validation',stats)
    if target:print('Current-season reconstruction',evaluate(model,target))
if __name__=='__main__':main()
